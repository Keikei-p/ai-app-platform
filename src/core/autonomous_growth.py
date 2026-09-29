from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import hashlib
import json
import threading

from .config import DATA_DIR
from .learning_flywheel import AivyLearningFlywheel


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class GrowthSkill:
    skill_id: str
    mode: str
    title: str
    lesson: str
    best_score: int
    evidence_count: int
    source_examples: tuple[str, ...]
    updated_at: str

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["source_examples"] = list(self.source_examples)
        return data


class AutonomousGrowthEngine:
    """Safe, evidence-backed self-growth for Aivy.

    The engine turns verified successful builds into reusable skills. It never
    rewrites Aivy source code, changes protected policy, touches secrets,
    publishes externally, spends money, or merges main. Source-code evolution
    remains in the separate human-reviewed Evolution pipeline.

    This gives Aivy useful unattended growth today: successful experience is
    continuously compressed into reusable guidance for future work.
    """

    def __init__(
        self,
        learning: AivyLearningFlywheel | None = None,
        skills_path: Path | None = None,
        settings_path: Path | None = None,
    ):
        self.learning = learning or AivyLearningFlywheel()
        self.skills_path = skills_path or (DATA_DIR / "aivy_growth_skills.json")
        self.settings_path = settings_path or (DATA_DIR / "aivy_autonomous_growth.json")
        self.skills_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def settings(self) -> dict[str, Any]:
        default = {
            "enabled": True,
            "interval_seconds": 900,
            "safe_scope": "verified-learning-only",
            "allow_source_self_edit": False,
            "allow_main_merge": False,
            "allow_external_publish": False,
            "allow_paid_actions": False,
        }
        if not self.settings_path.is_file():
            return default
        try:
            raw = json.loads(self.settings_path.read_text(encoding="utf-8"))
        except Exception:
            return default
        if not isinstance(raw, dict):
            return default
        merged = {**default, **raw}
        merged["enabled"] = bool(merged.get("enabled"))
        merged["interval_seconds"] = max(300, min(int(merged.get("interval_seconds") or 900), 86400))
        merged["allow_source_self_edit"] = False
        merged["allow_main_merge"] = False
        merged["allow_external_publish"] = False
        merged["allow_paid_actions"] = False
        return merged

    def set_enabled(self, enabled: bool) -> dict[str, Any]:
        cfg = self.settings()
        cfg["enabled"] = bool(enabled)
        cfg["updated_at"] = _now()
        self._write_json(self.settings_path, cfg)
        return cfg

    def status(self) -> dict[str, Any]:
        cfg = self.settings()
        skills = self.skills()
        learning = self.learning.stats()
        raw = self._read_settings_raw()
        return {
            "enabled": bool(cfg["enabled"]),
            "interval_seconds": int(cfg["interval_seconds"]),
            "safe_scope": cfg["safe_scope"],
            "skills": len(skills),
            "verified_examples": int(learning.get("verified_examples") or 0),
            "average_score": float(learning.get("average_score") or 0.0),
            "last_run_at": raw.get("last_run_at"),
            "last_result": raw.get("last_result"),
            "allow_source_self_edit": False,
            "allow_main_merge": False,
            "allow_external_publish": False,
            "allow_paid_actions": False,
        }

    def run_cycle(self) -> dict[str, Any]:
        cfg = self.settings()
        if not cfg["enabled"]:
            result = {
                "status": "disabled",
                "skills_added": 0,
                "skills_updated": 0,
                "source_code_mutated": False,
            }
            self._record_cycle(result)
            return result

        examples = self.learning.recent(1000)
        current = {skill.skill_id: skill for skill in self.skills()}
        added = 0
        updated = 0
        accepted = 0

        for row in examples:
            quality = dict(row.quality or {})
            if row.evaluation_score < 90:
                continue
            if not all(bool(quality.get(key)) for key in (
                "tests_passed", "design_passed", "security_passed", "preview_ready"
            )):
                continue
            lesson = " ".join(str(row.lesson or "").split()).strip()
            if not lesson:
                continue

            accepted += 1
            mode = self._mode_for(row.instruction)
            identity = (mode + "\n" + lesson).encode("utf-8")
            skill_id = hashlib.sha256(identity).hexdigest()[:24]
            source_id = str(row.example_id)
            existing = current.get(skill_id)
            if existing is None:
                current[skill_id] = GrowthSkill(
                    skill_id=skill_id,
                    mode=mode,
                    title=self._title_for(mode),
                    lesson=lesson[:1600],
                    best_score=max(0, min(100, int(row.evaluation_score))),
                    evidence_count=1,
                    source_examples=(source_id,),
                    updated_at=_now(),
                )
                added += 1
                continue

            sources = tuple(dict.fromkeys((*existing.source_examples, source_id)))[-50:]
            next_item = GrowthSkill(
                skill_id=existing.skill_id,
                mode=existing.mode,
                title=existing.title,
                lesson=existing.lesson,
                best_score=max(existing.best_score, int(row.evaluation_score)),
                evidence_count=len(sources),
                source_examples=sources,
                updated_at=_now(),
            )
            if next_item.source_examples != existing.source_examples or next_item.best_score != existing.best_score:
                current[skill_id] = next_item
                updated += 1

        rows = sorted(
            current.values(),
            key=lambda x: (x.best_score, x.evidence_count, x.updated_at),
            reverse=True,
        )[:500]
        self._write_skills(rows)

        learning = self.learning.stats()
        verified = int(learning.get("verified_examples") or 0)
        repaired = int(learning.get("repaired_examples") or 0)
        average = float(learning.get("average_score") or 0.0)
        weaknesses: list[str] = []
        if verified and repaired / verified >= 0.25:
            weaknesses.append("repair_rate_high")
        if verified and average < 95:
            weaknesses.append("verified_quality_below_95")
        if verified < 5:
            weaknesses.append("more_verified_examples_needed")

        result = {
            "status": "completed",
            "verified_examples_checked": len(examples),
            "eligible_examples": accepted,
            "skills_added": added,
            "skills_updated": updated,
            "total_skills": len(rows),
            "weaknesses": weaknesses,
            "source_code_mutated": False,
            "protected_actions_unchanged": True,
            "rule": (
                "Autonomous growth may learn from verified outcomes and create reusable skills. "
                "Aivy source edits, protected policy, secrets, paid actions, external publishing "
                "and main merges remain outside this unattended loop."
            ),
        }
        self._record_cycle(result)
        return result

    def skills(self) -> list[GrowthSkill]:
        if not self.skills_path.is_file():
            return []
        try:
            raw = json.loads(self.skills_path.read_text(encoding="utf-8"))
        except Exception:
            return []
        rows: list[GrowthSkill] = []
        for item in raw if isinstance(raw, list) else []:
            try:
                rows.append(GrowthSkill(
                    skill_id=str(item["skill_id"]),
                    mode=str(item.get("mode") or "app"),
                    title=str(item.get("title") or "Verified skill"),
                    lesson=str(item.get("lesson") or ""),
                    best_score=max(0, min(100, int(item.get("best_score") or 0))),
                    evidence_count=max(0, int(item.get("evidence_count") or 0)),
                    source_examples=tuple(str(x) for x in item.get("source_examples") or ()),
                    updated_at=str(item.get("updated_at") or ""),
                ))
            except Exception:
                continue
        return rows

    def context_for(self, text: str, limit: int = 5) -> list[str]:
        mode = self._mode_for(text)
        lowered = text.lower()
        scored: list[tuple[int, int, GrowthSkill]] = []
        for skill in self.skills():
            score = 3 if skill.mode == mode else 0
            lesson_lower = skill.lesson.lower()
            for token in self._tokens(lowered):
                if len(token) >= 2 and token in lesson_lower:
                    score += 1
            if score > 0:
                scored.append((score, skill.best_score, skill))
        scored.sort(key=lambda row: (row[0], row[1]), reverse=True)
        return [row[2].lesson for row in scored[: max(1, min(limit, 12))]]

    @staticmethod
    def _mode_for(text: str) -> str:
        lowered = str(text or "").lower()
        if any(x in lowered for x in (
            "webサイト", "サイト", "ホームページ", "wordpress", "seo", "lp", "ポートフォリオ"
        )):
            return "web"
        if any(x in lowered for x in (
            "自動化", "自動投稿", "定期実行", "workflow", "cron", "スケジュール"
        )):
            return "automation"
        return "app"

    @staticmethod
    def _title_for(mode: str) -> str:
        return {
            "web": "Verified Web Build Skill",
            "automation": "Verified Automation Skill",
            "app": "Verified App Build Skill",
        }.get(mode, "Verified Build Skill")

    @staticmethod
    def _tokens(text: str) -> tuple[str, ...]:
        raw = text.replace("、", " ").replace("。", " ").replace("/", " ").replace(":", " ")
        return tuple(dict.fromkeys(x.strip() for x in raw.split() if x.strip()))[:80]

    def _read_settings_raw(self) -> dict[str, Any]:
        if not self.settings_path.is_file():
            return {}
        try:
            raw = json.loads(self.settings_path.read_text(encoding="utf-8"))
            return raw if isinstance(raw, dict) else {}
        except Exception:
            return {}

    def _record_cycle(self, result: dict[str, Any]) -> None:
        cfg = self.settings()
        cfg["last_run_at"] = _now()
        cfg["last_result"] = result
        self._write_json(self.settings_path, cfg)

    def _write_skills(self, rows: list[GrowthSkill]) -> None:
        with self._lock:
            self._write_json(self.skills_path, [x.to_dict() for x in rows])

    @staticmethod
    def _write_json(path: Path, data: Any) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(path)
