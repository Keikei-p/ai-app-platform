from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Protocol
import json
import os
import shutil
import urllib.error
import urllib.request

from .config import DB_PATH


SecretGetter = Callable[[str], str]


@dataclass(frozen=True)
class ProviderTestResult:
    ok: bool
    status: str
    message: str


class ConnectorProvider(Protocol):
    provider_id: str

    def validate_configuration(
        self,
        config: dict[str, Any],
        get_secret: SecretGetter,
    ) -> list[str]: ...

    def test_connection(
        self,
        config: dict[str, Any],
        get_secret: SecretGetter,
    ) -> ProviderTestResult: ...

    def get_capabilities(self) -> tuple[str, ...]: ...


class BaseProvider:
    provider_id = "none"
    capabilities: tuple[str, ...] = ()

    def validate_configuration(
        self,
        config: dict[str, Any],
        get_secret: SecretGetter,
    ) -> list[str]:
        return []

    def get_capabilities(self) -> tuple[str, ...]:
        return self.capabilities

    @staticmethod
    def _get_json(url: str, headers: dict[str, str]) -> dict[str, Any]:
        request = urllib.request.Request(url, headers=headers, method="GET")
        try:
            with urllib.request.urlopen(request, timeout=12) as response:
                raw = response.read(1024 * 1024)
        except urllib.error.HTTPError as exc:
            if exc.code in {401, 403}:
                raise PermissionError(
                    "認証できませんでした。Credentialと権限を確認してください。"
                ) from exc
            if exc.code == 429:
                raise RuntimeError(
                    "利用制限またはレート制限の可能性があります。サービス側の状態を確認してください。"
                ) from exc
            raise RuntimeError(f"接続先からHTTP {exc.code}が返されました。") from exc
        except urllib.error.URLError as exc:
            raise ConnectionError(
                "ネットワーク接続またはサービスURLを確認してください。"
            ) from exc
        data = json.loads(raw.decode("utf-8") or "{}")
        return data if isinstance(data, dict) else {}


class UnavailableProvider(BaseProvider):
    provider_id = "none"

    def test_connection(self, config, get_secret):
        return ProviderTestResult(
            False,
            "unavailable",
            "このConnectorの接続テストはまだ利用できません。",
        )


class SQLiteProvider(BaseProvider):
    provider_id = "sqlite"
    capabilities = ("local_database",)

    def test_connection(self, config, get_secret):
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        return ProviderTestResult(True, "connected", "SQLiteローカルデータ領域を利用できます。")


class LocalGitProvider(BaseProvider):
    provider_id = "local_git"
    capabilities = ("source_history", "local_version_control")

    def test_connection(self, config, get_secret):
        if shutil.which("git"):
            return ProviderTestResult(True, "connected", "ローカルGitを利用できます。")
        return ProviderTestResult(
            False,
            "error",
            "Gitが見つかりません。Gitをインストールして再確認してください。",
        )


class WindowsDistributionProvider(BaseProvider):
    provider_id = "windows"
    capabilities = ("windows_distribution",)

    def test_connection(self, config, get_secret):
        if os.name == "nt":
            return ProviderTestResult(True, "connected", "Windows配布環境を利用できます。")
        return ProviderTestResult(False, "unavailable", "この環境はWindowsではありません。")


class OllamaProvider(BaseProvider):
    provider_id = "ollama"
    capabilities = ("local_llm", "offline_fallback")

    def test_connection(self, config, get_secret):
        base_url = str(config.get("base_url") or "http://127.0.0.1:11434").rstrip("/")
        data = self._get_json(base_url + "/api/tags", {})
        models = [
            str(x.get("name") or "")
            for x in data.get("models") or []
            if isinstance(x, dict)
        ]
        model = str(config.get("model") or "")
        suffix = (
            f" モデル {model} を確認しました。"
            if model and any(x.startswith(model) for x in models)
            else ""
        )
        return ProviderTestResult(True, "connected", "Ollamaへ接続できました。" + suffix)


class OpenAIProvider(BaseProvider):
    provider_id = "openai"
    capabilities = ("chat", "coding", "reasoning", "vision")

    def validate_configuration(self, config, get_secret):
        return [] if get_secret("api_key") else ["OpenAI APIキーが未設定です。"]

    def test_connection(self, config, get_secret):
        key = get_secret("api_key")
        if not key:
            return ProviderTestResult(False, "setting_incomplete", "OpenAI APIキーを設定してください。")
        self._get_json(
            "https://api.openai.com/v1/models",
            {"Authorization": f"Bearer {key}"},
        )
        return ProviderTestResult(True, "connected", "OpenAIへ接続できました。")


class GeminiProvider(BaseProvider):
    provider_id = "gemini"
    capabilities = ("chat", "coding", "reasoning", "vision")

    def validate_configuration(self, config, get_secret):
        return [] if get_secret("api_key") else ["Gemini APIキーが未設定です。"]

    def test_connection(self, config, get_secret):
        key = get_secret("api_key")
        if not key:
            return ProviderTestResult(False, "setting_incomplete", "Gemini APIキーを設定してください。")
        self._get_json(
            "https://generativelanguage.googleapis.com/v1beta/models",
            {"x-goog-api-key": key},
        )
        return ProviderTestResult(True, "connected", "Google Geminiへ接続できました。")


