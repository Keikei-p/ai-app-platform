import json
import shutil
import tempfile
import unittest
from pathlib import Path

from src.core.generation_pipeline import GeneratedArtifactSecurityScanner, GenerationPipeline
from src.core.test_runner import ProjectTestRunner, TestResult
from src.core.preview_runtime import PreviewRuntime


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

    def test_npm_lifecycle_script_is_blocked(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "package.json").write_text(
                json.dumps({"name": "demo", "scripts": {"postinstall": "node install.js"}}),
                encoding="utf-8",
            )
            report = GeneratedArtifactSecurityScanner().scan(root)
            self.assertFalse(report.passed)
            self.assertIn("package_lifecycle_script", {x.key for x in report.findings})

    def test_non_registry_dependency_is_blocked(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "package.json").write_text(
                json.dumps({"name": "demo", "dependencies": {"demo-lib": "git+https://example.com/repo.git"}}),
                encoding="utf-8",
            )
            report = GeneratedArtifactSecurityScanner().scan(root)
            self.assertFalse(report.passed)
            self.assertIn("non_registry_dependency", {x.key for x in report.findings})

    def test_normal_registry_dependency_is_allowed(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "package.json").write_text(
                json.dumps({"name": "demo", "dependencies": {"react": "19.2.3"}}),
                encoding="utf-8",
            )
            report = GeneratedArtifactSecurityScanner().scan(root)
            self.assertTrue(report.passed, report.findings)

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


    def test_repair_feedback_contains_only_quality_failures(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "server.py").write_text("import os\nos.system('unsafe')\n", encoding="utf-8")
            pipe = GenerationPipeline()
            report = pipe.evaluate(
                root,
                [TestResult("compile", False, "syntax failed")],
                design_passed=False,
                capability_gaps=[],
                risk_items=[],
            )
            feedback = pipe.repair_feedback(report, ["touch targets が不足"])
            self.assertIn("FAILED TESTS", feedback)
            self.assertIn("compile", feedback)
            self.assertIn("DESIGN FINDINGS", feedback)
            self.assertIn("SECURITY FINDINGS", feedback)
            self.assertIn("os_system", feedback)
            self.assertIn("Do not weaken tests", feedback)

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


class GeneratedSyntaxValidationTests(unittest.TestCase):
    def test_invalid_generated_json_is_reported(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "project.json").write_text('{"name":"Demo"}', encoding="utf-8")
            (root / "app_spec.json").write_text(
                json.dumps({"project_name": "Demo", "targets": ["web"], "features": []}),
                encoding="utf-8",
            )
            (root / "index.html").write_text(
                '<html><head><meta name="viewport" content="width=device-width"><title>Demo</title></head><body></body></html>',
                encoding="utf-8",
            )
            (root / "styles.css").write_text(
                "button{min-height:48px}button:focus-visible{outline:2px solid}",
                encoding="utf-8",
            )
            (root / "app.js").write_text("const ok = true;", encoding="utf-8")
            (root / "manifest.webmanifest").write_text("{broken", encoding="utf-8")
            (root / "generated_manifest.json").write_text("{}", encoding="utf-8")
            results = ProjectTestRunner().run(root)
            row = next(x for x in results if x.name == "manifest.webmanifest_json")
            self.assertFalse(row.passed)

    @unittest.skipUnless(shutil.which("node"), "Node.js is not available")
    def test_invalid_javascript_is_reported_when_node_exists(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "project.json").write_text('{"name":"Demo"}', encoding="utf-8")
            (root / "app_spec.json").write_text(
                json.dumps({"project_name": "Demo", "targets": ["web"], "features": []}),
                encoding="utf-8",
            )
            (root / "index.html").write_text(
                '<html><head><meta name="viewport" content="width=device-width"><title>Demo</title></head><body></body></html>',
                encoding="utf-8",
            )
            (root / "styles.css").write_text(
                "button{min-height:48px}button:focus-visible{outline:2px solid}",
                encoding="utf-8",
            )
            (root / "app.js").write_text("const broken = ;", encoding="utf-8")
            (root / "manifest.webmanifest").write_text("{}", encoding="utf-8")
            (root / "generated_manifest.json").write_text("{}", encoding="utf-8")
            results = ProjectTestRunner().run(root)
            row = next(x for x in results if x.name == "javascript_syntax")
            self.assertFalse(row.passed)


class PreviewVerificationTests(unittest.TestCase):
    def test_failed_readiness_report_blocks_preview(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            report = root / ".aiapp" / "reports" / "build_readiness.json"
            report.parent.mkdir(parents=True)
            report.write_text(
                json.dumps({"preview_ready": False, "blocking_reasons": ["security_gate_failed"]}),
                encoding="utf-8",
            )
            with self.assertRaises(PermissionError):
                PreviewRuntime.assert_verified(root)

    def test_legacy_project_without_report_is_not_broken(self):
        with tempfile.TemporaryDirectory() as td:
            PreviewRuntime.assert_verified(Path(td))


if __name__ == "__main__":
    unittest.main()
