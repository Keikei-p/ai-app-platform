from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from typing import Any
import json
import re


@dataclass(frozen=True)
class SecurityFinding:
    key: str
    severity: str
    path: str
    detail: str
    blocking: bool = True


@dataclass(frozen=True)
class SecurityReport:
    passed: bool
    scanned_files: int
    findings: list[SecurityFinding]

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "scanned_files": self.scanned_files,
            "findings": [asdict(x) for x in self.findings],
        }


@dataclass(frozen=True)
class PipelineReport:
    passed: bool
    preview_ready: bool
    release_ready: bool
    requires_release_approval: bool
    blocking_reasons: list[str]
    security: SecurityReport
    test_results: list[dict[str, Any]]
    design_passed: bool
    capability_gaps: list[dict[str, Any]]
    risk_items: list[dict[str, Any]]
    report_dir: str

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "preview_ready": self.preview_ready,
            "release_ready": self.release_ready,
            "requires_release_approval": self.requires_release_approval,
            "blocking_reasons": self.blocking_reasons,
            "security": self.security.to_dict(),
            "test_results": self.test_results,
            "design_passed": self.design_passed,
            "capability_gaps": self.capability_gaps,
            "risk_items": self.risk_items,
            "report_dir": self.report_dir,
        }


class GeneratedArtifactSecurityScanner:
    """Conservative static scanner for generated project artifacts.

    It intentionally avoids executing generated code. The goal is to catch obvious
    secrets, unsafe execution primitives and workspace escapes before preview/build.
    """

    TEXT_SUFFIXES = {
        ".py", ".js", ".mjs", ".cjs", ".ts", ".tsx", ".jsx", ".json", ".html",
        ".css", ".md", ".txt", ".yml", ".yaml", ".toml", ".ini", ".env",
    }
    IGNORE_PARTS = {".git", ".snapshots", ".vault", ".aiapp", "node_modules", "__pycache__", "artifacts"}
    MAX_TEXT_BYTES = 2 * 1024 * 1024

    SECRET_PATTERNS = (
        ("private_key", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"), "private key material"),
        ("aws_access_key", re.compile(r"\bAKIA[0-9A-Z]{16}\b"), "AWS access key"),
        ("openai_key", re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b"), "API key-like token"),
        (
            "hardcoded_secret",
            re.compile(
                r"""(?ix)
                \b(?:api[_-]?key|secret|access[_-]?token|client[_-]?secret|password)\b
                \s*[:=]\s*
                [\"'][^\"'\r\n]{24,}[\"']
                """
            ),
            "long credential-like literal",
        ),
    )
    DANGEROUS_PATTERNS = (
        ("os_system", re.compile(r"\bos\.system\s*\("), "os.system execution"),
        (
            "shell_true",
            re.compile(
                r"subprocess\.(?:run|Popen|call|check_call|check_output)\s*\([^)]*shell\s*=\s*True",
                re.I | re.S,
            ),
            "subprocess shell=True execution",
        ),
        ("dynamic_eval", re.compile(r"\b(?:eval|exec)\s*\("), "dynamic eval/exec"),
        ("unsafe_pickle", re.compile(r"\bpickle\.loads?\s*\("), "unsafe pickle loading"),
        ("path_escape", re.compile(r"(?:^|[\\/])\.\.[\\/]\.\.(?:[\\/]|$)"), "multi-level path traversal"),
    )

    def scan(self, project_dir: Path) -> SecurityReport:
        root = project_dir.resolve()
        findings: list[SecurityFinding] = []
        scanned = 0

        for path in sorted(project_dir.rglob("*")):
            try:
                rel = path.relative_to(project_dir)
            except ValueError:
                findings.append(SecurityFinding("path_escape", "critical", str(path), "artifact escaped project directory"))
                continue

            if any(part in self.IGNORE_PARTS for part in rel.parts):
                continue
            if path.is_symlink():
                findings.append(SecurityFinding("symlink", "critical", rel.as_posix(), "symbolic links are not allowed in generated artifacts"))
                continue
            if not path.is_file():
                continue

            try:
                resolved = path.resolve()
            except OSError as exc:
                findings.append(SecurityFinding("unreadable_path", "high", rel.as_posix(), str(exc)))
                continue
            if root != resolved and root not in resolved.parents:
                findings.append(SecurityFinding("path_escape", "critical", rel.as_posix(), "resolved path is outside project directory"))
                continue

            if path.suffix.lower() not in self.TEXT_SUFFIXES and path.name not in {".env", ".env.local"}:
                continue
            try:
                if path.stat().st_size > self.MAX_TEXT_BYTES:
                    findings.append(SecurityFinding("oversized_text", "medium", rel.as_posix(), "text artifact exceeds scanner size limit"))
                    continue
                text = path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError) as exc:
                findings.append(SecurityFinding("unreadable_text", "medium", rel.as_posix(), str(exc)))
                continue

            scanned += 1
            for key, pattern, detail in self.SECRET_PATTERNS:
                if pattern.search(text):
                    findings.append(SecurityFinding(key, "critical", rel.as_posix(), detail))
            for key, pattern, detail in self.DANGEROUS_PATTERNS:
                if pattern.search(text):
                    findings.append(SecurityFinding(key, "high", rel.as_posix(), detail))

            if re.search(r"(?i)(?:host|bind)\s*=\s*[\"']0\.0\.0\.0[\"']", text):
                findings.append(
                    SecurityFinding(
                        "public_bind",
                        "medium",
                        rel.as_posix(),
                        "runtime binds all network interfaces; review before preview/release",
                        False,
                    )
                )

        blocking = [x for x in findings if x.blocking]
        return SecurityReport(not blocking, scanned, findings)


class GenerationPipeline:
    """Post-generation quality gate and evidence writer.

    Preview readiness means local inspection is safe enough to proceed. Release
    readiness is stricter and stays separate from explicit human approval.
    """

    def __init__(self, scanner: GeneratedArtifactSecurityScanner | None = None):
        self.scanner = scanner or GeneratedArtifactSecurityScanner()

    @staticmethod
    def _json_write(path: Path, payload: dict) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return path

    @staticmethod
    def _as_dict(item: Any) -> dict[str, Any]:
        if isinstance(item, dict):
            return dict(item)
        if hasattr(item, "__dict__"):
            return dict(item.__dict__)
        return {"value": str(item)}

    def _manifest(self, project_dir: Path) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for path in sorted(project_dir.rglob("*")):
            if not path.is_file() or path.is_symlink():
                continue
            rel = path.relative_to(project_dir)
            if any(part in {".git", ".snapshots", ".vault", ".aiapp", "node_modules", "__pycache__"} for part in rel.parts):
                continue
            try:
                data = path.read_bytes()
            except OSError:
                continue
            rows.append({
                "path": rel.as_posix(),
                "bytes": len(data),
                "sha256": sha256(data).hexdigest(),
            })
        return rows

    @staticmethod
    def repair_feedback(report: PipelineReport, design_findings: list[str] | None = None) -> str:
        """Return bounded, non-secret quality feedback for one automatic repair attempt."""
        lines: list[str] = []
        failed_tests = [x for x in report.test_results if not x.get("passed")]
        if failed_tests:
            lines.append("FAILED TESTS:")
            for row in failed_tests[:12]:
                detail = str(row.get("detail") or "")[:500]
                lines.append(f"- {row.get('name', 'unknown')}: {detail}")
        if design_findings:
            lines.append("DESIGN FINDINGS:")
            for finding in design_findings[:12]:
                lines.append(f"- {str(finding)[:500]}")
        blocking_security = [x for x in report.security.findings if x.blocking]
        if blocking_security:
            lines.append("SECURITY FINDINGS:")
            for finding in blocking_security[:12]:
                lines.append(
                    f"- {finding.key} in {finding.path}: {finding.detail}"
                )
        if not lines:
            lines.append("No code-repairable quality failure was identified.")
        lines.append(
            "Fix only the application source needed for these findings. "
            "Do not weaken tests, security gates, approval checks, or platform metadata."
        )
        return "\n".join(lines)

    def evaluate(
        self,
        project_dir: Path,
        test_results: list[Any],
        design_passed: bool,
        capability_gaps: list[Any],
        risk_items: list[Any],
    ) -> PipelineReport:
        report_dir = project_dir / ".aiapp" / "reports"
        security = self.scanner.scan(project_dir)
        tests = [
            {
                "name": getattr(x, "name", "unknown"),
                "passed": bool(getattr(x, "passed", False)),
                "detail": str(getattr(x, "detail", "")),
            }
            for x in test_results
        ]
        gaps = [self._as_dict(x) for x in capability_gaps]
        risks = [self._as_dict(x) for x in risk_items]

        tests_ok = bool(tests) and all(x["passed"] for x in tests)
        blocking_gaps = [x for x in gaps if bool(x.get("blocking", True))]
        preview_ready = tests_ok and bool(design_passed) and security.passed
        release_ready = preview_ready and not blocking_gaps

        reasons: list[str] = []
        if not tests_ok:
            reasons.append("automated_tests_failed")
        if not design_passed:
            reasons.append("design_gate_failed")
        if not security.passed:
            reasons.append("security_gate_failed")
        if blocking_gaps:
            reasons.append("capability_gaps")

        self._json_write(report_dir / "security_report.json", security.to_dict())
        self._json_write(report_dir / "test_report.json", {"passed": tests_ok, "results": tests})
        self._json_write(
            report_dir / "generated_files_manifest.json",
            {
                "created_at": datetime.now(timezone.utc).isoformat(),
                "files": self._manifest(project_dir),
            },
        )
        self._json_write(
            project_dir / ".aiapp" / "approval_state.json",
            {
                "production_release": "required" if preview_ready else "blocked",
                "store_submit": "required" if preview_ready else "blocked",
                "domain_change": "required",
                "note": "Production/public release actions always require explicit human approval.",
            },
        )

        payload = {
            "created_at": datetime.now(timezone.utc).isoformat(),
            "passed": preview_ready,
            "preview_ready": preview_ready,
            "release_ready": release_ready,
            "requires_release_approval": True,
            "blocking_reasons": reasons,
            "design_passed": bool(design_passed),
            "security": security.to_dict(),
            "test_results": tests,
            "capability_gaps": gaps,
            "risk_items": risks,
        }
        self._json_write(report_dir / "build_readiness.json", payload)

        return PipelineReport(
            passed=preview_ready,
            preview_ready=preview_ready,
            release_ready=release_ready,
            requires_release_approval=True,
            blocking_reasons=reasons,
            security=security,
            test_results=tests,
            design_passed=bool(design_passed),
            capability_gaps=gaps,
            risk_items=risks,
            report_dir=str(report_dir),
        )
