from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any
import json


@dataclass(frozen=True)
class PerformanceFinding:
    severity: str
    metric: str
    value: int
    limit: int
    detail: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class PerformanceReport:
    status: str
    source_bytes: int
    largest_file_bytes: int
    asset_count: int
    findings: tuple[PerformanceFinding, ...]
    runtime_latency_measured: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "source_bytes": self.source_bytes,
            "largest_file_bytes": self.largest_file_bytes,
            "asset_count": self.asset_count,
            "findings": [x.to_dict() for x in self.findings],
            "runtime_latency_measured": self.runtime_latency_measured,
        }


class PerformanceGuardian:
    """Static performance budget guard. Runtime latency remains a separate benchmark."""

    SOURCE_LIMIT = 2 * 1024 * 1024
    SINGLE_FILE_LIMIT = 750 * 1024
    ASSET_COUNT_LIMIT = 250
    SUFFIXES = {".html", ".css", ".js", ".mjs", ".cjs", ".ts", ".tsx", ".jsx", ".json"}

    def scan(self, project_dir: Path) -> PerformanceReport:
        root = Path(project_dir)
        sizes: list[int] = []
        for path in root.rglob("*"):
            if not path.is_file() or path.is_symlink():
                continue
            rel = path.relative_to(root)
            if any(part in {".git", ".aiapp", ".vault", ".snapshots", "node_modules", "artifacts"} for part in rel.parts):
                continue
            if path.suffix.lower() not in self.SUFFIXES:
                continue
            try:
                sizes.append(path.stat().st_size)
            except OSError:
                continue

        total = sum(sizes)
        largest = max(sizes) if sizes else 0
        count = len(sizes)
        findings: list[PerformanceFinding] = []
        if total > self.SOURCE_LIMIT:
            findings.append(PerformanceFinding("medium", "source_bytes", total, self.SOURCE_LIMIT, "text source bundle exceeds static budget"))
        if largest > self.SINGLE_FILE_LIMIT:
            findings.append(PerformanceFinding("medium", "largest_file_bytes", largest, self.SINGLE_FILE_LIMIT, "single source file exceeds static budget"))
        if count > self.ASSET_COUNT_LIMIT:
            findings.append(PerformanceFinding("medium", "asset_count", count, self.ASSET_COUNT_LIMIT, "source asset count exceeds static budget"))

        return PerformanceReport(
            status="attention_required" if findings else "pass",
            source_bytes=total,
            largest_file_bytes=largest,
            asset_count=count,
            findings=tuple(findings),
            runtime_latency_measured=False,
        )

    @staticmethod
    def save(project_dir: Path, report: PerformanceReport) -> Path:
        path = Path(project_dir) / ".aiapp" / "reports" / "performance_guardian.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(report.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
        return path
