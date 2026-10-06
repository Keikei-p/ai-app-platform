from __future__ import annotations
import re

# Best-effort log redaction. Secrets must still be kept out of prompts/logs by design.
_KEY_VALUE = re.compile(r"(?i)\b(api[_-]?key|access[_-]?token|refresh[_-]?token|token|secret|password|authorization)\b\s*([:=])\s*([^\s,;]+)")
_BEARER = re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]{8,}")
_JWT = re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b")
_PRIVATE_KEY = re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----", re.S)
_OPENAI_KEY = re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b")
_GITHUB_KEY = re.compile(r"\b(?:github_pat_[A-Za-z0-9_]{20,}|gh[pousr]_[A-Za-z0-9]{20,})\b")
_GOOGLE_KEY = re.compile(r"\bAIza[A-Za-z0-9_-]{30,}\b")
_AWS_ACCESS_KEY = re.compile(r"\bAKIA[A-Z0-9]{16}\b")


def redact_sensitive(value: str) -> str:
    if not isinstance(value, str):
        value = str(value)
    value = _PRIVATE_KEY.sub("[REDACTED_PRIVATE_KEY]", value)
    value = _BEARER.sub("Bearer [REDACTED]", value)
    value = _JWT.sub("[REDACTED_JWT]", value)
    value = _OPENAI_KEY.sub("[REDACTED_OPENAI_KEY]", value)
    value = _GITHUB_KEY.sub("[REDACTED_GITHUB_TOKEN]", value)
    value = _GOOGLE_KEY.sub("[REDACTED_GOOGLE_KEY]", value)
    value = _AWS_ACCESS_KEY.sub("[REDACTED_AWS_KEY]", value)
    value = _KEY_VALUE.sub(lambda m: f"{m.group(1)}{m.group(2)}[REDACTED]", value)
    return value
