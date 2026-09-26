import tempfile
import unittest
import uuid
from pathlib import Path
from src.core.safety import SafetyGate
from src.core.permissions import PermissionEngine
from src.core.remote import RemoteCommand, sign_command, verify_command, RemoteCommandGate
from src.core.generator import StarterGenerator
from src.core.app_spec import AppSpec
from src.core.planner import IntentPlanner
from src.core.test_runner import ProjectTestRunner
from src.core.billing import EntitlementEngine
from src.core.workers import JobRouter
from src.core.platforms import PlatformPlanner
from src.core.cloud_profiles import CloudProfile, CloudDeploymentPlanner
from src.core.worker_executor import WorkerExecutor
from src.core.approval import ApprovalStore
from src.core.readiness import ReadinessChecker
from src.core.backup import BackupManager
from src.core.risk_report import ReleaseRiskAssessor
from src.core.redaction import redact_sensitive
from src.core.project_manager import ProjectManager
from src.core.code_vault import CodeVault
import zipfile

class SafetyTests(unittest.TestCase):
    def test_normal_allowed(self):
        d = SafetyGate().check("家計簿アプリを作って")
        self.assertTrue(d.allowed); self.assertFalse(d.requires_human_review)
    def test_malware_blocked(self):
        self.assertFalse(SafetyGate().check("キーロガーを作って").allowed)
    def test_high_risk_review(self):
        d = SafetyGate().check("患者の医療診断アプリ")
        self.assertTrue(d.allowed); self.assertTrue(d.requires_human_review)

class PermissionTests(unittest.TestCase):
    def test_production_requires_approval(self):
        d = PermissionEngine().decide("production_deploy")
        self.assertFalse(d.allowed); self.assertTrue(d.requires_approval)
    def test_constitution_block(self):
        self.assertFalse(PermissionEngine().decide("disable_safety", approved=True).allowed)

class PlannerTests(unittest.TestCase):
    def test_booking_plan(self):
        p = IntentPlanner().plan("Salon", "salon", "ログイン付き予約アプリをiPhoneとAndroidで作って")
        self.assertEqual(p.spec.app_type, "booking")
        self.assertIn("authentication", p.spec.features)
        self.assertIn("ios", p.spec.targets); self.assertIn("android", p.spec.targets)

class GeneratorTests(unittest.TestCase):
    def test_escapes_user_html(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root/"project.json").write_text('{"name":"Test"}', encoding="utf-8")
            spec = AppSpec("<script>alert(1)</script>", "test", "<img src=x onerror=alert(1)>", "generic", [], ["web"])
            spec.save(root)
            StarterGenerator().generate_from_spec(root, spec)
            html_text = (root/"index.html").read_text(encoding="utf-8")
            self.assertNotIn("<script>alert(1)</script>", html_text)
            self.assertNotIn("<img src=x onerror=alert(1)>", html_text)
            self.assertIn("&lt;script&gt;", html_text)

    def test_generates_and_tests(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root/"project.json").write_text('{"name":"Test"}', encoding="utf-8")
            spec = AppSpec("Test", "test", "ToDo", "todo", [], ["web"])
            spec.save(root)
            StarterGenerator().generate_from_spec(root, spec)
            results = ProjectTestRunner().run(root)
            self.assertTrue(all(x.passed for x in results))

REMOTE_SECRET = b"r" * 32

