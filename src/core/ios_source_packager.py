from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
from pathlib import Path
from typing import Any
import json
import zipfile

from .app_spec import AppSpec
from .database import log_event


@dataclass(frozen=True)
class IOSSourceBuildResult:
    built: bool
    artifact: Path | None
    manifest: Path | None
    sha256: str
    file_count: int
    detail: str

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["artifact"] = str(self.artifact) if self.artifact else None
        data["manifest"] = str(self.manifest) if self.manifest else None
        return data


class IOSSourcePackager:
    """Package generated Expo iOS source without pretending it is a signed IPA."""

    ALLOWED_NAMES = {
        "package.json",
        "app.json",
        "eas.json",
        "tsconfig.json",
        "App.tsx",
        "README.md",
    }

    def build(self, project_dir: Path, spec: AppSpec) -> IOSSourceBuildResult:
        project_dir = Path(project_dir)
        if "ios" not in spec.targets:
            return IOSSourceBuildResult(False, None, None, "", 0, "ios target not requested")

        mobile = project_dir / "mobile"
        if not mobile.is_dir():
            return IOSSourceBuildResult(False, None, None, "", 0, "mobile source is missing")

        files = tuple(
            mobile / name
            for name in sorted(self.ALLOWED_NAMES)
            if (mobile / name).is_file() and not (mobile / name).is_symlink()
        )
        required = {"package.json", "app.json", "App.tsx"}
        present = {x.name for x in files}
        if not required.issubset(present):
            return IOSSourceBuildResult(False, None, None, "", 0, "required iOS source files are missing")

        output = project_dir / "artifacts" / "ios"
        output.mkdir(parents=True, exist_ok=True)
        artifact = output / f"{spec.slug}-ios-source.zip"
        manifest = output / f"{spec.slug}-ios-source.manifest.json"

        with zipfile.ZipFile(artifact, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for path in files:
                archive.write(path, f"mobile/{path.name}")

        digest = sha256(artifact.read_bytes()).hexdigest()
        manifest.write_text(
            json.dumps(
                {
                    "target": "ios-source",
                    "artifact": artifact.name,
                    "sha256": digest,
                    "file_count": len(files),
                    "files": [f"mobile/{x.name}" for x in files],
                    "signed_ipa": False,
                    "distribution": "source only; Apple signing and IPA build are not included",
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        log_event("packager.ios.source_built", f"{artifact.name} sha256={digest}", spec.slug, "ios-source-packager")
        return IOSSourceBuildResult(
            True,
            artifact,
            manifest,
            digest,
            len(files),
            "iOS source ZIP built. This is not a signed IPA and cannot be submitted to the App Store as-is.",
        )
