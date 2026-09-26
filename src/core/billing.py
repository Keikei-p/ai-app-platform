from __future__ import annotations
from dataclasses import dataclass

@dataclass(frozen=True)
class Plan:
    key: str
    label: str
    worker_mode: str
    max_projects: int | None
    hosted_minutes: int
    multi_user: bool
    store_release: bool

PLANS = {
    "free": Plan("free", "Free", "local", 2, 0, False, False),
    "personal": Plan("personal", "Personal", "local", 10, 0, False, True),
    "pro": Plan("pro", "Pro", "local", None, 0, False, True),
    "cloud": Plan("cloud", "Cloud", "hosted", 10, 600, False, True),
    "business": Plan("business", "Business", "hosted", None, 3000, True, True),
    "enterprise": Plan("enterprise", "Enterprise", "enterprise", None, 0, True, True),
}

PAYMENT_ADAPTERS = ["web-payment-provider", "apple-iap", "google-play-billing"]

@dataclass(frozen=True)
class EntitlementDecision:
    allowed: bool
    reason: str

class EntitlementEngine:
    def check(self, plan_key: str, capability: str, *, project_count: int = 0, hosted_minutes_used: int = 0) -> EntitlementDecision:
        plan = PLANS.get(plan_key)
        if not plan:
            return EntitlementDecision(False, "unknown_plan")
        if capability == "create_project" and plan.max_projects is not None and project_count >= plan.max_projects:
            return EntitlementDecision(False, "project_limit_reached")
        if capability == "hosted_worker":
            if plan.worker_mode != "hosted":
                return EntitlementDecision(False, "hosted_worker_not_in_plan")
            if hosted_minutes_used >= plan.hosted_minutes:
                return EntitlementDecision(False, "hosted_minutes_exhausted")
        if capability == "multi_user" and not plan.multi_user:
            return EntitlementDecision(False, "multi_user_not_in_plan")
        if capability == "store_release" and not plan.store_release:
            return EntitlementDecision(False, "store_release_not_in_plan")
        return EntitlementDecision(True, "allowed")
