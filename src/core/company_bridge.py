"""Optional, localhost-only Ivy <-> AI COMPANY OS mission intake.

This interface does NOT execute builds, expose secrets, share databases or
approve work. It only queues a reviewed-by-owner Mission planning request.
Buyer/OEM installs configure their own token outside source control.
"""
from __future__ import annotations

import ipaddress
import os
import re
import secrets
from typing import Any, Mapping


_TOKEN_HEADER = "X-Ivy-Company-Token"
_SLUG = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,79}$")
_ALLOWED_FIELDS = {"goal", "project_slug", "max_cycles"}


class CompanyBridge:
    def __init__(self, service: Any, *, env: Mapping[str, str] | None = None):
        self.service = service
        env = os.environ if env is None else env
        self._token = str(env.get("AIVY_COMPANY_BRIDGE_TOKEN") or "")
        # Disabled by default. Reject short/malformed credentials.
        self.enabled = len(self._token) >= 32 and not self._token.isspace()

    @staticmethod
    def header_name() -> str:
        return _TOKEN_HEADER

    def authorized(self, client_ip: str, token: str, *, remote_mode: bool = False) -> bool:
        if not self.enabled or remote_mode or not isinstance(token, str):
            return False
        try:
            if not ipaddress.ip_address(client_ip).is_loopback:
                return False
        except ValueError:
            return False
        if not token or len(token) > 512:
            return False
        return secrets.compare_digest(token, self._token)

    def status(self) -> dict[str, Any]:
        # No CSRF tokens, connector details, project paths, secrets or raw
        # mission goals cross the integration boundary.
        watchdog = self.service.build_watchdog_status()
        return {
            "service": "aivy",
            "integration": "ai_company_os",
            "schema_version": 1,
            "mission_intake_enabled": self.enabled,
            "automatic_build_approval": False,
            "automatic_publication": False,
            "history_persistence_ok": watchdog.get("persistence_ok") is True,
            "active_build_count": int(watchdog.get("active_count") or 0),
        }

    def enqueue_mission(self, body: dict[str, Any]) -> dict[str, Any]:
        if not self.enabled:
            raise PermissionError("company_bridge_disabled")
        if not isinstance(body, dict) or body.keys() - _ALLOWED_FIELDS:
            raise ValueError("only goal, project_slug and max_cycles are accepted")
        goal = body.get("goal")
        slug = body.get("project_slug")
        cycles = body.get("max_cycles", 1)
        if not isinstance(goal, str) or not (1 <= len(goal.strip()) <= 2000):
            raise ValueError("goal must be 1-2000 characters")
        if not isinstance(slug, str) or not _SLUG.fullmatch(slug):
            raise ValueError("invalid project_slug")
        if type(cycles) is not int or not 1 <= cycles <= 8:
            raise ValueError("max_cycles must be an integer from 1 to 8")
        # Existing PlatformService checks the project exists and saves Mission
        # state. No run_mission_cycle() or approved_build=True call here.
        row = self.service.create_mission(
            goal=goal.strip(), project_slug=slug, max_cycles=cycles
        )
        return {
            "mission_id": str(row["mission_id"]),
            "status": str(row["status"]),
            "requires_owner_approval": True,
            "executed": False,
            "publish_performed": False,
        }
