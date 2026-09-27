from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from typing import Any
import json


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class CertificateEvidence:
    kind: str
    path: str
    sha256: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class DevelopmentCertificate:
    run_id: str
    project_slug: str
    status: str
    preview_verified: bool
    release_artifacts_verified: bool
    external_actions: str
    tests_passed: bool
    design_passed: bool
    security_passed: bool
    execution_trace_verified: bool
    agent_completion_verified: bool
    evidence: tuple[CertificateEvidence, ...]
    blockers: tuple[str, ...]
    created_at: str

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["evidence"] = [x.to_dict() for x in self.evidence]
        data["blockers"] = list(self.blockers)
        return data


class DevelopmentCertificateBuilder:
    """Create a hash-backed summary of one Aivy development run.

    This certificate never grants publish/store/signing authority. It summarizes
    existing platform evidence only and is invalidated when required quality or
    execution evidence is missing.
    """

    REQUIRED_REPORTS = (
        ("tests", ".aiapp/reports/test_report.json"),
        ("security", ".aiapp/reports/security_report.json"),
        ("design", "design_review.json"),
        ("evaluation", ".aiapp/reports/agent_evaluation.json"),
        ("release", ".aiapp/reports/release_manager.json"),
    )

    def create(
        self,
        project_dir: Path,
        *,
        run_id: str,
        project_slug: str,
        execution_trace_path: str | None,
        agent_completion: dict[str, Any] | None,
    ) -> DevelopmentCertificate:
        root = Path(project_dir)
        tests = self._json(root / ".aiapp/reports/test_report.json")
        security = self._json(root / ".aiapp/reports/security_report.json")
        design = self._json(root / "design_review.json")
        readiness = self._json(root / ".aiapp/reports/build_readiness.json")
        release = self._json(root / ".aiapp/reports/release_manager.json")

        tests_passed = tests.get("passed") is True
        security_passed = security.get("passed") is True
        design_passed = design.get("passed") is True
        preview_verified = bool(
            readiness.get("preview_ready") is True
            and tests_passed
            and security_passed
            and design_passed
        )

        trace_verified = False
        trace_rel = str(execution_trace_path or "").strip()
        if trace_rel:
            trace = self._json(root / trace_rel)
            trace_verified = trace.get("status") == "verified"

        completion = dict(agent_completion or {})
        completion_verified = completion.get("complete") is True

        requested_targets = list(release.get("targets") or [])
        release_artifacts_verified = bool(
            release.get("all_requested_artifacts_ready") is True
            and requested_targets
        )

        evidence: list[CertificateEvidence] = []
        for kind, rel in self.REQUIRED_REPORTS:
            path = root / rel
            item = self._evidence(root, kind, path)
            if item:
                evidence.append(item)
        if trace_rel:
            item = self._evidence(root, "execution_trace", root / trace_rel)
            if item:
                evidence.append(item)
        ledger = root / ".aiapp" / "agent" / "evidence.jsonl"
        item = self._evidence(root, "agent_evidence_ledger", ledger)
        if item:
            evidence.append(item)

        blockers: list[str] = []
        if not tests_passed:
            blockers.append("tests evidence is missing or failing")
        if not design_passed:
            blockers.append("design evidence is missing or failing")
        if not security_passed:
            blockers.append("security evidence is missing or failing")
        if readiness.get("preview_ready") is not True:
            blockers.append("preview readiness is not verified")
        if not trace_verified:
            blockers.append("execution trace is not verified")
        if not completion_verified:
            blockers.append("agent completion evidence is incomplete")

        verified = not blockers
        if verified and release_artifacts_verified:
            status = "verified_release_candidate"
        elif verified:
            status = "verified_preview_candidate"
        else:
            status = "blocked"

        return DevelopmentCertificate(
            run_id=run_id,
            project_slug=project_slug,
            status=status,
            preview_verified=preview_verified and trace_verified and completion_verified,
            release_artifacts_verified=release_artifacts_verified and verified,
            external_actions="approval_required",
            tests_passed=tests_passed,
            design_passed=design_passed,
            security_passed=security_passed,
            execution_trace_verified=trace_verified,
            agent_completion_verified=completion_verified,
            evidence=tuple(evidence),
            blockers=tuple(blockers),
            created_at=_now(),
        )

    def save(self, project_dir: Path, certificate: DevelopmentCertificate) -> Path:
        path = Path(project_dir) / ".aiapp" / "reports" / "development_certificate.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(
            json.dumps(certificate.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        tmp.replace(path)
        return path

    @staticmethod
    def _json(path: Path) -> dict[str, Any]:
        if not path.is_file() or path.is_symlink():
            return {}
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return {}
        return data if isinstance(data, dict) else {}

    @staticmethod
    def _evidence(root: Path, kind: str, path: Path) -> CertificateEvidence | None:
        if not path.is_file() or path.is_symlink():
            return None
        resolved = path.resolve()
        try:
            rel = resolved.relative_to(root.resolve()).as_posix()
        except ValueError:
            return None
        digest = sha256()
        try:
            with resolved.open("rb") as handle:
                for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                    digest.update(chunk)
        except OSError:
            return None
        return CertificateEvidence(kind, rel, digest.hexdigest())
