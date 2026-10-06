from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from src.core.credential_store import CredentialStore, SessionCredentialBackend
from src.core.llm_chat import AIChatEngine, ChatProviderStatus


class FallbackEngine(AIChatEngine):
    def __init__(self,path,store):
        super().__init__(path,credential_store=store)
        self.calls=[]

    def _openai_reply(self,*args,**kwargs):
        self.calls.append("openai")
        raise RuntimeError("openai down")

    def _gemini_reply(self,*args,**kwargs):
        self.calls.append("gemini")
        return "gemini fallback"

    def _ollama_reply(self,*args,**kwargs):
        self.calls.append("ollama")
        return "ollama fallback"


class AIProviderProductizationTests(unittest.TestCase):
    def test_paid_fallback_requires_explicit_order(self):
        with TemporaryDirectory() as tmp:
            store=CredentialStore(backend=SessionCredentialBackend())
            engine=FallbackEngine(Path(tmp)/"settings.json",store)
            store.set("openai.api_key","openai-secret")
            store.set("gemini.api_key","gemini-secret")
            engine.configure_provider("openai","model-a",make_default=True)
            engine.configure_provider("gemini","model-b")
            reply=engine.reply_resilient([],"hello","system")
            self.assertEqual(reply,"ollama fallback")
            self.assertEqual(engine.calls,["openai","ollama"])

    def test_explicit_paid_fallback_is_used_before_local(self):
        with TemporaryDirectory() as tmp:
            store=CredentialStore(backend=SessionCredentialBackend())
            engine=FallbackEngine(Path(tmp)/"settings.json",store)
            store.set("openai.api_key","openai-secret")
            store.set("gemini.api_key","gemini-secret")
            engine.configure_provider("openai","model-a",make_default=True)
            engine.configure_provider("gemini","model-b")
            engine.configure_fallback_order(["gemini"])
            reply=engine.reply_resilient([],"hello","system")
            self.assertEqual(reply,"gemini fallback")
            self.assertEqual(engine.calls,["openai","gemini"])

    def test_ollama_can_be_primary_without_api_key(self):
        with TemporaryDirectory() as tmp:
            store=CredentialStore(backend=SessionCredentialBackend())
            engine=FallbackEngine(Path(tmp)/"settings.json",store)
            engine.configure_provider("ollama","qwen2.5:7b",make_default=True,base_url="http://127.0.0.1:11434")
            self.assertTrue(engine.status().connected)
            self.assertEqual(engine.reply_resilient([],"hello","system"),"ollama fallback")


if __name__=="__main__":
    unittest.main()