class GitHubProvider(BaseProvider):
    provider_id = "github"
    capabilities = ("source_control", "backup", "updates")

    def validate_configuration(self, config, get_secret):
        return [] if get_secret("token") else ["GitHub Tokenが未設定です。"]

    def test_connection(self, config, get_secret):
        token = get_secret("token")
        if not token:
            return ProviderTestResult(False, "setting_incomplete", "GitHub Tokenを設定してください。")
        data = self._get_json(
            "https://api.github.com/user",
            {
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
                "User-Agent": "Aivy-Connector",
            },
        )
        login = str(data.get("login") or "").strip()
        message = "GitHubへ接続できました。"
        if login:
            message += f" アカウント: {login}"
        return ProviderTestResult(True, "connected", message)


class CloudflareProvider(BaseProvider):
    provider_id = "cloudflare"
    capabilities = ("workers", "pages", "web_deployment")

    def validate_configuration(self, config, get_secret):
        return [] if get_secret("token") else ["Cloudflare API Tokenが未設定です。"]

    def test_connection(self, config, get_secret):
        token = get_secret("token")
        if not token:
            return ProviderTestResult(False, "setting_incomplete", "Cloudflare API Tokenを設定してください。")
        data = self._get_json(
            "https://api.cloudflare.com/client/v4/user/tokens/verify",
            {"Authorization": f"Bearer {token}"},
        )
        if data.get("success") is not True:
            raise RuntimeError("Cloudflare Tokenを確認できませんでした。")
        return ProviderTestResult(True, "connected", "Cloudflare Tokenを確認できました。")


class D1Provider(BaseProvider):
    provider_id = "d1"
    capabilities = ("cloud_database",)

    def validate_configuration(self, config, get_secret):
        missing = []
        if not str(config.get("account_id") or "").strip():
            missing.append("Account IDが未設定です。")
        if not str(config.get("database_id") or "").strip():
            missing.append("Database IDが未設定です。")
        if not get_secret("token"):
            missing.append("Cloudflare API Tokenが未設定です。")
        return missing

    def test_connection(self, config, get_secret):
        missing = self.validate_configuration(config, get_secret)
        if missing:
            return ProviderTestResult(False, "setting_incomplete", " ".join(missing))
        data = self._get_json(
            "https://api.cloudflare.com/client/v4/accounts/"
            + str(config["account_id"])
            + "/d1/database/"
            + str(config["database_id"]),
            {"Authorization": f"Bearer {get_secret('token')}"},
        )
        if data.get("success") is not True:
            raise RuntimeError("Cloudflare D1を確認できませんでした。")
        return ProviderTestResult(True, "connected", "Cloudflare D1へ接続できました。")


class VercelProvider(BaseProvider):
    provider_id = "vercel"
    capabilities = ("web_deployment", "preview")

    def test_connection(self, config, get_secret):
        token = get_secret("token")
        if not token:
            return ProviderTestResult(False, "setting_incomplete", "Vercel Tokenを設定してください。")
        self._get_json(
            "https://api.vercel.com/v2/user",
            {"Authorization": f"Bearer {token}"},
        )
        return ProviderTestResult(True, "connected", "Vercelへ接続できました。")


class NetlifyProvider(BaseProvider):
    provider_id = "netlify"
    capabilities = ("web_deployment",)

    def test_connection(self, config, get_secret):
        token = get_secret("token")
        if not token:
            return ProviderTestResult(False, "setting_incomplete", "Netlify Tokenを設定してください。")
        self._get_json(
            "https://api.netlify.com/api/v1/user",
            {"Authorization": f"Bearer {token}"},
        )
        return ProviderTestResult(True, "connected", "Netlifyへ接続できました。")


class SupabaseProvider(BaseProvider):
    provider_id = "supabase"
    capabilities = ("database", "auth", "api")

    def validate_configuration(self, config, get_secret):
        missing = []
        url = str(config.get("url") or "").strip()
        if not url.startswith("https://"):
            missing.append("Supabase Project URLを設定してください。")
        if not get_secret("key"):
            missing.append("Supabase API Keyを設定してください。")
        return missing

    def test_connection(self, config, get_secret):
        missing = self.validate_configuration(config, get_secret)
        if missing:
            return ProviderTestResult(False, "setting_incomplete", " ".join(missing))
        url = str(config["url"]).rstrip("/")
        key = get_secret("key")
        self._get_json(
            url + "/rest/v1/",
            {"apikey": key, "Authorization": f"Bearer {key}"},
        )
        return ProviderTestResult(True, "connected", "Supabase APIへ接続できました。")


def default_provider_registry() -> dict[str, ConnectorProvider]:
    providers: list[ConnectorProvider] = [
        UnavailableProvider(),
        SQLiteProvider(),
        LocalGitProvider(),
        WindowsDistributionProvider(),
        OllamaProvider(),
        OpenAIProvider(),
        GeminiProvider(),
        GitHubProvider(),
        CloudflareProvider(),
        D1Provider(),
        VercelProvider(),
        NetlifyProvider(),
        SupabaseProvider(),
    ]
    return {provider.provider_id: provider for provider in providers}
