from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
import json
import zipfile

from .app_spec import AppSpec
from .database import log_event
from .artifact_verifier import ArtifactVerifier


@dataclass(frozen=True)
class WebBuildResult:
    built: bool
    artifact: Path | None
    manifest: Path | None
    file_count: int
    sha256: str
    detail: str


class WebPackager:
    """Create a portable web bundle without publishing it anywhere."""

    def __init__(self, verifier: ArtifactVerifier | None = None):
        self.verifier = verifier or ArtifactVerifier()

    EXCLUDED_PARTS = {
        ".git", ".snapshots", ".vault", ".aiapp", "node_modules", "__pycache__",
        "artifacts", "mobile", "windows",
    }
    EXCLUDED_NAMES = {
        "project.json", "app_spec.json", "release_risk.json", "implementation_gaps.json",
        "design_review.json", "app_data.db", ".gitignore", "BUILD_GENERATED_WINDOWS.bat",
    }
    ALLOWED_SUFFIXES = {
        ".html", ".css", ".js", ".mjs", ".cjs", ".py", ".json", ".webmanifest",
        ".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".ico",
        ".woff", ".woff2", ".ttf", ".txt", ".md",
    }

    def build(self, project_dir: Path, spec: AppSpec) -> WebBuildResult:
        if "web" not in spec.targets:
            return WebBuildResult(False, None, None, 0, "", "web target not requested")
        if not (project_dir / "index.html").is_file():
            return WebBuildResult(False, None, None, 0, "", "index.html is missing")

        artifact_dir = project_dir / "artifacts" / "web"
        artifact_dir.mkdir(parents=True, exist_ok=True)
        artifact = artifact_dir / f"{spec.slug}-web.zip"
        manifest = artifact_dir / f"{spec.slug}-web.manifest.json"

        entries: list[tuple[Path, str]] = []
        for src in sorted(project_dir.rglob("*")):
            if not src.is_file() or src.is_symlink():
                continue
            rel = src.relative_to(project_dir)
            if any(part in self.EXCLUDED_PARTS for part in rel.parts):
                continue
            if src.name in self.EXCLUDED_NAMES or src.name.startswith(".env"):
                continue
            if src.suffix.lower() not in self.ALLOWED_SUFFIXES:
                continue
            entries.append((src, rel.as_posix()))

        with zipfile.ZipFile(artifact, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for src, arcname in entries:
                archive.write(src, arcname)

        digest = sha256(artifact.read_bytes()).hexdigest()
        manifest.write_text(
            json.dumps(
                {
                    "target": "web",
                    "artifact": artifact.name,
                    "sha256": digest,
                    "file_count": len(entries),
                    "files": [arcname for _, arcname in entries],
                    "publication": "not published; explicit approval is required for production deployment",
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        verification = self.verifier.verify_web_zip(artifact, manifest)
        if not verification.valid:
            failures = "; ".join(verification.failures[:8]) or "unknown Web artifact verification failure"
            detail = "Web ZIP verification failed: " + failures
            log_event("packager.web.verification_failed", detail, spec.slug)
            try:
                artifact.unlink(missing_ok=True)
                manifest.unlink(missing_ok=True)
            except OSError:
                pass
            return WebBuildResult(False, None, None, 0, "", detail)

        log_event("packager.web.built", f"{artifact.name} sha256={digest}", spec.slug)
        return WebBuildResult(True, artifact, manifest, len(entries), digest, "Web ZIP built and artifact evidence verified")
