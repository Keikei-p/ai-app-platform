from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha1
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any
import json

from .config import DATA_DIR, ROOT_DIR, resolve_state_dir
from .remote_access import remote_bind_policy


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class CloudRuntimeReadinessVerifier:
    """Verify Aivy can be safely prepared for headless/cloud runtime.

    This does not deploy Aivy externally. It verifies the prerequisites needed
    to run behind a trusted gateway: externalized state, explicit remote opt-in,
    mandatory bearer token for non-loopback binding, and a public health probe.
    Evidence is invalidated whenever covered source files change.
    """

    SOURCE_PATHS = (
        "src/core/config.py",
        "src/core/platform_api.py",
        "src/core/remote_access.py",
        "src/core/cloud_runtime.py",
    )

    def __init__(
        self,
        *,
        root_dir: Path | None = None,
        evidence_path: Path | None = None,
    ):
        self.root_dir = Path(root_dir or ROOT_DIR)
        self.evidence_path = Path(
            evidence_path or (DATA_DIR / "completion_evidence" / "cloud_runtime.json")
        )

    def run(self) -> dict[str, Any]:
        with TemporaryDirectory(prefix="aivy-cloud-runtime-") as tmp:
            root = Path(tmp)
            external_state = root / "persistent-volume"
            resolved = resolve_state_dir(
                {"AI_APP_PLATFORM_STATE_DIR": str(external_state)},
                os_name="posix",
                home=root / "home",
            )

            loopback = remote_bind_policy("127.0.0.1", {})
            denied_no_optin = remote_bind_policy(
                "0.0.0.0",
                {"AI_APP_LOCAL_API_TOKEN": "token"},
            )
            denied_no_token = remote_bind_policy(
                "0.0.0.0",
                {"AI_APP_ENABLE_REMOTE": "1"},
            )
            remote_ok = remote_bind_policy(
                "0.0.0.0",
                {
                    "AI_APP_ENABLE_REMOTE": "1",
                    "AI_APP_LOCAL_API_TOKEN": "token",
                },
            )

            api_source = (self.root_dir / "src/core/platform_api.py").read_text(encoding="utf-8")
            checks = {
                "external_state_dir": resolved == external_state,
                "loopback_default_allowed": loopback.get("allowed") is True,
                "remote_denied_without_optin": denied_no_optin.get("allowed") is False,
                "remote_denied_without_token": denied_no_token.get("allowed") is False,
                "remote_allowed_only_with_optin_and_token": remote_ok.get("allowed") is True,
                "remote_requires_bearer": remote_ok.get("requires_bearer") is True,
                "health_endpoint_present": '"/api/v1/healthz"' in api_source,
                "remote_api_gets_require_bearer": (
                    "api.remote_mode and path.startswith" in api_source
                    and "bearer_token_required" in api_source
                ),
                "headless_start_supported": "open_browser: bool = False" in api_source,
                "graceful_server_close": "server.server_close()" in api_source,
            }
            verified = all(checks.values())
            payload = {
                "schema_version": 1,
                "kind": "cloud_runtime_readiness",
                "verified": verified,
                "checks": checks,
                "source_blobs": self.source_blobs(),
                "deployment_performed": False,
                "external_actions": False,
                "credentials_used": False,
                "paid_actions": False,
                "production_data_written": False,
                "recommended_topology": (
                    "private Aivy process + persistent volume + trusted TLS/reverse-proxy gateway"
                ),
                "required_env": [
                    "AI_APP_PLATFORM_STATE_DIR",
                    "AI_APP_ENABLE_REMOTE=1",
                    "AI_APP_LOCAL_API_TOKEN=<secret>",
                ],
                "created_at": _now(),
            }
            self.evidence_path.parent.mkdir(parents=True, exist_ok=True)
            tmp_path = self.evidence_path.with_suffix(self.evidence_path.suffix + ".tmp")
            tmp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            tmp_path.replace(self.evidence_path)
            return payload

    def status(self) -> dict[str, Any]:
        raw = self._read()
        if self._valid(raw):
            return {**raw, "stale": False}
        return {
            "schema_version": 1,
            "kind": "cloud_runtime_readiness",
            "verified": False,
            "stale": bool(raw),
            "checks": raw.get("checks") if isinstance(raw, dict) else {},
            "source_blobs": self.source_blobs(),
            "deployment_performed": False,
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
        return bool(
            raw.get("verified") is True
            and raw.get("source_blobs") == self.source_blobs()
            and isinstance(raw.get("checks"), dict)
            and raw.get("checks")
            and all(bool(x) for x in raw["checks"].values())
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
