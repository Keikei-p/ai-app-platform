from __future__ import annotations
from dataclasses import dataclass

@dataclass(frozen=True)
class SafetyDecision:
    allowed: bool
    level: str
    reasons: list[str]
    requires_human_review: bool = False

class SafetyGate:
    """Deterministic pre-AI safety gate. AI-generated code cannot bypass this policy layer."""

    BLOCK_PATTERNS = {
        "malware": ["ランサムウェア", "マルウェア", "keylogger", "キーロガー", "credential stealer", "パスワードを盗"],
        "unauthorized_access": ["不正アクセス", "他人のアカウントを乗っ取", "認証を回避", "2faを回避", "許可なく侵入"],
        "fraud": ["詐欺サイト", "フィッシング", "偽ログイン画面", "カード番号を盗", "本人になりすまし"],
        "physical_harm": ["爆弾", "毒物を作", "人を傷つけるため"],
        "covert_surveillance": ["こっそり盗撮", "無断で盗聴", "相手に知らせず位置追跡"],
    }
    REVIEW_PATTERNS = {
        "medical": ["診断", "処方", "医療", "患者"],
        "finance": ["融資審査", "投資助言", "金融商品", "信用スコア", "保険審査"],
        "legal": ["法律相談", "法的判断", "弁護士"],
        "children": ["子ども", "未成年", "児童"],
        "biometric": ["顔認証", "指紋", "生体情報"],
        "sensitive_data": ["マイナンバー", "健康情報", "位置情報を常時", "クレジットカード"],
        "payments": ["決済", "課金", "送金"],
        "public_release": ["app storeに公開", "google playに公開", "本番公開"],
    }

    def check(self, text: str) -> SafetyDecision:
        lowered = text.lower()
        blocked = [category for category, patterns in self.BLOCK_PATTERNS.items() if any(p.lower() in lowered for p in patterns)]
        if blocked:
            return SafetyDecision(False, "blocked", blocked, True)
        review = [category for category, patterns in self.REVIEW_PATTERNS.items() if any(p.lower() in lowered for p in patterns)]
        if review:
            return SafetyDecision(True, "high-risk", review, True)
        return SafetyDecision(True, "normal", [], False)
