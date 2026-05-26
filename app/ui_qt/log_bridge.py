from __future__ import annotations

from PySide6.QtCore import QObject, Signal

from app.pipeline.log import LogEvent, MemoryLogger


class LogBridge(QObject):
    """Пересылает события лога из worker-потока в GUI-поток."""

    event = Signal(object)

    def connect_logger(self, logger: MemoryLogger) -> None:
        def _listener(ev: LogEvent) -> None:
            self.event.emit(ev)

        logger.add_listener(_listener)
