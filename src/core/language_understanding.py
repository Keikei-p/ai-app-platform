from __future__ import annotations

from dataclasses import asdict, dataclass
from difflib import SequenceMatcher
from typing import Any
import re
import unicodedata


@dataclass(frozen=True)
class UnderstandingResult:
    original_text: str
    interpreted_text: str
    mode: str
    confidence: float
    corrections: tuple[dict[str, str], ...]
    references: tuple[str, ...]
    dangerous: bool
    needs_confirmation: bool

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["corrections"] = list(self.corrections)
        data["references"] = list(self.references)
        return data


class LanguageUnderstandingEngine:
    """Deterministic first-pass language understanding for Aivy.

    High-confidence spelling and service-name variations are normalized
    automatically. Ambiguous or risky instructions remain behind a human
    confirmation boundary. This layer complements the connected LLM and gives
    the rest of Aivy consistent handling for Japanese typos, shorthand,
    voice-input noise and common product-name variants.
    """

    ALIASES: tuple[tuple[str, str], ...] = (
        ("ファイやベース", "Firebase"),
        ("ファイヤベース", "Firebase"),
        ("ふぁいやべーす", "Firebase"),
        ("fire base", "Firebase"),
        ("ファイヤーbase", "Firebase"),
        ("じっとはぶ", "GitHub"),
        ("ギットハブ", "GitHub"),
        ("github", "GitHub"),
        ("ぎっと", "Git"),
        ("cloud flare", "Cloudflare"),
        ("クラウドフレア", "Cloudflare"),
        ("わーどぷれす", "WordPress"),
        ("ワードプレス", "WordPress"),
        ("ちゃっぴー", "ChatGPT"),
        ("チャッピー", "ChatGPT"),
        ("chat gpt", "ChatGPT"),
        ("愛ヴィ", "IVY"),
        ("アイヴィ", "IVY"),
        ("あいびー", "IVY"),
        ("アイビー", "IVY"),
        ("ｉｖｙ", "IVY"),
        ("webサイト", "Webサイト"),
        ("ウェブサイト", "Webサイト"),
        ("ホームぺージ", "ホームページ"),
        ("アンドロイド", "Android"),
        ("アイフォン", "iPhone"),
        ("本番に近ずけ", "本番に近づけ"),
        ("本番にちかずけ", "本番に近づけ"),
        ("本番実装にちかずけ", "本番実装に近づけ"),
    )

    ASCII_TERMS: tuple[str, ...] = (
        "Firebase", "GitHub", "Git", "Cloudflare", "WordPress",
        "ChatGPT", "Android", "iPhone", "iOS", "Windows", "React",
        "Python", "SQLite", "Flutter", "Docker", "Playwright", "IVY",
    )

    MODE_TERMS: dict[str, tuple[str, ...]] = {
        "ivy_lab": (
            "ivy", "自己成長", "自律成長", "成長させ", "進化させ",
            "学習して", "賢く", "skill", "スキル", "ivy lab", "アイビー自身",
        ),
        "web": (
            "webサイト", "サイト作", "ホームページ", "lp", "ランディングページ",
            "wordpress", "seo", "ポートフォリオ", "コーポレートサイト",
        ),
        "automation": (
            "自動化", "自動投稿", "定期実行", "スケジュール", "workflow",
            "ワークフロー", "cron", "放置運用", "無人運用",
        ),
        "app": (
            "アプリ", "システム", "ツール", "webアプリ", "android",
            "iphone", "ios", "windows", "apk", "aab", "exe",
        ),
    }

    RISK_TERMS: tuple[str, ...] = (
        "削除", "消して", "全消去", "本番db", "production db",
        "apiキー", "秘密鍵", "課金", "支払い", "購入", "権限変更",
        "mainに直接", "強制push", "force push", "公開して", "本番公開",
    )

    REFERENCE_TERMS: tuple[str, ...] = (
        "あれ", "それ", "これ", "さっきの", "前の", "昨日の",
        "あの画面", "あのボタン", "そこ", "こっち",
    )

    def interpret(
        self,
        text: str,
        context: dict[str, Any] | None = None,
    ) -> UnderstandingResult:
        original = str(text or "").strip()
        normalized = self._normalize(original)
        interpreted, corrections = self._apply_aliases(normalized)
        interpreted, fuzzy = self._correct_ascii_terms(interpreted)
        corrections.extend(fuzzy)

        references = tuple(
            term for term in self.REFERENCE_TERMS if term in interpreted.lower()
        )
        mode = self._detect_mode(interpreted, context or {})
        dangerous = any(term in interpreted.lower() for term in self.RISK_TERMS)

        confidence = 0.94
        if fuzzy:
            confidence -= min(0.16, 0.05 * len(fuzzy))
        if references and not self._has_context(context or {}):
            confidence -= 0.18
        if len(interpreted) <= 2:
            confidence -= 0.12
        confidence = max(0.0, min(1.0, round(confidence, 3)))

        needs_confirmation = bool(
            dangerous and (confidence < 0.97 or bool(corrections) or bool(references))
        )

        return UnderstandingResult(
            original_text=original,
            interpreted_text=interpreted,
            mode=mode,
            confidence=confidence,
            corrections=tuple(corrections),
            references=references,
            dangerous=dangerous,
            needs_confirmation=needs_confirmation,
        )

    @staticmethod
    def _normalize(text: str) -> str:
        value = unicodedata.normalize("NFKC", text)
        value = value.replace("\u3000", " ")
        value = re.sub(r"[ \t]+", " ", value)
        value = re.sub(r"\n{3,}", "\n\n", value)
        return value.strip()

    def _apply_aliases(self, text: str) -> tuple[str, list[dict[str, str]]]:
        value = text
        corrections: list[dict[str, str]] = []
        for source, target in self.ALIASES:
            pattern = re.compile(re.escape(source), re.IGNORECASE)
            if not pattern.search(value):
                continue
            before = value
            value = pattern.sub(target, value)
            if value != before:
                corrections.append({"from": source, "to": target, "kind": "alias"})
        return value, corrections

    def _correct_ascii_terms(self, text: str) -> tuple[str, list[dict[str, str]]]:
        corrections: list[dict[str, str]] = []
        tokens = list(re.finditer(r"[A-Za-z][A-Za-z0-9_.-]{2,}", text))
        if not tokens:
            return text, corrections

        replacements: list[tuple[int, int, str]] = []
        for match in tokens:
            token = match.group(0)
            if any(token.lower() == known.lower() for known in self.ASCII_TERMS):
                continue
            best = None
            best_ratio = 0.0
            for known in self.ASCII_TERMS:
                ratio = SequenceMatcher(None, token.lower(), known.lower()).ratio()
                if ratio > best_ratio:
                    best = known
                    best_ratio = ratio
            if best and best_ratio >= 0.78 and abs(len(token) - len(best)) <= 3:
                replacements.append((match.start(), match.end(), best))
                corrections.append({
                    "from": token,
                    "to": best,
                    "kind": "fuzzy",
                })

        if not replacements:
            return text, corrections

        value = text
        for start, end, replacement in reversed(replacements):
            value = value[:start] + replacement + value[end:]
        return value, corrections

    def _detect_mode(self, text: str, context: dict[str, Any]) -> str:
        lowered = text.lower()
        scores = {name: 0 for name in self.MODE_TERMS}
        for mode, terms in self.MODE_TERMS.items():
            for term in terms:
                if term in lowered:
                    scores[mode] += 2 if len(term) >= 4 else 1

        if "モード" in lowered and ("ivy" in lowered or "アイビー" in lowered):
            scores["ivy_lab"] += 4
        if "サイト作成モード" in lowered:
            scores["web"] += 2
        if "アプリ生成モード" in lowered:
            scores["app"] += 2
        if "自動化モード" in lowered:
            scores["automation"] += 2

        current_mode = str(context.get("current_mode") or "").strip()
        if current_mode in scores:
            scores[current_mode] += 1

        best_mode, best_score = max(scores.items(), key=lambda row: row[1])
        if best_score <= 0:
            return "chat"
        return best_mode

    @staticmethod
    def _has_context(context: dict[str, Any]) -> bool:
        if context.get("project_slug") or context.get("current_project"):
            return True
        recent = context.get("recent_messages")
        return isinstance(recent, list) and bool(recent)
