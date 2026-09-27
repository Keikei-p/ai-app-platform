from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path, PurePosixPath
from typing import Any
import json
import re


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
    preflight_verified: bool | None
    agent_completion_verified: bool
    evidence: tuple[CertificateEvidence, ...]
    blockers: tuple[str, ...]
    created_at: str

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["evidence"] = [x.to_dict() for x in self.evidence]
        data["blockers"] = list(self.blockers)
        return data


@dataclass(frozen=True)
class CertificateIntegrity:
    valid: bool
    status: str
    checked: int
    missing: tuple[str, ...]
    mismatched: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["missing"] = list(self.missing)
        data["mismatched"] = list(self.mismatched)
        return data


class DevelopmentCertificateBuilder:
    """Create and re-verify a hash-backed summary of one Aivy development run.

    This certificate never grants publish/store/signing authority. It summarizes
    existing platform evidence only. Completion evidence is snapshotted per run,
    so later append-only Agent Ledger activity does not invalidate older runs.
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
        preflight_path: str | None = None,
    ) -> DevelopmentCertificate:
        root = Path(project_dir)
        safe_run_id = self._safe_run_id(run_id)
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
            trace_path = self._safe_relative(root, trace_rel)
            trace = self._json(trace_path) if trace_path else {}
            trace_verified = trace.get("status") == "verified"

        preflight_verified: bool | None = None
        preflight_rel = str(preflight_path or "").strip()
        if preflight_rel:
            preflight_file = self._safe_relative(root, preflight_rel)
            preflight_data = self._json(preflight_file) if preflight_file else {}
            executed = set(str(x) for x in preflight_data.get("executed_tools") or [])
            preflight_verified = bool(
                preflight_data.get("status") == "completed"
                and {"project.inspect", "knowledge.search"}.issubset(executed)
            )

        completion = dict(agent_completion or {})
        completion_verified = completion.get("complete") is True
        completion_path = self._save_completion_snapshot(root, safe_run_id, completion)

        requested_targets = list(release.get("targets") or [])
        artifact_evidence, artifact_failures = self._release_artifact_evidence(
            root,
            release,
        )
        release_artifacts_verified = bool(
            release.get("all_requested_artifacts_ready") is True
            and requested_targets
            and any(x.kind.startswith("artifact:") for x in artifact_evidence)
            and not artifact_failures
            and self._release_candidate_targets(requested_targets)
        )

        evidence: list[CertificateEvidence] = []
        for kind, rel in self.REQUIRED_REPORTS:
            item = self._evidence(root, kind, root / rel)
            if item:
                evidence.append(item)
        if trace_rel:
            trace_path = self._safe_relative(root, trace_rel)
            if trace_path:
                item = self._evidence(root, "execution_trace", trace_path)
                if item:
                    evidence.append(item)
        if preflight_rel:
            preflight_file = self._safe_relative(root, preflight_rel)
            if preflight_file:
                item = self._evidence(root, "agent_preflight", preflight_file)
                if item:
                    evidence.append(item)
        item = self._evidence(root, "agent_completion", completion_path)
        if item:
            evidence.append(item)
        evidence.extend(artifact_evidence)

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
        if preflight_rel and preflight_verified is not True:
            blockers.append("agent preflight evidence is missing or invalid")
        if not completion_verified:
            blockers.append("agent completion evidence is incomplete")
        if release.get("all_requested_artifacts_ready") is True and artifact_failures:
            blockers.extend(artifact_failures)

        verified = not blockers
        if verified and release_artifacts_verified:
            status = "verified_release_candidate"
        elif verified:
            status = "verified_preview_candidate"
        else:
            status = "blocked"

        return DevelopmentCertificate(
            run_id=safe_run_id,
            project_slug=project_slug,
            status=status,
            preview_verified=bool(
                preview_verified
                and trace_verified
                and completion_verified
                and (preflight_verified is not False)
            ),
            release_artifacts_verified=release_artifacts_verified and verified,
            external_actions="approval_required",
            tests_passed=tests_passed,
            design_passed=design_passed,
            security_passed=security_passed,
            execution_trace_verified=trace_verified,
            preflight_verified=preflight_verified,
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

    def verify_saved(self, project_dir: Path) -> CertificateIntegrity:
        root = Path(project_dir).resolve()
        path = root / ".aiapp" / "reports" / "development_certificate.json"
        data = self._json(path)
        if not data:
            return CertificateIntegrity(False, "missing_certificate", 0, ("development_certificate.json",), ())

        if data.get("external_actions") != "approval_required":
            return CertificateIntegrity(False, "invalid_policy", 0, (), ("external_actions",))

        evidence = data.get("evidence")
        if not isinstance(evidence, list) or not evidence:
            return CertificateIntegrity(False, "missing_evidence", 0, ("evidence",), ())

        missing: list[str] = []
        mismatched: list[str] = []
        checked = 0
        for row in evidence:
            if not isinstance(row, dict):
                mismatched.append("invalid evidence row")
                continue
            rel = str(row.get("path") or "").strip()
            expected = str(row.get("sha256") or "").strip().lower()
            resolved = self._safe_relative(root, rel)
            if resolved is None or not resolved.is_file() or resolved.is_symlink():
                missing.append(rel or "invalid-path")
                continue
            actual = self._sha(resolved)
            checked += 1
            if not expected or actual != expected:
                mismatched.append(rel)

        valid_status = str(data.get("status") or "").startswith("verified_")
        valid = valid_status and not missing and not mismatched
        return CertificateIntegrity(
            valid,
            "verified" if valid else "tampered_or_stale",
            checked,
            tuple(missing),
            tuple(mismatched),
        )

    def _release_artifact_evidence(
        self,
        root: Path,
        release: dict[str, Any],
    ) -> tuple[list[CertificateEvidence], list[str]]:
        rows: list[CertificateEvidence] = []
        failures: list[str] = []
        targets = release.get("targets")
        if not isinstance(targets, list):
            return rows, failures

        for state in targets:
            if not isinstance(state, dict):
                continue
            target = str(state.get("target") or "unknown").strip().lower() or "unknown"
            artifacts = state.get("artifacts")
            checksums = state.get("checksums")
            artifact_rows = artifacts if isinstance(artifacts, list) else []
            checksum_rows = checksums if isinstance(checksums, list) else []

            for index, raw in enumerate(artifact_rows):
                raw_path = str(raw or "").strip()
                resolved = self._safe_project_path(root, raw_path)
                label = f"{target}:{Path(raw_path).name or 'artifact'}"
                if resolved is None or not resolved.is_file() or resolved.is_symlink():
                    failures.append(f"release artifact missing or outside project: {label}")
                    continue

                item = self._evidence(root, f"artifact:{target}", resolved)
                if item is None:
                    failures.append(f"release artifact unreadable: {label}")
                    continue
                rows.append(item)

                if index < len(checksum_rows):
                    expected = str(checksum_rows[index] or "").strip().lower()
                    if expected and expected != item.sha256:
                        failures.append(f"release checksum mismatch: {label}")

                manifest = resolved.with_name(resolved.stem + ".manifest.json")
                manifest_item = self._evidence(
                    root,
                    f"artifact_manifest:{target}",
                    manifest,
                )
                if manifest_item is None:
                    failures.append(f"release artifact manifest missing: {label}")
                else:
                    rows.append(manifest_item)

        if release.get("all_requested_artifacts_ready") is True and not any(
            x.kind.startswith("artifact:") for x in rows
        ):
            failures.append("release manager claimed ready artifacts without hashable project artifacts")
        return rows, list(dict.fromkeys(failures))

    @staticmethod
    def _release_candidate_targets(targets: list[Any]) -> bool:
        if not targets:
            return False
        allowed_statuses = {
            "portable_bundle",
            "local_executable",
            "store_bundle",
            "signed_ipa",
        }
        for row in targets:
            if not isinstance(row, dict):
                return False
            if str(row.get("artifact_status") or "") not in allowed_statuses:
                return False
        return True

    @staticmethod
    def _safe_project_path(root: Path, value: str) -> Path | None:
        raw = str(value).strip()
        if not raw:
            return None
        candidate = Path(raw)
        if not candidate.is_absolute():
            candidate = Path(root) / candidate
        try:
            resolved = candidate.resolve()
            resolved.relative_to(Path(root).resolve())
        except (OSError, ValueError):
            return None
        return resolved

    def _save_completion_snapshot(
        self,
        root: Path,
        run_id: str,
        completion: dict[str, Any],
    ) -> Path:
        path = root / ".aiapp" / "agent" / "runs" / f"{run_id}-completion.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "run_id": run_id,
            "complete": completion.get("complete") is True,
            "missing_evidence": [str(x) for x in completion.get("missing_evidence") or []],
            "blocking_evidence": [str(x) for x in completion.get("blocking_evidence") or []],
            "rule": str(completion.get("rule") or ""),
        }
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(path)
        return path

    @staticmethod
    def _safe_run_id(value: str) -> str:
        clean = str(value).strip()
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", clean):
            raise ValueError("invalid development run id")
        return clean

    @staticmethod
    def _safe_relative(root: Path, relative: str) -> Path | None:
        raw = str(relative).replace("\\", "/").strip().lstrip("/")
        pure = PurePosixPath(raw)
        if not raw or pure.is_absolute() or ".." in pure.parts:
            return None
        candidate = (Path(root) / pure.as_posix()).resolve()
        try:
            candidate.relative_to(Path(root).resolve())
        except ValueError:
            return None
        return candidate

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
    def _sha(path: Path) -> str:
        digest = sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    @classmethod
    def _evidence(cls, root: Path, kind: str, path: Path) -> CertificateEvidence | None:
        if not path.is_file() or path.is_symlink():
            return None
        resolved = path.resolve()
        try:
            rel = resolved.relative_to(Path(root).resolve()).as_posix()
        except ValueError:
            return None
        try:
            digest = cls._sha(resolved)
        except OSError:
            return None
        return CertificateEvidence(kind, rel, digest)
