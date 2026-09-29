from __future__ import annotations

from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from src.core.autonomous_backlog import AutonomousBacklog


def now_iso():
    return datetime.now().astimezone().isoformat()


class AutonomousBacklogTests(unittest.TestCase):
    def test_builds_daily_focus_from_self_drive_queue(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            backlog = AutonomousBacklog(
                self_drive_status=lambda: {
                    "enabled": True,
                    "background_active": True,
                    "queue": [
                        {
                            "task_id": "health:demo",
                            "kind": "project_health",
                            "priority": 75,
                            "title": "制作物の自動再点検",
                            "reason": "quality=BLOCKED",
                            "target": "demo",
                            "requires_human_approval": False,
                        },
                        {
                            "task_id": "growth",
                            "kind": "growth",
                            "priority": 45,
                            "title": "Verified経験の整理",
                            "reason": "成功Evidenceを整理",
                            "target": None,
                            "requires_human_approval": False,
                        },
                    ],
                    "recent_actions": [],
                },
                list_missions=lambda: [],
                path=root / "backlog.json",
            )
            row = backlog.refresh()
            self.assertEqual(row["counts"]["todo"], 2)
            self.assertEqual(row["safe_auto_count"], 2)
            self.assertEqual(row["focus"][0]["source_key"], "health:demo")
            self.assertTrue((root / "backlog.json").is_file())

    def test_approval_boundary_is_waiting_not_safe_auto_work(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            backlog = AutonomousBacklog(
                self_drive_status=lambda: {
                    "enabled": True,
                    "background_active": True,
                    "queue": [],
                    "recent_actions": [],
                },
                list_missions=lambda: [{
                    "mission_id": "m1",
                    "project_slug": "demo",
                    "status": "approval_required",
                    "requires_approval": True,
                    "message": "Build approval is required.",
                    "evidence_refs": ["evidence/preflight.json"],
                    "updated_at": now_iso(),
                }],
                path=root / "backlog.json",
            )
            row = backlog.refresh()
            self.assertEqual(row["counts"]["waiting_approval"], 1)
            self.assertEqual(row["safe_auto_count"], 0)
            item = row["items"][0]
            self.assertEqual(item["status"], "waiting_approval")
            self.assertTrue(item["requires_human_approval"])
            self.assertIn("evidence/preflight.json", item["evidence_refs"])

    def test_completed_action_overrides_same_queue_item(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            backlog = AutonomousBacklog(
                self_drive_status=lambda: {
                    "enabled": True,
                    "background_active": True,
                    "queue": [{
                        "task_id": "growth",
                        "kind": "growth",
                        "priority": 45,
                        "title": "Verified経験の整理",
                        "reason": "queue copy",
                        "target": None,
                        "requires_human_approval": False,
                    }],
                    "recent_actions": [{
                        "status": "completed",
                        "created_at": now_iso(),
                        "task": {
                            "task_id": "growth",
                            "kind": "growth",
                            "priority": 45,
                            "title": "Verified経験の整理",
                            "reason": "executed",
                            "target": None,
                        },
                        "outcome": {
                            "status": "completed",
                            "evidence_ref": "growth/evidence.json",
                        },
                    }],
                },
                list_missions=lambda: [],
                path=root / "backlog.json",
            )
            row = backlog.refresh()
            self.assertEqual(row["counts"]["todo"], 0)
            self.assertEqual(row["counts"]["completed"], 1)
            self.assertEqual(row["items"][0]["status"], "completed")
            self.assertIn("growth/evidence.json", row["items"][0]["evidence_refs"])

    def test_failed_action_remains_visible_for_review(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            backlog = AutonomousBacklog(
                self_drive_status=lambda: {
                    "enabled": True,
                    "background_active": True,
                    "queue": [],
                    "recent_actions": [{
                        "status": "failed",
                        "created_at": now_iso(),
                        "task": {
                            "task_id": "health:demo",
                            "kind": "project_health",
                            "priority": 75,
                            "title": "制作物の自動再点検",
                            "reason": "health",
                            "target": "demo",
                        },
                        "outcome": {
                            "status": "failed",
                            "message": "synthetic failure",
                        },
                    }],
                },
                list_missions=lambda: [],
                path=root / "backlog.json",
            )
            row = backlog.refresh()
            self.assertEqual(row["counts"]["failed"], 1)
            self.assertEqual(row["items"][0]["status"], "failed")
            self.assertIn("synthetic failure", row["items"][0]["reason"])


if __name__ == "__main__":
    unittest.main()
