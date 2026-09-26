from __future__ import annotations
import json
import shutil
import stat
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from .config import STATE_DIR, DATA_DIR, WORKSPACE_DIR, BACKUP_DIR
from .database import log_event
from .path_security import is_within

@dataclass(frozen=True)
class BackupResult:
    ok: bool
    path: str
    created_at: str
    included: list[str]
    error: str | None = None

class BackupManager:
    """Local safety backup. Skips symlinks and rejects unsafe archive paths."""
    def create(self, label: str = "manual") -> BackupResult:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        safe_label = "".join(c if c.isalnum() or c in "-_" else "-" for c in label)[:40] or "backup"
        dest = BACKUP_DIR / f"ai-app-platform-{stamp}-{safe_label}.zip"
        included: list[str] = []
        try:
            with zipfile.ZipFile(dest, "w", compression=zipfile.ZIP_DEFLATED) as z:
                for root, logical in ((DATA_DIR, "data"), (WORKSPACE_DIR, "workspace")):
                    if not root.exists():
                        continue
                    for path in root.rglob("*"):
                        if path.is_symlink() or not path.is_file() or not is_within(root, path):
                            continue
                        rel_parts = path.relative_to(root).parts
                        if ".git" in rel_parts or ".snapshots" in rel_parts:
                            continue
                        arc = Path(logical) / path.relative_to(root)
                        z.write(path, arc.as_posix())
                        included.append(arc.as_posix())
                manifest = {
                    "created_at": datetime.now(timezone.utc).isoformat(),
                    "label": safe_label,
                    "included_count": len(included),
                    "format": 2,
                }
                z.writestr("backup_manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
            log_event("backup.created", json.dumps({"path": str(dest), "count": len(included)}, ensure_ascii=False), actor="backup-manager")
            return BackupResult(True, str(dest), manifest["created_at"], included)
        except Exception as exc:
            return BackupResult(False, str(dest), datetime.now(timezone.utc).isoformat(), included, str(exc))

    def latest(self) -> Path | None:
        rows = sorted(BACKUP_DIR.glob("ai-app-platform-*.zip"), key=lambda p: p.stat().st_mtime, reverse=True)
        return rows[0] if rows else None

    @staticmethod
    def _safe_member(info: zipfile.ZipInfo) -> bool:
        name = PurePosixPath(info.filename)
        if name.is_absolute() or ".." in name.parts:
            return False
        mode = (info.external_attr >> 16) & 0o170000
        if mode == stat.S_IFLNK:
            return False
        return bool(name.parts)

    def validate(self, backup_path: Path) -> tuple[bool, str]:
        try:
            with zipfile.ZipFile(backup_path, "r") as z:
                infos = z.infolist()
                names = {i.filename for i in infos}
                if "backup_manifest.json" not in names:
                    return False, "backup_manifest.json missing"
                if any(not self._safe_member(i) for i in infos):
                    return False, "unsafe archive member"
                bad = z.testzip()
                if bad:
                    return False, f"corrupt entry: {bad}"
            return True, "valid"
        except Exception as exc:
            return False, str(exc)

    def _extract_safe(self, archive: Path, dest: Path) -> None:
        with zipfile.ZipFile(archive, "r") as z:
            for info in z.infolist():
                if not self._safe_member(info):
                    raise ValueError("unsafe archive member")
                rel = Path(*PurePosixPath(info.filename).parts)
                target = dest / rel
                if not is_within(dest, target):
                    raise ValueError("archive path escapes restore directory")
                if info.is_dir():
                    target.mkdir(parents=True, exist_ok=True)
                    continue
                target.parent.mkdir(parents=True, exist_ok=True)
                with z.open(info, "r") as src, target.open("wb") as out:
                    shutil.copyfileobj(src, out)

    def restore(self, backup_path: Path, *, confirmed: bool = False) -> BackupResult:
        if not confirmed:
            return BackupResult(False, str(backup_path), datetime.now(timezone.utc).isoformat(), [], "explicit confirmation required")
        valid, reason = self.validate(backup_path)
        if not valid:
            return BackupResult(False, str(backup_path), datetime.now(timezone.utc).isoformat(), [], reason)
        safety = self.create("before-restore")
        if not safety.ok:
            return BackupResult(False, str(backup_path), datetime.now(timezone.utc).isoformat(), [], "pre-restore backup failed")
        try:
            temp = STATE_DIR / ".restore-temp"
            if temp.exists():
                shutil.rmtree(temp)
            temp.mkdir()
            self._extract_safe(backup_path, temp)
            for logical, target in (("data", DATA_DIR), ("workspace", WORKSPACE_DIR)):
                src = temp / logical
                if not src.exists():
                    continue
                if target.exists():
                    shutil.rmtree(target)
                shutil.copytree(src, target)
            shutil.rmtree(temp, ignore_errors=True)
            log_event("backup.restored", str(backup_path), actor="backup-manager")
            return BackupResult(True, str(backup_path), datetime.now(timezone.utc).isoformat(), ["data", "workspace"])
        except Exception as exc:
            return BackupResult(False, str(backup_path), datetime.now(timezone.utc).isoformat(), [], str(exc))
