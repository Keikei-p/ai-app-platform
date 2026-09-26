from __future__ import annotations

import hashlib
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Callable, Protocol

from .backup import BackupManager
from .config import APP_DIR, APP_NAME, STATE_DIR, VERSION
from .database import log_event
from .path_security import is_within

UPDATE_FORMAT = 1
UPDATE_PRODUCT = APP_NAME
MAX_UPDATE_PACKAGE_BYTES = 200 * 1024 * 1024
MAX_UPDATE_TOTAL_BYTES = 512 * 1024 * 1024
MAX_UPDATE_FILE_BYTES = 128 * 1024 * 1024
MAX_UPDATE_FILES = 5000
UPDATE_BACKUP_DIR = STATE_DIR / "update_backups"
UPDATE_STAGE_DIR = STATE_DIR / "update_staging"

ALLOWED_ROOT_FILES = {
    ".gitignore",
    "00_READ_ME_FIRST.txt",
    "BUILD_WINDOWS.bat",
    "CHECK.bat",
    "CHECKSUMS.sha256",
    "DIAGNOSTICS.bat",
    "FILE_MANIFEST.txt",
    "README.md",
    "requirements.txt",
    "SETUP.bat",
    "START.bat",
    "STATUS.md",
    "VERSION",
}
ALLOWED_ROOT_DIRS = {"src", "tests", "docs", "schemas", "locales"}
BLOCKED_PATH_PARTS = {
    "data", "logs", "backups", "workspace", "config", "update_backups", "update_staging",
    ".git", "node_modules", "dist", "build", "__pycache__",
}


@dataclass(frozen=True)
class UpdateFile:
    path: str
    sha256: str
    size: int


@dataclass(frozen=True)
class UpdateCandidate:
    package_path: Path
    package_sha256: str
    version: str
    created_at: str
    files: tuple[UpdateFile, ...]
    delete: tuple[str, ...]
    notes: str


@dataclass(frozen=True)
class UpdateResult:
    ok: bool
    message: str
    from_version: str
    to_version: str | None
    app_backup: str | None = None
    state_backup: str | None = None
    rolled_back: bool = False


class UpdateProvider(Protocol):
    def inspect(self, engine: "UpdateEngine") -> UpdateCandidate:
        ...


class LocalPackageProvider:
    """Local, user-selected package provider used until signed HTTPS updates are enabled."""

    def __init__(self, package_path: str | Path):
        self.package_path = Path(package_path)

    def inspect(self, engine: "UpdateEngine") -> UpdateCandidate:
        return engine.inspect_package(self.package_path)


class HttpsUpdateProvider:
    """Reserved for signed remote updates.

    Remote updates remain intentionally disabled until publisher-signature verification
    is available. HTTPS + SHA-256 alone proves transport/integrity, not publisher identity.
    """

    def __init__(self, index_url: str):
        self.index_url = index_url

    def inspect(self, engine: "UpdateEngine") -> UpdateCandidate:
        raise RuntimeError("remote_updates_disabled_until_signature_verification")


def _version_tuple(value: str) -> tuple[int, ...]:
    parts = value.strip().split(".")
    if not parts or any(not p.isdigit() for p in parts):
        raise ValueError("invalid_version")
    return tuple(int(p) for p in parts)


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _safe_zip_member(info: zipfile.ZipInfo) -> bool:
    name = PurePosixPath(info.filename)
    if not name.parts or name.is_absolute() or ".." in name.parts:
        return False
    mode = (info.external_attr >> 16) & 0o170000
    if mode == stat.S_IFLNK:
        return False
    return True


def _normalize_rel_path(value: str) -> str:
    raw = value.replace("\\", "/").strip("/")
    path = PurePosixPath(raw)
    if not path.parts or path.is_absolute() or ".." in path.parts:
        raise ValueError("unsafe_update_path")
    if any(part in BLOCKED_PATH_PARTS for part in path.parts):
        raise ValueError("blocked_update_path")
    normalized = path.as_posix()
    if len(path.parts) == 1:
        if normalized not in ALLOWED_ROOT_FILES:
            raise ValueError("root_file_not_allowed")
    elif path.parts[0] not in ALLOWED_ROOT_DIRS:
        raise ValueError("root_directory_not_allowed")
    return normalized


