from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from hashlib import sha256
import importlib.util
import json
import os
import shutil
import subprocess
import sys

from .app_spec import AppSpec
from .database import log_event


@dataclass(frozen=True)
class WindowsPackagePreparation:
    prepared: bool
    artifact: str
    files: list[Path]


@dataclass(frozen=True)
class WindowsBuildResult:
    attempted: bool
    built: bool
    artifact: Path | None
    detail: str
    manifest: Path | None = None
    sha256: str = ""
    self_test_passed: bool = False


class WindowsPackager:
    """Prepare a generated project for a fixed-argv PyInstaller Windows build.

    Preparation never executes package managers or shell commands. The generated
    BUILD_GENERATED_WINDOWS.bat is an explicit user-triggered build step.
    """

    EXCLUDED_PARTS = {
        ".git", ".snapshots", ".vault", ".aiapp", "node_modules", "__pycache__",
        "mobile", "windows", "artifacts",
    }
    EXCLUDED_NAMES = {
        "project.json", "app_spec.json", "generated_manifest.json", "release_risk.json",
        "app_data.db", ".gitignore",
    }
    ALLOWED_SUFFIXES = {
        ".html", ".css", ".js", ".mjs", ".cjs", ".py", ".json", ".webmanifest",
        ".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".ico",
        ".woff", ".woff2", ".ttf", ".txt",
    }

    def prepare(self, project_dir: Path, spec: AppSpec) -> WindowsPackagePreparation:
        if "windows" not in spec.targets:
            return WindowsPackagePreparation(False, "", [])

        windows_dir = project_dir / "windows"
        payload = windows_dir / "payload"
        if payload.exists():
            shutil.rmtree(payload)
        payload.mkdir(parents=True, exist_ok=True)

        copied: list[Path] = []
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
            dest = payload / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dest)
            copied.append(dest)

        launcher = windows_dir / "launcher.py"
        launcher.write_text(self._launcher(spec.slug), encoding="utf-8")
        build_bat = project_dir / "BUILD_GENERATED_WINDOWS.bat"
        build_bat.write_text(self._build_bat(spec.slug), encoding="utf-8")
        manifest = windows_dir / "package_manifest.json"
        manifest.write_text(
            json.dumps(
                {
                    "target": "windows",
                    "builder": "PyInstaller 6.22.3",
                    "entrypoint": "windows/launcher.py",
                    "payload": [x.relative_to(payload).as_posix() for x in copied],
                    "artifact": f"artifacts/windows/{spec.slug}.exe",
                    "release_note": "Local build artifact only. Store publication remains approval-gated.",
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        files = copied + [launcher, build_bat, manifest]
        log_event("packager.windows.prepared", f"Prepared {len(copied)} payload files", spec.slug)
        return WindowsPackagePreparation(True, f"artifacts/windows/{spec.slug}.exe", files)

    def build(self, project_dir: Path, spec: AppSpec, timeout: int = 300) -> WindowsBuildResult:
        if "windows" not in spec.targets:
            return WindowsBuildResult(False, False, None, "windows target not requested")
        if os.name != "nt":
            return WindowsBuildResult(False, False, None, "Windows EXE builds require a Windows host")
        if importlib.util.find_spec("PyInstaller") is None:
            return WindowsBuildResult(False, False, None, "PyInstaller is not installed")

        prep = self.prepare(project_dir, spec)
        artifact = self.artifact_path(project_dir, spec.slug)
        artifact.parent.mkdir(parents=True, exist_ok=True)
        work = project_dir / ".aiapp-build" / "windows"
        work.mkdir(parents=True, exist_ok=True)
        name = "".join(ch for ch in spec.slug if ch.isalnum() or ch in "-_") or "generated-app"
        cmd = [
            sys.executable,
            "-m",
            "PyInstaller",
            "--noconfirm",
            "--clean",
            "--onefile",
            "--windowed",
            "--name",
            name,
            "--distpath",
            str(artifact.parent),
            "--workpath",
            str(work),
            "--specpath",
            str(work),
            "--add-data",
            f"{project_dir / 'windows' / 'payload'}{';' if sys.platform == 'win32' else ':'}app",
            str(project_dir / "windows" / "launcher.py"),
        ]
        try:
            completed = subprocess.run(
                cmd,
                cwd=project_dir,
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            log_event("packager.windows.build_failed", str(exc), spec.slug)
            return WindowsBuildResult(True, False, None, str(exc))

        built = completed.returncode == 0 and artifact.is_file() and artifact.stat().st_size > 0
        if not built:
            detail = (completed.stderr or completed.stdout)[-2000:]
            log_event("packager.windows.build_failed", detail, spec.slug)
            return WindowsBuildResult(True, False, None, detail)

        runtime_root = project_dir / ".aiapp-build" / "windows-runtime"
        runtime_root.mkdir(parents=True, exist_ok=True)
        env = dict(os.environ)
        env["LOCALAPPDATA"] = str(runtime_root)
        try:
            self_test = subprocess.run(
                [str(artifact), "--self-test"],
                cwd=project_dir,
                env=env,
                capture_output=True,
                text=True,
                timeout=min(60, max(15, timeout)),
                check=False,
                shell=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            self_test = None
            self_test_detail = f"{type(exc).__name__}: {exc}"
        else:
            self_test_detail = ((self_test.stdout or "") + "\n" + (self_test.stderr or ""))[-2000:]

        self_test_passed = bool(
            self_test is not None
            and self_test.returncode == 0
            and "AI_APP_WINDOWS_SELFTEST_OK" in (self_test.stdout or "")
        )
        if not self_test_passed:
            try:
                artifact.unlink(missing_ok=True)
            except OSError:
                pass
            detail = "Windows EXE self-test failed: " + self_test_detail
            log_event("packager.windows.self_test_failed", detail, spec.slug)
            return WindowsBuildResult(True, False, None, detail)

        digest = sha256(artifact.read_bytes()).hexdigest()
        manifest = artifact.parent / f"{spec.slug}.manifest.json"
        manifest.write_text(
            json.dumps(
                {
                    "target": "windows",
                    "artifact": artifact.name,
                    "sha256": digest,
                    "self_test_passed": True,
                    "signed": False,
                    "distribution": "local executable; code signing/public release require human approval",
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        detail = "Windows EXE built and self-test passed"
        log_event("packager.windows.built", f"{detail}; sha256={digest}", spec.slug)
        return WindowsBuildResult(
            True,
            True,
            artifact,
            detail,
            manifest,
            digest,
            True,
        )

    @staticmethod
    def artifact_path(project_dir: Path, slug: str) -> Path:
        return project_dir / "artifacts" / "windows" / f"{slug}.exe"

    @staticmethod
    def _launcher(slug: str) -> str:
        safe_slug = json.dumps(slug, ensure_ascii=False)
        return f'''from __future__ import annotations
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
import importlib.util
import os
import shutil
import sys
import threading
import webbrowser

SLUG = {safe_slug}

def bundled_root() -> Path:
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    return base / "app"

def runtime_root() -> Path:
    base = Path(os.environ.get("LOCALAPPDATA") or (Path.home() / "AppData" / "Local"))
    root = base / "AI-App-Generated" / SLUG
    root.mkdir(parents=True, exist_ok=True)
    return root

def sync_payload(source: Path, target: Path) -> None:
    for src in source.rglob("*"):
        if not src.is_file():
            continue
        rel = src.relative_to(source)
        dest = target / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)

def server_for(root: Path):
    server_py = root / "server.py"
    if server_py.exists():
        spec = importlib.util.spec_from_file_location("generated_packaged_server", server_py)
        if spec is None or spec.loader is None:
            raise RuntimeError("generated server could not be loaded")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module.ThreadingHTTPServer(("127.0.0.1", 0), module.Handler)

    class Handler(SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(root), **kwargs)
        def log_message(self, fmt, *args):
            pass

    return ThreadingHTTPServer(("127.0.0.1", 0), Handler)

def main() -> int:
    source = bundled_root()
    target = runtime_root()
    if not source.exists():
        raise RuntimeError("packaged application payload is missing")
    sync_payload(source, target)
    if "--self-test" in sys.argv:
        if not (target / "index.html").is_file():
            raise RuntimeError("index.html missing after payload sync")
        print("AI_APP_WINDOWS_SELFTEST_OK", flush=True)
        return 0
    server = server_for(target)
    port = int(server.server_address[1])
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    webbrowser.open(f"http://127.0.0.1:{{port}}/")
    try:
        thread.join()
    except KeyboardInterrupt:
        pass
    finally:
        server.shutdown()
        server.server_close()
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
'''

    @staticmethod
    def _build_bat(slug: str) -> str:
        safe_name = "".join(ch for ch in slug if ch.isalnum() or ch in "-_") or "generated-app"
        return f'''@echo off
setlocal
cd /d "%~dp0"
set "PY="
python -c "import sys;raise SystemExit(0 if sys.version_info>=(3,11) else 1)" >nul 2>nul
if not errorlevel 1 set "PY=python"
if not defined PY (
  py -3 -c "import sys;raise SystemExit(0 if sys.version_info>=(3,11) else 1)" >nul 2>nul
  if not errorlevel 1 set "PY=py -3"
)
if not defined PY (
  echo ERROR: Python 3.11 or newer was not found.
  pause
  exit /b 1
)

if not exist "windows\payload\index.html" (
  echo ERROR: Windows package payload is missing.
  pause
  exit /b 1
)

%PY% -c "import PyInstaller" >nul 2>nul
if errorlevel 1 (
  echo Installing verified PyInstaller version...
  %PY% -m pip install "pyinstaller==6.22.3" || goto :failed
)

if not exist "artifacts\windows" mkdir "artifacts\windows"
if not exist ".aiapp-build\windows" mkdir ".aiapp-build\windows"
%PY% -m PyInstaller --noconfirm --clean --onefile --windowed ^
  --name "{safe_name}" ^
  --distpath "artifacts\windows" ^
  --workpath ".aiapp-build\windows" ^
  --specpath ".aiapp-build\windows" ^
  --add-data "windows\payload;app" ^
  "windows\launcher.py" || goto :failed

set "AIVY_SELFTEST_ROOT=%CD%\.aiapp-build\windows-runtime"
set "LOCALAPPDATA=%AIVY_SELFTEST_ROOT%"
"artifacts\windows\{safe_name}.exe" --self-test || goto :failed
%PY% -c "import hashlib,json,pathlib;p=pathlib.Path(r'artifacts/windows/{safe_name}.exe');d=hashlib.sha256(p.read_bytes()).hexdigest();m=p.with_name(r'{safe_name}.manifest.json');m.write_text(json.dumps({{'target':'windows','artifact':p.name,'sha256':d,'self_test_passed':True,'signed':False,'distribution':'local executable; code signing/public release require human approval'}},ensure_ascii=False,indent=2),encoding='utf-8')" || goto :failed

echo.
echo BUILD PASSED + SELF-TEST PASSED
echo EXE: artifacts\windows\{safe_name}.exe
pause
exit /b 0

:failed
echo.
echo BUILD FAILED
pause
exit /b 1
'''
