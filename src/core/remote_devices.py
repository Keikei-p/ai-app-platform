from __future__ import annotations

import base64
import json
import os
import secrets
import threading
import ctypes
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from .config import CONFIG_DIR
from .database import log_event

_DEVICE_FILE = CONFIG_DIR / "remote_devices.json"
_SETTINGS_FILE = CONFIG_DIR / "remote_settings.json"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _atomic_json_write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    try:
        os.chmod(temp, 0o600)
    except OSError:
        pass
    temp.replace(path)
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


def _protect_secret(secret: bytes) -> str:
    """Protect a remote HMAC secret with Windows DPAPI when available."""
    if os.name != "nt":
        return "plain:" + base64.b64encode(secret).decode("ascii")
    try:
        from ctypes import wintypes
        class DATA_BLOB(ctypes.Structure):
            _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_ubyte))]
        buf = ctypes.create_string_buffer(secret)
        in_blob = DATA_BLOB(len(secret), ctypes.cast(buf, ctypes.POINTER(ctypes.c_ubyte)))
        out_blob = DATA_BLOB()
        crypt32 = ctypes.windll.crypt32
        kernel32 = ctypes.windll.kernel32
        crypt32.CryptProtectData.argtypes = [ctypes.POINTER(DATA_BLOB), wintypes.LPCWSTR, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(DATA_BLOB)]
        crypt32.CryptProtectData.restype = wintypes.BOOL
        kernel32.LocalFree.argtypes = [ctypes.c_void_p]
        kernel32.LocalFree.restype = ctypes.c_void_p
        if not crypt32.CryptProtectData(ctypes.byref(in_blob), None, None, None, None, 0x1, ctypes.byref(out_blob)):
            raise OSError("CryptProtectData failed")
        try:
            protected = ctypes.string_at(out_blob.pbData, out_blob.cbData)
        finally:
            kernel32.LocalFree(out_blob.pbData)
        return "dpapi:" + base64.b64encode(protected).decode("ascii")
    except Exception:
        # LocalAppData + best-effort file permissions still apply if DPAPI is unavailable.
        return "plain:" + base64.b64encode(secret).decode("ascii")


def _unprotect_secret(value: str) -> bytes | None:
    if not isinstance(value, str) or ":" not in value:
        return None
    mode, encoded = value.split(":", 1)
    try:
        raw = base64.b64decode(encoded, validate=True)
    except Exception:
        return None
    if mode == "plain":
        return raw
    if mode != "dpapi" or os.name != "nt":
        return None
    try:
        from ctypes import wintypes
        class DATA_BLOB(ctypes.Structure):
            _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_ubyte))]
        buf = ctypes.create_string_buffer(raw)
        in_blob = DATA_BLOB(len(raw), ctypes.cast(buf, ctypes.POINTER(ctypes.c_ubyte)))
        out_blob = DATA_BLOB()
        crypt32 = ctypes.windll.crypt32
        kernel32 = ctypes.windll.kernel32
        crypt32.CryptUnprotectData.argtypes = [ctypes.POINTER(DATA_BLOB), ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(DATA_BLOB)]
        crypt32.CryptUnprotectData.restype = wintypes.BOOL
        kernel32.LocalFree.argtypes = [ctypes.c_void_p]
        kernel32.LocalFree.restype = ctypes.c_void_p
        if not crypt32.CryptUnprotectData(ctypes.byref(in_blob), None, None, None, None, 0x1, ctypes.byref(out_blob)):
            return None
        try:
            return ctypes.string_at(out_blob.pbData, out_blob.cbData)
        finally:
            kernel32.LocalFree(out_blob.pbData)
    except Exception:
        return None


@dataclass(frozen=True)
class RemoteDevice:
    device_id: str
    name: str
    created_at: str
    last_seen_at: str | None
    revoked: bool


