"""Aivy desktop: safe and fast entry point."""
from __future__ import annotations

from src.core.desktop_instance import desktop_instance_lock


def main() -> int:
    with desktop_instance_lock() as can_start:
        if not can_start:
            print("Aivy desktop is already running. Continuing in the existing window.")
            return 0
        # Import Tk after locking to avoid initializing a second GUI during a
        # repeated shortcut click.
        from src.ui.main_window import MainWindow

        MainWindow().mainloop()
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
