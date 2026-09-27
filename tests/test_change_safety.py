import json
from pathlib import Path
import tempfile
import unittest

from src.core.project_understanding import ProjectUnderstandingAI, ChangeImpactAnalyzer, safe_path
from src.core.checkpoint_manager import CheckpointManager
from src.core.agent_tool_executor import AgentToolExecutor
from src.core.agent_plan_runner import AgentPlanRunner
from src.core.agent_runtime import AgentOrchestrator


class ChangeSafetyTests(unittest.TestCase):
    def test_transitive_python_impact(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            for name, text in {'a.py': 'import b', 'b.py': 'import c', 'c.py': 'x = 1', 'tests/test_a.py': 'import a'}.items():
                p = root / name
                p.parent.mkdir(exist_ok=True)
                p.write_text(text)
            mapping = ProjectUnderstandingAI().analyze(root)
            impact = ChangeImpactAnalyzer().analyze(mapping, 'change c', ['c.py'])
            self.assertEqual(impact['affected_paths'], ['a.py', 'b.py', 'c.py', 'tests/test_a.py'])
            self.assertEqual(impact['risk'], 'YELLOW')
            self.assertEqual(mapping['imports']['a.py'], ['b.py'])

    def test_risk_and_unknown_targets(self):
        with tempfile.TemporaryDirectory() as td:
            mapping = ProjectUnderstandingAI().analyze(Path(td))
            analyzer = ChangeImpactAnalyzer()
            self.assertEqual(analyzer.analyze(mapping, 'change', ['README.md'])['risk'], 'YELLOW')
            self.assertEqual(analyzer.analyze(mapping, 'change')['risk'], 'YELLOW')
            self.assertEqual(analyzer.analyze(mapping, 'change', ['src/core/safety.py'])['risk'], 'RED')
            self.assertEqual(analyzer.analyze(mapping, '本番DB削除')['risk'], 'RED')

    def test_checkpoint_recovers_deleted_and_modified_files_without_overwrite(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / 'a.py').write_bytes(b'original')
            (root / 'b.py').write_bytes(b'deleted')
            manager = CheckpointManager()
            point = manager.create(root)
            (root / 'a.py').write_bytes(b'changed')
            (root / 'b.py').unlink()
            (root / 'new.py').write_bytes(b'new')
            result = manager.restore(root, point['checkpoint_id'], point['manifest_sha256'])
            restored = Path(result['recovered_tree'])
            self.assertEqual((restored / 'a.py').read_bytes(), b'original')
            self.assertEqual((restored / 'b.py').read_bytes(), b'deleted')
            self.assertFalse((restored / 'new.py').exists())
            self.assertEqual((root / 'a.py').read_bytes(), b'changed')
            self.assertTrue(result['root_policy']['intact'])

    def test_checkpoint_tampering_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / 'a.py').write_bytes(b'original')
            manager = CheckpointManager()
            point = manager.create(root)
            folder = root / '.aiapp/checkpoints' / point['checkpoint_id']
            (folder / 'tree/a.py').write_bytes(b'tampered')
            with self.assertRaises(ValueError):
                manager.restore(root, point['checkpoint_id'], point['manifest_sha256'])
            (folder / 'manifest.json').write_text('{}')
            with self.assertRaises(ValueError):
                manager.restore(root, point['checkpoint_id'], point['manifest_sha256'])

    def test_path_escape_rejected(self):
        for rel in ['../outside', '/absolute', 'C:/file', 'dir\\file']:
            with self.assertRaises(ValueError):
                safe_path(Path.cwd(), rel)

    def test_real_preflight_creates_evidence_and_stops_red(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / 'a.py').write_text('x = 1')
            executor = AgentToolExecutor(project_resolver=lambda slug: root)
            runner = AgentPlanRunner(executor)
            report = runner.run_preflight(AgentOrchestrator().plan('a.py の改善', 'demo'), project_dir=root)
            prepared = next(s.result for s in report.steps if s.tool_name == 'change.prepare')
            self.assertTrue(prepared['checkpoint'])
            self.assertTrue((root / '.aiapp/agent/evidence.jsonl').is_file())
            with self.assertRaises(RuntimeError):
                runner.run_preflight(AgentOrchestrator().plan('本番DB削除', 'demo'), project_dir=root)
            self.assertFalse(json.loads((root / '.aiapp/reports/change_preparation.json').read_text(encoding='utf-8'))['passed'])

    def test_restore_requires_approval(self):
        with self.assertRaises(PermissionError):
            AgentToolExecutor().execute('checkpoint.restore', {})


if __name__ == '__main__':
    unittest.main()