class RemoteTests(unittest.TestCase):
    def test_signature(self):
        c = RemoteCommand("1",100,200,"build_preview",None,{})
        s = sign_command(c,REMOTE_SECRET)
        self.assertTrue(verify_command(c,s,REMOTE_SECRET,now=150))
        self.assertFalse(verify_command(c,s,b"o"*32,now=150))
    def test_replay_rejected(self):
        cid = "test-" + uuid.uuid4().hex
        c = RemoteCommand(cid,100,200,"status",None,{})
        s = sign_command(c,REMOTE_SECRET)
        gate = RemoteCommandGate(REMOTE_SECRET)
        self.assertTrue(gate.accept(c,s,now=150).accepted)
        self.assertFalse(gate.accept(c,s,now=150).accepted)

    def test_short_remote_secret_rejected(self):
        c = RemoteCommand("short-secret",100,200,"status",None,{})
        with self.assertRaises(ValueError):
            sign_command(c,b"short")

    def test_invalid_project_slug_rejected(self):
        c = RemoteCommand("bad-slug",100,200,"test","../../outside",{})
        with self.assertRaises(ValueError):
            sign_command(c,REMOTE_SECRET)

    def test_non_allowlisted_remote_action_rejected_even_if_approved_flag(self):
        c = RemoteCommand("prod-action",100,200,"production_deploy","demo",{})
        s = sign_command(c,REMOTE_SECRET)
        gate = RemoteCommandGate(REMOTE_SECRET)
        r = gate.accept(c,s,approved=True,now=150)
        self.assertFalse(r.accepted)
        self.assertEqual(r.reason, "remote_action_not_allowlisted")

class BillingWorkerTests(unittest.TestCase):
    def test_free_has_no_hosted_worker(self):
        self.assertFalse(EntitlementEngine().check("free", "hosted_worker").allowed)
        self.assertEqual(JobRouter().route("free", False).worker_mode, "unavailable")
    def test_cloud_routes_hosted(self):
        self.assertEqual(JobRouter().route("cloud", False).worker_mode, "hosted")

class WorkerSafetyTests(unittest.TestCase):
    def test_no_generic_shell(self):
        r = WorkerExecutor().execute("shell", None, {"cmd":"whoami"})
        self.assertFalse(r.ok)

    def test_path_traversal_rejected(self):
        r = WorkerExecutor().execute("build_preview", "../../etc", {})
        self.assertFalse(r.ok)
        self.assertEqual(r.data.get("error"), "invalid_project_slug")

class ApprovalTests(unittest.TestCase):
    def test_one_time_approval(self):
        store = ApprovalStore()
        req = store.create("production_deploy", "demo")
        self.assertTrue(store.approve(req.request_id, "human-test"))
        self.assertTrue(store.consume(req.request_id, "production_deploy", "demo"))
        self.assertFalse(store.consume(req.request_id, "production_deploy", "demo"))

class AdapterTests(unittest.TestCase):
    def test_ios_needs_mac(self):
        p = PlatformPlanner().plan("ios", "windows")
        self.assertFalse(p.possible_on_current_worker)
    def test_cloud_plan_is_dry_run(self):
        p = CloudDeploymentPlanner().plan(CloudProfile("x","cloudflare"), "demo")
        self.assertTrue(p.dry_run); self.assertIn("request_human_approval_before_production", p.steps)

class ProjectManagerTests(unittest.TestCase):
    def test_project_rename_keeps_slug(self):
        import src.core.project_manager as pm_mod
        import src.core.database as db_mod
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            old_workspace = pm_mod.WORKSPACE_DIR
            old_db = db_mod.DB_PATH
            old_db_workspace = db_mod.WORKSPACE_DIR
            try:
                pm_mod.WORKSPACE_DIR = root / "workspace"
                pm_mod.WORKSPACE_DIR.mkdir(parents=True)
                db_mod.DB_PATH = root / "data" / "platform.db"
                db_mod.DB_PATH.parent.mkdir(parents=True)
                db_mod.WORKSPACE_DIR = pm_mod.WORKSPACE_DIR
                manager = ProjectManager()
                slug, project_dir = manager.create("Old Name")
                gitignore = (project_dir / ".gitignore").read_text(encoding="utf-8")
                self.assertIn(".vault/", gitignore)
                self.assertIn(".env", gitignore)
                manager.rename(slug, "New Name")
                meta = __import__("json").loads((project_dir / "project.json").read_text(encoding="utf-8"))
                self.assertEqual(meta["name"], "New Name")
                self.assertEqual(meta["slug"], slug)
                rows = db_mod.list_projects()
                self.assertTrue(any(r["slug"] == slug and r["name"] == "New Name" for r in rows))
            finally:
                pm_mod.WORKSPACE_DIR = old_workspace
                db_mod.DB_PATH = old_db
                db_mod.WORKSPACE_DIR = old_db_workspace


