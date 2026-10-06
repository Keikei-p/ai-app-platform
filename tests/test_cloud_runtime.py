from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from src.core.cloud_runtime import CloudRuntimeReadinessVerifier
from src.core.config import resolve_state_dir
from src.core.platform_api import remote_bind_policy


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
            evidence.write_text(__import__("json").dumps(payload), encoding="utf-8")
            self.assertTrue(verifier.status()["verified"])

            (src / "platform_api.py").write_text("# changed\n", encoding="utf-8")
            stale = verifier.status()
            self.assertFalse(stale["verified"])
            self.assertTrue(stale["stale"])


if __name__ == "__main__":
    unittest.main()
