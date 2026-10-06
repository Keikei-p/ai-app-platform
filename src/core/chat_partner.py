from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from datetime import datetime, timezone
import json
import re
from .development_memory import DevelopmentMemory
from .language_understanding import LanguageUnderstandingEngine, UnderstandingResult
from .redaction import redact_sensitive


@dataclass(frozen=True)
class ChatDecision:
    action: str  # chat | ask | review | build | explain
    message: str
    instruction: str | None = None


class ChatPartner:
    """Conversation-first requirement collector with an explicit build gate.

    New projects are never generated from a casual or incomplete message.
    The assistant first builds a brief, shows it to the user, and only starts
    generation after explicit confirmation.
    """

    TARGET_WORDS = {
        "web": ("web", "ウェブ", "ブラウザ", "pwa", "サイト", "ホームページ", "wordpress", "lp"),
        "android": ("android", "アンドロイド", "apk", "aab"),
        "ios": ("iphone", "ipad", "ios", "アイフォン", "アップル"),
        "windows": ("windows", "pc", "パソコン", "exe"),
        "macos": ("mac", "macos", "マック"),
    }
    STYLE_WORDS = {
        "minimal": ("シンプル", "ミニマル", "すっきり", "appleっぽい", "アップルっぽい"),
        "premium": ("高級", "ラグジュアリー", "プレミアム"),
        "modern": ("おしゃれ", "スマート", "モダン", "洗練", "最先端"),
        "friendly": ("かわいい", "親しみ", "やさしい"),
        "business": ("ビジネス", "堅実", "信頼感", "企業向け", "b2b"),
        "soft": ("女性向け", "美容", "サロン", "柔らかい", "やわらかい", "上品"),
        "finance": ("金融", "投資", "資産", "会計", "フィンテック"),
        "youthful": ("若者向け", "学生向け", "ポップ", "カジュアル"),
        "future": ("未来的", "近未来", "aiっぽい", "フューチャー"),
        "dark": ("ダークモード", "ダーク", "黒基調"),
    }
    PROJECT_INTENT_WORDS = (
        "アプリ", "システム", "ツール", "webサイト", "ウェブサイト",
        "サイトを作", "ホームページ", "ポートフォリオ", "lp", "作って", "作りたい", "開発したい", "開発して",
        "自動化したい", "自動化して",
    )
    FEATURE_LABELS = {
        "authentication": "ログイン・アカウント",
        "database": "データ保存",
        "search": "検索",
        "notifications": "通知",
        "payments": "決済",
        "admin": "管理者機能",
        "analytics": "分析・集計",
        "multi_language": "多言語",
        "offline": "オフライン",
    }

    def __init__(self, memory: DevelopmentMemory | None = None):
        self.memory = memory or DevelopmentMemory()
        self.language = LanguageUnderstandingEngine()

    def understand(self, text: str, context: dict | None = None) -> UnderstandingResult:
        return self.language.interpret(text, context or {})

    def is_project_request(self, text: str) -> bool:
        understood = self.understand(text)
        lowered = understood.interpreted_text.lower()
        return understood.mode in {"app", "web", "automation"} or any(
            word.lower() in lowered for word in self.PROJECT_INTENT_WORDS
        )

    def opening_response(self, text: str) -> str | None:
        """Handle lightweight conversation before a real project exists."""
        understood = self.understand(text)
        normalized = re.sub(r"\s+", "", understood.interpreted_text).lower()
        greetings = ("こんにちは", "こんばんは", "おはよう", "やあ", "hello", "hi", "はじめまして")
        if any(word in normalized for word in greetings):
            return "こんにちは。まず相談だけでも大丈夫です。作りたいものが固まってから、内容を確認して制作に進みます。"
        if any(word in normalized for word in ("何ができる", "なにができる", "使い方", "どう使う")):
            return "普通の会話に加えて、アプリ生成、Webサイト制作、自動化、要件整理、設計、作成、テスト、修正まで進められます。誤字や言い間違いも文脈からできるだけ補います。"
        if any(word in normalized for word in ("相談したい", "相談から", "まだ曖昧", "決まってない", "決まっていない")):
            return "もちろん。作りたいものが決まっていなくても大丈夫です。誰のどんな困りごとを楽にしたいか、そこから一緒に整理できます。"
        if not self.is_project_request(text):
            return "話は聞けます。アプリ制作に進めたい時は『○○アプリを作りたい』のように言ってください。内容が固まるまでは勝手に生成しません。"
        return None

    def suggest_project_name(self, text: str) -> str:
        cleaned = re.sub(r"[\r\n\t]+", " ", self.understand(text).interpreted_text).strip()
        cleaned = re.sub(r"[。！？!?].*", "", cleaned)
        cleaned = cleaned[:22].strip(" 、,")
        return cleaned or "新しいアプリ"

    def handle(
        self,
        project_dir: Path,
        project_name: str,
        slug: str,
        user_text: str,
        *,
        has_generated: bool,
        preferred_mode: str | None = None,
    ) -> ChatDecision:
        original_text = user_text.strip()
        state = self._load(project_dir)
        explicit_mode = str(preferred_mode or "").strip().lower()
        if explicit_mode not in {"chat", "app", "web", "automation"}:
            explicit_mode = ""
        understood = self.understand(
            original_text,
            {
                "project_slug": slug,
                "current_project": project_name,
                "current_mode": explicit_mode or state.get("current_mode"),
                "recent_messages": state.get("history", [])[-8:],
            },
        )
        text = understood.interpreted_text
        resolved_mode = explicit_mode if explicit_mode and explicit_mode != "chat" else understood.mode
        state["current_mode"] = resolved_mode
        if resolved_mode == "web":
            targets = list(state.get("targets") or [])
            if "web" not in targets:
                targets.append("web")
            state["targets"] = targets
        state["last_understanding"] = understood.to_dict()
        self._append(state, "user", original_text)

        if understood.needs_confirmation:
            msg = "意味は推測できますが、削除・本番・権限・課金などに関わる可能性があるため、この操作だけは対象を明確にして確認してから進めます。"
            self._append(state, "assistant", msg)
            self._save(project_dir, state)
            return ChatDecision("ask", msg)

        if self._is_learning_question(text) and has_generated:
            decision = ChatDecision("explain", "生成したアプリを教材にして説明します。")
            self._append(state, "assistant", decision.message)
            self._save(project_dir, state)
            return decision

        if has_generated and self._looks_like_correction(text):
            lesson = self._lesson_from_correction(text)
            self.memory.record(category="human_correction", input_text=text, lesson=lesson, project_slug=slug)
            instruction = self._compose(state, correction=text)
            msg = "了解。今の指摘を改善要件として反映し、修正後にもう一度テストします。"
            self._append(state, "assistant", msg)
            self._save(project_dir, state)
            return ChatDecision("build", msg, instruction)

        # Once a brief is ready, building still requires a second explicit action.
        if state.get("awaiting_confirmation"):
            if self._is_build_confirmation(text):
                state["awaiting_confirmation"] = False
                instruction = self._compose(state)
                lessons = self.memory.lessons_for(instruction)
                if lessons:
                    instruction += "\n過去の学習事項: " + " / ".join(lessons)
                msg = "確認ありがとう。この設計内容で作成し、デザイン確認と自動テストまで進めます。"
                self._append(state, "assistant", msg)
                self._save(project_dir, state)
                return ChatDecision("build", msg, instruction)

            # Any other message is treated as a revision, not accidental approval.
            state["awaiting_confirmation"] = False
            state.setdefault("revision_notes", []).append(text[:400])
            self._extract(state, text)

        if state.get("pending"):
            pending = state["pending"]
            state["pending"] = None
            self._apply_answer(state, pending, text)
        else:
            self._extract(state, text)

        if not state.get("goal"):
            state["goal"] = text

        question = self._next_question(state)
        if question:
            key, message = question
            state["pending"] = key
            self._append(state, "assistant", message)
            self._save(project_dir, state)
            return ChatDecision("ask", message)

        # Requirements are complete enough to review, but never auto-build.
        state["awaiting_confirmation"] = True
        message = self._review_message(state)
        self._append(state, "assistant", message)
        self._save(project_dir, state)
        return ChatDecision("review", message, self._compose(state))

    def is_build_confirmation(self, text: str) -> bool:
        return self._is_build_confirmation(self.understand(text).interpreted_text)

    def is_conversation_only(self, text: str, *, has_generated: bool) -> bool:
        understood = self.understand(text)
        clean = understood.interpreted_text.strip()
        if not clean:
            return True
        if self._is_build_confirmation(clean) or self._looks_like_correction(clean):
            return False
        modification_words = (
            "追加して", "追加したい", "作って", "作りたい", "実装して", "変更して",
            "直して", "修正して", "消して", "削除して", "公開して", "デプロイして",
            "組み込んで", "入れて", "生成して", "作成して",
        )
        if any(word in clean for word in modification_words):
            return False
        conversation_words = (
            "ありがとう", "ありがと", "こんにちは", "こんばんは", "おはよう",
            "どういう", "どうなって", "どこまで", "何が", "なにが", "なぜ",
            "教えて", "説明して", "確認", "状態", "進捗", "できるの", "できる？",
            "どう思う", "相談", "とは", "？", "?",
        )
        if any(word in clean for word in conversation_words):
            return True
        return bool(has_generated and understood.mode == "chat")

    def history(self, project_dir: Path) -> list[dict]:
        return self._load(project_dir).get("history", [])

    def append_external_message(self, project_dir: Path, role: str, content: str) -> None:
        if role not in {"user", "assistant"}:
            raise ValueError("invalid chat role")
        state = self._load(project_dir)
        self._append(state, role, content)
        self._save(project_dir, state)

    def state(self, project_dir: Path) -> dict:
        return self._load(project_dir)

    def _next_question(self, state: dict) -> tuple[str, str] | None:
        if not state.get("usage_context"):
            return (
                "usage_context",
                "まず、誰が使って、どんな流れで使うアプリにしたいですか？\n"
                "例：営業担当が案件ごとにタスクを登録し、期限と完了状況を管理する。",
            )
        if not state.get("targets"):
            return "targets", "どこで使いますか？ Web／Android／iPhone／Windows など、必要なものを教えてください。"
        if not state.get("features_confirmed"):
            return (
                "features",
                "必要な機能を教えてください。\n"
                "例：ログイン、データ保存、検索、通知、管理者画面、分析、決済。不要なものは『特になし』でも大丈夫です。",
            )
        if not state.get("design_style"):
            return (
                "design_style",
                "見た目はどんな方向にしますか？\n"
                "例：最先端で洗練／高級感／シンプル／親しみやすい。参考イメージも言葉で伝えられます。",
            )
        return None

    def _extract(self, state: dict, text: str) -> None:
        lowered = text.lower()
        targets = list(state.get("targets") or [])
        if "スマホ" in text and not any(k in lowered for k in ("android", "iphone", "ios")):
            for target in ("android", "ios"):
                if target not in targets:
                    targets.append(target)
        for key, words in self.TARGET_WORDS.items():
            if any(word.lower() in lowered for word in words) and key not in targets:
                targets.append(key)
        if targets:
            state["targets"] = targets

        visual_markers = (
            "デザイン", "見た目", "雰囲気", "テーマ", "色", "基調",
            "かわいい", "おしゃれ", "シンプル", "洗練", "高級",
            "柔らか", "やわらか", "上品", "ダーク", "未来的", "モダン",
            "ミニマル", "親しみ", "スマート",
        )
        if any(marker in text.lower() for marker in visual_markers):
            detected = self._detect_design_style(text)
            if detected:
                state["design_style"] = detected
                state["design_note"] = text[:240]

        features = list(state.get("features") or [])
        feature_words = {
            "authentication": ("ログイン", "会員", "アカウント", "認証"),
            "database": ("保存", "データベース", "db", "履歴"),
            "search": ("検索",),
            "notifications": ("通知", "プッシュ"),
            "payments": ("決済", "課金", "支払い"),
            "admin": ("管理者", "管理画面"),
            "analytics": ("分析", "集計", "レポート"),
            "multi_language": ("多言語", "英語対応"),
            "offline": ("オフライン",),
        }
        for key, words in feature_words.items():
            if any(word.lower() in lowered for word in words) and key not in features:
                features.append(key)
        if features:
            state["features"] = features
            # Mentioning concrete feature requirements counts as an explicit feature decision.
            state["features_confirmed"] = True

        # A detailed first request can satisfy the usage-context question.
        detail_markers = ("が使", "向け", "担当", "ユーザー", "利用者", "流れ", "登録", "確認", "管理", "予約", "選ん", "入力")
        if not state.get("usage_context") and len(text) >= 45 and any(word in text for word in detail_markers):
            state["usage_context"] = text[:500]

    def _detect_design_style(self, text: str) -> str | None:
        lowered = text.lower()
        for key, words in self.STYLE_WORDS.items():
            if any(word.lower() in lowered for word in words):
                return key
        return None

    def _apply_answer(self, state: dict, key: str, text: str) -> None:
        if key == "usage_context":
            if len(text.strip()) >= 6:
                state["usage_context"] = text[:500]
            return

        if key == "targets":
            self._extract(state, text)
            return

        if key == "features":
            self._extract(state, text)
            state["features_confirmed"] = True
            state["feature_note"] = text[:300]
            return

        if key == "design_style":
            detected = self._detect_design_style(text)
            if detected:
                state["design_style"] = detected
                state["design_note"] = text[:300]
            elif text.strip():
                state["design_style"] = "custom"
                state["design_note"] = text[:300]

    def _review_message(self, state: dict) -> str:
        targets = " / ".join(state.get("targets") or [])
        features = state.get("features") or []
        feature_text = "、".join(self.FEATURE_LABELS.get(x, x) for x in features) if features else "追加機能なし"
        style = state.get("design_note") or state.get("design_style") or "未指定"
        notes = state.get("revision_notes") or []
        mode_labels = {
            "app": "APP",
            "web": "WEB",
            "automation": "AUTOMATION",
            "chat": "CHAT",
        }
        lines = [
            "いきなり作らず、まず設計内容を確認します。",
            "",
            f"モード：{mode_labels.get(str(state.get('current_mode') or ''), 'AUTO')}",
            f"目的：{state.get('goal', '')}",
            f"利用者・使い方：{state.get('usage_context', '')}",
            f"対応：{targets}",
            f"必要機能：{feature_text}",
            f"デザイン：{style}",
        ]
        if notes:
            lines.append("追加修正：" + " / ".join(notes[-3:]))
        lines += [
            "",
            "この内容で良ければ「この内容で作る」。",
            "違うところがあれば、そのまま修正内容を送ってください。まだ生成は始めません。",
        ]
        return "\n".join(lines)

    def _compose(self, state: dict, correction: str | None = None) -> str:
        mode = str(state.get("current_mode") or "app")
        mode_instruction = {
            "web": (
                "WEB MODE: Webサイトとして制作する。SEO、セマンティックHTML、"
                "アクセシビリティ、Core Web Vitalsを意識した表示性能、"
                "レスポンシブ、主要CTA、OGP/メタ情報、エラーのない主要導線を検証する。"
            ),
            "automation": (
                "AUTOMATION MODE: 自動化として制作する。再実行安全性、失敗時の再試行、"
                "重複実行防止、監査ログ、停止手段、認証情報の分離、"
                "スケジュール実行の失敗を検出できるようにする。"
            ),
            "app": (
                "APP MODE: アプリとして制作する。主要ユーザーフロー、データ整合性、"
                "認証・権限、空状態・エラー状態、モバイル操作性、"
                "対象プラットフォームのビルド可否を検証する。"
            ),
        }.get(mode, "AUTO MODE: 目的に最も合う成果物として設計する。")
        parts = [
            str(state.get("goal") or "アプリを作成"),
            mode_instruction,
            "利用者・主要フロー: " + str(state.get("usage_context") or ""),
            "出力先: " + ", ".join(state.get("targets") or []),
            "デザイン: " + str(state.get("design_style") or "custom"),
        ]
        if state.get("design_note"):
            parts.append("デザイン補足: " + state["design_note"])
        features = state.get("features") or []
        if features:
            parts.append("必須機能: " + ", ".join(features))
        if state.get("feature_note"):
            parts.append("機能補足: " + state["feature_note"])
        notes = state.get("revision_notes") or []
        if notes:
            parts.append("設計修正: " + " / ".join(notes[-5:]))
        if correction:
            parts.append("人間からの訂正: " + correction)
        parts.extend([
            "テンプレート感の強い画面を避け、目的に合う情報設計にする",
            "主要操作、空状態、エラー状態、モバイル表示、アクセシビリティを設計する",
            "完成扱いの前にデザイン審査と回帰テストを通す",
        ])
        return "\n".join(parts)

    @staticmethod
    def _is_build_confirmation(text: str) -> bool:
        normalized = re.sub(r"[\s　。！!]", "", text)
        confirmations = (
            "この内容で作る", "この内容で作って", "この内容で進めて",
            "この設計で作る", "この設計で作って", "これで作って",
            "これで作る", "作成開始", "制作開始",
        )
        return normalized in confirmations

    @staticmethod
    def _looks_like_correction(text: str) -> bool:
        return any(word in text for word in (
            "直して", "修正", "もっと", "見にく", "使いにく", "押しにく",
            "違う", "戻して", "追加して", "消して",
        ))

    @staticmethod
    def _lesson_from_correction(text: str) -> str:
        if any(word in text for word in ("押しにく", "小さい", "タップ")):
            return "スマホでは主要操作のタップ領域を十分大きくし、最低44px以上を維持する。"
        if any(word in text for word in ("見にく", "ごちゃ", "分かりにく")):
            return "情報量を整理し、重要操作を目立たせ、余白と視線誘導を改善する。"
        if any(word in text for word in ("おしゃれ", "高級", "スマート", "美し", "最先端")):
            return "テンプレ感を避け、余白・階層・タイポグラフィ・カード配置を統一して洗練する。"
        return "人間の訂正内容を次回生成の要件として優先し、修正後に回帰テストする。"

    @staticmethod
    def _is_learning_question(text: str) -> bool:
        return any(word in text for word in ("なぜ", "説明して", "教えて", "コードは何", "どういう仕組み"))

    @staticmethod
    def _append(state: dict, role: str, content: str) -> None:
        state.setdefault("history", []).append({
            "role": role,
            "content": redact_sensitive(content),
            "at": datetime.now(timezone.utc).isoformat(),
        })
        state["history"] = state["history"][-200:]

    def _path(self, project_dir: Path) -> Path:
        path = project_dir / ".ai"
        path.mkdir(exist_ok=True)
        return path / "chat_state.json"

    def _load(self, project_dir: Path) -> dict:
        path = self._path(project_dir)
        if not path.exists():
            return {"history": [], "targets": [], "features": []}
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                data.setdefault("history", [])
                data.setdefault("targets", [])
                data.setdefault("features", [])
                return data
        except Exception:
            pass
        return {"history": [], "targets": [], "features": []}

    def _save(self, project_dir: Path, state: dict) -> None:
        self._path(project_dir).write_text(
            json.dumps(state, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
