from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from src.core.productization_e2e import BuyerJourneyE2EVerifier


class BuyerJourneyE2ETests(unittest.TestCase):
    def test_full_buyer_journey_is_verified_without_network_or_real_credentials(self):
        with TemporaryDirectory() as tmp:
            evidence=Path(tmp)/"buyer_e2e.json"
            verifier=BuyerJourneyE2EVerifier(evidence_path=evidence)
            report=verifier.run()

            self.assertTrue(report["verified"])
            self.assertFalse(report["network_used"])
            self.assertFalse(report["real_credentials_used"])
            self.assertFalse(report["paid_api_used"])
            self.assertFalse(report["production_data_used"])
            self.assertFalse(report["live_user_data_mutated"])
            self.assertFalse(report["transfer_package_credentials_included"])
            self.assertTrue(all(report["checks"].values()))
            self.assertTrue(evidence.is_file())

            stages=[x["stage"] for x in report["stages"]]
            for expected in (
                "fresh_install",
                "local_ai",
                "external_connectors",
                "setup_complete",
                "new_pc_import",
                "new_pc_reauthentication",
                "transfer_package",
                "new_owner_first_boot",
            ):
                self.assertIn(expected,stages)

    def test_source_change_invalidates_buyer_e2e_evidence(self):
        with TemporaryDirectory() as tmp:
            root=Path(tmp)/"root"
            for rel in BuyerJourneyE2EVerifier.SOURCE_PATHS:
                path=root/rel
                path.parent.mkdir(parents=True,exist_ok=True)
                path.write_text("# stable\n",encoding="utf-8")
            evidence=Path(tmp)/"buyer_e2e.json"
            verifier=BuyerJourneyE2EVerifier(
                root_dir=root,
                evidence_path=evidence,
            )
            report=verifier.run()
            self.assertTrue(report["verified"])
            self.assertTrue(verifier.status()["verified"])

            changed=root/BuyerJourneyE2EVerifier.SOURCE_PATHS[0]
            changed.write_text("# changed\n",encoding="utf-8")
            stale=verifier.status()
            self.assertFalse(stale["verified"])
            self.assertTrue(stale["stale"])

    def test_transfer_package_proves_new_owner_reauthentication_boundary(self):
        with TemporaryDirectory() as tmp:
            report=BuyerJourneyE2EVerifier(
                evidence_path=Path(tmp)/"evidence.json"
            ).run()
            checks=report["checks"]
            self.assertTrue(checks["portable_export_has_no_credentials"])
            self.assertTrue(checks["import_requires_reauthentication"])
            self.assertTrue(checks["credential_namespaces_are_isolated"])
            self.assertTrue(checks["transfer_package_resets_owner_identity"])
            self.assertTrue(checks["transfer_package_resets_connector_configuration"])
            self.assertTrue(checks["transfer_package_has_no_credentials"])
            self.assertTrue(checks["same_machine_handoff_clears_ivy_credentials"])
            self.assertTrue(checks["same_machine_handoff_clears_connector_config"])
            self.assertTrue(checks["same_machine_handoff_reopens_setup"])
            self.assertTrue(checks["same_machine_handoff_resets_owner_identity"])
            self.assertTrue(checks["new_owner_starts_without_seller_identity"])
            self.assertTrue(checks["new_owner_starts_without_seller_connectors"])


if __name__=="__main__":
    unittest.main()