class CodeVaultTests(unittest.TestCase):
    def _with_isolated_vault(self):
        import src.core.code_vault as vault_mod
        import src.core.database as db_mod
        td = tempfile.TemporaryDirectory()
        root = Path(td.name)
        old_workspace = vault_mod.WORKSPACE_DIR
        old_db = db_mod.DB_PATH
        old_db_workspace = db_mod.WORKSPACE_DIR
        vault_mod.WORKSPACE_DIR = root / "workspace"
        vault_mod.WORKSPACE_DIR.mkdir(parents=True)
        db_mod.DB_PATH = root / "data" / "platform.db"
        db_mod.DB_PATH.parent.mkdir(parents=True)
        db_mod.WORKSPACE_DIR = vault_mod.WORKSPACE_DIR
        project = vault_mod.WORKSPACE_DIR / "demo"
        project.mkdir()
        (project / "project.json").write_text('{"name":"Demo","slug":"demo"}', encoding="utf-8")
        return td, project, vault_mod, db_mod, old_workspace, old_db, old_db_workspace

    def _restore_globals(self, td, vault_mod, db_mod, old_workspace, old_db, old_db_workspace):
        vault_mod.WORKSPACE_DIR = old_workspace
        db_mod.DB_PATH = old_db
        db_mod.WORKSPACE_DIR = old_db_workspace
        td.cleanup()

    def test_save_diff_restore_is_reversible(self):
        ctx = self._with_isolated_vault()
        td, project, vault_mod, db_mod, old_workspace, old_db, old_db_workspace = ctx
        try:
            (project / "app.txt").write_text("one\n", encoding="utf-8")
            vault = CodeVault()
            first = vault.save("demo", "first")
            valid, reason = vault.validate_version("demo", first.version_id)
            self.assertTrue(valid, reason)
            (project / "app.txt").write_text("two\n", encoding="utf-8")
            (project / "new.txt").write_text("new\n", encoding="utf-8")
            diff = vault.diff("demo", first.version_id)
            self.assertIn("app.txt", diff.modified)
            self.assertIn("new.txt", diff.added)
            safety = vault.restore("demo", first.version_id, confirmed=True)
            self.assertEqual((project / "app.txt").read_text(encoding="utf-8"), "one\n")
            self.assertFalse((project / "new.txt").exists())
            self.assertTrue(any(v.version_id == safety.version_id and v.kind == "pre-restore" for v in vault.list_versions("demo")))
        finally:
            self._restore_globals(*ctx[:1], ctx[2], ctx[3], ctx[4], ctx[5], ctx[6])

    def test_secrets_are_not_stored(self):
        ctx = self._with_isolated_vault()
        td, project, vault_mod, db_mod, old_workspace, old_db, old_db_workspace = ctx
        try:
            (project / "app.py").write_text("print('ok')", encoding="utf-8")
            (project / ".env").write_text("TOKEN=secret", encoding="utf-8")
            (project / "server.key").write_text("private", encoding="utf-8")
            vault = CodeVault()
            version = vault.save("demo", "secret-test")
            meta = vault._metadata("demo", version.version_id)
            self.assertIn("app.py", meta["files"])
            self.assertNotIn(".env", meta["files"])
            self.assertNotIn("server.key", meta["files"])
        finally:
            self._restore_globals(*ctx[:1], ctx[2], ctx[3], ctx[4], ctx[5], ctx[6])

    def test_restore_failure_rolls_back_to_current_state(self):
        ctx = self._with_isolated_vault()
        td, project, vault_mod, db_mod, old_workspace, old_db, old_db_workspace = ctx
        try:
            (project / "app.txt").write_text("version-one", encoding="utf-8")
            vault = CodeVault()
            target = vault.save("demo", "target")
            (project / "app.txt").write_text("current-two", encoding="utf-8")
            original_replace = vault._replace_project_contents
            calls = {"n": 0}
            def fail_once(project_path, content_path):
                calls["n"] += 1
                if calls["n"] == 1:
                    (project_path / "app.txt").write_text("partial-bad", encoding="utf-8")
                    raise OSError("simulated restore write failure")
                return original_replace(project_path, content_path)
            vault._replace_project_contents = fail_once
            with self.assertRaises(OSError):
                vault.restore("demo", target.version_id, confirmed=True)
            self.assertEqual((project / "app.txt").read_text(encoding="utf-8"), "current-two")
        finally:
            self._restore_globals(*ctx[:1], ctx[2], ctx[3], ctx[4], ctx[5], ctx[6])

    def test_tampered_version_is_rejected(self):
        ctx = self._with_isolated_vault()
        td, project, vault_mod, db_mod, old_workspace, old_db, old_db_workspace = ctx
        try:
            (project / "app.txt").write_text("safe", encoding="utf-8")
            vault = CodeVault()
            version = vault.save("demo", "safe")
            version_dir = vault._version_dir("demo", version.version_id)
            (version_dir / "content" / "app.txt").write_text("tampered", encoding="utf-8")
            valid, _ = vault.validate_version("demo", version.version_id)
            self.assertFalse(valid)
            with self.assertRaises(ValueError):
                vault.restore("demo", version.version_id, confirmed=True)
        finally:
            self._restore_globals(*ctx[:1], ctx[2], ctx[3], ctx[4], ctx[5], ctx[6])

