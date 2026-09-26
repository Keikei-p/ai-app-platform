from __future__ import annotations
import json
import platform
import sys
from datetime import datetime, timezone
from pathlib import Path
from src.core.config import LOG_DIR, VERSION, DB_PATH, WORKSPACE_DIR
from src.core.environment import diagnose
from src.core.readiness import ReadinessChecker
from src.core.database import list_projects, list_audit

if __name__ == "__main__":
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    out = LOG_DIR / "diagnostics.json"
    readiness = ReadinessChecker().run().to_dict()
    payload = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "version": VERSION,
        "python": sys.version,
        "platform": platform.platform(),
        "environment": diagnose(),
        "readiness": readiness,
        "db_exists": DB_PATH.exists(),
        "workspace_exists": WORKSPACE_DIR.exists(),
        "project_count": len(list_projects()),
        "recent_audit": list_audit(20),
    }
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(out)
