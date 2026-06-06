from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from app.pipeline.context import RunContext
from app.pipeline.registry import REGISTRY, StepDefinition
from app.pipeline.schema import Step
from app.steps.util import param_is_on

_SYSTEM_TYPES = frozenset({"date", "time", "datetime", "today", "now", "timestamp", "now_time"})


def _now() -> datetime:
    return datetime.now()


def _norm_name(name: str) -> str:
    n = str(name or "").strip()
    if n.startswith("@"):
        n = n[1:]
    return n.strip()


def _parse_days_offset(spec: dict[str, Any]) -> int:
    raw = spec.get("days_offset", spec.get("offset_days", spec.get("day_offset", spec.get("offset", 0))))
    if raw is None or raw == "":
        return 0
    try:
        return int(raw)
    except (TypeError, ValueError) as e:
        raise ValueError(f"days_offset must be an integer, got {raw!r}") from e


def _system_kind(spec: dict[str, Any]) -> str:
    return str(spec.get("system") or spec.get("type") or "").strip().lower()


def _is_system_value_spec(value: Any) -> bool:
    return isinstance(value, dict) and _system_kind(value) in _SYSTEM_TYPES


def _resolve_system_value(spec: dict[str, Any], *, label: str = "system value") -> str:
    kind = _system_kind(spec)
    if kind not in _SYSTEM_TYPES:
        raise ValueError(f"{label}: unknown system type {kind!r}; use date, time or datetime")

    fmt_raw = spec.get("format")
    offset = _parse_days_offset(spec)
    now = _now()

    if kind in ("date", "today"):
        dt = (now + timedelta(days=offset)).date()
        fmt = str(fmt_raw) if fmt_raw not in (None, "") else "%Y-%m-%d"
        try:
            return dt.strftime(fmt)
        except ValueError as e:
            raise ValueError(f"{label}: invalid date format {fmt!r}") from e

    if kind in ("time", "now_time"):
        fmt = str(fmt_raw) if fmt_raw not in (None, "") else "%H:%M:%S"
        try:
            return now.strftime(fmt)
        except ValueError as e:
            raise ValueError(f"{label}: invalid time format {fmt!r}") from e

    # datetime, now, timestamp
    dt = now + timedelta(days=offset)
    fmt = str(fmt_raw) if fmt_raw not in (None, "") else "%Y-%m-%d %H:%M:%S"
    try:
        return dt.strftime(fmt)
    except ValueError as e:
        raise ValueError(f"{label}: invalid datetime format {fmt!r}") from e


def _parse_system_values_list(raw: Any) -> list[dict[str, Any]]:
    if raw is None or raw == "" or raw == []:
        return []
    if not isinstance(raw, list):
        raise ValueError("globals_settings: system_values must be a list")
    out: list[dict[str, Any]] = []
    for i, item in enumerate(raw):
        if not isinstance(item, dict):
            raise ValueError(f"globals_settings: system_values[{i}] must be a dict")
        var = _norm_name(str(item.get("var") or item.get("name") or item.get("variable") or ""))
        if not var:
            raise ValueError(f"globals_settings: system_values[{i}]: var is required")
        out.append(dict(item, _var=var))
    return out


def _set_global(ctx: RunContext, name: str, value: Any, *, source: str = "") -> None:
    ctx.variables[name] = value
    suffix = f" ({source})" if source else ""
    ctx.logger.info(f"globals_settings: set @{name} = {value!r}{suffix}")


def run_globals_settings(ctx: RunContext, step: Step) -> None:
    """
    Задаёт глобальные переменные для всего пайплайна в ctx.variables.
    Эти значения можно подставлять в params других шагов как строку вида '@var'.
    """
    p = step.params

    # 1) Простые присваивания (в т.ч. системные date/time/datetime в виде dict)
    values = p.get("values") or {}
    if values:
        if not isinstance(values, dict):
            raise ValueError("globals_settings: values должен быть словарём {name: value}")
        for k, v in values.items():
            name = _norm_name(str(k))
            if not name:
                continue
            if _is_system_value_spec(v):
                resolved = _resolve_system_value(v, label=f"values[{name}]")
                _set_global(ctx, name, resolved, source="system")
            else:
                _set_global(ctx, name, v)

    # 2) Системные значения (дата, время) — список
    for i, item in enumerate(_parse_system_values_list(p.get("system_values"))):
        var = item["_var"]
        resolved = _resolve_system_value(item, label=f"system_values[{i}]")
        _set_global(ctx, var, resolved, source="system")

    # 3–4) Диалоги выбора каталога/файла — через params.dialogs или inline @*_dialog(...)
    # (выполняются в resolve_params до запуска шага)


def register_globals_settings() -> None:
    REGISTRY.register(
        StepDefinition(
            type="globals_settings",
            title="Общие настройки и установки",
            runner=run_globals_settings,
            default_params={
                "values": {},
                "system_values": [],
                "directory_open_dialog": False,
                "directory_var": "directory",
                "directory_open_dialog_help": "Выберите каталог",
                "directory_initial": "",
                "dialogs": [],
                "file_open_dialog": False,
                "file_var": "file_path",
                "file_open_dialog_help": "Выберите файл",
                "filetypes": [("All files", "*.*")],
            },
        )
    )
