from __future__ import annotations

import os
import tkinter as tk
from tkinter import ttk

from app.settings import load_settings
from app.ui.builder_view import BuilderView
from app.ui.runner_view import RunnerView
from app.ui.settings_view import SettingsView


class AppWindow(ttk.Frame):
    def __init__(self, master: tk.Misc):
        super().__init__(master)

        self._apply_saved_font(master)

        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill="both", expand=True)

        default_pipelines_dir = os.path.join(os.getcwd(), "pipelines")
        os.makedirs(default_pipelines_dir, exist_ok=True)

        self.runner = RunnerView(self.notebook, pipelines_dir=default_pipelines_dir)
        self.builder = BuilderView(self.notebook, pipelines_dir=default_pipelines_dir)
        self.settings = SettingsView(self.notebook, apply_font=self._apply_font)

        self.notebook.add(self.runner, text="Runner (выполнение)")
        self.notebook.add(self.builder, text="Builder (конструктор)")
        self.notebook.add(self.settings, text="Общие настройки")

    def _apply_saved_font(self, root: tk.Misc) -> None:
        s = load_settings()
        fam = str(s.font_family or "").strip()
        size = int(s.font_size or 10)
        if fam:
            self._apply_font(fam, size, root=root)

    def _apply_font(self, family: str, size: int, *, root: tk.Misc | None = None) -> None:
        r = root or self.winfo_toplevel()
        size = max(6, min(int(size), 48))
        family = str(family).strip()
        if not family:
            return

        # Keep it simple/stable: apply via option database + ttk default style.
        # This does not crash UI themes and is consistent with previous behavior.
        r.option_add("*Font", (family, size))
        try:
            style = ttk.Style(r)
            style.configure(".", font=(family, size))
        except Exception:
            pass

