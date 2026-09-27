import json
import unittest

from src.core.agent_evidence_review import AgentEvidenceReviewer
from src.core.agent_execution import AgentExecutionReport, AgentToolRun
from src.core.specialist_council import CouncilReport


class OfflineStatus:
    connected = False


class OfflineEngine:
    def status(self):
        return OfflineStatus()
    def settings(self):
        return {"provider": "none", "model": ""}


class FakeStatus:
    connected = True


class FakeEngine:
    def status(self):
        return FakeStatus()
    def settings(self):
        return {"provider": "fake", "model": "fake"}
    def reply(self, history, user_text, system_instruction):
        payload = json.loads(user_text)
        state = payload["context"]["deterministic_checks"]["state"]
        return json.dumps({
            "summary": "Evidence state: " + state,
            "findings": ["checked actual evidence"],
            "recommendations": [],
            "requested_tools": [],
            "uncertainties": [],
        })


def council():
    return CouncilReport(
        goal="verify app",
        status="ok",
        advisory_only=True,
        turns=(),
        requested_tools=(),
        approval_required_tools=(),
        budget={},
        summary="initial advice",
    )


def tool(name, payload):
    return AgentToolRun(
        specialist="test",
        tool_name=name,
        status="executed",
        detail="ok",
        result={
            "tool_name": name,
            "status": "executed",
            "evidence_stage": "validate",
            "approval_required": False,
            "result": payload,
        },
    )


def execution(rows):
    return AgentExecutionReport(
        run_id="run",
        goal="verify app",
        project_slug="demo",
        status="completed",
        executed=tuple(rows),
        skipped=(),
        budget={},
        external_actions_blocked=True,
    )


class AgentEvidenceReviewerTests(unittest.TestCase):
    def test_all_three_real_validation_results_are_verified(self):
        rows = [
            tool("tests.run", {"passed": True}),
            tool("design.review", {"review": {"passed": True}}),
            tool("security.scan", {"security": {"passed": True}}),
        ]
        out = AgentEvidenceReviewer(engine=FakeEngine()).review("verify app", council(), execution(rows))
        self.assertEqual(out.evidence_state, "verified")
        self.assertEqual(out.status, "ok")

    def test_failed_security_cannot_be_overridden_by_model(self):
        rows = [
            tool("tests.run", {"passed": True}),
            tool("design.review", {"review": {"passed": True}}),
            tool("security.scan", {"security": {"passed": False}}),
        ]
        out = AgentEvidenceReviewer(engine=FakeEngine()).review("verify app", council(), execution(rows))
        self.assertEqual(out.evidence_state, "failed")
        self.assertIn("failed", out.summary)

    def test_missing_validation_is_partial_even_without_model(self):
        rows = [tool("tests.run", {"passed": True})]
        out = AgentEvidenceReviewer(engine=OfflineEngine()).review("verify app", council(), execution(rows))
        self.assertEqual(out.evidence_state, "partial")
        self.assertEqual(out.status, "not_connected")


if __name__ == "__main__":
    unittest.main()
