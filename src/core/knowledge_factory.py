from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import json

from .config import DATA_DIR
from .knowledge_store import KnowledgeItem, VerifiedKnowledgeStore
from .redaction import redact_sensitive
from .research_guard import ResearchGuard
from .secrets_guard import SecretsGuard


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

        accepted = 0
        rejected = 0
        deduplicated = 0
        candidate_promotions = 0
        ids: list[str] = []
        rejection_reasons: list[str] = []
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
                if digest in seen_hashes:
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
                    safe_sources.append({
                        "kind": inspected.source_kind,
                        "locator": inspected.locator,
                        "title": inspected.title,
                    })

                self._reject_secret_like_payload(topic, statement, safe_sources)
                item: KnowledgeItem | None = None
                for source in safe_sources:
                    item = self.knowledge.ingest(
                        topic=topic,
                        statement=statement,
                        source_kind=source["kind"],
                        source_locator=source["locator"],
                        source_title=source["title"],
                    )
                assert item is not None
                accepted += 1
                ids.append(item.knowledge_id)

                locators = {
                    str(source.get("locator") or "").strip()
                    for source in item.sources
                    if str(source.get("locator") or "").strip()
                }
                if item.trust_level == "untrusted" and len(locators) >= 2:
                    item = self.knowledge.promote_candidate(item.knowledge_id)
                    candidate_promotions += 1

            except Exception as exc:
                rejected += 1
                rejection_reasons.append(
                    f"item[{index}]:" + redact_sensitive(f"{type(exc).__name__}:{exc}")[:300]
                )

        result = KnowledgeBatchResult(
            accepted=accepted,
            rejected=rejected,
            deduplicated=deduplicated,
            candidate_promotions=candidate_promotions,
            knowledge_ids=tuple(dict.fromkeys(ids)),
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

    def _audit(self, result: KnowledgeBatchResult) -> None:
        payload = result.to_dict()
        with self.audit_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False) + "\n")
