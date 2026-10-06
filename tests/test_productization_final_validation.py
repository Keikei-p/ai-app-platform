from __future__ import annotations
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]

class FinalProductizationValidation(unittest.TestCase):
    def test_transferable_product_contract(self):
        credential=(ROOT/"src"/"core"/"credential_store.py").read_text(encoding="utf-8")
        connectors=(ROOT/"src"/"core"/"connectors.py").read_text(encoding="utf-8")
        providers=(ROOT/"src"/"core"/"connector_providers.py").read_text(encoding="utf-8")
        product=(ROOT/"src"/"core"/"productization.py").read_text(encoding="utf-8")
        service=(ROOT/"src"/"core"/"platform_service.py").read_text(encoding="utf-8")
        api=(ROOT/"src"/"core"/"platform_api.py").read_text(encoding="utf-8")
        html=(ROOT/"webui"/"index.html").read_text(encoding="utf-8")
        app=(ROOT/"webui"/"app.js").read_text(encoding="utf-8")
        self.assertIn("WindowsCredentialBackend",credential)
        for name in ("connect(","disconnect(","test_connection(","get_status(","get_capabilities(","validate_configuration("):
            self.assertIn(name,connectors)
        self.assertIn("class ConnectorProvider",providers)
        self.assertIn("class TransferAuditor",product)
        self.assertIn("class TransferPackageBuilder",product)
        self.assertIn("OwnershipProfileStore",service)
        self.assertIn('"/api/v1/connectors"',api)
        self.assertIn('data-view="integrations"',html)
        self.assertIn("async function loadIntegrations()",app)
        for launcher in ("OPEN_AIVY_WEB.bat","INSTALL_OR_UPDATE.bat"):
            text=(ROOT/launcher).read_text(encoding="utf-8")
            self.assertNotIn("github.com/Keikei-p/ai-app-platform",text)
            self.assertIn("AIVY_UPSTREAM_REPO",text)

if __name__=="__main__":
    unittest.main()
