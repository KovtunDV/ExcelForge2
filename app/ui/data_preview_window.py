from __future__ import annotations

import tkinter as tk
from tkinter import ttk

import pandas as pd

from app.pipeline.context import RunContext
from app.ui.app_icon import apply_app_icon_to_window


class DataPreviewWindow(tk.Toplevel):
    """Отдельное окно просмотра датафреймов после preview / single-step run."""

    def __init__(self, master: tk.Misc, title: str = "Просмотр DataFrame"):
        super().__init__(master)
        apply_app_icon_to_window(self)
        self.title(title)
        self.geometry("900x520")
        self.minsize(600, 400)

        self._ctx: RunContext | None = None

        pw = ttk.Panedwindow(self, orient="horizontal")
        pw.pack(fill="both", expand=True, padx=10, pady=10)

        left = ttk.Frame(pw)
        right = ttk.Frame(pw)
        pw.add(left, weight=1)
        pw.add(right, weight=3)

        ttk.Label(left, text="Доступные DF:").pack(anchor="w")
        self.df_list = tk.Listbox(left, height=12, exportselection=False)
        self.df_list.pack(fill="both", expand=True, pady=(6, 0))
        self.df_list.bind("<<ListboxSelect>>", lambda _e: self._render_preview())

        self.df_info = ttk.Label(right, text="Нет данных.")
        self.df_info.pack(anchor="w")

        self._preview_row_limit = 10
        self.rows_label = ttk.Label(right, text="Первые 10 строк:")
        self.rows_label.pack(anchor="w", pady=(8, 0))
        prev_frame = ttk.Frame(right)
        prev_frame.pack(fill="both", expand=True, pady=(6, 0))
        yscroll = ttk.Scrollbar(prev_frame, orient="vertical")
        xscroll = ttk.Scrollbar(prev_frame, orient="horizontal")
        self.df_preview = tk.Text(
            prev_frame,
            height=16,
            wrap="none",
            yscrollcommand=yscroll.set,
            xscrollcommand=xscroll.set,
        )
        yscroll.config(command=self.df_preview.yview)
        xscroll.config(command=self.df_preview.xview)
        self.df_preview.grid(row=0, column=0, sticky="nsew")
        yscroll.grid(row=0, column=1, sticky="ns")
        xscroll.grid(row=1, column=0, sticky="we")
        prev_frame.grid_rowconfigure(0, weight=1)
        prev_frame.grid_columnconfigure(0, weight=1)

    def set_context(self, ctx: RunContext, subtitle: str = "", *, max_rows: int = 10) -> None:
        self._ctx = ctx
        try:
            self._preview_row_limit = max(1, min(int(max_rows), 5000))
        except (TypeError, ValueError):
            self._preview_row_limit = 10
        self.rows_label.configure(text=f"Первые {self._preview_row_limit} строк:")
        if subtitle:
            self.title(f"Просмотр DataFrame — {subtitle}")

        self.df_list.delete(0, "end")
        names = sorted(ctx.df_store.keys(), key=lambda s: s.lower())
        for n in names:
            self.df_list.insert("end", n)

        if names:
            self.df_list.selection_set(0)
            self.df_list.activate(0)
            self._render_preview()
        else:
            self.df_info.configure(text="Нет доступных датафреймов.")
            self.df_preview.delete("1.0", "end")

    def _render_preview(self) -> None:
        if not self._ctx:
            return
        sel = self.df_list.curselection()
        if not sel:
            return
        name = self.df_list.get(sel[0])
        df = self._ctx.df_store.get(name)
        if df is None:
            return

        cols = [str(c) for c in df.columns]
        self.df_info.configure(
            text=f"DF: {name} | rows={len(df)} cols={len(cols)}\nColumns: {', '.join(cols)}"
        )

        head = df.head(self._preview_row_limit)
        try:
            preview = head.to_string(index=False)
        except Exception:
            preview = str(head)
        self.df_preview.delete("1.0", "end")
        self.df_preview.insert("1.0", preview)
