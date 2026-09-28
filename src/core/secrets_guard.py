from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any
import json
import re


SECRET_KEY_NAMES = {
    "api_key", "apikey", "secret", "client_secret", "access_token",
    "refresh_token", "password", "private_key", "credential", "credentials",
}

SECRET_VALUE_PATTERNS = (
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
)


@dataclass(frozen=True)
class SecretAudit:
    passed: bool
    findings: tuple[str, ...]
    protected_storage_detected: bool
    plaintext_secret_fields: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["findings"] = list(self.findings)
        data["plaintext_secret_fields"] = list(self.plaintext_secret_fields)
        return data


class SecretsGuard:
    """Audit secret handling without returning secret values.

    The guard intentionally reports field/path names only. It never exposes the
    credential value it detected.
    """

    MAX_TEXT_BYTES = 1024 * 1024
    TEXT_SUFFIXES = {".json", ".env", ".ini", ".toml", ".yaml", ".yml", ".txt", ".py", ".js", ".ts"}

    def audit_settings(self, settings: dict[str, Any]) -> SecretAudit:
        fields: list[str] = []
        protected = False

        def visit(value: Any, prefix: str = "") -> None:
            nonlocal protected
            if isinstance(value, dict):
                for key, child in value.items():
                    name = str(key)
                    path = f"{prefix}.{name}" if prefix else name
                    lower = name.lower()
                    if lower.endswith("_cipher") and isinstance(child, str) and child.startswith("dpapi:"):
                        protected = True
                    elif lower in SECRET_KEY_NAMES or any(token in lower for token in ("api_key", "secret", "token", "password", "credential")):
                        if isinstance(child, str) and child.strip() and not child.startswith(("dpapi:", "env:", "session:")):
                            fields.append(path)
                    visit(child, path)
            elif isinstance(value, list):
                for index, child in enumerate(value):
                    visit(child, f"{prefix}[{index}]")

        visit(settings)
        findings = tuple(f"plaintext_secret_field:{x}" for x in sorted(set(fields)))
        return SecretAudit(not findings, findings, protected, tuple(sorted(set(fields))))

    def audit_project(self, project_dir: Path) -> SecretAudit:
        root = Path(project_dir).resolve()
        findings: list[str] = []
        for path in sorted(root.rglob("*")):
            if not path.is_file() or path.is_symlink():
                continue
            rel = path.relative_to(root)
            if any(part in {".git", ".aiapp", ".snapshots", ".vault", "node_modules", "__pycache__", "artifacts"} for part in rel.parts):
                continue
            if path.stat().st_size > self.MAX_TEXT_BYTES:
                continue
            if path.name.startswith(".env") or path.suffix.lower() in self.TEXT_SUFFIXES:
                try:
                    text = path.read_text(encoding="utf-8")
                except (OSError, UnicodeDecodeError):
                    continue
                if path.name.startswith(".env") and text.strip():
                    findings.append(f"secret_file_present:{rel.as_posix()}")
                for pattern in SECRET_VALUE_PATTERNS:
                    if pattern.search(text):
                        findings.append(f"secret_value_pattern:{rel.as_posix()}")
                        break
                if path.suffix.lower() in {".json", ".yaml", ".yml", ".toml", ".ini"}:
                    for line in text.splitlines():
                        lower = line.lower()
                        if any(token in lower for token in ("api_key", "client_secret", "access_token", "password")):
                            if "dpapi:" not in lower and "env:" not in lower and "session:" not in lower:
                                findings.append(f"possible_plaintext_secret:{rel.as_posix()}")
                                break
        unique = tuple(sorted(set(findings)))
        return SecretAudit(not unique, unique, False, ())
