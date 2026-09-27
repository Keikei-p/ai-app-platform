from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

from src.core.app_spec import AppSpec
from src.core.mobile_generator import MobileGenerator


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
    run(["npx", "expo", "prebuild", "--platform", "android", "--clean"], mobile, timeout=600)

    android = mobile / "android"
    gradlew = android / "gradlew"
    if not gradlew.is_file():
        raise RuntimeError("Expo prebuild did not create android/gradlew")
    gradlew.chmod(gradlew.stat().st_mode | 0o111)
    run([str(gradlew), "assembleDebug", "--no-daemon"], android, timeout=900)

    apk = android / "app" / "build" / "outputs" / "apk" / "debug" / "app-debug.apk"
    if not apk.is_file() or apk.stat().st_size <= 0:
        raise RuntimeError("Android debug APK was not produced")

    print(f"ANDROID DEBUG APK ACCEPTANCE PASS: {apk} ({apk.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
