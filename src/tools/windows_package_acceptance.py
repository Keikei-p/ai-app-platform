from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

from src.core.app_spec import AppSpec
from src.core.windows_packager import WindowsPackager


def main() -> int:
    if os.name != "nt":
        print("SKIP: Windows package acceptance requires Windows")
        return 0

    root = Path.cwd() / "ci_artifacts" / "windows-smoke-project"
    if root.exists():
        shutil.rmtree(root)
    root.mkdir(parents=True)

    (root / "index.html").write_text(
        '<!doctype html><html><head><meta name="viewport" content="width=device-width"><title>Smoke</title></head><body>OK</body></html>',
        encoding="utf-8",
    )
    (root / "styles.css").write_text("button{min-height:48px}button:focus-visible{outline:2px solid}", encoding="utf-8")
    (root / "app.js").write_text("console.log('smoke')", encoding="utf-8")
    (root / "manifest.webmanifest").write_text('{"name":"Smoke"}', encoding="utf-8")

    spec = AppSpec(
        project_name="Windows Smoke",
        slug="windows-smoke",
        summary="Windows packaging smoke test",
        app_type="generic",
        features=[],
        targets=["web", "windows"],
    )
    result = WindowsPackager().build(root, spec, timeout=240)
    if not result.attempted:
        raise RuntimeError(result.detail)
    if not result.built or result.artifact is None or not result.artifact.is_file():
        raise RuntimeError("Windows EXE build failed: " + result.detail)

    runtime_base = root / "runtime-localappdata"
    env = dict(os.environ)
    env["LOCALAPPDATA"] = str(runtime_base)
    completed = subprocess.run(
        [str(result.artifact), "--self-test"],
        cwd=root,
        env=env,
        timeout=45,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(f"Generated EXE self-test failed: exit={completed.returncode}")

    copied_index = runtime_base / "AI-App-Generated" / "windows-smoke" / "index.html"
    if not copied_index.is_file():
        raise RuntimeError("Generated EXE did not unpack its app payload into writable runtime storage")

    print(f"WINDOWS GENERATED APP ACCEPTANCE PASS: {result.artifact}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
