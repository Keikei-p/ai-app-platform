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

    def test_unrecoverable_mission_files_are_never_overwritten(self):
        for condition in (
            "primary_only_corrupt",
            "both_corrupt",
            "backup_only_corrupt",
            "primary_valid_backup_corrupt",
        ):
            with self.subTest(condition=condition):
                with tempfile.TemporaryDirectory() as td:
                    path = Path(td) / "missions.json"
                    backup = path.with_suffix(".json.bak")
                    store = MissionStore(path)
                    mission = store.create(
                        project_slug="demo", goal="Preserve data", plan={}
                    )

                    if condition == "primary_only_corrupt":
                        path.write_bytes(b"{primary-unreadable")
                    elif condition == "both_corrupt":
                        store.update(mission.mission_id, phase="review")
                        path.write_bytes(b"{primary-unreadable")
                        backup.write_bytes(b"{backup-unreadable")
                    elif condition == "backup_only_corrupt":
                        path.unlink()
                        backup.write_bytes(b"{backup-unreadable")
                    else:
                        backup.write_bytes(b"{backup-unreadable")

                    before = {
                        p: p.read_bytes()
                        for p in (path, backup)
                        if p.exists()
                    }
                    # A new process must not turn an unreadable on-disk state
                    # into an empty writable Mission database.
                    restarted = MissionStore(path)
                    with self.assertRaisesRegex(
                        RuntimeError, "Mission persistence is blocked"
                    ):
                        restarted.create(
                            project_slug="demo", goal="Should not overwrite", plan={}
                        )
                    self.assertEqual(
                        {
                            p: p.read_bytes()
                            for p in (path, backup)
                            if p.exists()
                        },
                        before,
                    )

    def test_state_corrupted_after_read_still_blocks_write(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "missions.json"
            store = MissionStore(path)
            store.create(project_slug="demo", goal="Before corruption", plan={})
            rows = store._read()
            path.write_bytes(b"{corrupted-since-read")
            original = path.read_bytes()

            with self.assertRaisesRegex(RuntimeError, "Mission persistence is blocked"):
                store._write(rows)

            self.assertEqual(path.read_bytes(), original)
            self.assertFalse(path.with_suffix(".json.bak").exists())

    def test_clean_install_still_creates_missions(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "missions.json"
            store = MissionStore(path)
            mission = store.create(project_slug="demo", goal="New installation", plan={})
            self.assertEqual(store.get(mission.mission_id).goal, "New installation")
            self.assertEqual(
                json.loads(path.read_text(encoding="utf-8"))[0]["mission_id"],
                mission.mission_id,
            )

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


    def test_unknown_future_and_malformed_rows_survive_update_and_create(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "missions.json"
            store = MissionStore(path)
            mission = store.create(project_slug="demo", goal="Keep data", plan={})
            original = json.loads(path.read_text(encoding="utf-8"))
            original[0]["future_extension"] = {"keep": ["nested", 42]}
            future = {**original[0], "mission_id": "future-mission", "schema_version": 99}
            malformed = {"mission_id": "malformed", "plan": ["unknown-format"]}
            opaque = ["unrecognized", {"v": 3}]
            original.extend([future, malformed, opaque])
            path.write_text(json.dumps(original), encoding="utf-8")

            store.update(mission.mission_id, phase="review", cycle=1)
            after_update = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(after_update[0]["future_extension"], original[0]["future_extension"])
            self.assertEqual(after_update[1:], [future, malformed, opaque])
            self.assertEqual(after_update[0]["cycle"], 1)
            self.assertEqual(
                json.loads(path.with_suffix(".json.bak").read_text(encoding="utf-8")),
                original,
            )

            new_mission = store.create(project_slug="demo", goal="Another", plan={})
            after_create = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(after_create[1:4], [future, malformed, opaque])
            self.assertEqual(after_create[4]["mission_id"], new_mission.mission_id)
            self.assertEqual(MissionStore(path).get(mission.mission_id).cycle, 1)

    def test_recovery_preserves_unknown_rows_while_pausing_active_mission(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "missions.json"
            store = MissionStore(path)
            mission = store.create(project_slug="demo", goal="Recover", plan={})
            store.update(mission.mission_id, status="running", phase="build_running")
            original = json.loads(path.read_text(encoding="utf-8"))
            future = {**original[0], "mission_id": "future", "schema_version": 2}
            original.append(future)
            path.write_text(json.dumps(original), encoding="utf-8")

            restarted = MissionStore(path)
            self.assertEqual(restarted.get(mission.mission_id).phase, "resume_required")
            saved = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(saved[1], future)


if __name__ == "__main__":
    unittest.main()
