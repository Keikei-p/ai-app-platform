"""Read-only offline growth audit for GitHub-hosted runners.

Does not claim that an AI has modified source code or that physical devices
have passed long-duration tests. Deliberately has no GitHub write operations,
model credentials, network calls or access to the owner's local runtime.
"""
from __future__ import annotations

from hashlib import sha1
from pathlib import Path
from typing import Any
import json

ROOT = Path(__file__).resolve().parents[2]
ATTESTATIONS = (
    "evidence/multi_mission_e2e_ci.json",
    "evidence/cross_mode_e2e_ci.json",
)
CRITICAL_SOURCES = (
    "src/core/mission_control.py",
    "src/core/build_jobs.py",
    "src/core/long_run_soak.py",
)


def blob_sha(data: bytes) -> str:
    return sha1(f"blob {len(data)}\\0".encode("ascii") + data).hexdigest()


def inspect(root: Path = ROOT) -> dict[str, Any]:
    root = root.resolve()
    checks: dict[str, bool] = {}
    issues: list[str] = []

    for rel in CRITICAL_SOURCES:
        present = (root / rel).is_file()
        checks[f"source_present:{rel}"] = present
        if not present:
            issues.append(f"required_source_missing:{rel}")

    for rel in ATTESTATIONS:
        evidence = root / rel
        try:
            raw = json.loads(evidence.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            checks[f"attestation:{rel}"] = False
            issues.append(f"attestation_unreadable:{rel}")
            continue
        blobs = raw.get("source_blobs") if isinstance(raw, dict) else None
        if raw.get("verified") is not True or not isinstance(blobs, dict) or not blobs:
            checks[f"attestation:{rel}"] = False
            issues.append(f"attestation_unverified:{rel}")
            continue
        valid = True
        for source, expected in blobs.items():
            # Prevent arbitrary paths and never read outside this checkout.
            if (
                not isinstance(source, str)
                or not source.startswith("src/")
                or any(part in {"", ".", ".."} for part in Path(source).parts)
                or not isinstance(expected, str)
            ):
                valid = False
                break
            item = (root / source).resolve()
            if not item.is_relative_to(root) or not item.is_file():
                valid = False
                break
            if blob_sha(item.read_bytes().replace(b"\\r\\n", b"\\n")) != expected:
                valid = False
                break
        checks[f"attestation:{rel}"] = valid
        if not valid:
            issues.append(f"attestation_stale_or_invalid:{rel}")

    # The runner has no access to the user's PC or persisted runtime clock.
    # Never manufacture 24-hour, Windows reboot or source-auto-edit evidence.
    return {
        "kind": "ivy_cloud_growth_audit",
        "schema_version": 1,
        "checks": checks,
        "all_source_checks_passed": all(checks.values()),
        "issues": issues,
        "actual_source_changes": False,
        "real_24h_soak_verified": False,
        "physical_pc_reboot_verified": False,
        "buyer_release_approved": False,
        "safe_next_action": (
            "inspect reported checkout or attestation failures"
            if issues else "run selected regression tests and report results"
        ),
    }


def main() -> int:
    report = inspect()
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["all_source_checks_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
