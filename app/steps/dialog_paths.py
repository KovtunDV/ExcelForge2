from __future__ import annotations

import os
from typing import Any

from app.pipeline.context import RunContext
from app.steps.util import param_is_on


def _require_tk_callable(ctx: RunContext, key: str, feature: str) -> Any:
    fn = ctx.variables.get(key)
    if not callable(fn):
        raise ValueError(
            f"{feature}: требуется GUI (в контексте не задан {key}). "
            "Запускайте пайплайн из вкладок Builder или Runner с подключёнными диалогами."
        )
    return fn


def apply_load_excel_runtime_dialogs(ctx: RunContext, p: dict[str, Any]) -> None:
    """При включённых флагах запрашивает файл/каталог и перезаписывает file_path или directory."""
    input_mode = str(p.get("input_mode", "mask"))

    if param_is_on(p.get("file_open_dialog")) and input_mode == "file":
        ask = _require_tk_callable(ctx, "tk_askopenfilename", "file_open_dialog")
        title = str(p.get("file_open_dialog_help") or "Выберите файл для загрузки")
        fp_existing = str(p.get("file_path", "") or "").strip()
        initialdir = os.path.dirname(fp_existing) if fp_existing else os.getcwd()
        path = ask(
            title=title,
            initialdir=initialdir or os.getcwd(),
            filetypes=[("Excel", "*.xlsx *.xlsm *.xls"), ("All files", "*.*")],
        )
        if not path:
            raise ValueError("Файл не выбран (file_open_dialog).")
        p["file_path"] = path

    if param_is_on(p.get("directory_open_dialog")) and input_mode in ("mask", "latest"):
        askd = _require_tk_callable(ctx, "tk_askdirectory", "directory_open_dialog")
        title = str(p.get("directory_open_dialog_help") or "Выберите каталог с файлами Excel")
        initial = str(p.get("directory", "") or "").strip() or os.getcwd()
        d = askd(title=title, initialdir=initial)
        if not d:
            raise ValueError("Каталог не выбран (directory_open_dialog).")
        p["directory"] = d


def apply_save_excel_runtime_dialogs(ctx: RunContext, p: dict[str, Any]) -> None:
    """
    При file_open_dialog — диалог «Сохранить как»: задаёт out_dir и (если нет split) filename.
    При directory_open_dialog — только каталог out_dir (имя файла из YAML).
    Если оба on, срабатывает только выбор файла (как более конкретный путь).
    """
    split_by = str(p.get("split_by_column", "") or "").strip()

    if param_is_on(p.get("file_open_dialog")):
        asks = _require_tk_callable(ctx, "tk_asksaveasfilename", "file_open_dialog")
        title = str(p.get("file_open_dialog_help") or "Укажите файл для сохранения")
        out_dir = str(p.get("out_dir", "") or "").strip()
        filename = str(p.get("filename", "") or "result.xlsx").strip() or "result.xlsx"
        initialdir = out_dir if out_dir else os.getcwd()
        path = asks(
            title=title,
            initialdir=initialdir,
            initialfile=filename,
            defaultextension=".xlsx",
            filetypes=[("Excel", "*.xlsx"), ("All files", "*.*")],
        )
        if not path:
            raise ValueError("Файл не выбран (file_open_dialog).")
        dirpart = os.path.dirname(path)
        p["out_dir"] = dirpart if dirpart else initialdir
        if not split_by:
            p["filename"] = os.path.basename(path)
        return

    if param_is_on(p.get("directory_open_dialog")):
        askd = _require_tk_callable(ctx, "tk_askdirectory", "directory_open_dialog")
        title = str(p.get("directory_open_dialog_help") or "Выберите каталог для сохранения файлов")
        initial = str(p.get("out_dir", "") or "").strip() or os.getcwd()
        d = askd(title=title, initialdir=initial)
        if not d:
            raise ValueError("Каталог не выбран (directory_open_dialog).")
        p["out_dir"] = d
