import json
import unittest

from src.core.specialist_council import SpecialistCouncil


class FakeStatus:
    connected = True


class SequenceEngine:
    def __init__(self):
        self.calls = []

    def status(self):
        return FakeStatus()

    def settings(self):
        return {"provider": "fake", "model": "fake-model"}

    def reply(self, history, user_text, system_instruction):
        self.calls.append({"prompt": user_text, "system": system_instruction})
        payload = json.loads(user_text)
        allowed = payload.get("allowed_tools") or []
        tool = allowed[0] if allowed else None
        index = len(self.calls)
        return json.dumps({
            "summary": f"specialist-{index}",
            "findings": [f"finding-{index}"],
            "recommendations": [f"recommendation-{index}"],
            "requested_tools": [tool] if tool else [],
            "uncertainties": [],
        })


class OfflineStatus:
    connected = False


class OfflineEngine:
    def status(self):
        return OfflineStatus()

    def settings(self):
        return {"provider": "none", "model": ""}


class SpecialistCouncilTests(unittest.TestCase):
    def test_specialists_receive_prior_conclusions(self):
        engine = SequenceEngine()
        council = SpecialistCouncil(engine=engine)
        report = council.run(
            "build a secure todo app",
            roles=("research", "architect", "coding"),
        )
        self.assertEqual(report.status, "ok")
        self.assertEqual(len(report.turns), 3)
        second = json.loads(engine.calls[1]["prompt"])
        prior = second["context"]["prior_specialists"]
        self.assertEqual(prior[0]["specialist"], "research")
        self.assertEqual(prior[0]["summary"], "specialist-1")

    def test_council_is_advisory_and_never_executes_tools(self):
        engine = SequenceEngine()
        report = SpecialistCouncil(engine=engine).run(
            "improve validation",
            roles=("coding", "test", "security"),
        )
        self.assertTrue(report.advisory_only)
        self.assertIn("project.inspect", report.requested_tools)
        self.assertEqual(report.approval_required_tools, ())
        self.assertEqual(report.budget["used"]["model_calls"], 3)

    def test_offline_council_stops_after_first_specialist(self):
        report = SpecialistCouncil(engine=OfflineEngine()).run("make an app")
        self.assertEqual(report.status, "not_connected")
        self.assertEqual(len(report.turns), 1)
        self.assertEqual(report.budget["used"]["model_calls"], 0)

    def test_release_role_cannot_be_smuggled_into_council(self):
        with self.assertRaises(ValueError):
            SpecialistCouncil(engine=SequenceEngine()).run(
                "publish it",
                roles=("release",),
            )


if __name__ == "__main__":
    unittest.main()