class RemoteDeviceStore:
    """Stores paired-device metadata and per-device HMAC secrets in user-local config.

    v0.4.8 is LAN-only beta. The file is placed under the current user's app-data
    directory and permissions are tightened where supported. Internet exposure is not
    enabled by this module.
    """

    def __init__(self, path: Path | None = None, settings_path: Path | None = None):
        self.path = path or _DEVICE_FILE
        self.settings_path = settings_path or _SETTINGS_FILE
        self._lock = threading.RLock()
        self._ensure_files()

    def _ensure_files(self) -> None:
        with self._lock:
            if not self.path.exists():
                _atomic_json_write(self.path, {"format": 1, "devices": []})
            if not self.settings_path.exists():
                _atomic_json_write(self.settings_path, {"format": 1, "enabled": False})

    def _read(self) -> dict:
        self._ensure_files()
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            if raw.get("format") != 1 or not isinstance(raw.get("devices"), list):
                raise ValueError("invalid_remote_device_store")
            return raw
        except (OSError, json.JSONDecodeError, ValueError):
            return {"format": 1, "devices": []}

    def _write(self, raw: dict) -> None:
        _atomic_json_write(self.path, raw)

    def list_devices(self, include_revoked: bool = False) -> list[RemoteDevice]:
        with self._lock:
            rows = []
            for d in self._read()["devices"]:
                if d.get("revoked") and not include_revoked:
                    continue
                rows.append(RemoteDevice(
                    device_id=str(d.get("device_id") or ""),
                    name=str(d.get("name") or "端末"),
                    created_at=str(d.get("created_at") or ""),
                    last_seen_at=d.get("last_seen_at"),
                    revoked=bool(d.get("revoked")),
                ))
            return rows

    def pair(self, name: str) -> tuple[RemoteDevice, bytes]:
        clean_name = (name or "スマホ").strip()[:80] or "スマホ"
        with self._lock:
            raw = self._read()
            device_id = secrets.token_hex(12)
            secret = secrets.token_bytes(32)
            now = _utc_now()
            raw["devices"].append({
                "device_id": device_id,
                "name": clean_name,
                "created_at": now,
                "last_seen_at": now,
                "revoked": False,
                "secret_protected": _protect_secret(secret),
            })
            self._write(raw)
            log_event("remote.device.paired", json.dumps({"device_id": device_id, "name": clean_name}, ensure_ascii=False), actor="remote-pairing")
            return RemoteDevice(device_id, clean_name, now, now, False), secret

    def secret_for(self, device_id: str) -> bytes | None:
        if not isinstance(device_id, str) or len(device_id) > 128:
            return None
        with self._lock:
            raw = self._read()
            changed = False
            for d in raw["devices"]:
                if d.get("device_id") != device_id or d.get("revoked"):
                    continue
                secret = _unprotect_secret(str(d.get("secret_protected") or ""))
                if secret is None:
                    return None
                if len(secret) < 32:
                    return None
                d["last_seen_at"] = _utc_now()
                changed = True
                if changed:
                    self._write(raw)
                return secret
            return None

    def revoke(self, device_id: str) -> bool:
        with self._lock:
            raw = self._read()
            for d in raw["devices"]:
                if d.get("device_id") == device_id and not d.get("revoked"):
                    d["revoked"] = True
                    d.pop("secret_protected", None)
                    self._write(raw)
                    log_event("remote.device.revoked", device_id, actor="remote-control")
                    return True
            return False

    def revoke_all(self) -> int:
        count = 0
        with self._lock:
            raw = self._read()
            for d in raw["devices"]:
                if not d.get("revoked"):
                    d["revoked"] = True
                    d.pop("secret_protected", None)
                    count += 1
            self._write(raw)
        if count:
            log_event("remote.devices.revoked_all", str(count), actor="remote-control")
        return count

    def is_enabled(self) -> bool:
        try:
            raw = json.loads(self.settings_path.read_text(encoding="utf-8"))
            return bool(raw.get("enabled"))
        except (OSError, json.JSONDecodeError):
            return False

    def set_enabled(self, enabled: bool) -> None:
        _atomic_json_write(self.settings_path, {"format": 1, "enabled": bool(enabled), "updated_at": _utc_now()})
        log_event("remote.enabled" if enabled else "remote.disabled", str(bool(enabled)), actor="remote-control")
