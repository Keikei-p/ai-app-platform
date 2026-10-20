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

    def test_silent_web_launcher_hides_console(self):
        script = self.read_root("AIVY_WEB_SILENT.vbs").lower()
        self.assertIn("aivy-latest", script)
        self.assertIn("call aivy.bat web", script)
        self.assertIn("shell.run command, 0, false", script)
        self.assertIn("winhttp.winhttprequest.5.1", script)
        self.assertIn("isaivyrunning", script)
        self.assertIn("127.0.0.1:8766", script)
        self.assertIn("shell.run url, 1, false", script)
        self.assertNotIn("reset --hard", script)
        self.assertNotIn("clean -fd", script)

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
        """ZIP setup delegates Git operations to argv-only Python code."""
        script = self.read_root("OPEN_AIVY_WEB.bat").lower()
        helper = self.read_root("src/tools/ivy_bootstrap.py")
        self.assertIn("src.tools.ivy_bootstrap", script)
        self.assertIn('"%~dp0."', script)
        self.assertIn("aivy_web_silent.vbs", script)
        self.assertIn('"--single-branch"', helper)
        self.assertIn('"clone"', helper)
        self.assertIn('"--ff-only"', helper)
        self.assertIn('"--porcelain"', helper)
        self.assertIn("shell=False", helper)
        self.assertIn('AIVY_UPSTREAM_REPO', helper)
        self.assertNotIn("reset --hard", script + helper)
        self.assertNotIn("clean -fd", script + helper)

    def test_installer_never_discards_local_work(self):
        script = self.read_root("INSTALL_OR_UPDATE.bat")
        lowered = script.lower()
        self.assertIn('set "channel=develop"', lowered)
        self.assertIn("status --porcelain --untracked-files=all", lowered)
        self.assertIn('merge --ff-only "origin/%channel%"', lowered)
        self.assertIn("aivy.bat --skip-update", lowered)
        self.assertNotIn("reset --hard", lowered)
        self.assertNotIn("clean -fd", lowered)

    def test_one_click_installers_have_reachable_git_and_missing_repo_paths(self):
        legacy = self.read_root("INSTALL_OR_UPDATE.bat").lower()
        self.assertIn("if errorlevel 1 goto :no_git", legacy)
        self.assertEqual(legacy.count("\n:repo_missing\n"), 1)
        self.assertIn("remote get-url origin", legacy)
        self.assertIn("git clone --branch", legacy)
        self.assertIn("merge --ff-only", legacy)
        self.assertNotIn("reset --hard", legacy)
        self.assertNotIn("clean -fd", legacy)

        # The browser-first installer uses the Python helper so ZIP checkouts
        # can capture the owner's upstream once without batch command injection.
        web = self.read_root("OPEN_AIVY_WEB.bat").lower()
        helper = self.read_root("src/tools/ivy_bootstrap.py").lower()
        self.assertIn("where git >nul 2>nul", web)
        self.assertIn("if errorlevel 1 goto :git_missing", web)
        self.assertEqual(web.count("\n:git_missing\n"), 1)
        self.assertIn("src.tools.ivy_bootstrap", web)
        self.assertIn('def source_from_checkout(', helper)
        self.assertIn('remote", "get-url", "origin"', helper)
        self.assertIn("git_executable", helper)
        self.assertIn("shell=false", helper)
        self.assertIn('"clone", "--branch", channel', helper)
        self.assertIn('"merge", "--ff-only"', helper)
        self.assertNotIn("reset --hard", web + helper)
        self.assertNotIn("clean -fd", web + helper)

    def test_launcher_runtime_state_is_not_committed(self):
        ignored = self.read_root(".gitignore").splitlines()
        self.assertIn(".aivy/", ignored)


if __name__ == "__main__":
    unittest.main()
