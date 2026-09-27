from __future__ import annotations

import json
import os
import plistlib
import shutil
import subprocess
from pathlib import Path

from src.core.app_spec import AppSpec
from src.core.mobile_generator import MobileGenerator


def run(command: list[str], cwd: Path, timeout: int = 1200) -> subprocess.CompletedProcess:
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
        output = ((completed.stdout or "") + "\n" + (completed.stderr or ""))[-14000:]
        raise RuntimeError(
            "command failed: " + " ".join(command) + "\n" + output
        )
    return completed


def discover_workspace(ios_dir: Path) -> Path:
    rows = sorted(
        path for path in ios_dir.glob("*.xcworkspace")
        if path.is_dir() and not path.is_symlink()
    )
    if len(rows) != 1:
        raise RuntimeError(
            f"expected exactly one generated iOS workspace, found {len(rows)}"
        )
    return rows[0]


def discover_scheme(workspace: Path, mobile: Path) -> str:
    result = run(
        ["xcodebuild", "-workspace", str(workspace), "-list", "-json"],
        mobile,
        timeout=180,
    )
    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError("xcodebuild did not return scheme JSON") from exc
    workspace_data = data.get("workspace") if isinstance(data, dict) else None
    schemes = workspace_data.get("schemes") if isinstance(workspace_data, dict) else None
    if not isinstance(schemes, list):
        raise RuntimeError("xcodebuild workspace scheme list is missing")
    clean = [str(x).strip() for x in schemes if str(x).strip()]
    if not clean:
        raise RuntimeError("generated iOS workspace has no build scheme")
    return clean[0]


def discover_app(derived_data: Path) -> Path:
    products = derived_data / "Build" / "Products" / "Debug-iphonesimulator"
    rows = sorted(
        path for path in products.glob("*.app")
        if path.is_dir() and not path.is_symlink()
    )
    if len(rows) != 1:
        raise RuntimeError(
            f"expected exactly one iOS Simulator .app, found {len(rows)}"
        )
    return rows[0]


def verify_simulator_app(app: Path) -> tuple[str, int]:
    info_path = app / "Info.plist"
    if not info_path.is_file() or info_path.is_symlink():
        raise RuntimeError("iOS Simulator app is missing Info.plist")
    try:
        info = plistlib.loads(info_path.read_bytes())
    except Exception as exc:
        raise RuntimeError("iOS Simulator Info.plist is invalid") from exc
    if not isinstance(info, dict):
        raise RuntimeError("iOS Simulator Info.plist root is invalid")
    executable_name = str(info.get("CFBundleExecutable") or "").strip()
    bundle_id = str(info.get("CFBundleIdentifier") or "").strip()
    if not executable_name or not bundle_id:
        raise RuntimeError("iOS Simulator app metadata is incomplete")
    executable = app / executable_name
    if (
        not executable.is_file()
        or executable.is_symlink()
        or executable.stat().st_size <= 0
    ):
        raise RuntimeError("iOS Simulator app executable is missing or empty")
    return bundle_id, executable.stat().st_size


def main() -> int:
    if os.uname().sysname != "Darwin":
        raise RuntimeError("iOS native acceptance requires a macOS/Xcode worker")
    if not shutil.which("xcodebuild"):
        raise RuntimeError("xcodebuild is not available")
    if not shutil.which("npm") or not shutil.which("npx"):
        raise RuntimeError("Node/npm/npx are required")

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
    run(
        ["npx", "expo", "prebuild", "--platform", "ios", "--clean"],
        mobile,
        timeout=900,
    )

    ios_dir = mobile / "ios"
    if not ios_dir.is_dir():
        raise RuntimeError("Expo prebuild did not create the iOS native project")

    workspace = discover_workspace(ios_dir)
    scheme = discover_scheme(workspace, mobile)
    derived_data = root / ".aiapp-build" / "ios-simulator"

    run(
        [
            "xcodebuild",
            "-workspace",
            str(workspace),
            "-scheme",
            scheme,
            "-configuration",
            "Debug",
            "-sdk",
            "iphonesimulator",
            "-destination",
            "generic/platform=iOS Simulator",
            "-derivedDataPath",
            str(derived_data),
            "CODE_SIGNING_ALLOWED=NO",
            "build",
        ],
        mobile,
        timeout=1200,
    )

    app = discover_app(derived_data)
    bundle_id, executable_bytes = verify_simulator_app(app)

    print(
        "IOS NATIVE SIMULATOR ACCEPTANCE PASS: "
        f"workspace={workspace.name} scheme={scheme} "
        f"app={app.name} bundle={bundle_id} executable={executable_bytes}B"
    )
    print(
        "IOS RELEASE STATUS: simulator build only; "
        "no Apple signing, device IPA, TestFlight, or App Store submission was performed."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
