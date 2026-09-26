from __future__ import annotations
from pathlib import Path
from src.core.config import LOG_DIR
from src.core.readiness import ReadinessChecker

if __name__ == "__main__":
    out = LOG_DIR / "preflight.json"
    report = ReadinessChecker().write(out)
    print("=== AI App Platform Preflight ===")
    for c in report.checks:
        print(f"[{c.status.upper():8}] {c.key}: {c.detail}")
    print(f"Report: {out}")
    raise SystemExit(0 if report.ready_for_local_mvp else 2)
