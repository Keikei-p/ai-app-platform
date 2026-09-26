import json
import tempfile
import unittest
from pathlib import Path

from src.core.generation_pipeline import GeneratedArtifactSecurityScanner, GenerationPipeline
from src.core.test_runner import TestResult


class GeneratedArtifactSecurityTests(unittest.TestCase):
    def test_clean_project_passes(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "app.js").write_text("const message = 'hello';", encoding="utf-8")
            report = GeneratedArtifactSecurityScanner().scan(root)
            self.assertTrue(report.passed, report.findings)
            self.assertEqual(report.scanned_files, 1)

    def test_hardcoded_api_key_is_blocked(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "app.js").write_text("const apiKey = 'sk-" + "a" * 32 + "';", encoding="utf-8")
            report = GeneratedArtifactSecurityScanner().scan(root)
            self.assertFalse(report.passed)
            self.assertIn("openai_key", {x.key for x in report.findings})

    def test_shell_true_is_blocked(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "server.py").write_text(
                "import subprocess\nsubprocess.run('echo unsafe', shell=True)\n",
                encoding="utf-8",
            )
            report = GeneratedArtifactSecurityScanner().scan(root)
            self.assertFalse(report.passed)
            self.assertIn("shell_true", {x.key for x in report.findings})

    def test_symlink_is_blocked_when_supported(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            outside = root.parent / (root.name + "-outside.txt")
            outside.write_text("outside", encoding="utf-8")
            link = root / "linked.txt"
            try:
                link.symlink_to(outside)
            except (OSError, NotImplementedError):
                self.skipTest("symlink not supported")
            try:
                report = GeneratedArtifactSecurityScanner().scan(root)
                self.assertFalse(report.passed)
                self.assertIn("symlink", {x.key for x in report.findings})
            finally:
                outside.unlink(missing_ok=True)


class GenerationPipelineTests(unittest.TestCase):
    def test_pipeline_writes_evidence_and_requires_release_approval(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "index.html").write_text("<title>Demo</title>", encoding="utf-8")
            report = GenerationPipeline().evaluate(
                root,
                [TestResult("unit", True, "ok")],
                design_passed=True,
                capability_gaps=[],
                risk_items=[],
            )
            self.assertTrue(report.preview_ready)
            self.assertTrue(report.release_ready)
            self.assertTrue(report.requires_release_approval)
            self.assertTrue((root / ".aiapp" / "reports" / "security_report.json").is_file())
            self.assertTrue((root / ".aiapp" / "reports" / "test_report.json").is_file())
            self.assertTrue((root / ".aiapp" / "reports" / "generated_files_manifest.json").is_file())
            self.assertTrue((root / ".aiapp" / "reports" / "build_readiness.json").is_file())
            state = json.loads((root / ".aiapp" / "approval_state.json").read_text(encoding="utf-8"))
            self.assertEqual(state["production_release"], "required")

    def test_capability_gap_blocks_release_but_not_preview(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "index.html").write_text("<title>Demo</title>", encoding="utf-8")
            report = GenerationPipeline().evaluate(
                root,
                [TestResult("unit", True, "ok")],
                design_passed=True,
                capability_gaps=[{"key": "ios_binary", "blocking": True}],
                risk_items=[],
            )
            self.assertTrue(report.preview_ready)
            self.assertFalse(report.release_ready)
            self.assertIn("capability_gaps", report.blocking_reasons)

    def test_failed_test_blocks_preview(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "index.html").write_text("<title>Demo</title>", encoding="utf-8")
            report = GenerationPipeline().evaluate(
                root,
                [TestResult("unit", False, "boom")],
                design_passed=True,
                capability_gaps=[],
                risk_items=[],
            )
            self.assertFalse(report.preview_ready)
            self.assertIn("automated_tests_failed", report.blocking_reasons)

    def test_manifest_hash_changes_with_content(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            target = root / "app.js"
            target.write_text("one", encoding="utf-8")
            pipe = GenerationPipeline()
            pipe.evaluate(root, [TestResult("unit", True, "ok")], True, [], [])
            first = json.loads((root / ".aiapp" / "reports" / "generated_files_manifest.json").read_text(encoding="utf-8"))
            first_hash = next(x["sha256"] for x in first["files"] if x["path"] == "app.js")
            target.write_text("two", encoding="utf-8")
            pipe.evaluate(root, [TestResult("unit", True, "ok")], True, [], [])
            second = json.loads((root / ".aiapp" / "reports" / "generated_files_manifest.json").read_text(encoding="utf-8"))
            second_hash = next(x["sha256"] for x in second["files"] if x["path"] == "app.js")
            self.assertNotEqual(first_hash, second_hash)


if __name__ == "__main__":
    unittest.main()
