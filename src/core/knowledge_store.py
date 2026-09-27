from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import hashlib
import json
import uuid

from .config import DATA_DIR
from .redaction import redact_sensitive


TRUST_LEVELS = {"untrusted", "candidate", "verified"}
VERIFICATION_TYPES = {"tests", "design", "security", "build", "human_review"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class KnowledgeItem:
    knowledge_id: str
    created_at: str
    updated_at: str
    topic: str
    statement: str
    trust_level: str
    sources: tuple[dict[str, str], ...]
    evidence_refs: tuple[str, ...]
    verified_by: tuple[str, ...]
    content_hash: str

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["sources"] = list(self.sources)
        data["evidence_refs"] = list(self.evidence_refs)
        data["verified_by"] = list(self.verified_by)
        return data


class VerifiedKnowledgeStore:
    """Three-stage knowledge store: untrusted -> candidate -> verified.

    Internet/source material is never directly promoted to verified. Verification
    requires platform evidence such as tests, security/design checks, builds, or
    explicit human review.
    """

    def __init__(self, path: Path | None = None):
        self.path = path or (DATA_DIR / "verified_knowledge.json")
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def _read(self) -> list[KnowledgeItem]:
        if not self.path.is_file():
            return []
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except Exception:
            return []
        rows: list[KnowledgeItem] = []
        for item in raw if isinstance(raw, list) else []:
            try:
                rows.append(
                    KnowledgeItem(
                        knowledge_id=str(item["knowledge_id"]),
                        created_at=str(item["created_at"]),
                        updated_at=str(item["updated_at"]),
                        topic=str(item["topic"]),
                        statement=str(item["statement"]),
                        trust_level=str(item["trust_level"]),
                        sources=tuple(item.get("sources") or ()),
                        evidence_refs=tuple(str(x) for x in item.get("evidence_refs") or ()),
                        verified_by=tuple(str(x) for x in item.get("verified_by") or ()),
                        content_hash=str(item["content_hash"]),
                    )
                )
            except Exception:
                continue
        return rows

    def _write(self, rows: list[KnowledgeItem]) -> None:
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        tmp.write_text(
            json.dumps([x.to_dict() for x in rows], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        tmp.replace(self.path)

    @staticmethod
    def _source(source_kind: str, locator: str, title: str = "") -> dict[str, str]:
        return {
            "kind": redact_sensitive(source_kind.strip())[:40],
            "locator": redact_sensitive(locator.strip())[:500],
            "title": redact_sensitive(title.strip())[:240],
        }

    @staticmethod
    def _hash(topic: str, statement: str) -> str:
        normalized = json.dumps(
            {"topic": topic.strip(), "statement": statement.strip()},
            ensure_ascii=False,
            sort_keys=True,
        )
        return hashlib.sha256(normalized.encode("utf-8")).hexdigest()

    def ingest(
        self,
        *,
        topic: str,
        statement: str,
        source_kind: str,
        source_locator: str,
        source_title: str = "",
    ) -> KnowledgeItem:
        clean_topic = redact_sensitive(topic.strip())[:180]
        clean_statement = redact_sensitive(statement.strip())[:4000]
        if not clean_topic or not clean_statement:
            raise ValueError("topic and statement are required")
        source = self._source(source_kind, source_locator, source_title)
        rows = self._read()
        digest = self._hash(clean_topic, clean_statement)
        existing = next((x for x in rows if x.content_hash == digest), None)
        if existing:
            sources = list(existing.sources)
            if source not in sources:
                sources.append(source)
            updated = KnowledgeItem(
                existing.knowledge_id,
                existing.created_at,
                _now(),
                existing.topic,
                existing.statement,
                existing.trust_level,
                tuple(sources),
                existing.evidence_refs,
                existing.verified_by,
                existing.content_hash,
            )
            rows = [updated if x.knowledge_id == existing.knowledge_id else x for x in rows]
            self._write(rows)
            return updated

        item = KnowledgeItem(
            uuid.uuid4().hex,
            _now(),
            _now(),
            clean_topic,
            clean_statement,
            "untrusted",
            (source,),
            (),
            (),
            digest,
        )
        rows.append(item)
        self._write(rows)
        return item

    def promote_candidate(self, knowledge_id: str) -> KnowledgeItem:
        rows = self._read()
        item = next((x for x in rows if x.knowledge_id == knowledge_id), None)
        if item is None:
            raise KeyError(knowledge_id)
        distinct_sources = {(x.get("kind", ""), x.get("locator", "")) for x in item.sources}
        kinds = {x.get("kind", "").lower() for x in item.sources}
        has_official = "official" in kinds or "official_docs" in kinds
        if len(distinct_sources) < 2 and not has_official:
            raise ValueError("candidate promotion requires corroboration or an identified official source")
        updated = KnowledgeItem(
            item.knowledge_id,
            item.created_at,
            _now(),
            item.topic,
            item.statement,
            "candidate",
            item.sources,
            item.evidence_refs,
            item.verified_by,
            item.content_hash,
        )
        rows = [updated if x.knowledge_id == knowledge_id else x for x in rows]
        self._write(rows)
        return updated

    def verify(
        self,
        knowledge_id: str,
        *,
        evidence_refs: list[str],
        verified_by: list[str],
    ) -> KnowledgeItem:
        rows = self._read()
        item = next((x for x in rows if x.knowledge_id == knowledge_id), None)
        if item is None:
            raise KeyError(knowledge_id)
        if item.trust_level not in {"candidate", "verified"}:
            raise ValueError("knowledge must be candidate before verification")
        verifiers = tuple(dict.fromkeys(x.strip() for x in verified_by if x.strip()))
        evidence = tuple(dict.fromkeys(x.strip() for x in evidence_refs if x.strip()))
        if not evidence:
            raise ValueError("verification requires evidence references")
        if not verifiers or any(x not in VERIFICATION_TYPES for x in verifiers):
            raise ValueError("verification requires approved verifier types")
        updated = KnowledgeItem(
            item.knowledge_id,
            item.created_at,
            _now(),
            item.topic,
            item.statement,
            "verified",
            item.sources,
            tuple(dict.fromkeys((*item.evidence_refs, *evidence))),
            tuple(dict.fromkeys((*item.verified_by, *verifiers))),
            item.content_hash,
        )
        rows = [updated if x.knowledge_id == knowledge_id else x for x in rows]
        self._write(rows)
        return updated

    def search(self, text: str, *, verified_only: bool = True, limit: int = 8) -> list[KnowledgeItem]:
        terms = {x for x in text.lower().replace("、", " ").replace("。", " ").split() if len(x) >= 2}
        scored: list[tuple[int, str, KnowledgeItem]] = []
        for item in self._read():
            if verified_only and item.trust_level != "verified":
                continue
            hay = (item.topic + " " + item.statement).lower()
            score = sum(1 for term in terms if term in hay)
            if score:
                scored.append((score, item.updated_at, item))
        scored.sort(key=lambda x: (x[0], x[1]), reverse=True)
        return [x[2] for x in scored[: max(1, limit)]]

    def list(self, trust_level: str | None = None) -> list[KnowledgeItem]:
        rows = self._read()
        if trust_level is None:
            return rows
        if trust_level not in TRUST_LEVELS:
            raise ValueError("invalid trust level")
        return [x for x in rows if x.trust_level == trust_level]
