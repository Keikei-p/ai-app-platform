from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import json
import re

from .config import DATA_DIR
from .knowledge_store import KnowledgeItem, VerifiedKnowledgeStore
from .redaction import redact_sensitive
from .research_guard import ResearchGuard
from .secrets_guard import SecretsGuard, SECRET_VALUE_PATTERNS


@dataclass(frozen=True)
class KnowledgeBatchResult:
    accepted: int
    rejected: int
    deduplicated: int
    candidate_promotions: int
    knowledge_ids: tuple[str, ...]
    rejections: tuple[str, ...]
    created_at: str

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["knowledge_ids"] = list(self.knowledge_ids)
        data["rejections"] = list(self.rejections)
        return data


_SENSITIVE_CONTENT_PATTERNS = (
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(
        r"""(?ix)\b(?:api[_-]?key|secret|access[_-]?token|refresh[_-]?token|client[_-]?secret|password)\b
        \s*[:=]\s*[\"'][^\"'\r\n]{12,}[\"']"""
    ),
)
_PII_PATTERNS = (
    re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.I),
    re.compile(r"(?<!\d)(?:\+?81[- ]?)?0\d{1,4}[- ]?\d{1,4}[- ]?\d{3,4}(?!\d)"),
)


class KnowledgeFactory:
    """Bounded bulk intake for large knowledge imports.

    Factory intake can create untrusted/candidate knowledge only. It can never
    mark content verified; verified promotion stays behind real project evidence
    or explicit human review in the existing Knowledge Store.
    """

    MAX_BATCH_ITEMS = 500
    MAX_STATEMENT_CHARS = 12_000
    MAX_SOURCE_CONTENT_CHARS = 120_000

    def __init__(
        self,
        knowledge: VerifiedKnowledgeStore | None = None,
        research_guard: ResearchGuard | None = None,
        secrets_guard: SecretsGuard | None = None,
        audit_path: Path | None = None,
    ):
        self.knowledge = knowledge or VerifiedKnowledgeStore()
        self.research_guard = research_guard or ResearchGuard()
        self.secrets_guard = secrets_guard or SecretsGuard()
        self.audit_path = audit_path or (DATA_DIR / "knowledge_factory_audit.jsonl")
        self.audit_path.parent.mkdir(parents=True, exist_ok=True)

    def ingest_batch(self, rows: list[dict[str, Any]]) -> KnowledgeBatchResult:
        if not isinstance(rows, list):
            raise ValueError("knowledge batch must be an array")
        if len(rows) > self.MAX_BATCH_ITEMS:
            raise ValueError(f"knowledge batch exceeds {self.MAX_BATCH_ITEMS} items")

        rejected = 0
        deduplicated = 0
        rejection_reasons: list[str] = []
        prepared: list[dict[str, Any]] = []
        existing_hashes = {item.content_hash for item in self.knowledge.list()}
        seen_hashes: set[str] = set()

        for index, row in enumerate(rows):
            if not isinstance(row, dict):
                rejected += 1
                rejection_reasons.append(f"item[{index}]:not_object")
                continue
            try:
                topic = str(row.get("topic") or "").strip()
                statement = str(row.get("statement") or "").strip()
                sources = row.get("sources")
                if not topic or not statement:
                    raise ValueError("topic and statement are required")
                if len(statement) > self.MAX_STATEMENT_CHARS:
                    raise ValueError("statement exceeds intake size limit")
                if not isinstance(sources, list) or not sources:
                    raise ValueError("at least one source is required")

                digest = self.knowledge._hash(topic[:180], statement[:4000])
                if digest in seen_hashes or digest in existing_hashes:
                    deduplicated += 1
                seen_hashes.add(digest)

                safe_sources: list[dict[str, str]] = []
                for source in sources:
                    if not isinstance(source, dict):
                        raise ValueError("source must be an object")
                    content = str(source.get("content") or "")
                    if len(content) > self.MAX_SOURCE_CONTENT_CHARS:
                        raise ValueError("source content exceeds intake size limit")
                    inspected = self.research_guard.inspect(
                        source_kind=str(source.get("kind") or "unknown"),
                        locator=str(source.get("locator") or ""),
                        title=str(source.get("title") or ""),
                        content=content,
                    )
                    if not inspected.safe_for_reasoning:
                        raise ValueError(
                            "source quarantined:" + ",".join(inspected.indicators)
                        )
                    if self._contains_sensitive_content(content):
                        raise ValueError("source contains secret or PII-like content")
                    safe_sources.append({
                        "kind": inspected.source_kind,
                        "locator": inspected.locator,
                        "title": inspected.title,
                        "version": str(source.get("version") or "")[:120],
                        "retrieved_at": str(source.get("retrieved_at") or inspected.retrieved_at)[:80],
                    })

                self._reject_secret_like_payload(topic, statement, safe_sources)
                if self._contains_sensitive_content(statement):
                    raise ValueError("statement contains secret or PII-like content")
                prepared.append({
                    "topic": topic,
                    "statement": statement,
                    "sources": safe_sources,
                })
            except Exception as exc:
                rejected += 1
                rejection_reasons.append(
                    f"item[{index}]:" + redact_sensitive(
                        f"{type(exc).__name__}:{exc}"
                    )[:300]
                )

        items = self.knowledge.ingest_many(prepared) if prepared else []
        knowledge_ids = tuple(dict.fromkeys(item.knowledge_id for item in items))
        requested_ids = set(knowledge_ids)
        stored = {
            item.knowledge_id: item
            for item in self.knowledge.list()
            if item.knowledge_id in requested_ids
        }
        promotable: list[str] = []
        for knowledge_id, item in stored.items():
            if item.trust_level != "untrusted":
                continue
            locators = {
                str(source.get("locator") or "").strip()
                for source in item.sources
                if str(source.get("locator") or "").strip()
            }
            if len(locators) >= 2:
                promotable.append(knowledge_id)
        promoted = self.knowledge.promote_candidates(promotable)

        result = KnowledgeBatchResult(
            accepted=len(prepared),
            rejected=rejected,
            deduplicated=deduplicated,
            candidate_promotions=sum(
                1 for item in promoted if item.trust_level == "candidate"
            ),
            knowledge_ids=knowledge_ids,
            rejections=tuple(rejection_reasons[:100]),
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        self._audit(result)
        return result

    def _reject_secret_like_payload(
        self,
        topic: str,
        statement: str,
        sources: list[dict[str, str]],
    ) -> None:
        payload = {
            "topic": topic,
            "statement": statement,
            "sources": sources,
        }
        audit = self.secrets_guard.audit_settings(payload)
        if not audit.passed:
            raise ValueError("secret-like fields are not allowed in knowledge intake")
        combined = json.dumps(payload, ensure_ascii=False)
        if any(pattern.search(combined) for pattern in SECRET_VALUE_PATTERNS):
            raise ValueError("secret-like values are not allowed in knowledge intake")

    @staticmethod
    def _contains_sensitive_content(text: str) -> bool:
        raw = str(text)
        return any(
            pattern.search(raw)
            for pattern in (*_SENSITIVE_CONTENT_PATTERNS, *_PII_PATTERNS)
        )

    def _audit(self, result: KnowledgeBatchResult) -> None:
        payload = result.to_dict()
        with self.audit_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False) + "\n")
