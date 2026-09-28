from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from hashlib import sha256
from math import sqrt
from pathlib import Path
from typing import Any
import json
import re

from .config import DATA_DIR
from .knowledge_store import KnowledgeItem, VerifiedKnowledgeStore
from .knowledge_index import ScalableKnowledgeIndex, knowledge_source_signature


@dataclass(frozen=True)
class KnowledgeUsage:
    knowledge_id: str
    uses: int = 0
    successes: int = 0
    failures: int = 0
    last_used_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class RankedKnowledge:
    item: KnowledgeItem
    relevance: float
    confidence: float
    score: float
    usage: KnowledgeUsage

    def to_dict(self) -> dict[str, Any]:
        return {
            "knowledge": self.item.to_dict(),
            "relevance": round(self.relevance, 4),
            "confidence": round(self.confidence, 4),
            "score": round(self.score, 4),
            "usage": self.usage.to_dict(),
        }


class KnowledgeUsageStore:
    """Inspectable, evidence-linked success/failure history for real work."""

    def __init__(self, path: Path | None = None, audit_path: Path | None = None):
        self.path = path or (DATA_DIR / "knowledge_usage.json")
        self.audit_path = audit_path or (DATA_DIR / "knowledge_usage_evidence.jsonl")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.audit_path.parent.mkdir(parents=True, exist_ok=True)

    def _read(self) -> dict[str, KnowledgeUsage]:
        if not self.path.is_file():
            return {}
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except Exception:
            return {}
        rows: dict[str, KnowledgeUsage] = {}
        for key, value in raw.items() if isinstance(raw, dict) else []:
            if not isinstance(value, dict):
                continue
            try:
                rows[str(key)] = KnowledgeUsage(
                    knowledge_id=str(value.get("knowledge_id") or key),
                    uses=max(0, int(value.get("uses") or 0)),
                    successes=max(0, int(value.get("successes") or 0)),
                    failures=max(0, int(value.get("failures") or 0)),
                    last_used_at=str(value.get("last_used_at") or ""),
                )
            except Exception:
                continue
        return rows

    def _write(self, rows: dict[str, KnowledgeUsage]) -> None:
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        tmp.write_text(
            json.dumps({key: row.to_dict() for key, row in rows.items()}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        tmp.replace(self.path)

    def get(self, knowledge_id: str) -> KnowledgeUsage:
        return self._read().get(knowledge_id, KnowledgeUsage(knowledge_id))

    def record(
        self,
        knowledge_id: str,
        *,
        success: bool,
        project_slug: str,
        evidence_ref: str,
    ) -> KnowledgeUsage:
        key = str(knowledge_id).strip()
        if not key:
            raise ValueError("knowledge_id is required")
        evidence = str(evidence_ref).strip()
        if not evidence:
            raise ValueError("knowledge usage feedback requires evidence_ref")
        slug = str(project_slug).strip()
        if not slug:
            raise ValueError("knowledge usage feedback requires project_slug")
        rows = self._read()
        current = rows.get(key, KnowledgeUsage(key))
        updated = KnowledgeUsage(
            knowledge_id=key,
            uses=current.uses + 1,
            successes=current.successes + (1 if success else 0),
            failures=current.failures + (0 if success else 1),
            last_used_at=datetime.now(timezone.utc).isoformat(),
        )
        rows[key] = updated
        self._write(rows)
        with self.audit_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps({
                "knowledge_id": key,
                "project_slug": slug[:120],
                "success": bool(success),
                "evidence_ref": evidence[:500],
                "created_at": updated.last_used_at,
            }, ensure_ascii=False) + "\n")
        return updated


class LocalSemanticIndex:
    """Deterministic local vector-like search with no embedding API dependency.

    Character n-grams work for Japanese and Latin text, remain inspectable, and
    provide a free fallback until a real embedding adapter is explicitly enabled.
    """

    DIMENSIONS = 256

    @classmethod
    def vector(cls, text: str) -> tuple[float, ...]:
        normalized = cls._normalize(text)
        grams = cls._ngrams(normalized)
        values = [0.0] * cls.DIMENSIONS
        for gram in grams:
            digest = sha256(gram.encode("utf-8")).digest()
            index = int.from_bytes(digest[:2], "big") % cls.DIMENSIONS
            sign = -1.0 if digest[2] & 1 else 1.0
            values[index] += sign
        norm = sqrt(sum(x * x for x in values))
        if norm:
            values = [x / norm for x in values]
        return tuple(values)

    @staticmethod
    def similarity(left: tuple[float, ...], right: tuple[float, ...]) -> float:
        if len(left) != len(right):
            raise ValueError("vector dimensions must match")
        raw = sum(a * b for a, b in zip(left, right))
        return max(0.0, min(1.0, raw))

    @staticmethod
    def _normalize(text: str) -> str:
        return re.sub(r"\s+", " ", str(text).strip().lower())[:24_000]

    @classmethod
    def _ngrams(cls, text: str) -> tuple[str, ...]:
        compact = text.replace(" ", "")
        grams: list[str] = []
        for size in (2, 3, 4):
            for index in range(max(0, len(compact) - size + 1)):
                grams.append(compact[index:index + size])
        words = re.findall(r"[a-z0-9_+#.-]{2,}", text)
        grams.extend(words)
        return tuple(dict.fromkeys(grams[:12_000]))


class KnowledgeConfidenceEngine:
    """Score knowledge quality without treating heuristics as verification."""

    SOURCE_WEIGHTS = {
        "official": 0.95,
        "official_docs": 0.95,
        "documentation": 0.85,
        "repository": 0.80,
        "github": 0.75,
        "project_evidence": 0.90,
        "web": 0.55,
        "manual": 0.55,
        "unknown": 0.40,
    }

    def score(self, item: KnowledgeItem, usage: KnowledgeUsage) -> float:
        trust_base = {
            "untrusted": 0.20,
            "candidate": 0.48,
            "verified": 0.76,
        }.get(item.trust_level, 0.10)

        source_scores = [
            self.SOURCE_WEIGHTS.get(str(source.get("kind") or "").lower(), 0.45)
            for source in item.sources
        ]
        source_quality = sum(source_scores) / len(source_scores) if source_scores else 0.30
        source_bonus = min(0.08, max(0, len({
            str(source.get("locator") or "") for source in item.sources
            if str(source.get("locator") or "").strip()
        }) - 1) * 0.025)

        verifier_bonus = min(0.10, len(set(item.verified_by)) * 0.025)
        source_times = [
            str(source.get("retrieved_at") or "").strip()
            for source in item.sources
            if str(source.get("retrieved_at") or "").strip()
        ]
        freshness = self._freshness(max(source_times) if source_times else item.updated_at)

        if usage.uses:
            success_rate = usage.successes / usage.uses
            experience = min(0.12, usage.uses * 0.012)
            usage_adjustment = (success_rate - 0.5) * 2 * experience
        else:
            usage_adjustment = 0.0

        score = (
            trust_base * 0.52
            + source_quality * 0.18
            + freshness * 0.12
            + source_bonus
            + verifier_bonus
            + usage_adjustment
        )
        if item.trust_level != "verified":
            score = min(score, 0.69)
        return max(0.0, min(1.0, score))

    @staticmethod
    def _freshness(value: str) -> float:
        try:
            updated = datetime.fromisoformat(value.replace("Z", "+00:00"))
            if updated.tzinfo is None:
                updated = updated.replace(tzinfo=timezone.utc)
            age_days = max(0, (datetime.now(timezone.utc) - updated).days)
        except Exception:
            return 0.35
        if age_days <= 30:
            return 1.0
        if age_days <= 180:
            return 0.82
        if age_days <= 365:
            return 0.65
        if age_days <= 730:
            return 0.48
        return 0.30


class KnowledgeSearchEngine:
    """Hybrid relevance + confidence search over the existing staged store."""

    def __init__(
        self,
        knowledge: VerifiedKnowledgeStore | None = None,
        usage: KnowledgeUsageStore | None = None,
        confidence: KnowledgeConfidenceEngine | None = None,
        index: LocalSemanticIndex | None = None,
        scalable_index: ScalableKnowledgeIndex | None = None,
    ):
        self.knowledge = knowledge or VerifiedKnowledgeStore()
        self.usage = usage or KnowledgeUsageStore()
        self.confidence = confidence or KnowledgeConfidenceEngine()
        self.index = index or LocalSemanticIndex()
        knowledge_path = getattr(self.knowledge, "path", None)
        default_index_path = (
            Path(knowledge_path).with_suffix(".index.sqlite3")
            if knowledge_path is not None
            else None
        )
        self.scalable_index = scalable_index or ScalableKnowledgeIndex(default_index_path)

    def search(
        self,
        query: str,
        *,
        verified_only: bool = True,
        limit: int = 8,
        minimum_confidence: float = 0.0,
    ) -> list[RankedKnowledge]:
        clean = str(query).strip()
        if not clean:
            return []
        source_signature = knowledge_source_signature(
            getattr(self.knowledge, "path", None)
        )
        index_current = self.scalable_index.is_current(source_signature)
        all_items: list[KnowledgeItem] | None = None
        if not index_current:
            all_items = self.knowledge.list()
            self.scalable_index.sync(
                all_items,
                source_signature=source_signature,
            )

        candidate_limit = max(160, min(1000, int(limit) * 24))
        candidate_ids = self.scalable_index.candidates(
            clean,
            verified_only=verified_only,
            limit=candidate_limit,
        )
        if candidate_ids:
            candidates = self.scalable_index.items(candidate_ids)
            if not candidates and all_items is not None:
                by_id = {item.knowledge_id: item for item in all_items}
                candidates = [
                    by_id[knowledge_id]
                    for knowledge_id in candidate_ids
                    if knowledge_id in by_id
                ]
        elif self.scalable_index.fts_available:
            candidates = []
        else:
            candidates = all_items if all_items is not None else self.knowledge.list()

        query_vector = self.index.vector(clean)
        rows: list[RankedKnowledge] = []
        for item in candidates:
            if verified_only and item.trust_level != "verified":
                continue
            use = self.usage.get(item.knowledge_id)
            confidence = self.confidence.score(item, use)
            if confidence < minimum_confidence:
                continue
            item_vector = self.index.vector(item.topic + "\n" + item.statement)
            semantic = self.index.similarity(query_vector, item_vector)
            lexical = self._lexical(clean, item.topic + " " + item.statement)
            relevance = semantic * 0.65 + lexical * 0.35
            score = relevance * 0.72 + confidence * 0.28
            rows.append(RankedKnowledge(item, relevance, confidence, score, use))
        rows.sort(key=lambda row: (row.score, row.confidence, row.item.updated_at), reverse=True)
        return rows[: max(1, min(int(limit), 50))]

    def index_stats(self) -> dict[str, int | bool]:
        return self.scalable_index.stats()

    def record_outcome(
        self,
        knowledge_ids: list[str] | tuple[str, ...],
        *,
        success: bool,
        project_slug: str,
        evidence_ref: str,
    ) -> list[KnowledgeUsage]:
        items = {item.knowledge_id: item for item in self.knowledge.list()}
        requested = list(dict.fromkeys(str(x).strip() for x in knowledge_ids if str(x).strip()))
        unknown = [knowledge_id for knowledge_id in requested if knowledge_id not in items]
        if unknown:
            raise KeyError("unknown knowledge ids: " + ", ".join(unknown[:10]))
        if success:
            not_verified = [
                knowledge_id for knowledge_id in requested
                if items[knowledge_id].trust_level != "verified"
            ]
            if not_verified:
                raise ValueError("successful feedback is allowed only for verified knowledge")
        updated: list[KnowledgeUsage] = []
        for knowledge_id in requested:
            updated.append(self.usage.record(
                knowledge_id,
                success=success,
                project_slug=project_slug,
                evidence_ref=evidence_ref,
            ))
        return updated

    @staticmethod
    def _lexical(query: str, text: str) -> float:
        query_terms = set(LocalSemanticIndex._ngrams(LocalSemanticIndex._normalize(query)))
        text_terms = set(LocalSemanticIndex._ngrams(LocalSemanticIndex._normalize(text)))
        if not query_terms:
            return 0.0
        return len(query_terms & text_terms) / len(query_terms)
