from __future__ import annotations

from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]


class ProductizationUIContractTests(unittest.TestCase):
    def test_visible_services_tab_and_setup_transfer_ui_exist(self):
        html=(ROOT/"webui"/"index.html").read_text(encoding="utf-8")
        app=(ROOT/"webui"/"app.js").read_text(encoding="utf-8")
        css=(ROOT/"webui"/"styles.css").read_text(encoding="utf-8")
        for token in (
            'data-view="integrations"',
            'id="view-integrations"',
            'id="setupWizard"',
            'id="connectorCategories"',
            'id="currentDependencies"',
            'id="connectorDialog"',
            'id="createTransferPackage"',
            'id="runBuyerE2E"',
            'id="buyerE2EResult"',
            'id="ownerBrandName"',
            'id="exportConfig"',
        ):
            self.assertIn(token,html)
        for token in (
            "/api/v1/connectors",
            "async function loadIntegrations()",
            "async function testConnector(",
            "async function runTransferAudit()",
            "async function createTransferPackage()",
            "async function runBuyerE2E()",
            "/api/v1/productization/e2e",
            "async function exportPortableConfig()",
        ):
            self.assertIn(token,app)
        self.assertIn(".connector-grid",css)
        self.assertIn(".productization-grid",css)

    def test_api_exposes_productization_routes(self):
        api=(ROOT/"src"/"core"/"platform_api.py").read_text(encoding="utf-8")
        for token in (
            '"/api/v1/connectors"',
            '"/api/v1/ownership"',
            '"/api/v1/setup"',
            '"/api/v1/config/export"',
            '"/api/v1/config/import"',
            '"/api/v1/transfer/audit"',
            '"/api/v1/transfer/package"',
            '"/api/v1/productization/e2e"',
            '"/api/v1/productization/e2e/run"',
        ):
            self.assertIn(token,api)

    def test_buyer_e2e_is_explicit_not_startup_work(self):
        service=(ROOT/"src"/"core"/"platform_service.py").read_text(encoding="utf-8")
        init_start=service.index("    def __init__(self):")
        next_method=service.index("\n    def ",init_start+10)
        init_body=service[init_start:next_method]
        self.assertIn("BuyerJourneyE2EVerifier()",init_body)
        self.assertNotIn("buyer_journey_e2e.run()",init_body)

    def test_developer_repo_is_not_hardcoded_in_bootstrap_launchers(self):
        for name in ("OPEN_AIVY_WEB.bat","INSTALL_OR_UPDATE.bat"):
            text=(ROOT/name).read_text(encoding="utf-8")
            self.assertNotIn("github.com/Keikei-p/ai-app-platform",text)
            self.assertIn("AIVY_UPSTREAM_REPO",text)


if __name__=="__main__":
    unittest.main()
