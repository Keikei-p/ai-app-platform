from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any
import hashlib
import re
import uuid

from .knowledge_store import VerifiedKnowledgeStore, KnowledgeItem
from .redaction import redact_sensitive


_INJECTION_PATTERNS = (
    (re.compile(r"(?i)ignore\s+(all\s+)?(previous|prior|system|developer)\s+instructions?"), "instruction_override"),
    (re.compile(r"(?i)(reveal|print|show|send|upload|exfiltrate).{0,80}(api[_ -]?key|token|password|secret|credential)"), "secret_exfiltration"),
    (re.compile(r"(?i)(system\s+prompt|developer\s+message).{0,80}(reveal|print|ignore|replace)"), "prompt_extraction"),
    (re.compile(r"(?i)(disable|bypass|remove).{0,60}(security|safety|approval|guard|test)"), "guard_bypass"),
    (re.compile(r"(?i)(run|execute).{0,40}(shell|powershell|cmd\.exe|bash|terminal)"), "arbitrary_execution"),
    (re.compile(r"(?i)(curl|wget).{0,120}(token|secret|key|credential|localhost|127\.0\.0\.1)"), "suspicious_network_command"),
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class ResearchSource:
    source_id: str
    source_kind: str
    locator: str
    title: str
    retrieved_at: str
    content_hash: str
    safe_for_reasoning: bool
    indicators: tuple[str, ...]
    redacted_excerpt: str

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["indicators"] = list(self.indicators)
        return data


@dataclass(frozen=True)
class ResearchIntakeResult:
    accepted: bool
    reason: str
    sources: tuple[ResearchSource, ...]
    knowledge: KnowledgeItem | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "accepted": self.accepted,
            "reason": self.reason,
            "sources": [x.to_dict() for x in self.sources],
            "knowledge": self.knowledge.to_dict() if self.knowledge else None,
        }


class ResearchGuard:
    """Best-effort classifier for untrusted external research text.

    This is a guardrail, not proof that a page is safe or factually correct.
    """

    MAX_SOURCE_CHARS = 120_000

    def inspect(
        self,
        *,
        source_kind: str,
        locator: str,
        title: str,
        content: str,
    ) -> ResearchSource:
        raw = str(content)[: self.MAX_SOURCE_CHARS]
        indicators = tuple(dict.fromkeys(name for pattern, name in _INJECTION_PATTERNS if pattern.search(raw)))
        safe = not indicators
        digest = hashlib.sha256(raw.encode("utf-8", errors="replace")).hexdigest()
        excerpt = redact_sensitive(raw[:1800])
        return ResearchSource(
            source_id=uuid.uuid4().hex,
            source_kind=redact_sensitive(source_kind.strip())[:40],
            locator=redact_sensitive(locator.strip())[:500],
            title=redact_sensitive(title.strip())[:240],
            retrieved_at=_now(),
            content_hash=digest,
            safe_for_reasoning=safe,
            indicators=indicators,
            redacted_excerpt=excerpt,
        )


class ResearchIntake:
    """Moves externally researched claims into the staged Knowledge Store.

    Even accepted claims start as untrusted. Candidate/verified promotion remains
    a separate step and verified promotion requires platform evidence.
    """

    def __init__(
        self,
        knowledge: VerifiedKnowledgeStore | None = None,
        guard: ResearchGuard | None = None,
    ):
        self.knowledge = knowledge or VerifiedKnowledgeStore()
        self.guard = guard or ResearchGuard()

    def submit_claim(
        self,
        *,
        topic: str,
        statement: str,
        sources: list[dict[str, str]],
    ) -> ResearchIntakeResult:
        if not sources:
            return ResearchIntakeResult(False, "at least one research source is required", ())
        inspected = tuple(
            self.guard.inspect(
                source_kind=str(row.get("kind") or "web"),
                locator=str(row.get("locator") or ""),
                title=str(row.get("title") or ""),
                content=str(row.get("content") or ""),
            )
            for row in sources
        )
        unsafe = [x for x in inspected if not x.safe_for_reasoning]
        if unsafe:
            return ResearchIntakeResult(
                False,
                "source quarantined because prompt-injection or unsafe-operation indicators were detected",
                inspected,
            )

        item: KnowledgeItem | None = None
        for source in inspected:
            item = self.knowledge.ingest(
                topic=topic,
                statement=statement,
                source_kind=source.source_kind,
                source_locator=source.locator,
                source_title=source.title,
                retrieved_at=source.retrieved_at,
            )
        assert item is not None
        return ResearchIntakeResult(
            True,
            "accepted as untrusted knowledge; corroboration and platform evidence are still required",
            inspected,
            item,
        )
