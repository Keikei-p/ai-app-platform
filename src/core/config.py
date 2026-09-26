from __future__ import annotations
import os
import shutil
from pathlib import Path

APP_NAME = "AI App Platform"
VERSION = "0.5.0"
APP_DIR = Path(__file__).resolve().parents[2]


def _state_dir() -> Path:
    override = os.environ.get("AI_APP_PLATFORM_STATE_DIR")
    if override:
        return Path(override).expanduser()
    if os.name == "nt":
        base = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA") or str(Path.home())
        return Path(base) / "AI-App-Platform"
    if sys_platform := os.environ.get("OSTYPE", ""):
        _ = sys_platform  # keep environment access harmless for frozen builds
    if Path.home().joinpath("Library", "Application Support").exists():
        return Path.home() / "Library" / "Application Support" / "AI-App-Platform"
    base = os.environ.get("XDG_DATA_HOME")
    return (Path(base) if base else Path.home() / ".local" / "share") / "AI-App-Platform"


STATE_DIR = _state_dir()
ROOT_DIR = APP_DIR
DATA_DIR = STATE_DIR / "data"
WORKSPACE_DIR = STATE_DIR / "workspace"
BACKUP_DIR = STATE_DIR / "backups"
LOG_DIR = STATE_DIR / "logs"
CONFIG_DIR = STATE_DIR / "config"
DB_PATH = DATA_DIR / "platform.db"
PROFILES_PATH = DATA_DIR / "cloud_profiles.json"
SETTINGS_PATH = DATA_DIR / "settings.json"

for directory in (DATA_DIR, WORKSPACE_DIR, BACKUP_DIR, LOG_DIR, CONFIG_DIR):
    directory.mkdir(parents=True, exist_ok=True)


def _migrate_legacy_local_state() -> None:
    """One-time safe migration from v0.4.2 project-local storage to persistent user storage.

    Migration only runs when the persistent workspace has no projects yet, so existing
    user data is never overwritten.
    """
    if STATE_DIR.resolve() == APP_DIR.resolve():
        return
    legacy_workspace = APP_DIR / "workspace"
    legacy_data = APP_DIR / "data"
    if not legacy_workspace.exists():
        return
    legacy_projects = [p for p in legacy_workspace.iterdir() if p.is_dir() and not p.name.startswith(".")]
    for src in legacy_projects:
        dst = WORKSPACE_DIR / src.name
        if not dst.exists():
            shutil.copytree(src, dst)
    legacy_db = legacy_data / "platform.db"
    if legacy_db.exists() and not DB_PATH.exists():
        shutil.copy2(legacy_db, DB_PATH)
    for filename in ("cloud_profiles.json", "settings.json"):
        src = legacy_data / filename
        dst = DATA_DIR / filename
        if src.exists() and not dst.exists():
            shutil.copy2(src, dst)


_migrate_legacy_local_state()
