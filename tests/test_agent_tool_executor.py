import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.core.agent_tools import AgentToolRegistry
from src.core.agent_tool_executor import AgentToolExecutor


class FakeKnowledge:
    def search(self, query, verified_only=True, limit=8):
        self.args = (query, verified_only, limit)
        return []


class FakeResearch:
    class Row:
        def to_dict(self):
            return {"safe_for_reasoning": True, "content": "docs"}
    def fetch(self, url):
        self.url = url
        return self.Row()


class AgentToolExecutorTests(unittest.TestCase):
    def test_only_reviewed_bindings_are_executable(self):
        executor = AgentToolExecutor()
        self.assertIn("tests.run", executor.executable_tools())
        self.assertNotIn("release.publish", executor.executable_tools())
        with self.assertRaises(PermissionError):
            executor.execute("release.publish", {}, approved=True)

    def test_generic_shell_arguments_are_rejected(self):
        executor = AgentToolExecutor(knowledge=FakeKnowledge())
        with self.assertRaises(ValueError):
            executor.execute("knowledge.search", {"query": "api", "command": "whoami"})

    def test_verified_knowledge_search_is_forced(self):
        knowledge = FakeKnowledge()
        result = AgentToolExecutor(knowledge=knowledge).execute(
            "knowledge.search",
            {"query": "firebase auth", "limit": 3},
        )
        self.assertEqual(result.status, "executed")
        self.assertEqual(knowledge.args, ("firebase auth", True, 3))

    def test_guarded_research_fetch_binding_is_used(self):
        research = FakeResearch()
        result = AgentToolExecutor(research=research).execute(
            "research.fetch",
            {"url": "https://example.test/docs"},
        )
        self.assertTrue(result.result["safe_for_reasoning"])
        self.assertEqual(research.url, "https://example.test/docs")

    def test_project_tool_records_evidence_without_shell(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            project = root / "demo"
            project.mkdir()
            (project / "project.json").write_text(json.dumps({"name": "Demo", "slug": "demo"}), encoding="utf-8")
            (project / "app_spec.json").write_text(json.dumps({"project_name": "Demo", "targets": ["web"]}), encoding="utf-8")
            with patch("src.core.agent_tool_executor.WORKSPACE_DIR", root), patch("src.core.agent_runtime.WORKSPACE_DIR", root):
                executor = AgentToolExecutor()
                result = executor.execute("tests.run", {"project_slug": "demo"}, run_id="run-1")
                self.assertEqual(result.tool_name, "tests.run")
                evidence = project / ".aiapp" / "agent" / "evidence.jsonl"
                self.assertTrue(evidence.is_file())


if __name__ == "__main__":
    unittest.main()
