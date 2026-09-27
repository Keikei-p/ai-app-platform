from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import json
import uuid

from .config import DATA_DIR
from .evolution_engine import EvolutionDecision
from .redaction import redact_sensitive


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class EvolutionExperiment:
    experiment_id: str
    title: str
    status: str
    created_at: str
    updated_at: str
    baseline_label: str
    candidate_label: str
    changed_paths: tuple[str, ...]
    evidence_refs: tuple[str, ...]
    decision: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["changed_paths"] = list(self.changed_paths)
        data["evidence_refs"] = list(self.evidence_refs)
        return data


class EvolutionExperimentStore:
    """Persistent local history for Aivy improvement comparisons.

    Experiments store evidence and decisions only. They do not apply patches,
    merge branches, publish releases, or change root policy.
    """

    def __init__(self, path: Path | None = None):
        self.path = path or (DATA_DIR / "evolution_experiments.json")
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def create(
        self,
        *,
        title: str,
        baseline_label: str,
        candidate_label: str,
        changed_paths: list[str] | tuple[str, ...],
        evidence_refs: list[str] | tuple[str, ...],
        decision: EvolutionDecision,
    ) -> EvolutionExperiment:
        now = _now()
        clean_title = redact_sensitive(title.strip())[:180] or "Aivy improvement experiment"
        item = EvolutionExperiment(
            experiment_id=uuid.uuid4().hex,
            title=clean_title,
            status=decision.status,
            created_at=now,
            updated_at=now,
            baseline_label=redact_sensitive(baseline_label.strip())[:180] or "baseline",
            candidate_label=redact_sensitive(candidate_label.strip())[:180] or "candidate",
            changed_paths=tuple(str(x)[:500] for x in changed_paths),
            evidence_refs=tuple(redact_sensitive(str(x))[:500] for x in evidence_refs),
            decision=decision.to_dict(),
        )
        rows = self._read()
        rows.append(item)
        self._write(rows[-200:])
        return item

    def list(self, limit: int = 50) -> list[EvolutionExperiment]:
        limit = max(1, min(int(limit), 200))
        rows = self._read()
        rows.sort(key=lambda x: x.updated_at, reverse=True)
        return rows[:limit]

    def get(self, experiment_id: str) -> EvolutionExperiment:
        item = next((x for x in self._read() if x.experiment_id == experiment_id), None)
        if item is None:
            raise KeyError(experiment_id)
        return item

    def record_human_review(
        self,
        experiment_id: str,
        *,
        approved: bool,
        note: str = "",
    ) -> EvolutionExperiment:
        rows = self._read()
        current = next((x for x in rows if x.experiment_id == experiment_id), None)
        if current is None:
            raise KeyError(experiment_id)
        if current.status != "human_review_required":
            raise ValueError("only human-review candidates can be reviewed")
        decision = dict(current.decision)
        decision["human_review"] = {
            "approved": bool(approved),
            "note": redact_sensitive(note.strip())[:1200],
            "reviewed_at": _now(),
        }
        updated = EvolutionExperiment(
            experiment_id=current.experiment_id,
            title=current.title,
            status="human_approved" if approved else "human_rejected",
            created_at=current.created_at,
            updated_at=_now(),
            baseline_label=current.baseline_label,
            candidate_label=current.candidate_label,
            changed_paths=current.changed_paths,
            evidence_refs=current.evidence_refs,
            decision=decision,
        )
        rows = [updated if x.experiment_id == experiment_id else x for x in rows]
        self._write(rows)
        return updated

    def _read(self) -> list[EvolutionExperiment]:
        if not self.path.is_file():
            return []
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except Exception:
            return []
        rows: list[EvolutionExperiment] = []
        for item in raw if isinstance(raw, list) else []:
            try:
                rows.append(
                    EvolutionExperiment(
                        experiment_id=str(item["experiment_id"]),
                        title=str(item["title"]),
                        status=str(item["status"]),
                        created_at=str(item["created_at"]),
                        updated_at=str(item["updated_at"]),
                        baseline_label=str(item["baseline_label"]),
                        candidate_label=str(item["candidate_label"]),
                        changed_paths=tuple(str(x) for x in item.get("changed_paths") or ()),
                        evidence_refs=tuple(str(x) for x in item.get("evidence_refs") or ()),
                        decision=dict(item.get("decision") or {}),
                    )
                )
            except Exception:
                continue
        return rows

    def _write(self, rows: list[EvolutionExperiment]) -> None:
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        tmp.write_text(
            json.dumps([x.to_dict() for x in rows], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        tmp.replace(self.path)
