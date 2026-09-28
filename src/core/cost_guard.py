from __future__ import annotations

from dataclasses import asdict, dataclass
from decimal import Decimal, InvalidOperation
from typing import Any


@dataclass(frozen=True)
class CostDecision:
    allowed: bool
    status: str
    estimated_cost_yen: str
    remaining_budget_yen: str
    requires_human_approval: bool
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class CostGuard:
    """Deterministic no-surprise-spend gate.

    This class never performs billing or network calls. Unknown or metered cost
    is blocked unless the caller supplies explicit approval and a configured
    positive session budget.
    """

    def __init__(self, budget_yen: int | float | str = 0):
        self._budget = self._money(budget_yen)
        self._committed = Decimal("0")

    @staticmethod
    def _money(value: int | float | str | Decimal) -> Decimal:
        try:
            amount = Decimal(str(value))
        except (InvalidOperation, ValueError):
            raise ValueError("invalid cost value")
        if amount < 0:
            raise ValueError("cost cannot be negative")
        return amount.quantize(Decimal("0.01"))

    @property
    def remaining(self) -> Decimal:
        return max(Decimal("0"), self._budget - self._committed)

    def check(
        self,
        *,
        billing_mode: str,
        estimated_cost_yen: int | float | str | Decimal | None = None,
        explicitly_approved: bool = False,
    ) -> CostDecision:
        mode = str(billing_mode or "").strip().lower()
        if mode not in {"free", "metered", "unknown"}:
            raise ValueError("billing_mode must be free, metered, or unknown")

        if mode == "free":
            return CostDecision(True, "free", "0.00", f"{self.remaining:.2f}", False, "operation is classified as free/local")

        if estimated_cost_yen is None:
            return CostDecision(False, "blocked_unknown_cost", "unknown", f"{self.remaining:.2f}", True, "paid/unknown-cost operation requires an estimate and explicit approval")

        estimate = self._money(estimated_cost_yen)
        if not explicitly_approved:
            return CostDecision(False, "approval_required", f"{estimate:.2f}", f"{self.remaining:.2f}", True, "explicit approval is required before a metered operation")

        if self._budget <= 0:
            return CostDecision(False, "budget_not_configured", f"{estimate:.2f}", f"{self.remaining:.2f}", True, "no positive session spending budget is configured")

        if estimate > self.remaining:
            return CostDecision(False, "budget_exceeded", f"{estimate:.2f}", f"{self.remaining:.2f}", True, "estimated cost exceeds remaining session budget")

        return CostDecision(True, "approved_within_budget", f"{estimate:.2f}", f"{self.remaining:.2f}", False, "approved estimate fits within remaining session budget")

    def commit(self, decision: CostDecision) -> str:
        if not decision.allowed:
            raise PermissionError("cannot commit a blocked cost decision")
        if decision.estimated_cost_yen == "unknown":
            raise ValueError("cannot commit unknown cost")
        amount = self._money(decision.estimated_cost_yen)
        if amount > self.remaining:
            raise RuntimeError("cost budget changed before commit")
        self._committed += amount
        return f"{self._committed:.2f}"

    def snapshot(self) -> dict[str, str]:
        return {
            "budget_yen": f"{self._budget:.2f}",
            "committed_yen": f"{self._committed:.2f}",
            "remaining_yen": f"{self.remaining:.2f}",
        }
