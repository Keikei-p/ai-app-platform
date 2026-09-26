from __future__ import annotations

import argparse
import os
import subprocess
import sys
import tempfile
from pathlib import Path


def _run_persistence_test() -> None:
    with tempfile.TemporaryDirectory(prefix="ai-app-platform-accept-") as td:
        env = os.environ.copy()
        env["AI_APP_PLATFORM_STATE_DIR"] = td
        create_code = r'''
from src.core.database import init_db
from src.core.project_manager import ProjectManager
init_db()
slug, path = ProjectManager().create("Persistence Acceptance")
print(slug)
'''
        first = subprocess.run(
            [sys.executable, "-c", create_code],
            cwd=Path.cwd(), env=env, text=True, capture_output=True, check=True,
        )
        slug = first.stdout.strip().splitlines()[-1]
        verify_code = rf'''
from pathlib import Path
from src.core.database import init_db, list_projects
from src.core.config import WORKSPACE_DIR
init_db()
slug = {slug!r}
rows = list_projects()
assert any(x["slug"] == slug for x in rows), rows
root = WORKSPACE_DIR / slug
assert root.is_dir(), root
assert (root / "project.json").is_file(), root
print("PERSISTENCE_OK")
'''
        second = subprocess.run(
            [sys.executable, "-c", verify_code],
            cwd=Path.cwd(), env=env, text=True, capture_output=True, check=True,
        )
        if "PERSISTENCE_OK" not in second.stdout:
            raise RuntimeError("persistence acceptance test did not confirm restart persistence")


