from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any
import hashlib

from .evolution_engine import ROOT_POLICY_PATHS, ROOT_POLICY_PREFIXES


@dataclass(frozen=True)
class RootPolicyDiff:
    intact: bool
    changed_paths: tuple[str, ...]
    missing_in_candidate: tuple[str, ...]
    added_in_candidate: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["changed_paths"] = list(self.changed_paths)
        data["missing_in_candidate"] = list(self.missing_in_candidate)
        data["added_in_candidate"] = list(self.added_in_candidate)
        return data


class RootPolicyGuard:
    """Compare actual protected files between baseline and candidate trees.

    This does not trust a candidate's declared changed-path list. Protected
    policy/CI files are discovered from the filesystem and compared by SHA-256.
    """

    def compare(self, baseline_root: Path, candidate_root: Path) -> RootPolicyDiff:
        baseline_root = Path(baseline_root).resolve()
        candidate_root = Path(candidate_root).resolve()
        baseline = self._protected_files(baseline_root)
        candidate = self._protected_files(candidate_root)

        keys = sorted(set(baseline) | set(candidate))
        changed: list[str] = []
        missing: list[str] = []
        added: list[str] = []

        for rel in keys:
            before = baseline.get(rel)
            after = candidate.get(rel)
            if before is None and after is not None:
                added.append(rel)
                changed.append(rel)
            elif before is not None and after is None:
                missing.append(rel)
                changed.append(rel)
            elif before != after:
                changed.append(rel)

        return RootPolicyDiff(
            intact=not changed,
            changed_paths=tuple(changed),
            missing_in_candidate=tuple(missing),
            added_in_candidate=tuple(added),
        )

    def _protected_files(self, root: Path) -> dict[str, str]:
        rows: dict[str, str] = {}
        for rel in sorted(ROOT_POLICY_PATHS):
            path = root / rel
            if path.is_file() and not path.is_symlink():
                rows[rel] = self._sha256(path)

        for prefix in ROOT_POLICY_PREFIXES:
            folder = root / prefix.rstrip("/")
            if not folder.is_dir():
                continue
            for path in sorted(folder.rglob("*")):
                if not path.is_file() or path.is_symlink():
                    continue
                rel = path.relative_to(root).as_posix()
                rows[rel] = self._sha256(path)
        return rows

    @staticmethod
    def _sha256(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()
