from __future__ import annotations
import re
from pathlib import Path

SAFE_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")


def is_safe_slug(slug: str) -> bool:
    return bool(isinstance(slug, str) and SAFE_SLUG_RE.fullmatch(slug))


def safe_child(root: Path, name: str) -> Path:
    """Return a child path only when name is a platform-safe project slug."""
    if not is_safe_slug(name):
        raise ValueError("invalid_project_slug")
    root_resolved = root.resolve()
    candidate = (root_resolved / name).resolve()
    try:
        candidate.relative_to(root_resolved)
    except ValueError as exc:
        raise ValueError("path_outside_workspace") from exc
    return candidate


def is_within(root: Path, path: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except (ValueError, OSError):
        return False
