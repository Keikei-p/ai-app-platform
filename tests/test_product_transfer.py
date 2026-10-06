from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import json
import sqlite3
import unittest
import zipfile

from src.core.connectors import ConnectorManager
from src.core.credential_store import CredentialStore, SessionCredentialBackend
from src.core.productization import (
    OwnershipProfileStore,
    SetupStateStore,
    PortableConfigManager,
    TransferAuditor,
    TransferPackageBuilder,
)


class ProductTransferTests(unittest.TestCase):
    def make_parts(self, root: Path):
        credentials=CredentialStore(backend=SessionCredentialBackend())
        connectors=ConnectorManager(credentials=credentials,config_path=root/"state"/"connectors.json")
        ownership=OwnershipProfileStore(root/"state"/"ownership.json")
        setup=SetupStateStore(root/"state"/"setup.json")
        settings=root/"state"/"settings.json"
        settings.parent.mkdir(parents=True,exist_ok=True)
        settings.write_text(json.dumps({
            "ai_provider":"openai",
            "ai_model":"demo",
            "ai_routes":{"coding":{"provider":"openai","model":"demo"}},
        }),encoding="utf-8")
        portable=PortableConfigManager(
            connectors=connectors,
            ownership=ownership,
            setup=setup,
            settings_path=settings,
        )
        auditor=TransferAuditor(
            connectors=connectors,
            credentials=credentials,
            root_dir=root/"product",
            settings_path=settings,
            log_dir=root/"logs",
            db_path=root/"state"/"platform.db",
        )
        return credentials,connectors,ownership,setup,portable,auditor

    def test_export_contains_no_credentials(self):
        with TemporaryDirectory() as tmp:
            root=Path(tmp)
            product=root/"product";product.mkdir()
            credentials,connectors,ownership,setup,portable,_=self.make_parts(root)
            connectors.configure("github",config={"repository":"buyer/repo"},credentials={"token":"very-secret-token"},remember=True)
            ownership.update({"organization_name":"Buyer Inc.","brand_name":"Buyer Builder"})
            exported=portable.export_dict()
            text=json.dumps(exported,ensure_ascii=False)
            self.assertFalse(exported["credentials_included"])
            self.assertNotIn("very-secret-token",text)
            self.assertIn("Buyer Builder",text)

    def test_transfer_export_resets_seller_identity_but_keeps_generic_brand(self):
        with TemporaryDirectory() as tmp:
            root=Path(tmp);product=root/"product";product.mkdir()
            _,_,ownership,_,portable,_=self.make_parts(root)
            ownership.update({
                "product_name":"Aivy",
                "brand_name":"OEM Builder",
                "owner_name":"Seller Name",
                "organization_name":"Seller Company",
                "support_email":"seller@example.com",
                "support_url":"https://seller.example.com",
                "accent_color":"#123456",
            })
            normal=portable.export_dict()
            transfer=portable.export_dict(for_transfer=True)
            self.assertEqual(normal["ownership"]["owner_name"],"Seller Name")
            self.assertEqual(transfer["ownership"]["brand_name"],"OEM Builder")
            self.assertEqual(transfer["ownership"]["accent_color"],"#123456")
            self.assertEqual(transfer["ownership"]["owner_name"],"")
            self.assertEqual(transfer["ownership"]["organization_name"],"")
            self.assertEqual(transfer["ownership"]["support_email"],"")
            self.assertEqual(transfer["ownership"]["support_url"],"")
            self.assertTrue(transfer["transfer_sanitized"])

    def test_real_env_file_blocks_transfer_but_env_example_does_not(self):
        with TemporaryDirectory() as tmp:
            root=Path(tmp);product=root/"product";product.mkdir()
            _,_,_,_,_,auditor=self.make_parts(root)
            (product/".env.example").write_text("OPENAI_API_KEY=\n",encoding="utf-8")
            self.assertTrue(auditor.run()["ready"])
            (product/".env").write_text("SOME_KEY=value\n",encoding="utf-8")
            report=auditor.run()
            self.assertFalse(report["ready"])
            self.assertTrue(any(x["code"]=="env_file_present" for x in report["blockers"]))

    def test_runtime_db_scan_reports_location_without_secret_value(self):
        with TemporaryDirectory() as tmp:
            root=Path(tmp);product=root/"product";product.mkdir()
            _,_,_,_,_,auditor=self.make_parts(root)
            db=root/"state"/"platform.db"
            db.parent.mkdir(parents=True,exist_ok=True)
            conn=sqlite3.connect(db)
            try:
                conn.execute("CREATE TABLE chats (content TEXT, email TEXT, auth_token TEXT)")
                conn.execute(
                    "INSERT INTO chats(content,email,auth_token) VALUES(?,?,?)",
                    ("hello","buyer@example.com","sk-"+"A"*30),
                )
                conn.commit()
            finally:
                conn.close()
            report=auditor.run()
            serialized=json.dumps(report,ensure_ascii=False)
            self.assertIn("runtime_db_credential_data",serialized)
            self.assertIn("runtime_db_personal_data",serialized)
            self.assertIn("chats.auth_token",serialized)
            self.assertNotIn("buyer@example.com",serialized)
            self.assertNotIn("sk-"+"A"*30,serialized)
            self.assertTrue(report["ready"])

    def test_transfer_package_is_non_destructive_and_excludes_runtime_data(self):
        with TemporaryDirectory() as tmp:
            root=Path(tmp);product=root/"product";product.mkdir()
            (product/"src").mkdir()
            (product/"src"/"app.py").write_text("print('ok')\n",encoding="utf-8")
            (product/"data").mkdir();(product/"data"/"secret.db").write_text("runtime",encoding="utf-8")
            credentials,connectors,ownership,setup,portable,auditor=self.make_parts(root)
            ownership.update({
                "brand_name":"Buyer Ready Brand",
                "owner_name":"Original Seller",
                "support_email":"seller@example.com",
            })
            builder=TransferPackageBuilder(
                auditor=auditor,
                portable_config=portable,
                root_dir=product,
                backup_dir=root/"backups",
            )
            result=builder.create(approved=True)
            self.assertTrue(result["created"])
            self.assertTrue((product/"data"/"secret.db").is_file())
            with zipfile.ZipFile(result["path"]) as z:
                names=set(z.namelist())
                exported=json.loads(z.read("ivy-config.json").decode("utf-8"))
            self.assertIn("src/app.py",names)
            self.assertIn("ivy-config.json",names)
            self.assertIn("TRANSFER_READY.json",names)
            self.assertNotIn("data/secret.db",names)
            self.assertEqual(exported["ownership"]["owner_name"],"")
            self.assertEqual(exported["ownership"]["support_email"],"")
            self.assertEqual(exported["ownership"]["brand_name"],"Buyer Ready Brand")
            self.assertTrue(exported["transfer_sanitized"])


if __name__=="__main__":
    unittest.main()
