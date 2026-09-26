from __future__ import annotations

import difflib
import hashlib
import json
import re
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from .config import WORKSPACE_DIR
from .database import log_event, upsert_project
from .path_security import is_within, safe_child
from .redaction import redact_sensitive

_VERSION_RE = re.compile(r"^[0-9]{8}T[0-9]{6}Z-[a-f0-9]{8}$")
_EXCLUDED_DIRS = {".vault", ".snapshots", ".git", "node_modules", "dist", "build", ".venv", "venv", "__pycache__"}
_EXCLUDED_NAMES = {".env", "credentials.json", "service-account.json"}
_EXCLUDED_SUFFIXES = {".pem", ".key", ".p12", ".pfx"}
_TEXT_SUFFIXES = {
    ".txt", ".md", ".json", ".toml", ".yaml", ".yml", ".ini", ".cfg", ".conf",
    ".py", ".js", ".jsx", ".ts", ".tsx", ".html", ".htm", ".css", ".scss", ".xml",
    ".sql", ".sh", ".bat", ".cmd", ".ps1", ".java", ".kt", ".swift", ".dart", ".go", ".rs",
}
_MAX_DIFF_FILE_BYTES = 512_000


@dataclass(frozen=True)
class VaultVersion:
    version_id: str
    created_at: str
    label: str
    actor: str
    reason: str
    kind: str
    file_count: int
    total_bytes: int
    warnings: list[str]


@dataclass(frozen=True)
class VaultDiff:
    added: list[str]
    removed: list[str]
    modified: list[str]
    unchanged: int
    unified_diff: str


