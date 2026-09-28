import tempfile
import unittest
from pathlib import Path

from src.core.accessibility_guardian import AccessibilityGuardian
from src.core.performance_guardian import PerformanceGuardian


class AccessibilityGuardianTests(unittest.TestCase):
    def test_high_severity_missing_alt_is_detected(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "index.html").write_text(
                '<!doctype html><html lang="ja"><body><img src="x.png"><button>OK</button></body></html>',
                encoding="utf-8",
            )
            report = AccessibilityGuardian().scan(root)
            self.assertEqual(report.status, "attention_required")
            self.assertTrue(any(x.rule == "image_alt" and x.severity == "high" for x in report.issues))

    def test_basic_accessible_document_passes(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "index.html").write_text(
                '<!doctype html><html lang="ja"><body><img src="x.png" alt="説明"><label for="name">名前</label><input id="name"><button>保存</button></body></html>',
                encoding="utf-8",
            )
            report = AccessibilityGuardian().scan(root)
            self.assertEqual(report.status, "pass")
            self.assertEqual(report.score, 100)


class PerformanceGuardianTests(unittest.TestCase):
    def test_large_single_file_is_reported_without_fake_latency_claim(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "app.js").write_text("x" * (800 * 1024), encoding="utf-8")
            report = PerformanceGuardian().scan(root)
            self.assertEqual(report.status, "attention_required")
            self.assertTrue(any(x.metric == "largest_file_bytes" for x in report.findings))
            self.assertFalse(report.runtime_latency_measured)


if __name__ == "__main__":
    unittest.main()
