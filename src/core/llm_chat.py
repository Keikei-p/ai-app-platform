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
    }

    def __init__(self, settings_path: Path | None = None):
        self.settings_path = settings_path or SETTINGS_PATH
        self._session_key = ""

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
        model = str(data.get("ai_model") or self.DEFAULT_MODELS.get(provider, ""))
        return {"provider": provider, "model": model}

    def configure(self, provider: str, model: str, api_key: str = "", *, remember_key: bool = True) -> None:
        provider = provider.strip().lower()
        if provider not in {"none", "openai", "gemini"}:
            raise ValueError("unsupported provider")
        data = self._read()
        data["ai_provider"] = provider
        data["ai_model"] = model.strip() or self.DEFAULT_MODELS.get(provider, "")
        if api_key:
            self._session_key = api_key.strip()
            if remember_key and os.name == "nt":
                data["ai_key_cipher"] = _dpapi_protect(self._session_key)
            elif not remember_key:
                data.pop("ai_key_cipher", None)
        elif provider == "none":
            data.pop("ai_key_cipher", None)
            self._session_key = ""
        self._write(data)

    def clear_key(self) -> None:
        data = self._read()
        data.pop("ai_key_cipher", None)
        self._session_key = ""
        self._write(data)

    def _key(self, provider: str) -> str:
        env_name = "OPENAI_API_KEY" if provider == "openai" else "GEMINI_API_KEY"
        env = os.environ.get(env_name, "").strip()
        if env:
            return env
        if self._session_key:
            return self._session_key
        cipher = str(self._read().get("ai_key_cipher") or "")
        if cipher and os.name == "nt":
            try:
                return _dpapi_unprotect(cipher)
            except Exception:
                return ""
        return ""

    def status(self) -> ChatProviderStatus:
        cfg = self.settings()
        provider = cfg["provider"]
        model = cfg["model"]
        if provider == "none":
            return ChatProviderStatus(provider, model, False, "AIモデル未接続")
        if not self._key(provider):
            return ChatProviderStatus(provider, model, False, "APIキー未設定")
        return ChatProviderStatus(provider, model, True, f"{provider} / {model}")

    def reply(self, history: list[dict], user_text: str, system_instruction: str) -> str:
        cfg = self.settings()
        provider = cfg["provider"]
        model = cfg["model"]
        key = self._key(provider)
        if provider not in {"openai", "gemini"}:
            raise RuntimeError("AIモデルが未接続です")
        if not key:
            raise RuntimeError("APIキーが未設定です")
        if provider == "openai":
            return self._openai_reply(model, key, history, user_text, system_instruction)
        return self._gemini_reply(model, key, history, user_text, system_instruction)

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
