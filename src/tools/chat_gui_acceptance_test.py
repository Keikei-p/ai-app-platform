from __future__ import annotations
import os
import tempfile
import time
from pathlib import Path
from unittest.mock import patch


def _assert_inside(widget, parent, label):
    if not widget.winfo_viewable():
        raise AssertionError(f"{label}: {widget} is not visible")
    x, y = widget.winfo_rootx(), widget.winfo_rooty()
    px, py = parent.winfo_rootx(), parent.winfo_rooty()
    if (x < px or y < py or x + widget.winfo_width() > px + parent.winfo_width()
            or y + widget.winfo_height() > py + parent.winfo_height()):
        raise AssertionError(f"{label} is clipped")


def _assert_chat_visible(app, label: str) -> None:
    app.update_idletasks()
    for widget in (app.instruction, app.send_button, app.ai_button, app.connection_note):
        _assert_inside(widget, app, label)
    if app.chat_history.winfo_height() < 56:
        raise AssertionError(f"history has no useful reading area at {label}")
    if not app.chat_history.winfo_viewable():
        raise AssertionError(f"chat history is not viewable at {label}")
    if not app.instruction.winfo_viewable():
        raise AssertionError(f"composer input is not viewable at {label}")
    if not app.send_button.winfo_viewable():
        raise AssertionError(f"send button is not viewable at {label}")
    app_top = app.winfo_rooty()
    app_bottom = app_top + app.winfo_height()
    composer_top = app.composer_area.winfo_rooty()
    composer_bottom = composer_top + app.composer_area.winfo_height()
    if composer_top < app_top or composer_bottom > app_bottom:
        raise AssertionError(
            f"composer is clipped at {label}: composer={composer_top}-{composer_bottom}, window={app_top}-{app_bottom}"
        )
    if app.instruction.winfo_height() < 55:
        raise AssertionError(f"composer became too short at {label}: {app.instruction.winfo_height()}px")
    if app.instruction.cget("foreground") == app.instruction.cget("background"):
        raise AssertionError(f"composer text is not visually distinguishable at {label}")


