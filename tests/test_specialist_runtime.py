import json
import unittest

from src.core.agent_budget import AgentBudget, AgentBudgetTracker
from src.core.specialist_runtime import SpecialistRuntime


class FakeStatus:
    connected = True


class FakeEngine:
    def __init__(self, response):
        self.response = response
        self.calls = 0

    def status(self):
        return FakeStatus()

    def settings(self):
        return {"provider": "fake", "model": "fake-model"}

    def reply(self, history, user_text, system_instruction):
        self.calls += 1
        return self.response


class AgentBudgetTests(unittest.TestCase):
    def test_tool_call_budget_is_enforced(self):
        tracker = AgentBudgetTracker(AgentBudget(max_tool_calls=1))
        self.assertEqual(tracker.reserve_tool_call(), 1)
        with self.assertRaises(RuntimeError):
            tracker.reserve_tool_call()
        self.assertEqual(tracker.snapshot()["used"]["tool_calls"], 1)

    def test_model_call_budget_is_enforced(self):
        tracker = AgentBudgetTracker(AgentBudget(max_model_calls=1))
        self.assertEqual(tracker.reserve_model_call(), 1)
        with self.assertRaises(RuntimeError):
            tracker.reserve_model_call()


class SpecialistRuntimeTests(unittest.TestCase):
    def test_coding_specialist_returns_structured_result(self):
        engine = FakeEngine(json.dumps({
            "summary": "Add validation",
            "findings": ["input is unchecked"],
            "recommendations": ["validate before save"],
            "requested_tools": ["code.generate"],
            "uncertainties": [],
        }))
        runtime = SpecialistRuntime(engine=engine)
        result = runtime.consult("coding", "improve form validation", {"project": "demo"})
        self.assertEqual(result.status, "ok")
        self.assertEqual(result.requested_tools, ("code.generate",))
        self.assertEqual(engine.calls, 1)

    def test_specialist_cannot_request_tool_outside_role(self):
        engine = FakeEngine(json.dumps({
            "summary": "publish it",
            "findings": [],
            "recommendations": [],
            "requested_tools": ["release.publish"],
            "uncertainties": [],
        }))
        runtime = SpecialistRuntime(engine=engine)
        with self.assertRaises(ValueError):
            runtime.consult("coding", "ship it")

    def test_specialist_budget_stops_runaway_calls(self):
        engine = FakeEngine(json.dumps({
            "summary": "ok",
            "findings": [],
            "recommendations": [],
            "requested_tools": [],
            "uncertainties": [],
        }))
        tracker = AgentBudgetTracker(AgentBudget(max_model_calls=1))
        runtime = SpecialistRuntime(engine=engine, budget=tracker)
        runtime.consult("test", "first")
        with self.assertRaises(RuntimeError):
            runtime.consult("test", "second")


if __name__ == "__main__":
    unittest.main()
