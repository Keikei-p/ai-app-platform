from pathlib import Path
import json
import tempfile
import unittest

from src.core.production_monitor import HealthSample, ProductionMonitor


class ProductionMonitorTests(unittest.TestCase):
    def test_healthy_samples_are_healthy(self):
        report = ProductionMonitor().evaluate([
            HealthSample(True, 200, 120),
            HealthSample(True, 200, 180),
        ])
        self.assertEqual(report.status, "healthy")
        self.assertTrue(report.healthy)
        self.assertFalse(report.requires_human_attention)

    def test_latency_or_single_failure_degrades_without_mutation(self):
        report = ProductionMonitor(latency_warning_ms=1000).evaluate([
            HealthSample(True, 200, 120),
            HealthSample(False, 503, 1500, "upstream unavailable"),
            HealthSample(True, 200, 110),
        ])
        self.assertEqual(report.status, "degraded")
        self.assertFalse(report.requires_human_attention)
        self.assertTrue(any("5xx" in x for x in report.reasons))

    def test_consecutive_failures_raise_incident(self):
        report = ProductionMonitor(incident_failures=3).evaluate([
            HealthSample(True, 200, 100),
            HealthSample(False, 500, 100),
            HealthSample(False, 500, 100),
            HealthSample(False, 500, 100),
        ])
        self.assertEqual(report.status, "incident")
        self.assertTrue(report.requires_human_attention)
        self.assertEqual(report.consecutive_failures, 3)

    def test_saved_policy_never_auto_mutates_production(self):
        with tempfile.TemporaryDirectory() as td:
            monitor = ProductionMonitor()
            report = monitor.evaluate([HealthSample(False, 500, 100)])
            path = monitor.save(Path(td), report)
            data = json.loads(path.read_text(encoding="utf-8"))
            self.assertFalse(data["policy"]["automatic_restart"])
            self.assertFalse(data["policy"]["automatic_deploy"])
            self.assertFalse(data["policy"]["automatic_dns_change"])


if __name__ == "__main__":
    unittest.main()
