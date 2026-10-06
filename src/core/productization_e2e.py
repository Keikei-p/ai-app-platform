from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha1
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any
import json
import zipfile

from .config import DATA_DIR, ROOT_DIR
from .connector_providers import BaseProvider, ProviderTestResult, default_provider_registry
from .connectors import ConnectorManager
from .credential_store import CredentialStore, SessionCredentialBackend
from .llm_chat import AIChatEngine
from .productization import (
    OwnershipProfileStore,
    PortableConfigManager,
    SetupStateStore,
    TransferAuditor,
    TransferPackageBuilder,
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class _SyntheticOllamaProvider(BaseProvider):
    provider_id = "ollama"
    capabilities = ("local_llm", "offline_fallback")

    def test_connection(self, config, get_secret):
        model = str(config.get("model") or "qwen2.5:7b")
        return ProviderTestResult(
            True,
            "connected",
            f"Synthetic local Ollama ready: {model}",
        )


class _SyntheticGitHubProvider(BaseProvider):
    provider_id = "github"
    capabilities = ("source_control", "backup", "updates")

    def validate_configuration(self, config, get_secret):
        return [] if get_secret("token") else ["GitHub Token is required"]

    def test_connection(self, config, get_secret):
        if not get_secret("token"):
            return ProviderTestResult(False, "setting_incomplete", "GitHub Token is required")
        return ProviderTestResult(True, "connected", "Synthetic GitHub connection succeeded")


class _SyntheticCloudflareProvider(BaseProvider):
    provider_id = "cloudflare"
    capabilities = ("workers", "pages", "web_deployment")

    def validate_configuration(self, config, get_secret):
        return [] if get_secret("token") else ["Cloudflare Token is required"]

    def test_connection(self, config, get_secret):
        if not get_secret("token"):
            return ProviderTestResult(False, "setting_incomplete", "Cloudflare Token is required")
        return ProviderTestResult(True, "connected", "Synthetic Cloudflare connection succeeded")


class BuyerJourneyE2EVerifier:
    """Run the transferable-product buyer journey without real external accounts.

    No network, real credentials, paid APIs, production projects or live user
    data are used. The purpose is to prove separation boundaries and lifecycle
    behavior: fresh install -> setup -> buyer-owned connectors -> export/import
    -> reauthentication -> transfer package.
    """

    SOURCE_PATHS = (
        "src/core/credential_store.py",
        "src/core/connectors.py",
        "src/core/connector_providers.py",
        "src/core/llm_chat.py",
        "src/core/productization.py",
        "src/core/productization_e2e.py",
    )

    def __init__(
        self,
        *,
        root_dir: Path | None = None,
        evidence_path: Path | None = None,
    ):
        self.root_dir = Path(root_dir or ROOT_DIR)
        self.evidence_path = Path(
            evidence_path
            or (DATA_DIR / "completion_evidence" / "buyer_productization_e2e.json")
        )

    def run(self) -> dict[str, Any]:
        checks: dict[str, bool] = {}
        stages: list[dict[str, Any]] = []
        secret_markers: list[str] = []

        with TemporaryDirectory(prefix="aivy-buyer-e2e-") as tmp:
            sandbox = Path(tmp)
            seller = sandbox / "seller"
            migrated = sandbox / "migrated-pc"
            product_tree = sandbox / "product"
            seller.mkdir(parents=True)
            migrated.mkdir(parents=True)
            (product_tree / "src").mkdir(parents=True)
            (product_tree / "src" / "app.py").write_text(
                "print('transfer-safe fixture')\n",
                encoding="utf-8",
            )
            (product_tree / ".env.example").write_text(
                "OPENAI_API_KEY=\nGITHUB_TOKEN=\n",
                encoding="utf-8",
            )
            (product_tree / "data").mkdir()
            (product_tree / "data" / "runtime.db").write_text(
                "synthetic runtime data",
                encoding="utf-8",
            )

            providers = default_provider_registry()
            providers["ollama"] = _SyntheticOllamaProvider()
            providers["github"] = _SyntheticGitHubProvider()
            providers["cloudflare"] = _SyntheticCloudflareProvider()

            seller_store = CredentialStore(
                backend=SessionCredentialBackend(),
                namespace="AivySellerE2E",
            )
            seller_connectors = ConnectorManager(
                credentials=seller_store,
                config_path=seller / "connectors.json",
                providers=providers,
            )
            seller_ownership = OwnershipProfileStore(seller / "ownership.json")
            seller_setup = SetupStateStore(seller / "setup.json")
            seller_settings = seller / "settings.json"
            seller_ai = AIChatEngine(
                seller_settings,
                credential_store=seller_store,
            )
            seller_portable = PortableConfigManager(
                connectors=seller_connectors,
                ownership=seller_ownership,
                setup=seller_setup,
                settings_path=seller_settings,
            )

            checks["fresh_install_not_completed"] = seller_setup.get()["completed"] is False
            stages.append({
                "stage": "fresh_install",
                "status": "pass" if checks["fresh_install_not_completed"] else "fail",
            })

            seller_connectors.connect(
                "ollama",
                config={
                    "base_url": "http://127.0.0.1:11434",
                    "model": "qwen2.5:7b",
                },
            )
            seller_ai.configure_provider(
                "ollama",
                "qwen2.5:7b",
                make_default=True,
                base_url="http://127.0.0.1:11434",
            )
            local_test = seller_connectors.test_connection("ollama")
            checks["local_ai_starts_without_paid_api"] = bool(
                local_test.get("ok")
                and seller_ai.status().connected
                and seller_ai.status().provider == "ollama"
            )
            stages.append({
                "stage": "local_ai",
                "status": "pass" if checks["local_ai_starts_without_paid_api"] else "fail",
                "provider": seller_ai.status().provider,
            })

            seller_github_secret = "github_pat_" + "SELLER_E2E_" + "G" * 28
            seller_cloud_secret = "cf_e2e_" + "C" * 36
            secret_markers.extend([seller_github_secret, seller_cloud_secret])

            seller_connectors.connect(
                "github",
                config={"repository": "buyer-owned/example"},
                credentials={"token": seller_github_secret},
                remember=True,
            )
            seller_connectors.connect(
                "cloudflare",
                config={"account_id": "synthetic-account"},
                credentials={"token": seller_cloud_secret},
                remember=True,
            )
            github_test = seller_connectors.test_connection("github")
            cloud_test = seller_connectors.test_connection("cloudflare")
            checks["buyer_owned_connectors_test"] = bool(
                github_test.get("ok") and cloud_test.get("ok")
            )
            checks["connector_config_has_no_secret"] = all(
                marker not in (seller / "connectors.json").read_text(encoding="utf-8")
                for marker in secret_markers
            )
            stages.append({
                "stage": "external_connectors",
                "status": "pass"
                if checks["buyer_owned_connectors_test"]
                and checks["connector_config_has_no_secret"]
                else "fail",
                "github": github_test.get("status"),
                "cloudflare": cloud_test.get("status"),
            })

            seller_ownership.update({
                "product_name": "Aivy",
                "brand_name": "Buyer Ready Builder",
                "owner_name": "Original Owner",
                "organization_name": "Original Org",
                "license_label": "Transferable License",
                "support_email": "seller@example.invalid",
                "support_url": "https://seller.example.invalid",
                "accent_color": "#6655cc",
            })
            seller_setup.update({
                "ai_choice": "ollama",
                "github_choice": "github",
                "cloud_choice": "cloudflare",
                "completed": True,
            })
            checks["setup_completes"] = seller_setup.get()["completed"] is True
            stages.append({
                "stage": "setup_complete",
                "status": "pass" if checks["setup_completes"] else "fail",
            })

            exported = seller_portable.export_dict()
            exported_text = json.dumps(exported, ensure_ascii=False)
            checks["portable_export_has_no_credentials"] = bool(
                exported.get("credentials_included") is False
                and all(marker not in exported_text for marker in secret_markers)
            )

            migrated_store = CredentialStore(
                backend=SessionCredentialBackend(),
                namespace="AivyMigratedE2E",
            )
            migrated_connectors = ConnectorManager(
                credentials=migrated_store,
                config_path=migrated / "connectors.json",
                providers=providers,
            )
            migrated_ownership = OwnershipProfileStore(migrated / "ownership.json")
            migrated_setup = SetupStateStore(migrated / "setup.json")
            migrated_settings = migrated / "settings.json"
            migrated_portable = PortableConfigManager(
                connectors=migrated_connectors,
                ownership=migrated_ownership,
                setup=migrated_setup,
                settings_path=migrated_settings,
            )
            import_result = migrated_portable.import_dict(exported)

            checks["import_requires_reauthentication"] = bool(
                import_result.get("requires_reauthentication")
                and not migrated_store.has("github.token")
                and not migrated_store.has("cloudflare.token")
            )
            migrated_github = migrated_connectors.get_public("github")
            migrated_cloud = migrated_connectors.get_public("cloudflare")
            checks["non_secret_connector_config_migrates"] = bool(
                migrated_github.get("config", {}).get("repository") == "buyer-owned/example"
                and migrated_cloud.get("config", {}).get("account_id") == "synthetic-account"
            )
            stages.append({
                "stage": "new_pc_import",
                "status": "pass"
                if checks["portable_export_has_no_credentials"]
                and checks["import_requires_reauthentication"]
                and checks["non_secret_connector_config_migrates"]
                else "fail",
            })

            migrated_github_secret = "github_pat_" + "NEWPC_E2E_" + "N" * 30
            migrated_cloud_secret = "cf_newpc_" + "D" * 36
            secret_markers.extend([migrated_github_secret, migrated_cloud_secret])
            migrated_connectors.connect(
                "github",
                credentials={"token": migrated_github_secret},
                remember=True,
            )
            migrated_connectors.connect(
                "cloudflare",
                credentials={"token": migrated_cloud_secret},
                remember=True,
            )
            migrated_gh_test = migrated_connectors.test_connection("github")
            migrated_cf_test = migrated_connectors.test_connection("cloudflare")
            checks["new_pc_reauthentication_succeeds"] = bool(
                migrated_gh_test.get("ok") and migrated_cf_test.get("ok")
            )
            checks["credential_namespaces_are_isolated"] = bool(
                seller_store.get("github.token") == seller_github_secret
                and migrated_store.get("github.token") == migrated_github_secret
                and seller_store.get("github.token") != migrated_store.get("github.token")
            )
            stages.append({
                "stage": "new_pc_reauthentication",
                "status": "pass"
                if checks["new_pc_reauthentication_succeeds"]
                and checks["credential_namespaces_are_isolated"]
                else "fail",
            })

            auditor = TransferAuditor(
                connectors=migrated_connectors,
                credentials=migrated_store,
                root_dir=product_tree,
                settings_path=migrated_settings,
                log_dir=migrated / "logs",
                db_path=migrated / "platform.db",
            )
            audit = auditor.run()
            checks["transfer_audit_ready"] = bool(audit.get("ready"))

            builder = TransferPackageBuilder(
                auditor=auditor,
                portable_config=migrated_portable,
                root_dir=product_tree,
                backup_dir=migrated / "backups",
            )
            transfer = builder.create(approved=True)
            checks["transfer_package_created"] = bool(transfer.get("created"))

            package_config: dict[str, Any] = {}
            names: set[str] = set()
            package_payloads: list[bytes] = []
            if transfer.get("created"):
                package_path = Path(str(transfer["path"]))
                with zipfile.ZipFile(package_path) as archive:
                    names = set(archive.namelist())
                    package_config = json.loads(
                        archive.read("ivy-config.json").decode("utf-8")
                    )
                    for name in names:
                        if name.endswith("/"):
                            continue
                        try:
                            package_payloads.append(archive.read(name))
                        except Exception:
                            pass

            checks["transfer_package_excludes_runtime_data"] = bool(
                "data/runtime.db" not in names
                and ".git" not in names
                and "ivy-config.json" in names
                and "TRANSFER_READY.json" in names
            )
            checks["transfer_package_resets_owner_identity"] = bool(
                package_config.get("transfer_sanitized") is True
                and package_config.get("ownership", {}).get("owner_name") == ""
                and package_config.get("ownership", {}).get("organization_name") == ""
                and package_config.get("ownership", {}).get("support_email") == ""
            )
            checks["transfer_package_resets_connector_configuration"] = bool(
                package_config.get("connectors") == {}
                and "buyer-owned/example" not in json.dumps(package_config, ensure_ascii=False)
                and "synthetic-account" not in json.dumps(package_config, ensure_ascii=False)
            )
            checks["transfer_package_has_no_credentials"] = all(
                marker.encode("utf-8") not in payload
                for marker in secret_markers
                for payload in package_payloads
            )
            checks["live_source_state_not_mutated"] = bool(
                migrated_store.get("github.token") == migrated_github_secret
                and (product_tree / "data" / "runtime.db").is_file()
            )
            stages.append({
                "stage": "transfer_package",
                "status": "pass"
                if all((
                    checks["transfer_audit_ready"],
                    checks["transfer_package_created"],
                    checks["transfer_package_excludes_runtime_data"],
                    checks["transfer_package_resets_owner_identity"],
                    checks["transfer_package_resets_connector_configuration"],
                    checks["transfer_package_has_no_credentials"],
                    checks["live_source_state_not_mutated"],
                ))
                else "fail",
            })

            # Also prove a direct handoff on the same machine is safe. The
            # previous owner may have Ivy-managed credentials/config locally.
            reused = sandbox / "reused-owner-machine"
            reused.mkdir()
            reused_backend = SessionCredentialBackend()
            reused_store = CredentialStore(
                backend=reused_backend,
                namespace="AivyReusedOwnerE2E",
            )
            reused_connectors = ConnectorManager(
                credentials=reused_store,
                config_path=reused / "connectors.json",
                providers=providers,
            )
            reused_ownership = OwnershipProfileStore(reused / "ownership.json")
            reused_setup = SetupStateStore(reused / "setup.json")
            reused_settings = reused / "settings.json"
            reused_portable = PortableConfigManager(
                connectors=reused_connectors,
                ownership=reused_ownership,
                setup=reused_setup,
                settings_path=reused_settings,
            )
            reused_connectors.connect(
                "github",
                config={"repository": "old-owner/private"},
                credentials={"token": "old-owner-local-token"},
                remember=True,
            )
            reused_ownership.update({
                "brand_name": "Old Owner Brand",
                "owner_name": "Old Owner",
                "organization_name": "Old Owner Org",
                "support_email": "old-owner@example.invalid",
            })
            reused_setup.update({
                "completed": True,
                "ai_choice": "openai",
                "github_choice": "github",
                "cloud_choice": "cloudflare",
            })
            reused_import = reused_portable.import_dict(package_config)
            reused_profile = reused_ownership.get().to_dict()

            checks["same_machine_handoff_clears_ivy_credentials"] = bool(
                reused_import.get("connector_state_reset")
                and not reused_backend.has(reused_store.target("github.token"))
            )
            checks["same_machine_handoff_clears_connector_config"] = bool(
                reused_connectors._read() == {}
            )
            checks["same_machine_handoff_reopens_setup"] = bool(
                reused_import.get("owner_setup_reset")
                and reused_setup.get().get("completed") is False
                and reused_setup.get().get("github_choice") == ""
            )
            checks["same_machine_handoff_resets_owner_identity"] = bool(
                reused_profile.get("brand_name") == "Buyer Ready Builder"
                and reused_profile.get("owner_name") == ""
                and reused_profile.get("organization_name") == ""
                and reused_profile.get("support_email") == ""
            )
            stages.append({
                "stage": "same_machine_owner_handoff",
                "status": "pass"
                if all((
                    checks["same_machine_handoff_clears_ivy_credentials"],
                    checks["same_machine_handoff_clears_connector_config"],
                    checks["same_machine_handoff_reopens_setup"],
                    checks["same_machine_handoff_resets_owner_identity"],
                ))
                else "fail",
            })

            # Simulate the package arriving on a third, brand-new owner machine.
            new_owner = sandbox / "new-owner"
            new_owner.mkdir()
            new_owner_store = CredentialStore(
                backend=SessionCredentialBackend(),
                namespace="AivyNewOwnerE2E",
            )
            new_owner_connectors = ConnectorManager(
                credentials=new_owner_store,
                config_path=new_owner / "connectors.json",
                providers=providers,
            )
            new_owner_ownership = OwnershipProfileStore(new_owner / "ownership.json")
            new_owner_setup = SetupStateStore(new_owner / "setup.json")
            new_owner_settings = new_owner / "settings.json"
            new_owner_portable = PortableConfigManager(
                connectors=new_owner_connectors,
                ownership=new_owner_ownership,
                setup=new_owner_setup,
                settings_path=new_owner_settings,
            )
            new_owner_import = new_owner_portable.import_dict(package_config)
            new_owner_profile = new_owner_ownership.get().to_dict()
            checks["new_owner_starts_without_seller_identity"] = bool(
                new_owner_import.get("requires_reauthentication")
                and new_owner_profile.get("brand_name") == "Buyer Ready Builder"
                and new_owner_profile.get("owner_name") == ""
                and new_owner_profile.get("organization_name") == ""
                and new_owner_profile.get("support_email") == ""
            )
            checks["new_owner_starts_without_seller_connectors"] = bool(
                not new_owner_store.has("github.token")
                and not new_owner_store.has("cloudflare.token")
                and new_owner_connectors.get_public("github").get("config") == {}
                and new_owner_connectors.get_public("cloudflare").get("config") == {}
                and new_owner_setup.get().get("completed") is False
            )
            stages.append({
                "stage": "new_owner_first_boot",
                "status": "pass"
                if checks["new_owner_starts_without_seller_identity"]
                and checks["new_owner_starts_without_seller_connectors"]
                else "fail",
            })

        verified = all(checks.values())
        payload = {
            "schema_version": 1,
            "kind": "buyer_productization_e2e",
            "verified": verified,
            "checks": checks,
            "stages": stages,
            "source_blobs": self.source_blobs(),
            "network_used": False,
            "real_credentials_used": False,
            "paid_api_used": False,
            "production_data_used": False,
            "live_user_data_mutated": False,
            "transfer_package_credentials_included": False,
            "created_at": _now(),
        }
        self.evidence_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = self.evidence_path.with_suffix(self.evidence_path.suffix + ".tmp")
        tmp_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        tmp_path.replace(self.evidence_path)
        return payload

    def status(self) -> dict[str, Any]:
        raw = self._read()
        if self._valid(raw):
            return {**raw, "stale": False}
        return {
            "schema_version": 1,
            "kind": "buyer_productization_e2e",
            "verified": False,
            "stale": bool(raw),
            "checks": raw.get("checks") if isinstance(raw, dict) else {},
            "stages": raw.get("stages") if isinstance(raw, dict) else [],
            "source_blobs": self.source_blobs(),
            "network_used": False,
            "real_credentials_used": False,
            "paid_api_used": False,
            "production_data_used": False,
            "live_user_data_mutated": False,
            "created_at": raw.get("created_at") if isinstance(raw, dict) else None,
        }

    def source_blobs(self) -> dict[str, str]:
        rows: dict[str, str] = {}
        for rel in self.SOURCE_PATHS:
            path = self.root_dir / rel
            if path.is_file():
                rows[rel] = self._git_blob_sha(path)
        return rows

    def _valid(self, raw: dict[str, Any]) -> bool:
        checks = raw.get("checks")
        return bool(
            raw.get("verified") is True
            and raw.get("source_blobs") == self.source_blobs()
            and isinstance(checks, dict)
            and checks
            and all(bool(value) for value in checks.values())
        )

    def _read(self) -> dict[str, Any]:
        if not self.evidence_path.is_file():
            return {}
        try:
            raw = json.loads(self.evidence_path.read_text(encoding="utf-8"))
            return raw if isinstance(raw, dict) else {}
        except Exception:
            return {}

    @staticmethod
    def _git_blob_sha(path: Path) -> str:
        text = path.read_text(encoding="utf-8")
        normalized = text.replace("\r\n", "\n").replace("\r", "\n").encode("utf-8")
        header = f"blob {len(normalized)}\0".encode("ascii")
        return sha1(header + normalized).hexdigest()
