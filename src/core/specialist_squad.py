from __future__ import annotations

from dataclasses import dataclass
from typing import Any


CORE_ROLES = ("architect", "coding", "test", "security")
OPTIONAL_RULES = {
    "research": (
        "research", "latest", "current", "compare", "調査", "最新", "比較", "仕様確認",
    ),
    "database": (
        "database", "db", "sql", "sqlite", "firestore", "firebase", "schema",
        "migration", "index", "データベース", "保存", "永続", "移行", "集計",
    ),
    "web": (
        "web", "website", "browser", "html", "css", "javascript", "frontend",
        "backend", "wordpress", "cloudflare", "サイト", "ブラウザ", "ホームページ",
    ),
    "mobile": (
        "android", "ios", "iphone", "ipad", "mobile", "smartphone", "apk", "ipa",
        "flutter", "react native", "スマホ", "モバイル", "アプリ化",
    ),
    "design": (
        "design", "ui", "ux", "responsive", "layout", "デザイン", "見た目",
        "レスポンシブ", "レイアウト", "使いやす", "美しく",
    ),
    "performance": (
        "performance", "latency", "speed", "startup", "memory", "cpu", "gpu",
        "optimize", "高速", "速度", "重い", "遅い", "負荷", "最適化",
    ),
    "accessibility": (
        "accessibility", "a11y", "keyboard", "contrast", "aria", "screen reader",
        "アクセシビリティ", "キーボード", "コントラスト", "読みやす",
    ),
    "devops": (
        "deploy", "deployment", "server", "cloud", "docker", "container",
        "github actions", "ci", "cd", "monitor", "rollback", "デプロイ",
        "公開", "サーバー", "クラウド", "監視", "自動更新",
    ),
    "build": (
        "build", "package", "artifact", "exe", "apk", "ipa", "ビルド",
        "成果物", "インストーラー", "ダウンロード",
    ),
    "release": (
        "release", "publish", "store", "app store", "google play", "production",
        "リリース", "公開", "本番", "ストア",
    ),
}


@dataclass(frozen=True)
class SquadSelection:
    goal: str
    roles: tuple[str, ...]
    worker_roles: tuple[str, ...]
    reasons: dict[str, tuple[str, ...]]
    scores: dict[str, int]

    def to_dict(self) -> dict[str, Any]:
        return {
            "goal": self.goal,
            "roles": list(self.roles),
            "worker_roles": list(self.worker_roles),
            "reasons": {key: list(value) for key, value in self.reasons.items()},
            "scores": dict(self.scores),
        }


class SpecialistSquadSelector:
    """Deterministic specialist team selection from the user's goal.

    Selection is transparent and bounded. Coordinator is always present in the
    full team. Core engineering roles stay available, while optional specialists
    are added only when the goal or project metadata makes them relevant.
    """

    WORKER_CAP = 6

    def select(
        self,
        goal: str,
        *,
        project_detail: dict[str, Any] | None = None,
        worker_cap: int | None = None,
    ) -> SquadSelection:
        clean_goal = goal.strip()
        if not clean_goal:
            raise ValueError("goal is required")
        detail = dict(project_detail or {})
        corpus = self._corpus(clean_goal, detail)

        scores: dict[str, int] = {role: 100 for role in CORE_ROLES}
        reasons: dict[str, list[str]] = {
            role: ["core engineering role"] for role in CORE_ROLES
        }

        for role, terms in OPTIONAL_RULES.items():
            hits = [term for term in terms if term in corpus]
            if not hits:
                continue
            score = min(95, 35 + len(hits) * 12)
            scores[role] = max(scores.get(role, 0), score)
            reasons.setdefault(role, []).append(
                "matched: " + ", ".join(hits[:5])
            )

        targets = {
            str(x).strip().lower()
            for x in detail.get("targets") or ()
            if str(x).strip()
        }
        app_type = str(detail.get("app_type") or "").strip().lower()

        if targets & {"android", "ios"} or app_type in {"mobile", "android", "ios"}:
            self._boost(scores, reasons, "mobile", 90, "project targets mobile")
            self._boost(scores, reasons, "accessibility", 55, "mobile UX relevance")
        if "web" in targets or app_type in {"web", "website", "fullstack"}:
            self._boost(scores, reasons, "web", 90, "project targets web")
            self._boost(scores, reasons, "accessibility", 55, "web UX relevance")
            self._boost(scores, reasons, "performance", 50, "web performance relevance")
        if targets & {"windows", "android", "ios"}:
            self._boost(scores, reasons, "build", 60, "binary/package target")

        ordered_optional = sorted(
            (role for role in scores if role not in CORE_ROLES),
            key=lambda role: (-scores[role], role),
        )
        full_roles = ["coordinator", *CORE_ROLES, *ordered_optional]

        cap = max(4, min(int(worker_cap or self.WORKER_CAP), self.WORKER_CAP))
        worker_candidates = [
            role for role in (*CORE_ROLES, *ordered_optional)
            if role not in {"build", "release"}
        ]
        worker_roles = tuple(worker_candidates[:cap])

        return SquadSelection(
            goal=clean_goal,
            roles=tuple(dict.fromkeys(full_roles)),
            worker_roles=worker_roles,
            reasons={key: tuple(value) for key, value in reasons.items()},
            scores=scores,
        )

    @staticmethod
    def _boost(
        scores: dict[str, int],
        reasons: dict[str, list[str]],
        role: str,
        score: int,
        reason: str,
    ) -> None:
        scores[role] = max(scores.get(role, 0), score)
        reasons.setdefault(role, []).append(reason)

    @staticmethod
    def _corpus(goal: str, detail: dict[str, Any]) -> str:
        values = [
            goal,
            str(detail.get("name") or ""),
            str(detail.get("app_type") or ""),
            " ".join(str(x) for x in detail.get("targets") or ()),
            str(detail.get("status") or ""),
        ]
        return " ".join(values).lower()
