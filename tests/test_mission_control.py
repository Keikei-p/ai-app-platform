import json
import tempfile
import unittest
from pathlib import Path

from src.core.mission_control import MissionStore


class MissionStoreTests(unittest.TestCase):
    def test_running_mission_recovers_as_paused_after_restart(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "missions.json"
            store = MissionStore(path)
            mission = store.create(
                project_slug="demo",
                goal="Improve the app safely",
                plan={"steps": [{"id": "inspect"}]},
            )
            store.update(
                mission.mission_id,
                status="running",
                phase="preflight",
                message="Checking project",
                cycle=1,
            )

            restarted = MissionStore(path)
            recovered = restarted.get(mission.mission_id)
            self.assertEqual(recovered.status, "paused")
            self.assertEqual(recovered.phase, "resume_required")
            self.assertEqual(recovered.cycle, 1)
            self.assertTrue(recovered.history)

    def test_restart_clears_process_local_build_job_reference(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "missions.json"
            store = MissionStore(path)
            mission = store.create(project_slug="demo", goal="Build safely", plan={})
            store.update(
                mission.mission_id,
                status="running",
                phase="build_running",
                cycle=2,
                build_job_id="process-local-job",
                evidence_refs=["evidence/preflight.json"],
            )

            restarted = MissionStore(path)
            recovered = restarted.get(mission.mission_id)

            self.assertEqual(recovered.status, "paused")
            self.assertEqual(recovered.phase, "resume_required")
            self.assertIsNone(recovered.build_job_id)
            self.assertEqual(recovered.cycle, 2)
            self.assertEqual(recovered.evidence_refs, ["evidence/preflight.json"])
            self.assertIn("new build approval", recovered.message)

    def test_corrupt_primary_recovers_last_known_good_mission_snapshot(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "missions.json"
            store = MissionStore(path)
            mission = store.create(project_slug="demo", goal="Preserve me", plan={})
            store.update(
                mission.mission_id,
                status="paused",
                phase="review",
                message="checkpoint one",
                cycle=1,
            )
            store.update(
                mission.mission_id,
                status="paused",
                phase="review",
                message="checkpoint two",
                cycle=2,
            )
            self.assertTrue(path.with_suffix(".json.bak").is_file())

            path.write_text("{broken-json", encoding="utf-8")
            restarted = MissionStore(path)
            recovered = restarted.get(mission.mission_id)

            self.assertEqual(recovered.mission_id, mission.mission_id)
            self.assertEqual(recovered.cycle, 1)
            self.assertEqual(recovered.message, "checkpoint one")
            restored_payload = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(restored_payload[0]["mission_id"], mission.mission_id)

    def test_active_build_cannot_be_cancelled_mid_write(self):
        with tempfile.TemporaryDirectory() as td:
            store = MissionStore(Path(td) / "missions.json")
            mission = store.create(project_slug="demo", goal="Build", plan={})
            store.update(
                mission.mission_id,
                status="running",
                phase="build_running",
                build_job_id="job-1",
            )
            with self.assertRaises(RuntimeError):
                store.cancel(mission.mission_id)

    def test_terminal_mission_does_not_reopen(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "missions.json"
            store = MissionStore(path)
            mission = store.create(project_slug="demo", goal="Done", plan={})
            store.update(
                mission.mission_id,
                status="completed",
                phase="done",
                result={"ok": True},
            )
            with self.assertRaises(ValueError):
                store.update(mission.mission_id, status="running")
            raw = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(raw[0]["status"], "completed")


if __name__ == "__main__":
    unittest.main()
