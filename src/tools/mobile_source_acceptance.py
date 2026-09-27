from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

from src.core.app_spec import AppSpec
from src.core.mobile_generator import MobileGenerator


def run(cmd: list[str], cwd: Path, timeout: int = 420) -> None:
    completed = subprocess.run(
        cmd,
        cwd=cwd,
        text=True,
        capture_output=True,
        timeout=timeout,
        check=False,
        shell=False,
    )
    if completed.returncode != 0:
        output = (completed.stdout or "") + "\n" + (completed.stderr or "")
        raise RuntimeError("command failed: " + " ".join(cmd) + "\n" + output[-6000:])


def main() -> int:
    root = Path.cwd() / "ci_artifacts" / "mobile-smoke-project"
    if root.exists():
        shutil.rmtree(root)
    root.mkdir(parents=True)

    spec = AppSpec(
        project_name="Mobile Smoke",
        slug="mobile-smoke",
        summary="Android and iOS generation smoke test",
        app_type="todo",
        features=[],
        targets=["android", "ios"],
    )
    MobileGenerator().generate(root, spec)
    mobile = root / "mobile"

    npm = "npm.cmd" if os.name == "nt" else "npm"
    npx = "npx.cmd" if os.name == "nt" else "npx"
    run([npm, "install", "--no-audit", "--no-fund"], mobile)
    run([npm, "run", "typecheck"], mobile)
    run([npx, "expo", "export", "--platform", "android", "--output-dir", "dist-android"], mobile)
    run([npx, "expo", "export", "--platform", "ios", "--output-dir", "dist-ios"], mobile)

    if not (mobile / "dist-android").exists():
        raise RuntimeError("Android Expo export directory was not created")
    if not (mobile / "dist-ios").exists():
        raise RuntimeError("iOS Expo export directory was not created")

    print("MOBILE SOURCE ACCEPTANCE PASS: typecheck + Android/iOS Expo export")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
