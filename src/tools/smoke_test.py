from __future__ import annotations
import shutil
import sys
import uuid
from pathlib import Path
from src.core.ai_core import AICore
from src.core.project_manager import ProjectManager
from src.core.database import delete_project_record

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

if __name__ == "__main__":
    name = "Smoke Test " + uuid.uuid4().hex[:8]
    pm = ProjectManager()
    slug, path = pm.create(name)
    try:
        result = AICore().execute(name, slug, path, "ログイン付き予約アプリをWebとAndroid向けに作って")
        print(result.message)
        for t in result.tests:
            print(("PASS" if t.passed else "FAIL"), t.name, t.detail)
        raise SystemExit(0 if result.ok else 1)
    finally:
        # Remove smoke-test workspace. DB audit intentionally remains for traceability.
        shutil.rmtree(path, ignore_errors=True)
        delete_project_record(slug)
