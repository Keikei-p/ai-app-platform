from __future__ import annotations

from dataclasses import dataclass
import base64
import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path
import urllib.error
import urllib.request

from .config import SETTINGS_PATH
from .credential_store import CredentialStore


@dataclass(frozen=True)
class ChatProviderStatus:
    provider: str
    model: str
    connected: bool
    detail: str


class _DataBlob(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_byte))]


def _dpapi_protect(value: str) -> str:
    if os.name != "nt" or not value:
        return ""
    raw = value.encode("utf-8")
    buf = ctypes.create_string_buffer(raw)
    in_blob = _DataBlob(len(raw), ctypes.cast(buf, ctypes.POINTER(ctypes.c_byte)))
    out_blob = _DataBlob()
    crypt32 = ctypes.windll.crypt32
    kernel32 = ctypes.windll.kernel32
    ok = crypt32.CryptProtectData(
        ctypes.byref(in_blob), "AI App Platform", None, None, None, 0,
        ctypes.byref(out_blob),
    )
    if not ok:
        raise OSError("Windows DPAPI encryption failed")
    try:
        data = ctypes.string_at(out_blob.pbData, out_blob.cbData)
        return "dpapi:" + base64.b64encode(data).decode("ascii")
    finally:
        kernel32.LocalFree(out_blob.pbData)


def _dpapi_unprotect(value: str) -> str:
    if os.name != "nt" or not value.startswith("dpapi:"):
        return ""
    raw = base64.b64decode(value[6:].encode("ascii"))
    buf = ctypes.create_string_buffer(raw)
    in_blob = _DataBlob(len(raw), ctypes.cast(buf, ctypes.POINTER(ctypes.c_byte)))
    out_blob = _DataBlob()
    crypt32 = ctypes.windll.crypt32
    kernel32 = ctypes.windll.kernel32
    ok = crypt32.CryptUnprotectData(
        ctypes.byref(in_blob), None, None, None, None, 0,
        ctypes.byref(out_blob),
    )
    if not ok:
        raise OSError("Windows DPAPI decryption failed")
    try:
        return ctypes.string_at(out_blob.pbData, out_blob.cbData).decode("utf-8")
    finally:
        kernel32.LocalFree(out_blob.pbData)


