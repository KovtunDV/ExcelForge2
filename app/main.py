from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from app.ui_qt.app_icon import application_icon
from app.ui_qt.app_window import AppWindow
from app.steps import register_all_steps

_APP_STYLE = """
QTabWidget::pane { border: 1px solid #c0c0c0; }
QGroupBox { font-weight: bold; margin-top: 8px; padding-top: 8px; }
QGroupBox::title { subcontrol-origin: margin; left: 8px; padding: 0 4px; }
QSplitter::handle { width: 4px; background: #e0e0e0; }
"""


def main() -> None:
    register_all_steps()

    app = QApplication(sys.argv)
    icon = application_icon()
    if not icon.isNull():
        app.setWindowIcon(icon)
    app.setStyleSheet(_APP_STYLE)

    window = AppWindow()
    if not icon.isNull():
        window.setWindowIcon(icon)
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