class ReadinessBackupRiskTests(unittest.TestCase):
    def test_readiness_report_has_core_checks(self):
        r = ReadinessChecker().run()
        keys = {x.key for x in r.checks}
        self.assertIn("python", keys)
        self.assertIn("sqlite", keys)
        self.assertIn("workspace_dir", keys)

    def test_backup_create_and_validate(self):
        manager = BackupManager()
        result = manager.create("unit-test")
        self.assertTrue(result.ok)
        path = Path(result.path)
        valid, reason = manager.validate(path)
        self.assertTrue(valid, reason)
        path.unlink(missing_ok=True)

    def test_risk_report_adds_payment_review(self):
        spec = AppSpec("Pay", "pay", "決済アプリ", "generic", ["payments"], ["web"])
        rows = ReleaseRiskAssessor().assess(spec)
        self.assertTrue(any(x.key == "payments" and x.severity == "high" for x in rows))

    def test_backup_rejects_zip_slip(self):
        manager = BackupManager()
        with tempfile.TemporaryDirectory() as td:
            evil = Path(td) / "evil.zip"
            with zipfile.ZipFile(evil, "w") as z:
                z.writestr("backup_manifest.json", "{}")
                z.writestr("../escape.txt", "bad")
            valid, reason = manager.validate(evil)
            self.assertFalse(valid)
            self.assertIn("unsafe", reason)

    def test_log_redaction(self):
        text = redact_sensitive("token=abc123456 password:hello Bearer abcdefghijk")
        self.assertNotIn("abc123456", text)
        self.assertNotIn("hello", text)
        self.assertNotIn("abcdefghijk", text)


if __name__ == "__main__": unittest.main()

