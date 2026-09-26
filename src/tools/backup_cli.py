from __future__ import annotations
from src.core.backup import BackupManager

if __name__ == "__main__":
    r = BackupManager().create("manual")
    print("OK" if r.ok else "FAILED", r.path)
    if r.error:
        print(r.error)
    raise SystemExit(0 if r.ok else 1)
