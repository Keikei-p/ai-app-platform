from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha1
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any
import json

from .config import DATA_DIR, ROOT_DIR
from .mission_control import MissionStore
from .strategic_goals import StrategicGoalStore, StrategicAutonomyEngine


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class MultiMissionE2EVerifier:
    """Verify a bounded long-term goal can advance through multiple Missions.

    The verifier uses the real persistent StrategicGoalStore, MissionStore and
    StrategicAutonomyEngine in an isolated temporary directory. It deliberately
    requires an explicit synthetic-human approval marker before a Mission can be
    completed. No build, deploy, billing, secrets or production data are touched.
    """

    SOURCE_PATHS = (
        "src/core/mission_control.py",
        "src/core/strategic_goals.py",
        "src/core/multi_mission_e2e.py",
    )

    def __init__(
        self,
        *,
        root_dir: Path | None = None,
        evidence_path: Path | None = None,
        attestation_path: Path | None = None,
    ):
        self.root_dir = Path(root_dir or ROOT_DIR)
        self.evidence_path = Path(
            evidence_path or (DATA_DIR / "completion_evidence" / "multi_mission_e2e.json")
        )
        self.attestation_path = Path(
            attestation_path or (self.root_dir / "evidence" / "multi_mission_e2e_ci.json")
        )

    def run(self) -> dict[str, Any]:
        with TemporaryDirectory(prefix="aivy-multi-mission-e2e-") as tmp:
            root = Path(tmp)
            missions = MissionStore(root / "missions.json")
            goals = StrategicGoalStore(root / "goals.json")

            project_rows = [{
                "slug": "e2e-project",
                "name": "E2E Project",
                "quality": "PASS",
                "status": "ready",
            }]

            def list_projects() -> list[dict[str, Any]]:
                return list(project_rows)

            def project_detail(_slug: str) -> dict[str, Any]:
                return {
                    "readiness": {
                        "preview_ready": True,
                        "release_ready": True,
                    },
                    "gaps": {"items": []},
                }

            def list_missions() -> list[dict[str, Any]]:
                return [x.to_dict() for x in missions.list(100)]

            def create_mission(*, goal: str, project_slug: str, max_cycles: int = 8) -> dict[str, Any]:
                row = missions.create(
                    project_slug=project_slug,
                    goal=goal,
                    plan={
                        "source": "multi-mission-e2e",
                        "approval_policy": "explicit_human_required",
                    },
                    max_cycles=max_cycles,
                )
                return row.to_dict()

            engine = StrategicAutonomyEngine(
                store=goals,
                list_projects=list_projects,
                project_detail=project_detail,
                list_missions=list_missions,
                create_mission=create_mission,
                history_path=root / "strategic_history.jsonl",
            )

            goal = engine.create_goal(
                project_slug="e2e-project",
                objective="安全な改善を複数Missionで継続する",
                max_auto_missions=2,
            )

            first_created = engine.run_cycle(trigger="e2e")
            m1_id = str((first_created.get("mission") or {}).get("mission_id") or "")
            m1 = missions.get(m1_id)
            missions.update(
                m1_id,
                status="approval_required",
                phase="build_approval",
                message="Synthetic safe preflight complete. Explicit approval required.",
                requires_approval=True,
                evidence_refs=["evidence/m1-preflight.json"],
            )
            wait_after_m1 = engine.run_cycle(trigger="e2e")

            # Synthetic human approval is explicit in Evidence and cannot be skipped.
            missions.update(
                m1_id,
                status="running",
                phase="build_running",
                message="Explicit synthetic-human approval recorded.",
                requires_approval=False,
                build_job_id="synthetic-human-approved-job-1",
                evidence_refs=[
                    "evidence/m1-preflight.json",
                    "approval:explicit-synthetic-human",
                ],
            )
            missions.update(
                m1_id,
                status="completed",
                phase="verified",
                message="Mission 1 completed with verified synthetic Evidence.",
                requires_approval=False,
                build_job_id=None,
                evidence_refs=[
                    "evidence/m1-preflight.json",
                    "approval:explicit-synthetic-human",
                    "evidence/m1-postflight.json",
                ],
                result={
                    "ok": True,
                    "approval": "explicit-synthetic-human",
                    "external_actions": False,
                },
            )

            second_created = engine.run_cycle(trigger="e2e")
            m2_id = str((second_created.get("mission") or {}).get("mission_id") or "")
            missions.update(
                m2_id,
                status="approval_required",
                phase="build_approval",
                message="Second Mission safe preflight complete. Explicit approval required.",
                requires_approval=True,
                evidence_refs=["evidence/m2-preflight.json"],
            )
            wait_after_m2 = engine.run_cycle(trigger="e2e")

            missions.update(
                m2_id,
                status="running",
                phase="build_running",
                message="Explicit synthetic-human approval recorded.",
                requires_approval=False,
                build_job_id="synthetic-human-approved-job-2",
                evidence_refs=[
                    "evidence/m2-preflight.json",
                    "approval:explicit-synthetic-human",
                ],
            )
            missions.update(
                m2_id,
                status="completed",
                phase="verified",
                message="Mission 2 completed with verified synthetic Evidence.",
                requires_approval=False,
                build_job_id=None,
                evidence_refs=[
                    "evidence/m2-preflight.json",
                    "approval:explicit-synthetic-human",
                    "evidence/m2-postflight.json",
                ],
                result={
                    "ok": True,
                    "approval": "explicit-synthetic-human",
                    "external_actions": False,
                },
            )

            after_budget = engine.run_cycle(trigger="e2e")
            saved_goal = goals.get(str(goal["goal_id"]))
            final_m1 = missions.get(m1_id)
            final_m2 = missions.get(m2_id)

            checks = {
                "first_mission_created": first_created.get("status") == "mission_created",
                "first_waited_for_approval": (
                    wait_after_m1.get("status") == "waiting_on_mission"
                    and wait_after_m1.get("requires_approval") is True
                ),
                "second_created_only_after_first_completed": (
                    second_created.get("status") == "mission_created"
                    and m2_id
                    and m2_id != m1_id
                    and m1_id in saved_goal.completed_mission_ids
                ),
                "second_waited_for_approval": (
                    wait_after_m2.get("status") == "waiting_on_mission"
                    and wait_after_m2.get("requires_approval") is True
                ),
                "two_missions_completed": (
                    final_m1.status == "completed"
                    and final_m2.status == "completed"
                ),
                "explicit_approval_evidence_preserved": (
                    "approval:explicit-synthetic-human" in final_m1.evidence_refs
                    and "approval:explicit-synthetic-human" in final_m2.evidence_refs
                ),
                "mission_budget_stops_more_work": (
                    after_budget.get("status") == "mission_budget_reached"
                    and goals.get(str(goal["goal_id"])).status == "paused"
                ),
                "no_auto_build_approval": engine.status().get("build_auto_approval") is False,
            }
            verified = all(checks.values())

            payload = {
                "schema_version": 1,
                "kind": "multi_mission_end_to_end",
                "verified": verified,
                "goal_id": str(goal["goal_id"]),
                "mission_ids": [m1_id, m2_id],
                "checks": checks,
                "missions_created": saved_goal.missions_created,
                "completed_mission_ids": list(saved_goal.completed_mission_ids),
                "approval_boundary_observed": True,
                "external_actions": False,
                "credentials_used": False,
                "paid_actions": False,
                "production_data_written": False,
                "source_blobs": self.source_blobs(),
                "created_at": _now(),
            }

        self.evidence_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = self.evidence_path.with_suffix(self.evidence_path.suffix + ".tmp")
        tmp_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        tmp_path.replace(self.evidence_path)
        return payload

    def status(self) -> dict[str, Any]:
        local = self._read(self.evidence_path)
        if self._valid_evidence(local):
            return {**local, "source": "local_runtime_evidence", "stale": False}

        attestation = self._read(self.attestation_path)
        if self._valid_evidence(attestation):
            return {**attestation, "source": "repository_ci_attestation", "stale": False}

        return {
            "schema_version": 1,
            "kind": "multi_mission_end_to_end",
            "verified": False,
            "source": "none",
            "stale": bool(local or attestation),
            "checks": {},
            "source_blobs": self.source_blobs(),
            "created_at": None,
        }

    def source_blobs(self) -> dict[str, str]:
        rows: dict[str, str] = {}
        for rel in self.SOURCE_PATHS:
            path = self.root_dir / rel
            if path.is_file():
                rows[rel] = self._git_blob_sha(path)
        return rows

    def _valid_evidence(self, raw: dict[str, Any]) -> bool:
        if raw.get("verified") is not True:
            return False
        expected = raw.get("source_blobs")
        if not isinstance(expected, dict) or not expected:
            return False
        current = self.source_blobs()
        if current != {str(k): str(v) for k, v in expected.items()}:
            return False
        checks = raw.get("checks")
        if not isinstance(checks, dict) or not checks:
            return False
        required = {
            "first_mission_created",
            "first_waited_for_approval",
            "second_created_only_after_first_completed",
            "second_waited_for_approval",
            "two_missions_completed",
            "explicit_approval_evidence_preserved",
            "mission_budget_stops_more_work",
            "no_auto_build_approval",
        }
        return required.issubset(checks) and all(checks.get(key) is True for key in required)

    @staticmethod
    def _read(path: Path) -> dict[str, Any]:
        if not path.is_file():
            return {}
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            return raw if isinstance(raw, dict) else {}
        except Exception:
            return {}

    @staticmethod
    def _git_blob_sha(path: Path) -> str:
        text = path.read_text(encoding="utf-8")
        normalized = text.replace("\r\n", "\n").replace("\r", "\n").encode("utf-8")
        header = f"blob {len(normalized)}\0".encode("ascii")
        return sha1(header + normalized).hexdigest()
