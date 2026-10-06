from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import json
import unittest

from src.core.connectors import ConnectorManager
from src.core.credential_store import CredentialStore, SessionCredentialBackend
from src.core.productization import TransferAuditor


ROOT=Path(__file__).resolve().parents[1]


class RepositoryTransferAuditTests(unittest.TestCase):
    def test_current_product_tree_has_no_transfer_blocker(self):
        with TemporaryDirectory() as tmp:
            temp=Path(tmp)
            settings=temp/"settings.json"
            settings.write_text(json.dumps({"ai_provider":"none"}),encoding="utf-8")
            manager=ConnectorManager(
                credentials=CredentialStore(backend=SessionCredentialBackend()),
                config_path=temp/"connectors.json",
            )
            auditor=TransferAuditor(
                connectors=manager,
                credentials=manager.credentials,
                root_dir=ROOT,
                settings_path=settings,
                log_dir=temp/"logs",
                db_path=temp/"platform.db",
            )
            report=auditor.run()
            self.assertEqual(
                report["blockers"],
                [],
                "current repository is not transfer-ready: "+
                " / ".join(str(x.get("message") or x.get("code")) for x in report["blockers"]),
            )
            self.assertFalse(report["credentials_in_transfer_package"])
            self.assertFalse(report["git_history_included_in_transfer_package"])


if __name__=="__main__":
    unittest.main()
