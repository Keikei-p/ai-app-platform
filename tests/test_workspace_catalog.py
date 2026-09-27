import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.core.workspace_catalog import ConversationStore, ProjectCatalog


class ConversationStoreTests(unittest.TestCase):
    def test_thread_persists_search_pin_and_rename(self):
        store = ConversationStore()
        thread = store.create_thread()
        store.append(thread, "user", "かわいい予約アプリを作りたい")
        store.append(thread, "assistant", "どこで使いますか？")
        store.rename(thread, "予約アプリ相談")
        store.set_pinned(thread, True)
        rows = store.list_threads("予約")
        row = next(x for x in rows if x.thread_id == thread)
        self.assertEqual(row.title, "予約アプリ相談")
        self.assertTrue(row.pinned)
        self.assertEqual(row.message_count, 2)

    def test_archive_hides_thread_without_deleting_messages(self):
        store = ConversationStore()
        thread = store.create_thread("削除テスト")
        store.append(thread, "user", "hello")
        store.archive(thread)
        self.assertFalse(any(x.thread_id == thread for x in store.list_threads()))
        self.assertEqual(len(store.messages(thread)), 1)

    def test_project_link_is_recoverable(self):
        store = ConversationStore()
        thread = store.create_thread("アプリ相談")
        store.link_project(thread, "demo", "Demo App")
        found = store.find_for_project("demo")
        self.assertIsNotNone(found)
        self.assertEqual(found.thread_id, thread)
        self.assertEqual(found.title, "Demo App")


class ProjectCatalogTests(unittest.TestCase):
    def test_only_existing_user_artifacts_are_listed(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            project = root / "demo"
            (project / "artifacts" / "web").mkdir(parents=True)
            (project / "artifacts" / "web" / "demo-web.zip").write_bytes(b"zip")
            (project / "artifacts" / "web" / "demo.manifest.json").write_text("{}", encoding="utf-8")
            (project / "project.json").write_text(
                json.dumps({"name": "Demo", "slug": "demo", "targets": ["web"]}),
                encoding="utf-8",
            )
            with patch("src.core.workspace_catalog.WORKSPACE_DIR", root):
                rows = ProjectCatalog().artifacts("demo")
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0].label, "Web ZIP")
            self.assertTrue(rows[0].path.endswith("demo-web.zip"))

    def test_missing_artifact_cannot_be_exported(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            project = root / "demo"
            project.mkdir()
            (project / "project.json").write_text(
                json.dumps({"name": "Demo", "slug": "demo"}),
                encoding="utf-8",
            )
            with patch("src.core.workspace_catalog.WORKSPACE_DIR", root):
                with self.assertRaises(FileNotFoundError):
                    ProjectCatalog().export_artifact("demo", "artifacts/windows/nope.exe", root / "out.exe")


if __name__ == "__main__":
    unittest.main()
