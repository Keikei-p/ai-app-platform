from __future__ import annotations

import tkinter as tk
from tkinter import ttk, messagebox
import webbrowser

from ..core.remote_server import RemoteServerController


class RemoteWindow(tk.Toplevel):
    def __init__(self, master, controller: RemoteServerController):
        super().__init__(master)
        self.controller = controller
        self.title("自作リモート / LAN Remote Beta")
        self.geometry("720x600")
        self.minsize(640, 520)
        self.transient(master)
        self._build()
        self.refresh()

    def _build(self):
        outer = ttk.Frame(self, padding=16)
        outer.pack(fill="both", expand=True)
        ttk.Label(outer, text="自作リモート", font=("Segoe UI", 18, "bold")).pack(anchor="w")
        ttk.Label(
            outer,
            text="同じ信頼できるWi‑Fi/LAN内で使うBetaです。ルーターのポート開放やインターネット公開はしません。",
            foreground="#667085",
            wraplength=660,
        ).pack(anchor="w", pady=(4, 12))

        server = ttk.LabelFrame(outer, text="PC側 Remote Worker", padding=12)
        server.pack(fill="x")
        self.status_label = ttk.Label(server, text="停止中")
        self.status_label.pack(anchor="w")
        self.url_var = tk.StringVar(value="-")
        ttk.Entry(server, textvariable=self.url_var, state="readonly").pack(fill="x", pady=(8, 6))
        row = ttk.Frame(server); row.pack(fill="x")
        ttk.Button(row, text="同じWi‑Fi向けに開始", command=self.start_lan).pack(side="left")
        ttk.Button(row, text="停止", command=self.stop_server).pack(side="left", padx=6)
        ttk.Button(row, text="スマホ画面をこのPCで開く", command=self.open_local).pack(side="left")

        pair = ttk.LabelFrame(outer, text="スマホをペアリング", padding=12)
        pair.pack(fill="x", pady=12)
        self.pair_var = tk.StringVar(value="-")
        ttk.Entry(pair, textvariable=self.pair_var, state="readonly", font=("Consolas", 15, "bold")).pack(fill="x")
        prow = ttk.Frame(pair); prow.pack(fill="x", pady=(8, 0))
        ttk.Button(prow, text="新しいペアリングコード", command=self.new_pairing).pack(side="left")
        ttk.Button(prow, text="URLをコピー", command=self.copy_url).pack(side="left", padx=6)
        ttk.Label(pair, text="スマホで上のURLを開き、この10文字コードを入力します。コードは1回限り・5分で失効します。", foreground="#667085", wraplength=650).pack(anchor="w", pady=(8,0))

        devices = ttk.LabelFrame(outer, text="接続済み端末", padding=12)
        devices.pack(fill="both", expand=True)
        self.device_list = tk.Listbox(devices, height=8)
        self.device_list.pack(fill="both", expand=True)
        drow = ttk.Frame(devices); drow.pack(fill="x", pady=(8,0))
        ttk.Button(drow, text="選択端末を失効", command=self.revoke_selected).pack(side="left")
        ttk.Button(drow, text="一覧更新", command=self.refresh).pack(side="left", padx=6)
        ttk.Button(drow, text="緊急停止＋全端末失効", command=self.emergency_stop).pack(side="right")

        ttk.Label(
            outer,
            text="Remote Betaで可能: 状態確認 / プロジェクト一覧・作成 / 制作AI / テスト / バックアップ / Code Vault保存。\n禁止: 任意Shell、削除、本番公開、課金、認証情報操作。",
            foreground="#667085",
            wraplength=660,
        ).pack(anchor="w", pady=(10,0))

    def start_lan(self):
        if not messagebox.askyesno(
            "LAN Remoteを開始",
            "同じWi‑Fi/LAN上の端末からこのPCへ接続できるようにします。\n\n信頼できる自宅/社内Wi‑Fiでのみ使用してください。\nインターネット向けのポート開放はしないでください。\n\n開始しますか？",
            parent=self,
        ):
            return
        try:
            url = self.controller.start(lan=True)
            self.url_var.set(url)
            self.new_pairing()
            self.refresh()
        except Exception as exc:
            messagebox.showerror("リモート", f"開始できませんでした。\n{exc}", parent=self)

    def stop_server(self):
        self.controller.stop()
        self.pair_var.set("-")
        self.refresh()

    def new_pairing(self):
        if not self.controller.running:
            messagebox.showinfo("リモート", "先にLAN Remoteを開始してください。", parent=self)
            return
        try:
            ticket = self.controller.create_pairing()
            self.pair_var.set(ticket.code)
        except Exception as exc:
            messagebox.showerror("リモート", str(exc), parent=self)

    def open_local(self):
        if not self.controller.running:
            return
        webbrowser.open(f"http://127.0.0.1:{self.controller.port}/")

    def copy_url(self):
        url = self.controller.url
        if not url:
            return
        try:
            self.clipboard_clear(); self.clipboard_append(url); self.update_idletasks()
        except tk.TclError:
            pass

    def refresh(self):
        running = self.controller.running
        self.status_label.configure(text=("稼働中" if running else "停止中"))
        self.url_var.set(self.controller.url if running else "-")
        self.devices = self.controller.devices.list_devices()
        self.device_list.delete(0, "end")
        for d in self.devices:
            self.device_list.insert("end", f"{d.name}  /  {d.device_id[:8]}…  /  last: {d.last_seen_at or '-'}")

    def revoke_selected(self):
        sel = self.device_list.curselection()
        if not sel:
            return
        device = self.devices[sel[0]]
        if messagebox.askyesno("端末を失効", f"{device.name} の接続権限を失効しますか？", parent=self):
            self.controller.devices.revoke(device.device_id)
            self.refresh()

    def emergency_stop(self):
        if not messagebox.askyesno("緊急停止", "Remote Workerを停止し、接続済み端末をすべて失効します。実行しますか？", parent=self):
            return
        self.controller.devices.revoke_all()
        self.controller.stop(emergency=True)
        self.pair_var.set("-")
        self.refresh()