class UpdateEngineTests(unittest.TestCase):
    def _make_source(self, root: Path, version: str, content: str) -> None:
        (root / "src" / "core").mkdir(parents=True, exist_ok=True)
        (root / "tests").mkdir(parents=True, exist_ok=True)
        (root / "src" / "core" / "demo.py").write_text(content, encoding="utf-8")
        (root / "tests" / "test_demo.py").write_text("# update test\n", encoding="utf-8")
        (root / "VERSION").write_text(version + "\n", encoding="utf-8")
        (root / "README.md").write_text("demo\n", encoding="utf-8")

    def _engine(self, app: Path, state: Path, *, validator=None):
        from src.core.update_engine import UpdateEngine
        return UpdateEngine(
            app_dir=app,
            state_dir=state,
            current_version="0.4.6",
            validator=validator or (lambda _p: (True, "ok")),
            state_backup_callback=lambda _label: (True, "state-backup.zip"),
            audit_callback=lambda *a, **k: None,
        )

    def test_update_package_applies_verified_files(self):
        from src.core.update_engine import build_update_package
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            app, source, state = root / "app", root / "source", root / "state"
            self._make_source(app, "0.4.6", "OLD = True\n")
            self._make_source(source, "0.4.7", "NEW = True\n")
            package = root / "update.aipupdate"
            build_update_package(source, package, version="0.4.7", notes="test")
            engine = self._engine(app, state)
            candidate = engine.inspect_package(package)
            self.assertEqual(candidate.version, "0.4.7")
            result = engine.apply(candidate)
            self.assertTrue(result.ok, result.message)
            self.assertIn("NEW = True", (app / "src" / "core" / "demo.py").read_text(encoding="utf-8"))
            self.assertEqual((app / "VERSION").read_text(encoding="utf-8").strip(), "0.4.7")

    def test_tampered_update_payload_is_rejected(self):
        from src.core.update_engine import build_update_package
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            source, state, app = root / "source", root / "state", root / "app"
            self._make_source(app, "0.4.6", "OLD = True\n")
            self._make_source(source, "0.4.7", "NEW = True\n")
            package = root / "update.aipupdate"
            build_update_package(source, package, version="0.4.7")
            tampered = root / "tampered.aipupdate"
            with zipfile.ZipFile(package, "r") as zin, zipfile.ZipFile(tampered, "w", compression=zipfile.ZIP_DEFLATED) as zout:
                for info in zin.infolist():
                    data = zin.read(info.filename)
                    if info.filename == "payload/src/core/demo.py":
                        data = b"TAMPERED = True\n"
                    zout.writestr(info, data)
            engine = self._engine(app, state)
            with self.assertRaises(ValueError):
                engine.inspect_package(tampered)

    def test_update_forbidden_path_is_rejected(self):
        import hashlib, json
        from datetime import datetime, timezone
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            app, state = root / "app", root / "state"
            self._make_source(app, "0.4.6", "OLD = True\n")
            package = root / "bad.aipupdate"
            data = b"bad"
            manifest = {
                "format": 1,
                "product": "AI App Platform",
                "version": "0.4.7",
                "created_at": datetime.now(timezone.utc).isoformat(),
                "notes": "",
                "files": [{"path": "../outside.txt", "sha256": hashlib.sha256(data).hexdigest(), "size": len(data)}],
                "delete": [],
            }
            with zipfile.ZipFile(package, "w", compression=zipfile.ZIP_DEFLATED) as z:
                z.writestr("update_manifest.json", json.dumps(manifest))
                z.writestr("payload/../outside.txt", data)
            engine = self._engine(app, state)
            with self.assertRaises(ValueError):
                engine.inspect_package(package)

    def test_failed_post_update_check_rolls_back_program_files(self):
        from src.core.update_engine import build_update_package
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            app, source, state = root / "app", root / "source", root / "state"
            self._make_source(app, "0.4.6", "OLD = True\n")
            self._make_source(source, "0.4.7", "NEW = True\n")
            package = root / "update.aipupdate"
            build_update_package(source, package, version="0.4.7")
            calls = {"n": 0}
            def validator(_path):
                calls["n"] += 1
                return (True, "pre-ok") if calls["n"] == 1 else (False, "simulated post failure")
            engine = self._engine(app, state, validator=validator)
            candidate = engine.inspect_package(package)
            result = engine.apply(candidate)
            self.assertFalse(result.ok)
            self.assertTrue(result.rolled_back, result.message)
            self.assertIn("OLD = True", (app / "src" / "core" / "demo.py").read_text(encoding="utf-8"))
            self.assertEqual((app / "VERSION").read_text(encoding="utf-8").strip(), "0.4.6")

    def test_same_or_older_version_is_rejected(self):
        from src.core.update_engine import build_update_package
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            app, source, state = root / "app", root / "source", root / "state"
            self._make_source(app, "0.4.6", "OLD = True\n")
            self._make_source(source, "0.4.6", "SAME = True\n")
            package = root / "same.aipupdate"
            build_update_package(source, package, version="0.4.6")
            engine = self._engine(app, state)
            with self.assertRaises(ValueError):
                engine.inspect_package(package)

