from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import json


@dataclass(frozen=True)
class HealthSample:
    ok: bool
    status_code: int | None = None
    latency_ms: int | None = None
    error: str = ""
    observed_at: str = ""

    def normalized(self) -> "HealthSample":
        return HealthSample(
            ok=bool(self.ok),
            status_code=int(self.status_code) if self.status_code is not None else None,
            latency_ms=max(0, int(self.latency_ms)) if self.latency_ms is not None else None,
            error=str(self.error or "")[:500],
            observed_at=self.observed_at or datetime.now(timezone.utc).isoformat(),
        )


@dataclass(frozen=True)
class ProductionHealthReport:
    status: str
    healthy: bool
    requires_human_attention: bool
    consecutive_failures: int
    failure_rate: float
    max_latency_ms: int | None
    reasons: tuple[str, ...]
    samples_checked: int
    created_at: str

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["reasons"] = list(self.reasons)
        return data


class ProductionMonitor:
    """Pure evaluator for externally collected health samples.

    Network polling belongs to an explicit adapter/scheduler. This evaluator
    never restarts, deploys, edits DNS, or performs production mutations.
    """

    def __init__(self, *, latency_warning_ms: int = 2000, incident_failures: int = 3):
        self.latency_warning_ms = max(100, int(latency_warning_ms))
        self.incident_failures = max(1, int(incident_failures))

    def evaluate(self, samples: list[HealthSample] | tuple[HealthSample, ...]) -> ProductionHealthReport:
        rows = [sample.normalized() for sample in samples]
        if not rows:
            return ProductionHealthReport(
                "unknown", False, False, 0, 0.0, None,
                ("no health samples available",), 0,
                datetime.now(timezone.utc).isoformat(),
            )

        failures = sum(1 for row in rows if not row.ok)
        consecutive = 0
        for row in reversed(rows):
            if row.ok:
                break
            consecutive += 1

        latencies = [row.latency_ms for row in rows if row.latency_ms is not None]
        max_latency = max(latencies) if latencies else None
        reasons: list[str] = []

        if consecutive >= self.incident_failures:
            reasons.append(f"{consecutive} consecutive health failures")
        if any((row.status_code or 0) >= 500 for row in rows):
            reasons.append("server 5xx response observed")
        if max_latency is not None and max_latency >= self.latency_warning_ms:
            reasons.append(f"latency reached {max_latency}ms")
        failure_rate = failures / len(rows)

        incident = consecutive >= self.incident_failures or failure_rate >= 0.5
        degraded = bool(reasons) or failure_rate > 0
        status = "incident" if incident else "degraded" if degraded else "healthy"
        return ProductionHealthReport(
            status=status,
            healthy=status == "healthy",
            requires_human_attention=status == "incident",
            consecutive_failures=consecutive,
            failure_rate=round(failure_rate, 4),
            max_latency_ms=max_latency,
            reasons=tuple(reasons),
            samples_checked=len(rows),
            created_at=datetime.now(timezone.utc).isoformat(),
        )

    def save(self, project_dir: Path, report: ProductionHealthReport) -> Path:
        path = Path(project_dir) / ".aiapp" / "reports" / "production_health.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            **report.to_dict(),
            "policy": {
                "automatic_restart": False,
                "automatic_deploy": False,
                "automatic_dns_change": False,
                "incident_requires_human_attention": True,
            },
        }
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(path)
        return path
