from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import json

from .app_spec import AppSpec
from .redaction import redact_sensitive


@dataclass(frozen=True)
class RequirementCoverage:
    requirement: str
    status: str
    evidence: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["evidence"] = list(self.evidence)
        return data


@dataclass(frozen=True)
class RequirementReport:
    status: str
    requirements: tuple[RequirementCoverage, ...]
    structural_blockers: tuple[str, ...]
    semantic_review_required: bool
    created_at: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "requirements": [x.to_dict() for x in self.requirements],
            "structural_blockers": list(self.structural_blockers),
            "semantic_review_required": self.semantic_review_required,
            "created_at": self.created_at,
        }


class RequirementGuardian:
    """Creates a requirement-to-evidence ledger without pretending semantic proof."""

    def assess(
        self,
        project_dir: Path,
        spec: AppSpec,
        *,
        instruction: str,
        pipeline_report: dict[str, Any] | None,
        trace: dict[str, Any] | None,
    ) -> RequirementReport:
        root = Path(project_dir)
        blockers: list[str] = []
        if not spec.features:
            blockers.append("app specification contains no explicit features")
        if not instruction.strip():
            blockers.append("build instruction is empty")

        pipeline = dict(pipeline_report or {})
        trace_data = dict(trace or {})
        common_evidence: list[str] = []
        if (root / "app_spec.json").is_file():
            common_evidence.append("app_spec.json")
        for candidate in (
            ".aiapp/reports/test_report.json",
            ".aiapp/reports/security_report.json",
            ".aiapp/reports/build_readiness.json",
        ):
            if (root / candidate).is_file():
                common_evidence.append(candidate)
        history_path = str(trace_data.get("history_path") or "")
        if history_path:
            common_evidence.append(history_path)

        pipeline_verified = bool(
            (pipeline.get("agent_postflight") or {}).get("status") == "pass"
            or pipeline.get("preview_ready") is True
        )
        rows: list[RequirementCoverage] = []
        for feature in spec.features:
            clean = redact_sensitive(str(feature).strip())[:1000]
            if not clean:
                continue
            rows.append(RequirementCoverage(
                requirement=clean,
                status="pipeline_evidence_present" if pipeline_verified else "verification_required",
                evidence=tuple(common_evidence),
            ))

        semantic_review_required = bool(rows)
        status = "blocked" if blockers else (
            "review_required" if semantic_review_required else "pass"
        )
        return RequirementReport(
            status=status,
            requirements=tuple(rows),
            structural_blockers=tuple(blockers),
            semantic_review_required=semantic_review_required,
            created_at=datetime.now(timezone.utc).isoformat(),
        )

    @staticmethod
    def save(project_dir: Path, report: RequirementReport) -> Path:
        path = Path(project_dir) / ".aiapp" / "reports" / "requirement_guardian.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(report.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
        return path
