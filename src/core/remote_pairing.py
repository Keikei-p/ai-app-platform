from __future__ import annotations

import secrets
import threading
import time
from dataclasses import dataclass


@dataclass(frozen=True)
class PairingTicket:
    code: str
    expires_at: int


class PairingManager:
    """In-memory, one-time pairing codes. Codes disappear on app restart."""

    def __init__(self, ttl_seconds: int = 300, max_attempts: int = 8):
        self.ttl_seconds = max(60, min(int(ttl_seconds), 900))
        self.max_attempts = max(1, min(int(max_attempts), 20))
        self._lock = threading.Lock()
        self._code: str | None = None
        self._expires_at = 0
        self._attempts = 0

    def create(self, now: int | None = None) -> PairingTicket:
        now = int(time.time()) if now is None else int(now)
        # 10 chars from a reduced alphabet: easy to type, much stronger than a 6-digit PIN.
        alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
        code = "".join(secrets.choice(alphabet) for _ in range(10))
        with self._lock:
            self._code = code
            self._expires_at = now + self.ttl_seconds
            self._attempts = 0
        return PairingTicket(code, self._expires_at)

    def consume(self, code: str, now: int | None = None) -> bool:
        now = int(time.time()) if now is None else int(now)
        supplied = (code or "").strip().upper()
        with self._lock:
            if not self._code or now > self._expires_at or self._attempts >= self.max_attempts:
                self._code = None
                return False
            self._attempts += 1
            if not secrets.compare_digest(supplied, self._code):
                return False
            self._code = None
            self._expires_at = 0
            return True

    def invalidate(self) -> None:
        with self._lock:
            self._code = None
            self._expires_at = 0
            self._attempts = 0
