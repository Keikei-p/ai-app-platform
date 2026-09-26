from __future__ import annotations

import tempfile
import tkinter as tk
from pathlib import Path

from src.core.remote_devices import RemoteDeviceStore
from src.core.remote_server import RemoteServerController
from src.ui.remote_window import RemoteWindow


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="ai-app-remote-gui-") as td:
        root_dir = Path(td)
        store = RemoteDeviceStore(root_dir / "devices.json", root_dir / "settings.json")
        controller = RemoteServerController(store)
        root = tk.Tk()
        root.withdraw()
        win = RemoteWindow(root, controller)
        try:
            controller.start(lan=False, port=0)
            ticket = controller.create_pairing()
            win.pair_var.set(ticket.code)
            win.refresh()
            if "稼働中" not in win.status_label.cget("text"):
                raise RuntimeError("remote GUI did not show running state")
            if not win.url_var.get().startswith("http://127.0.0.1:"):
                raise RuntimeError("remote GUI localhost URL missing")
            if len(win.pair_var.get()) != 10:
                raise RuntimeError("pairing code not displayed")
            device, _ = store.pair("GUI Phone")
            win.refresh()
            if win.device_list.size() != 1:
                raise RuntimeError("paired device not displayed")
            store.revoke(device.device_id)
            win.refresh()
            if win.device_list.size() != 0:
                raise RuntimeError("revoked device remained visible")
        finally:
            controller.stop(emergency=True)
            win.destroy()
            root.destroy()
    print("REMOTE_GUI_ACCEPTANCE: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
