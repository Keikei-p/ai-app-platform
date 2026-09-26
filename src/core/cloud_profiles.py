from __future__ import annotations
import json
from dataclasses import dataclass, asdict
from .config import PROFILES_PATH

SUPPORTED_PROVIDERS = ["cloudflare", "aws", "firebase", "azure", "self-hosted"]

@dataclass
class CloudProfile:
    name: str
    provider: str
    account_label: str = ""
    region: str = ""
    notes: str = ""

@dataclass(frozen=True)
class DeploymentPlan:
    provider: str
    project_slug: str
    steps: list[str]
    dry_run: bool = True

class CloudProfileStore:
    """Non-secret metadata only. Credentials are deliberately excluded from this file."""
    def load(self) -> list[CloudProfile]:
        if not PROFILES_PATH.exists():
            return []
        raw = json.loads(PROFILES_PATH.read_text(encoding="utf-8"))
        return [CloudProfile(**item) for item in raw]

    def save(self, profiles: list[CloudProfile]) -> None:
        PROFILES_PATH.write_text(json.dumps([asdict(p) for p in profiles], ensure_ascii=False, indent=2), encoding="utf-8")

class CloudDeploymentPlanner:
    def plan(self, profile: CloudProfile, project_slug: str) -> DeploymentPlan:
        if profile.provider not in SUPPORTED_PROVIDERS:
            raise ValueError("unsupported provider")
        return DeploymentPlan(profile.provider, project_slug, [
            "validate_connection",
            "validate_target_permissions",
            "create_or_update_preview_environment",
            "deploy_preview",
            "run_health_check",
            "request_human_approval_before_production",
        ], True)
