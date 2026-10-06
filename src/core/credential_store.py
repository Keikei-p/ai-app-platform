from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol
import ctypes
from ctypes import wintypes
import os


class CredentialBackend(Protocol):
    name: str

    def get(self, target: str) -> str: ...
    def set(self, target: str, value: str) -> None: ...
    def delete(self, target: str) -> None: ...
    def has(self, target: str) -> bool: ...


class SessionCredentialBackend:
    name = "session"

    def __init__(self):
        self._values: dict[str, str] = {}

    def get(self, target: str) -> str:
        return self._values.get(target, "")

    def set(self, target: str, value: str) -> None:
        self._values[target] = str(value)

    def delete(self, target: str) -> None:
        self._values.pop(target, None)

    def has(self, target: str) -> bool:
        return bool(self._values.get(target))


if os.name == "nt":
    LPBYTE = ctypes.POINTER(wintypes.BYTE)

    class _CREDENTIALW(ctypes.Structure):
        _fields_ = [
            ("Flags", wintypes.DWORD),
            ("Type", wintypes.DWORD),
            ("TargetName", wintypes.LPWSTR),
            ("Comment", wintypes.LPWSTR),
            ("LastWritten", wintypes.FILETIME),
            ("CredentialBlobSize", wintypes.DWORD),
            ("CredentialBlob", LPBYTE),
            ("Persist", wintypes.DWORD),
            ("AttributeCount", wintypes.DWORD),
            ("Attributes", ctypes.c_void_p),
            ("TargetAlias", wintypes.LPWSTR),
            ("UserName", wintypes.LPWSTR),
        ]


class WindowsCredentialBackend:
    name = "windows_credential_manager"
    CRED_TYPE_GENERIC = 1
    CRED_PERSIST_LOCAL_MACHINE = 2

    def __init__(self):
        if os.name != "nt":
            raise OSError("Windows Credential Manager is available only on Windows")
        self.advapi32 = ctypes.windll.advapi32
        self.advapi32.CredWriteW.argtypes = [ctypes.POINTER(_CREDENTIALW), wintypes.DWORD]
        self.advapi32.CredWriteW.restype = wintypes.BOOL
        self.advapi32.CredReadW.argtypes = [
            wintypes.LPCWSTR,
            wintypes.DWORD,
            wintypes.DWORD,
            ctypes.POINTER(ctypes.POINTER(_CREDENTIALW)),
        ]
        self.advapi32.CredReadW.restype = wintypes.BOOL
        self.advapi32.CredDeleteW.argtypes = [
            wintypes.LPCWSTR,
            wintypes.DWORD,
            wintypes.DWORD,
        ]
        self.advapi32.CredDeleteW.restype = wintypes.BOOL
        self.advapi32.CredFree.argtypes = [ctypes.c_void_p]
        self.advapi32.CredFree.restype = None

    def get(self, target: str) -> str:
        pointer = ctypes.POINTER(_CREDENTIALW)()
        ok = self.advapi32.CredReadW(
            target,
            self.CRED_TYPE_GENERIC,
            0,
            ctypes.byref(pointer),
        )
        if not ok:
            return ""
        try:
            item = pointer.contents
            if not item.CredentialBlob or not item.CredentialBlobSize:
                return ""
            raw = ctypes.string_at(item.CredentialBlob, item.CredentialBlobSize)
            return raw.decode("utf-16-le")
        finally:
            self.advapi32.CredFree(pointer)

    def set(self, target: str, value: str) -> None:
        raw = str(value).encode("utf-16-le")
        blob = (wintypes.BYTE * len(raw)).from_buffer_copy(raw)
        credential = _CREDENTIALW()
        credential.Flags = 0
        credential.Type = self.CRED_TYPE_GENERIC
        credential.TargetName = target
        credential.Comment = "Aivy external service credential"
        credential.CredentialBlobSize = len(raw)
        credential.CredentialBlob = ctypes.cast(blob, LPBYTE)
        credential.Persist = self.CRED_PERSIST_LOCAL_MACHINE
        credential.AttributeCount = 0
        credential.Attributes = None
        credential.TargetAlias = None
        credential.UserName = "Aivy"
        if not self.advapi32.CredWriteW(ctypes.byref(credential), 0):
            raise OSError("Windows Credential Manager write failed")

    def delete(self, target: str) -> None:
        self.advapi32.CredDeleteW(target, self.CRED_TYPE_GENERIC, 0)

    def has(self, target: str) -> bool:
        return bool(self.get(target))