def _wait_idle(app, timeout: float = 15.0) -> None:
    deadline = time.monotonic() + timeout
    while app._busy and time.monotonic() < deadline:
        app.update()
        time.sleep(0.03)
    app.update()
    if app._busy:
        raise AssertionError("chat build did not finish before timeout")


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="ai-app-platform-chat-gui-") as td:
        os.environ["AI_APP_PLATFORM_STATE_DIR"] = td
        from src.ui.main_window import MainWindow
        from src.ui.workspace_center import WorkspaceCenter
        from src.core.config import WORKSPACE_DIR

        configure_styles = MainWindow._configure_styles
        def scaled_styles(window):
            window.tk.call("tk", "scaling", float(os.environ.get("IVY_TEST_TK_SCALING", "1.333")))
            configure_styles(window)

        # Reproduce a short laptop work area independently of the runner monitor.
        with patch("src.ui.main_window.work_area", return_value=(0, 0, 1280, 720)), \
                patch.object(MainWindow, "_configure_styles", scaled_styles):
            app = MainWindow()
        try:
            app.deiconify(); app.update()
            app.chat_engine.configure("none", "", "", remember_key=False)
            app._refresh_ai_status()
            if app.winfo_rooty() + app.winfo_height() > 720:
                raise AssertionError("initial window extends below the laptop work area")
            _assert_chat_visible(app, "initial short-screen startup")

            # Landing page must be AI-first: no category-choice buttons or template picker.
            if hasattr(app, "starter_frame"):
                raise AssertionError("legacy category shortcut frame still exists")
            if not app.welcome_panel.winfo_viewable():
                raise AssertionError("premium AI-first welcome panel is not visible")
            def widget_texts(widget):
                values = []
                try:
                    value = widget.cget("text")
                    if value:
                        values.append(str(value))
                except Exception:
                    pass
                for child in widget.winfo_children():
                    values.extend(widget_texts(child))
                return values
            visible_copy = "\n".join(widget_texts(app))
            for forbidden in ("業務アプリ", "予約アプリ", "相談から"):
                if forbidden in visible_copy:
                    raise AssertionError(f"legacy category choice is still visible: {forbidden}")
            if "Aivy" not in visible_copy or "何を作ってほしいですか？" not in visible_copy:
                raise AssertionError("Aivy AI-first landing identity is missing")
            if app.preview_button.winfo_manager():
                raise AssertionError("preview action should be hidden before a project exists")
            if app.details_button.winfo_manager():
                raise AssertionError("test-details action should be hidden before a project exists")
            if app.download_button.winfo_manager():
                raise AssertionError("download action should be hidden before a project exists")
            for expected_nav in ("最近の会話", "作成したアプリ", "ダウンロード"):
                if expected_nav not in visible_copy:
                    raise AssertionError(f"workspace navigation is missing: {expected_nav}")
            if not app.ai_button.winfo_manager():
                raise AssertionError("AI connection control should remain available on landing")

            # Compact windows must preserve the actual chat and composer inside the visible client area.
            for width, height in ((820, 520), (700, 460), (680, 440), (390, 600), (360, 440)):
                app.geometry(f"{width}x{height}"); app.update()
                app._apply_responsive_layout(width, height); app.update()
                _assert_chat_visible(app, f"{width}x{height}")
                if app.sidebar.winfo_manager():
                    raise AssertionError(f"sidebar did not collapse at {width}x{height}")
                if (app.winfo_width(), app.winfo_height()) != (width, height):
                    raise AssertionError("requested narrow size was silently clamped")
                app._toggle_sidebar(); app.update()
                _assert_inside(app.menu_button, app, "close navigation")
                app._toggle_sidebar(); app.update()
                _assert_chat_visible(app, "after closing navigation")
                app._set_project_actions_visible(True); app.update()
                _assert_inside(app.ai_button, app, "AI setup after project action refresh")
                app._set_project_actions_visible(False)

            # Exercise the real settings action; do not send API requests.
            app.ai_button.invoke(); app.update()
            import tkinter as tk
            dialog = next(w for w in app.winfo_children() if isinstance(w, tk.Toplevel))
            dialog.geometry("340x380"); app.update()
            def descendants(widget):
                for child in widget.winfo_children():
                    yield child
                    yield from descendants(child)
            save = next(w for w in descendants(dialog)
                        if "text" in w.keys() and w.cget("text") == "保存")
            _assert_inside(save, dialog, "AI settings save")
            dialog.destroy()

            from src.core.llm_chat import ChatProviderStatus
            with patch.object(app.chat_engine, "status", return_value=ChatProviderStatus(
                    "ollama", "example", True, "configured")):
                app._refresh_ai_status()
                if "疎通は未確認" not in app.connection_note.cget("text"):
                    raise AssertionError("configuration was mistaken for verified connectivity")
            app._refresh_ai_status()

            app.geometry("1280x820"); app.update()
            app._apply_responsive_layout(1280, 820); app.update()
            _assert_chat_visible(app, "1280x820")

            # A normal greeting must start a real conversation without forcing project setup.
            app.instruction.insert("1.0", "こんにちは")
            app.run_ai(); app.update()
            if app.current_slug is not None:
                raise AssertionError("greeting unexpectedly created a project")
            if not app.current_thread_id:
                raise AssertionError("standalone chat was not assigned a persistent thread")
            greeting_text = app.chat_history.get("1.0", "end-1c")
            if "こんにちは" not in greeting_text or "作りたい" not in greeting_text:
                raise AssertionError("natural opening conversation was not rendered")
            if "AI未接続・定型案内" not in greeting_text:
                raise AssertionError("offline reply was presented as a live AI answer")
            persisted = app.conversations.messages(app.current_thread_id)
            if len(persisted) < 2 or persisted[0].get("role") != "user":
                raise AssertionError("standalone chat was not persisted")

            # Direct creation from a fresh blank chat must gather/review requirements first.
            app.new_project(); app.update()
            app.instruction.insert(
                "1.0",
                "営業担当が案件ごとにタスクを登録して期限と完了状況を管理するWebのToDoアプリを作りたい。ログインとデータ保存が必要。最先端で洗練されたデザイン。"
            )
            app.instruction.focus_force(); app.update()
            if not app.instruction.bind("<Return>"):
                raise AssertionError("Enter send binding is missing")
            result = app._composer_submit()
            if result != "break":
                raise AssertionError("Enter handler did not consume the key event")
            app.update()

            if not app.current_slug:
                raise AssertionError("project was not created for requirement collection")
            if not app.preview_button.winfo_manager():
                raise AssertionError("preview action did not appear after project creation")
            if not app.details_button.winfo_manager():
                raise AssertionError("test-details action did not appear after project creation")
            if not app.download_button.winfo_manager():
                raise AssertionError("download action did not appear after project creation")
            if not app.current_thread_id:
                raise AssertionError("project chat is not linked to a persistent conversation")
            linked = app.conversations.find_for_project(app.current_slug)
            if not linked or linked.thread_id != app.current_thread_id:
                raise AssertionError("conversation/project link is missing")
            project = WORKSPACE_DIR / app.current_slug
            if (project / "app_spec.json").exists():
                raise AssertionError("app generated before explicit approval")
            if not app.build_confirm_button.winfo_manager():
                raise AssertionError("explicit build approval control was not shown")
            for width, height in ((360, 440), (680, 440)):
                app.geometry(f"{width}x{height}"); app.update()
                app._apply_responsive_layout(width, height); app.update()
                _assert_chat_visible(app, "pending build approval")
                _assert_inside(app.build_confirm_button, app, "build approval")
            app.geometry("1280x820"); app.update()
            app._apply_responsive_layout(1280, 820); app.update()
            if app.progress_title_var.get() != "設計内容を確認してください":
                raise AssertionError("review state was not surfaced")

            chat_text = app.chat_history.get("1.0", "end-1c")
            if "この内容で作る" not in chat_text:
                raise AssertionError("design brief review was not rendered")

            # Only the explicit approval may begin generation.
            app.build_confirm_button.invoke()
            _wait_idle(app)
            if not (project / "app_spec.json").is_file():
                raise AssertionError("approved chat did not generate app spec")
            if not (project / "server.py").is_file():
                raise AssertionError("approved chat did not generate functional server")
            chat_text = app.chat_history.get("1.0", "end-1c")
            if "あなた" not in chat_text or "Aivy" not in chat_text:
                raise AssertionError("Aivy chat history not rendered")

            app.instruction.insert("1.0", "スマホでボタンが押しにくいから直して")
            app.send_button.invoke()
            _wait_idle(app)
            memory = Path(td) / "data" / "development_memory.jsonl"
            if not memory.is_file() or "44px" not in memory.read_text(encoding="utf-8"):
                raise AssertionError("human correction was not learned")
            if "Design AI" not in app.output.get("1.0", "end-1c"):
                raise AssertionError("design review not surfaced")
            if app.progress_title_var.get() != "作成とテストが完了":
                raise AssertionError("final progress state was not surfaced")
            if app.send_button.instate(["disabled"]):
                raise AssertionError("send button did not recover after background build")
            artifacts = app.catalog.artifacts(app.current_slug)
            if not any(row.target == "Web" and row.path.endswith(".zip") for row in artifacts):
                raise AssertionError("verified Web artifact was not exposed in download catalog")
            for row in artifacts:
                if not Path(row.path).is_file():
                    raise AssertionError("download catalog exposed a missing artifact")
            cards = app.catalog.list_cards()
            card = next((x for x in cards if x.slug == app.current_slug), None)
            if not card or card.quality != "PASS":
                raise AssertionError("generated app was not surfaced with verified quality state")

            center = WorkspaceCenter(
                app,
                app.conversations,
                app.catalog,
                on_open_thread=lambda _thread_id: None,
                on_open_project=lambda _slug: None,
                on_preview_project=lambda _slug: None,
                on_restore_project=lambda _slug: None,
                initial_tab="projects",
            )
            center.update()
            try:
                if len(center.tabs.tabs()) != 3:
                    raise AssertionError("workspace center does not expose conversation/project/download tabs")
                if not any(row.project_slug == app.current_slug for row in center._thread_rows):
                    raise AssertionError("workspace center did not show the linked conversation")
                if not any(row.slug == app.current_slug for row in center._project_rows):
                    raise AssertionError("workspace center did not show the generated app")
                if not any(row.project_slug == app.current_slug for row in center._artifact_rows):
                    raise AssertionError("workspace center did not show the real generated artifact")
            finally:
                center.destroy()

            if not app.next_actions.winfo_manager():
                raise AssertionError("post-build next-action bar was not shown")
            app.geometry("680x440"); app.update()
            app._apply_responsive_layout(680, 440); app.update()
            _assert_chat_visible(app, "680x440 after build")
            if app.next_actions.winfo_manager():
                raise AssertionError("post-build actions should collapse before the composer on compact windows")
            app.geometry("1280x820"); app.update()
            app._apply_responsive_layout(1280, 820); app.update()

            app.instruction.delete("1.0", "end")
            app.instruction.insert("1.0", "1行目")
            app.instruction.mark_set("insert", "end-1c")
            if not app.instruction.bind("<Shift-Return>"):
                raise AssertionError("Shift+Enter newline binding is missing")
            result = app._composer_newline()
            if result != "break":
                raise AssertionError("Shift+Enter handler did not consume the key event")
            app.instruction.insert("insert", "2行目")
            app.update()
            if app.instruction.get("1.0", "end-1c") != "1行目\n2行目":
                raise AssertionError("Shift+Enter did not insert newline")
        finally:
            app.destroy()
    print("CHAT_GUI_ACCEPTANCE: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
