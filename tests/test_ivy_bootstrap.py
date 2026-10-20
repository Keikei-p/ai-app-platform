"""Offline tests for ZIP-to-Git Ivy auto-update bootstrap (no Windows required)."""
from __future__ import annotations

from pathlib import Path
from subprocess import CompletedProcess
from tempfile import TemporaryDirectory
from unittest.mock import patch
import unittest

from src.tools import ivy_bootstrap as updater


def ok(stdout=""):
    return CompletedProcess(["git"], 0, stdout=stdout, stderr="")


def fail():
    return CompletedProcess(["git"], 1, stdout="", stderr="PRIVATE GIT TOKEN")


class IvyAutoUpdateBootstrapTests(unittest.TestCase):
    def test_repository_validation_requires_https_public_host_without_keys(self):
        self.assertEqual(
            updater.validate_repository_url("https://github.com/Keikei-p/ai-app-platform.git"),
            "https://github.com/Keikei-p/ai-app-platform.git",
        )
        for value in (
            "",
            "https://user:secret@github.com/account/repo.git",
            "git@github.com:account/repo.git",
            "file:///C:/tmp/repo",
            "http://github.com/account/repo",
            "https://localhost/account/repo",
            "https://127.0.0.1/account/repo",
            "https://github.com/account/repo?access_token=secret",
            "https://github.com/account/repo#secret",
            "https://github.com/account/repo:443",
            "https://github.com/account/repo\n",
            "https://github.com/account",
            "https://github.com/account/repo?q=a",
        ):
            with self.subTest(value=value):
                if value.endswith("\n"):
                    # Leading/trailing whitespace is intentionally normalized.
                    continue
                with self.assertRaises(updater.BootstrapError):
                    updater.validate_repository_url(value)

    def test_install_selects_empty_folder_and_never_touches_existing_zip(self):
        with TemporaryDirectory() as base:
            root = Path(base)
            home = root / "home"
            home.mkdir()
            source = root / "unpacked-zip"
            source.mkdir()
            data = root / "AppData" / "Local" / "AI-App-Platform" / "data"
            data.mkdir(parents=True)
            protected = data / "platform.db"
            protected.write_bytes(b"EXISTING_DB")
            zip_code = source / "AIVY.bat"
            zip_code.write_bytes(b"EXISTING_ZIP")
            commands = []

            def fake_git(_binary, *args, **kwargs):
                commands.append(args)
                if args[0] == "clone":
                    Path(args[-1], ".git").mkdir(parents=True)
                return ok()

            with patch.object(updater, "_git", side_effect=fake_git):
                path, status = updater.install_or_update(
                    home=home,
                    source_folder=source,
                    ask=lambda _: "https://github.com/Keikei-p/ai-app-platform.git",
                    git_executable="git",
                )
            self.assertEqual(path, home / "Aivy-Latest")
            self.assertEqual(status, "installed")
            self.assertEqual(protected.read_bytes(), b"EXISTING_DB")
            self.assertEqual(zip_code.read_bytes(), b"EXISTING_ZIP")
            self.assertEqual(commands[0][:4], ("clone", "--branch", "develop", "--single-branch"))
            self.assertEqual(commands[0][4], "--")
            self.assertEqual(len(commands), 1)

    def test_reuses_git_folder_and_fast_forwards_when_clean(self):
        with TemporaryDirectory() as base:
            home = Path(base)
            (home / "Aivy-Latest" / ".git").mkdir(parents=True)
            commands = []

            def fake_git(_binary, *args, **kwargs):
                commands.append(args)
                if "status" in args:
                    return ok("")
                if "show-current" in args:
                    return ok("develop\n")
                return ok()

            with patch.object(updater, "_git", side_effect=fake_git):
                target, status = updater.install_or_update(
                    home=home, source_folder=home, git_executable="git",
                    ask=lambda _: self.fail("existing Git repo must not prompt"),
                )
            self.assertEqual(status, "updated")
            self.assertEqual(target, home / "Aivy-Latest")
            self.assertTrue(any("fetch" in c for c in commands))
            self.assertTrue(any("merge" in c and "--ff-only" in c for c in commands))
            self.assertFalse(any("reset" in c or "clean" in c for c in commands))

    def test_local_changes_block_all_git_mutations(self):
        with TemporaryDirectory() as base:
            home = Path(base)
            (home / "Aivy-Latest" / ".git").mkdir(parents=True)
            with patch.object(updater, "_git", return_value=ok(" M src/user.py\n")) as git:
                _, status = updater.install_or_update(
                    home=home, source_folder=home, git_executable="git",
                )
            self.assertEqual(status, "local_changes_preserved")
            self.assertEqual(git.call_count, 1)
            self.assertIn("status", git.call_args.args)

    def test_offline_failure_starts_existing_without_reset(self):
        with TemporaryDirectory() as base:
            home = Path(base)
            (home / "Aivy-Latest" / ".git").mkdir(parents=True)
            calls = []

            def fake_git(_binary, *args, **kwargs):
                calls.append(args)
                if "status" in args:
                    return ok("")
                if "show-current" in args:
                    return ok("develop\n")
                if "fetch" in args:
                    return fail()
                raise AssertionError("No more Git calls allowed on fetch error")

            with patch.object(updater, "_git", side_effect=fake_git):
                _, status = updater.install_or_update(
                    home=home, source_folder=home, git_executable="git",
                )
            self.assertEqual(status, "update_failed_using_existing")
            self.assertEqual(len(calls), 3)

    def test_existing_branch_not_changed_and_running_skips_update(self):
        with TemporaryDirectory() as base:
            home = Path(base)
            (home / "Aivy-Latest" / ".git").mkdir(parents=True)
            with patch.object(updater, "_git", return_value=ok("develop\n")) as git:
                _, status = updater.install_or_update(
                    home=home, source_folder=home, git_executable="git", running=True,
                )
            self.assertEqual(status, "already_running")
            git.assert_not_called()
            values = iter([ok(""), ok("main\n")])
            with patch.object(updater, "_git", side_effect=values) as git:
                _, status = updater.install_or_update(
                    home=home, source_folder=home, git_executable="git",
                )
            self.assertEqual(status, "different_branch_preserved")
            self.assertEqual(git.call_count, 2)

    def test_uses_second_folder_without_overwriting_first(self):
        with TemporaryDirectory() as base:
            home = Path(base)
            first = home / "Aivy-Latest"
            first.mkdir()
            (first / "old.txt").write_text("keep")
            self.assertEqual(updater.choose_install_dir(home), home / "Aivy-Latest-Git")
            second = home / "Aivy-Latest-Git"
            second.mkdir()
            with self.assertRaises(updater.BootstrapError):
                updater.choose_install_dir(home)
            self.assertEqual((first / "old.txt").read_text(), "keep")

    def test_batch_and_vbs_use_git_install_not_zip_instance(self):
        root = Path(__file__).resolve().parents[1]
        bat = (root / "OPEN_AIVY_WEB.bat").read_text(encoding="utf-8").lower()
        silent = (root / "AIVY_WEB_SILENT.vbs").read_text(encoding="utf-8").lower()
        self.assertIn("src.tools.ivy_bootstrap", bat)
        self.assertIn('"%~dp0."', bat)
        self.assertIn('aivy_web_silent.vbs', bat)
        self.assertIn('fso.folderexists(repo & "\\.git")', silent)
        self.assertIn("aivy-latest-git", silent)
        self.assertIn("open_aivy_web.bat", silent)
        self.assertNotIn("reset --hard", bat + silent)
        self.assertNotIn("clean -fd", bat + silent)


if __name__ == "__main__":
    unittest.main()