@dataclass(frozen=True)
class CredentialStatus:
    credential_id: str
    configured: bool
    backend: str
    masked: str


class CredentialStore:
    """Dedicated credential boundary.

    Secrets never belong in normal settings/config exports. Persistent storage
    uses Windows Credential Manager on Windows. Non-Windows runtimes use
    environment variables or session-only memory unless another secure backend
    is explicitly added later.
    """

    ENV_MAP = {
        "openai.api_key": "OPENAI_API_KEY",
        "gemini.api_key": "GEMINI_API_KEY",
        "github.token": "GITHUB_TOKEN",
        "cloudflare.token": "CLOUDFLARE_API_TOKEN",
        "vercel.token": "VERCEL_TOKEN",
        "netlify.token": "NETLIFY_AUTH_TOKEN",
        "supabase.key": "SUPABASE_KEY",
        "firebase.service_account": "FIREBASE_SERVICE_ACCOUNT_JSON",
        "google_play.service_account": "GOOGLE_PLAY_SERVICE_ACCOUNT_JSON",
        "apple.private_key": "APPLE_DEVELOPER_PRIVATE_KEY",
        "d1.token": "CLOUDFLARE_API_TOKEN",
    }

    def __init__(self, backend: CredentialBackend | None = None, *, namespace: str = "Aivy"):
        if backend is not None:
            self.backend = backend
        elif os.name == "nt":
            self.backend = WindowsCredentialBackend()
        else:
            self.backend = SessionCredentialBackend()
        self.namespace = namespace.strip() or "Aivy"
        self.session = SessionCredentialBackend()

    def target(self, credential_id: str) -> str:
        clean = credential_id.strip().lower()
        if not clean or any(ch.isspace() for ch in clean):
            raise ValueError("invalid credential id")
        return f"{self.namespace}/{clean}"

    def get(self, credential_id: str) -> str:
        env_name = self.ENV_MAP.get(credential_id.strip().lower())
        if env_name:
            value = os.environ.get(env_name, "").strip()
            if value:
                return value
        target = self.target(credential_id)
        session_value = self.session.get(target)
        if session_value:
            return session_value
        return self.backend.get(target)

    def set(self, credential_id: str, value: str, *, remember: bool = True) -> None:
        clean = str(value or "").strip()
        if not clean:
            raise ValueError("credential value is required")
        target = self.target(credential_id)
        if remember:
            self.backend.set(target, clean)
            self.session.delete(target)
        else:
            self.session.set(target, clean)

    def delete(self, credential_id: str) -> None:
        target = self.target(credential_id)
        self.session.delete(target)
        self.backend.delete(target)

    def has(self, credential_id: str) -> bool:
        return bool(self.get(credential_id))

    def status(self, credential_id: str) -> CredentialStatus:
        value = self.get(credential_id)
        return CredentialStatus(
            credential_id=credential_id,
            configured=bool(value),
            backend=self._effective_backend(credential_id),
            masked=self.mask(value),
        )

    def _effective_backend(self, credential_id: str) -> str:
        env_name = self.ENV_MAP.get(credential_id.strip().lower())
        if env_name and os.environ.get(env_name, "").strip():
            return "environment"
        target = self.target(credential_id)
        if self.session.has(target):
            return "session"
        return self.backend.name

    @staticmethod
    def mask(value: str) -> str:
        clean = str(value or "")
        if not clean:
            return ""
        if len(clean) <= 4:
            return "••••"
        suffix = clean[-4:]
        prefix = clean[:3] if len(clean) > 8 else ""
        return f"{prefix}••••••••{suffix}"
