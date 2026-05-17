from __future__ import annotations

import tkinter as tk
from tkinter import ttk


class LabeledEntry(ttk.Frame):
    def __init__(
        self,
        master: tk.Misc,
        label: str,
        textvariable: tk.StringVar,
        width: int = 40,
    ):
        super().__init__(master)
        ttk.Label(self, text=label).pack(side="left")
        self.entry = ttk.Entry(self, textvariable=textvariable, width=width)
        self.entry.pack(side="left", padx=(8, 0), fill="x", expand=True)


class LabeledCombobox(ttk.Frame):
    def __init__(
        self,
        master: tk.Misc,
        label: str,
        textvariable: tk.StringVar,
        values: list[str],
        width: int = 38,
        state: str = "readonly",
    ):
        super().__init__(master)
        ttk.Label(self, text=label).pack(side="left")
        self.combo = ttk.Combobox(
            self,
            textvariable=textvariable,
            values=values,
            width=width,
            state=state,
        )
        self.combo.pack(side="left", padx=(8, 0), fill="x", expand=True)


class LabeledCheckbutton(ttk.Frame):
    def __init__(self, master: tk.Misc, label: str, variable: tk.BooleanVar):
        super().__init__(master)
        self.chk = ttk.Checkbutton(self, text=label, variable=variable)
        self.chk.pack(side="left")

