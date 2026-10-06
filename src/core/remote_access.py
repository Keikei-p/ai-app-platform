from __future__ import annotations

from typing import Mapping
import os


def remote_bind_policy(
    host: str,
    env: Mapping[str, str] | None = None,
) -> dict[str, object]:
    values = os.environ if env is None else env
    normalized = str(host or "").strip().lower()
    loopback = normalized in {"127.0.0.1", "localhost", "::1"}
    token = str(values.get("AI_APP_LOCAL_API_TOKEN") or "").strip()
    remote_enabled = str(values.get("AI_APP_ENABLE_REMOTE") or "").strip().lower() in {
        "1", "true", "yes", "on",
    }
    allowed = loopback or (remote_enabled and bool(token))
    return {
        "host": normalized,
        "loopback": loopback,
        "remote_enabled": remote_enabled,
        "token_configured": bool(token),
        "allowed": allowed,
        "requires_bearer": not loopback,
        "reason": (
            "loopback"
            if loopback
            else "remote_enabled_with_token"
            if allowed
            else "remote_bind_requires_AI_APP_ENABLE_REMOTE_and_AI_APP_LOCAL_API_TOKEN"
        ),
    }
