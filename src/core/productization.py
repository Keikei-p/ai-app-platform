from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import json
import re
import shutil
import sqlite3
import subprocess
import zipfile

from .config import BACKUP_DIR, DATA_DIR, DB_PATH, LOG_DIR, ROOT_DIR, SETTINGS_PATH
from .connectors import ConnectorManager
from .credential_store import CredentialStore
from .redaction import redact_sensitive
from .secrets_guard import SECRET_VALUE_PATTERNS, SecretsGuard


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class OwnershipProfile:
    product_name: str = "Aivy"
    brand_name: str = "Aivy"
    owner_name: str = ""
    organization_name: str = ""
    license_label: str = "Private / Unconfigured"
    accent_color: str = ""
    logo_path: str = ""
    support_email: str = ""
    support_url: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class OwnershipProfileStore:
    ALLOWED = {
        "product_name", "brand_name", "owner_name", "organization_name",
        "license_label", "accent_color", "logo_path", "support_email", "support_url",
    }

    def __init__(self, path: Path | None = None):
        self.path = Path(path or (DATA_DIR / "ownership.json"))
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def get(self) -> OwnershipProfile:
        if not self.path.is_file():
            return OwnershipProfile()
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(raw, dict):
                return OwnershipProfile()
            values = {
                key: str(raw.get(key) or "")[:2000]
                for key in self.ALLOWED
            }
            return OwnershipProfile(**values)
        except Exception:
            return OwnershipProfile()

    def update(self, values: dict[str, Any]) -> OwnershipProfile:
        current = self.get().to_dict()
        for key, value in values.items():
            if key in self.ALLOWED:
                current[key] = str(value or "").strip()[:2000]
        profile = OwnershipProfile(**current)
        self._write(profile.to_dict())
        return profile

    def _write(self, raw: dict[str, Any]) -> None:
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        tmp.write_text(json.dumps(raw, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(self.path)


class SetupStateStore:
    def __init__(self, path: Path | None = None):
        self.path = Path(path or (DATA_DIR / "setup_state.json"))
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def get(self) -> dict[str, Any]:
        default = {
            "completed": False,
            "ai_choice": "",
            "github_choice": "",
            "cloud_choice": "",
            "updated_at": None,
        }
        if not self.path.is_file():
            return default
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                default.update({
                    key: raw.get(key)
                    for key in default
                    if key in raw
                })
        except Exception:
            pass
        return default

    def update(self, values: dict[str, Any]) -> dict[str, Any]:
        current = self.get()
        for key in ("completed", "ai_choice", "github_choice", "cloud_choice"):
            if key in values:
                current[key] = bool(values[key]) if key == "completed" else str(values[key] or "")[:120]
        current["updated_at"] = _now()
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        tmp.write_text(json.dumps(current, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(self.path)
        return current


class PortableConfigManager:
    """Credential-free settings export/import for a new PC or new owner."""

    SCHEMA_VERSION = 1

    def __init__(
        self,
        *,
        connectors: ConnectorManager,
        ownership: OwnershipProfileStore,
        setup: SetupStateStore,
        settings_path: Path | None = None,
    ):
        self.connectors = connectors
        self.ownership = ownership
        self.setup = setup
        self.settings_path = Path(settings_path or SETTINGS_PATH)

    def export_dict(self, *, for_transfer: bool = False) -> dict[str, Any]:
        settings = self._safe_settings()
        connector_state = self.connectors._read()
        safe_connectors: dict[str, Any] = {}
        for definition in self.connectors.registry.list():
            saved = connector_state.get(definition.connector_id)
            if not isinstance(saved, dict):
                continue
            safe_connectors[definition.connector_id] = {
                "config": self.connectors._safe_config(definition, saved.get("config")),
            }
        ownership = self.ownership.get().to_dict()
        setup = {
            key: value
            for key, value in self.setup.get().items()
            if key != "completed"
        }
        if for_transfer:
            # Preserve generic/OEM presentation, but never carry the seller's
            # personal owner/support identity into a new-owner package.
            ownership = {
                "product_name": ownership.get("product_name") or "Aivy",
                "brand_name": ownership.get("brand_name") or ownership.get("product_name") or "Aivy",
                "owner_name": "",
                "organization_name": "",
                "license_label": "Unconfigured",
                "accent_color": ownership.get("accent_color") or "",
                "logo_path": "",
                "support_email": "",
                "support_url": "",
            }
            setup = {
                "ai_choice": "",
                "github_choice": "",
                "cloud_choice": "",
                "updated_at": None,
            }
        return {
            "schema_version": self.SCHEMA_VERSION,
            "kind": "ivy-config",
            "credentials_included": False,
            "transfer_sanitized": bool(for_transfer),
            "settings": settings,
            "connectors": safe_connectors,
            "ownership": ownership,
            "setup": setup,
            "exported_at": _now(),
        }

    def import_dict(self, raw: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(raw, dict) or raw.get("kind") != "ivy-config":
            raise ValueError("有効なivy-config.jsonではありません")
        if raw.get("credentials_included") is not False:
            raise ValueError("Credentialを含む設定ファイルはImportできません")

        settings = raw.get("settings")
        if isinstance(settings, dict):
            current = self._settings_read()
            for key in ("ai_provider", "ai_model", "ai_routes", "ui", "workspace_preferences"):
                if key in settings:
                    current[key] = settings[key]
            self._settings_write(self._strip_secret_fields(current))

        connector_rows = raw.get("connectors")
        if isinstance(connector_rows, dict):
            for connector_id, row in connector_rows.items():
                try:
                    definition = self.connectors.registry.get(str(connector_id))
                except KeyError:
                    continue
                if isinstance(row, dict):
                    self.connectors.configure(
                        definition.connector_id,
                        config=row.get("config") if isinstance(row.get("config"), dict) else {},
                        credentials={},
                        remember=False,
                    )

        if isinstance(raw.get("ownership"), dict):
            self.ownership.update(raw["ownership"])

        return {
            "imported": True,
            "credentials_imported": False,
            "requires_reauthentication": True,
            "message": "設定をImportしました。外部サービスのCredentialは再接続してください。",
        }

    def _safe_settings(self) -> dict[str, Any]:
        raw = self._settings_read()
        return self._strip_secret_fields({
            key: raw.get(key)
            for key in ("ai_provider", "ai_model", "ai_routes", "ui", "workspace_preferences")
            if key in raw
        })

    @classmethod
    def _strip_secret_fields(cls, value: Any) -> Any:
        if isinstance(value, dict):
            clean = {}
            for key, child in value.items():
                lower = str(key).lower()
                if any(token in lower for token in (
                    "key_cipher", "api_key", "secret", "token", "password",
                    "credential", "private_key", "service_account",
                )):
                    continue
                clean[str(key)] = cls._strip_secret_fields(child)
            return clean
        if isinstance(value, list):
            return [cls._strip_secret_fields(x) for x in value]
        return value

    def _settings_read(self) -> dict[str, Any]:
        if not self.settings_path.is_file():
            return {}
        try:
            raw = json.loads(self.settings_path.read_text(encoding="utf-8"))
            return raw if isinstance(raw, dict) else {}
        except Exception:
            return {}

    def _settings_write(self, raw: dict[str, Any]) -> None:
        self.settings_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.settings_path.with_suffix(self.settings_path.suffix + ".tmp")
        tmp.write_text(json.dumps(raw, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(self.settings_path)


class TransferAuditor:
    """Non-destructive audit for transfer/OEM preparation.

    Findings never include the secret value itself.
    """

    TEXT_SUFFIXES = {
        ".py", ".js", ".ts", ".html", ".css", ".json", ".md", ".txt",
        ".yml", ".yaml", ".toml", ".ini", ".bat", ".ps1", ".vbs",
    }
    EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
    WINDOWS_USER_RE = re.compile(r"(?i)[A-Z]:\\Users\\[^\\\s]+")
    GITHUB_OWNER_RE = re.compile(r"https?://github\.com/([^/\s]+)/")
    FIREBASE_ID_RE = re.compile(r"(?i)(?:firebase|project)[_-]?id\s*[=:]\s*[\x22\x27]?([a-z0-9-]{6,})")
    CF_ACCOUNT_RE = re.compile(r"(?i)account[_-]?id\s*[=:]\s*[\x22\x27]?([a-f0-9]{20,})")

    def __init__(
        self,
        *,
        connectors: ConnectorManager,
        credentials: CredentialStore,
        root_dir: Path | None = None,
        settings_path: Path | None = None,
        log_dir: Path | None = None,
        db_path: Path | None = None,
    ):
        self.connectors = connectors
        self.credentials = credentials
        self.root_dir = Path(root_dir or ROOT_DIR)
        self.settings_path = Path(settings_path or SETTINGS_PATH)
        self.log_dir = Path(log_dir or LOG_DIR)
        self.db_path = Path(db_path or DB_PATH)
        self.secrets = SecretsGuard()

    def run(self) -> dict[str, Any]:
        findings: list[dict[str, Any]] = []

        settings = self._read_json(self.settings_path)
        settings_audit = self.secrets.audit_settings(settings)
        for field in settings_audit.plaintext_secret_fields:
            findings.append(self._finding(
                "danger", "settings_plaintext_secret",
                f"通常設定に秘密情報フィールドが残っています: {field}",
                blocker=True,
            ))

        for row in self.connectors.list_public():
            configured = [
                key for key, status in (row.get("credentials") or {}).items()
                if isinstance(status, dict) and status.get("configured")
            ]
            if configured:
                findings.append(self._finding(
                    "safe", "credential_store_present",
                    f"{row['name']} Credentialは専用Storeに存在します。譲渡Packageには含めません。",
                    blocker=False,
                ))

        current_scan = self._scan_current_tree()
        findings.extend(current_scan)

        log_scan = self._scan_directory(self.log_dir, scope="logs")
        findings.extend(log_scan)

        database_scan = self._scan_sqlite_db(self.db_path)
        findings.extend(database_scan)

        history = self._scan_git_history()
        findings.extend(history["findings"])

        blockers = [x for x in findings if x.get("blocker")]
        warnings = [x for x in findings if x.get("severity") in {"warning", "danger"}]
        return {
            "ready": not blockers,
            "status": "譲渡準備完了" if not blockers else "譲渡準備未完了",
            "findings": findings,
            "blockers": blockers,
            "warning_count": len(warnings),
            "git_history_checked": history["checked"],
            "git_history_included_in_transfer_package": False,
            "credentials_in_transfer_package": False,
            "live_data_modified": False,
            "created_at": _now(),
        }

    def _scan_current_tree(self) -> list[dict[str, Any]]:
        findings: list[dict[str, Any]] = []
        root = self.root_dir.resolve()
        ignored = {".git", ".aivy", "__pycache__", "node_modules", "build", "dist"}
        for path in sorted(root.rglob("*")):
            if not path.is_file() or path.is_symlink():
                continue
            rel = path.relative_to(root)
            if any(part in ignored for part in rel.parts):
                continue
            if path.name == ".env.example":
                continue
            if path.name.startswith(".env"):
                findings.append(self._finding(
                    "danger", "env_file_present",
                    f".env系ファイルが製品ツリーに存在します: {rel.as_posix()}",
                    blocker=True,
                ))
                continue
            if path.suffix.lower() not in self.TEXT_SUFFIXES or path.stat().st_size > 2 * 1024 * 1024:
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue

            if any(pattern.search(text) for pattern in SECRET_VALUE_PATTERNS):
                findings.append(self._finding(
                    "danger", "secret_pattern_in_source",
                    f"秘密情報らしい値を検出しました: {rel.as_posix()}",
                    blocker=True,
                ))

            if self.WINDOWS_USER_RE.search(text):
                findings.append(self._finding(
                    "warning", "personal_path",
                    f"個人Windowsパスの可能性があります: {rel.as_posix()}",
                    blocker=False,
                ))

            emails = self.EMAIL_RE.findall(text)
            if emails and not rel.as_posix().startswith("tests/"):
                findings.append(self._finding(
                    "warning", "email_literal",
                    f"メールアドレス文字列を確認してください: {rel.as_posix()}",
                    blocker=False,
                ))

            owners = {
                owner for owner in self.GITHUB_OWNER_RE.findall(text)
                if owner.lower() not in {
                    "actions", "python", "git-for-windows", "github",
                    "openai", "google", "microsoft",
                }
            }
            if owners:
                findings.append(self._finding(
                    "warning", "github_owner_dependency",
                    f"GitHub所有者に依存するURLがあります: {rel.as_posix()}",
                    blocker=False,
                ))

            if self.FIREBASE_ID_RE.search(text):
                findings.append(self._finding(
                    "warning", "firebase_project_dependency",
                    f"Firebase Project ID依存の可能性があります: {rel.as_posix()}",
                    blocker=False,
                ))
            if self.CF_ACCOUNT_RE.search(text):
                findings.append(self._finding(
                    "warning", "cloudflare_account_dependency",
                    f"Cloudflare Account ID依存の可能性があります: {rel.as_posix()}",
                    blocker=False,
                ))
        return self._dedupe(findings)

    def _scan_directory(self, root: Path, *, scope: str) -> list[dict[str, Any]]:
        if not root.exists():
            return []
        findings: list[dict[str, Any]] = []
        for path in sorted(root.rglob("*")):
            if not path.is_file() or path.is_symlink() or path.stat().st_size > 2 * 1024 * 1024:
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            if any(pattern.search(text) for pattern in SECRET_VALUE_PATTERNS):
                findings.append(self._finding(
                    "danger", f"{scope}_secret_pattern",
                    f"{scope}内にCredentialらしい値があります: {path.name}",
                    blocker=True,
                ))
        return self._dedupe(findings)

    def _scan_sqlite_db(self, path: Path) -> list[dict[str, Any]]:
        """Inspect runtime SQLite text without ever returning stored values.

        Runtime DB is excluded from transfer packages. Findings are warnings so
        the live owner's data is never automatically deleted just to build a
        clean transfer copy.
        """
        if not path.is_file():
            return []
        findings: list[dict[str, Any]] = []
        try:
            connection = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
        except sqlite3.Error:
            return [self._finding(
                "warning", "runtime_db_unchecked",
                "ローカルSQLite履歴を読み取り専用で確認できませんでした。",
                blocker=False,
            )]
        try:
            tables = [
                str(row[0])
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
                ).fetchall()
                if row and row[0]
            ]
            for table in tables[:80]:
                safe_table = table.replace('"', '""')
                try:
                    columns = connection.execute(f'PRAGMA table_info("{safe_table}")').fetchall()
                except sqlite3.Error:
                    continue
                text_columns = [
                    str(row[1])
                    for row in columns
                    if len(row) > 2 and str(row[2] or "").upper() in {"", "TEXT", "VARCHAR", "CHAR", "CLOB", "JSON"}
                ]
                for column in text_columns[:80]:
                    safe_column = column.replace('"', '""')
                    try:
                        rows = connection.execute(
                            f'SELECT "{safe_column}" FROM "{safe_table}" '
                            f'WHERE "{safe_column}" IS NOT NULL LIMIT 500'
                        ).fetchall()
                    except sqlite3.Error:
                        continue
                    secret_hit = False
                    personal_hit = False
                    credential_name_hit = any(
                        token in column.lower()
                        for token in ("token", "secret", "password", "api_key", "credential", "cookie")
                    )
                    for row in rows:
                        value = str(row[0] if row else "")
                        if not value:
                            continue
                        if any(pattern.search(value) for pattern in SECRET_VALUE_PATTERNS):
                            secret_hit = True
                        if self.EMAIL_RE.search(value) or self.WINDOWS_USER_RE.search(value):
                            personal_hit = True
                        if secret_hit and personal_hit:
                            break
                    if secret_hit or credential_name_hit:
                        findings.append(self._finding(
                            "warning", "runtime_db_credential_data",
                            f"ライブSQLiteにCredential関連データの可能性があります: {table}.{column}。譲渡PackageにはDBを含めません。",
                            blocker=False,
                        ))
                    if personal_hit:
                        findings.append(self._finding(
                            "warning", "runtime_db_personal_data",
                            f"ライブSQLiteに個人情報の可能性があります: {table}.{column}。譲渡PackageにはDBを含めません。",
                            blocker=False,
                        ))
        finally:
            connection.close()
        return self._dedupe(findings)

    def _scan_git_history(self) -> dict[str, Any]:
        git_dir = self.root_dir / ".git"
        if not git_dir.exists() or not shutil.which("git"):
            return {
                "checked": False,
                "findings": [self._finding(
                    "warning", "git_history_unchecked",
                    "Git履歴はこの環境で確認できませんでした。",
                    blocker=False,
                )],
            }
        try:
            proc = subprocess.run(
                ["git", "-C", str(self.root_dir), "log", "--all", "-p", "--no-color"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=30,
                check=False,
            )
            text = proc.stdout[:25 * 1024 * 1024]
        except Exception:
            return {
                "checked": False,
                "findings": [self._finding(
                    "warning", "git_history_unchecked",
                    "Git履歴スキャンを完了できませんでした。",
                    blocker=False,
                )],
            }

        findings: list[dict[str, Any]] = []
        if any(pattern.search(text) for pattern in SECRET_VALUE_PATTERNS):
            findings.append(self._finding(
                "warning", "git_history_secret_pattern",
                "Git履歴にCredentialらしい値が残っている可能性があります。.gitは譲渡Packageへ含めません。履歴ごと譲渡する場合は別途履歴洗浄が必要です。",
                blocker=False,
            ))
        if self.WINDOWS_USER_RE.search(text):
            findings.append(self._finding(
                "warning", "git_history_personal_path",
                "Git履歴に個人Windowsパスの可能性があります。譲渡Packageには.gitを含めません。",
                blocker=False,
            ))
        if "github.com/Keikei-p/" in text:
            findings.append(self._finding(
                "warning", "git_history_developer_repo",
                "Git履歴に開発者リポジトリ参照があります。譲渡Packageには.gitを含めません。",
                blocker=False,
            ))
        return {"checked": True, "findings": findings}

    @staticmethod
    def _finding(severity: str, code: str, message: str, *, blocker: bool) -> dict[str, Any]:
        return {
            "severity": severity,
            "code": code,
            "message": redact_sensitive(message),
            "blocker": bool(blocker),
        }

    @staticmethod
    def _dedupe(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        unique: dict[tuple[str, str], dict[str, Any]] = {}
        for row in rows:
            unique[(str(row.get("code")), str(row.get("message")))] = row
        return list(unique.values())

    @staticmethod
    def _read_json(path: Path) -> dict[str, Any]:
        if not path.is_file():
            return {}
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            return raw if isinstance(raw, dict) else {}
        except Exception:
            return {}


class TransferPackageBuilder:
    """Create a separate owner-clean package without mutating the live Ivy."""

    EXCLUDED_TOP = {
        ".git", ".aivy", "data", "logs", "backups", "workspace",
        "build", "dist", "__pycache__",
    }
    EXCLUDED_SUFFIXES = {".db", ".sqlite", ".sqlite3", ".pem", ".key", ".p12", ".pfx", ".jks", ".keystore"}

    def __init__(
        self,
        *,
        auditor: TransferAuditor,
        portable_config: PortableConfigManager,
        root_dir: Path | None = None,
        backup_dir: Path | None = None,
    ):
        self.auditor = auditor
        self.portable_config = portable_config
        self.root_dir = Path(root_dir or ROOT_DIR)
        self.backup_dir = Path(backup_dir or BACKUP_DIR)

    def create(self, *, approved: bool) -> dict[str, Any]:
        if not approved:
            raise PermissionError("譲渡用Package作成には明示的な確認が必要です")
        audit = self.auditor.run()
        if not audit.get("ready"):
            return {
                "created": False,
                "status": "譲渡準備未完了",
                "audit": audit,
            }

        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        backup = self.backup_dir / f"transfer-prep-{stamp}"
        backup.mkdir(parents=True, exist_ok=True)
        (backup / "ivy-config.json").write_text(
            json.dumps(self.portable_config.export_dict(for_transfer=True), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        (backup / "transfer-audit.json").write_text(
            json.dumps(audit, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        output = self.backup_dir / f"ivy-transfer-{stamp}.zip"
        with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for path in sorted(self.root_dir.rglob("*")):
                if not path.is_file() or path.is_symlink():
                    continue
                rel = path.relative_to(self.root_dir)
                if not rel.parts or rel.parts[0] in self.EXCLUDED_TOP:
                    continue
                if path.name.startswith(".env") and path.name != ".env.example":
                    continue
                if path.suffix.lower() in self.EXCLUDED_SUFFIXES:
                    continue
                if path.name.startswith(("credentials", "secrets")) and path.suffix.lower() == ".json":
                    continue
                archive.write(path, rel.as_posix())

            archive.writestr(
                "ivy-config.json",
                json.dumps(self.portable_config.export_dict(for_transfer=True), ensure_ascii=False, indent=2),
            )
            archive.writestr(
                "TRANSFER_READY.json",
                json.dumps({
                    "credentials_included": False,
                    "git_history_included": False,
                    "runtime_user_data_included": False,
                    "new_owner_must_run_setup": True,
                    "created_at": _now(),
                }, ensure_ascii=False, indent=2),
            )

        return {
            "created": True,
            "status": "譲渡用Ivyを作成しました",
            "path": str(output),
            "backup_path": str(backup),
            "credentials_included": False,
            "live_data_modified": False,
            "audit": audit,
        }
