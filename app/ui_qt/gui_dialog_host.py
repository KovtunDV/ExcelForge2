from __future__ import annotations

import os
from typing import Any, Callable

from PySide6.QtCore import QObject, Qt, QThread, Signal, Slot
from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox, QWidget


class GuiDialogHost(QObject):
    """Run dialogs on the GUI thread; safe to call from a QThread worker."""

    _invoke = Signal(object)

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self._parent = parent
        self._invoke.connect(self._run_callable, Qt.BlockingQueuedConnection)

    def _on_gui_thread(self) -> bool:
        app = QApplication.instance()
        return app is not None and QThread.currentThread() is app.thread()

    def invoke(self, func: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        if self._on_gui_thread():
            return func(*args, **kwargs)
        result: list[Any] = []
        self._invoke.emit((func, args, kwargs, result))
        return result[0] if result else None

    @Slot(object)
    def _run_callable(self, payload: object) -> None:
        func, args, kwargs, result = payload  # type: ignore[misc]
        result.append(func(*args, **kwargs))

    def ask_open_filename(self, **kwargs: Any) -> str:
        def _do() -> str:
            title = str(kwargs.get("title", "") or "Выберите файл")
            initial = str(kwargs.get("initialdir", "") or "")
            filetypes = kwargs.get("filetypes")
            filt = "All files (*.*)"
            if filetypes and isinstance(filetypes, list):
                parts = [f"{d} ({p})" for d, p in filetypes if isinstance(d, str) and isinstance(p, str)]
                if parts:
                    filt = ";;".join(parts)
            path, _ = QFileDialog.getOpenFileName(self._parent, title, initial, filt)
            return path or ""

        return str(self.invoke(_do) or "")

    def ask_directory(self, **kwargs: Any) -> str:
        def _do() -> str:
            title = str(kwargs.get("title", "") or "Выберите каталог")
            initial = str(kwargs.get("initialdir", "") or "")
            path = QFileDialog.getExistingDirectory(self._parent, title, initial)
            return path or ""

        return str(self.invoke(_do) or "")

    def ask_save_filename(self, **kwargs: Any) -> str:
        def _do() -> str:
            title = str(kwargs.get("title", "") or "Сохранить файл")
            initialdir = str(kwargs.get("initialdir", "") or "")
            initialfile = str(kwargs.get("initialfile", "") or "")
            defaultext = str(kwargs.get("defaultextension", "") or "")
            filetypes = kwargs.get("filetypes")

            initial = initialdir
            if initialfile:
                initial = os.path.join(initialdir, initialfile) if initialdir else initialfile

            filt = "All files (*.*)"
            selected_filter = ""
            if filetypes and isinstance(filetypes, list):
                parts = [f"{d} ({p})" for d, p in filetypes if isinstance(d, str) and isinstance(p, str)]
                if parts:
                    filt = ";;".join(parts)
                    selected_filter = parts[0]

            path, _ = QFileDialog.getSaveFileName(
                self._parent,
                title,
                initial,
                filt,
                selected_filter,
            )
            if not path:
                return ""

            root, ext = os.path.splitext(path)
            if not ext and defaultext:
                suffix = defaultext if defaultext.startswith(".") else f".{defaultext}"
                path = root + suffix
            return path

        return str(self.invoke(_do) or "")

    def ask_retry_cancel(self, title: str, message: str) -> bool:
        def _do() -> bool:
            btn = QMessageBox.question(
                self._parent,
                title,
                message,
                QMessageBox.StandardButton.Retry | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Cancel,
            )
            return btn == QMessageBox.StandardButton.Retry

        return bool(self.invoke(_do))
