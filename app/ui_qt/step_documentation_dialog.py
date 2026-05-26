from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QHBoxLayout, QPushButton, QTextBrowser, QVBoxLayout

from app.docs.loader import get_section_for_step
from app.ui_qt.app_icon import apply_window_icon
from app.ui_qt.markdown_render import markdown_to_html


class StepDocumentationDialog(QDialog):
    """Немодальное окно справки по шагу — не блокирует основное окно."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        apply_window_icon(self)
        self.setWindowFlags(
            Qt.WindowType.Window
            | Qt.WindowType.WindowMinMaxButtonsHint
            | Qt.WindowType.WindowCloseButtonHint
        )
        self.setMinimumSize(480, 360)
        self.resize(760, 560)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, False)

        layout = QVBoxLayout(self)
        self._browser = QTextBrowser()
        self._browser.setOpenExternalLinks(True)
        self._browser.setReadOnly(True)
        layout.addWidget(self._browser)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        btn_close = QPushButton("Закрыть")
        btn_close.clicked.connect(self.hide)
        btn_row.addWidget(btn_close)
        layout.addLayout(btn_row)

    def set_step(self, step_type: str, step_title: str = "") -> None:
        title = f"Документация: {step_type}"
        if step_title:
            title = f"{title} ({step_title})"
        self.setWindowTitle(title)

        content = get_section_for_step(step_type)
        try:
            self._browser.setHtml(markdown_to_html(content))
        except Exception:
            self._browser.setPlainText(content)

    def show_documentation(self, step_type: str, step_title: str = "") -> None:
        self.set_step(step_type, step_title)
        self.show()
        self.raise_()
        self.activateWindow()
