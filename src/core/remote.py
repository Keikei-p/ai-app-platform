from __future__ import annotations
import hashlib
import hmac
import json
import time
from dataclasses import dataclass, asdict
from .permissions import PermissionEngine
from .database import save_remote_command, log_event
from .path_security import is_safe_slug

MIN_SECRET_BYTES = 32
MAX_COMMAND_TTL_SECONDS = 300
MAX_CLOCK_SKEW_SECONDS = 60
MAX_PAYLOAD_BYTES = 64 * 1024
MAX_COMMAND_ID_LEN = 128

@dataclass(frozen=True)
class RemoteCommand:
    command_id: str
    issued_at: int
    expires_at: int
    action: str
    project_slug: str | None
    payload: dict

    def canonical(self) -> bytes:
        return json.dumps(asdict(self), ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")

def _secret_ok(secret: bytes) -> bool:
    return isinstance(secret, (bytes, bytearray)) and len(secret) >= MIN_SECRET_BYTES

def _shape_ok(command: RemoteCommand) -> bool:
    if not command.command_id or len(command.command_id) > MAX_COMMAND_ID_LEN:
        return False
    if command.expires_at <= command.issued_at:
        return False
    if command.expires_at - command.issued_at > MAX_COMMAND_TTL_SECONDS:
        return False
    if command.project_slug is not None and not is_safe_slug(command.project_slug):
        return False
    try:
        if len(command.canonical()) > MAX_PAYLOAD_BYTES:
            return False
    except Exception:
        return False
    return True

def sign_command(command: RemoteCommand, secret: bytes) -> str:
    if not _secret_ok(secret):
        raise ValueError("remote_secret_must_be_at_least_32_bytes")
    if not _shape_ok(command):
        raise ValueError("invalid_remote_command")
    return hmac.new(secret, command.canonical(), hashlib.sha256).hexdigest()

def verify_command(command: RemoteCommand, signature: str, secret: bytes, now: int | None = None) -> bool:
    if not _secret_ok(secret) or not _shape_ok(command):
        return False
    now = int(time.time()) if now is None else now
    if now < command.issued_at - MAX_CLOCK_SKEW_SECONDS or now > command.expires_at:
        return False
    expected = hmac.new(secret, command.canonical(), hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)

@dataclass(frozen=True)
class RemoteAcceptance:
    accepted: bool
    reason: str
    requires_approval: bool = False

class RemoteCommandGate:
    """Validates signed remote commands before any worker can execute them.

    v0.4.8 Remote Beta remains LAN/local only; internet exposure is deliberately absent.
    """
    SAFE_REMOTE_ACTIONS = {"status", "project_list", "project_create", "run_pipeline", "run_tests", "backup", "vault_save", "build_preview", "maintenance_scan", "create_snapshot"}

    def __init__(self, secret: bytes):
        if not _secret_ok(secret):
            raise ValueError("remote_secret_must_be_at_least_32_bytes")
        self.secret = bytes(secret)
        self.permissions = PermissionEngine()

    def accept(self, command: RemoteCommand, signature: str, approved: bool = False, now: int | None = None) -> RemoteAcceptance:
        if not verify_command(command, signature, self.secret, now=now):
            return RemoteAcceptance(False, "invalid_or_expired_signature")
        if command.action not in self.SAFE_REMOTE_ACTIONS:
            p = self.permissions.decide(command.action, approved=False)
            # v0.4.2 deliberately refuses all non-allowlisted remote actions, even if a caller
            # supplies an "approved" flag. Future production actions must consume a server-side
            # one-time ApprovalStore record in a dedicated adapter; client booleans are not trust.
            return RemoteAcceptance(False, "remote_action_not_allowlisted", p.requires_approval)
        if not save_remote_command(command.command_id, command.action, command.project_slug, "accepted", json.dumps(command.payload, ensure_ascii=False)):
            return RemoteAcceptance(False, "replay_or_duplicate_command")
        log_event("remote.command.accepted", command.action, command.project_slug, "remote-gate")
        return RemoteAcceptance(True, "accepted")
