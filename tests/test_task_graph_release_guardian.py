import tempfile
import unittest
from pathlib import Path

from src.core.app_spec import AppSpec
from src.core.release_guardian import ReleaseGuardian
from src.core.task_graph import TaskGraphPlanner


class TaskGraphPlannerTests(unittest.TestCase):
    def test_graph_builds_parallel_validation_wave(self):
        squad = {
            "roles": [
                "coordinator", "architect", "coding", "test", "security",
                "web", "accessibility", "performance", "build", "release",
            ]
        }
        graph = TaskGraphPlanner().build("Build and release a web app", squad)
        nodes = {x.task_id: x for x in graph.nodes}
        self.assertIn("generate", nodes)
        self.assertIn("tests", nodes)
        self.assertIn("security", nodes)
        self.assertIn("accessibility", nodes)
        self.assertIn("performance", nodes)
        self.assertTrue(nodes["release-gate"].approval_required)
        wave_sets = [set(x) for x in graph.waves]
        self.assertTrue(any({"tests", "security", "accessibility", "performance"}.issubset(w) for w in wave_sets))

    def test_graph_has_no_cycles(self):
        graph = TaskGraphPlanner().build(
            "Review database app",
            {"roles": ["coordinator", "architect", "coding", "test", "security", "database"]},
        )
        seen = set()
        node_map = {x.task_id: x for x in graph.nodes}
        for wave in graph.waves:
            for task_id in wave:
                self.assertTrue(set(node_map[task_id].depends_on).issubset(seen))
            seen.update(wave)
        self.assertEqual(seen, set(node_map))


class ReleaseGuardianTests(unittest.TestCase):
    def test_missing_release_evidence_blocks_external_release(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "index.html").write_text("<html lang='ja'><body><button>OK</button></body></html>", encoding="utf-8")
            spec = AppSpec(
                project_name="Demo",
                slug="demo",
                summary="demo",
                app_type="web",
                features=["dashboard"],
                targets=["web"],
            )
            report = ReleaseGuardian().assess(root, spec, instruction="demo")
            self.assertEqual(report.status, "blocked")
            self.assertTrue(report.blockers)
            self.assertTrue(report.release["external_release_requires_approval"])

    def test_release_guardian_never_publishes(self):
        guardian = ReleaseGuardian()
        self.assertFalse(hasattr(guardian, "publish"))
        self.assertFalse(hasattr(guardian, "submit"))


if __name__ == "__main__":
    unittest.main()
