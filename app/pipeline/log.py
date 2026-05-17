from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class LogEvent:
    ts: datetime
    level: str  # INFO/WARN/ERROR
    message: str


class MemoryLogger:
    def __init__(self):
        self.events: list[LogEvent] = []
        self._listeners: list[callable[[LogEvent], None]] = []

    def add_listener(self, fn: callable[[LogEvent], None]) -> None:
        self._listeners.append(fn)

    def _emit(self, level: str, message: str) -> None:
        ev = LogEvent(ts=datetime.now(), level=level, message=message)
        self.events.append(ev)
        for fn in list(self._listeners):
            fn(ev)

    def info(self, message: str) -> None:
        self._emit("INFO", message)

    def warn(self, message: str) -> None:
        self._emit("WARN", message)

    def error(self, message: str) -> None:
        self._emit("ERROR", message)

    def clear(self) -> None:
        self.events.clear()

