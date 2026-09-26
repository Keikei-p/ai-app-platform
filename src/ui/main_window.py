from __future__ import annotations
import json
import queue
import threading
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from tkinter import font as tkfont
import webbrowser
from ..core.ai_core import AICore
from ..core.config import APP_NAME, VERSION, WORKSPACE_DIR, LOG_DIR
from ..core.database import init_db, list_projects
from ..core.environment import diagnose
from ..core.project_manager import ProjectManager
from ..core.maintenance import MaintenanceInspector
from ..core.backup import BackupManager
from ..core.readiness import ReadinessChecker
from ..core.code_vault import CodeVault
from ..core.update_engine import UpdateEngine, LocalPackageProvider
from ..core.remote_server import RemoteServerController
from ..core.chat_partner import ChatPartner
from ..core.learning_mode import LearningCoach
from ..core.preview_runtime import PreviewRuntime
from .remote_window import RemoteWindow

class MainWindow(tk.Tk):
    def __init__(self):
        super().__init__()
        init_db()
        self.title(f"{APP_NAME} v{VERSION}")
        self.geometry("1140x780")
        self.minsize(920, 660)
        self.core = AICore()
        self.pm = ProjectManager()
        self.maintenance = MaintenanceInspector()
        self.backup = BackupManager()
        self.readiness = ReadinessChecker()
        self.vault = CodeVault()
        self.updater = UpdateEngine()
        self.pending_update = None
        self.remote_controller = RemoteServerController()
        self.chat_partner = ChatPartner()
        self.learning_coach = LearningCoach()
        self.learning_mode = tk.BooleanVar(value=False)
        self.preview_runtime = PreviewRuntime()
        self.remote_window = None
        self.current_slug: str | None = None
        self._busy = False
        self._build_thread = None
        self._ui_queue = queue.Queue()
        self.details_visible = False
        self._showing_welcome = False
        self.ui_font_family = "Yu Gothic UI"
        self.ui_font_semibold = "Yu Gothic UI Semibold"
        self.mono_font_family = "Cascadia Mono"
        self._build()
        self.after(50, self._drain_ui_queue)
        self.refresh_projects()
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.after(350, self._startup_readiness)

    def _configure_styles(self):
        self.configure(background="#FFFFFF")
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass

        families = set(tkfont.families(self))
        if "Yu Gothic UI" not in families:
            self.ui_font_family = "Meiryo UI" if "Meiryo UI" in families else "Segoe UI"
        if "Yu Gothic UI Semibold" not in families:
            self.ui_font_semibold = self.ui_font_family
        if "Cascadia Mono" not in families:
            self.mono_font_family = "Consolas"

        # Replace Tk's retro-looking defaults across dialogs, menus and text fields.
        for name in ("TkDefaultFont", "TkTextFont", "TkMenuFont", "TkCaptionFont", "TkSmallCaptionFont"):
            try:
                tkfont.nametofont(name).configure(family=self.ui_font_family, size=10)
            except tk.TclError:
                pass
        try:
            tkfont.nametofont("TkHeadingFont").configure(
                family=self.ui_font_semibold, size=10, weight="bold"
            )
            tkfont.nametofont("TkFixedFont").configure(family=self.mono_font_family, size=9)
        except tk.TclError:
            pass

        style.configure("Primary.TButton", font=(self.ui_font_semibold, 10, "bold"),
                        padding=(16, 10), relief="flat",
                        background="#111111", foreground="#FFFFFF", borderwidth=0)
        style.map("Primary.TButton",
                  background=[("active", "#2B2B2B"), ("pressed", "#000000"), ("disabled", "#B8B8B8")],
                  foreground=[("disabled", "#F5F5F5")])
        style.configure("Secondary.TButton", font=(self.ui_font_family, 10),
                        padding=(13, 9), relief="flat",
                        background="#F4F4F4", foreground="#262626", borderwidth=0)
        style.map("Secondary.TButton",
                  background=[("active", "#EAEAEA"), ("pressed", "#E1E1E1")])
        style.configure("Sidebar.TButton", font=(self.ui_font_family, 10),
                        padding=(12, 10), relief="flat",
                        background="#F7F7F8", foreground="#262626", borderwidth=0)
        style.map("Sidebar.TButton",
                  background=[("active", "#ECECEE"), ("pressed", "#E5E5E7")])
        style.configure("Sidebar.TCheckbutton", font=(self.ui_font_family, 9),
                        background="#F7F7F8", foreground="#666666")
        style.map("Sidebar.TCheckbutton", background=[("active", "#F7F7F8")])

    def _build(self):
        self._configure_styles()
        self.geometry("1280x820")
        self.minsize(1000, 680)

        shell = tk.Frame(self, bg="#FFFFFF")
        shell.pack(fill="both", expand=True)

        # ChatGPT-style neutral sidebar: projects and secondary tools only.
        sidebar = tk.Frame(shell, bg="#F7F7F8", width=250)
        sidebar.pack(side="left", fill="y")
        sidebar.pack_propagate(False)

        brand = tk.Frame(sidebar, bg="#F7F7F8")
        brand.pack(fill="x", padx=14, pady=(14, 8))
        tk.Label(brand, text="AI App Platform", bg="#F7F7F8", fg="#202123",
                 font=(self.ui_font_semibold, 14, "bold")).pack(anchor="w")
        tk.Label(brand, text=f"v{VERSION}", bg="#F7F7F8", fg="#8E8E8E",
                 font=(self.ui_font_family, 8)).pack(anchor="w", pady=(2, 0))

        self.new_app_button = ttk.Button(
            sidebar, text="＋  新しいチャット", style="Sidebar.TButton", command=self.new_project
        )
        self.new_app_button.pack(fill="x", padx=10, pady=(4, 12))

        tk.Label(sidebar, text="プロジェクト", bg="#F7F7F8", fg="#8E8E8E",
                 font=(self.ui_font_semibold, 9, "bold")).pack(anchor="w", padx=16, pady=(4, 5))
        self.projects = tk.Listbox(
            sidebar, activestyle="none", borderwidth=0, highlightthickness=0,
            bg="#F7F7F8", fg="#343541", selectbackground="#ECECEC",
            selectforeground="#202123", font=(self.ui_font_family, 10), exportselection=False
        )
        self.projects.pack(fill="both", expand=True, padx=8)
        self.projects.bind("<<ListboxSelect>>", self.on_project_select)

        sidebar_bottom = tk.Frame(sidebar, bg="#F7F7F8")
        sidebar_bottom.pack(fill="x", padx=10, pady=12)
        ttk.Checkbutton(
            sidebar_bottom, text="学習モード  —  理由も説明", variable=self.learning_mode,
            style="Sidebar.TCheckbutton"
        ).pack(anchor="w", padx=4, pady=(0, 8))
        ttk.Button(sidebar_bottom, text="履歴・復元", style="Sidebar.TButton",
                   command=self.vault_history).pack(fill="x", pady=2)
        ttk.Button(sidebar_bottom, text="プロジェクト名を変更", style="Sidebar.TButton",
                   command=self.rename_project).pack(fill="x", pady=2)
        ttk.Button(sidebar_bottom, text="設定・診断", style="Sidebar.TButton",
                   command=self._toggle_details).pack(fill="x", pady=2)

        main = tk.Frame(shell, bg="#FFFFFF")
        main.pack(side="left", fill="both", expand=True)

        # Quiet header: project name + only the two actions users need often.
        header = tk.Frame(main, bg="#FFFFFF", height=62)
        header.pack(fill="x")
        header.pack_propagate(False)
        header_left = tk.Frame(header, bg="#FFFFFF")
        header_left.pack(side="left", fill="y", padx=(26, 8))
        self.project_label = tk.Label(
            header_left, text="新しいチャット", bg="#FFFFFF", fg="#202123",
            font=(self.ui_font_semibold, 12, "bold")
        )
        self.project_label.pack(anchor="w", pady=(13, 0))
        self.activity_var = tk.StringVar(value="何を作りたいか、そのまま話してください")
        tk.Label(header_left, textvariable=self.activity_var, bg="#FFFFFF", fg="#8E8E8E",
                 font=(self.ui_font_family, 9)).pack(anchor="w", pady=(2, 0))

        header_right = tk.Frame(header, bg="#FFFFFF")
        header_right.pack(side="right", padx=(8, 18), pady=12)
        self.preview_button = ttk.Button(
            header_right, text="アプリを確認", style="Secondary.TButton", command=self.preview
        )
        self.preview_button.pack(side="left", padx=3)
        self.details_button = ttk.Button(
            header_right, text="テスト結果", style="Secondary.TButton", command=self._toggle_details
        )
        self.details_button.pack(side="left", padx=3)

        tk.Frame(main, bg="#ECECEC", height=1).pack(fill="x")

        # Visible progress area. It stays compact but always explains the current stage.
        self.progress_card = tk.Frame(main, bg="#F8F8F9", height=76)
        self.progress_card.pack(fill="x", padx=24, pady=(12, 0))
        self.progress_card.pack_propagate(False)

        progress_top = tk.Frame(self.progress_card, bg="#F8F8F9")
        progress_top.pack(fill="x", padx=16, pady=(10, 6))
        self.progress_title_var = tk.StringVar(value="準備完了")
        self.progress_detail_var = tk.StringVar(value="メッセージを送ると、ここにAIの作業状況が表示されます")
        tk.Label(progress_top, textvariable=self.progress_title_var, bg="#F8F8F9", fg="#202123",
                 font=("Segoe UI", 10, "bold")).pack(side="left")
        tk.Label(progress_top, textvariable=self.progress_detail_var, bg="#F8F8F9", fg="#8E8E8E",
                 font=(self.ui_font_family, 9)).pack(side="right")

        stages = tk.Frame(self.progress_card, bg="#F8F8F9")
        stages.pack(fill="x", padx=16, pady=(0, 9))
        self._progress_segments = []
        self._progress_labels = []
        stage_names = ["要件確認", "設計", "作成", "デザイン確認", "テスト", "完了"]
        for i, name in enumerate(stage_names):
            cell = tk.Frame(stages, bg="#F8F8F9")
            cell.pack(side="left", fill="x", expand=True, padx=(0 if i == 0 else 3, 0))
            bar = tk.Frame(cell, bg="#E5E5E5", height=4)
            bar.pack(fill="x")
            bar.pack_propagate(False)
            label = tk.Label(cell, text=name, bg="#F8F8F9", fg="#A0A0A0",
                             font=(self.ui_font_family, 8))
            label.pack(anchor="w", pady=(3, 0))
            self._progress_segments.append(bar)
            self._progress_labels.append(label)

        workspace = tk.Frame(main, bg="#FFFFFF")
        workspace.pack(fill="both", expand=True)

        chat_column = tk.Frame(workspace, bg="#FFFFFF")
        chat_column.pack(side="left", fill="both", expand=True)

        history_wrap = tk.Frame(chat_column, bg="#FFFFFF")
        history_wrap.pack(fill="both", expand=True, padx=(56, 34), pady=(8, 0))
        scrollbar = ttk.Scrollbar(history_wrap, orient="vertical")
        scrollbar.pack(side="right", fill="y")
        self.chat_history = tk.Text(
            history_wrap, wrap="word", state="disabled", relief="flat", borderwidth=0,
            highlightthickness=0, background="#FFFFFF", foreground="#202123",
            insertbackground="#202123", font=(self.ui_font_family, 11), padx=18, pady=18,
            yscrollcommand=scrollbar.set, spacing3=5
        )
        self.chat_history.pack(side="left", fill="both", expand=True)
        scrollbar.configure(command=self.chat_history.yview)
        self._enable_readonly_copy(self.chat_history)

        self.chat_history.tag_configure(
            "user_label", foreground="#8E8E8E", font=(self.ui_font_semibold, 8, "bold"),
            justify="right", lmargin1=155, rmargin=12, spacing1=12
        )
        self.chat_history.tag_configure(
            "user", foreground="#202123", background="#F4F4F4",
            lmargin1=155, lmargin2=155, rmargin=12, spacing1=3, spacing3=16
        )
        self.chat_history.tag_configure(
            "assistant_label", foreground="#10A37F", font=(self.ui_font_semibold, 8, "bold"),
            lmargin1=12, rmargin=155, spacing1=10
        )
        self.chat_history.tag_configure(
            "assistant", foreground="#202123",
            lmargin1=12, lmargin2=12, rmargin=155, spacing1=3, spacing3=18
        )
        self.chat_history.tag_configure(
            "welcome_title", foreground="#202123", font=(self.ui_font_semibold, 22, "bold"),
            justify="center", spacing1=58, spacing3=10
        )
        self.chat_history.tag_configure(
            "welcome", foreground="#747474", font=(self.ui_font_family, 11),
            justify="center", lmargin1=90, rmargin=90, spacing3=10
        )

        # Starter cards feel like modern AI suggestions and start the conversation immediately.
        self.starter_frame = tk.Frame(chat_column, bg="#FFFFFF")
        self.starter_frame.pack(fill="x", padx=72, pady=(0, 12))
        self._starter_cards = []
        suggestions = [
            ("業務アプリ", "仕事の管理をもっと楽に", "営業実績を管理できるWebアプリを作りたい"),
            ("予約アプリ", "スマホで簡単に予約", "スマホで使いやすい予約アプリを作りたい"),
            ("相談から", "まだ決まってなくてもOK", "作りたいものがまだ曖昧なので、アイデア整理から手伝って"),
        ]
        for title, subtitle, prompt in suggestions:
            card = self._make_prompt_card(self.starter_frame, title, subtitle, prompt)
            card.pack(side="left", expand=True, fill="both", padx=5)
            self._starter_cards.append(card)

        composer_area = tk.Frame(chat_column, bg="#FFFFFF")
        composer_area.pack(fill="x", padx=(72, 54), pady=(4, 18))
        composer = tk.Frame(
            composer_area, bg="#F7F7F8", highlightbackground="#D9D9DC",
            highlightcolor="#BDBDC2", highlightthickness=1, bd=0
        )
        composer.pack(fill="x")
        self.composer = composer
        self.instruction = tk.Text(
            composer, height=5, wrap="word", undo=True, autoseparators=True, maxundo=-1,
            relief="flat", borderwidth=0, highlightthickness=0, background="#F7F7F8",
            foreground="#202123", insertbackground="#202123", font=(self.ui_font_family, 12),
            padx=18, pady=15
        )
        self.instruction.pack(side="left", fill="both", expand=True)
        self._enable_text_editing(self.instruction)
        self.instruction.bind("<Return>", self._composer_submit, add=False)
        self.instruction.bind("<KP_Enter>", self._composer_submit, add=False)
        self.instruction.bind("<Shift-Return>", self._composer_newline, add=False)
        self.instruction.bind("<Control-Return>", self._composer_submit, add=False)
        self.instruction.bind("<KeyRelease>", self._update_placeholder, add=True)
        self.instruction.bind("<FocusIn>", self._update_placeholder, add=True)
        self.instruction.bind("<FocusOut>", self._update_placeholder, add=True)

        self.placeholder_label = tk.Label(
            composer, text="作りたいアプリや相談したいことを入力…",
            bg="#F7F7F8", fg="#9A9A9F", font=(self.ui_font_family, 11)
        )
        self.placeholder_label.place(x=18, y=15)
        self.placeholder_label.bind("<Button-1>", lambda _e: self.instruction.focus_force())

        send_wrap = tk.Frame(composer, bg="#F7F7F8")
        send_wrap.pack(side="right", fill="y", padx=(8, 12), pady=12)
        self.send_button = ttk.Button(
            send_wrap, text="送信  ↑", style="Primary.TButton", command=self.run_ai
        )
        self.send_button.pack(side="bottom")

        footer = tk.Frame(composer_area, bg="#FFFFFF")
        footer.pack(fill="x", pady=(6, 0))
        tk.Label(footer, text="Enterで送信  ·  Shift+Enterで改行",
                 bg="#FFFFFF", fg="#A0A0A0", font=(self.ui_font_family, 8)).pack(side="left")
        tk.Label(footer, text="生成物は自動テスト後に「完成候補」として表示します",
                 bg="#FFFFFF", fg="#A0A0A0", font=(self.ui_font_family, 8)).pack(side="right")

        # Advanced information stays hidden unless requested.
        self.details_panel = tk.Frame(workspace, bg="#F7F7F8", width=330)
        self.details_panel.pack_propagate(False)
        tk.Label(self.details_panel, text="テスト結果と詳細", bg="#F7F7F8", fg="#202123",
                 font=(self.ui_font_semibold, 12, "bold")).pack(anchor="w", padx=16, pady=(18, 2))
        tk.Label(self.details_panel, text="普段は閉じたままで大丈夫です", bg="#F7F7F8", fg="#8E8E8E",
                 font=(self.ui_font_family, 9)).pack(anchor="w", padx=16, pady=(0, 10))
        self.output = tk.Text(
            self.details_panel, height=24, wrap="word", state="disabled", relief="flat",
            background="#FFFFFF", foreground="#444444", borderwidth=0,
            highlightthickness=1, highlightbackground="#E5E5E5",
            font=(self.mono_font_family, 9), padx=10, pady=10
        )
        self.output.pack(fill="both", expand=True, padx=12)
        self._enable_readonly_copy(self.output)
        actions = tk.Frame(self.details_panel, bg="#F7F7F8")
        actions.pack(fill="x", padx=12, pady=12)
        ttk.Button(actions, text="公開前チェック", style="Secondary.TButton",
                   command=self.show_release_risk).pack(fill="x", pady=2)
        ttk.Button(actions, text="準備状況を確認", style="Secondary.TButton",
                   command=self.show_readiness).pack(fill="x", pady=2)
        ttk.Button(actions, text="環境診断", style="Secondary.TButton",
                   command=self.show_diagnostics).pack(fill="x", pady=2)
        ttk.Button(actions, text="バックアップを作る", style="Secondary.TButton",
                   command=self.make_backup).pack(fill="x", pady=2)
        ttk.Button(actions, text="リモート機能", style="Secondary.TButton",
                   command=self.open_remote).pack(fill="x", pady=2)
        ttk.Button(actions, text="更新パッケージ", style="Secondary.TButton",
                   command=self.check_update).pack(fill="x", pady=2)

        self._show_empty_chat()
        self._set_progress("idle", "準備完了", "何を作りたいか、そのまま話してください")
        self.after(120, self.instruction.focus_force)

    def _toggle_details(self):
        if self.details_visible:
            self.details_panel.pack_forget()
            self.details_visible = False
            self.details_button.configure(text="テスト結果")
        else:
            self.details_panel.pack(side="right", fill="y", padx=(8, 0))
            self.details_visible = True
            self.details_button.configure(text="テスト結果を閉じる")

    def _use_suggestion(self, prompt: str):
        if self._busy:
            return
        self.instruction.delete("1.0", "end")
        self.instruction.insert("1.0", prompt)
        self.instruction.focus_force()

    def _show_empty_chat(self):
        self.chat_history.configure(state="normal")
        if not self.chat_history.get("1.0", "end-1c").strip():
            self.chat_history.insert("end", "今日は何を作りますか？\n", "welcome_title")
            self.chat_history.insert(
                "end",
                "専門用語は不要です。作りたいものを普段の言葉で話してください。\n"
                "AIが必要なことだけ確認し、設計・作成・テストまで進めます。\n",
                "welcome"
            )
        self.chat_history.configure(state="disabled")

    def _sync_starter_visibility(self):
        if not hasattr(self, "starter_frame"):
            return
        has_history = False
        if self.current_slug:
            path = WORKSPACE_DIR / self.current_slug
            has_history = bool(self.chat_partner.history(path))
        if has_history:
            self.starter_frame.pack_forget()
        elif not self.starter_frame.winfo_manager():
            self.starter_frame.pack(fill="x", padx=72, pady=(0, 8), before=self.instruction.master.master)

    def _composer_submit(self, _event=None):
        if self._busy:
            return "break"
        self.run_ai()
        return "break"

    def _composer_newline(self, _event=None):
        if not self._busy:
            self.instruction.insert("insert", "\n")
        return "break"

    def _set_progress(self, stage: str, title: str, detail: str):
        order = ["understand", "plan", "build", "design", "test", "done"]
        if stage == "idle":
            active = -1
        elif stage == "issue":
            active = len(order) - 1
        else:
            active = order.index(stage) if stage in order else 0
        for i, (bar, label) in enumerate(zip(self._progress_segments, self._progress_labels)):
            if stage == "issue" and i == len(order) - 1:
                color = "#D97706"
                text_color = "#92400E"
            elif active >= 0 and i <= active:
                color = "#10A37F"
                text_color = "#202123" if i == active else "#666666"
            else:
                color = "#E5E5E5"
                text_color = "#A0A0A0"
            bar.configure(bg=color)
            label.configure(fg=text_color)
        self.progress_title_var.set(title)
        self.progress_detail_var.set(detail)
        self.activity_var.set(detail)

    def _set_busy(self, busy: bool, message: str | None = None):
        self._busy = busy
        if hasattr(self, "send_button"):
            self.send_button.configure(text="作業中…" if busy else "送信")
            self.send_button.state(["disabled"] if busy else ["!disabled"])
        self.instruction.configure(state="disabled" if busy else "normal")
        try:
            self.projects.configure(state="disabled" if busy else "normal")
            self.new_app_button.state(["disabled"] if busy else ["!disabled"])
        except (tk.TclError, AttributeError):
            pass
        if message:
            self.activity_var.set(message)
        self.update_idletasks()

    def _enable_text_editing(self, widget):
        """Windows-friendly text editing with explicit correction and clipboard fallbacks."""
        try:
            widget.configure(takefocus=True)
        except tk.TclError:
            pass

        def is_text():
            return isinstance(widget, tk.Text)

        def has_selection():
            try:
                if is_text():
                    return bool(widget.tag_ranges("sel"))
                return bool(widget.selection_present())
            except tk.TclError:
                return False

        def selection_bounds():
            try:
                if is_text():
                    ranges = widget.tag_ranges("sel")
                    return (ranges[0], ranges[1]) if ranges else None
                if widget.selection_present():
                    return ("sel.first", "sel.last")
            except tk.TclError:
                pass
            return None

        def selected_text():
            bounds = selection_bounds()
            if not bounds:
                return ""
            try:
                return widget.get(bounds[0], bounds[1])
            except tk.TclError:
                return ""

        def delete_selection():
            bounds = selection_bounds()
            if not bounds:
                return False
            try:
                widget.delete(bounds[0], bounds[1])
                return True
            except tk.TclError:
                return False

        def backspace(_event=None):
            try:
                if delete_selection():
                    return "break"
                if is_text():
                    if widget.compare("insert", ">", "1.0"):
                        widget.delete("insert-1c", "insert")
                else:
                    pos = int(widget.index("insert"))
                    if pos > 0:
                        widget.delete(pos - 1, pos)
            except (tk.TclError, ValueError):
                pass
            return "break"

        def delete_forward(_event=None):
            try:
                if delete_selection():
                    return "break"
                if is_text():
                    if widget.compare("insert", "<", "end-1c"):
                        widget.delete("insert", "insert+1c")
                else:
                    pos = int(widget.index("insert"))
                    if pos < len(widget.get()):
                        widget.delete(pos, pos + 1)
            except (tk.TclError, ValueError):
                pass
            return "break"

        def copy(_event=None):
            text = selected_text()
            if text:
                try:
                    self.clipboard_clear()
                    self.clipboard_append(text)
                    self.update_idletasks()
                except tk.TclError:
                    pass
            return "break"

        def cut(_event=None):
            if selected_text():
                copy()
                delete_selection()
            return "break"

        def paste(_event=None):
            try:
                text = self.clipboard_get()
            except tk.TclError:
                return "break"
            try:
                bounds = selection_bounds()
                if is_text() and bounds:
                    # Text.replace keeps replacing a selection as one undoable action.
                    widget.replace(bounds[0], bounds[1], text)
                else:
                    delete_selection()
                    widget.insert("insert", text)
            except tk.TclError:
                pass
            return "break"

        def select_all(_event=None):
            try:
                if is_text():
                    widget.tag_add("sel", "1.0", "end-1c")
                    widget.mark_set("insert", "end-1c")
                    widget.see("insert")
                else:
                    widget.selection_range(0, tk.END)
                    widget.icursor(tk.END)
            except tk.TclError:
                pass
            return "break"

        def undo(_event=None):
            if is_text():
                try:
                    widget.edit_undo()
                except tk.TclError:
                    pass
            return "break"

        def redo(_event=None):
            if is_text():
                try:
                    widget.edit_redo()
                except tk.TclError:
                    pass
            return "break"

        bindings = (
            ("<BackSpace>", backspace), ("<Delete>", delete_forward),
            ("<Control-c>", copy), ("<Control-x>", cut), ("<Control-v>", paste),
            ("<Control-a>", select_all), ("<Control-z>", undo), ("<Control-y>", redo),
            ("<Shift-Insert>", paste), ("<Control-Insert>", copy),
        )
        for seq, fn in bindings:
            try:
                widget.bind(seq, fn, add=False)
            except tk.TclError:
                pass

        menu = tk.Menu(widget, tearoff=False)
        menu.add_command(label="元に戻す", command=undo)
        menu.add_separator()
        menu.add_command(label="切り取り", command=cut)
        menu.add_command(label="コピー", command=copy)
        menu.add_command(label="貼り付け", command=paste)
        menu.add_separator()
        menu.add_command(label="すべて選択", command=select_all)

        def popup(event):
            try:
                widget.focus_force()
                menu.tk_popup(event.x_root, event.y_root)
            finally:
                menu.grab_release()
            return "break"

        widget.bind("<Button-3>", popup, add=False)

    def _enable_readonly_copy(self, widget):
        """Allow selecting/copying diagnostics even though the output widget is read-only."""
        def copy(_event=None):
            try: widget.event_generate("<<Copy>>")
            except tk.TclError: pass
            return "break"

        def select_all(_event=None):
            try:
                widget.tag_add("sel", "1.0", "end-1c")
                widget.mark_set("insert", "end-1c")
                widget.see("insert")
            except tk.TclError: pass
            return "break"

        widget.bind("<Control-c>", copy)
        widget.bind("<Control-a>", select_all)
        widget.bind("<Command-c>", copy)
        widget.bind("<Command-a>", select_all)

        menu = tk.Menu(widget, tearoff=False)
        menu.add_command(label="コピー", command=lambda: copy())
        menu.add_command(label="すべて選択", command=lambda: select_all())
        def popup(event):
            try:
                menu.tk_popup(event.x_root, event.y_root)
            finally:
                menu.grab_release()
            return "break"
        widget.bind("<Button-3>", popup)


    def open_remote(self):
        try:
            if self.remote_window is not None and self.remote_window.winfo_exists():
                self.remote_window.lift(); self.remote_window.focus_force(); return
        except tk.TclError:
            pass
        self.remote_window = RemoteWindow(self, self.remote_controller)

    def _on_close(self):
        try:
            self.preview_runtime.stop()
            if self.remote_controller.running:
                self.remote_controller.stop()
        finally:
            self.destroy()

    def check_update(self):
        path = filedialog.askopenfilename(
            parent=self,
            title="更新パッケージを選択",
            filetypes=[("AI App Platform Update", "*.aipupdate *.zip"), ("ZIP", "*.zip"), ("All files", "*.*")],
        )
        if not path:
            return
        try:
            candidate = self.updater.inspect_provider(LocalPackageProvider(path))
            self.pending_update = candidate
            created = candidate.created_at.replace("T", " ")[:19] if candidate.created_at else "-"
            self.write(f"✓ 更新確認: v{candidate.version} / {len(candidate.files)} files / SHA-256 {candidate.package_sha256[:16]}…")
            messagebox.showinfo(
                "更新を確認",
                f"更新パッケージを確認しました。\n\n現在: v{VERSION}\n更新: v{candidate.version}\n作成: {created}\nファイル: {len(candidate.files)}\n\n「更新する」で適用できます。",
                parent=self,
            )
        except Exception as exc:
            self.pending_update = None
            self.write(f"⚠ 更新パッケージ拒否: {exc}")
            messagebox.showerror("更新を確認", f"この更新パッケージは使用できません。\n\n{exc}", parent=self)

    def apply_update(self):
        candidate = self.pending_update
        if candidate is None:
            messagebox.showinfo("更新", "先に「更新を確認」から更新パッケージを選択してください。", parent=self)
            return
        if not messagebox.askyesno(
            "更新する",
            f"v{VERSION} → v{candidate.version} に更新します。\n\n更新前バックアップと自動テストを実行し、失敗時は元の本体へ戻します。\n実行しますか？",
            parent=self,
        ):
            return
        self.write(f"更新開始: v{VERSION} → v{candidate.version}")
        self.update_idletasks()
        result = self.updater.apply(candidate)
        if result.ok:
            self.write(f"✓ 更新完了: v{candidate.version}")
            self.pending_update = None
            messagebox.showinfo(
                "更新完了",
                "更新と自動テストが完了しました。\n\nいったんアプリを閉じて START.bat から再起動してください。",
                parent=self,
            )
        else:
            status = "ロールバック済み" if result.rolled_back else "要確認"
            self.write(f"⚠ 更新失敗 ({status}): {result.message}")
            messagebox.showerror("更新失敗", result.message, parent=self)

    def write(self, text: str):
        self.output.configure(state="normal"); self.output.insert("end", text + "\n"); self.output.see("end"); self.output.configure(state="disabled")

    def _startup_readiness(self):
        report = self.readiness.run()
        if report.ready_for_local_mvp:
            self.write("✓ 初回準備チェック: ローカルMVPを実行できます。")
        else:
            failed = [c.key for c in report.checks if c.status == "fail"]
            self.write("⚠ 初回準備チェック: 要確認 → " + ", ".join(failed))

    def refresh_projects(self):
        self.project_rows = list_projects()
        self.projects.delete(0, "end")
        for p in self.project_rows: self.projects.insert("end", p["name"])

    def on_project_select(self, _event=None):
        sel = self.projects.curselection()
        if not sel:
            return
        row = self.project_rows[sel[0]]
        self.current_slug = row["slug"]
        self.project_label.configure(text=row["name"])
        self._load_chat_history()
        self._sync_starter_visibility()
        self._set_progress("idle", "会話を続けられます", "修正したいことをそのまま送ってください")

    def new_project(self):
        """Start a blank chat immediately; the first message creates and names the project."""
        if self._busy:
            return
        self.current_slug = None
        self.projects.selection_clear(0, "end")
        self.project_label.configure(text="新しいチャット")
        self.chat_history.configure(state="normal")
        self.chat_history.delete("1.0", "end")
        self.chat_history.configure(state="disabled")
        self._show_empty_chat()
        self.instruction.configure(state="normal")
        self.instruction.delete("1.0", "end")
        self._sync_starter_visibility()
        self._set_progress("idle", "準備完了", "何を作りたいか、そのまま話してください")
        self.instruction.focus_force()

    def rename_project(self):
        p = self._current()
        if not p:
            return
        dialog = tk.Toplevel(self)
        dialog.title("プロジェクト名を変更")
        dialog.transient(self)
        dialog.grab_set()
        dialog.geometry("430x180")
        ttk.Label(dialog, text="新しいプロジェクト名", font=("Segoe UI", 11, "bold")).pack(anchor="w", padx=18, pady=(18,6))
        entry = ttk.Entry(dialog)
        entry.pack(fill="x", padx=18)
        entry.insert(0, p["name"])
        entry.selection_range(0, tk.END)
        entry.icursor(tk.END)
        self._enable_text_editing(entry)
        entry.focus_force()

        def save():
            name = entry.get().strip()
            if not name:
                return
            self.pm.rename(self.current_slug, name)
            dialog.destroy()
            self.refresh_projects()
            self.project_label.configure(text=name)
            self.instruction.configure(state="normal")
            self.instruction.focus_force()
            self.write(f"✓ プロジェクト名変更: {name}")

        entry.bind("<Return>", lambda _e: save())
        ttk.Button(dialog, text="保存", command=save).pack(pady=18)

    def _current(self):
        if not self.current_slug:
            messagebox.showinfo("プロジェクト", "先にプロジェクトを作成または選択してください。")
            return None
        for p in self.project_rows:
            if p["slug"] == self.current_slug: return p
        path = WORKSPACE_DIR / self.current_slug / "project.json"
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None

    def _append_chat(self, role: str, text: str):
        self.chat_history.configure(state="normal")
        if role == "user":
            self.chat_history.insert("end", "あなた\n", "user_label")
            self.chat_history.insert("end", f"{text}\n", "user")
        else:
            self.chat_history.insert("end", "AI App Platform\n", "assistant_label")
            self.chat_history.insert("end", f"{text}\n", "assistant")
        self.chat_history.see("end")
        self.chat_history.configure(state="disabled")

    def _load_chat_history(self):
        self.chat_history.configure(state="normal")
        self.chat_history.delete("1.0", "end")
        rows = []
        if self.current_slug:
            path = WORKSPACE_DIR / self.current_slug
            rows = self.chat_partner.history(path)
            for row in rows:
                if row.get("role") == "user":
                    self.chat_history.insert("end", "あなた\n", "user_label")
                    self.chat_history.insert("end", f"{row.get('content','')}\n", "user")
                else:
                    self.chat_history.insert("end", "AI App Platform\n", "assistant_label")
                    self.chat_history.insert("end", f"{row.get('content','')}\n", "assistant")
        self.chat_history.configure(state="disabled")
        if not rows:
            self._show_empty_chat()
        self.chat_history.see("end")
        self._sync_starter_visibility()

    def _ensure_chat_project(self, first_message: str):
        if self.current_slug:
            return self._current()
        name = self.chat_partner.suggest_project_name(first_message)
        slug, _ = self.pm.create(name)
        self.refresh_projects()
        self.current_slug = slug
        self.project_label.configure(text=name)
        # Select the newly created row when possible.
        for i, row in enumerate(self.project_rows):
            if row["slug"] == slug:
                self.projects.selection_clear(0, "end")
                self.projects.selection_set(i)
                self.projects.see(i)
                break
        self.write(f"✓ 新しいアプリを自動作成: {name}")
        return self._current()

    def _progress_from_core(self, stage: str, message: str):
        self._ui_queue.put(("progress", stage, message))

    def _drain_ui_queue(self):
        titles = {
            "understand": "要件を確認中",
            "plan": "設計中",
            "build": "アプリを作成中",
            "design": "デザインを確認中",
            "test": "自動テスト中",
            "done": "確認完了",
            "issue": "確認が必要です",
        }
        try:
            while True:
                item = self._ui_queue.get_nowait()
                kind = item[0]
                if kind == "progress":
                    _, stage, message = item
                    self._set_progress(stage, titles.get(stage, "作業中"), message)
                elif kind == "result":
                    _, result, learning_enabled = item
                    self._finish_build(result, learning_enabled)
                elif kind == "error":
                    _, exc = item
                    self._handle_build_error(exc)
        except queue.Empty:
            pass
        try:
            self.after(50, self._drain_ui_queue)
        except tk.TclError:
            pass

    def run_ai(self):
        if self._busy:
            return
        text = self.instruction.get("1.0", "end").strip()
        if not text:
            self._set_progress("idle", "メッセージを入力してください", "作りたいものや直したいことを書いて送信してください")
            self.instruction.focus_force()
            return

        self._set_busy(True, "内容を確認しています")
        self._set_progress("understand", "要件を確認中", "メッセージの内容を読み取っています")
        try:
            p = self._ensure_chat_project(text)
            if not p:
                self._set_busy(False)
                return
            path = WORKSPACE_DIR / self.current_slug
            has_generated = (path / "app_spec.json").exists()
            self.instruction.configure(state="normal")
            self.instruction.delete("1.0", "end")
            self.instruction.configure(state="disabled")

            decision = self.chat_partner.handle(
                path, p["name"], self.current_slug, text, has_generated=has_generated
            )
            self._load_chat_history()

            if decision.action == "ask":
                self.write("AIが必要情報を確認中")
                self._set_progress("understand", "あなたの返事待ち", decision.message)
                self._set_busy(False)
                self.instruction.focus_force()
                return

            if decision.action == "explain":
                spec_path = path / "app_spec.json"
                if not spec_path.exists():
                    self._append_chat("assistant", "まだ生成前なので、まずアプリを作成してから説明します。")
                    self._set_progress("idle", "まだ生成前です", "先に作りたいアプリを送ってください")
                else:
                    from ..core.app_spec import AppSpec
                    raw = json.loads(spec_path.read_text(encoding="utf-8"))
                    spec = AppSpec(**raw)
                    files = [x.name for x in path.iterdir() if x.is_file()]
                    explanation = self.learning_coach.explain(spec, files)
                    self._append_chat("assistant", explanation)
                    self._set_progress("done", "説明しました", "続けて質問や修正を送れます")
                self._set_busy(False)
                self.instruction.focus_force()
                return

            self.write("AI: 要件確認 → 設計 → 作成 → デザイン確認 → テスト")
            learning_enabled = bool(self.learning_mode.get())
            instruction = decision.instruction or text
            build_slug = self.current_slug
            self._build_thread = threading.Thread(
                target=self._run_build_background,
                args=(p, build_slug, path, instruction, learning_enabled),
                daemon=True,
            )
            self._build_thread.start()
        except Exception as exc:
            self._handle_build_error(exc)

    def _run_build_background(self, project: dict, slug: str, path, instruction: str, learning_enabled: bool):
        try:
            result = self.core.execute(
                project["name"], slug, path, instruction,
                progress=self._progress_from_core,
            )
            self._ui_queue.put(("result", result, learning_enabled))
        except Exception as exc:
            self._ui_queue.put(("error", exc))

    def _finish_build(self, result, learning_enabled: bool):
        self._append_chat("assistant", result.message)
        self.write(("✓ " if result.ok else "⚠ ") + result.message)
        if result.plan:
            spec = result.plan["spec"]
            self.write(f"仕様: {spec['app_type']} / {', '.join(spec['targets'])}")
        for t in result.tests:
            self.write(f"{'PASS' if t.passed else 'FAIL'} {t.name}: {t.detail}")
        if result.design_review:
            self.write(
                f"Design AI: {result.design_review.score}/100 "
                f"{'PASS' if result.design_review.passed else '要改善'}"
            )
        blockers = result.capability_gaps or []
        if blockers:
            self.write("未完了項目:")
            for gap in blockers[:8]:
                self.write(f"・{gap.reason} / 根拠: {gap.evidence} / 次: {gap.next_step}")
        if learning_enabled and result.plan:
            from ..core.app_spec import AppSpec
            spec = AppSpec(**result.plan["spec"])
            explanation = self.learning_coach.explain(spec, [f.name for f in result.files])
            self._append_chat("assistant", explanation)

        if result.ok:
            self._set_progress("done", "作成とテストが完了", "「アプリを確認」で実際の画面を開けます")
        else:
            self._set_progress("issue", "確認が必要です", "「テスト結果」を開くと原因を確認できます")
        self._set_busy(False)
        self.instruction.focus_force()

    def _handle_build_error(self, exc: Exception):
        message = f"処理中にエラーが起きました。\n{type(exc).__name__}: {exc}"
        self._append_chat("assistant", message)
        self.write("⚠ " + message.replace("\n", " / "))
        self._set_progress("issue", "エラーが発生しました", "「テスト結果」を開くと詳細を確認できます")
        self._set_busy(False)
        self.instruction.focus_force()

    def vault_save(self):
        p = self._current()
        if not p:
            return
        try:
            version = self.vault.save(self.current_slug, "手動保存", actor="local-user", reason="manual save", kind="manual")
            self.write(f"✓ Code Vault保存: {version.version_id} / {version.file_count} files")
            messagebox.showinfo("Code Vault", "現在の状態を保存しました。")
        except Exception as exc:
            messagebox.showerror("Code Vault", f"保存に失敗しました。\n{exc}")

    def _vault_format_version(self, version):
        created = version.created_at.replace("T", " ")[:19]
        return f"{created}  {version.label}  [{version.kind}]"

    def _open_vault_window(self, *, restore_mode: bool = False):
        p = self._current()
        if not p:
            return
        versions = self.vault.list_versions(self.current_slug)
        if not versions:
            messagebox.showinfo("Code Vault", "まだ保存履歴がありません。")
            return

        win = tk.Toplevel(self)
        win.title("Code Vault - 履歴")
        win.transient(self)
        win.geometry("820x520")
        outer = ttk.Frame(win, padding=14)
        outer.pack(fill="both", expand=True)
        ttk.Label(outer, text=f"{p['name']} の保存履歴", font=("Segoe UI", 14, "bold")).pack(anchor="w")
        ttk.Label(outer, text="戻したい時点を選べます。復元前には現在の状態を自動保存します。", foreground="#667085").pack(anchor="w", pady=(4,10))

        listbox = tk.Listbox(outer, height=12)
        listbox.pack(fill="x")
        for version in versions:
            listbox.insert("end", self._vault_format_version(version))
        listbox.selection_set(0)

        details = tk.Text(outer, height=10, wrap="word", state="disabled")
        details.pack(fill="both", expand=True, pady=(10,8))
        self._enable_readonly_copy(details)

        def selected_version():
            sel = listbox.curselection()
            return versions[sel[0]] if sel else None

        def show_selected_details(_event=None):
            version = selected_version()
            if not version:
                return
            text = (
                f"保存日時: {version.created_at}\n"
                f"ラベル: {version.label}\n"
                f"種類: {version.kind}\n"
                f"実行者: {version.actor}\n"
                f"ファイル数: {version.file_count}\n"
                f"サイズ: {version.total_bytes} bytes\n"
                f"理由: {version.reason or '-'}\n"
            )
            if version.warnings:
                text += "注意:\n- " + "\n- ".join(version.warnings)
            details.configure(state="normal")
            details.delete("1.0", "end")
            details.insert("1.0", text)
            details.configure(state="disabled")

        def show_diff():
            version = selected_version()
            if version:
                self._show_vault_diff(version.version_id)

        def restore():
            version = selected_version()
            if not version:
                return
            if not messagebox.askyesno(
                "前の状態に戻す",
                f"{version.created_at[:19]} の状態に戻しますか？\n\n現在の状態は先に自動保存されます。",
                parent=win,
            ):
                return
            try:
                safety = self.vault.restore(self.current_slug, version.version_id, confirmed=True, actor="local-user")
                self.refresh_projects()
                self.write(f"✓ Code Vault復元: {version.version_id} / 復元前保存={safety.version_id}")
                messagebox.showinfo("Code Vault", "復元しました。現在の状態も復元前に保存済みです。", parent=win)
                win.destroy()
            except Exception as exc:
                messagebox.showerror("Code Vault", f"復元に失敗しました。\n{exc}", parent=win)

        listbox.bind("<<ListboxSelect>>", show_selected_details)
        actions = ttk.Frame(outer)
        actions.pack(fill="x")
        ttk.Button(actions, text="この時点との差分", command=show_diff).pack(side="left")
        ttk.Button(actions, text="この状態に戻す", command=restore).pack(side="left", padx=8)
        ttk.Button(actions, text="閉じる", command=win.destroy).pack(side="right")
        show_selected_details()
        if restore_mode:
            listbox.focus_force()

    def vault_history(self):
        self._open_vault_window(restore_mode=False)

    def vault_restore_picker(self):
        self._open_vault_window(restore_mode=True)

    def vault_show_latest_diff(self):
        p = self._current()
        if not p:
            return
        versions = self.vault.list_versions(self.current_slug)
        if not versions:
            messagebox.showinfo("Code Vault", "まだ保存履歴がありません。")
            return
        self._show_vault_diff(versions[0].version_id)

    def _show_vault_diff(self, version_id: str):
        try:
            diff = self.vault.diff(self.current_slug, version_id)
        except Exception as exc:
            messagebox.showerror("変更を見る", f"差分確認に失敗しました。\n{exc}")
            return
        summary = [
            f"追加: {len(diff.added)}",
            f"削除: {len(diff.removed)}",
            f"変更: {len(diff.modified)}",
            f"変更なし: {diff.unchanged}",
            "",
        ]
        if diff.added:
            summary.append("追加ファイル:\n  " + "\n  ".join(diff.added[:40]))
        if diff.removed:
            summary.append("削除ファイル:\n  " + "\n  ".join(diff.removed[:40]))
        if diff.modified:
            summary.append("変更ファイル:\n  " + "\n  ".join(diff.modified[:40]))
        if diff.unified_diff:
            summary.append("\n--- テキスト差分 ---\n" + diff.unified_diff[:30000])
        elif not (diff.added or diff.removed or diff.modified):
            summary.append("現在の状態と同じです。")

        win = tk.Toplevel(self)
        win.title("Code Vault - 変更を見る")
        win.geometry("920x620")
        text = tk.Text(win, wrap="none")
        text.pack(fill="both", expand=True, padx=12, pady=12)
        text.insert("1.0", "\n".join(summary))
        text.configure(state="disabled")
        self._enable_readonly_copy(text)

    def run_maintenance(self):
        p = self._current()
        if not p: return
        path = WORKSPACE_DIR / self.current_slug
        findings = self.maintenance.inspect_project(path)
        self.maintenance.record(self.current_slug, findings)
        self.write("--- 保守スキャン ---")
        for f in findings: self.write(f"[{f.severity}] {f.code}: {f.message}")

    def show_release_risk(self):
        if not self.current_slug: return
        path = WORKSPACE_DIR / self.current_slug / "release_risk.json"
        if not path.exists():
            messagebox.showinfo("公開前リスク", "制作パイプライン実行後にチェックリストが生成されます。")
            return
        raw = json.loads(path.read_text(encoding="utf-8"))
        lines = ["※自動チェックであり法的保証ではありません。", ""]
        for item in raw.get("items", []):
            lines.append(f"[{item['severity']}] {item['message']}")
        messagebox.showinfo("公開前リスク確認", "\n".join(lines[:18]))

    def make_backup(self):
        r = self.backup.create("ui")
        if r.ok:
            self.write(f"✓ バックアップ作成: {r.path}")
            messagebox.showinfo("バックアップ", f"作成しました。\n{r.path}")
        else:
            messagebox.showerror("バックアップ", r.error or "作成に失敗しました。")

    def preview(self):
        if not self.current_slug: return
        project = WORKSPACE_DIR / self.current_slug
        index = project / "index.html"
        if not index.exists():
            messagebox.showinfo("プレビュー", "まだアプリがありません。先にAIへ作りたい内容を送ってください。")
            return
        try:
            if (project / "server.py").exists():
                session = self.preview_runtime.start(project)
                webbrowser.open(session.url)
                self.write(f"✓ 実アプリプレビュー: {session.url}")
            else:
                webbrowser.open(index.resolve().as_uri())
                self.write("✓ Webプレビューを開きました")
        except Exception as exc:
            messagebox.showerror("プレビュー", f"プレビューを開始できませんでした。\n{exc}")

    def show_path(self):
        if self.current_slug: self.write(f"保存先: {WORKSPACE_DIR / self.current_slug}")

    def show_diagnostics(self):
        d = diagnose()
        messagebox.showinfo("環境診断", "\n".join(f"{k}: {v}" for k,v in d.items()))

    def show_readiness(self):
        r = self.readiness.run()
        lines = [f"ローカルMVP準備: {'OK' if r.ready_for_local_mvp else '要確認'}", ""]
        for c in r.checks:
            lines.append(f"[{c.status}] {c.key}: {c.detail}")
        lines.append(f"\n診断ログ保存先: {LOG_DIR}")
        messagebox.showinfo("準備状況", "\n".join(lines))