class AIChatEngine:
    """Small provider-agnostic chat client.

    The API key is never written as plaintext. On Windows it is stored with
    DPAPI (bound to the current Windows user). Environment variables still
    override stored credentials for development and CI.
    """

    DEFAULT_MODELS = {
        "openai": "gpt-6-astra",
        "gemini": "gemini-3.5-flash",
        "ollama": "qwen2.5:7b",
    }

    def __init__(
        self,
        settings_path: Path | None = None,
        credential_store: CredentialStore | None = None,
    ):
        self.settings_path = settings_path or SETTINGS_PATH
        self.credentials = credential_store or CredentialStore()
        self._session_key = ""
        self._session_keys: dict[str, str] = {}

    def _read(self) -> dict:
        if not self.settings_path.exists():
            return {}
        try:
            data = json.loads(self.settings_path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    def _write(self, data: dict) -> None:
        self.settings_path.parent.mkdir(parents=True, exist_ok=True)
        self.settings_path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def settings(self) -> dict:
        data = self._read()
        provider = str(data.get("ai_provider") or "none")
        profiles = data.get("ai_profiles") if isinstance(data.get("ai_profiles"), dict) else {}
        profile = profiles.get(provider) if isinstance(profiles.get(provider), dict) else {}
        model = str(
            data.get("ai_model")
            or profile.get("model")
            or self.DEFAULT_MODELS.get(provider, "")
        )
        routes = data.get("ai_routes") if isinstance(data.get("ai_routes"), dict) else {}
        return {"provider": provider, "model": model, "routes": routes}

    def provider_settings(self, provider: str) -> dict:
        provider = provider.strip().lower()
        data = self._read()
        profiles = data.get("ai_profiles") if isinstance(data.get("ai_profiles"), dict) else {}
        profile = profiles.get(provider) if isinstance(profiles.get(provider), dict) else {}
        model = str(profile.get("model") or self.DEFAULT_MODELS.get(provider, ""))
        return {"provider": provider, "model": model}

    def configure_route(self, capability: str, provider: str, model: str = "") -> None:
        capability = capability.strip().lower()
        provider = provider.strip().lower()
        allowed_capabilities = {"fast", "reasoning", "coding", "vision", "research", "security"}
        if capability not in allowed_capabilities:
            raise ValueError("unsupported model-route capability")
        if provider not in {"none", "openai", "gemini", "ollama"}:
            raise ValueError("unsupported provider")
        if capability == "vision" and provider == "ollama":
            raise ValueError("ollama vision routing is not supported by this connector yet")
        data = self._read()
        routes = data.get("ai_routes") if isinstance(data.get("ai_routes"), dict) else {}
        if provider == "none":
            routes.pop(capability, None)
        else:
            profile = self.provider_settings(provider)
            routes[capability] = {
                "provider": provider,
                "model": model.strip() or str(profile.get("model") or ""),
            }
        data["ai_routes"] = routes
        self._write(data)

    def route_config(self, capability: str) -> dict | None:
        data = self._read()
        routes = data.get("ai_routes") if isinstance(data.get("ai_routes"), dict) else {}
        row = routes.get(capability.strip().lower())
        if not isinstance(row, dict):
            return None
        provider = str(row.get("provider") or "").strip().lower()
        model = str(row.get("model") or "").strip()
        if provider not in {"openai", "gemini", "ollama"}:
            return None
        if not model:
            model = self.DEFAULT_MODELS.get(provider, "")
        return {"provider": provider, "model": model}

    def configure(self, provider: str, model: str, api_key: str = "", *, remember_key: bool = True) -> None:
        provider = provider.strip().lower()
        if provider not in {"none", "openai", "gemini", "ollama"}:
            raise ValueError("unsupported provider")
        data = self._read()
        data["ai_provider"] = provider
        data["ai_model"] = model.strip() or self.DEFAULT_MODELS.get(provider, "")
        profiles = data.get("ai_profiles") if isinstance(data.get("ai_profiles"), dict) else {}
        if provider in {"openai", "gemini", "ollama"}:
            profile = profiles.get(provider) if isinstance(profiles.get(provider), dict) else {}
            profile["model"] = data["ai_model"]
            if api_key and provider in {"openai", "gemini"}:
                clean_key = api_key.strip()
                self._session_key = clean_key
                self._session_keys[provider] = clean_key
                self.credentials.set(f"{provider}.api_key", clean_key, remember=remember_key)
            profile.pop("key_cipher", None)
            data.pop("ai_key_cipher", None)
            profiles[provider] = profile
            data["ai_profiles"] = profiles
        elif provider == "none":
            data.pop("ai_key_cipher", None)
            self._session_key = ""
        self._write(data)

    def configure_provider(
        self,
        provider: str,
        model: str,
        api_key: str = "",
        *,
        remember_key: bool = True,
        make_default: bool = False,
        base_url: str = "",
    ) -> None:
        provider = provider.strip().lower()
        if provider not in {"openai", "gemini", "ollama"}:
            raise ValueError("unsupported provider")
        data = self._read()
        profiles = data.get("ai_profiles") if isinstance(data.get("ai_profiles"), dict) else {}
        profile = profiles.get(provider) if isinstance(profiles.get(provider), dict) else {}
        profile["model"] = model.strip() or self.DEFAULT_MODELS.get(provider, "")
        if provider == "ollama":
            profile["base_url"] = base_url.strip().rstrip("/") or str(profile.get("base_url") or "http://127.0.0.1:11434")
        if api_key and provider in {"openai", "gemini"}:
            clean_key = api_key.strip()
            self._session_keys[provider] = clean_key
            self.credentials.set(f"{provider}.api_key", clean_key, remember=remember_key)
        profile.pop("key_cipher", None)
        profiles[provider] = profile
        data["ai_profiles"] = profiles
        if make_default or str(data.get("ai_provider") or "none") == "none":
            data["ai_provider"] = provider
            data["ai_model"] = profile["model"]
            self._session_key = self._session_keys.get(provider, "")
        data.pop("ai_key_cipher", None)
        self._write(data)

    def clear_key(self) -> None:
        data = self._read()
        provider = str(data.get("ai_provider") or "").strip().lower()
        if provider in {"openai", "gemini"}:
            self.credentials.delete(f"{provider}.api_key")
            self._session_keys.pop(provider, None)
            profiles = data.get("ai_profiles") if isinstance(data.get("ai_profiles"), dict) else {}
            profile = profiles.get(provider) if isinstance(profiles.get(provider), dict) else {}
            profile.pop("key_cipher", None)
            profiles[provider] = profile
            data["ai_profiles"] = profiles
        data.pop("ai_key_cipher", None)
        self._session_key = ""
        self._write(data)

    def disconnect_provider(self, provider: str) -> None:
        provider = provider.strip().lower()
        if provider not in {"openai", "gemini", "ollama"}:
            return
        self.credentials.delete(f"{provider}.api_key")
        self._session_keys.pop(provider, None)
        data = self._read()
        profiles = data.get("ai_profiles") if isinstance(data.get("ai_profiles"), dict) else {}
        profile = profiles.get(provider) if isinstance(profiles.get(provider), dict) else {}
        profile.pop("key_cipher", None)
        profiles[provider] = profile
        data["ai_profiles"] = profiles
        if str(data.get("ai_provider") or "") == provider:
            data["ai_provider"] = "none"
            data["ai_model"] = ""
            data.pop("ai_key_cipher", None)
        self._write(data)

    def _key(self, provider: str) -> str:
        provider = provider.strip().lower()
        if provider == "ollama":
            return ""
        stored = self.credentials.get(f"{provider}.api_key")
        if stored:
            return stored
        if self._session_keys.get(provider):
            return self._session_keys[provider]

        # One-time compatibility migration from legacy DPAPI-in-settings storage.
        data = self._read()
        profiles = data.get("ai_profiles") if isinstance(data.get("ai_profiles"), dict) else {}
        profile = profiles.get(provider) if isinstance(profiles.get(provider), dict) else {}
        cipher = str(profile.get("key_cipher") or "")
        if not cipher and str(data.get("ai_provider") or "") == provider:
            if self._session_key:
                return self._session_key
            cipher = str(data.get("ai_key_cipher") or "")
        if cipher and os.name == "nt":
            try:
                value = _dpapi_unprotect(cipher)
                if value:
                    self.credentials.set(f"{provider}.api_key", value, remember=True)
                    profile.pop("key_cipher", None)
                    profiles[provider] = profile
                    data["ai_profiles"] = profiles
                    data.pop("ai_key_cipher", None)
                    self._write(data)
                    return value
            except Exception:
                return ""
        return ""

    def status(self, provider: str | None = None, model: str | None = None) -> ChatProviderStatus:
        cfg = self.settings()
        provider = (provider or str(cfg["provider"])).strip().lower()
        model = (model or (str(cfg["model"]) if provider == cfg["provider"] else self.provider_settings(provider)["model"])).strip()
        if provider == "none":
            return ChatProviderStatus(provider, model, False, "AIモデル未接続")
        if provider == "ollama":
            return ChatProviderStatus(provider, model, True, f"ollama / {model}")
        if provider not in {"openai", "gemini"}:
            return ChatProviderStatus(provider, model, False, "未対応プロバイダ")
        if not self._key(provider):
            return ChatProviderStatus(provider, model, False, "APIキー未設定")
        return ChatProviderStatus(provider, model, True, f"{provider} / {model}")

    def reply(self, history: list[dict], user_text: str, system_instruction: str) -> str:
        cfg = self.settings()
        provider = cfg["provider"]
        model = cfg["model"]
        key = self._key(provider)
        if provider == "ollama":
            profile = self.provider_settings("ollama")
            data = self._read()
            profiles = data.get("ai_profiles") if isinstance(data.get("ai_profiles"), dict) else {}
            raw = profiles.get("ollama") if isinstance(profiles.get("ollama"), dict) else {}
            base_url = os.environ.get("AIVY_OLLAMA_URL", str(raw.get("base_url") or "http://127.0.0.1:11434")).strip().rstrip("/")
            return self._ollama_reply(model, history, user_text, system_instruction, base_url=base_url)
        if provider not in {"openai", "gemini"}:
            raise RuntimeError("AIモデルが未接続です")
        if not key:
            raise RuntimeError("APIキーが未設定です")
        if provider == "openai":
            return self._openai_reply(model, key, history, user_text, system_instruction)
        return self._gemini_reply(model, key, history, user_text, system_instruction)

    def reply_resilient(
        self,
        history: list[dict],
        user_text: str,
        system_instruction: str,
    ) -> str:
        """Use configured provider, explicit cloud fallbacks, then local Ollama.

        Paid/cloud fallback providers are never used merely because credentials
        exist. They must be explicitly listed in ai_fallback_order. Ollama is a
        free/local final fallback and can be disabled with AIVY_DISABLE_OLLAMA_FALLBACK=1.
        """
        errors: list[str] = []
        settings = self.settings()
        primary = str(settings.get("provider") or "none").strip().lower()
        attempted: set[str] = set()

        if primary != "none":
            attempted.add(primary)
            try:
                status = self.status(primary)
                if status.connected:
                    return self.reply(history, user_text, system_instruction)
            except Exception as exc:
                errors.append(f"{primary}:{type(exc).__name__}")

        data = self._read()
        fallback_order = data.get("ai_fallback_order") if isinstance(data.get("ai_fallback_order"), list) else []
        for provider in [str(x).strip().lower() for x in fallback_order]:
            if provider in attempted or provider not in {"openai", "gemini", "ollama"}:
                continue
            attempted.add(provider)
            try:
                if provider == "ollama":
                    raw_profiles = data.get("ai_profiles") if isinstance(data.get("ai_profiles"), dict) else {}
                    raw = raw_profiles.get("ollama") if isinstance(raw_profiles.get("ollama"), dict) else {}
                    model = str(raw.get("model") or self.DEFAULT_MODELS["ollama"])
                    base_url = os.environ.get("AIVY_OLLAMA_URL", str(raw.get("base_url") or "http://127.0.0.1:11434")).strip().rstrip("/")
                    return self._ollama_reply(model, history, user_text, system_instruction, base_url=base_url)
                profile = self.provider_settings(provider)
                if self._key(provider):
                    return self.reply_routed(provider, str(profile.get("model") or ""), history, user_text, system_instruction)
            except Exception as exc:
                errors.append(f"{provider}:{type(exc).__name__}")

        if os.environ.get("AIVY_DISABLE_OLLAMA_FALLBACK", "").strip().lower() not in {"1", "true", "yes", "on"} and "ollama" not in attempted:
            raw_profiles = data.get("ai_profiles") if isinstance(data.get("ai_profiles"), dict) else {}
            raw = raw_profiles.get("ollama") if isinstance(raw_profiles.get("ollama"), dict) else {}
            model = os.environ.get("AIVY_OLLAMA_MODEL", str(raw.get("model") or self.DEFAULT_MODELS["ollama"])).strip() or self.DEFAULT_MODELS["ollama"]
            base_url = os.environ.get("AIVY_OLLAMA_URL", str(raw.get("base_url") or "http://127.0.0.1:11434")).strip().rstrip("/")
            try:
                return self._ollama_reply(model, history, user_text, system_instruction, base_url=base_url)
            except Exception as exc:
                errors.append(f"ollama:{type(exc).__name__}")
        raise RuntimeError("AI conversation providers unavailable: " + ", ".join(errors))

    def configure_fallback_order(self, providers: list[str]) -> None:
        clean = []
        for provider in providers:
            name = str(provider or "").strip().lower()
            if name in {"openai", "gemini", "ollama"} and name not in clean:
                clean.append(name)
        data = self._read()
        data["ai_fallback_order"] = clean
        self._write(data)

    def fallback_order(self) -> list[str]:
        data = self._read()
        rows = data.get("ai_fallback_order") if isinstance(data.get("ai_fallback_order"), list) else []
        return [str(x) for x in rows if str(x) in {"openai", "gemini", "ollama"}]

    def reply_routed(
        self,
        provider: str,
        model: str,
        history: list[dict],
        user_text: str,
        system_instruction: str,
    ) -> str:
        provider = provider.strip().lower()
        key = self._key(provider)
        if provider == "ollama":
            data = self._read()
            profiles = data.get("ai_profiles") if isinstance(data.get("ai_profiles"), dict) else {}
            raw = profiles.get("ollama") if isinstance(profiles.get("ollama"), dict) else {}
            base_url = os.environ.get("AIVY_OLLAMA_URL", str(raw.get("base_url") or "http://127.0.0.1:11434")).strip().rstrip("/")
            return self._ollama_reply(model or self.DEFAULT_MODELS["ollama"], history, user_text, system_instruction, base_url=base_url)
        if provider not in {"openai", "gemini"}:
            raise RuntimeError("AIモデルが未接続です")
        if not key:
            raise RuntimeError("APIキーが未設定です")
        if provider == "openai":
            return self._openai_reply(model, key, history, user_text, system_instruction)
        return self._gemini_reply(model, key, history, user_text, system_instruction)

    def vision_reply_routed(
        self,
        provider: str,
        model: str,
        image_paths: list[Path],
        prompt: str,
        system_instruction: str,
    ) -> str:
        provider = provider.strip().lower()
        key = self._key(provider)
        if provider not in {"openai", "gemini"}:
            raise RuntimeError("AIモデルが未接続です")
        if not key:
            raise RuntimeError("APIキーが未設定です")
        images = self._prepare_images(image_paths)
        if provider == "openai":
            return self._openai_vision_reply(model, key, images, prompt, system_instruction)
        return self._gemini_vision_reply(model, key, images, prompt, system_instruction)

    def vision_reply(
        self,
        image_paths: list[Path],
        prompt: str,
        system_instruction: str,
    ) -> str:
        cfg = self.settings()
        provider = cfg["provider"]
        model = cfg["model"]
        key = self._key(provider)
        if provider not in {"openai", "gemini"}:
            raise RuntimeError("AIモデルが未接続です")
        if not key:
            raise RuntimeError("APIキーが未設定です")
        images = self._prepare_images(image_paths)
        if provider == "openai":
            return self._openai_vision_reply(model, key, images, prompt, system_instruction)
        return self._gemini_vision_reply(model, key, images, prompt, system_instruction)

    @staticmethod
    def _prepare_images(image_paths: list[Path]) -> list[tuple[str, str]]:
        if not image_paths:
            raise ValueError("at least one image is required")
        if len(image_paths) > 3:
            raise ValueError("at most three screenshots can be reviewed at once")
        mime_by_suffix = {
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".webp": "image/webp",
        }
        rows: list[tuple[str, str]] = []
        for path in image_paths:
            path = Path(path)
            mime = mime_by_suffix.get(path.suffix.lower())
            if mime is None:
                raise ValueError("unsupported screenshot format")
            if not path.is_file() or path.is_symlink():
                raise ValueError("screenshot file is missing or unsafe")
            raw = path.read_bytes()
            if len(raw) > 5 * 1024 * 1024:
                raise ValueError("screenshot exceeds 5MB limit")
            rows.append((mime, base64.b64encode(raw).decode("ascii")))
        return rows

    @staticmethod
    def _request_json(url: str, headers: dict[str, str], payload: dict, timeout: int = 60) -> dict:
        request = urllib.request.Request(
            url,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json", **headers},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                raw = response.read()
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:800]
            raise RuntimeError(f"AI API error {exc.code}: {detail}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"AI API connection failed: {exc.reason}") from exc
        data = json.loads(raw.decode("utf-8"))
        if not isinstance(data, dict):
            raise RuntimeError("AI API returned an invalid response")
        return data

    def _ollama_reply(
        self,
        model: str,
        history: list[dict],
        user_text: str,
        system_instruction: str,
        *,
        base_url: str = "http://127.0.0.1:11434",
    ) -> str:
        messages: list[dict[str, str]] = [
            {"role": "system", "content": system_instruction},
        ]
        for row in history[-30:]:
            content = str(row.get("content") or "").strip()
            if not content:
                continue
            role = "user" if row.get("role") == "user" else "assistant"
            messages.append({"role": role, "content": content})
        messages.append({"role": "user", "content": user_text})
        data = self._request_json(
            base_url + "/api/chat",
            {},
            {
                "model": model,
                "messages": messages,
                "stream": False,
                "options": {
                    "temperature": 0.45,
                    "num_predict": 1600,
                },
            },
            timeout=90,
        )
        message = data.get("message")
        if isinstance(message, dict):
            content = str(message.get("content") or "").strip()
            if content:
                return content
        response = str(data.get("response") or "").strip()
        if response:
            return response
        raise RuntimeError("Ollama response did not contain text")

    def _openai_reply(self, model: str, key: str, history: list[dict], user_text: str, system_instruction: str) -> str:
        transcript = []
        for row in history[-30:]:
            role = "User" if row.get("role") == "user" else "Assistant"
            content = str(row.get("content") or "").strip()
            if content:
                transcript.append(f"{role}: {content}")
        transcript.append(f"User: {user_text}")
        data = self._request_json(
            "https://api.openai.com/v1/responses",
            {"Authorization": f"Bearer {key}"},
            {
                "model": model,
                "instructions": system_instruction,
                "input": "\n\n".join(transcript),
            },
        )
        if isinstance(data.get("output_text"), str) and data["output_text"].strip():
            return data["output_text"].strip()
        pieces: list[str] = []
        for item in data.get("output") or []:
            for part in item.get("content") or []:
                if part.get("type") == "output_text" and part.get("text"):
                    pieces.append(str(part["text"]))
        if pieces:
            return "\n".join(pieces).strip()
        raise RuntimeError("OpenAI response did not contain text")

    def _openai_vision_reply(
        self,
        model: str,
        key: str,
        images: list[tuple[str, str]],
        prompt: str,
        system_instruction: str,
    ) -> str:
        content: list[dict] = [{"type": "input_text", "text": prompt}]
        for mime, encoded in images:
            content.append({
                "type": "input_image",
                "image_url": f"data:{mime};base64,{encoded}",
                "detail": "auto",
            })
        data = self._request_json(
            "https://api.openai.com/v1/responses",
            {"Authorization": f"Bearer {key}"},
            {
                "model": model,
                "instructions": system_instruction,
                "input": [{"role": "user", "content": content}],
            },
        )
        if isinstance(data.get("output_text"), str) and data["output_text"].strip():
            return data["output_text"].strip()
        pieces: list[str] = []
        for item in data.get("output") or []:
            for part in item.get("content") or []:
                if part.get("type") == "output_text" and part.get("text"):
                    pieces.append(str(part["text"]))
        if pieces:
            return "\n".join(pieces).strip()
        raise RuntimeError("OpenAI vision response did not contain text")

    def _gemini_vision_reply(
        self,
        model: str,
        key: str,
        images: list[tuple[str, str]],
        prompt: str,
        system_instruction: str,
    ) -> str:
        parts: list[dict] = [{"text": prompt}]
        for mime, encoded in images:
            parts.append({"inlineData": {"mimeType": mime, "data": encoded}})
        data = self._request_json(
            f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
            {"x-goog-api-key": key},
            {
                "systemInstruction": {"parts": [{"text": system_instruction}]},
                "contents": [{"role": "user", "parts": parts}],
                "generationConfig": {"temperature": 0.2, "maxOutputTokens": 1800},
            },
        )
        pieces: list[str] = []
        for candidate in data.get("candidates") or []:
            for part in (candidate.get("content") or {}).get("parts") or []:
                if part.get("text"):
                    pieces.append(str(part["text"]))
        if pieces:
            return "\n".join(pieces).strip()
        raise RuntimeError("Gemini vision response did not contain text")

    def _gemini_reply(self, model: str, key: str, history: list[dict], user_text: str, system_instruction: str) -> str:
        contents = []
        for row in history[-30:]:
            content = str(row.get("content") or "").strip()
            if not content:
                continue
            contents.append({
                "role": "user" if row.get("role") == "user" else "model",
                "parts": [{"text": content}],
            })
        contents.append({"role": "user", "parts": [{"text": user_text}]})
        data = self._request_json(
            f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
            {"x-goog-api-key": key},
            {
                "systemInstruction": {"parts": [{"text": system_instruction}]},
                "contents": contents,
                "generationConfig": {"temperature": 0.7, "maxOutputTokens": 1600},
            },
        )
        pieces: list[str] = []
        for candidate in data.get("candidates") or []:
            for part in (candidate.get("content") or {}).get("parts") or []:
                if part.get("text"):
                    pieces.append(str(part["text"]))
        if pieces:
            return "\n".join(pieces).strip()
        raise RuntimeError("Gemini response did not contain text")
