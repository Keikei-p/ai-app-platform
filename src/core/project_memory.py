from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import json

from .redaction import redact_sensitive


@dataclass(frozen=True)
class ProjectMemoryItem:
    created_at: str
    category: str
    statement: str
    verified: bool
    evidence_ref: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class ProjectMemory:
    """Project-local durable memory kept inside the project's Aivy metadata."""

    def _path(self, project_dir: Path) -> Path:
        return Path(project_dir) / ".aiapp" / "project_memory.jsonl"

    def record(
        self,
        project_dir: Path,
        *,
        category: str,
        statement: str,
        verified: bool = False,
        evidence_ref: str = "",
    ) -> ProjectMemoryItem:
        item = ProjectMemoryItem(
            created_at=datetime.now(timezone.utc).isoformat(),
            category=redact_sensitive(category.strip())[:120],
            statement=redact_sensitive(statement.strip())[:4000],
            verified=bool(verified),
            evidence_ref=redact_sensitive(evidence_ref.strip())[:500],
        )
        path = self._path(project_dir)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(item.to_dict(), ensure_ascii=False) + "\n")
        return item

    def recent(
        self,
        project_dir: Path,
        *,
        limit: int = 100,
        verified_only: bool = False,
    ) -> list[ProjectMemoryItem]:
        path = self._path(project_dir)
        if not path.is_file():
            return []
        rows: list[ProjectMemoryItem] = []
        for line in path.read_text(encoding="utf-8").splitlines()[-max(1, limit):]:
            try:
                item = ProjectMemoryItem(**json.loads(line))
            except Exception:
                continue
            if verified_only and not item.verified:
                continue
            rows.append(item)
        return list(reversed(rows))
