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
        # Re-open the store to prove the chat is not only in process memory.
        reopened = ConversationStore()
        rows = reopened.list_threads("予約")
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

    def test_artifact_path_resolves_only_cataloged_real_artifacts(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            with patch("src.core.workspace_catalog.WORKSPACE_DIR", root):
                slug = "safe-artifact"
                project = root / slug
                project.mkdir()
                (project / "project.json").write_text('{"name":"Safe"}', encoding="utf-8")
                artifact = project / "artifacts/web/demo.zip"
                artifact.parent.mkdir(parents=True)
                artifact.write_bytes(b"zip")
                catalog = ProjectCatalog()
                rows = catalog.artifacts(slug)
                self.assertEqual(len(rows), 1)
                resolved = catalog.artifact_path(slug, rows[0].artifact_id)
                self.assertEqual(resolved, artifact.resolve())
                with self.assertRaises(FileNotFoundError):
                    catalog.artifact_path(slug, "../../outside.zip")

    def test_requested_ios_is_visible_as_pending_not_downloadable(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            project = root / "demo"
            project.mkdir()
            (project / "project.json").write_text(
                json.dumps({"name": "Demo", "slug": "demo", "targets": ["web", "ios"]}),
                encoding="utf-8",
            )
            (project / "app_spec.json").write_text(
                json.dumps({"project_name": "Demo", "slug": "demo", "targets": ["web", "ios"]}),
                encoding="utf-8",
            )
            (project / "implementation_gaps.json").write_text(
                json.dumps({"items": [{
                    "key": "ios_binary",
                    "reason": "IPAはまだ生成されていません。",
                    "next_step": "Apple署名を準備する。",
                }]}),
                encoding="utf-8",
            )
            with patch("src.core.workspace_catalog.WORKSPACE_DIR", root):
                rows = ProjectCatalog().delivery_options("demo")
            ios = next(x for x in rows if x.target == "iOS")
            self.assertFalse(ios.available)
            self.assertEqual(ios.status, "準備中")
            self.assertIn("Apple署名", ios.guide)

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
