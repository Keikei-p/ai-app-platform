from __future__ import annotations

from pathlib import Path
import unittest

from src.core.chat_partner import ChatPartner
from src.core.redaction import redact_sensitive


ROOT=Path(__file__).resolve().parents[1]


class ProductCredentialRedactionTests(unittest.TestCase):
    def test_raw_provider_tokens_are_redacted(self):
        values=[
            "sk-"+"A"*32,
            "github_pat_"+"B"*32,
            "ghp_"+"C"*32,
            "AIza"+"D"*36,
            "AKIA"+"E"*16,
        ]
        for secret in values:
            redacted=redact_sensitive("credential "+secret)
            self.assertNotIn(secret,redacted)
            self.assertIn("REDACTED",redacted)

    def test_project_chat_state_redacts_before_persistence(self):
        state={"history":[]}
        secret="sk-"+"Z"*32
        ChatPartner._append(state,"user","my key is "+secret)
        self.assertNotIn(secret,state["history"][0]["content"])
        self.assertIn("REDACTED",state["history"][0]["content"])

    def test_ai_http_error_body_is_not_exposed(self):
        source=(ROOT/"src"/"core"/"llm_chat.py").read_text(encoding="utf-8")
        self.assertNotIn('detail = exc.read().decode',source)
        self.assertIn("Credentialと権限を確認",source)

    def test_conversation_store_redacts_before_sqlite_write(self):
        source=(ROOT/"src"/"core"/"workspace_catalog.py").read_text(encoding="utf-8")
        self.assertIn("clean = redact_sensitive(str(content))",source)
        self.assertIn('content = redact_sensitive(str(row.get("content") or ""))',source)


if __name__=="__main__":
    unittest.main()
