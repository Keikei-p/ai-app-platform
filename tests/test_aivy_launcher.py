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
