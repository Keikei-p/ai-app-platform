from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class AivyLauncherSafetyTests(unittest.TestCase):
    def read_root(self, name: str) -> str:
        return (ROOT / name).read_text(encoding="utf-8").replace("\r\n", "\n")

    def test_aivy_launcher_tracks_latest_develop_safely(self):
        script = self.read_root("AIVY.bat")
        lowered = script.lower()
        self.assertIn('set "channel=develop"', lowered)
        self.assertIn("git status --porcelain --untracked-files=all", lowered)
        self.assertIn("git fetch --prune origin", lowered)
        self.assertIn('git merge --ff-only "origin/%channel%"', lowered)
        self.assertIn("call start.bat", lowered)
        self.assertIn('set "mode=desktop"', lowered)
        self.assertIn('if /i "%~1"=="web" set "mode=web"', lowered)
        self.assertIn("call start_web.bat", lowered)
        self.assertNotIn("reset --hard", lowered)
        self.assertNotIn("clean -fd", lowered)

    def test_web_shortcut_uses_safe_aivy_launcher(self):
        script = self.read_root("AIVY_WEB.bat").lower()
        self.assertIn("call aivy.bat web", script)
        web_start = self.read_root("START_WEB.bat").lower()
        self.assertIn("src.tools.preflight", web_start)
        self.assertIn("src.core.platform_api --open-browser", web_start)
        self.assertNotIn("unittest discover", web_start)

    def test_platform_api_supports_browser_open_flag(self):
        source = self.read_root("src/core/platform_api.py")
        self.assertIn('parser.add_argument("--open-browser", action="store_true")', source)
        self.assertIn("webbrowser.open", source)
        self.assertIn("ThreadingHTTPServer", source)

    def test_one_click_web_bootstrap_is_safe(self):
        script = self.read_root("OPEN_AIVY_WEB.bat")
        lowered = script.lower()
        self.assertIn('set "channel=develop"', lowered)
        self.assertIn("git clone --branch", lowered)
        self.assertIn('git -c "%dest%" status --porcelain --untracked-files=all', lowered)
        self.assertIn('git -c "%dest%" merge --ff-only "origin/%channel%"', lowered)
        self.assertIn("call aivy_web.bat", lowered)
        self.assertNotIn("reset --hard", lowered)
        self.assertNotIn("clean -fd", lowered)

    def test_installer_never_discards_local_work(self):
        script = self.read_root("INSTALL_OR_UPDATE.bat")
        lowered = script.lower()
        self.assertIn('set "channel=develop"', lowered)
        self.assertIn("status --porcelain --untracked-files=all", lowered)
        self.assertIn('merge --ff-only "origin/%channel%"', lowered)
        self.assertIn("aivy.bat --skip-update", lowered)
        self.assertNotIn("reset --hard", lowered)
        self.assertNotIn("clean -fd", lowered)

    def test_launcher_runtime_state_is_not_committed(self):
        ignored = self.read_root(".gitignore").splitlines()
        self.assertIn(".aivy/", ignored)


if __name__ == "__main__":
    unittest.main()