def _run_gui_edit_test() -> None:
    # Imports must happen after state isolation so the GUI never touches user data.
    with tempfile.TemporaryDirectory(prefix="ai-app-platform-gui-") as td:
        os.environ["AI_APP_PLATFORM_STATE_DIR"] = td
        from src.ui.main_window import MainWindow

        app = MainWindow()
        try:
            app.deiconify()
            app.update()
            w = app.instruction
            w.delete("1.0", "end")
            w.insert("1.0", "abcde")
            w.mark_set("insert", "1.3")
            w.focus_force()
            app.update()

            w.event_generate("<KeyPress-BackSpace>", keysym="BackSpace")
            w.event_generate("<KeyRelease-BackSpace>", keysym="BackSpace")
            app.update()
            if w.get("1.0", "end-1c") != "abde":
                raise AssertionError("Backspace editing failed")

            app.clipboard_clear()
            app.clipboard_append("XYZ")
            app.update()
            w.tag_add("sel", "1.1", "1.3")
            w.event_generate("<Control-KeyPress-v>", keysym="v")
            app.update()
            if w.get("1.0", "end-1c") != "aXYZe":
                raise AssertionError("Ctrl+V paste failed")

            w.event_generate("<Control-KeyPress-z>", keysym="z")
            app.update()
            if w.get("1.0", "end-1c") != "abde":
                raise AssertionError("Ctrl+Z undo failed")

            w.tag_add("sel", "1.0", "1.1")
            w.event_generate("<KeyPress-Delete>", keysym="Delete")
            w.event_generate("<KeyRelease-Delete>", keysym="Delete")
            app.update()
            if w.get("1.0", "end-1c") != "bde":
                raise AssertionError("Delete editing failed")

            # New-project name entry must be editable, and the project must
            # immediately expose an editable instruction field after creation.
            import tkinter as tk
            from tkinter import ttk
            app.new_project()
            app.update()
            dialogs = [x for x in app.winfo_children() if isinstance(x, tk.Toplevel)]
            if not dialogs:
                raise AssertionError("new project dialog did not open")
            dialog = dialogs[-1]
            entry = next(x for x in dialog.winfo_children() if isinstance(x, ttk.Entry))
            entry.insert(0, "EditableX")
            entry.icursor(tk.END)
            entry.event_generate("<KeyPress-BackSpace>", keysym="BackSpace")
            entry.event_generate("<KeyRelease-BackSpace>", keysym="BackSpace")
            app.update()
            if entry.get() != "Editable":
                raise AssertionError("project-name Backspace editing failed")
            create_button = next(x for x in dialog.winfo_children() if isinstance(x, ttk.Button))
            create_button.invoke()
            app.update()
            if not app.current_slug:
                raise AssertionError("project was not created")

            app.instruction.delete("1.0", "end")
            app.instruction.insert("1.0", "helloX")
            app.instruction.mark_set("insert", "end-1c")
            app.instruction.event_generate("<KeyPress-BackSpace>", keysym="BackSpace")
            app.instruction.event_generate("<KeyRelease-BackSpace>", keysym="BackSpace")
            app.update()
            if app.instruction.get("1.0", "end-1c") != "hello":
                raise AssertionError("instruction editing after project create failed")

            # Project display name must also be editable after creation.
            app.rename_project()
            app.update()
            dialogs = [x for x in app.winfo_children() if isinstance(x, tk.Toplevel)]
            if not dialogs:
                raise AssertionError("rename dialog did not open")
            dialog = dialogs[-1]
            entry = next(x for x in dialog.winfo_children() if isinstance(x, ttk.Entry))
            entry.delete(0, tk.END)
            entry.insert(0, "RenamedX")
            entry.event_generate("<KeyPress-BackSpace>", keysym="BackSpace")
            entry.event_generate("<KeyRelease-BackSpace>", keysym="BackSpace")
            app.update()
            if entry.get() != "Renamed":
                raise AssertionError("rename-field Backspace editing failed")
            save_button = next(x for x in dialog.winfo_children() if isinstance(x, ttk.Button))
            save_button.invoke()
            app.update()
            if "Renamed" not in app.project_label.cget("text"):
                raise AssertionError("project rename did not update UI")

            # Update-center GUI flow: select verified candidate -> apply result.
            import src.ui.main_window as main_window_mod
            from types import SimpleNamespace
            main_window_mod.messagebox.showinfo = lambda *a, **k: None
            main_window_mod.messagebox.showerror = lambda *a, **k: None
            main_window_mod.messagebox.askyesno = lambda *a, **k: True
            main_window_mod.filedialog.askopenfilename = lambda *a, **k: "dummy.aipupdate"

            class FakeUpdater:
                def __init__(self):
                    self.applied = False
                    self.candidate = SimpleNamespace(
                        package_path=Path("dummy.aipupdate"),
                        package_sha256="a" * 64,
                        version="9.9.9",
                        created_at="2026-09-25T00:00:00+00:00",
                        files=(SimpleNamespace(path="src/main.py"),),
                        delete=(),
                        notes="acceptance",
                    )
                def inspect_provider(self, _provider):
                    return self.candidate
                def apply(self, candidate):
                    assert candidate is self.candidate
                    self.applied = True
                    return SimpleNamespace(ok=True, rolled_back=False, message="ok")

            fake_updater = FakeUpdater()
            app.updater = fake_updater
            app.check_update()
            app.update()
            if app.pending_update is not fake_updater.candidate:
                raise AssertionError("update check did not store candidate")
            app.apply_update()
            app.update()
            if not fake_updater.applied or app.pending_update is not None:
                raise AssertionError("update apply GUI flow failed")

            # Code Vault GUI flow: save -> history -> diff -> restore.
            from src.core.config import WORKSPACE_DIR
            live_file = WORKSPACE_DIR / app.current_slug / "vault-gui.txt"
            live_file.write_text("saved-state", encoding="utf-8")
            app.vault_save()
            app.update()
            versions = app.vault.list_versions(app.current_slug)
            if not versions:
                raise AssertionError("Code Vault save did not create history")
            saved_id = versions[0].version_id

            live_file.write_text("changed-state", encoding="utf-8")
            diff = app.vault.diff(app.current_slug, saved_id)
            if "vault-gui.txt" not in diff.modified:
                raise AssertionError("Code Vault diff did not detect change")

            app.vault_history()
            app.update()
            vault_windows = [x for x in app.winfo_children() if isinstance(x, tk.Toplevel) and "Code Vault" in x.title()]
            if not vault_windows:
                raise AssertionError("Code Vault history window did not open")
            for wv in vault_windows:
                wv.destroy()

            app._show_vault_diff(saved_id)
            app.update()
            diff_windows = [x for x in app.winfo_children() if isinstance(x, tk.Toplevel) and "変更を見る" in x.title()]
            if not diff_windows:
                raise AssertionError("Code Vault diff window did not open")
            for wv in diff_windows:
                wv.destroy()

            app.vault.restore(app.current_slug, saved_id, confirmed=True, actor="acceptance-test")
            if live_file.read_text(encoding="utf-8") != "saved-state":
                raise AssertionError("Code Vault restore did not restore selected state")
        finally:
            app.destroy()



def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--gui", action="store_true", help="also run real Tk clipboard/editing checks")
    args = parser.parse_args()

    _run_persistence_test()
    print("PASS persistence_restart")

    if args.gui:
        _run_gui_edit_test()
        print("PASS gui_editing_project_create_rename_code_vault_and_update_center")

    print("ACCEPTANCE TESTS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
