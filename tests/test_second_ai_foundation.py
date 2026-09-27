import tempfile
import unittest
from pathlib import Path

from src.core.agent_tools import AgentToolRegistry
from src.core.specialist_agents import SpecialistAgentRegistry
from src.core.model_router import ModelRouter
from src.core.knowledge_store import VerifiedKnowledgeStore


class SpecialistAgentTests(unittest.TestCase):
    def test_specialists_only_reference_registered_tools(self):
        tools = AgentToolRegistry()
        agents = SpecialistAgentRegistry(tools)
        registered = {x.name for x in tools.list()}
        self.assertGreaterEqual(len(agents.list()), 8)
        for agent in agents.list():
            self.assertTrue(set(agent.allowed_tools).issubset(registered))

    def test_security_and_release_roles_are_separated(self):
        agents = SpecialistAgentRegistry()
        self.assertIn("security.scan", agents.tools_for("security"))
        self.assertNotIn("release.publish", agents.tools_for("security"))
        self.assertIn("release.publish", agents.tools_for("release"))


class ModelRouterTests(unittest.TestCase):
    def test_router_exposes_task_capability_without_inventing_provider(self):
        route = ModelRouter().route("coding")
        self.assertEqual(route.capability, "coding")
        self.assertIn(route.mode, {"deterministic_fallback", "configured_provider"})


class VerifiedKnowledgeStoreTests(unittest.TestCase):
    def test_web_information_starts_untrusted(self):
        with tempfile.TemporaryDirectory() as td:
            store = VerifiedKnowledgeStore(Path(td) / "knowledge.json")
            item = store.ingest(
                topic="Example API",
                statement="The API uses endpoint /v2/items.",
                source_kind="web",
                source_locator="https://example.test/docs",
            )
            self.assertEqual(item.trust_level, "untrusted")
            self.assertEqual(store.search("Example API"), [])

    def test_candidate_requires_source_confidence(self):
        with tempfile.TemporaryDirectory() as td:
            store = VerifiedKnowledgeStore(Path(td) / "knowledge.json")
            item = store.ingest(
                topic="API",
                statement="Use /v2.",
                source_kind="web",
                source_locator="https://one.test",
            )
            with self.assertRaises(ValueError):
                store.promote_candidate(item.knowledge_id)
            store.ingest(
                topic="API",
                statement="Use /v2.",
                source_kind="official_docs",
                source_locator="https://official.test",
            )
            candidate = store.promote_candidate(item.knowledge_id)
            self.assertEqual(candidate.trust_level, "candidate")

    def test_verified_requires_platform_evidence(self):
        with tempfile.TemporaryDirectory() as td:
            store = VerifiedKnowledgeStore(Path(td) / "knowledge.json")
            item = store.ingest(
                topic="Build",
                statement="This configuration builds successfully.",
                source_kind="official_docs",
                source_locator="https://official.test/build",
            )
            item = store.promote_candidate(item.knowledge_id)
            with self.assertRaises(ValueError):
                store.verify(item.knowledge_id, evidence_refs=[], verified_by=["tests"])
            verified = store.verify(
                item.knowledge_id,
                evidence_refs=["ci:run-123"],
                verified_by=["tests", "build"],
            )
            self.assertEqual(verified.trust_level, "verified")
            found = store.search("Build configuration")
            self.assertEqual(found[0].knowledge_id, verified.knowledge_id)


if __name__ == "__main__":
    unittest.main()
