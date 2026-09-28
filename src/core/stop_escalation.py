from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
from typing import Any
import json


@dataclass(frozen=True)
class EscalationDecision:
    action: str
    reason: str
    requires_human: bool
    fingerprint: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class StopEscalationJudge:
    """Stop runaway autonomy and surface cases that need a human/environment fix."""

    MAX_REPAIR_ATTEMPTS = 2

    def decide(
        self,
        *,
        risk: str = "GREEN",
        failure_kind: str = "UNKNOWN",
        attempts_used: int = 0,
        prior_fingerprints: list[str] | tuple[str, ...] = (),
        signals: list[str] | tuple[str, ...] = (),
        external_dependency_blocked: bool = False,
        permission_missing: bool = False,
    ) -> EscalationDecision:
        normalized = tuple(sorted(set(str(x).strip().lower() for x in signals if str(x).strip())))
        fingerprint = sha256(json.dumps({
            "failure_kind": str(failure_kind).upper(),
            "signals": normalized,
        }, sort_keys=True).encode("utf-8")).hexdigest()

        risk = str(risk or "GREEN").upper()
        kind = str(failure_kind or "UNKNOWN").upper()
        attempts = max(0, int(attempts_used))
        repeated = bool(prior_fingerprints) and fingerprint == str(prior_fingerprints[-1])

        if risk == "RED":
            return EscalationDecision("ESCALATE", "red-risk change requires human approval", True, fingerprint)
        if permission_missing:
            return EscalationDecision("ESCALATE", "required permission/credential is missing", True, fingerprint)
        if external_dependency_blocked:
            return EscalationDecision("STOP", "external dependency or service is unavailable", False, fingerprint)
        if repeated:
            return EscalationDecision("STOP", "same failure fingerprint repeated", False, fingerprint)
        if attempts >= self.MAX_REPAIR_ATTEMPTS:
            return EscalationDecision("STOP", "repair-attempt budget exhausted", False, fingerprint)
        if kind in {"ENVIRONMENT", "CAPABILITY", "UNKNOWN", "SECURITY"}:
            return EscalationDecision("ESCALATE", f"{kind.lower()} failure needs additional evidence or human/environment action", True, fingerprint)
        return EscalationDecision("CONTINUE", "bounded local repair may continue", False, fingerprint)
