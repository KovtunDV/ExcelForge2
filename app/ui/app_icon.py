from __future__ import annotations

import sys
import tkinter as tk
from pathlib import Path

# Keep PhotoImage alive for the lifetime of the process.
_icon_photo: tk.PhotoImage | None = None
_ico_default_set: bool = False


def _app_dir() -> Path:
    # app/ui/app_icon.py -> app/
    return Path(__file__).resolve().parent.parent


def _try_ico_windows(root: tk.Misc, p: Path) -> bool:
    global _ico_default_set
    if sys.platform != "win32":
        return False
    try:
        root.iconbitmap(default=str(p))
        _ico_default_set = True
        return True
    except Exception:
        try:
            root.iconbitmap(str(p))
            return True
        except Exception:
            return False


def _try_ico_any(root: tk.Misc, p: Path) -> bool:
    try:
        root.iconbitmap(str(p))
        return True
    except Exception:
        return False


def _load_png_photo(path: Path) -> tk.PhotoImage | None:
    global _icon_photo
    if _icon_photo is not None:
        return _icon_photo
    try:
        _icon_photo = tk.PhotoImage(file=str(path))
        return _icon_photo
    except Exception:
        return None


def apply_app_icon(root: tk.Misc) -> None:
    """
    Set window/taskbar icon for the main window.

    Looks under app/ for:
      - 1-var.ico, 1 var.ico
      - 1 var.png, 1-var.png

    On Windows, prefers .ico and uses iconbitmap(default=...) so new Toplevels get the same icon.
    """
    base = _app_dir()
    ico_paths = [base / "1-var.ico", base / "1 var.ico"]
    png_paths = [base / "1 var.png", base / "1-var.png"]

    if sys.platform == "win32":
        for p in ico_paths:
            if p.is_file() and _try_ico_windows(root, p):
                return

    for p in ico_paths:
        if p.is_file() and _try_ico_any(root, p):
            return

    for p in png_paths:
        if not p.is_file():
            continue
        img = _load_png_photo(p)
        if img is None:
            continue
        try:
            root.iconphoto(True, img)
            setattr(root, "_excelforge_app_icon", img)
            return
        except Exception:
            continue


def apply_app_icon_to_window(w: tk.Misc) -> None:
    """Apply the same icon to a Toplevel (or any Tk window) if assets are available."""
    if sys.platform == "win32" and _ico_default_set:
        return

    base = _app_dir()
    ico_paths = [base / "1-var.ico", base / "1 var.ico"]
    png_paths = [base / "1 var.png", base / "1-var.png"]

    for p in ico_paths:
        if p.is_file() and _try_ico_any(w, p):
            return

    for p in png_paths:
        if not p.is_file():
            continue
        img = _load_png_photo(p)
        if img is None:
            continue
        try:
            w.iconphoto(True, img)
            return
        except Exception:
            continue
