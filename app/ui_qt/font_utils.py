from __future__ import annotations

from PySide6.QtGui import QFont, QFontDatabase
from PySide6.QtWidgets import QApplication


def list_font_families() -> list[str]:
    """Список семейств шрифтов, доступных в системе (Qt 6)."""
    if QApplication.instance() is None:
        families: list[str] = []
    else:
        db = QFontDatabase()
        families = list(db.families())
    return sorted({str(f) for f in families if f}, key=str.lower)


def make_app_font(family: str, size: int) -> QFont:
    family = str(family or "").strip()
    size = max(6, min(int(size), 48))
    font = QFont()
    if family:
        font.setFamily(family)
    font.setPointSize(size)
    return font


def apply_font_to_application(family: str, size: int) -> QFont:
    """Применить шрифт ко всему приложению, включая уже созданные виджеты."""
    app = QApplication.instance()
    if app is None:
        return make_app_font(family, size)

    font = make_app_font(family, size)
    app.setFont(font)
    for widget in app.allWidgets():
        try:
            widget.setFont(font)
        except Exception:
            pass
    return font
