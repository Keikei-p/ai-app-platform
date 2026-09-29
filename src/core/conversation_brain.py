from __future__ import annotations

from dataclasses import dataclass
from typing import Any
import re


@dataclass(frozen=True)
class ConversationIntent:
    kind: str
    confidence: float
    reason: str
    should_create_project: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "confidence": self.confidence,
            "reason": self.reason,
            "should_create_project": self.should_create_project,
        }


class ConversationBrain:
    """Conversation routing and continuity for Aivy.

    Mode words such as "app" or "site" describe the topic. They must not by
    themselves turn a question into a build. Project creation requires an
    explicit creation/change intention.
    """

    QUESTION_MARKERS = (
        "？", "?", "教えて", "どういう", "どうやって", "どうしたら",
        "できる？", "できる?", "できるの", "できるん", "可能？", "可能?",
        "何が", "なにが", "なぜ", "なんで", "どこまで", "いつ", "とは",
        "どう思う", "おすすめ", "相談", "確認したい",
    )
    CASUAL_MARKERS = (
        "ありがとう", "ありがと", "いいね", "なるほど", "おっけい", "ok",
        "そうだね", "そうやね", "わかった", "了解", "すごい", "よし",
        "こんにちは", "こんばんは", "おはよう", "おつかれ",
    )
    CREATE_MARKERS = (
        "作って", "作りたい", "作成して", "開発して", "開発したい",
        "実装して", "組み込んで", "生成して", "構築して",
        "サイトを作", "ホームページを作", "アプリを作", "システムを作",
    )
    CHANGE_MARKERS = (
        "直して", "修正して", "変更して", "追加して", "消して", "削除して",
        "改善して", "大きくして", "小さくして", "変えて", "完成させて",
        "仕上げて", "反映して",
    )
    IVY_MARKERS = (
        "自走", "オートパイロット", "自己成長", "自律成長", "自主トレ",
        "進化させ", "成長させ",
    )
    SOFT_REQUEST_MARKERS = (
        "してほしい", "して欲しい", "やってほしい", "やって欲しい",
        "作ってほしい", "作って欲しい", "作ってくれる", "直してほしい",
        "直して欲しい", "お願い", "頼む", "頼んだ",
    )

    def classify(
        self,
        text: str,
        *,
        has_project: bool,
        mode: str = "chat",
        history: list[dict[str, Any]] | None = None,
    ) -> ConversationIntent:
        clean = " ".join(str(text or "").split()).strip()
        lowered = clean.lower()
        history = history or []

        if not clean:
            return ConversationIntent("chat", 1.0, "empty input is conversational")

        if any(word.lower() in lowered for word in self.IVY_MARKERS):
            return ConversationIntent("ivy_lab", 0.98, "explicit Aivy growth/self-drive intent")

        is_question = (
            clean.endswith(("?", "？"))
            or any(word.lower() in lowered for word in self.QUESTION_MARKERS)
        )
        has_create = any(word.lower() in lowered for word in self.CREATE_MARKERS)
        has_change = any(word.lower() in lowered for word in self.CHANGE_MARKERS)
        soft_request = any(word.lower() in lowered for word in self.SOFT_REQUEST_MARKERS)

        if has_project and soft_request and (has_change or not is_question):
            return ConversationIntent("project_change", 0.95, "natural Japanese soft change request")

        if has_create and soft_request:
            return ConversationIntent(
                "project_request",
                0.96,
                "natural Japanese soft creation request",
                not has_project,
            )

        if is_question and not self._explicit_imperative(clean):
            return ConversationIntent(
                "project_question" if has_project else "chat",
                0.97,
                "question takes priority over topic mode",
                False,
            )

        if has_project and has_change:
            return ConversationIntent("project_change", 0.98, "explicit project change request")

        if has_create:
            return ConversationIntent(
                "project_request",
                0.98,
                "explicit creation request",
                not has_project,
            )

        if any(word.lower() in lowered for word in self.CASUAL_MARKERS):
            return ConversationIntent("chat", 0.96, "casual acknowledgement or greeting")

        # Short follow-ups should remain in the current conversation instead of
        # unexpectedly starting a new project merely because they mention apps.
        if history and len(clean) <= 80:
            return ConversationIntent(
                "project_question" if has_project else "chat",
                0.82,
                "short contextual follow-up",
                False,
            )

        if has_project:
            return ConversationIntent("project_question", 0.72, "existing-project conversation")
        if mode in {"app", "web", "automation"}:
            return ConversationIntent(
                "chat",
                0.68,
                "topic mode without explicit creation verb",
                False,
            )
        return ConversationIntent("chat", 0.74, "general conversation")

    def continuity_digest(
        self,
        history: list[dict[str, Any]],
        *,
        max_chars: int = 7000,
    ) -> str:
        """Build a compact long-conversation digest without another model call."""
        clean_rows: list[tuple[str, str]] = []
        for row in history[-120:]:
            role = "user" if row.get("role") == "user" else "assistant"
            content = " ".join(str(row.get("content") or "").split()).strip()
            if content:
                clean_rows.append((role, content))

        if not clean_rows:
            return "No prior conversation."

        recent = clean_rows[-24:]
        older_users = [
            content for role, content in clean_rows[:-24]
            if role == "user"
        ][-8:]

        pieces: list[str] = []
        if older_users:
            pieces.append("Earlier user context:")
            for content in older_users:
                pieces.append("- " + content[:360])
        pieces.append("Recent conversation:")
        for role, content in recent:
            label = "User" if role == "user" else "Aivy"
            pieces.append(f"{label}: {content[:900]}")

        text = "\n".join(pieces)
        if len(text) > max_chars:
            text = text[-max_chars:]
        return text

    def system_instruction(
        self,
        *,
        mode: str,
        continuity: str,
        project_context: dict[str, Any] | None = None,
        self_drive_context: dict[str, Any] | None = None,
    ) -> str:
        project_context = project_context or {}
        self_drive_context = self_drive_context or {}
        return (
            "あなたはAivy。自然な日本語で会話するAI開発パートナーです。"
            "ChatGPTのように、質問、相談、雑談、短い相づち、曖昧な続きの発言にも前後文脈を使って自然に応答してください。"
            "ユーザーの誤字・脱字・音声入力崩れ・省略は、意味が一意なら自然に補って理解します。"
            "意味が複数に分かれる時だけ、必要最小限の確認をしてください。"
            "毎回質問で返さず、分かる範囲はまず答えてください。"
            "過剰に長い前置き、機械的な定型文、同じ説明の繰り返しは避けてください。"
            "ユーザーの口調に多少合わせても、事実・安全・品質については曖昧にしません。"
            "質問や相談を、制作命令だと勝手に解釈しないでください。"
            "逆に『作って』『直して』『実装して』など明確な変更依頼は会話だけで済ませず、Aivyの制作フローへ渡します。"
            "実行していない変更、テスト、公開、保存を実行済みとは言わないでください。"
            "削除・本番公開・権限・課金・秘密情報・本番DBなど危険操作は明示確認なしで進めません。"
            f"\ncurrent_mode={mode}"
            "\nconversation_continuity:\n" + continuity
            + "\nproject_context:\n" + self._compact(project_context)
            + "\nself_drive_context:\n" + self._compact(self_drive_context)
        )

    def fallback_reply(
        self,
        text: str,
        *,
        has_project: bool,
        project_name: str = "",
    ) -> str:
        lowered = str(text or "").lower()
        if any(x in lowered for x in ("ありがとう", "ありがと")):
            return "どういたしまして。続きでも別の相談でも、そのまま話して大丈夫です。"
        if any(x in lowered for x in ("こんにちは", "こんばんは", "おはよう")):
            return "こんにちは。相談でも制作でも、そのまま話してください。"
        if has_project:
            name = project_name or "この制作物"
            return f"{name}のことなら、そのまま質問して大丈夫です。変更したい時は『○○を直して』のように言えば制作フローへ切り替えます。"
        return "もちろん。普通の会話や相談もできます。作りたいものがある時だけ、そのまま『○○を作りたい』と話してください。"

    @staticmethod
    def _explicit_imperative(text: str) -> bool:
        normalized = re.sub(r"[！？!?。\s]+$", "", text)
        return normalized.endswith((
            "作って", "直して", "修正して", "変更して", "追加して",
            "実装して", "生成して", "構築して", "完成させて", "仕上げて",
        ))

    @staticmethod
    def _compact(data: dict[str, Any]) -> str:
        if not data:
            return "{}"
        safe: dict[str, Any] = {}
        for key, value in data.items():
            if key in {"secrets", "api_key", "token", "password"}:
                continue
            if isinstance(value, str):
                safe[key] = value[:1200]
            elif isinstance(value, list):
                safe[key] = value[:12]
            elif isinstance(value, dict):
                safe[key] = {
                    str(k): (str(v)[:500] if not isinstance(v, (dict, list)) else v)
                    for k, v in list(value.items())[:16]
                }
            else:
                safe[key] = value
        import json
        return json.dumps(safe, ensure_ascii=False)
