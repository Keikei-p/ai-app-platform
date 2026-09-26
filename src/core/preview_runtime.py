from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
import importlib.util
import json
import threading
import uuid
from .config import WORKSPACE_DIR

@dataclass(frozen=True)
class PreviewSession:
    url: str
    project_dir: Path

class PreviewRuntime:
    """Loopback-only runtime for generated Python web apps.

    Generated server code is loaded from a verified project directory and bound to
    127.0.0.1 on an ephemeral port. No generic shell/process execution is exposed.
    """
    def __init__(self):
        self._server = None
        self._thread: threading.Thread | None = None
        self._session: PreviewSession | None = None

    @staticmethod
    def assert_verified(project_dir: Path) -> None:
        """Block preview when the latest generation quality gate explicitly failed.

        Legacy projects without a report remain previewable so upgrades do not break
        existing work. Newly generated projects always receive this report.
        """
        report_path = project_dir / ".aiapp" / "reports" / "build_readiness.json"
        if not report_path.exists():
            return
        try:
            data = json.loads(report_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise PermissionError(f"preview verification report is invalid: {exc}") from exc
        if not bool(data.get("preview_ready")):
            reasons = ", ".join(str(x) for x in data.get("blocking_reasons") or [])
            raise PermissionError("preview blocked by quality gate" + (f": {reasons}" if reasons else ""))

    def start(self, project_dir: Path) -> PreviewSession:
        self.stop()
        root = WORKSPACE_DIR.resolve()
        project = project_dir.resolve()
        if root not in project.parents:
            raise ValueError("preview project is outside workspace")
        self.assert_verified(project)
        server_path = project / "server.py"
        if not server_path.is_file():
            raise FileNotFoundError("server.py")
        spec = importlib.util.spec_from_file_location(f"generated_preview_{uuid.uuid4().hex}", server_path)
        if spec is None or spec.loader is None:
            raise RuntimeError("preview module load failed")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        server = module.ThreadingHTTPServer(("127.0.0.1", 0), module.Handler)
        port = int(server.server_address[1])
        thread = threading.Thread(target=server.serve_forever, name="AIAppPreview", daemon=True)
        thread.start()
        self._server = server
        self._thread = thread
        self._session = PreviewSession(f"http://127.0.0.1:{port}/", project)
        return self._session

    def stop(self) -> None:
        if self._server is not None:
            try:
                self._server.shutdown()
                self._server.server_close()
            except Exception:
                pass
        self._server = None
        self._thread = None
        self._session = None
