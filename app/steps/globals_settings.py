from __future__ import annotations

from typing import Any

from app.pipeline.context import RunContext
from app.pipeline.registry import REGISTRY, StepDefinition
from app.pipeline.schema import Step
from app.steps.dialog_paths import parse_filetypes_param
from app.steps.util import param_is_on


def _norm_name(name: str) -> str:
    n = str(name or "").strip()
    if n.startswith("@"):
        n = n[1:]
    return n.strip()


def _require_tk_callable(ctx: RunContext, key: str, feature: str) -> Any:
    fn = ctx.variables.get(key)
    if not callable(fn):
        raise ValueError(
            f"{feature}: требуется GUI (в контексте не задан {key}). "
            "Запускайте пайплайн из вкладок Builder или Runner с подключёнными диалогами."
        )
    return fn


def run_globals_settings(ctx: RunContext, step: Step) -> None:
    """
    Задаёт глобальные переменные для всего пайплайна в ctx.variables.
    Эти значения можно подставлять в params других шагов как строку вида '@var'.
    """
    p = step.params

    # 1) Простые присваивания
    values = p.get("values") or {}
    if values:
        if not isinstance(values, dict):
            raise ValueError("globals_settings: values должен быть словарём {name: value}")
        for k, v in values.items():
            name = _norm_name(str(k))
            if not name:
                continue
            ctx.variables[name] = v
            ctx.logger.info(f"globals_settings: set @{name} = {v!r}")

    # 2) Диалог выбора каталога
    if param_is_on(p.get("directory_open_dialog")):
        var = _norm_name(str(p.get("directory_var") or "directory"))
        askd = _require_tk_callable(ctx, "tk_askdirectory", "directory_open_dialog")
        title = str(p.get("directory_open_dialog_help") or "Выберите каталог")
        initial = str(p.get("directory_initial", "") or "").strip()
        d = askd(title=title, initialdir=initial) if initial else askd(title=title)
        if not d:
            raise ValueError("Каталог не выбран (directory_open_dialog).")
        ctx.variables[var] = d
        ctx.logger.info(f"globals_settings: set @{var} = {d!r} (from directory dialog)")

    # 3) Диалог выбора файла
    if param_is_on(p.get("file_open_dialog")):
        var = _norm_name(str(p.get("file_var") or "file_path"))
        askf = _require_tk_callable(ctx, "tk_askopenfilename", "file_open_dialog")
        title = str(p.get("file_open_dialog_help") or "Выберите файл")
        filetypes = parse_filetypes_param(p.get("filetypes")) or [("All files", "*.*")]
        r = askf(title=title, filetypes=filetypes)
        if not r:
            raise ValueError("Файл не выбран (file_open_dialog).")
        ctx.variables[var] = r
        ctx.logger.info(f"globals_settings: set @{var} = {r!r} (from file dialog)")


def register_globals_settings() -> None:
    REGISTRY.register(
        StepDefinition(
            type="globals_settings",
            title="Общие настройки и установки",
            runner=run_globals_settings,
            default_params={
                "values": {},
                "directory_open_dialog": False,
                "directory_var": "directory",
                "directory_open_dialog_help": "Выберите каталог",
                "directory_initial": "",
                "file_open_dialog": False,
                "file_var": "file_path",
                "file_open_dialog_help": "Выберите файл",
                "filetypes": [("All files", "*.*")],
            },
        )
    )

