from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

from src.core.app_spec import AppSpec
from src.core.mobile_generator import MobileGenerator
from src.core.android_packager import AndroidPackager


def run(cmd: list[str], cwd: Path, timeout: int = 900) -> None:
    env = dict(os.environ)
    env["CI"] = "1"
    completed = subprocess.run(
        cmd,
        cwd=cwd,
        env=env,
        text=True,
        capture_output=True,
        timeout=timeout,
        check=False,
        shell=False,
    )
    if completed.returncode != 0:
        output = (completed.stdout or "") + "\n" + (completed.stderr or "")
        raise RuntimeError("command failed: " + " ".join(cmd) + "\n" + output[-10000:])


def main() -> int:
    if os.name == "nt":
        raise RuntimeError("Android native acceptance is intended for the Linux CI worker")

    root = Path.cwd() / "ci_artifacts" / "android-native-smoke"
    if root.exists():
        shutil.rmtree(root)
    root.mkdir(parents=True)

    spec = AppSpec(
        project_name="Android Native Smoke",
        slug="android-native-smoke",
        summary="Android native debug APK smoke test",
        app_type="todo",
        features=[],
        targets=["android"],
    )
    MobileGenerator().generate(root, spec)
    mobile = root / "mobile"

    run(["npm", "install", "--no-audit", "--no-fund"], mobile, timeout=600)
    result = AndroidPackager().build_debug_apk(root, spec, timeout=900)
    if not result.built or result.artifact is None:
        raise RuntimeError("AndroidPackager failed: " + result.detail)
    if not result.artifact.is_file() or result.artifact.stat().st_size <= 0:
        raise RuntimeError("AndroidPackager did not produce an artifact")

    print(
        f"ANDROID DEBUG APK ACCEPTANCE PASS: {result.artifact} "
        f"({result.artifact.stat().st_size} bytes) sha256={result.sha256}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
