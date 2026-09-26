from __future__ import annotations
from dataclasses import dataclass

@dataclass(frozen=True)
class PlatformTarget:
    key: str
    label: str
    artifact: str
    build_worker_os: str
    external_authority: str | None

TARGETS = {
    "web": PlatformTarget("web", "Web", "site bundle", "any", None),
    "windows": PlatformTarget("windows", "Windows", ".exe / .msix", "windows", "Microsoft Store only if store distribution is chosen"),
    "android": PlatformTarget("android", "Android", ".apk / .aab", "windows/linux/macos", "Google Play only if store distribution is chosen"),
    "ios": PlatformTarget("ios", "iPhone / iPad", ".ipa / archive", "macos", "Apple signing/App Store"),
    "macos": PlatformTarget("macos", "macOS", ".app / pkg", "macos", "Apple signing/notarization"),
}

@dataclass(frozen=True)
class BuildPlan:
    target: str
    possible_on_current_worker: bool
    required_worker_os: str
    artifact: str
    note: str

class PlatformPlanner:
    def plan(self, target: str, worker_os: str) -> BuildPlan:
        t = TARGETS[target]
        possible = t.build_worker_os == "any" or worker_os.lower() in t.build_worker_os.split("/")
        note = "local build available" if possible else f"requires {t.build_worker_os} worker"
        if t.external_authority:
            note += f"; release may require {t.external_authority}"
        return BuildPlan(target, possible, t.build_worker_os, t.artifact, note)
