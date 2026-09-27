from __future__ import annotations

import json
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from pathlib import Path
from typing import Callable

from ..core.workspace_catalog import ConversationStore, ProjectCatalog, ConversationThread, ArtifactRecord, DeliveryOption


def _short_time(value: str) -> str:
    return value.replace("T", " ")[:16] if value else "-"


def _human_size(size: int) -> str:
    value = float(max(0, size))
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024 or unit == "GB":
            return f"{value:.0f} {unit}" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} GB"


class WorkspaceCenter(tk.Toplevel):
    """Unified conversation/project/download library for non-technical users."""

    def __init__(
        self,
        parent,
        conversations: ConversationStore,
        catalog: ProjectCatalog,
        *,
        on_open_thread: Callable[[str], None],
        on_open_project: Callable[[str], None],
        on_preview_project: Callable[[str], None],
        on_restore_project: Callable[[str], None],
        initial_tab: str = "conversations",
    ):
        super().__init__(parent)
        self.parent = parent
        self.conversations = conversations
        self.catalog = catalog
        self.on_open_thread = on_open_thread
        self.on_open_project = on_open_project
        self.on_preview_project = on_preview_project
        self.on_restore_project = on_restore_project
        self.title("AI App Platform — ライブラリ")
        self.geometry("1060x700")
        self.minsize(760, 520)
        self.configure(bg="#F7F7F8")
        self.transient(parent)

        self._thread_rows: list[ConversationThread] = []
        self._project_rows = []
        self._artifact_rows: list[DeliveryOption] = []

        outer = tk.Frame(self, bg="#F7F7F8")
        outer.pack(fill="both", expand=True, padx=22, pady=20)

        hero = tk.Frame(outer, bg="#F7F7F8")
        hero.pack(fill="x", pady=(0, 14))
        tk.Label(
            hero, text="ライブラリ", bg="#F7F7F8", fg="#111827",
            font=(getattr(parent, "ui_font_semibold", "Segoe UI"), 20, "bold"),
        ).pack(anchor="w")
        tk.Label(
            hero,
            text="会話・作ったアプリ・ダウンロードを、ここから迷わず開けます。",
            bg="#F7F7F8", fg="#6B7280",
            font=(getattr(parent, "ui_font_family", "Segoe UI"), 9),
        ).pack(anchor="w", pady=(4, 0))

        style = ttk.Style(self)
        style.configure("Center.Treeview", rowheight=36, borderwidth=0, font=(getattr(parent, "ui_font_family", "Segoe UI"), 9))
        style.configure("Center.Treeview.Heading", font=(getattr(parent, "ui_font_semibold", "Segoe UI"), 9, "bold"))
        style.configure("Center.TNotebook", background="#F7F7F8", borderwidth=0)
        style.configure("Center.TNotebook.Tab", padding=(14, 9))

        self.tabs = ttk.Notebook(outer, style="Center.TNotebook")
        self.tabs.pack(fill="both", expand=True)
        self.chat_tab = tk.Frame(self.tabs, bg="#FFFFFF")
        self.project_tab = tk.Frame(self.tabs, bg="#FFFFFF")
        self.download_tab = tk.Frame(self.tabs, bg="#FFFFFF")
        self.tabs.add(self.chat_tab, text="会話")
        self.tabs.add(self.project_tab, text="作成したアプリ")
        self.tabs.add(self.download_tab, text="ダウンロード")

        self._build_chat_tab()
        self._build_project_tab()
        self._build_download_tab()
        self.refresh_all()

        mapping = {"conversations": 0, "projects": 1, "downloads": 2}
        self.tabs.select(mapping.get(initial_tab, 0))

    def _build_chat_tab(self):
        top = tk.Frame(self.chat_tab, bg="#FFFFFF")
        top.pack(fill="x", padx=16, pady=16)
        self.search_var = tk.StringVar()
        entry = ttk.Entry(top, textvariable=self.search_var)
        entry.pack(side="left", fill="x", expand=True)
        entry.bind("<Return>", lambda _e: self.refresh_chats())
        ttk.Button(top, text="検索", command=self.refresh_chats).pack(side="left", padx=(8, 0))

        self.chat_tree = ttk.Treeview(
            self.chat_tab,
            columns=("pin", "title", "project", "updated"),
            show="headings",
            style="Center.Treeview",
            selectmode="browse",
        )
        self.chat_tree.heading("pin", text="")
        self.chat_tree.heading("title", text="会話")
        self.chat_tree.heading("project", text="アプリ")
        self.chat_tree.heading("updated", text="最終更新")
        self.chat_tree.column("pin", width=46, anchor="center", stretch=False)
        self.chat_tree.column("title", width=430)
        self.chat_tree.column("project", width=180)
        self.chat_tree.column("updated", width=150, stretch=False)
        self.chat_tree.pack(fill="both", expand=True, padx=16)
        self.chat_tree.bind("<Double-1>", lambda _e: self.open_selected_chat())

        bar = tk.Frame(self.chat_tab, bg="#FFFFFF")
        bar.pack(fill="x", padx=16, pady=14)
        ttk.Button(bar, text="開く", command=self.open_selected_chat).pack(side="left")
        ttk.Button(bar, text="名前を変更", command=self.rename_selected_chat).pack(side="left", padx=6)
        ttk.Button(bar, text="ピン留め切替", command=self.pin_selected_chat).pack(side="left", padx=6)
        ttk.Button(bar, text="履歴から削除", command=self.archive_selected_chat).pack(side="right")

    def _build_project_tab(self):
        self.project_tree = ttk.Treeview(
            self.project_tab,
            columns=("name", "status", "targets", "quality", "updated"),
            show="headings",
            style="Center.Treeview",
            selectmode="browse",
        )
        for key, label in (
            ("name", "アプリ"),
            ("status", "状態"),
            ("targets", "対応"),
            ("quality", "品質"),
            ("updated", "最終更新"),
        ):
            self.project_tree.heading(key, text=label)
        self.project_tree.column("name", width=320)
        self.project_tree.column("status", width=130, stretch=False)
        self.project_tree.column("targets", width=190)
        self.project_tree.column("quality", width=90, anchor="center", stretch=False)
        self.project_tree.column("updated", width=150, stretch=False)
        self.project_tree.pack(fill="both", expand=True, padx=16, pady=(16, 0))
        self.project_tree.bind("<Double-1>", lambda _e: self.show_project_detail())

        bar = tk.Frame(self.project_tab, bg="#FFFFFF")
        bar.pack(fill="x", padx=16, pady=14)
        ttk.Button(bar, text="チャットで開く", command=self.open_selected_project).pack(side="left")
        ttk.Button(bar, text="アプリ詳細", command=self.show_project_detail).pack(side="left", padx=6)
        ttk.Button(bar, text="プレビュー", command=self.preview_selected_project).pack(side="left", padx=6)
        ttk.Button(bar, text="更新", command=self.refresh_projects).pack(side="right")

    def _build_download_tab(self):
        tip = tk.Label(
            self.download_tab,
            text="実際に生成されたファイルだけを表示します。存在しないEXE/APK/IPAをダウンロード可能とは表示しません。",
            bg="#FFFFFF", fg="#6B7280", anchor="w", justify="left",
            font=(getattr(self.parent, "ui_font_family", "Segoe UI"), 9),
        )
        tip.pack(fill="x", padx=16, pady=(16, 8))

        self.download_tree = ttk.Treeview(
            self.download_tab,
            columns=("project", "target", "label", "status", "size"),
            show="headings",
            style="Center.Treeview",
            selectmode="browse",
        )
        for key, label in (
            ("project", "アプリ"),
            ("target", "形式"),
            ("label", "形式"),
            ("status", "状態"),
            ("size", "サイズ"),
        ):
            self.download_tree.heading(key, text=label)
        self.download_tree.column("project", width=300)
        self.download_tree.column("target", width=130, stretch=False)
        self.download_tree.column("label", width=190)
        self.download_tree.column("status", width=140, anchor="center", stretch=False)
        self.download_tree.column("size", width=100, anchor="e", stretch=False)
        self.download_tree.pack(fill="both", expand=True, padx=16)
        self.download_tree.bind("<Double-1>", lambda _e: self.save_selected_artifact())

        self.download_hint = tk.StringVar(value="ファイルを選ぶと使い方を表示します。")
        tk.Label(
            self.download_tab, textvariable=self.download_hint, bg="#FFFFFF", fg="#6B7280",
            anchor="w", justify="left", wraplength=870,
            font=(getattr(self.parent, "ui_font_family", "Segoe UI"), 9),
        ).pack(fill="x", padx=16, pady=(10, 4))
        self.download_tree.bind("<<TreeviewSelect>>", lambda _e: self._update_download_hint())

        bar = tk.Frame(self.download_tab, bg="#FFFFFF")
        bar.pack(fill="x", padx=16, pady=14)
        ttk.Button(bar, text="名前を付けて保存", command=self.save_selected_artifact).pack(side="left")
        ttk.Button(bar, text="更新", command=self.refresh_downloads).pack(side="right")

    def refresh_all(self):
        self.refresh_chats()
        self.refresh_projects()
        self.refresh_downloads()

    def refresh_chats(self):
        self._thread_rows = self.conversations.list_threads(self.search_var.get())
        self.chat_tree.delete(*self.chat_tree.get_children())
        for i, row in enumerate(self._thread_rows):
            self.chat_tree.insert(
                "", "end", iid=str(i),
                values=("★" if row.pinned else "", row.title, row.project_slug or "会話のみ", _short_time(row.updated_at)),
            )

    def refresh_projects(self):
        self._project_rows = self.catalog.list_cards()
        self.project_tree.delete(*self.project_tree.get_children())
        for i, row in enumerate(self._project_rows):
            self.project_tree.insert(
                "", "end", iid=str(i),
                values=(row.name, row.status, " / ".join(row.targets), row.quality, _short_time(row.updated_at)),
            )

    def refresh_downloads(self):
        name_by_slug = {x.slug: x.name for x in self.catalog.list_cards()}
        self._artifact_rows = self.catalog.all_delivery_options()
        self.download_tree.delete(*self.download_tree.get_children())
        for i, row in enumerate(self._artifact_rows):
            self.download_tree.insert(
                "", "end", iid=str(i),
                values=(
                    name_by_slug.get(row.project_slug, row.project_slug),
                    row.target,
                    row.label,
                    row.status,
                    _human_size(row.size_bytes) if row.available else "—",
                ),
                tags=("available" if row.available else "pending",),
            )
        self.download_tree.tag_configure("pending", foreground="#8A8F98")
        if not self._artifact_rows:
            self.download_hint.set("まだ配布対象のアプリはありません。アプリを生成すると、ここに準備状況が表示されます。")

    @staticmethod
    def _selected(tree, rows):
        selection = tree.selection()
        if not selection:
            return None
        try:
            return rows[int(selection[0])]
        except (ValueError, IndexError):
            return None

    def open_selected_chat(self):
        row = self._selected(self.chat_tree, self._thread_rows)
        if not row:
            return
        self.on_open_thread(row.thread_id)
        self.destroy()

    def rename_selected_chat(self):
        row = self._selected(self.chat_tree, self._thread_rows)
        if not row:
            return
        win = tk.Toplevel(self)
        win.title("会話名を変更")
        win.transient(self)
        win.grab_set()
        body = tk.Frame(win, bg="#FFFFFF")
        body.pack(fill="both", expand=True, padx=18, pady=18)
        value = tk.StringVar(value=row.title)
        entry = ttk.Entry(body, textvariable=value, width=48)
        entry.pack(fill="x")
        entry.select_range(0, "end")
        entry.focus_force()

        def save():
            try:
                self.conversations.rename(row.thread_id, value.get())
            except Exception as exc:
                messagebox.showerror("会話名", str(exc), parent=win)
                return
            win.destroy()
            self.refresh_chats()

        ttk.Button(body, text="保存", command=save).pack(anchor="e", pady=(12, 0))
        entry.bind("<Return>", lambda _e: save())

    def pin_selected_chat(self):
        row = self._selected(self.chat_tree, self._thread_rows)
        if not row:
            return
        self.conversations.set_pinned(row.thread_id, not row.pinned)
        self.refresh_chats()

    def archive_selected_chat(self):
        row = self._selected(self.chat_tree, self._thread_rows)
        if not row:
            return
        extra = "\n\nアプリ本体やCode Vaultの履歴は削除しません。" if row.project_slug else ""
        if not messagebox.askyesno("履歴から削除", "この会話を最近の履歴から削除しますか？" + extra, parent=self):
            return
        self.conversations.archive(row.thread_id)
        self.refresh_chats()

    def open_selected_project(self):
        row = self._selected(self.project_tree, self._project_rows)
        if not row:
            return
        self.on_open_project(row.slug)
        self.destroy()

    def preview_selected_project(self):
        row = self._selected(self.project_tree, self._project_rows)
        if not row:
            return
        self.on_preview_project(row.slug)

    def show_project_detail(self):
        row = self._selected(self.project_tree, self._project_rows)
        if not row:
            return
        ProjectDetailWindow(
            self,
            self.catalog,
            row.slug,
            on_open_project=self.on_open_project,
            on_preview_project=self.on_preview_project,
            on_restore_project=self.on_restore_project,
        )

    def _update_download_hint(self):
        row = self._selected(self.download_tree, self._artifact_rows)
        if row:
            self.download_hint.set(row.guide)

    def save_selected_artifact(self):
        row = self._selected(self.download_tree, self._artifact_rows)
        if not row:
            return
        if not row.available or not row.artifact_id:
            messagebox.showinfo("ダウンロード", "この形式はまだダウンロードできません。\n\n" + row.guide, parent=self)
            return
        source_record = next(
            (x for x in self.catalog.artifacts(row.project_slug) if x.artifact_id == row.artifact_id),
            None,
        )
        if source_record is None:
            messagebox.showerror("ダウンロード", "実際の成果物ファイルを確認できませんでした。", parent=self)
            return
        source = Path(source_record.path)
        destination = filedialog.asksaveasfilename(
            parent=self,
            title=f"{row.label}を保存",
            initialfile=source.name,
            defaultextension=source.suffix,
        )
        if not destination:
            return
        try:
            saved = self.catalog.export_artifact(row.project_slug, row.artifact_id, Path(destination))
        except Exception as exc:
            messagebox.showerror("ダウンロード", f"保存できませんでした。\n{exc}", parent=self)
            return
        messagebox.showinfo("ダウンロード", f"保存しました。\n{saved}\n\n{row.guide}", parent=self)


