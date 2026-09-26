from __future__ import annotations
import argparse
from pathlib import Path
from src.core.config import APP_DIR, VERSION
from src.core.update_engine import build_update_package


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a local AI App Platform update package")
    parser.add_argument("output", nargs="?", default=f"AI-App-Platform-v{VERSION}.aipupdate")
    parser.add_argument("--notes", default="")
    args = parser.parse_args()
    out = Path(args.output).resolve()
    build_update_package(APP_DIR, out, version=VERSION, notes=args.notes)
    print(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
