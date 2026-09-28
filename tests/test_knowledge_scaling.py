import tempfile
import unittest
from pathlib import Path

from src.core.knowledge_factory import KnowledgeFactory
from src.core.knowledge_index import ScalableKnowledgeIndex
from src.core.knowledge_intelligence import KnowledgeSearchEngine, KnowledgeUsageStore
from src.core.knowledge_store import VerifiedKnowledgeStore


class CountingKnowledgeStore(VerifiedKnowledgeStore):
    def __init__(self, path: Path):
        super().__init__(path)
        self.write_count = 0
        self.list_count = 0

    def _write(self, rows):
        self.write_count += 1
        return super()._write(rows)

    def list(self, trust_level=None):
        self.list_count += 1
        return super().list(trust_level)


def make_row(index: int, *, two_sources: bool = False):
    sources = [{
        "kind": "official_docs",
        "locator": f"https://example.com/docs/{index}",
        "title": f"Doc {index}",
        "content": f"Public technical documentation for feature {index}.",
        "version": "v1",
        "retrieved_at": "2026-09-28T00:00:00+00:00",
    }]
    if two_sources:
        sources.append({
            "kind": "repository",
            "locator": f"https://example.com/repo/{index}",
            "title": f"Repo {index}",
            "content": f"Public repository documentation for feature {index}.",
            "version": "v1",
            "retrieved_at": "2026-09-28T00:00:00+00:00",
        })
    return {
        "topic": f"Feature {index}",
        "statement": f"Feature {index} uses a deterministic implementation pattern.",
        "sources": sources,
    }


def verify_item(store: VerifiedKnowledgeStore, topic: str, statement: str):
    first = store.ingest(
        topic=topic,
        statement=statement,
        source_kind="official_docs",
        source_locator="https://example.com/official/" + topic,
        retrieved_at="2026-09-28T00:00:00+00:00",
    )
    store.ingest(
        topic=topic,
        statement=statement,
        source_kind="repository",
        source_locator="https://example.com/repo/" + topic,
        retrieved_at="2026-09-28T00:00:00+00:00",
    )
    store.promote_candidate(first.knowledge_id)
    return store.verify(
        first.knowledge_id,
        evidence_refs=["tests:sha256:abc"],
        verified_by=["tests"],
    )


class KnowledgeScalingTests(unittest.TestCase):
    def test_hundred_row_page_uses_bounded_store_writes(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            store = CountingKnowledgeStore(root / "knowledge.json")
            factory = KnowledgeFactory(store, audit_path=root / "audit.jsonl")
            result = factory.ingest_batch([make_row(i) for i in range(100)])
            self.assertEqual(result.accepted, 100)
            self.assertEqual(result.rejected, 0)
            self.assertEqual(len(store.list()), 100)
            self.assertLessEqual(store.write_count, 1)

    def test_candidate_promotions_add_at_most_one_extra_batch_write(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            store = CountingKnowledgeStore(root / "knowledge.json")
            factory = KnowledgeFactory(store, audit_path=root / "audit.jsonl")
            result = factory.ingest_batch([
                make_row(i, two_sources=True)
                for i in range(25)
            ])
            self.assertEqual(result.accepted, 25)
            self.assertEqual(result.candidate_promotions, 25)
            self.assertLessEqual(store.write_count, 2)
            self.assertTrue(all(
                item.trust_level == "candidate"
                for item in store.list()
            ))

    def test_second_search_uses_current_sqlite_index_without_full_list_scan(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            store = CountingKnowledgeStore(root / "knowledge.json")
            verify_item(
                store,
                "Firebase Authentication",
                "Firebase Authentication handles user sign-in and verified email state.",
            )
            verify_item(
                store,
                "Responsive CSS",
                "CSS Grid and Flexbox build responsive layouts.",
            )
            store.list_count = 0
            index = ScalableKnowledgeIndex(root / "index.sqlite3")
            search = KnowledgeSearchEngine(
                store,
                KnowledgeUsageStore(
                    root / "usage.json",
                    root / "usage-evidence.jsonl",
                ),
                scalable_index=index,
            )
            first = search.search("Firebase Authentication sign-in", limit=5)
            self.assertTrue(first)
            first_count = store.list_count
            self.assertGreaterEqual(first_count, 1)

            second = search.search("Firebase user sign-in", limit=5)
            self.assertTrue(second)
            if index.fts_available:
                self.assertEqual(store.list_count, first_count)
            else:
                self.assertGreaterEqual(store.list_count, first_count)

    def test_sqlite_index_payload_contains_only_staged_knowledge_not_raw_source_body(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            store = VerifiedKnowledgeStore(root / "knowledge.json")
            item = verify_item(
                store,
                "Safe knowledge",
                "Only the staged statement and provenance are indexed.",
            )
            index = ScalableKnowledgeIndex(root / "index.sqlite3")
            index.sync(store.list(), source_signature="test")
            loaded = index.items([item.knowledge_id])
            self.assertEqual(len(loaded), 1)
            self.assertEqual(loaded[0].statement, item.statement)
            self.assertFalse(any(
                "content" in source
                for source in loaded[0].sources
            ))


if __name__ == "__main__":
    unittest.main()
