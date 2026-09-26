from __future__ import annotations
from dataclasses import dataclass, asdict
from .app_spec import AppSpec

@dataclass(frozen=True)
class RiskItem:
    key: str
    severity: str
    message: str
    required_before_release: bool

class ReleaseRiskAssessor:
    """Deterministic release checklist; not a legal opinion or guarantee."""
    def assess(self, spec: AppSpec) -> list[RiskItem]:
        rows: list[RiskItem] = [
            RiskItem("terms", "info", "公開前に利用規約と責任範囲を確認する。", True),
            RiskItem("privacy", "info", "収集データがある場合はプライバシーポリシーと削除手段を確認する。", True),
            RiskItem("security_test", "info", "公開用ビルドでセキュリティ・依存関係・権限を再確認する。", True),
        ]
        f = set(spec.features)
        if "authentication" in f:
            rows.append(RiskItem("account_security", "medium", "認証・パスワード再設定・アカウント削除・セッション管理を確認する。", True))
        if "payments" in f:
            rows.append(RiskItem("payments", "high", "決済事業者・ストア規約・返金・税表示を地域ごとに確認する。", True))
        if "notifications" in f:
            rows.append(RiskItem("notifications", "medium", "通知許可・解除・頻度・広告通知の扱いを確認する。", True))
        if "analytics" in f:
            rows.append(RiskItem("analytics", "medium", "分析データの同意・保持期間・第三者提供を確認する。", True))
        if "multi_language" in f or spec.region != "JP":
            rows.append(RiskItem("regional_review", "medium", "公開地域ごとのプライバシー・消費者保護・ストア要件を最新版で確認する。", True))
        for target in spec.targets:
            if target in {"ios", "macos"}:
                rows.append(RiskItem("apple_release", "medium", "Apple署名・審査・最新App Store要件は外部権限のため提出時に再確認する。", True))
            elif target == "android":
                rows.append(RiskItem("android_release", "medium", "Google Play利用時は最新の開発者・データ安全性・課金要件を提出時に再確認する。", True))
            elif target == "windows":
                rows.append(RiskItem("windows_release", "low", "配布方式に応じてコード署名・SmartScreen・Store要件を確認する。", True))
        return rows
