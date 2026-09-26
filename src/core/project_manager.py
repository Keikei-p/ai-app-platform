from __future__ import annotations
import json
import re
import shutil
import subprocess
from datetime import datetime
from pathlib import Path
from .config import WORKSPACE_DIR
from .database import upsert_project, log_event
from .path_security import safe_child


def slugify(name: str) -> str:
    value = re.sub(r"[^a-zA-Z0-9_-]+", "-", name.strip().lower()).strip("-")
    value = value[:64].rstrip("-_")
    return value or f"project-{datetime.now().strftime('%Y%m%d%H%M%S')}"

class ProjectManager:
    def create(self, name: str) -> tuple[str, Path]:
        slug = slugify(name)
        base = WORKSPACE_DIR / slug
        suffix = 2
        original = slug
        while base.exists():
            suffix_text = f"-{suffix}"
            slug = f"{original[:64-len(suffix_text)]}{suffix_text}"
            base = WORKSPACE_DIR / slug
            suffix += 1
        base.mkdir(parents=True)
        (base / ".snapshots").mkdir()
        meta = {"name": name, "slug": slug, "created_at": datetime.now().isoformat(), "targets": ["web"]}
        (base / "project.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
        (base / ".gitignore").write_text(
            ".vault/\n.snapshots/\n.env\n.env.*\n*.key\n*.pem\n*.p12\n*.pfx\nnode_modules/\ndist/\nbuild/\n",
            encoding="utf-8",
        )
        self._init_git(base)
        upsert_project(name, slug)
        log_event("project.created", f"Created project {name}", slug)
        # Create the first Code Vault version immediately. Import lazily to avoid
        # coupling project creation to the vault module at import time.
        try:
            from .code_vault import CodeVault
            CodeVault().save(slug, "初期状態", actor="project-manager", reason="project created", kind="initial")
        except Exception as exc:
            log_event("vault.version.save_failed", str(exc), slug, "project-manager")
        return slug, base

    def snapshot(self, slug: str, label: str = "snapshot") -> Path:
        src = safe_child(WORKSPACE_DIR, slug)
        if not src.exists():
            raise FileNotFoundError(slug)
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
        dest = src / ".snapshots" / f"{stamp}-{slugify(label)}"
        dest.mkdir(parents=True)
        for item in src.iterdir():
            if item.name == ".snapshots" or item.name == ".git" or item.is_symlink():
                continue
            target = dest / item.name
            if item.is_dir():
                shutil.copytree(item, target, symlinks=True)
            else:
                shutil.copy2(item, target)
        log_event("project.snapshot", str(dest), slug)
        return dest

    def rename(self, slug: str, new_name: str) -> Path:
        """Rename a project display name without changing its stable slug/folder.

        Keeping the slug stable avoids breaking snapshots, generated files, audit
        references, and future remote-worker references.
        """
        name = new_name.strip()
        if not name:
            raise ValueError("project name is required")
        base = safe_child(WORKSPACE_DIR, slug)
        if not base.exists():
            raise FileNotFoundError(slug)
        meta_path = base / "project.json"
        if meta_path.exists():
            try:
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                meta = {"slug": slug, "created_at": datetime.now().isoformat(), "targets": ["web"]}
        else:
            meta = {"slug": slug, "created_at": datetime.now().isoformat(), "targets": ["web"]}
        old_name = str(meta.get("name") or slug)
        meta["name"] = name
        meta["slug"] = slug
        meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
        upsert_project(name, slug)
        log_event("project.renamed", f"Renamed project {old_name} -> {name}", slug)
        return meta_path

    def _init_git(self, base: Path) -> None:
        if shutil.which("git") is None:
            return
        try:
            subprocess.run(["git", "init"], cwd=base, check=True, capture_output=True, text=True)
        except Exception:
            pass
