from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import json
import shutil
import urllib.error
import urllib.request

from .config import DATA_DIR, ROOT_DIR
from .credential_store import CredentialStore
from .connector_providers import ConnectorProvider, default_provider_registry
from .redaction import redact_sensitive


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class ConnectorDefinition:
    connector_id: str
    name: str
    category: str
    description: str
    capabilities: tuple[str, ...]
    requirements: tuple[str, ...]
    requirement_level: str
    cost_label: str
    cost_note: str
    config_fields: tuple[dict[str, Any], ...] = ()
    credential_fields: tuple[dict[str, Any], ...] = ()
    available: bool = True
    test_mode: str = "none"

    def to_dict(self) -> dict[str, Any]:
        row = asdict(self)
        row["capabilities"] = list(self.capabilities)
        row["requirements"] = list(self.requirements)
        row["config_fields"] = [dict(x) for x in self.config_fields]
        row["credential_fields"] = [dict(x) for x in self.credential_fields]
        return row


class ConnectorRegistry:
    CATEGORY_ORDER = (
        "AI",
        "開発",
        "データベース・バックエンド",
        "クラウド・公開",
        "アプリ配布",
        "その他",
    )

    def __init__(self):
        self._definitions = {x.connector_id: x for x in self._defaults()}

    def get(self, connector_id: str) -> ConnectorDefinition:
        key = connector_id.strip().lower()
        if key not in self._definitions:
            raise KeyError(connector_id)
        return self._definitions[key]

    def list(self) -> list[ConnectorDefinition]:
        order = {name: index for index, name in enumerate(self.CATEGORY_ORDER)}
        return sorted(
            self._definitions.values(),
            key=lambda x: (order.get(x.category, 999), x.name.lower()),
        )

    @staticmethod
    def _defaults() -> list[ConnectorDefinition]:
        return [
            ConnectorDefinition(
                "openai", "OpenAI", "AI",
                "高度な会話・設計・コード生成・分析に利用します。",
                ("AI会話", "アプリ設計", "コード生成", "コード修正", "AI分析", "画像理解"),
                ("OpenAIアカウント", "APIキー"),
                "推奨", "有料の場合あり",
                "外部サービス側で利用料金が発生する可能性があります。最新料金は提供元で確認してください。",
                (
                    {"key": "model", "label": "使用モデル", "placeholder": "例: gpt-6-astra"},
                    {"key": "auto_fallback", "label": "障害時の自動フォールバックを許可", "type": "checkbox"},
                ),
                ({"key": "api_key", "label": "APIキー", "placeholder": "sk-...", "remember_default": True},),
                True, "openai",
            ),
            ConnectorDefinition(
                "gemini", "Google Gemini", "AI",
                "Google Geminiを会話・推論・コード・画像理解に利用します。",
                ("AI会話", "コード生成", "分析", "画像理解"),
                ("Googleアカウント", "Gemini APIキー"),
                "推奨", "無料枠あり / 有料の場合あり",
                "料金や無料枠は変更される可能性があります。最新料金は提供元で確認してください。",
                (
                    {"key": "model", "label": "使用モデル", "placeholder": "例: gemini-3.5-flash"},
                    {"key": "auto_fallback", "label": "障害時の自動フォールバックを許可", "type": "checkbox"},
                ),
                ({"key": "api_key", "label": "APIキー", "placeholder": "API key", "remember_default": True},),
                True, "gemini",
            ),
            ConnectorDefinition(
                "ollama", "Ollama / ローカルLLM", "AI",
                "PC上のローカルLLMを使います。外部APIキーなしで利用できます。",
                ("ローカルAI会話", "フォールバック", "オフライン寄りの利用"),
                ("Ollama", "ローカルモデル"),
                "推奨", "無料で利用可能",
                "モデル実行にPCリソースを使用します。",
                (
                    {"key": "base_url", "label": "Ollama URL", "placeholder": "http://127.0.0.1:11434"},
                    {"key": "model", "label": "モデル", "placeholder": "qwen2.5:7b"},
                ),
                (), True, "ollama",
            ),
            ConnectorDefinition(
                "github", "GitHub", "開発",
                "ソースコード管理・バックアップ・更新に利用します。",
                ("Git管理", "バックアップ", "更新", "リポジトリ連携"),
                ("GitHubアカウント", "Personal Access Token等"),
                "任意", "無料で利用可能 / 有料プランあり",
                "Ivyは購入者自身のGitHubアカウントを使用します。",
                ({"key": "repository", "label": "既定リポジトリ", "placeholder": "owner/repository"},),
                ({"key": "token", "label": "GitHub Token", "placeholder": "github_pat_...", "remember_default": True},),
                True, "github",
            ),
            ConnectorDefinition(
                "gitlab", "GitLab", "開発",
                "将来のGitLabソース管理連携用Connectorです。",
                ("Git管理", "バックアップ"),
                ("GitLabアカウント",),
                "任意", "外部サービス側で確認",
                "現在のIvyでは接続処理は未実装です。",
                (), (), False, "none",
            ),
            ConnectorDefinition(
                "local_git", "ローカルGit", "開発",
                "PC内のGitを利用します。外部アカウントは不要です。",
                ("ローカル版管理", "履歴", "差分管理"),
                ("Gitコマンド",),
                "推奨", "無料で利用可能",
                "外部課金はありません。",
                (), (), True, "local_git",
            ),
            ConnectorDefinition(
                "firebase", "Firebase", "データベース・バックエンド",
                "Firebaseプロジェクトを購入者自身の設定で利用するためのConnectorです。",
                ("認証", "Firestore", "Hosting等"),
                ("Firebase / Google Cloudプロジェクト",),
                "任意", "無料枠あり / 有料の場合あり",
                "料金は利用量とプランで変わります。最新料金は提供元で確認してください。",
                ({"key": "project_id", "label": "Project ID", "placeholder": "my-project"},),
                ({"key": "service_account", "label": "Service Account JSON", "placeholder": "{...}", "remember_default": True},),
                False, "none",
            ),
            ConnectorDefinition(
                "supabase", "Supabase", "データベース・バックエンド",
                "Supabaseをデータ保存・認証等に利用します。",
                ("データベース", "認証", "API"),
                ("Supabaseプロジェクト", "Project URL", "API Key"),
                "任意", "無料枠あり / 有料の場合あり",
                "最新料金は提供元で確認してください。",
                ({"key": "url", "label": "Project URL", "placeholder": "https://xxxxx.supabase.co"},),
                ({"key": "key", "label": "API Key", "placeholder": "key", "remember_default": True},),
                True, "supabase",
            ),
            ConnectorDefinition(
                "sqlite", "SQLite", "データベース・バックエンド",
                "Ivyのローカルデータ保存に利用します。",
                ("ローカルデータ", "履歴", "Workspace管理"),
                (),
                "必須", "無料で利用可能",
                "Ivy内蔵のローカル機能です。",
                (), (), True, "sqlite",
            ),
            ConnectorDefinition(
                "d1", "Cloudflare D1", "データベース・バックエンド",
                "Cloudflare D1データベースを利用します。",
                ("クラウドDB", "Workers連携"),
                ("Cloudflareアカウント", "Account ID", "Database ID", "API Token"),
                "任意", "無料枠あり / 有料の場合あり",
                "最新料金はCloudflareで確認してください。",
                (
                    {"key": "account_id", "label": "Account ID", "placeholder": "account id"},
                    {"key": "database_id", "label": "Database ID", "placeholder": "database id"},
                ),
                ({"key": "token", "label": "Cloudflare API Token", "placeholder": "token", "remember_default": True},),
                True, "d1",
            ),
            ConnectorDefinition(
                "cloudflare", "Cloudflare", "クラウド・公開",
                "Workers / Pages等の公開基盤に利用します。",
                ("Web公開", "Workers", "Pages"),
                ("Cloudflareアカウント", "API Token"),
                "任意", "無料枠あり / 有料の場合あり",
                "最新料金はCloudflareで確認してください。",
                ({"key": "account_id", "label": "Account ID", "placeholder": "account id"},),
                ({"key": "token", "label": "API Token", "placeholder": "token", "remember_default": True},),
                True, "cloudflare",
            ),
            ConnectorDefinition(
                "vercel", "Vercel", "クラウド・公開",
                "Webアプリのプレビュー・公開に利用できます。",
                ("Web公開", "Preview"),
                ("Vercelアカウント", "Token"),
                "任意", "無料枠あり / 有料の場合あり",
                "最新料金はVercelで確認してください。",
                (), ({"key": "token", "label": "Token", "placeholder": "token", "remember_default": True},),
                True, "vercel",
            ),
            ConnectorDefinition(
                "netlify", "Netlify", "クラウド・公開",
                "Webサイトの公開に利用できます。",
                ("Web公開",),
                ("Netlifyアカウント", "Token"),
                "任意", "無料枠あり / 有料の場合あり",
                "最新料金はNetlifyで確認してください。",
                (), ({"key": "token", "label": "Token", "placeholder": "token", "remember_default": True},),
                True, "netlify",
            ),
            ConnectorDefinition(
                "google_play", "Google Play", "アプリ配布",
                "Androidアプリ配布用の将来Connectorです。",
                ("Android配布",),
                ("Google Play Console", "サービスアカウント"),
                "任意", "外部費用あり",
                "登録料・利用条件はGoogleで最新情報を確認してください。",
                ({"key": "package_name", "label": "Package Name", "placeholder": "com.example.app"},),
                ({"key": "service_account", "label": "Service Account JSON", "placeholder": "{...}", "remember_default": True},),
                False, "none",
            ),
            ConnectorDefinition(
                "apple_developer", "Apple Developer", "アプリ配布",
                "iOS署名・配布用の将来Connectorです。",
                ("iOS署名", "App Store配布"),
                ("Apple Developer Program", "Issuer / Key ID / Private Key"),
                "任意", "外部費用あり",
                "Apple側の登録料・条件は最新情報を確認してください。",
                (
                    {"key": "issuer_id", "label": "Issuer ID", "placeholder": "issuer id"},
                    {"key": "key_id", "label": "Key ID", "placeholder": "key id"},
                ),
                ({"key": "private_key", "label": "Private Key", "placeholder": "private key", "remember_default": True},),
                False, "none",
            ),
            ConnectorDefinition(
                "windows_distribution", "Windows配布", "アプリ配布",
                "ローカルWindowsビルド・配布成果物を扱います。",
                ("Windows EXE", "ローカル配布"),
                ("Windows環境",),
                "任意", "無料で利用可能",
                "コード署名等を行う場合は外部証明書費用が発生する場合があります。",
                (), (), True, "windows",
            ),
        ]