class UpdateEngine:
    def __init__(
        self,
        *,
        app_dir: Path | None = None,
        state_dir: Path | None = None,
        current_version: str | None = None,
        validator: Callable[[Path], tuple[bool, str]] | None = None,
        state_backup_callback: Callable[[str], tuple[bool, str]] | None = None,
        audit_callback: Callable[..., None] | None = None,
    ):
        self.app_dir = (app_dir or APP_DIR).resolve()
        self.state_dir = (state_dir or STATE_DIR).resolve()
        self.current_version = current_version or VERSION
        self.validator = validator or self._default_validator
        self.state_backup_callback = state_backup_callback or self._default_state_backup
        self.audit_callback = audit_callback or log_event
        self.update_backup_dir = self.state_dir / "update_backups"
        self.update_stage_dir = self.state_dir / "update_staging"
        self.update_backup_dir.mkdir(parents=True, exist_ok=True)
        self.update_stage_dir.mkdir(parents=True, exist_ok=True)

    def inspect_provider(self, provider: UpdateProvider) -> UpdateCandidate:
        return provider.inspect(self)

    def inspect_package(self, package_path: str | Path) -> UpdateCandidate:
        package = Path(package_path).expanduser().resolve()
        if not package.is_file():
            raise FileNotFoundError("update_package_not_found")
        if package.stat().st_size > MAX_UPDATE_PACKAGE_BYTES:
            raise ValueError("update_package_too_large")
        package_sha = _sha256_file(package)
        with zipfile.ZipFile(package, "r") as z:
            infos = z.infolist()
            if len(infos) > MAX_UPDATE_FILES + 100:
                raise ValueError("too_many_archive_members")
            if any(not _safe_zip_member(info) for info in infos):
                raise ValueError("unsafe_archive_member")
            names = [PurePosixPath(i.filename).as_posix() for i in infos if not i.is_dir()]
            if len(names) != len(set(names)):
                raise ValueError("duplicate_archive_member")
            if "update_manifest.json" not in names:
                raise ValueError("update_manifest_missing")
            manifest = json.loads(z.read("update_manifest.json").decode("utf-8"))

            if manifest.get("format") != UPDATE_FORMAT:
                raise ValueError("unsupported_update_format")
            if manifest.get("product") != UPDATE_PRODUCT:
                raise ValueError("wrong_update_product")
            version = str(manifest.get("version") or "")
            if _version_tuple(version) <= _version_tuple(self.current_version):
                raise ValueError("update_not_newer")
            created_at = str(manifest.get("created_at") or "")
            notes = str(manifest.get("notes") or "")[:4000]

            raw_files = manifest.get("files")
            if not isinstance(raw_files, list) or not raw_files:
                raise ValueError("update_files_missing")
            if len(raw_files) > MAX_UPDATE_FILES:
                raise ValueError("too_many_update_files")
            files: list[UpdateFile] = []
            seen_paths: set[str] = set()
            total_size = 0
            for row in raw_files:
                if not isinstance(row, dict):
                    raise ValueError("invalid_update_file_row")
                rel = _normalize_rel_path(str(row.get("path") or ""))
                if rel in seen_paths:
                    raise ValueError("duplicate_update_path")
                seen_paths.add(rel)
                expected_sha = str(row.get("sha256") or "").lower()
                if len(expected_sha) != 64 or any(c not in "0123456789abcdef" for c in expected_sha):
                    raise ValueError("invalid_file_sha256")
                expected_size = int(row.get("size"))
                if expected_size < 0 or expected_size > MAX_UPDATE_FILE_BYTES:
                    raise ValueError(f"update_file_too_large:{rel}")
                total_size += expected_size
                if total_size > MAX_UPDATE_TOTAL_BYTES:
                    raise ValueError("update_payload_too_large")
                member = f"payload/{rel}"
                if member not in names:
                    raise ValueError(f"payload_missing:{rel}")
                data = z.read(member)
                actual_sha = hashlib.sha256(data).hexdigest()
                if actual_sha != expected_sha:
                    raise ValueError(f"payload_hash_mismatch:{rel}")
                if len(data) != expected_size:
                    raise ValueError(f"payload_size_mismatch:{rel}")
                files.append(UpdateFile(rel, expected_sha, expected_size))

            payload_files = {n.removeprefix("payload/") for n in names if n.startswith("payload/")}
            if payload_files != seen_paths:
                raise ValueError("unexpected_payload_file")

            raw_delete = manifest.get("delete") or []
            if not isinstance(raw_delete, list):
                raise ValueError("invalid_delete_list")
            delete: list[str] = []
            for value in raw_delete:
                rel = _normalize_rel_path(str(value))
                if rel in seen_paths:
                    raise ValueError("path_both_update_and_delete")
                if rel not in delete:
                    delete.append(rel)

        return UpdateCandidate(
            package_path=package,
            package_sha256=package_sha,
            version=version,
            created_at=created_at,
            files=tuple(files),
            delete=tuple(delete),
            notes=notes,
        )

    def _default_state_backup(self, label: str) -> tuple[bool, str]:
        result = BackupManager().create(label)
        return result.ok, result.path if result.ok else (result.error or result.path)

    def _default_validator(self, app_dir: Path) -> tuple[bool, str]:
        if getattr(sys, "frozen", False):
            return False, "frozen_build_update_validation_not_enabled"
        commands = [
            [sys.executable, "-m", "compileall", "-q", "src", "tests"],
            [sys.executable, "-m", "src.tools.security_selfcheck"],
            [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-q"],
            [sys.executable, "-m", "src.tools.acceptance_test"],
            [sys.executable, "-m", "src.tools.remote_acceptance_test"],
            [sys.executable, "-m", "src.tools.smoke_test"],
        ]
        output: list[str] = []
        env = os.environ.copy()
        for command in commands:
            proc = subprocess.run(
                command,
                cwd=app_dir,
                env=env,
                text=True,
                capture_output=True,
                timeout=180,
            )
            output.append((proc.stdout or "")[-2500:])
            output.append((proc.stderr or "")[-1500:])
            if proc.returncode != 0:
                return False, "\n".join(x for x in output if x).strip()[-7000:]
        return True, "\n".join(x for x in output if x).strip()[-7000:]

    def _iter_app_files(self):
        for root_name in ALLOWED_ROOT_DIRS:
            root = self.app_dir / root_name
            if not root.exists():
                continue
            for path in root.rglob("*"):
                if path.is_symlink() or not path.is_file() or not is_within(root, path):
                    continue
                rel_parts = path.relative_to(self.app_dir).parts
                if any(part in BLOCKED_PATH_PARTS for part in rel_parts):
                    continue
                yield path.relative_to(self.app_dir).as_posix(), path
        for filename in ALLOWED_ROOT_FILES:
            path = self.app_dir / filename
            if path.is_file() and not path.is_symlink():
                yield filename, path

    def _create_app_snapshot(self, label: str) -> Path:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S-%f")
        target = self.update_backup_dir / f"app-{stamp}-{label}.zip"
        included: list[str] = []
        with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED) as z:
            for rel, path in self._iter_app_files():
                z.write(path, f"payload/{rel}")
                included.append(rel)
            manifest = {"format": 1, "created_at": datetime.now(timezone.utc).isoformat(), "files": sorted(included)}
            z.writestr("snapshot_manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
        return target

    def _restore_app_snapshot(self, snapshot: Path) -> None:
        with zipfile.ZipFile(snapshot, "r") as z:
            infos = z.infolist()
            if len(infos) > MAX_UPDATE_FILES + 100:
                raise ValueError("too_many_archive_members")
            if any(not _safe_zip_member(info) for info in infos):
                raise ValueError("unsafe_snapshot_member")
            manifest = json.loads(z.read("snapshot_manifest.json").decode("utf-8"))
            listed = [_normalize_rel_path(str(x)) for x in manifest.get("files", [])]

            for root_name in ALLOWED_ROOT_DIRS:
                root = self.app_dir / root_name
                if root.exists():
                    shutil.rmtree(root)
            for filename in ALLOWED_ROOT_FILES:
                path = self.app_dir / filename
                if path.exists():
                    path.unlink()

            for rel in listed:
                member = f"payload/{rel}"
                if member not in z.namelist():
                    raise ValueError("snapshot_file_missing")
                target = self.app_dir / Path(*PurePosixPath(rel).parts)
                if not is_within(self.app_dir, target):
                    raise ValueError("snapshot_path_outside_app")
                target.parent.mkdir(parents=True, exist_ok=True)
                with z.open(member, "r") as src, target.open("wb") as out:
                    shutil.copyfileobj(src, out)

    def _stage(self, candidate: UpdateCandidate) -> Path:
        stage = Path(tempfile.mkdtemp(prefix="update-", dir=self.update_stage_dir))
        with zipfile.ZipFile(candidate.package_path, "r") as z:
            for item in candidate.files:
                member = f"payload/{item.path}"
                target = stage / item.path
                if not is_within(stage, target):
                    raise ValueError("stage_path_outside")
                target.parent.mkdir(parents=True, exist_ok=True)
                data = z.read(member)
                if hashlib.sha256(data).hexdigest() != item.sha256 or len(data) != item.size:
                    raise ValueError("stage_integrity_failed")
                target.write_bytes(data)
        return stage

    def _apply_staged(self, candidate: UpdateCandidate, stage: Path) -> None:
        for rel in candidate.delete:
            target = self.app_dir / Path(*PurePosixPath(rel).parts)
            if not is_within(self.app_dir, target):
                raise ValueError("delete_path_outside_app")
            if target.is_dir():
                shutil.rmtree(target)
            elif target.exists():
                target.unlink()

        for item in candidate.files:
            src = stage / item.path
            target = self.app_dir / Path(*PurePosixPath(item.path).parts)
            if not is_within(self.app_dir, target):
                raise ValueError("apply_path_outside_app")
            target.parent.mkdir(parents=True, exist_ok=True)
            tmp = target.with_name(target.name + ".update-tmp")
            shutil.copy2(src, tmp)
            os.replace(tmp, target)

    def apply(self, candidate: UpdateCandidate) -> UpdateResult:
        # Re-inspect immediately before applying so a package swapped after selection is rejected.
        fresh = self.inspect_package(candidate.package_path)
        if fresh.package_sha256 != candidate.package_sha256 or fresh.version != candidate.version:
            return UpdateResult(False, "更新パッケージが選択後に変更されました。", self.current_version, candidate.version)
        if getattr(sys, "frozen", False):
            return UpdateResult(False, "EXE版の自己更新はまだ有効化していません。START.bat版から更新してください。", self.current_version, candidate.version)

        pre_ok, pre_detail = self.validator(self.app_dir)
        if not pre_ok:
            return UpdateResult(False, "更新前チェックに失敗しました。\n" + pre_detail, self.current_version, candidate.version)

        state_ok, state_backup = self.state_backup_callback("before-update")
        if not state_ok:
            return UpdateResult(False, "ユーザーデータのバックアップに失敗したため更新を中止しました。", self.current_version, candidate.version, state_backup=state_backup)

        app_snapshot: Path | None = None
        stage: Path | None = None
        try:
            app_snapshot = self._create_app_snapshot("before-update")
            stage = self._stage(fresh)
            self._apply_staged(fresh, stage)
            post_ok, post_detail = self.validator(self.app_dir)
            if not post_ok:
                raise RuntimeError("post_update_check_failed\n" + post_detail)
            self.audit_callback(
                "update.applied",
                json.dumps({"from": self.current_version, "to": fresh.version, "package_sha256": fresh.package_sha256}, ensure_ascii=False),
                actor="update-engine",
            )
            return UpdateResult(
                True,
                "更新と自動テストが完了しました。アプリを再起動してください。",
                self.current_version,
                fresh.version,
                str(app_snapshot),
                state_backup,
                False,
            )
        except Exception as exc:
            rolled_back = False
            rollback_error = ""
            if app_snapshot and app_snapshot.exists():
                try:
                    self._restore_app_snapshot(app_snapshot)
                    rolled_back = True
                except Exception as rb_exc:
                    rollback_error = f" / rollback_failed={rb_exc}"
            self.audit_callback(
                "update.failed",
                f"to={candidate.version}; error={exc}; rolled_back={rolled_back}{rollback_error}",
                actor="update-engine",
            )
            return UpdateResult(
                False,
                f"更新に失敗しました。{'元の本体へ戻しました。' if rolled_back else '自動復旧に失敗しました。バックアップを保持しています。'}\n{exc}{rollback_error}",
                self.current_version,
                candidate.version,
                str(app_snapshot) if app_snapshot else None,
                state_backup,
                rolled_back,
            )
        finally:
            if stage:
                shutil.rmtree(stage, ignore_errors=True)


def build_update_package(source_dir: Path, output_path: Path, *, version: str, notes: str = "") -> Path:
    """Build a local update package from an application source tree.

    This is an internal packaging helper. Publisher authenticity is not established by
    this package alone; remote distribution must add signature verification first.
    """
    source_dir = source_dir.resolve()
    files: list[dict] = []
    paths: list[tuple[str, Path]] = []
    for root_name in sorted(ALLOWED_ROOT_DIRS):
        root = source_dir / root_name
        if root.exists():
            for path in sorted(root.rglob("*")):
                if not path.is_file() or path.is_symlink():
                    continue
                rel = path.relative_to(source_dir).as_posix()
                if any(part in BLOCKED_PATH_PARTS for part in PurePosixPath(rel).parts):
                    continue
                _normalize_rel_path(rel)
                paths.append((rel, path))
    for filename in sorted(ALLOWED_ROOT_FILES):
        path = source_dir / filename
        if path.is_file() and not path.is_symlink():
            _normalize_rel_path(filename)
            paths.append((filename, path))

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output_path, "w", compression=zipfile.ZIP_DEFLATED) as z:
        for rel, path in paths:
            data = path.read_bytes()
            sha = hashlib.sha256(data).hexdigest()
            files.append({"path": rel, "sha256": sha, "size": len(data)})
            z.writestr(f"payload/{rel}", data)
        manifest = {
            "format": UPDATE_FORMAT,
            "product": UPDATE_PRODUCT,
            "version": version,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "notes": notes,
            "files": files,
            "delete": [],
        }
        z.writestr("update_manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
    return output_path