class UpdateSizeLimitTests(unittest.TestCase):
    def test_oversized_declared_file_is_rejected(self):
        import hashlib, json
        from datetime import datetime, timezone
        from src.core.update_engine import UpdateEngine, MAX_UPDATE_FILE_BYTES
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            app, state = root / "app", root / "state"
            (app / "src").mkdir(parents=True)
            (app / "VERSION").write_text("0.4.6\n", encoding="utf-8")
            package = root / "oversize.aipupdate"
            data = b"tiny"
            manifest = {
                "format": 1,
                "product": "AI App Platform",
                "version": "0.4.7",
                "created_at": datetime.now(timezone.utc).isoformat(),
                "notes": "",
                "files": [{
                    "path": "src/demo.py",
                    "sha256": hashlib.sha256(data).hexdigest(),
                    "size": MAX_UPDATE_FILE_BYTES + 1,
                }],
                "delete": [],
            }
            with zipfile.ZipFile(package, "w", compression=zipfile.ZIP_DEFLATED) as z:
                z.writestr("update_manifest.json", json.dumps(manifest))
                z.writestr("payload/src/demo.py", data)
            engine = UpdateEngine(
                app_dir=app,
                state_dir=state,
                current_version="0.4.6",
                validator=lambda _p: (True, "ok"),
                state_backup_callback=lambda _label: (True, "state.zip"),
                audit_callback=lambda *a, **k: None,
            )
            with self.assertRaises(ValueError):
                engine.inspect_package(package)

