from __future__ import annotations

from pathlib import Path

from PySide6.QtGui import QIcon


def _app_dir() -> Path:
    return Path(__file__).resolve().parent.parent


def application_icon() -> QIcon:
    base = _app_dir()
    candidates = [
        base / "1-var.ico",
        base / "1 var.ico",
        base / "1 var.png",
        base / "1-var.png",
    ]
    for p in candidates:
        if p.is_file():
            icon = QIcon(str(p))
            if not icon.isNull():
                return icon
    return QIcon()


def apply_window_icon(window) -> None:
    icon = application_icon()
    if not icon.isNull():
        window.setWindowIcon(icon)
