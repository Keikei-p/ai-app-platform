import unittest

from src.core.agent_tools import AgentToolRegistry


class AgentToolRegistryTests(unittest.TestCase):
    def test_unknown_tool_is_rejected(self):
        registry = AgentToolRegistry()
        with self.assertRaises(KeyError):
            registry.get("shell.exec")

    def test_external_release_tools_require_approval(self):
        registry = AgentToolRegistry()
        self.assertTrue(registry.requires_approval("release.publish"))
        self.assertTrue(registry.requires_approval("store.submit"))
        self.assertTrue(registry.requires_approval("artifact.export"))

    def test_internal_validation_tools_are_registered_without_shell(self):
        registry = AgentToolRegistry()
        names = {x.name for x in registry.list()}
        self.assertIn("tests.run", names)
        self.assertIn("security.scan", names)
        self.assertIn("design.review", names)
        self.assertNotIn("shell", names)
        self.assertNotIn("exec", names)
        self.assertFalse(registry.requires_approval("tests.run"))


if __name__ == "__main__":
    unittest.main()
