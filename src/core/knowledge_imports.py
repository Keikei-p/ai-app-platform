from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from typing import Any
import json
import uuid

from .config import DATA_DIR
from .knowledge_factory import KnowledgeFactory


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class KnowledgeImportState:
    import_id: str
    name: str
    status: str
    next_page: int
    pages_completed: int
    rows_received: int
    accepted: int
    rejected: int
    deduplicated: int
    candidate_promotions: int
    page_hashes: tuple[str, ...]
    created_at: str
    updated_at: str

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["page_hashes"] = list(self.page_hashes)
        return data


class KnowledgeImportManager:
    """Resumable bounded intake for very large knowledge datasets.

    Raw dataset rows are not persisted by the manager. Only counters and page
    hashes are stored, allowing callers to retry safely without duplicating an
    already committed page. Each page still passes through KnowledgeFactory
    safety, deduplication and staged-trust rules.
    """

    MAX_PAGES = 10_000

    def __init__(
        self,
        factory: KnowledgeFactory,
        *,
        state_dir: Path | None = None,
    ):
        self.factory = factory
        self.state_dir = state_dir or (DATA_DIR / "knowledge_imports")
        self.state_dir.mkdir(parents=True, exist_ok=True)

    def start(self, name: str) -> KnowledgeImportState:
        clean = str(name).strip()[:180]
        if not clean:
            raise ValueError("knowledge import name is required")
        import_id = uuid.uuid4().hex
        now = _now()
        state = KnowledgeImportState(
            import_id=import_id,
            name=clean,
            status="active",
            next_page=0,
            pages_completed=0,
            rows_received=0,
            accepted=0,
            rejected=0,
            deduplicated=0,
            candidate_promotions=0,
            page_hashes=(),
            created_at=now,
            updated_at=now,
        )
        self._save(state)
        return state

    def ingest_page(
        self,
        import_id: str,
        *,
        page_index: int,
        rows: list[dict[str, Any]],
        final: bool = False,
    ) -> KnowledgeImportState:
        state = self.get(import_id)
        if state.status != "active":
            raise RuntimeError("knowledge import is not active")
        index = int(page_index)
        if index < 0 or index >= self.MAX_PAGES:
            raise ValueError("knowledge import page index is outside the safe range")
        if not isinstance(rows, list):
            raise ValueError("knowledge import page rows must be an array")

        digest = self._page_hash(rows)
        if index < state.next_page:
            prior = state.page_hashes[index] if index < len(state.page_hashes) else ""
            if prior == digest:
                return state
            raise ValueError("knowledge import replay does not match the committed page")
        if index != state.next_page:
            raise ValueError(f"expected knowledge import page {state.next_page}")

        result = self.factory.ingest_batch(rows)
        hashes = list(state.page_hashes)
        hashes.append(digest)
        now = _now()
        updated = KnowledgeImportState(
            import_id=state.import_id,
            name=state.name,
            status="completed" if final else "active",
            next_page=index + 1,
            pages_completed=state.pages_completed + 1,
            rows_received=state.rows_received + len(rows),
            accepted=state.accepted + result.accepted,
            rejected=state.rejected + result.rejected,
            deduplicated=state.deduplicated + result.deduplicated,
            candidate_promotions=state.candidate_promotions + result.candidate_promotions,
            page_hashes=tuple(hashes),
            created_at=state.created_at,
            updated_at=now,
        )
        self._save(updated)
        return updated

    def complete(self, import_id: str) -> KnowledgeImportState:
        state = self.get(import_id)
        if state.status == "completed":
            return state
        if state.status != "active":
            raise RuntimeError("knowledge import cannot be completed")
        updated = KnowledgeImportState(
            **{
                **state.to_dict(),
                "status": "completed",
                "page_hashes": state.page_hashes,
                "updated_at": _now(),
            }
        )
        self._save(updated)
        return updated

    def get(self, import_id: str) -> KnowledgeImportState:
        key = self._safe_id(import_id)
        path = self.state_dir / f"{key}.json"
        if not path.is_file() or path.is_symlink():
            raise KeyError(key)
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            return self._from_dict(raw)
        except KeyError:
            raise
        except Exception as exc:
            raise RuntimeError("knowledge import state is invalid") from exc

    def list(self, limit: int = 50) -> list[KnowledgeImportState]:
        rows: list[KnowledgeImportState] = []
        for path in sorted(
            self.state_dir.glob("*.json"),
            key=lambda item: item.stat().st_mtime,
            reverse=True,
        ):
            if path.is_symlink():
                continue
            try:
                rows.append(self._from_dict(json.loads(path.read_text(encoding="utf-8"))))
            except Exception:
                continue
            if len(rows) >= max(1, min(int(limit), 200)):
                break
        return rows

    def _save(self, state: KnowledgeImportState) -> None:
        path = self.state_dir / f"{self._safe_id(state.import_id)}.json"
        tmp = path.with_suffix(".tmp")
        tmp.write_text(
            json.dumps(state.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        tmp.replace(path)

    @staticmethod
    def _page_hash(rows: list[dict[str, Any]]) -> str:
        canonical = json.dumps(rows, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return sha256(canonical.encode("utf-8")).hexdigest()

    @staticmethod
    def _safe_id(value: str) -> str:
        key = str(value).strip()
        if len(key) != 32 or any(ch not in "0123456789abcdef" for ch in key.lower()):
            raise ValueError("invalid knowledge import id")
        return key.lower()

    @staticmethod
    def _from_dict(raw: Any) -> KnowledgeImportState:
        if not isinstance(raw, dict):
            raise ValueError("knowledge import state must be an object")
        return KnowledgeImportState(
            import_id=str(raw["import_id"]),
            name=str(raw["name"]),
            status=str(raw["status"]),
            next_page=max(0, int(raw.get("next_page", 0))),
            pages_completed=max(0, int(raw.get("pages_completed", 0))),
            rows_received=max(0, int(raw.get("rows_received", 0))),
            accepted=max(0, int(raw.get("accepted", 0))),
            rejected=max(0, int(raw.get("rejected", 0))),
            deduplicated=max(0, int(raw.get("deduplicated", 0))),
            candidate_promotions=max(0, int(raw.get("candidate_promotions", 0))),
            page_hashes=tuple(str(x) for x in raw.get("page_hashes") or ()),
            created_at=str(raw.get("created_at") or ""),
            updated_at=str(raw.get("updated_at") or ""),
        )
