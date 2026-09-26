from __future__ import annotations
import json
import os
import platform
import sqlite3
import sys
from dataclasses import dataclass, asdict
from pathlib import Path
from .config import ROOT_DIR, DATA_DIR, WORKSPACE_DIR, DB_PATH, VERSION
from .database import init_db
from .environment import diagnose

@dataclass(frozen=True)
class Check:
    key: str
    ok: bool
    status: str
    detail: str

@dataclass(frozen=True)
class ReadinessReport:
    version: str
    ready_for_local_mvp: bool
    checks: list[Check]

    def to_dict(self) -> dict:
        return {"version": self.version, "ready_for_local_mvp": self.ready_for_local_mvp, "checks": [asdict(c) for c in self.checks]}

class ReadinessChecker:
    def run(self) -> ReadinessReport:
        checks: list[Check] = []
        py_ok = sys.version_info >= (3, 11)
        checks.append(Check("python", py_ok, "pass" if py_ok else "fail", sys.version.split()[0]))
        checks.append(Check("os", True, "info", f"{platform.system()} {platform.release()}"))
        for key, path in (("data_dir", DATA_DIR), ("workspace_dir", WORKSPACE_DIR)):
            try:
                path.mkdir(parents=True, exist_ok=True)
                probe = path / ".write-test"
                probe.write_text("ok", encoding="utf-8")
                probe.unlink()
                checks.append(Check(key, True, "pass", str(path)))
            except Exception as exc:
                checks.append(Check(key, False, "fail", str(exc)))
        try:
            init_db()
            conn = sqlite3.connect(DB_PATH)
            try:
                conn.execute("SELECT 1").fetchone()
            finally:
                conn.close()
            checks.append(Check("sqlite", True, "pass", str(DB_PATH)))
        except Exception as exc:
            checks.append(Check("sqlite", False, "fail", str(exc)))
        env = diagnose()
        for optional in ("git", "node", "npm"):
            val = env.get(optional, "未検出")
            checks.append(Check(optional, val != "未検出", "pass" if val != "未検出" else "optional", val))
        # Tkinter is required for desktop GUI, but core CLI can still run without it.
        try:
            import tkinter  # noqa: F401
            checks.append(Check("tkinter", True, "pass", "available"))
        except Exception as exc:
            checks.append(Check("tkinter", False, "fail", str(exc)))
        critical = {"python", "data_dir", "workspace_dir", "sqlite", "tkinter"}
        ready = all(c.ok for c in checks if c.key in critical)
        return ReadinessReport(VERSION, ready, checks)

    def write(self, path: Path) -> ReadinessReport:
        report = self.run()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(report.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
        return report
