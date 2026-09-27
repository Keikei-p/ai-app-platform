from __future__ import annotations

from dataclasses import dataclass, asdict
from hashlib import sha256
from pathlib import Path
from typing import Any
import json

from .config import WORKSPACE_DIR
from .knowledge_store import KnowledgeItem, VerifiedKnowledgeStore
from .path_security import safe_child


SUPPORTED_PROJECT_VERIFIERS = {"tests", "design", "security"}


@dataclass(frozen=True)
class KnowledgeVerificationResult:
    knowledge: KnowledgeItem
    project_slug: str
    verifier_types: tuple[str, ...]
    evidence_refs: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "knowledge": self.knowledge.to_dict(),
            "project_slug": self.project_slug,
            "verifier_types": list(self.verifier_types),
            "evidence_refs": list(self.evidence_refs),
        }


class ProjectKnowledgeVerifier:
    """Promote candidate knowledge only from real passing project reports.

    Callers cannot supply arbitrary evidence strings. Evidence references are
    generated from SHA-256 hashes of reports that this verifier independently
    reads from the project workspace.
    """

    def __init__(
        self,
        knowledge: VerifiedKnowledgeStore | None = None,
        workspace_dir: Path | None = None,
    ):
        self.knowledge = knowledge or VerifiedKnowledgeStore()
        self.workspace_dir = Path(workspace_dir) if workspace_dir else WORKSPACE_DIR

    def verify(
        self,
        knowledge_id: str,
        *,
        project_slug: str,
        verifier_types: list[str] | tuple[str, ...],
    ) -> KnowledgeVerificationResult:
        slug = project_slug.strip()
        if not slug:
            raise ValueError("project_slug is required")
        requested = tuple(dict.fromkeys(str(x).strip() for x in verifier_types if str(x).strip()))
        if not requested:
            raise ValueError("at least one verifier type is required")
        unsupported = [x for x in requested if x not in SUPPORTED_PROJECT_VERIFIERS]
        if unsupported:
            raise ValueError("unsupported project verifier types: " + ", ".join(unsupported))

        project_dir = safe_child(self.workspace_dir, slug)
        if not project_dir.is_dir():
            raise FileNotFoundError(slug)

        refs: list[str] = []
        for verifier in requested:
            path, passed = self._report(project_dir, verifier)
            if not passed:
                raise ValueError(f"{verifier} evidence is missing or not passing")
            refs.append(f"{verifier}:sha256:{self._sha(path)}")

        item = self.knowledge.verify(
            knowledge_id,
            evidence_refs=refs,
            verified_by=list(requested),
        )
        return KnowledgeVerificationResult(item, slug, requested, tuple(refs))

    @staticmethod
    def _report(project_dir: Path, verifier: str) -> tuple[Path, bool]:
        if verifier == "tests":
            path = project_dir / ".aiapp" / "reports" / "test_report.json"
            return path, ProjectKnowledgeVerifier._json_pass(path, "passed")
        if verifier == "security":
            path = project_dir / ".aiapp" / "reports" / "security_report.json"
            return path, ProjectKnowledgeVerifier._json_pass(path, "passed")
        if verifier == "design":
            path = project_dir / "design_review.json"
            return path, ProjectKnowledgeVerifier._json_pass(path, "passed")
        raise ValueError("unsupported verifier")

    @staticmethod
    def _json_pass(path: Path, key: str) -> bool:
        if not path.is_file() or path.is_symlink():
            return False
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return False
        return isinstance(data, dict) and data.get(key) is True

    @staticmethod
    def _sha(path: Path) -> str:
        digest = sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()
