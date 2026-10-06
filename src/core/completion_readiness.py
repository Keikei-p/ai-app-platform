from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any, Callable


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class CompletionCriterion:
    criterion_id: str
    title: str
    weight: int
    score: int
    status: str
    evidence: tuple[str, ...]
    gaps: tuple[str, ...]
    next_action: str

    def to_dict(self) -> dict[str, Any]:
        row = asdict(self)
        row["evidence"] = list(self.evidence)
        row["gaps"] = list(self.gaps)
        return row


class CompletionReadinessEngine:
    """Evidence-oriented platform completion assessment.

    This score is intentionally strict. Aivy does not get credit merely because
    a class or button exists. Runtime autonomy must be enabled, safety boundaries
    must remain closed, and evidence-oriented quality systems must be present.
    External account-dependent actions such as store signing/publishing are
    reported separately and never auto-approved to inflate the score.
    """

    def __init__(
        self,
        *,
        capability_snapshot: Callable[[], dict[str, Any]],
        self_drive_status: Callable[[], dict[str, Any]],
        daily_evolution_status: Callable[[], dict[str, Any]],
        strategic_status: Callable[[], dict[str, Any]],
        learning_status: Callable[[], dict[str, Any]],
        health_status: Callable[[], dict[str, Any]],
    ):
        self.capability_snapshot = capability_snapshot
        self.self_drive_status = self_drive_status
        self.daily_evolution_status = daily_evolution_status
        self.strategic_status = strategic_status
        self.learning_status = learning_status
        self.health_status = health_status

    def assess(self) -> dict[str, Any]:
        caps = dict(self.capability_snapshot() or {})
        drive = dict(self.self_drive_status() or {})
        daily = dict(self.daily_evolution_status() or {})
        strategic = dict(self.strategic_status() or {})
        learning = dict(self.learning_status() or {})
        health = dict(self.health_status() or {})

        criteria = [
            self._criterion(
                "conversation",
                "自然会話・意図理解",
                10,
                checks={
                    "context aware": caps.get("context_aware_conversation"),
                    "long continuity": caps.get("long_conversation_continuity"),
                    "intent routing": caps.get("conversation_intent_routing"),
                    "typo tolerance": caps.get("typo_tolerant_language_understanding"),
                    "local fallback": caps.get("local_ollama_conversation_fallback"),
                },
                next_action="会話文脈・誤字・参照解決の回帰ケースを追加する",
            ),
            self._criterion(
                "creation",
                "APP / WEB / AUTOMATION生成",
                12,
                checks={
                    "web": caps.get("web"),
                    "windows": caps.get("windows"),
                    "android": caps.get("android"),
                    "ios source": caps.get("ios_source"),
                    "automation": caps.get("social_automation"),
                    "artifact catalog": caps.get("artifact_catalog"),
                    "cross-mode real E2E": caps.get("cross_mode_real_app_e2e_verified"),
                },
                next_action="各モードの実生成E2Eケースを増やし失敗率を下げる",
            ),
            self._criterion(
                "agent_team",
                "AI開発チーム・並列実行",
                10,
                checks={
                    "planner": caps.get("agent_planning"),
                    "specialists": bool(caps.get("specialist_agents")),
                    "reviewed tools": caps.get("reviewed_tool_executor"),
                    "execution council": caps.get("specialist_execution_council"),
                    "parallel sandbox": caps.get("parallel_sandbox_workers"),
                    "single writer": caps.get("source_write_single_coordinator"),
                },
                next_action="Agent間競合・失敗時再実行のStress Testを追加する",
            ),
            self._criterion(
                "quality",
                "品質・Evidence・Release Gate",
                16,
                checks={
                    "health check": caps.get("project_health_check"),
                    "development certificate": caps.get("development_certificate"),
                    "regression": caps.get("regression_guardian"),
                    "requirements": caps.get("requirement_guardian"),
                    "dependencies": caps.get("dependency_guardian"),
                    "accessibility": caps.get("accessibility_guardian"),
                    "performance": caps.get("performance_guardian"),
                    "release guardian": caps.get("release_guardian"),
                },
                next_action="実生成物でGuardian全通過Evidenceを継続蓄積する",
            ),
            self._criterion(
                "recovery_learning",
                "自己修復・学習",
                12,
                checks={
                    "recovery supervisor": caps.get("recovery_supervisor"),
                    "independent review": caps.get("independent_recovery_review"),
                    "validated recovery": caps.get("validated_recovery_learning"),
                    "verified learning": caps.get("verified_learning_flywheel"),
                    "candidate arena": caps.get("candidate_arena"),
                    "model benchmark": caps.get("model_benchmark_store"),
                },
                next_action="失敗注入テストを増やし修復成功率を測定する",
            ),
            self._criterion(
                "autonomy",
                "安全な自走",
                12,
                checks={
                    "scheduler": caps.get("self_drive_scheduler"),
                    "priority queue": caps.get("self_drive_priority_queue"),
                    "approval boundary": caps.get("self_drive_approval_boundary"),
                    "daily backlog": caps.get("persistent_daily_backlog"),
                    "runtime enabled": drive.get("enabled"),
                    "background active": drive.get("background_active"),
                    "no approval bypass": drive.get("approval_bypass_allowed") is False,
                },
                next_action="長時間自走Soak Testで停止・復帰・失敗継続を検証する",
            ),
            self._criterion(
                "daily_evolution",
                "毎日自動進化",
                10,
                checks={
                    "engine": caps.get("daily_evolution_engine"),
                    "catchup": caps.get("daily_evolution_catchup"),
                    "bounded practice": caps.get("daily_evolution_single_practice"),
                    "enabled": daily.get("enabled"),
                    "background active": daily.get("background_active"),
                    "source protected": daily.get("source_self_edit_allowed") is False,
                },
                next_action="複数日を模擬したCatch-up / partial retryの耐久試験を増やす",
            ),
            self._criterion(
                "strategy",
                "長期目標→Mission自動生成",
                8,
                checks={
                    "long term goals": caps.get("strategic_long_term_goals"),
                    "bounded mission generation": caps.get("automatic_bounded_mission_generation"),
                    "approval boundary": caps.get("strategic_mission_approval_boundary"),
                    "no build auto approval": strategic.get("build_auto_approval") is False,
                    "mission limit": strategic.get("max_missions_created_per_cycle") == 1,
                    "multi-mission E2E": caps.get("multi_mission_end_to_end_verified"),
                },
                next_action="複数Mission完走シナリオを実アプリで検証する",
            ),
            self._criterion(
                "productization",
                "販売・譲渡・OEM準備",
                10,
                checks={
                    "credential store": caps.get("dedicated_credential_store"),
                    "connector registry": caps.get("connector_registry"),
                    "credential-free export": caps.get("credential_free_config_export"),
                    "transfer audit": caps.get("transfer_audit"),
                    "transfer package": caps.get("non_destructive_transfer_package"),
                    "ownership profile": caps.get("ownership_profile"),
                    "OEM foundation": caps.get("oem_branding_foundation"),
                    "buyer journey E2E": caps.get("buyer_productization_e2e_verified"),
                },
                next_action="新品Ivyから移行・譲渡までのBuyer Journey E2Eを再検証する",
            ),
            self._criterion(
                "operations",
                "配布・運用・長時間安定性",
                10,
                checks={
                    "release manager": caps.get("release_manager"),
                    "observable jobs": caps.get("observable_build_jobs"),
                    "production monitor": caps.get("production_monitor"),
                    "cost guard": caps.get("cost_guard"),
                    "secrets guard": caps.get("secrets_guard"),
                    "health guarded": str(health.get("status") or "").lower() not in {"failed", "critical"},
                    # A local-first process is not equivalent to proven 24/7 operation.
                    "24h soak evidence": bool(caps.get("long_run_soak_verified")),
                    "cloud runtime ready": bool(caps.get("cloud_runtime_ready")),
                },
                next_action="24時間相当のSoak Testと再起動復旧Evidenceを作る",
            ),
        ]

        score = sum(x.score for x in criteria)
        total_weight = sum(x.weight for x in criteria)
        score = max(0, min(total_weight, score))
        gaps = [
            {
                "criterion_id": row.criterion_id,
                "title": row.title,
                "missing": list(row.gaps),
                "next_action": row.next_action,
                "lost_points": row.weight - row.score,
            }
            for row in criteria
            if row.score < row.weight
        ]
        gaps.sort(key=lambda x: (-int(x["lost_points"]), x["criterion_id"]))
        external_dependencies = []
        if not caps.get("ios_signed_ipa"):
            external_dependencies.append(
                "iOS署名IPA/ストア提出はAppleアカウント・署名資格情報・人の承認が必要"
            )

        complete = score == total_weight and not gaps
        return {
            "score": score,
            "max_score": total_weight,
            "percentage": round((score / total_weight) * 100, 1) if total_weight else 0.0,
            "status": "complete" if complete else "in_progress",
            "complete": complete,
            "criteria": [x.to_dict() for x in criteria],
            "gaps": gaps,
            "highest_priority_gap": gaps[0] if gaps else None,
            "external_dependencies": external_dependencies,
            "verified_learning_examples": int(learning.get("verified_examples") or 0),
            "average_learning_score": float(learning.get("average_score") or 0.0),
            "rule": (
                "100% requires every scored criterion to be fully evidenced. "
                "Protected external actions are never auto-approved merely to raise the score."
            ),
            "created_at": _now(),
        }

    @staticmethod
    def _criterion(
        criterion_id: str,
        title: str,
        weight: int,
        *,
        checks: dict[str, Any],
        next_action: str,
    ) -> CompletionCriterion:
        passed = [name for name, value in checks.items() if value is True]
        failed = [name for name, value in checks.items() if value is not True]
        total = max(1, len(checks))
        ratio = len(passed) / total
        score = int(round(weight * ratio))
        if not failed:
            score = weight
            status = "pass"
        elif passed:
            status = "partial"
        else:
            status = "blocked"
        return CompletionCriterion(
            criterion_id=criterion_id,
            title=title,
            weight=weight,
            score=max(0, min(weight, score)),
            status=status,
            evidence=tuple(passed),
            gaps=tuple(failed),
            next_action=next_action,
        )
