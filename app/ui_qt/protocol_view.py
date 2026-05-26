from __future__ import annotations

from PySide6.QtCore import Qt, Slot
from PySide6.QtWidgets import QFrame, QPlainTextEdit, QSizePolicy, QVBoxLayout

from app.pipeline.log import LogEvent, MemoryLogger
from app.settings import load_settings
from app.ui_qt.font_utils import make_app_font


class ProtocolView(QFrame):
    def __init__(self, parent=None, *, height_lines: int | None = 5) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.text = QPlainTextEdit()
        self.text.setReadOnly(True)
        self.text.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        s = load_settings()
        self.text.setFont(make_app_font(s.font_family, s.font_size))

        if height_lines is None:
            self.text.setSizePolicy(
                QSizePolicy.Policy.Expanding,
                QSizePolicy.Policy.Expanding,
            )
            self.setSizePolicy(
                QSizePolicy.Policy.Expanding,
                QSizePolicy.Policy.Expanding,
            )
            layout.addWidget(self.text, stretch=1)
        else:
            line_px = max(16, self.text.fontMetrics().lineSpacing())
            fixed_h = max(72, height_lines * line_px + 12)
            self.text.setMinimumHeight(fixed_h)
            self.text.setMaximumHeight(fixed_h)
            layout.addWidget(self.text)

    def clear(self) -> None:
        self.text.clear()

    def append_event(self, ev: LogEvent) -> None:
        line = f"{ev.ts:%Y-%m-%d %H:%M:%S} [{ev.level}] {ev.message}"
        self.text.appendPlainText(line)
        sb = self.text.verticalScrollBar()
        sb.setValue(sb.maximum())

    def bind_logger(self, logger: MemoryLogger) -> None:
        def _listener(ev: LogEvent) -> None:
            self.append_event(ev)

        logger.add_listener(_listener)

    @Slot(object)
    def on_log_event(self, ev: LogEvent) -> None:
        self.append_event(ev)
