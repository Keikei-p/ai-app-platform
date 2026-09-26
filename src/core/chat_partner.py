from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from datetime import datetime, timezone
import json
import re
from .development_memory import DevelopmentMemory

@dataclass(frozen=True)
class ChatDecision:
    action: str  # ask | build | explain
    message: str
    instruction: str | None = None

class ChatPartner:
    """Conversation-first requirement collector.

    It asks only for missing decisions that materially affect the generated app.
    State lives inside each project so restarting the platform does not erase the conversation.
    """
    TARGET_WORDS = {
        "web": ("web", "ウェブ", "ブラウザ", "pwa"),
        "android": ("android", "アンドロイド", "apk", "aab"),
        "ios": ("iphone", "ipad", "ios", "アイフォン", "アップル"),
        "windows": ("windows", "pc", "パソコン", "exe"),
        "macos": ("mac", "macos", "マック"),
    }
    STYLE_WORDS = {
        "minimal": ("シンプル", "ミニマル", "すっきり"),
        "premium": ("高級", "上品", "ラグジュアリー"),
        "modern": ("おしゃれ", "スマート", "モダン", "洗練"),
        "friendly": ("かわいい", "親しみ", "やさしい"),
        "business": ("ビジネス", "堅実", "信頼感"),
    }

    def __init__(self, memory: DevelopmentMemory | None = None):
        self.memory = memory or DevelopmentMemory()

    def suggest_project_name(self, text: str) -> str:
        cleaned = re.sub(r"[\r\n\t]+", " ", text).strip()
        cleaned = re.sub(r"[。！？!?].*", "", cleaned)
        cleaned = cleaned[:22].strip(" 、,")
        return cleaned or "新しいアプリ"

    def handle(self, project_dir: Path, project_name: str, slug: str, user_text: str, *, has_generated: bool) -> ChatDecision:
        text = user_text.strip()
        state = self._load(project_dir)
        self._append(state, "user", text)

        if self._is_learning_question(text) and has_generated:
            decision = ChatDecision("explain", "生成したアプリを教材にして説明します。")
            self._append(state, "assistant", decision.message)
            self._save(project_dir, state)
            return decision

        if state.get("pending"):
            self._apply_answer(state, state["pending"], text)
            state["pending"] = None
        else:
            self._extract(state, text)

        if not state.get("goal"):
            state["goal"] = text

        if has_generated and self._looks_like_correction(text):
            lesson = self._lesson_from_correction(text)
            self.memory.record(category="human_correction", input_text=text, lesson=lesson, project_slug=slug)
            instruction = self._compose(state, correction=text)
            msg = "了解。今の指摘を学習履歴に残して、修正→再テストします。"
            self._append(state, "assistant", msg)
            self._save(project_dir, state)
            return ChatDecision("build", msg, instruction)

        question = self._next_question(state)
        if question:
            key, message = question
            state["pending"] = key
            self._append(state, "assistant", message)
            self._save(project_dir, state)
            return ChatDecision("ask", message)

        instruction = self._compose(state)
        lessons = self.memory.lessons_for(instruction)
        if lessons:
            instruction += "\n過去の学習事項: " + " / ".join(lessons)
        msg = "必要な情報がそろいました。設計→作成→テストまで進めます。"
        self._append(state, "assistant", msg)
        self._save(project_dir, state)
        return ChatDecision("build", msg, instruction)

    def history(self, project_dir: Path) -> list[dict]:
        return self._load(project_dir).get("history", [])

    def state(self, project_dir: Path) -> dict:
        return self._load(project_dir)

    def _next_question(self, state: dict) -> tuple[str, str] | None:
        if not state.get("targets"):
            return "targets", "どこで使うアプリにしますか？ Web／Android／iPhone／PC から選べます。『スマホ両方』でも大丈夫です。"
        if not state.get("design_style"):
            return "design_style", "デザインはどんな雰囲気がいいですか？ 例：シンプル／高級感／おしゃれでスマート／かわいい。"
        return None

    def _extract(self, state: dict, text: str) -> None:
        lowered = text.lower()
        targets = list(state.get("targets") or [])
        if "スマホ" in text and not any(k in lowered for k in ("android", "iphone", "ios")):
            for t in ("android", "ios"):
                if t not in targets:
                    targets.append(t)
        for key, words in self.TARGET_WORDS.items():
            if any(w.lower() in lowered for w in words) and key not in targets:
                targets.append(key)
        if targets:
            state["targets"] = targets
        for key, words in self.STYLE_WORDS.items():
            if any(w in text for w in words):
                state["design_style"] = key
                break
        if any(w in text for w in ("ログイン", "会員", "アカウント", "認証")):
            state["authentication"] = True
        if any(w in text.lower() for w in ("db", "database")) or any(w in text for w in ("保存", "データベース", "履歴")):
            state["database"] = True

    def _apply_answer(self, state: dict, key: str, text: str) -> None:
        if key == "targets":
            self._extract(state, text)
            if not state.get("targets"):
                if "両方" in text or "スマホ" in text:
                    state["targets"] = ["android", "ios"]
                else:
                    state["targets"] = ["web"]
        elif key == "design_style":
            self._extract(state, text)
            if not state.get("design_style"):
                state["design_style"] = "modern"
                state["design_note"] = text[:120]

    def _compose(self, state: dict, correction: str | None = None) -> str:
        parts = [str(state.get("goal") or "アプリを作成")]
        targets = state.get("targets") or ["web"]
        parts.append("出力先: " + ", ".join(targets))
        parts.append("デザイン: " + str(state.get("design_style") or "modern"))
        if state.get("design_note"):
            parts.append("デザイン補足: " + state["design_note"])
        if state.get("authentication"):
            parts.append("ログイン/認証を実装")
        if state.get("database"):
            parts.append("データ保存を実装")
        if correction:
            parts.append("人間からの訂正: " + correction)
        parts.append("使いやすさ、スマホ操作性、見た目の一貫性を優先する")
        return "\n".join(parts)

    @staticmethod
    def _looks_like_correction(text: str) -> bool:
        return any(w in text for w in ("直して", "修正", "もっと", "見にく", "使いにく", "押しにく", "違う", "戻して", "追加して", "消して"))

    @staticmethod
    def _lesson_from_correction(text: str) -> str:
        if any(w in text for w in ("押しにく", "小さい", "タップ")):
            return "スマホでは主要操作のタップ領域を十分大きくし、最低44px以上を維持する。"
        if any(w in text for w in ("見にく", "ごちゃ", "分かりにく")):
            return "情報量を整理し、重要操作を目立たせ、余白と視線誘導を改善する。"
        if any(w in text for w in ("おしゃれ", "高級", "スマート", "美し")):
            return "テンプレ感を避け、余白・階層・タイポグラフィ・カード配置を統一して洗練する。"
        return "人間の訂正内容を次回生成の要件として優先し、修正後に回帰テストする。"

    @staticmethod
    def _is_learning_question(text: str) -> bool:
        return any(w in text for w in ("なぜ", "説明して", "教えて", "コードは何", "どういう仕組み"))

    @staticmethod
    def _append(state: dict, role: str, content: str) -> None:
        state.setdefault("history", []).append({"role": role, "content": content, "at": datetime.now(timezone.utc).isoformat()})
        state["history"] = state["history"][-200:]

    def _path(self, project_dir: Path) -> Path:
        p = project_dir / ".ai"
        p.mkdir(exist_ok=True)
        return p / "chat_state.json"

    def _load(self, project_dir: Path) -> dict:
        path = self._path(project_dir)
        if not path.exists():
            return {"history": [], "targets": []}
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                data.setdefault("history", [])
                data.setdefault("targets", [])
                return data
        except Exception:
            pass
        return {"history": [], "targets": []}

    def _save(self, project_dir: Path, state: dict) -> None:
        self._path(project_dir).write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
