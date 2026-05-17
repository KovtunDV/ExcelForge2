from __future__ import annotations

import tkinter as tk
from tkinter import filedialog
from tkinter import messagebox

from app.pipeline.context import RunContext


def bind_tk_dialogs_to_context(ctx: RunContext, widget: tk.Misc) -> None:
    """Подключает стандартные Tk-диалоги к контексту выполнения (главный поток UI)."""
    root = widget.winfo_toplevel()

    def tk_askopenfilename(**kwargs: object) -> str:
        kwargs.setdefault("parent", root)
        root.update_idletasks()
        r = filedialog.askopenfilename(**kwargs)
        return r if isinstance(r, str) else ""

    def tk_askdirectory(**kwargs: object) -> str:
        kwargs.setdefault("parent", root)
        root.update_idletasks()
        r = filedialog.askdirectory(**kwargs)
        return r if isinstance(r, str) else ""

    def tk_asksaveasfilename(**kwargs: object) -> str:
        kwargs.setdefault("parent", root)
        root.update_idletasks()
        r = filedialog.asksaveasfilename(**kwargs)
        return r if isinstance(r, str) else ""

    def tk_askretrycancel(title: str, message: str) -> bool:
        root.update_idletasks()
        return bool(messagebox.askretrycancel(title, message, parent=root))

    ctx.variables["tk_askopenfilename"] = tk_askopenfilename
    ctx.variables["tk_askdirectory"] = tk_askdirectory
    ctx.variables["tk_asksaveasfilename"] = tk_asksaveasfilename
    ctx.variables["tk_askretrycancel"] = tk_askretrycancel
