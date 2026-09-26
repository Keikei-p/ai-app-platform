from __future__ import annotations
from .app_spec import AppSpec, AppPlan, BuildStep

class IntentPlanner:
    """Deterministic v0.3 planner. A future local model may enrich this plan, but policy remains outside the model."""

    APP_TYPES = [
        ("booking", ["予約", "booking", "appointment"]),
        ("todo", ["todo", "タスク", "やること"]),
        ("inventory", ["在庫", "inventory"]),
        ("crm", ["顧客管理", "crm", "顧客"]),
        ("dashboard", ["ダッシュボード", "集計", "dashboard"]),
        ("ecommerce", ["ec", "通販", "ショップ", "商品販売", "ecommerce"]),
    ]
    FEATURES = [
        ("authentication", ["ログイン", "アカウント", "認証"]),
        ("database", ["データベース", "db", "保存"]),
        ("search", ["検索"]),
        ("notifications", ["通知", "プッシュ"]),
        ("payments", ["決済", "課金", "支払い"]),
        ("admin", ["管理者", "管理画面"]),
        ("analytics", ["分析", "集計", "レポート"]),
        ("multi_language", ["多言語", "英語", "海外"]),
        ("offline", ["オフライン"]),
    ]
    TARGETS = [
        ("windows", ["windows", "ウィンドウズ", "exe", "msix"]),
        ("android", ["android", "アンドロイド", "apk", "aab"]),
        ("ios", ["iphone", "ipad", "ios", "アイフォン"]),
        ("macos", ["mac", "macos", "マック"]),
        ("web", ["web", "ブラウザ", "ウェブ"]),
    ]

    def _matches(self, text: str, table: list[tuple[str, list[str]]]) -> list[str]:
        lowered = text.lower()
        return [key for key, words in table if any(w.lower() in lowered for w in words)]

    def plan(self, project_name: str, slug: str, instruction: str, risk_level: str = "normal") -> AppPlan:
        kinds = self._matches(instruction, self.APP_TYPES)
        app_type = kinds[0] if kinds else "generic"
        features = list(dict.fromkeys(self._matches(instruction, self.FEATURES)))
        targets = list(dict.fromkeys(self._matches(instruction, self.TARGETS))) or ["web"]
        spec = AppSpec(
            project_name=project_name,
            slug=slug,
            summary=instruction.strip(),
            app_type=app_type,
            features=features,
            targets=targets,
            risk_level=risk_level,
        )
        steps = [
            BuildStep("snapshot", "変更前スナップショット"),
            BuildStep("spec", "アプリ仕様を保存"),
            BuildStep("generate", "スターター実装を生成"),
            BuildStep("test", "ローカル自動テスト"),
            BuildStep("audit", "監査ログを保存"),
        ]
        return AppPlan(spec=spec, steps=steps)