class RemoteDeviceAndServerTests(unittest.TestCase):
    def test_pairing_code_is_one_time(self):
        from src.core.remote_pairing import PairingManager
        p = PairingManager(ttl_seconds=300, max_attempts=3)
        t = p.create(now=100)
        self.assertTrue(p.consume(t.code, now=101))
        self.assertFalse(p.consume(t.code, now=102))

    def test_pairing_code_expires(self):
        from src.core.remote_pairing import PairingManager
        p = PairingManager(ttl_seconds=60)
        t = p.create(now=100)
        self.assertFalse(p.consume(t.code, now=161))

    def test_device_store_pair_and_revoke(self):
        from src.core.remote_devices import RemoteDeviceStore
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            store = RemoteDeviceStore(root/'devices.json', root/'settings.json')
            device, secret = store.pair('Phone')
            self.assertGreaterEqual(len(secret), 32)
            self.assertEqual(store.secret_for(device.device_id), secret)
            self.assertTrue(store.revoke(device.device_id))
            self.assertIsNone(store.secret_for(device.device_id))

    def test_device_store_does_not_write_raw_secret_field(self):
        import json
        from src.core.remote_devices import RemoteDeviceStore
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            store = RemoteDeviceStore(root/'devices.json', root/'settings.json')
            store.pair('Phone')
            raw = json.loads((root/'devices.json').read_text(encoding='utf-8'))
            device = raw['devices'][0]
            self.assertNotIn('secret_b64', device)
            self.assertIn('secret_protected', device)

    def test_signed_command_accepts_then_replay_rejects(self):
        import time
        from src.core.remote_devices import RemoteDeviceStore
        from src.core.remote_server import RemoteServerController
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            store = RemoteDeviceStore(root/'devices.json', root/'settings.json')
            controller = RemoteServerController(store)
            store.set_enabled(True)
            device, secret = store.pair('Phone')
            now = int(time.time())
            cmd = RemoteCommand('srv-'+uuid.uuid4().hex, now, now+120, 'status', None, {})
            sig = sign_command(cmd, secret)
            result = controller.execute_signed(device.device_id, cmd.__dict__, sig)
            self.assertTrue(result['ok'])
            with self.assertRaises(PermissionError):
                controller.execute_signed(device.device_id, cmd.__dict__, sig)

    def test_revoked_device_cannot_execute(self):
        import time
        from src.core.remote_devices import RemoteDeviceStore
        from src.core.remote_server import RemoteServerController
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            store = RemoteDeviceStore(root/'devices.json', root/'settings.json')
            controller = RemoteServerController(store)
            store.set_enabled(True)
            device, secret = store.pair('Phone')
            store.revoke(device.device_id)
            now = int(time.time())
            cmd = RemoteCommand('rev-'+uuid.uuid4().hex, now, now+120, 'status', None, {})
            sig = sign_command(cmd, secret)
            with self.assertRaises(PermissionError):
                controller.execute_signed(device.device_id, cmd.__dict__, sig)

    def test_non_allowlisted_remote_command_stays_blocked(self):
        import time
        from src.core.remote_devices import RemoteDeviceStore
        from src.core.remote_server import RemoteServerController
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            store = RemoteDeviceStore(root/'devices.json', root/'settings.json')
            controller = RemoteServerController(store)
            store.set_enabled(True)
            device, secret = store.pair('Phone')
            now = int(time.time())
            cmd = RemoteCommand('bad-'+uuid.uuid4().hex, now, now+120, 'production_deploy', None, {})
            sig = sign_command(cmd, secret)
            with self.assertRaises(PermissionError):
                controller.execute_signed(device.device_id, cmd.__dict__, sig)

    def test_http_pair_and_signed_status(self):
        import json, time, urllib.request
        from src.core.remote_devices import RemoteDeviceStore
        from src.core.remote_server import RemoteServerController
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            store = RemoteDeviceStore(root/'devices.json', root/'settings.json')
            controller = RemoteServerController(store)
            try:
                controller.start(lan=False, port=0)
                ticket = controller.create_pairing()
                base = f'http://127.0.0.1:{controller.port}'
                req = urllib.request.Request(base+'/api/pair', data=json.dumps({'code':ticket.code,'name':'Phone'}).encode(), headers={'Content-Type':'application/json'}, method='POST')
                with urllib.request.urlopen(req, timeout=3) as r:
                    pair = json.loads(r.read().decode())
                secret = __import__('base64').b64decode(pair['secret_b64'])
                now = int(time.time())
                cmd = RemoteCommand('http-'+uuid.uuid4().hex, now, now+120, 'status', None, {})
                sig = sign_command(cmd, secret)
                body = json.dumps({'command':cmd.__dict__,'signature':sig}, ensure_ascii=False).encode('utf-8')
                req2 = urllib.request.Request(base+'/api/command', data=body, headers={'Content-Type':'application/json','X-Device-ID':pair['device_id']}, method='POST')
                with urllib.request.urlopen(req2, timeout=3) as r:
                    result = json.loads(r.read().decode())
                self.assertTrue(result['ok'])
                self.assertEqual(result['action'], 'status')
            finally:
                controller.stop()

    def test_emergency_stop_disables_remote(self):
        from src.core.remote_devices import RemoteDeviceStore
        from src.core.remote_server import RemoteServerController
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            store = RemoteDeviceStore(root/'devices.json', root/'settings.json')
            controller = RemoteServerController(store)
            controller.start(lan=False, port=0)
            self.assertTrue(store.is_enabled())
            controller.stop(emergency=True)
            self.assertFalse(store.is_enabled())