class ConnectorManager:
    STATUS_LABELS = {
        "connected": "接続済み",
        "disconnected": "未接続",
        "error": "エラー",
        "setting_incomplete": "設定途中",
        "unavailable": "利用不可",
    }

    def __init__(
        self,
        *,
        registry: ConnectorRegistry | None = None,
        credentials: CredentialStore | None = None,
        config_path: Path | None = None,
        providers: dict[str, ConnectorProvider] | None = None,
    ):
        self.registry = registry or ConnectorRegistry()
        self.credentials = credentials or CredentialStore()
        self.providers = providers or default_provider_registry()
        self.config_path = Path(config_path or (DATA_DIR / "connectors.json"))
        self.config_path.parent.mkdir(parents=True, exist_ok=True)

    def list_public(self) -> list[dict[str, Any]]:
        state = self._read()
        rows = []
        for definition in self.registry.list():
            row = definition.to_dict()
            saved = state.get(definition.connector_id) if isinstance(state.get(definition.connector_id), dict) else {}
            status = self._status(definition, saved)
            row["status"] = status
            row["status_label"] = self.STATUS_LABELS[status]
            row["config"] = self._safe_config(definition, saved.get("config"))
            row["credentials"] = {
                field["key"]: asdict(self.credentials.status(f"{definition.connector_id}.{field['key']}"))
                for field in definition.credential_fields
            }
            row["last_test"] = saved.get("last_test") if isinstance(saved.get("last_test"), dict) else None
            rows.append(row)
        return rows

    def get_public(self, connector_id: str) -> dict[str, Any]:
        return next(x for x in self.list_public() if x["connector_id"] == connector_id)

    def connect(
        self,
        connector_id: str,
        *,
        config: dict[str, Any] | None = None,
        credentials: dict[str, Any] | None = None,
        remember: bool = True,
    ) -> dict[str, Any]:
        return self.configure(
            connector_id,
            config=config,
            credentials=credentials,
            remember=remember,
        )

    def get_status(self, connector_id: str) -> dict[str, Any]:
        return self.get_public(connector_id)

    def get_capabilities(self, connector_id: str) -> list[str]:
        definition = self.registry.get(connector_id)
        provider = self.providers.get(definition.test_mode)
        if provider is None:
            return list(definition.capabilities)
        runtime = list(provider.get_capabilities())
        return runtime or list(definition.capabilities)

    def validate_configuration(self, connector_id: str) -> dict[str, Any]:
        definition = self.registry.get(connector_id)
        saved = self._read().get(definition.connector_id)
        saved = saved if isinstance(saved, dict) else {}
        provider = self.providers.get(definition.test_mode) or self.providers.get("none")
        if provider is None:
            return {"valid": False, "issues": ["Provider adapter is unavailable."]}
        issues = provider.validate_configuration(
            dict(saved.get("config") or {}),
            lambda key: self.credentials.get(f"{definition.connector_id}.{key}"),
        )
        return {
            "valid": not issues,
            "issues": [redact_sensitive(str(x)) for x in issues],
        }

    def configure(
        self,
        connector_id: str,
        *,
        config: dict[str, Any] | None = None,
        credentials: dict[str, Any] | None = None,
        remember: bool = True,
    ) -> dict[str, Any]:
        definition = self.registry.get(connector_id)
        if not definition.available:
            raise ValueError("このConnectorは現在利用できません")
        state = self._read()
        saved = state.get(definition.connector_id) if isinstance(state.get(definition.connector_id), dict) else {}
        field_map = {str(x["key"]): x for x in definition.config_fields}
        allowed_config = set(field_map)
        clean_config = dict(saved.get("config") or {})
        for key, value in dict(config or {}).items():
            if key not in allowed_config:
                continue
            if str(field_map[key].get("type") or "") == "checkbox":
                clean_config[key] = bool(value)
            else:
                clean_config[key] = str(value or "").strip()[:2000]
        for field in definition.credential_fields:
            key = str(field["key"])
            value = str((credentials or {}).get(key) or "").strip()
            if value:
                self.credentials.set(
                    f"{definition.connector_id}.{key}",
                    value,
                    remember=remember,
                )
        saved["config"] = clean_config
        saved["updated_at"] = _now()
        saved["last_test"] = None
        state[definition.connector_id] = saved
        self._write(state)
        return self.get_public(definition.connector_id)

    def disconnect(self, connector_id: str) -> dict[str, Any]:
        definition = self.registry.get(connector_id)
        for field in definition.credential_fields:
            self.credentials.delete(f"{definition.connector_id}.{field['key']}")
        state = self._read()
        saved = state.get(definition.connector_id) if isinstance(state.get(definition.connector_id), dict) else {}
        saved["last_test"] = None
        saved["updated_at"] = _now()
        state[definition.connector_id] = saved
        self._write(state)
        return self.get_public(definition.connector_id)

    def test_connection(self, connector_id: str) -> dict[str, Any]:
        definition = self.registry.get(connector_id)
        if not definition.available:
            result = self._test_result(False, "unavailable", "このConnectorは現在利用できません。")
        else:
            try:
                result = self._run_test(definition)
            except Exception as exc:
                result = self._test_result(
                    False,
                    "error",
                    self._human_error(exc),
                )
        state = self._read()
        saved = state.get(definition.connector_id) if isinstance(state.get(definition.connector_id), dict) else {}
        saved["last_test"] = result
        saved["updated_at"] = _now()
        state[definition.connector_id] = saved
        self._write(state)
        return {**result, "connector": self.get_public(definition.connector_id)}

    def dependency_summary(self) -> list[dict[str, Any]]:
        rows = []
        for row in self.list_public():
            if row["status"] != "disconnected" or row["connector_id"] in {"sqlite", "local_git", "windows_distribution"}:
                rows.append({
                    "connector_id": row["connector_id"],
                    "name": row["name"],
                    "category": row["category"],
                    "status": row["status"],
                    "status_label": row["status_label"],
                    "capabilities": row["capabilities"],
                    "requirement_level": row["requirement_level"],
                })
        return rows

    def _run_test(self, definition: ConnectorDefinition) -> dict[str, Any]:
        saved = self._read().get(definition.connector_id)
        saved = saved if isinstance(saved, dict) else {}
        provider = self.providers.get(definition.test_mode) or self.providers.get("none")
        if provider is None:
            return self._test_result(
                False,
                "unavailable",
                "このConnectorのProvider Adapterがありません。",
            )
        result = provider.test_connection(
            dict(saved.get("config") or {}),
            lambda key: self.credentials.get(f"{definition.connector_id}.{key}"),
        )
        return self._test_result(result.ok, result.status, result.message)

    def _status(self, definition: ConnectorDefinition, saved: dict[str, Any]) -> str:
        if not definition.available:
            return "unavailable"

        missing_config = [
            str(field["key"])
            for field in definition.config_fields
            if field.get("required") and not str((saved.get("config") or {}).get(field["key"]) or "").strip()
        ]
        missing_secret = [
            str(field["key"])
            for field in definition.credential_fields
            if not self.credentials.has(f"{definition.connector_id}.{field['key']}")
        ]

        # A stale successful test must never outlive the credential/config that
        # made it successful.
        if definition.credential_fields and len(missing_secret) == len(definition.credential_fields):
            return "disconnected"
        if missing_config or missing_secret:
            return "setting_incomplete"

        last = saved.get("last_test")
        if isinstance(last, dict):
            state = str(last.get("status") or "")
            if state in self.STATUS_LABELS:
                return state

        if not definition.credential_fields and not definition.config_fields:
            if definition.test_mode in {"sqlite", "local_git", "windows"}:
                return "setting_incomplete"
        return "setting_incomplete"

    @staticmethod
    def _safe_config(definition: ConnectorDefinition, raw: Any) -> dict[str, Any]:
        values = raw if isinstance(raw, dict) else {}
        field_map = {str(x["key"]): x for x in definition.config_fields}
        result: dict[str, Any] = {}
        for key, value in values.items():
            if key not in field_map:
                continue
            if str(field_map[key].get("type") or "") == "checkbox":
                result[key] = bool(value)
            else:
                result[key] = str(value)
        return result

    @staticmethod
    def _test_result(ok: bool, status: str, message: str) -> dict[str, Any]:
        return {
            "ok": bool(ok),
            "status": status,
            "message": redact_sensitive(message),
            "tested_at": _now(),
        }

    @staticmethod
    def _human_error(exc: Exception) -> str:
        if isinstance(exc, PermissionError):
            return redact_sensitive(str(exc) or "認証エラーです。Credentialと権限を確認してください。")
        if isinstance(exc, ConnectionError):
            return redact_sensitive(str(exc) or "ネットワーク接続を確認してください。")
        if isinstance(exc, ValueError):
            return redact_sensitive(str(exc))
        return redact_sensitive(str(exc) or "接続テストに失敗しました。")

    def _read(self) -> dict[str, Any]:
        if not self.config_path.is_file():
            return {}
        try:
            raw = json.loads(self.config_path.read_text(encoding="utf-8"))
            return raw if isinstance(raw, dict) else {}
        except Exception:
            return {}

    def _write(self, state: dict[str, Any]) -> None:
        tmp = self.config_path.with_suffix(self.config_path.suffix + ".tmp")
        tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(self.config_path)
