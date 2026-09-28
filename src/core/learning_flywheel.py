from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import hashlib
import json
import threading

from .config import DATA_DIR
from .redaction import redact_sensitive


SAFE_SOURCE_SUFFIXES = {
    ".py", ".js", ".mjs", ".cjs", ".ts", ".tsx", ".jsx",
    ".html", ".css", ".json", ".md", ".txt", ".yml", ".yaml",
    ".toml", ".ini", ".webmanifest",
}
BLOCKED_PARTS = {
    ".git", ".aiapp", ".vault", ".snapshots", "node_modules",
    "__pycache__", "artifacts",
}
BLOCKED_SUFFIXES = {".key", ".pem", ".p12", ".pfx", ".db", ".sqlite", ".sqlite3"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class LearningExample:
    example_id: str
    created_at: str
    project_slug: str
    instruction: str
    outcome_summary: str
    evaluation_score: int
    quality: dict[str, Any]
    model_route: dict[str, str]
    ai_status: str
    repair_count: int
    evidence_refs: tuple[str, ...]
    source_manifest: tuple[dict[str, Any], ...]
    lesson: str

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["evidence_refs"] = list(self.evidence_refs)
        data["source_manifest"] = list(self.source_manifest)
        return data


class AivyLearningFlywheel:
    """Verified experience store for Aivy's long-term learning loop.

    Only completed outcomes that already passed the platform learning gate and
    have evidence are accepted. This store never fine-tunes a model, changes
    policy, publishes code, or treats an unverified result as truth.
    """

    def __init__(self, path: Path | None = None):
        self.path = path or (DATA_DIR / "aivy_learning_examples.jsonl")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def recent(self, limit: int = 100) -> list[LearningExample]:
        if not self.path.is_file():
            return []
        rows: list[LearningExample] = []
        try:
            lines = self.path.read_text(encoding="utf-8").splitlines()
        except OSError:
            return []
        for line in lines[-max(1, limit):]:
            try:
                raw = json.loads(line)
                rows.append(LearningExample(
                    example_id=str(raw["example_id"]),
                    created_at=str(raw["created_at"]),
                    project_slug=str(raw["project_slug"]),
                    instruction=str(raw["instruction"]),
                    outcome_summary=str(raw["outcome_summary"]),
                    evaluation_score=int(raw["evaluation_score"]),
                    quality=dict(raw.get("quality") or {}),
                    model_route={
                        str(k): str(v)
                        for k, v in dict(raw.get("model_route") or {}).items()
                    },
                    ai_status=str(raw.get("ai_status") or ""),
                    repair_count=max(0, int(raw.get("repair_count") or 0)),
                    evidence_refs=tuple(str(x) for x in raw.get("evidence_refs") or ()),
                    source_manifest=tuple(
                        dict(x) for x in raw.get("source_manifest") or ()
                        if isinstance(x, dict)
                    ),
                    lesson=str(raw.get("lesson") or ""),
                ))
            except Exception:
                continue
        return list(reversed(rows))

    def capture_verified_build(
        self,
        *,
        project_slug: str,
        instruction: str,
        outcome_summary: str,
        result_ok: bool,
        evaluation: dict[str, Any],
        evidence_refs: list[str] | tuple[str, ...],
        project_dir: Path,
        result_files: list[Path] | tuple[Path, ...] = (),
        model_route: dict[str, Any] | None = None,
        ai_status: str = "",
        repair_attempts: list[dict[str, Any]] | tuple[dict[str, Any], ...] = (),
    ) -> dict[str, Any]:
        if not result_ok:
            return {"captured": False, "reason": "result_not_verified_success"}
        if not bool(evaluation.get("learning_eligible")):
            return {"captured": False, "reason": "quality_gates_not_learning_eligible"}

        evidence = tuple(dict.fromkeys(
            redact_sensitive(str(x).strip())[:500]
            for x in evidence_refs
            if str(x).strip()
        ))
        if not evidence:
            return {"captured": False, "reason": "verification_evidence_required"}

        clean_instruction = redact_sensitive(instruction.strip())[:6000]
        clean_summary = redact_sensitive(outcome_summary.strip())[:3000]
        if not clean_instruction:
            return {"captured": False, "reason": "instruction_required"}

        route_raw = dict(model_route or {})
        route = {
            "mode": redact_sensitive(str(route_raw.get("mode") or ""))[:80],
            "provider": redact_sensitive(str(route_raw.get("provider") or "none"))[:80],
            "model": redact_sensitive(str(route_raw.get("model") or ""))[:160],
            "capability": redact_sensitive(str(route_raw.get("capability") or "coding"))[:80],
        }
        quality = {
            "tests_passed": bool(evaluation.get("tests_passed")),
            "test_pass_ratio": float(evaluation.get("test_pass_ratio") or 0.0),
            "design_passed": bool(evaluation.get("design_passed")),
            "design_score": int(evaluation.get("design_score") or 0),
            "security_passed": bool(evaluation.get("security_passed")),
            "preview_ready": bool(evaluation.get("preview_ready")),
            "release_ready": bool(evaluation.get("release_ready")),
            "artifact_count": max(0, int(evaluation.get("artifact_count") or 0)),
        }
        score = max(0, min(100, int(evaluation.get("score") or 0)))
        manifest = tuple(self._source_manifest(Path(project_dir), result_files))
        repair_count = len(list(repair_attempts or ()))

        identity = json.dumps({
            "project_slug": project_slug.strip(),
            "instruction": clean_instruction,
            "evidence_refs": evidence,
            "source_manifest": manifest,
        }, ensure_ascii=False, sort_keys=True)
        example_id = hashlib.sha256(identity.encode("utf-8")).hexdigest()
        short_goal = " ".join(clean_instruction.split())[:180]
        lesson = (
            f"Verified build succeeded for '{short_goal}' with quality score "
            f"{score}/100, route {route['provider'] or 'none'}/"
            f"{route['model'] or 'deterministic'}, and {repair_count} repair attempt(s). "
            "Reuse the verified approach only when the new requirement is relevant."
        )
        item = LearningExample(
            example_id=example_id,
            created_at=_now(),
            project_slug=redact_sensitive(project_slug.strip())[:180],
            instruction=clean_instruction,
            outcome_summary=clean_summary,
            evaluation_score=score,
            quality=quality,
            model_route=route,
            ai_status=redact_sensitive(ai_status.strip())[:80],
            repair_count=repair_count,
            evidence_refs=evidence,
            source_manifest=manifest,
            lesson=lesson,
        )

        with self._lock:
            existing = next(
                (x for x in self.recent(5000) if x.example_id == example_id),
                None,
            )
            if existing is not None:
                return {
                    "captured": True,
                    "duplicate": True,
                    "example": existing.to_dict(),
                }
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(item.to_dict(), ensure_ascii=False) + "\n")

        return {
            "captured": True,
            "duplicate": False,
            "example": item.to_dict(),
        }

    def stats(self) -> dict[str, Any]:
        rows = self.recent(5000)
        scores = [x.evaluation_score for x in rows]
        providers: dict[str, int] = {}
        ai_backed = 0
        repaired = 0
        for row in rows:
            provider = row.model_route.get("provider") or "none"
            providers[provider] = providers.get(provider, 0) + 1
            if provider != "none":
                ai_backed += 1
            if row.repair_count:
                repaired += 1
        return {
            "verified_examples": len(rows),
            "average_score": round(sum(scores) / len(scores), 2) if scores else 0.0,
            "ai_backed_examples": ai_backed,
            "deterministic_examples": len(rows) - ai_backed,
            "repaired_examples": repaired,
            "providers": providers,
            "latest": rows[0].to_dict() if rows else None,
            "training_stage": "collecting_verified_supervision",
            "auto_fine_tune": False,
            "rule": "Only evidence-backed successful builds become supervision candidates; model training remains separately reviewed.",
        }

    def supervision_candidates(self, limit: int = 200) -> list[dict[str, Any]]:
        rows = self.recent(max(1, min(limit, 1000)))
        return [
            {
                "messages": [
                    {"role": "user", "content": row.instruction},
                    {"role": "assistant", "content": row.outcome_summary},
                ],
                "metadata": {
                    "example_id": row.example_id,
                    "project_slug": row.project_slug,
                    "evaluation_score": row.evaluation_score,
                    "quality": row.quality,
                    "model_route": row.model_route,
                    "repair_count": row.repair_count,
                    "evidence_refs": list(row.evidence_refs),
                    "source_manifest": list(row.source_manifest),
                },
            }
            for row in rows
        ]

    @staticmethod
    def _source_manifest(
        project_dir: Path,
        result_files: list[Path] | tuple[Path, ...],
    ) -> list[dict[str, Any]]:
        root = project_dir.resolve()
        rows: list[dict[str, Any]] = []
        seen: set[str] = set()
        for raw_path in result_files or ():
            try:
                path = Path(raw_path)
                resolved = (
                    path.resolve()
                    if path.is_absolute()
                    else (root / path).resolve()
                )
                if resolved != root and root not in resolved.parents:
                    continue
                rel = resolved.relative_to(root)
                if any(part in BLOCKED_PARTS for part in rel.parts):
                    continue
                if resolved.name.startswith(".env"):
                    continue
                if resolved.suffix.lower() in BLOCKED_SUFFIXES:
                    continue
                if resolved.suffix.lower() not in SAFE_SOURCE_SUFFIXES:
                    continue
                if not resolved.is_file() or resolved.is_symlink():
                    continue
                relative = rel.as_posix()
                if relative in seen:
                    continue
                raw = resolved.read_bytes()
                if len(raw) > 2 * 1024 * 1024:
                    continue
                seen.add(relative)
                rows.append({
                    "path": relative,
                    "sha256": hashlib.sha256(raw).hexdigest(),
                    "bytes": len(raw),
                })
            except (OSError, ValueError):
                continue
        rows.sort(key=lambda x: x["path"])
        return rows
