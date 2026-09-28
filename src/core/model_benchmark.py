from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Any
import json

from .config import DATA_DIR
from .redaction import redact_sensitive


@dataclass(frozen=True)
class ModelObservation:
    created_at: str
    capability: str
    provider: str
    model: str
    success: bool
    quality_score: int
    latency_ms: float | None
    estimated_cost_yen: float | None
    evidence_ref: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class ModelBenchmarkStore:
    """Measured model outcome store. Recommendations are based only on recorded evidence."""

    def __init__(self, path: Path | None = None):
        self.path = path or (DATA_DIR / "model_benchmark.jsonl")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = Lock()

    def record(
        self,
        *,
        capability: str,
        provider: str,
        model: str,
        success: bool,
        quality_score: int,
        latency_ms: float | None = None,
        estimated_cost_yen: float | None = None,
        evidence_ref: str = "",
    ) -> ModelObservation:
        item = ModelObservation(
            created_at=datetime.now(timezone.utc).isoformat(),
            capability=redact_sensitive(capability.strip())[:80],
            provider=redact_sensitive(provider.strip())[:80],
            model=redact_sensitive(model.strip())[:160],
            success=bool(success),
            quality_score=max(0, min(100, int(quality_score))),
            latency_ms=float(latency_ms) if latency_ms is not None else None,
            estimated_cost_yen=float(estimated_cost_yen) if estimated_cost_yen is not None else None,
            evidence_ref=redact_sensitive(evidence_ref.strip())[:500],
        )
        with self._lock:
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(item.to_dict(), ensure_ascii=False) + "\n")
        return item

    def recent(self, limit: int = 500) -> list[ModelObservation]:
        if not self.path.is_file():
            return []
        rows: list[ModelObservation] = []
        for line in self.path.read_text(encoding="utf-8").splitlines()[-max(1, limit):]:
            try:
                rows.append(ModelObservation(**json.loads(line)))
            except Exception:
                continue
        return list(reversed(rows))

    def summary(self, capability: str | None = None) -> dict[str, Any]:
        rows = [
            row for row in self.recent(5000)
            if capability is None or row.capability == capability
        ]
        grouped: dict[str, dict[str, Any]] = {}
        for row in rows:
            key = f"{row.provider}/{row.model}"
            bucket = grouped.setdefault(key, {
                "provider": row.provider,
                "model": row.model,
                "runs": 0,
                "successes": 0,
                "score_total": 0,
                "latencies": [],
                "costs": [],
            })
            bucket["runs"] += 1
            bucket["successes"] += 1 if row.success else 0
            bucket["score_total"] += row.quality_score
            if row.latency_ms is not None:
                bucket["latencies"].append(row.latency_ms)
            if row.estimated_cost_yen is not None:
                bucket["costs"].append(row.estimated_cost_yen)

        models = []
        for bucket in grouped.values():
            runs = bucket["runs"]
            models.append({
                "provider": bucket["provider"],
                "model": bucket["model"],
                "runs": runs,
                "success_rate": round(bucket["successes"] / runs, 4) if runs else 0.0,
                "average_quality": round(bucket["score_total"] / runs, 2) if runs else 0.0,
                "average_latency_ms": round(sum(bucket["latencies"]) / len(bucket["latencies"]), 2) if bucket["latencies"] else None,
                "average_cost_yen": round(sum(bucket["costs"]) / len(bucket["costs"]), 4) if bucket["costs"] else None,
            })
        models.sort(key=lambda x: (-x["success_rate"], -x["average_quality"], x["provider"], x["model"]))
        return {
            "capability": capability,
            "observations": len(rows),
            "models": models,
            "rule": "Ordering uses only measured Aivy outcomes; no unmeasured model is declared better.",
        }
