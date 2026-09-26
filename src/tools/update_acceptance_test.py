from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

from src.core.config import APP_DIR, VERSION
from src.core.update_engine import UpdateEngine, build_update_package


def _copy_app(src: Path, dst: Path) -> None:
    shutil.copytree(
        src,
        dst,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".git", "dist", "build"),
    )


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="ai-app-update-accept-") as td:
        root = Path(td)
        app = root / "installed"
        future = root / "future"
        state = root / "state"
        package = root / "future.aipupdate"
        _copy_app(APP_DIR, app)
        _copy_app(APP_DIR, future)

        parts = [int(x) for x in VERSION.split(".")]
        future_version = f"{parts[0]}.{parts[1]}.{parts[2] + 1}"
        (future / "VERSION").write_text(future_version + "\n", encoding="utf-8")
        config_path = future / "src" / "core" / "config.py"
        config_text = config_path.read_text(encoding="utf-8").replace(
            f'VERSION = "{VERSION}"', f'VERSION = "{future_version}"'
        )
        config_path.write_text(config_text, encoding="utf-8")
        marker = future / "docs" / "UPDATE_ACCEPTANCE_MARKER.txt"
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text("future-package-ok\n", encoding="utf-8")

        build_update_package(future, package, version=future_version, notes="acceptance-test")
        engine = UpdateEngine(
            app_dir=app,
            state_dir=state,
            current_version=VERSION,
            state_backup_callback=lambda _label: (True, "acceptance-state-backup"),
            audit_callback=lambda *a, **k: None,
        )
        candidate = engine.inspect_package(package)
        result = engine.apply(candidate)
        if not result.ok:
            raise RuntimeError(result.message)
        if (app / "VERSION").read_text(encoding="utf-8").strip() != future_version:
            raise AssertionError("updated VERSION was not applied")
        if not (app / "docs" / "UPDATE_ACCEPTANCE_MARKER.txt").is_file():
            raise AssertionError("update payload marker missing")
        print("PASS update_engine_end_to_end")
        print("UPDATE ACCEPTANCE TEST PASSED")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
