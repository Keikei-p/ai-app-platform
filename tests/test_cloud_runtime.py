from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
from http.server import ThreadingHTTPServer
from threading import Thread
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from unittest.mock import patch
import json
import unittest

from src.core.cloud_runtime import CloudRuntimeReadinessVerifier
from src.core.config import resolve_state_dir
from src.core.platform_api import PlatformAPI
from src.core.remote_access import remote_bind_policy


class CloudRuntimeTests(unittest.TestCase):
    def test_external_state_dir_override_is_deterministic(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            target = root / "persistent"
            resolved = resolve_state_dir(
                {"AI_APP_PLATFORM_STATE_DIR": str(target)},
                os_name="posix",
                home=root / "home",
            )
            self.assertEqual(resolved, target)

    def test_remote_bind_requires_explicit_opt_in_and_token(self):
        self.assertTrue(remote_bind_policy("127.0.0.1", {})["allowed"])
        self.assertFalse(remote_bind_policy(
            "0.0.0.0",
            {"AI_APP_LOCAL_API_TOKEN": "secret"},
        )["allowed"])
        self.assertFalse(remote_bind_policy(
            "0.0.0.0",
            {"AI_APP_ENABLE_REMOTE": "1"},
        )["allowed"])
        allowed = remote_bind_policy(
            "0.0.0.0",
            {
                "AI_APP_ENABLE_REMOTE": "1",
                "AI_APP_LOCAL_API_TOKEN": "secret",
            },
        )
        self.assertTrue(allowed["allowed"])
        self.assertTrue(allowed["requires_bearer"])

    def test_remote_mode_keeps_health_public_but_protects_api_reads(self):
        api = PlatformAPI(remote_mode=True)
        server = ThreadingHTTPServer(("127.0.0.1", 0), api.handler_class())
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        port = int(server.server_address[1])
        try:
            with patch.dict(
                "os.environ",
                {"AI_APP_LOCAL_API_TOKEN": "cloud-secret"},
                clear=False,
            ):
                health = json.loads(urlopen(
                    f"http://127.0.0.1:{port}/api/v1/healthz",
                    timeout=3,
                ).read().decode("utf-8"))
                self.assertEqual(health["status"], "ok")
                self.assertTrue(health["remote_mode"])

                with self.assertRaises(HTTPError) as denied:
                    urlopen(f"http://127.0.0.1:{port}/api/v1/status", timeout=3)
                self.assertEqual(denied.exception.code, 401)

                req = Request(
                    f"http://127.0.0.1:{port}/api/v1/status",
                    headers={"Authorization": "Bearer cloud-secret"},
                )
                allowed = json.loads(urlopen(req, timeout=3).read().decode("utf-8"))
                self.assertEqual(allowed["service"], "ai-app-platform")
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=3)

    def test_cloud_runtime_verifier_generates_strict_evidence(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            evidence = root / "cloud.json"
            verifier = CloudRuntimeReadinessVerifier(evidence_path=evidence)
            report = verifier.run()

            self.assertTrue(report["verified"])
            self.assertFalse(report["deployment_performed"])
            self.assertFalse(report["external_actions"])
            self.assertFalse(report["credentials_used"])
            self.assertFalse(report["paid_actions"])
            self.assertFalse(report["production_data_written"])
            self.assertTrue(all(report["checks"].values()))
            self.assertTrue(evidence.is_file())
            self.assertTrue(verifier.status()["verified"])

    def test_source_change_invalidates_cloud_readiness_evidence(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            src = root / "src/core"
            src.mkdir(parents=True)
            for rel in (
                "config.py",
                "platform_api.py",
                "remote_access.py",
                "cloud_runtime.py",
            ):
                (src / rel).write_text("# stable\n", encoding="utf-8")
            evidence = root / "cloud.json"
            verifier = CloudRuntimeReadinessVerifier(
                root_dir=root,
                evidence_path=evidence,
            )
            # This fixture cannot pass the semantic checks, so write a synthetic
            # structurally valid attestation using the current covered blobs.
            payload = {
                "verified": True,
                "checks": {"fixture": True},
                "source_blobs": verifier.source_blobs(),
                "created_at": "2026-10-06T00:00:00+00:00",
            }
            evidence.write_text(json.dumps(payload), encoding="utf-8")
            self.assertTrue(verifier.status()["verified"])

            (src / "platform_api.py").write_text("# changed\n", encoding="utf-8")
            stale = verifier.status()
            self.assertFalse(stale["verified"])
            self.assertTrue(stale["stale"])


if __name__ == "__main__":
    unittest.main()
