from __future__ import annotations

from typing import Any

# Ключи Qt/tk-диалогов и прочие runtime-хуки UI (см. pipeline_qt_hooks, builder_view).
QT_DIALOG_VARIABLE_KEYS: tuple[str, ...] = (
    "tk_askopenfilename",
    "tk_askdirectory",
    "tk_asksaveasfilename",
    "tk_askretrycancel",
    "qt_askopenfilename",
    "qt_askdirectory",
    "qt_asksaveasfilename",
    "qt_askretrycancel",
)

SYSTEM_RUNTIME_VARIABLE_KEYS: frozenset[str] = frozenset(
    {
        "_qt_dialog_host",
        "confirm_continue_on_zero_rows",
        *QT_DIALOG_VARIABLE_KEYS,
    }
)


def is_system_variable(name: str, value: Any = None) -> bool:
    """Служебная переменная контекста выполнения, не заданная пользователем в пайплайне."""
    key = str(name or "").strip()
    if not key:
        return True
    if key in SYSTEM_RUNTIME_VARIABLE_KEYS:
        return True
    if key.startswith("_"):
        return True
    if callable(value):
        return True
    return False


def user_variables_for_display(variables: dict[str, Any]) -> dict[str, Any]:
    """Переменные пайплайна для отображения пользователю (без служебных)."""
    return {k: v for k, v in variables.items() if not is_system_variable(k, v)}
