from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
import json
from datetime import datetime, timezone
from .config import DATA_DIR
from .redaction import redact_sensitive

MEMORY_PATH = DATA_DIR / "development_memory.jsonl"

@dataclass(frozen=True)
class MemoryItem:
    created_at: str
    project_slug: str | None
    category: str
    input_text: str
    lesson: str
    outcome: str
    verified: bool = False
    evidence_source: str = ""

class DevelopmentMemory:
    """Inspectable learning store. It records lessons but cannot modify policy or permissions."""
    def __init__(self, path: Path | None = None):
        self.path = path or MEMORY_PATH
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def record(
        self,
        *,
        category: str,
        input_text: str,
        lesson: str,
        outcome: str = "learned",
        project_slug: str | None = None,
        verified: bool = False,
        evidence_source: str = "",
    ) -> MemoryItem:
        item = MemoryItem(
            datetime.now(timezone.utc).isoformat(),
            project_slug,
            category,
            redact_sensitive(input_text.strip()),
            redact_sensitive(lesson.strip()),
            redact_sensitive(outcome),
            verified,
            redact_sensitive(evidence_source),
        )
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(item.__dict__, ensure_ascii=False) + "\n")
        return item

    def recent(self, limit: int = 50) -> list[MemoryItem]:
        if not self.path.exists():
            return []
        rows: list[MemoryItem] = []
        for line in self.path.read_text(encoding="utf-8").splitlines()[-limit:]:
            try:
                rows.append(MemoryItem(**json.loads(line)))
            except Exception:
                continue
        return list(reversed(rows))

    def lessons_for(self, text: str, limit: int = 5, verified_only: bool = False) -> list[str]:
        terms = {x for x in text.lower().replace("、", " ").replace("。", " ").split() if len(x) >= 2}
        scored: list[tuple[int, str, str]] = []
        for item in self.recent(200):
            if verified_only and not item.verified:
                continue
            hay = (item.input_text + " " + item.lesson + " " + item.category).lower()
            score = sum(1 for term in terms if term in hay)
            if score:
                scored.append((score, item.created_at, item.lesson))
        scored.sort(reverse=True)
        out: list[str] = []
        for _, _, lesson in scored:
            if lesson not in out:
                out.append(lesson)
            if len(out) >= limit:
                break
        return out
