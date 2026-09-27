from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any
import json

from .app_spec import AppSpec
from .llm_chat import AIChatEngine
from .model_router import ModelRouter


@dataclass(frozen=True)
class CodingBrainResult:
    status: str
    summary: str
    files: list[Path]

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "summary": self.summary,
            "files": [str(x) for x in self.files],
        }


class CodingBrain:
    """Optional LLM coding layer with deterministic safety boundaries."""

    ALLOWED_SUFFIXES = {
        ".py", ".js", ".mjs", ".cjs", ".ts", ".tsx", ".jsx", ".html", ".css",
        ".json", ".md", ".txt", ".yml", ".yaml", ".toml", ".ini", ".webmanifest",
    }
    PROTECTED_NAMES = {
        "project.json", "app_spec.json", "generated_manifest.json", "release_risk.json",
        ".gitignore",
    }
    PROTECTED_PARTS = {
        ".git", ".snapshots", ".vault", ".aiapp", "node_modules", "__pycache__", "artifacts",
    }
    SENSITIVE_SUFFIXES = {".key", ".pem", ".p12", ".pfx", ".db", ".sqlite", ".sqlite3"}
    MAX_FILES = 30
    MAX_FILE_CHARS = 220_000
    MAX_TOTAL_CHARS = 700_000
    MAX_CONTEXT_CHARS = 60_000

    def __init__(self, engine: AIChatEngine | None = None, router: ModelRouter | None = None):
        self.engine = engine or AIChatEngine()
        self.router = router or ModelRouter(self.engine)

    def enhance(self, project_dir: Path, spec: AppSpec, instruction: str) -> CodingBrainResult:
        route = self.router.route("coding")
        if route.mode == "deterministic_fallback":
            status = self.engine.status()
            return CodingBrainResult("not_connected", status.detail, [])

        context = self._project_context(project_dir)
        system = (
            "You are the coding brain inside a local app generator. "
            "Return ONLY one JSON object with keys summary and files. "
            "files must be an array of objects with path and content. "
            "Only provide complete UTF-8 text files that need to be created or replaced. "
            "Do not include secrets, credentials, destructive commands, malware, shell execution, "
            "or any path outside the project. Never request deployment or store submission. "
            "Preserve working behavior and improve the app specifically for the user's requirements. "
            "If no change is needed return an empty files array."
        )
        prompt = (
            "USER REQUIREMENT:\n"
            + instruction.strip()
            + "\n\nAPP SPEC:\n"
            + json.dumps(spec.to_dict(), ensure_ascii=False, indent=2)
            + "\n\nCURRENT PROJECT FILES:\n"
            + context
        )
        if hasattr(self.engine, "reply_routed"):
            raw = self.engine.reply_routed(route.provider, route.model, [], prompt, system)
        else:
            raw = self.engine.reply([], prompt, system)
        proposal = self._parse(raw)
        summary = str(proposal.get("summary") or "AI code enhancement").strip()[:1000]
        files = proposal.get("files")
        if not isinstance(files, list):
            raise ValueError("coding proposal files must be a list")
        if not files:
            return CodingBrainResult("no_changes", summary, [])

        validated = self._validate_files(project_dir, files)
        written = self._apply_atomically(validated)
        return CodingBrainResult("applied", summary, written)

    def _project_context(self, project_dir: Path) -> str:
        chunks: list[str] = []
        used = 0
        for path in sorted(project_dir.rglob("*")):
            if not path.is_file() or path.is_symlink():
                continue
            rel = path.relative_to(project_dir)
            if any(part in self.PROTECTED_PARTS for part in rel.parts):
                continue
            if path.name.startswith(".env") or path.suffix.lower() in self.SENSITIVE_SUFFIXES:
                continue
            if path.suffix.lower() not in self.ALLOWED_SUFFIXES:
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            room = self.MAX_CONTEXT_CHARS - used
            if room <= 0:
                break
            piece = text[: min(len(text), room, 12_000)]
            chunks.append(f"--- {rel.as_posix()} ---\n{piece}")
            used += len(piece)
        return "\n\n".join(chunks)

    @staticmethod
    def _parse(raw: str) -> dict[str, Any]:
        text = raw.strip()
        if text.startswith(chr(96) * 3):
            first_newline = text.find("\n")
            if first_newline >= 0:
                text = text[first_newline + 1 :]
            if text.endswith(chr(96) * 3):
                text = text[:-3].rstrip()
        start = text.find("{")
        end = text.rfind("}")
        if start < 0 or end < start:
            raise ValueError("coding model did not return JSON")
        data = json.loads(text[start : end + 1])
        if not isinstance(data, dict):
            raise ValueError("coding proposal must be a JSON object")
        return data

    def _validate_files(self, project_dir: Path, rows: list[Any]) -> list[tuple[Path, str]]:
        if len(rows) > self.MAX_FILES:
            raise ValueError("coding proposal contains too many files")
        root = project_dir.resolve()
        validated: list[tuple[Path, str]] = []
        seen: set[str] = set()
        total = 0

        for row in rows:
            if not isinstance(row, dict):
                raise ValueError("coding proposal file entry must be an object")
            raw_path = str(row.get("path") or "").replace("\\", "/").strip()
            content = row.get("content")
            if not raw_path or not isinstance(content, str):
                raise ValueError("coding proposal requires path and text content")

            pure = PurePosixPath(raw_path)
            if pure.is_absolute() or ".." in pure.parts or "." in pure.parts:
                raise ValueError(f"unsafe proposal path: {raw_path}")
            if any(part in self.PROTECTED_PARTS for part in pure.parts):
                raise ValueError(f"protected proposal path: {raw_path}")
            if pure.name in self.PROTECTED_NAMES or pure.name.startswith(".env"):
                raise ValueError(f"protected proposal file: {raw_path}")
            if pure.suffix.lower() in self.SENSITIVE_SUFFIXES:
                raise ValueError(f"sensitive/binary proposal file: {raw_path}")
            if pure.suffix.lower() not in self.ALLOWED_SUFFIXES:
                raise ValueError(f"unsupported proposal file type: {raw_path}")
            if len(content) > self.MAX_FILE_CHARS:
                raise ValueError(f"proposal file is too large: {raw_path}")

            total += len(content)
            if total > self.MAX_TOTAL_CHARS:
                raise ValueError("coding proposal is too large")
            normalized = pure.as_posix()
            if normalized in seen:
                raise ValueError(f"duplicate proposal path: {raw_path}")
            seen.add(normalized)

            target = root.joinpath(*pure.parts)
            parent = target.parent
            while parent != root:
                if parent.exists() and parent.is_symlink():
                    raise ValueError(f"proposal parent is a symlink: {raw_path}")
                resolved_parent = parent.resolve()
                if resolved_parent != root and root not in resolved_parent.parents:
                    raise ValueError(f"proposal escaped project: {raw_path}")
                parent = parent.parent
            if target.exists() and target.is_symlink():
                raise ValueError(f"proposal target is a symlink: {raw_path}")
            resolved_parent = target.parent.resolve()
            if resolved_parent != root and root not in resolved_parent.parents:
                raise ValueError(f"proposal escaped project: {raw_path}")
            validated.append((target, content))
        return validated

    @staticmethod
    def _apply_atomically(rows: list[tuple[Path, str]]) -> list[Path]:
        originals: dict[Path, bytes | None] = {}
        written: list[Path] = []
        try:
            for target, content in rows:
                originals[target] = target.read_bytes() if target.exists() else None
                target.parent.mkdir(parents=True, exist_ok=True)
                tmp = target.with_name(target.name + ".aiapp-tmp")
                tmp.write_text(content, encoding="utf-8")
                tmp.replace(target)
                written.append(target)
            return written
        except Exception:
            for target, original in reversed(list(originals.items())):
                try:
                    if original is None:
                        target.unlink(missing_ok=True)
                    else:
                        target.write_bytes(original)
                except Exception:
                    pass
            raise
