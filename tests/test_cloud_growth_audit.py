import json
import tempfile
import unittest
from pathlib import Path

from src.tools.cloud_growth_audit import (
    ATTESTATIONS, ATTESTATION_CONTRACTS, CRITICAL_SOURCES, blob_sha, inspect,
)


class CloudGrowthAuditTests(unittest.TestCase):
    def make_checkout(self, root):
        for source in CRITICAL_SOURCES:
            path = root / source
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"# known source\n")
        for name in ATTESTATIONS:
            contract = ATTESTATION_CONTRACTS[name]
            sources = {}
            for source in contract["required_sources"]:
                file = root / source
                file.parent.mkdir(parents=True, exist_ok=True)
                file.write_bytes(b"# known source\n")
                sources[source] = blob_sha(file.read_bytes())
            path = root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                json.dumps({
                    "schema_version": 1,
                    "kind": contract["kind"],
                    "verified": True,
                    "source_blobs": sources,
                }),
                encoding="utf-8",
            )

    def test_valid_checkout_reports_static_attestations_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_checkout(root)
            report = inspect(root)
            self.assertTrue(report["all_source_checks_passed"], report["issues"])
            self.assertEqual(report["issues"], [])
            self.assertFalse(report["actual_source_changes"])
            self.assertFalse(report["real_24h_soak_verified"])
            self.assertFalse(report["physical_pc_reboot_verified"])
            self.assertFalse(report["buyer_release_approved"])

    def test_changed_source_rejects_stale_attestation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_checkout(root)
            (root / CRITICAL_SOURCES[0]).write_bytes(b"# changed\n")
            report = inspect(root)
            self.assertFalse(report["all_source_checks_passed"])
            self.assertTrue(any("attestation_stale" in x for x in report["issues"]))

    def test_malformed_or_future_evidence_is_never_accepted(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_checkout(root)
            evidence = root / ATTESTATIONS[0]
            evidence.write_text("[]", encoding="utf-8")
            report = inspect(root)
            self.assertFalse(report["all_source_checks_passed"])
            self.assertIn("attestation_unverified:" + ATTESTATIONS[0], report["issues"])

    def test_paths_outside_checkout_are_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_checkout(root)
            evidence = root / ATTESTATIONS[0]
            raw = json.loads(evidence.read_text(encoding="utf-8"))
            raw["source_blobs"]["src/../../private.txt"] = "0" * 40
            evidence.write_text(json.dumps(raw), encoding="utf-8")
            report = inspect(root)
            self.assertFalse(report["all_source_checks_passed"])
            self.assertIn("attestation_stale_or_invalid:" + ATTESTATIONS[0], report["issues"])

    def test_incomplete_attestation_cannot_claim_verified(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_checkout(root)
            evidence = root / ATTESTATIONS[0]
            raw = json.loads(evidence.read_text(encoding="utf-8"))
            raw["source_blobs"] = {
                CRITICAL_SOURCES[0]: blob_sha((root / CRITICAL_SOURCES[0]).read_bytes())
            }
            evidence.write_text(json.dumps(raw), encoding="utf-8")
            report = inspect(root)
            self.assertFalse(report["all_source_checks_passed"])
            self.assertIn("attestation_unverified:" + ATTESTATIONS[0], report["issues"])

    def test_wrong_kind_future_schema_and_invalid_hash_fail_closed(self):
        for fault in ("kind", "version", "hash"):
            with self.subTest(fault=fault):
                with tempfile.TemporaryDirectory() as tmp:
                    root = Path(tmp)
                    self.make_checkout(root)
                    evidence = root / ATTESTATIONS[1]
                    raw = json.loads(evidence.read_text(encoding="utf-8"))
                    if fault == "kind":
                        raw["kind"] = "unrelated_evidence"
                    elif fault == "version":
                        raw["schema_version"] = 999
                    else:
                        source = next(iter(raw["source_blobs"]))
                        raw["source_blobs"][source] = "not-a-git-blob-sha"
                    evidence.write_text(json.dumps(raw), encoding="utf-8")
                    report = inspect(root)
                    self.assertFalse(report["all_source_checks_passed"])
                    self.assertTrue(any(ATTESTATIONS[1] in issue for issue in report["issues"]))

    def test_missing_mission_file_fails_without_modifying_checkout(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_checkout(root)
            missing = root / CRITICAL_SOURCES[0]
            missing.unlink()
            report = inspect(root)
            self.assertFalse(report["all_source_checks_passed"])
            self.assertIn("required_source_missing:" + CRITICAL_SOURCES[0], report["issues"])
            self.assertFalse(missing.exists())


if __name__ == "__main__":
    unittest.main()
