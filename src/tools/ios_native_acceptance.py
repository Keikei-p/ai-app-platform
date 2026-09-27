from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

from src.core.app_spec import AppSpec
from src.core.ios_simulator_packager import IOSSimulatorPackager
from src.core.mobile_generator import MobileGenerator


def run(command: list[str], cwd: Path, timeout: int = 600) -> None:
    env = dict(os.environ)
    env["CI"] = "1"
    env["EXPO_NO_GIT_STATUS"] = "1"
    completed = subprocess.run(
        command,
        cwd=cwd,
        env=env,
        text=True,
        capture_output=True,
        timeout=timeout,
        check=False,
        shell=False,
    )
    if completed.returncode != 0:
        output = ((completed.stdout or "") + "\n" + (completed.stderr or ""))[-12000:]
        raise RuntimeError("command failed: " + " ".join(command) + "\n" + output)


def main() -> int:
    if os.uname().sysname != "Darwin":
        raise RuntimeError("iOS native acceptance requires a macOS/Xcode worker")

    root = Path.cwd() / "ci_artifacts" / "ios-native-smoke"
    if root.exists():
        shutil.rmtree(root)
    root.mkdir(parents=True)

    spec = AppSpec(
        project_name="iOS Native Smoke",
        slug="ios-native-smoke",
        summary="iOS Simulator native compilation acceptance",
        app_type="todo",
        features=[],
        targets=["ios"],
    )
    MobileGenerator().generate(root, spec)
    mobile = root / "mobile"

    run(["npm", "install", "--no-audit", "--no-fund"], mobile, timeout=600)
    run(["npm", "run", "typecheck"], mobile, timeout=300)

    result = IOSSimulatorPackager().build(root, spec, timeout=1200)
    if not result.built or result.artifact is None or result.manifest is None:
        raise RuntimeError("IOSSimulatorPackager failed: " + result.detail)
    if not result.artifact.is_file() or result.artifact.stat().st_size <= 0:
        raise RuntimeError("iOS Simulator packager did not produce an artifact ZIP")
    if not result.manifest.is_file():
        raise RuntimeError("iOS Simulator packager did not produce a manifest")

    manifest = json.loads(result.manifest.read_text(encoding="utf-8"))
    if manifest.get("sha256") != result.sha256:
        raise RuntimeError("iOS Simulator checksum evidence is inconsistent")
    if manifest.get("simulator_only") is not True:
        raise RuntimeError("iOS Simulator artifact is not marked simulator-only")
    if manifest.get("signed_ipa") is not False:
        raise RuntimeError("iOS Simulator artifact falsely claims to be a signed IPA")
    if manifest.get("apple_signing_verified") is not False:
        raise RuntimeError("iOS Simulator artifact falsely claims Apple signing")
    if manifest.get("store_ready") is not False:
        raise RuntimeError("iOS Simulator artifact falsely claims App Store readiness")

    print(
        "IOS NATIVE SIMULATOR ACCEPTANCE PASS: "
        f"{result.artifact.name} ({result.artifact.stat().st_size} bytes) "
        f"bundle={result.bundle_identifier} sha256={result.sha256}"
    )
    print(
        "IOS RELEASE STATUS: simulator build only; "
        "no Apple signing, device IPA, TestFlight, or App Store submission was performed."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
