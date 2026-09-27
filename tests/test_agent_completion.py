import unittest

from src.core.agent_runtime import AgentOrchestrator, EvidenceRecord


def e(stage: str, status: str, summary: str = "ok") -> EvidenceRecord:
    return EvidenceRecord(
        evidence_id=stage + status,
        run_id="run",
        created_at="2026-01-01T00:00:00+00:00",
        stage=stage,
        status=status,
        summary=summary,
        source="test",
        sha256="0" * 64,
    )


class AgentCompletionTests(unittest.TestCase):
    def test_agent_cannot_self_declare_completion_without_evidence(self):
        result = AgentOrchestrator().completion_check([])
        self.assertFalse(result["complete"])
        self.assertIn("validate", result["missing_evidence"])
        self.assertIn("report", result["missing_evidence"])

    def test_verified_pipeline_evidence_can_complete_run(self):
        rows = [e("plan", "ready"), e("validate", "pass"), e("report", "verified")]
        result = AgentOrchestrator().completion_check(rows)
        self.assertTrue(result["complete"])

    def test_failed_evidence_blocks_completion(self):
        rows = [
            e("plan", "ready"),
            e("validate", "pass"),
            e("report", "verified"),
            e("repair", "failed", "repair failed"),
        ]
        result = AgentOrchestrator().completion_check(rows)
        self.assertFalse(result["complete"])
        self.assertIn("repair failed", result["blocking_evidence"])

    def test_release_requires_human_review_evidence_when_requested(self):
        rows = [e("plan", "ready"), e("validate", "pass"), e("report", "verified")]
        result = AgentOrchestrator().completion_check(rows, require_human_review=True)
        self.assertFalse(result["complete"])
        rows.append(e("review", "approved", "user approved release"))
        self.assertTrue(AgentOrchestrator().completion_check(rows, require_human_review=True)["complete"])


if __name__ == "__main__":
    unittest.main()
