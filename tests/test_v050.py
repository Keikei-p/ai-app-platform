import http.client
import importlib.util
import json
import tempfile
import threading
import unittest
from pathlib import Path

from src.core.app_spec import AppSpec
from src.core.capability import CapabilityAssessor
from src.core.chat_partner import ChatPartner
from src.core.design_ai import DesignAI
from src.core.development_memory import DevelopmentMemory
from src.core.generator import StarterGenerator
from src.core.mobile_generator import MobileGenerator
from src.core.test_runner import ProjectTestRunner

class ChatPartnerTests(unittest.TestCase):
    def test_conversation_can_start_before_project_requirements(self):
        chat = ChatPartner()
        greeting = chat.opening_response("こんにちは")
        self.assertIsNotNone(greeting)
        self.assertIn("作りたい", greeting)
        consult = chat.opening_response("まだ何を作るか決まってないので相談したい")
        self.assertIsNotNone(consult)
        self.assertIn("一緒に", consult)

    def test_chat_collects_requirements_then_requires_explicit_approval(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            memory = DevelopmentMemory(root / "memory.jsonl")
            chat = ChatPartner(memory)

            d1 = chat.handle(root, "予約", "booking", "美容室の予約アプリを作りたい", has_generated=False)
            self.assertEqual(d1.action, "ask")
            self.assertIn("誰が使って", d1.message)

            d2 = chat.handle(root, "予約", "booking", "お客さんがスタッフを選び、空いている日時を予約する", has_generated=False)
            self.assertEqual(d2.action, "ask")
            self.assertIn("どこで使いますか", d2.message)

            d3 = chat.handle(root, "予約", "booking", "スマホ両方", has_generated=False)
            self.assertEqual(d3.action, "ask")
            self.assertIn("必要な機能", d3.message)

            d4 = chat.handle(root, "予約", "booking", "ログイン、データ保存、通知", has_generated=False)
            self.assertEqual(d4.action, "ask")
            self.assertIn("見た目", d4.message)

            d5 = chat.handle(root, "予約", "booking", "最先端で洗練されたデザイン", has_generated=False)
            self.assertEqual(d5.action, "review")
            self.assertIn("この内容で作る", d5.message)
            self.assertTrue(chat.state(root).get("awaiting_confirmation"))

            d6 = chat.handle(root, "予約", "booking", "この内容で作る", has_generated=False)
            self.assertEqual(d6.action, "build")
            self.assertIn("android", d6.instruction)
            self.assertIn("ios", d6.instruction)
            self.assertIn("modern", d6.instruction)

    def test_initial_build_never_starts_without_confirmation(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            chat = ChatPartner(DevelopmentMemory(root / "memory.jsonl"))
            d1 = chat.handle(
                root,
                "Todo",
                "todo",
                "営業担当が案件ごとにタスクを登録して期限と完了状況を管理するWebアプリを作りたい。ログインとデータ保存が必要。最先端で洗練されたデザイン。",
                has_generated=False,
            )
            self.assertEqual(d1.action, "review")
            self.assertNotEqual(d1.action, "build")
            d2 = chat.handle(root, "Todo", "todo", "いい感じだね", has_generated=False)
            self.assertEqual(d2.action, "review")
            d3 = chat.handle(root, "Todo", "todo", "この内容で作る", has_generated=False)
            self.assertEqual(d3.action, "build")

    def test_correction_is_learned(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            memory = DevelopmentMemory(root / "memory.jsonl")
            chat = ChatPartner(memory)
            # Seed a completed state directly through the conversation.
            chat.handle(root, "Demo", "demo", "WebでおしゃれなToDoアプリ", has_generated=False)
            # If one requirement remains, answer it.
            state = chat.state(root)
            if state.get("pending"):
                chat.handle(root, "Demo", "demo", "おしゃれでスマート", has_generated=False)
            d = chat.handle(root, "Demo", "demo", "スマホでボタンが押しにくいから直して", has_generated=True)
            self.assertEqual(d.action, "build")
            lessons = [x.lesson for x in memory.recent()]
            self.assertTrue(any("44px" in x for x in lessons))

class GenerationV050Tests(unittest.TestCase):
    def _base(self, root: Path):
        (root / "project.json").write_text('{"name":"Demo","slug":"demo"}', encoding="utf-8")

    def test_design_gate_passes_generated_ui(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); self._base(root)
            spec = AppSpec("Demo", "demo", "おしゃれな予約アプリ", "booking", [], ["web"])
            spec.save(root); StarterGenerator().generate_from_spec(root, spec)
            review = DesignAI().review(root)
            self.assertTrue(review.passed, review.findings)
            self.assertGreaterEqual(review.score, 88)
            html = (root / "index.html").read_text(encoding="utf-8")
            self.assertNotIn("AI App Platform", html)
            self.assertIn("empty-state", html)

    def test_mobile_source_generated_for_android_ios(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); self._base(root)
            spec = AppSpec("Demo", "demo", "スマホアプリ", "generic", [], ["android", "ios"])
            spec.save(root); StarterGenerator().generate_from_spec(root, spec); MobileGenerator().generate(root, spec)
            self.assertTrue((root / "mobile" / "App.tsx").is_file())
            package = json.loads((root / "mobile" / "package.json").read_text(encoding="utf-8"))
            self.assertEqual(package["dependencies"]["expo"], "~57.0.0")
            results = ProjectTestRunner().run(root)
            self.assertTrue(all(x.passed for x in results), results)

    def test_mobile_binary_gap_is_explicit(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); self._base(root)
            spec = AppSpec("Demo", "demo", "スマホアプリ", "generic", [], ["android", "ios"])
            spec.save(root); StarterGenerator().generate_from_spec(root, spec); MobileGenerator().generate(root, spec)
            gaps = CapabilityAssessor().assess(spec, root)
            keys = {g.key for g in gaps}
            self.assertIn("android_binary", keys)
            self.assertIn("ios_binary", keys)

    def test_fullstack_register_login_crud_and_isolation(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); self._base(root)
            spec = AppSpec("Demo", "demo", "ログインと保存", "todo", ["authentication", "database"], ["web"])
            spec.save(root); StarterGenerator().generate_from_spec(root, spec)
            results = ProjectTestRunner().run(root)
            self.assertTrue(all(x.passed for x in results), results)

            server_path = root / "server.py"
            modspec = importlib.util.spec_from_file_location("generated_server_test", server_path)
            module = importlib.util.module_from_spec(modspec); modspec.loader.exec_module(module)
            server = module.ThreadingHTTPServer(("127.0.0.1", 0), module.Handler)
            thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
            port = server.server_address[1]
            try:
                cookie1, csrf1 = self._register(port, "a@example.com", "passwordA1")
                self._request(port, "POST", "/api/items", {"title":"mine","value":"1"}, cookie1, csrf1, 201)
                data = self._request(port, "GET", "/api/items", None, cookie1, None, 200)
                self.assertEqual([x["title"] for x in data["items"]], ["mine"])

                cookie2, csrf2 = self._register(port, "b@example.com", "passwordB1")
                data2 = self._request(port, "GET", "/api/items", None, cookie2, None, 200)
                self.assertEqual(data2["items"], [])
                # Account deletion invalidates the session and removes owned data.
                self._request(port, "POST", "/api/account", {"current_password":"passwordA1"}, cookie1, csrf1, 200)
                self._request(port, "GET", "/api/me", None, cookie1, None, 401)
            finally:
                server.shutdown(); server.server_close()

    def _register(self, port, email, password):
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
        body = json.dumps({"email":email,"password":password})
        conn.request("POST", "/api/register", body=body, headers={"Content-Type":"application/json"})
        r = conn.getresponse(); data = json.loads(r.read()); self.assertEqual(r.status, 201, data)
        cookie = r.getheader("Set-Cookie").split(";", 1)[0]
        conn.close()
        me = self._request(port, "GET", "/api/me", None, cookie, None, 200)
        return cookie, me["csrf"]

    def _request(self, port, method, path, payload, cookie, csrf, expected):
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
        headers = {}
        body = None
        if payload is not None:
            body = json.dumps(payload); headers["Content-Type"] = "application/json"
        if cookie: headers["Cookie"] = cookie
        if csrf: headers["X-CSRF-Token"] = csrf
        conn.request(method, path, body=body, headers=headers)
        r = conn.getresponse(); raw = r.read(); data = json.loads(raw or b"{}")
        self.assertEqual(r.status, expected, data)
        conn.close(); return data

if __name__ == "__main__":
    unittest.main()
