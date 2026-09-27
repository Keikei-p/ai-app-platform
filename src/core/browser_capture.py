from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable
import os
import shutil
import subprocess
import tempfile

from .preview_runtime import PreviewRuntime, PreviewSession


VIEWPORTS = (
    ("mobile", 390, 844),
    ("tablet", 768, 1024),
    ("desktop", 1440, 1000),
)

APPROVED_BROWSER_NAMES = {
    "msedge.exe",
    "chrome.exe",
    "chromium.exe",
    "msedge",
    "google-chrome",
    "chromium-browser",
    "microsoft edge",
    "google chrome",
    "chromium",
}


@dataclass(frozen=True)
class ScreenshotCaptureResult:
    status: str
    browser: str
    screenshots: tuple[str, ...]
    detail: str

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["screenshots"] = list(self.screenshots)
        return data


class BrowserScreenshotCapture:
    """Capture verified loopback previews with a reviewed browser command.

    The browser command is fixed and argument-list based. No arbitrary shell,
    arbitrary executable name, public URL, or pre-quality-gate preview is allowed.
    """

    def __init__(
        self,
        *,
        browser_path: Path | None = None,
        preview: PreviewRuntime | None = None,
        runner: Callable[[list[str], int], Any] | None = None,
    ):
        self.browser_path = Path(browser_path) if browser_path else None
        self.preview = preview or PreviewRuntime()
        self.runner = runner or self._run

    def capture(self, project_dir: Path) -> ScreenshotCaptureResult:
        project_dir = Path(project_dir)
        PreviewRuntime.assert_verified(project_dir)

        browser = self.browser_path or self._find_browser()
        if browser is None:
            return ScreenshotCaptureResult(
                "browser_unavailable",
                "",
                (),
                "No approved Chrome/Edge/Chromium executable was found.",
            )
        browser = browser.resolve()
        if not browser.is_file() or browser.name.lower() not in APPROVED_BROWSER_NAMES:
            raise PermissionError("browser executable is not approved")

        session: PreviewSession | None = None
        output_dir = project_dir / ".aiapp" / "screenshots"
        output_dir.mkdir(parents=True, exist_ok=True)
        screenshots: list[str] = []

        try:
            session = self.preview.start(project_dir)
            if not session.url.startswith("http://127.0.0.1:"):
                raise PermissionError("screenshot preview must be loopback-only")

            with tempfile.TemporaryDirectory(prefix="aivy-browser-") as profile:
                for name, width, height in VIEWPORTS:
                    target = output_dir / f"{name}.png"
                    command = [
                        str(browser),
                        "--headless=new",
                        "--disable-gpu",
                        "--no-first-run",
                        "--disable-extensions",
                        f"--user-data-dir={profile}",
                        f"--window-size={width},{height}",
                        f"--screenshot={target}",
                        session.url,
                    ]
                    self.runner(command, 30)
                    if not target.is_file() or target.stat().st_size <= 0:
                        raise RuntimeError(f"browser did not create {name} screenshot")
                    screenshots.append(target.name)
        finally:
            try:
                self.preview.stop()
            except Exception:
                pass

        return ScreenshotCaptureResult(
            "captured",
            str(browser),
            tuple(screenshots),
            "Verified loopback preview captured at mobile, tablet, and desktop sizes.",
        )

    def save(self, project_dir: Path, result: ScreenshotCaptureResult) -> Path:
        import json
        path = Path(project_dir) / ".aiapp" / "reports" / "screenshot_capture.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(result.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
        return path

    @staticmethod
    def _run(command: list[str], timeout: int) -> None:
        subprocess.run(
            command,
            timeout=timeout,
            check=True,
            capture_output=True,
            text=True,
            shell=False,
        )

    @staticmethod
    def _find_browser() -> Path | None:
        candidates: list[Path] = []
        for env_name in ("PROGRAMFILES", "PROGRAMFILES(X86)", "LOCALAPPDATA"):
            root = os.environ.get(env_name, "").strip()
            if not root:
                continue
            base = Path(root)
            candidates += [
                base / "Microsoft" / "Edge" / "Application" / "msedge.exe",
                base / "Google" / "Chrome" / "Application" / "chrome.exe",
                base / "Chromium" / "Application" / "chromium.exe",
            ]
        candidates += [
            Path("/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge"),
            Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"),
            Path("/Applications/Chromium.app/Contents/MacOS/Chromium"),
        ]
        for name in ("msedge", "google-chrome", "chromium", "chromium-browser"):
            found = shutil.which(name)
            if found:
                candidates.append(Path(found))
        for path in candidates:
            try:
                if path.is_file() and path.name.lower() in APPROVED_BROWSER_NAMES:
                    return path
            except OSError:
                continue
        return None
