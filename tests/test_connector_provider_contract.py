from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from src.core.connectors import ConnectorManager
from src.core.connector_providers import default_provider_registry
from src.core.credential_store import CredentialStore, SessionCredentialBackend


class ConnectorProviderContractTests(unittest.TestCase):
    def test_common_provider_interface_is_available(self):
        providers=default_provider_registry()
        for provider_id in ("openai","gemini","ollama","github","cloudflare","d1","vercel","netlify","supabase","sqlite","local_git"):
            provider=providers[provider_id]
            self.assertTrue(callable(provider.validate_configuration))
            self.assertTrue(callable(provider.test_connection))
            self.assertTrue(callable(provider.get_capabilities))

    def test_manager_exposes_common_connector_contract(self):
        with TemporaryDirectory() as tmp:
            manager=ConnectorManager(
                credentials=CredentialStore(backend=SessionCredentialBackend()),
                config_path=Path(tmp)/"connectors.json",
            )
            for name in ("connect","disconnect","test_connection","get_status","get_capabilities","validate_configuration"):
                self.assertTrue(callable(getattr(manager,name)))
            result=manager.validate_configuration("openai")
            self.assertFalse(result["valid"])
            self.assertTrue(result["issues"])

    def test_stale_success_does_not_survive_missing_credential(self):
        with TemporaryDirectory() as tmp:
            store=CredentialStore(backend=SessionCredentialBackend())
            path=Path(tmp)/"connectors.json"
            manager=ConnectorManager(credentials=store,config_path=path)
            store.set("github.token","github_pat_"+"A"*30)
            state={"github":{"config":{},"last_test":{"ok":True,"status":"connected","message":"ok","tested_at":"now"}}}
            manager._write(state)
            self.assertEqual(manager.get_status("github")["status"],"connected")
            store.delete("github.token")
            self.assertEqual(manager.get_status("github")["status"],"disconnected")


if __name__=="__main__":
    unittest.main()
