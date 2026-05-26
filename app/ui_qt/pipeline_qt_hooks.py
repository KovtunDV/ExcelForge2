from __future__ import annotations

from PySide6.QtWidgets import QWidget

from app.pipeline.context import RunContext
from app.ui_qt.gui_dialog_host import GuiDialogHost


def bind_qt_dialogs_to_context(ctx: RunContext, parent: QWidget) -> GuiDialogHost:
    """Подключает Qt-диалоги к контексту выполнения (с поддержкой вызова из worker-потока)."""
    host = GuiDialogHost(parent)
    ctx.variables["_qt_dialog_host"] = host

    def qt_askopenfilename(**kwargs: object) -> str:
        return host.ask_open_filename(**kwargs)  # type: ignore[arg-type]

    def qt_askdirectory(**kwargs: object) -> str:
        return host.ask_directory(**kwargs)  # type: ignore[arg-type]

    def qt_asksaveasfilename(**kwargs: object) -> str:
        return host.ask_save_filename(**kwargs)  # type: ignore[arg-type]

    def qt_askretrycancel(title: str, message: str) -> bool:
        return host.ask_retry_cancel(title, message)

    for key, fn in (
        ("tk_askopenfilename", qt_askopenfilename),
        ("tk_askdirectory", qt_askdirectory),
        ("tk_asksaveasfilename", qt_asksaveasfilename),
        ("tk_askretrycancel", qt_askretrycancel),
        ("qt_askopenfilename", qt_askopenfilename),
        ("qt_askdirectory", qt_askdirectory),
        ("qt_asksaveasfilename", qt_asksaveasfilename),
        ("qt_askretrycancel", qt_askretrycancel),
    ):
        ctx.variables[key] = fn

    return host
