from __future__ import annotations
from dataclasses import dataclass

@dataclass(frozen=True)
class PermissionDecision:
    allowed: bool
    requires_approval: bool
    reason: str

class PermissionEngine:
    """Non-AI policy layer. Destructive/production actions require explicit approval."""

    ALWAYS_BLOCK = {"disable_safety", "self_elevate", "erase_audit_log", "erase_all_backups"}
    REQUIRE_APPROVAL = {
        "production_deploy", "production_db_delete", "billing_change", "domain_change",
        "secret_export", "remote_shell_enable", "mass_user_delete", "store_submit"
    }

    def decide(self, action: str, approved: bool = False) -> PermissionDecision:
        if action in self.ALWAYS_BLOCK:
            return PermissionDecision(False, False, "This action is forbidden by the platform constitution.")
        if action in self.REQUIRE_APPROVAL and not approved:
            return PermissionDecision(False, True, "Human approval is required.")
        return PermissionDecision(True, False, "Allowed.")
