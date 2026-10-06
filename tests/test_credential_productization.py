from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import json
import unittest

from src.core.credential_store import CredentialStore, SessionCredentialBackend
from src.core.llm_chat import AIChatEngine
from src.core.connectors import ConnectorManager


class CredentialProductizationTests(unittest.TestCase):
    def test_ai_key_is_not_written_to_settings_json(self):
        with TemporaryDirectory() as tmp:
            root=Path(tmp)
            backend=SessionCredentialBackend()
            store=CredentialStore(backend=backend)
            settings=root/"settings.json"
            engine=AIChatEngine(settings, credential_store=store)
            secret="sk-test-credential-value-1234567890"
            engine.configure_provider("openai","test-model",secret,remember_key=True,make_default=True)

            raw=json.loads(settings.read_text(encoding="utf-8"))
            serialized=json.dumps(raw)
            self.assertNotIn(secret,serialized)
            self.assertNotIn("key_cipher",serialized)
            self.assertEqual(store.get("openai.api_key"),secret)
            self.assertTrue(engine.status().connected)

    def test_transient_credential_does_not_replace_persistent_backend(self):
        backend=SessionCredentialBackend()
        store=CredentialStore(backend=backend)
        store.set("openai.api_key","persistent-secret",remember=True)
        store.set("gemini.api_key","temporary-secret",remember=False)
        self.assertEqual(store.get("openai.api_key"),"persistent-secret")
        self.assertEqual(store.get("gemini.api_key"),"temporary-secret")
        self.assertEqual(store.status("gemini.api_key").backend,"session")

    def test_connector_public_state_masks_secret_and_config_file_has_no_secret(self):
        with TemporaryDirectory() as tmp:
            root=Path(tmp)
            store=CredentialStore(backend=SessionCredentialBackend())
            manager=ConnectorManager(credentials=store,config_path=root/"connectors.json")
            secret="github_pat_TEST_SECRET_1234567890"
            row=manager.configure(
                "github",
                config={"repository":"buyer/example"},
                credentials={"token":secret},
                remember=True,
            )
            self.assertNotIn(secret,json.dumps(row,ensure_ascii=False))
            self.assertTrue(row["credentials"]["token"]["configured"])
            self.assertIn("7890",row["credentials"]["token"]["masked"])
            self.assertNotIn(secret,(root/"connectors.json").read_text(encoding="utf-8"))

    def test_local_connectors_do_not_require_paid_service(self):
        with TemporaryDirectory() as tmp:
            manager=ConnectorManager(
                credentials=CredentialStore(backend=SessionCredentialBackend()),
                config_path=Path(tmp)/"connectors.json",
            )
            result=manager.test_connection("sqlite")
            self.assertTrue(result["ok"])
            self.assertEqual(result["status"],"connected")


if __name__=="__main__":
    unittest.main()
