from __future__ import annotations

from pathlib import Path
from typing import Iterable
import json
import re
import sqlite3

from .config import DATA_DIR
from .knowledge_store import KnowledgeItem


class ScalableKnowledgeIndex:
    """SQLite FTS cache for narrowing large knowledge collections.

    The verified JSON store remains the authoritative safety/trust record.
    This index is disposable and rebuildable: it stores only searchable text,
    hashes and trust metadata, never credentials or raw research source bodies.
    """

    MAX_INDEX_TOKENS = 700
    MAX_QUERY_TOKENS = 48

    def __init__(self, path: Path | None = None):
        self.path = path or (DATA_DIR / "knowledge_search_index.sqlite3")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.fts_available = self._ensure_schema()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=15)
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA synchronous=NORMAL")
        return connection

    def _ensure_schema(self) -> bool:
        with self._connect() as db:
            db.execute(
                """
                CREATE TABLE IF NOT EXISTS knowledge_docs (
                    knowledge_id TEXT PRIMARY KEY,
                    content_hash TEXT NOT NULL,
                    trust_level TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    tokens TEXT NOT NULL
                )
                """
            )
            db.execute(
                """
                CREATE TABLE IF NOT EXISTS knowledge_index_meta (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                )
                """
            )
            try:
                db.execute(
                    """
                    CREATE VIRTUAL TABLE IF NOT EXISTS knowledge_fts
                    USING fts5(knowledge_id UNINDEXED, tokens)
                    """
                )
            except sqlite3.OperationalError:
                return False
        return True

    def sync(
        self,
        items: Iterable[KnowledgeItem],
        *,
        source_signature: str = "",
    ) -> dict[str, int | bool]:
        rows = list(items)
        signature = str(source_signature or "").strip()
        with self._connect() as db:
            if signature:
                current = db.execute(
                    "SELECT value FROM knowledge_index_meta WHERE key='source_signature'"
                ).fetchone()
                if current and current[0] == signature:
                    return {
                        "synced": False,
                        "documents": len(rows),
                        "updated": 0,
                        "fts": self.fts_available,
                    }

            existing = {
                row[0]: (row[1], row[2], row[3])
                for row in db.execute(
                    "SELECT knowledge_id, content_hash, trust_level, updated_at FROM knowledge_docs"
                )
            }
            live_ids: set[str] = set()
            updated = 0
            for item in rows:
                live_ids.add(item.knowledge_id)
                marker = (item.content_hash, item.trust_level, item.updated_at)
                if existing.get(item.knowledge_id) == marker:
                    continue
                tokens = self._document_tokens(item.topic + "\n" + item.statement)
                db.execute(
                    """
                    INSERT INTO knowledge_docs
                        (knowledge_id, content_hash, trust_level, updated_at, tokens)
                    VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(knowledge_id) DO UPDATE SET
                        content_hash=excluded.content_hash,
                        trust_level=excluded.trust_level,
                        updated_at=excluded.updated_at,
                        tokens=excluded.tokens
                    """,
                    (
                        item.knowledge_id,
                        item.content_hash,
                        item.trust_level,
                        item.updated_at,
                        tokens,
                    ),
                )
                if self.fts_available:
                    db.execute(
                        "DELETE FROM knowledge_fts WHERE knowledge_id=?",
                        (item.knowledge_id,),
                    )
                    db.execute(
                        "INSERT INTO knowledge_fts (knowledge_id, tokens) VALUES (?, ?)",
                        (item.knowledge_id, tokens),
                    )
                updated += 1

            stale = [knowledge_id for knowledge_id in existing if knowledge_id not in live_ids]
            if stale:
                db.executemany(
                    "DELETE FROM knowledge_docs WHERE knowledge_id=?",
                    ((knowledge_id,) for knowledge_id in stale),
                )
                if self.fts_available:
                    db.executemany(
                        "DELETE FROM knowledge_fts WHERE knowledge_id=?",
                        ((knowledge_id,) for knowledge_id in stale),
                    )

            if signature:
                db.execute(
                    """
                    INSERT INTO knowledge_index_meta (key, value)
                    VALUES ('source_signature', ?)
                    ON CONFLICT(key) DO UPDATE SET value=excluded.value
                    """,
                    (signature,),
                )
            return {
                "synced": True,
                "documents": len(rows),
                "updated": updated,
                "fts": self.fts_available,
            }

    def candidates(
        self,
        query: str,
        *,
        verified_only: bool = True,
        limit: int = 160,
    ) -> list[str]:
        if not self.fts_available:
            return []
        expression = self._match_expression(query)
        if not expression:
            return []
        bounded = max(1, min(int(limit), 1000))
        sql = (
            "SELECT knowledge_fts.knowledge_id "
            "FROM knowledge_fts "
            "JOIN knowledge_docs ON knowledge_docs.knowledge_id=knowledge_fts.knowledge_id "
            "WHERE knowledge_fts MATCH ? "
        )
        args: list[object] = [expression]
        if verified_only:
            sql += "AND knowledge_docs.trust_level='verified' "
        sql += "ORDER BY bm25(knowledge_fts) LIMIT ?"
        args.append(bounded)
        try:
            with self._connect() as db:
                return [str(row[0]) for row in db.execute(sql, args)]
        except sqlite3.OperationalError:
            return []

    def stats(self) -> dict[str, int | bool]:
        with self._connect() as db:
            count = int(db.execute("SELECT COUNT(*) FROM knowledge_docs").fetchone()[0])
        return {
            "documents": count,
            "fts": self.fts_available,
        }

    @classmethod
    def _document_tokens(cls, text: str) -> str:
        return " ".join(cls._tokens(text, cls.MAX_INDEX_TOKENS))

    @classmethod
    def _match_expression(cls, text: str) -> str:
        tokens = cls._tokens(text, cls.MAX_QUERY_TOKENS)
        safe = []
        for token in tokens:
            clean = token.replace('"', "").strip()
            if clean:
                safe.append('"' + clean + '"')
        return " OR ".join(safe)

    @staticmethod
    def _tokens(text: str, limit: int) -> list[str]:
        normalized = re.sub(r"\s+", " ", str(text).strip().lower())[:24_000]
        compact = normalized.replace(" ", "")
        tokens: list[str] = []
        words = re.findall(r"[a-z0-9_+#.-]{2,}", normalized)
        tokens.extend(words)
        for size in (2, 3):
            for index in range(max(0, len(compact) - size + 1)):
                gram = compact[index:index + size]
                if gram.strip():
                    tokens.append(gram)
                if len(tokens) >= limit * 2:
                    break
            if len(tokens) >= limit * 2:
                break
        return list(dict.fromkeys(tokens))[:limit]


def knowledge_source_signature(path: Path | None) -> str:
    if path is None:
        return ""
    try:
        stat = Path(path).stat()
    except OSError:
        return ""
    return json.dumps(
        {
            "path": str(Path(path).resolve()),
            "size": stat.st_size,
            "mtime_ns": stat.st_mtime_ns,
        },
        sort_keys=True,
    )
