import tempfile
import unittest
from pathlib import Path

from src.core.knowledge_factory import KnowledgeFactory
from src.core.knowledge_imports import KnowledgeImportManager
from src.core.knowledge_store import VerifiedKnowledgeStore


def row(topic: str, statement: str, locator: str):
    return {
        "topic": topic,
        "statement": statement,
        "sources": [{
            "kind": "official_docs",
            "locator": locator,
            "title": topic,
            "content": "Official technical documentation for this topic.",
            "version": "v1",
            "retrieved_at": "2026-09-28T00:00:00+00:00",
        }],
    }


class KnowledgeImportManagerTests(unittest.TestCase):
    def _manager(self, root: Path):
        store = VerifiedKnowledgeStore(root / "knowledge.json")
        factory = KnowledgeFactory(store, audit_path=root / "factory.jsonl")
        manager = KnowledgeImportManager(factory, state_dir=root / "imports")
        return store, manager

    def test_multi_page_import_accumulates_and_completes(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            store, manager = self._manager(root)
            state = manager.start("docs")
            first = manager.ingest_page(
                state.import_id,
                page_index=0,
                rows=[row("A", "Knowledge A", "https://example.com/a")],
            )
            self.assertEqual(first.status, "active")
            self.assertEqual(first.next_page, 1)
            final = manager.ingest_page(
                state.import_id,
                page_index=1,
                rows=[row("B", "Knowledge B", "https://example.com/b")],
                final=True,
            )
            self.assertEqual(final.status, "completed")
            self.assertEqual(final.pages_completed, 2)
            self.assertEqual(final.rows_received, 2)
            self.assertEqual(final.accepted, 2)
            self.assertEqual(len(store.list()), 2)

    def test_committed_page_retry_is_idempotent(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            store, manager = self._manager(root)
            state = manager.start("docs")
            rows = [row("A", "Knowledge A", "https://example.com/a")]
            first = manager.ingest_page(state.import_id, page_index=0, rows=rows)
            replay = manager.ingest_page(state.import_id, page_index=0, rows=rows)
            self.assertEqual(first.to_dict(), replay.to_dict())
            self.assertEqual(len(store.list()), 1)

    def test_changed_replay_and_out_of_order_page_are_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _, manager = self._manager(root)
            state = manager.start("docs")
            manager.ingest_page(
                state.import_id,
                page_index=0,
                rows=[row("A", "Knowledge A", "https://example.com/a")],
            )
            with self.assertRaises(ValueError):
                manager.ingest_page(
                    state.import_id,
                    page_index=0,
                    rows=[row("A", "Changed A", "https://example.com/a")],
                )
            with self.assertRaises(ValueError):
                manager.ingest_page(
                    state.import_id,
                    page_index=2,
                    rows=[row("C", "Knowledge C", "https://example.com/c")],
                )

    def test_session_resumes_after_manager_restart(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            store, manager = self._manager(root)
            state = manager.start("docs")
            manager.ingest_page(
                state.import_id,
                page_index=0,
                rows=[row("A", "Knowledge A", "https://example.com/a")],
            )

            factory2 = KnowledgeFactory(store, audit_path=root / "factory-2.jsonl")
            restarted = KnowledgeImportManager(factory2, state_dir=root / "imports")
            loaded = restarted.get(state.import_id)
            self.assertEqual(loaded.next_page, 1)
            completed = restarted.ingest_page(
                state.import_id,
                page_index=1,
                rows=[row("B", "Knowledge B", "https://example.com/b")],
                final=True,
            )
            self.assertEqual(completed.status, "completed")
            self.assertEqual(len(store.list()), 2)

    def test_completed_session_refuses_new_pages(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _, manager = self._manager(root)
            state = manager.start("docs")
            manager.ingest_page(
                state.import_id,
                page_index=0,
                rows=[row("A", "Knowledge A", "https://example.com/a")],
                final=True,
            )
            with self.assertRaises(RuntimeError):
                manager.ingest_page(
                    state.import_id,
                    page_index=1,
                    rows=[row("B", "Knowledge B", "https://example.com/b")],
                )


if __name__ == "__main__":
    unittest.main()
