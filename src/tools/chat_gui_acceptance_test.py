from __future__ import annotations
import os
import tempfile
import time
from pathlib import Path


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
        from src.core.config import WORKSPACE_DIR

        app = MainWindow()
        try:
            app.deiconify(); app.update()

            # A normal greeting must start a real conversation without forcing project setup.
            app.instruction.insert("1.0", "こんにちは")
            app.run_ai(); app.update()
            if app.current_slug is not None:
                raise AssertionError("greeting unexpectedly created a project")
            greeting_text = app.chat_history.get("1.0", "end-1c")
            if "こんにちは" not in greeting_text or "作りたい" not in greeting_text:
                raise AssertionError("natural opening conversation was not rendered")

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
            project = WORKSPACE_DIR / app.current_slug
            if (project / "app_spec.json").exists():
                raise AssertionError("app generated before explicit approval")
            if not app.build_confirm_button.winfo_manager():
                raise AssertionError("explicit build approval control was not shown")
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
            if "あなた" not in chat_text or "AI" not in chat_text:
                raise AssertionError("chat history not rendered")

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