class ProjectDetailWindow(tk.Toplevel):
    def __init__(self, parent, catalog: ProjectCatalog, slug: str, *, on_open_project, on_preview_project, on_restore_project):
        super().__init__(parent)
        self.catalog = catalog
        self.slug = slug
        self.on_open_project = on_open_project
        self.on_preview_project = on_preview_project
        self.on_restore_project = on_restore_project
        self.data = catalog.detail(slug)
        card = self.data["card"]
        self.title(str(card["name"]) + " — アプリ詳細")
        self.geometry("940x650")
        self.minsize(700, 500)
        self.configure(bg="#F7F7F8")

        top = tk.Frame(self, bg="#F7F7F8")
        top.pack(fill="x", padx=20, pady=(18, 10))
        tk.Label(
            top, text=str(card["name"]), bg="#F7F7F8", fg="#111827",
            font=(getattr(parent.parent if hasattr(parent, "parent") else parent, "ui_font_semibold", "Segoe UI"), 18, "bold")
        ).pack(side="left")
        badge = tk.Label(
            top, text=f"  {card['status']}  ", bg="#ECFDF3" if card["quality"] == "PASS" else "#FFF7ED",
            fg="#067647" if card["quality"] == "PASS" else "#B54708",
            font=("Segoe UI", 9, "bold"), padx=8, pady=5,
        )
        badge.pack(side="left", padx=10)
        ttk.Button(top, text="チャットで開く", command=self._open).pack(side="right")
        ttk.Button(top, text="プレビュー", command=lambda: self.on_preview_project(self.slug)).pack(side="right", padx=6)

        tabs = ttk.Notebook(self)
        tabs.pack(fill="both", expand=True, padx=20, pady=(0, 20))
        overview = tk.Frame(tabs, bg="#FFFFFF")
        quality = tk.Frame(tabs, bg="#FFFFFF")
        history = tk.Frame(tabs, bg="#FFFFFF")
        downloads = tk.Frame(tabs, bg="#FFFFFF")
        tabs.add(overview, text="概要")
        tabs.add(quality, text="品質・ビルド")
        tabs.add(history, text="履歴")
        tabs.add(downloads, text="ダウンロード")

        spec = self.data.get("spec") or {}
        self._text_panel(
            overview,
            "いまの状態",
            (
                f"種類: {card['app_type']}\n"
                f"対応: {' / '.join(card['targets'])}\n"
                f"状態: {card['status']}\n"
                f"品質チェック: {card['quality']}\n"
                f"保存バージョン: {card['version_count']}\n"
                f"ダウンロード可能: {card['artifact_count']}件\n\n"
                f"目的: {spec.get('summary') or 'まだ生成前です。'}\n"
                f"利用イメージ: {spec.get('usage_context') or '-'}"
            ),
        )

        test_data = self.data.get("tests") or {}
        sec_data = self.data.get("security") or {}
        ready = self.data.get("readiness") or {}
        approval = self.data.get("approval") or {}
        failed = [x for x in test_data.get("results", []) if not x.get("passed")]
        findings = [x for x in sec_data.get("findings", []) if x.get("blocking")]
        quality_text = (
            f"自動テスト: {'PASS' if test_data.get('passed') else ('FAIL' if test_data else '未実行')}\n"
            f"セキュリティ: {'PASS' if sec_data.get('passed') else ('FAIL' if sec_data else '未実行')}\n"
            f"プレビュー可能: {'はい' if ready.get('preview_ready') else 'いいえ'}\n"
            f"公開準備: {'準備済み（公開は要承認）' if ready.get('release_ready') else '未完了項目あり'}\n"
            f"公開承認: {approval.get('production_release') or '未設定'}\n"
        )
        if failed:
            quality_text += "\n失敗テスト:\n" + "\n".join(
                f"・{x.get('name')}: {x.get('detail')}" for x in failed[:10]
            )
        if findings:
            quality_text += "\n安全上の確認事項:\n" + "\n".join(
                f"・{x.get('key')}: {x.get('detail')}" for x in findings[:10]
            )
        gaps = (self.data.get("gaps") or {}).get("items") or []
        if gaps:
            quality_text += "\n\nまだ準備が必要なもの:\n" + "\n".join(
                f"・{x.get('reason','')}\n  次: {x.get('next_step','')}" for x in gaps[:10]
            )
        self._text_panel(quality, "品質チェック", quality_text)

        versions = self.data.get("versions") or []
        audit = self.data.get("audit") or []
        history_text = "保存履歴\n" + (
            "\n".join(f"・{_short_time(x.get('created_at',''))}  {x.get('label','保存')} [{x.get('kind','')}]"
                      for x in versions[:20])
            if versions else "・まだ保存履歴はありません。"
        )
        history_text += "\n\n作業履歴\n" + (
            "\n".join(f"・{_short_time(x.get('created_at',''))}  {x.get('event_type','')}"
                      for x in audit[:30])
            if audit else "・まだ作業履歴はありません。"
        )
        self._text_panel(history, "変更とバージョン", history_text)
        restore_bar = tk.Frame(history, bg="#FFFFFF")
        restore_bar.pack(fill="x", padx=18, pady=(0, 16))
        tk.Label(
            restore_bar,
            text="以前の状態へ戻す場合も、現在の状態を自動保存してから復元します。",
            bg="#FFFFFF", fg="#6B7280", font=("Segoe UI", 8)
        ).pack(side="left")
        ttk.Button(
            restore_bar, text="履歴から復元", command=lambda: self.on_restore_project(self.slug)
        ).pack(side="right")

        artifact_rows = self.catalog.artifacts(slug)
        if not artifact_rows:
            self._text_panel(downloads, "ダウンロード", "まだ実在するビルド成果物はありません。\nテストとビルドが完了すると、ここに表示されます。")
        else:
            wrap = tk.Frame(downloads, bg="#FFFFFF")
            wrap.pack(fill="both", expand=True, padx=18, pady=18)
            for artifact in artifact_rows:
                card_frame = tk.Frame(wrap, bg="#F9FAFB", highlightbackground="#E5E7EB", highlightthickness=1)
                card_frame.pack(fill="x", pady=5)
                left = tk.Frame(card_frame, bg="#F9FAFB")
                left.pack(side="left", fill="x", expand=True, padx=12, pady=10)
                tk.Label(left, text=f"{artifact.label}  ·  {_human_size(artifact.size_bytes)}",
                         bg="#F9FAFB", fg="#111827", font=("Segoe UI", 10, "bold")).pack(anchor="w")
                tk.Label(left, text=artifact.guide, bg="#F9FAFB", fg="#6B7280",
                         font=("Segoe UI", 8), wraplength=560, justify="left").pack(anchor="w", pady=(3, 0))
                ttk.Button(card_frame, text="保存", command=lambda a=artifact: self._save(a)).pack(side="right", padx=12)

    def _open(self):
        self.on_open_project(self.slug)
        self.destroy()

    @staticmethod
    def _text_panel(parent, title: str, content: str):
        tk.Label(parent, text=title, bg="#FFFFFF", fg="#111827",
                 font=("Segoe UI Semibold", 13, "bold")).pack(anchor="w", padx=18, pady=(18, 8))
        text = tk.Text(parent, wrap="word", borderwidth=0, bg="#FFFFFF", fg="#374151", padx=2, pady=2)
        text.pack(fill="both", expand=True, padx=18, pady=(0, 18))
        text.insert("1.0", content)
        text.configure(state="disabled")

    def _save(self, artifact: ArtifactRecord):
        src = Path(artifact.path)
        destination = filedialog.asksaveasfilename(
            parent=self, title=f"{artifact.label}を保存", initialfile=src.name, defaultextension=src.suffix
        )
        if not destination:
            return
        try:
            out = self.catalog.export_artifact(self.slug, artifact.artifact_id, Path(destination))
        except Exception as exc:
            messagebox.showerror("ダウンロード", str(exc), parent=self)
            return
        messagebox.showinfo("ダウンロード", f"保存しました。\n{out}", parent=self)
