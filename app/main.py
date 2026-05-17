from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from app.ui.app_window import AppWindow
from app.ui.app_icon import apply_app_icon
from app.steps import register_all_steps


def main() -> None:
    register_all_steps()

    root = tk.Tk()
    root.title("ExcelForge")
    root.geometry("1200x750")
    root.minsize(1000, 650)
    apply_app_icon(root)

    style = ttk.Style(root)
    if "clam" in style.theme_names():
        style.theme_use("clam")

    AppWindow(root).pack(fill="both", expand=True)
    root.mainloop()


if __name__ == "__main__":
    main()

