from __future__ import annotations
from dataclasses import dataclass
from .billing import PLANS

@dataclass(frozen=True)
class WorkerMode:
    key: str
    label: str
    owner: str
    purpose: str

WORKER_MODES = {
    "local": WorkerMode("local", "Home PC Worker", "user", "Use user's own PC for AI/build/test workloads."),
    "hosted": WorkerMode("hosted", "Hosted Worker", "platform", "For users without a PC; metered compute provided by platform."),
    "enterprise": WorkerMode("enterprise", "Enterprise Worker", "customer-org", "Runs in company-managed infrastructure."),
}

@dataclass(frozen=True)
class JobRoute:
    worker_mode: str
    reason: str

class JobRouter:
    def route(self, plan_key: str, home_pc_online: bool) -> JobRoute:
        plan = PLANS.get(plan_key, PLANS["free"])
        if home_pc_online:
            return JobRoute("local", "home_pc_available")
        if plan.worker_mode == "hosted":
            return JobRoute("hosted", "pc_offline_use_hosted_entitlement")
        if plan.worker_mode == "enterprise":
            return JobRoute("enterprise", "enterprise_worker")
        return JobRoute("unavailable", "home_pc_required_for_current_plan")