class CodeVault:
    """Project-local version vault.

    The vault deliberately stores project source snapshots, not secrets or dependency/build folders.
    Users see simple save/history/restore language while the implementation keeps immutable versions.
    """

    def _project_dir(self, slug: str) -> Path:
        project = safe_child(WORKSPACE_DIR, slug)
        if not project.is_dir():
            raise FileNotFoundError(slug)
        return project

    def _vault_dir(self, slug: str) -> Path:
        root = self._project_dir(slug) / ".vault"
        (root / "versions").mkdir(parents=True, exist_ok=True)
        return root

    @staticmethod
    def _should_skip(path: Path, project_root: Path) -> bool:
        rel = path.relative_to(project_root)
        if any(part in _EXCLUDED_DIRS for part in rel.parts[:-1]):
            return True
        name = path.name.lower()
        if name in _EXCLUDED_NAMES or name.startswith(".env."):
            return True
        if path.suffix.lower() in _EXCLUDED_SUFFIXES:
            return True
        return False

    @staticmethod
    def _sha256(path: Path) -> str:
        h = hashlib.sha256()
        with path.open("rb") as f:
            for block in iter(lambda: f.read(1024 * 1024), b""):
                h.update(block)
        return h.hexdigest()

    def _scan(self, project_root: Path) -> tuple[dict[str, dict], list[str]]:
        files: dict[str, dict] = {}
        warnings: list[str] = []
        for path in sorted(project_root.rglob("*")):
            if path.is_symlink():
                warnings.append(f"symlink skipped: {path.relative_to(project_root).as_posix()}")
                continue
            if not path.is_file() or not is_within(project_root, path):
                continue
            if self._should_skip(path, project_root):
                continue
            rel = path.relative_to(project_root).as_posix()
            size = path.stat().st_size
            files[rel] = {"sha256": self._sha256(path), "size": size}
        return files, warnings

    @staticmethod
    def _make_version_id() -> str:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        token = hashlib.sha256(f"{stamp}-{datetime.now(timezone.utc).timestamp()}".encode()).hexdigest()[:8]
        return f"{stamp}-{token}"

    def save(
        self,
        slug: str,
        label: str = "保存",
        *,
        actor: str = "local-user",
        reason: str = "",
        kind: str = "manual",
    ) -> VaultVersion:
        project = self._project_dir(slug)
        vault = self._vault_dir(slug)
        version_id = self._make_version_id()
        version_dir = vault / "versions" / version_id
        while version_dir.exists():
            version_id = self._make_version_id()
            version_dir = vault / "versions" / version_id
        content_dir = version_dir / "content"
        content_dir.mkdir(parents=True, exist_ok=False)

        files, warnings = self._scan(project)
        total_bytes = 0
        for rel, info in files.items():
            src = project / Path(rel)
            dst = content_dir / Path(rel)
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst, follow_symlinks=False)
            total_bytes += int(info["size"])

        meta = {
            "version_id": version_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "label": (label or "保存")[:80],
            "actor": (actor or "local-user")[:80],
            "reason": redact_sensitive(reason)[:1000],
            "kind": (kind or "manual")[:40],
            "file_count": len(files),
            "total_bytes": total_bytes,
            "warnings": warnings,
            "files": files,
            "format": 1,
        }
        (version_dir / "metadata.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
        log_event(
            "vault.version.saved",
            json.dumps({k: meta[k] for k in ("version_id", "label", "actor", "reason", "kind", "file_count", "warnings")}, ensure_ascii=False),
            slug,
            actor,
        )
        return self._to_version(meta)

    @staticmethod
    def _to_version(meta: dict) -> VaultVersion:
        return VaultVersion(
            version_id=str(meta["version_id"]),
            created_at=str(meta["created_at"]),
            label=str(meta.get("label") or "保存"),
            actor=str(meta.get("actor") or "unknown"),
            reason=str(meta.get("reason") or ""),
            kind=str(meta.get("kind") or "manual"),
            file_count=int(meta.get("file_count") or 0),
            total_bytes=int(meta.get("total_bytes") or 0),
            warnings=list(meta.get("warnings") or []),
        )

    def _version_dir(self, slug: str, version_id: str) -> Path:
        if not _VERSION_RE.fullmatch(version_id):
            raise ValueError("invalid_vault_version")
        base = self._vault_dir(slug) / "versions"
        candidate = (base / version_id).resolve()
        try:
            candidate.relative_to(base.resolve())
        except ValueError as exc:
            raise ValueError("vault_path_escape") from exc
        if not candidate.is_dir():
            raise FileNotFoundError(version_id)
        return candidate

    def _metadata(self, slug: str, version_id: str) -> dict:
        path = self._version_dir(slug, version_id) / "metadata.json"
        raw = json.loads(path.read_text(encoding="utf-8"))
        if raw.get("version_id") != version_id or not isinstance(raw.get("files"), dict):
            raise ValueError("invalid_vault_metadata")
        return raw

    def list_versions(self, slug: str) -> list[VaultVersion]:
        vault = self._vault_dir(slug) / "versions"
        rows: list[VaultVersion] = []
        for item in vault.iterdir():
            if not item.is_dir() or not _VERSION_RE.fullmatch(item.name):
                continue
            try:
                rows.append(self._to_version(self._metadata(slug, item.name)))
            except (OSError, ValueError, json.JSONDecodeError):
                continue
        rows.sort(key=lambda x: x.created_at, reverse=True)
        return rows

    def diff(self, slug: str, version_id: str) -> VaultDiff:
        project = self._project_dir(slug)
        meta = self._metadata(slug, version_id)
        old_files = meta["files"]
        current_files, _ = self._scan(project)
        old_names = set(old_files)
        new_names = set(current_files)
        added = sorted(new_names - old_names)
        removed = sorted(old_names - new_names)
        modified = sorted(name for name in old_names & new_names if old_files[name]["sha256"] != current_files[name]["sha256"])
        unchanged = sum(1 for name in old_names & new_names if old_files[name]["sha256"] == current_files[name]["sha256"])

        lines: list[str] = []
        version_content = self._version_dir(slug, version_id) / "content"
        for name in modified:
            suffix = Path(name).suffix.lower()
            old_path = version_content / Path(name)
            new_path = project / Path(name)
            if suffix not in _TEXT_SUFFIXES or old_path.stat().st_size > _MAX_DIFF_FILE_BYTES or new_path.stat().st_size > _MAX_DIFF_FILE_BYTES:
                lines.append(f"--- {name}\n+++ {name}\n(binary/large file changed)\n")
                continue
            try:
                before = old_path.read_text(encoding="utf-8").splitlines(keepends=True)
                after = new_path.read_text(encoding="utf-8").splitlines(keepends=True)
            except UnicodeDecodeError:
                lines.append(f"--- {name}\n+++ {name}\n(non-UTF-8 file changed)\n")
                continue
            lines.extend(difflib.unified_diff(before, after, fromfile=f"saved/{name}", tofile=f"current/{name}", n=3))
            if lines and not lines[-1].endswith("\n"):
                lines[-1] += "\n"
        return VaultDiff(added, removed, modified, unchanged, "".join(lines))

    def validate_version(self, slug: str, version_id: str) -> tuple[bool, str]:
        try:
            meta = self._metadata(slug, version_id)
            content = self._version_dir(slug, version_id) / "content"
            expected = meta.get("files") or {}
            seen: set[str] = set()
            for path in content.rglob("*"):
                if path.is_symlink():
                    return False, "symlink found in version"
                if not path.is_file():
                    continue
                if not is_within(content, path):
                    return False, "version path escapes content"
                rel = path.relative_to(content).as_posix()
                seen.add(rel)
                row = expected.get(rel)
                if not isinstance(row, dict):
                    return False, f"unexpected file: {rel}"
                if path.stat().st_size != int(row.get("size", -1)):
                    return False, f"size mismatch: {rel}"
                if self._sha256(path) != row.get("sha256"):
                    return False, f"hash mismatch: {rel}"
            if seen != set(expected):
                missing = sorted(set(expected) - seen)
                return False, f"missing files: {', '.join(missing[:5])}"
            return True, "valid"
        except Exception as exc:
            return False, str(exc)

    def _replace_project_contents(self, project: Path, content: Path) -> None:
        stage = project / ".vault" / ".restore-stage"
        if stage.exists():
            shutil.rmtree(stage)
        stage.mkdir(parents=True, exist_ok=False)
        try:
            for src in sorted(content.rglob("*")):
                if src.is_symlink() or not is_within(content, src):
                    raise ValueError("unsafe_vault_content")
                rel = src.relative_to(content)
                dst = stage / rel
                if not is_within(stage, dst):
                    raise ValueError("restore_stage_path_escape")
                if src.is_dir():
                    dst.mkdir(parents=True, exist_ok=True)
                elif src.is_file():
                    dst.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(src, dst, follow_symlinks=False)

            for item in list(project.iterdir()):
                if item.name in {".vault", ".snapshots", ".git"}:
                    continue
                if item.is_symlink():
                    item.unlink(missing_ok=True)
                elif item.is_dir():
                    shutil.rmtree(item)
                else:
                    item.unlink(missing_ok=True)

            for src in sorted(stage.rglob("*")):
                rel = src.relative_to(stage)
                dst = project / rel
                if not is_within(project, dst):
                    raise ValueError("restore_path_escape")
                if src.is_dir():
                    dst.mkdir(parents=True, exist_ok=True)
                elif src.is_file():
                    dst.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(src, dst, follow_symlinks=False)
        finally:
            shutil.rmtree(stage, ignore_errors=True)

    def restore(self, slug: str, version_id: str, *, confirmed: bool = False, actor: str = "local-user") -> VaultVersion:
        if not confirmed:
            raise PermissionError("explicit confirmation required")
        project = self._project_dir(slug)
        valid, reason = self.validate_version(slug, version_id)
        if not valid:
            raise ValueError(f"invalid vault version: {reason}")
        meta = self._metadata(slug, version_id)
        version_dir = self._version_dir(slug, version_id)
        content = version_dir / "content"

        # The current state is always saved first so restore is reversible.
        safety = self.save(slug, "復元前の自動保存", actor=actor, reason=f"restore target={version_id}", kind="pre-restore")

        try:
            self._replace_project_contents(project, content)
        except Exception:
            # Best-effort automatic rollback to the pre-restore safety version.
            try:
                rollback_dir = self._version_dir(slug, safety.version_id) / "content"
                self._replace_project_contents(project, rollback_dir)
                log_event("vault.restore.auto_rollback", safety.version_id, slug, "code-vault")
            except Exception as rollback_exc:
                log_event("vault.restore.auto_rollback_failed", str(rollback_exc), slug, "code-vault")
            raise

        meta_path = project / "project.json"
        if meta_path.exists():
            try:
                project_meta = json.loads(meta_path.read_text(encoding="utf-8"))
                name = str(project_meta.get("name") or slug).strip()
                if name:
                    upsert_project(name, slug)
            except (OSError, ValueError, TypeError, json.JSONDecodeError):
                pass
        log_event(
            "vault.version.restored",
            json.dumps({"restored_version": version_id, "pre_restore_version": safety.version_id}, ensure_ascii=False),
            slug,
            actor,
        )
        return safety
