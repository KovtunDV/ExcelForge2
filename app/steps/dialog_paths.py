from __future__ import annotations

import os
from typing import Any

from app.pipeline.context import RunContext
from app.steps.util import param_is_on


def parse_filetypes_param(raw: object) -> list[tuple[str, str]] | None:
    """
    Список пар (описание, маска) для Tk filetypes / askopenfilename.

    Поддерживает:
    - [["Excel", "*.xlsx"], ...]
    - [{"description": "Excel", "pattern": "*.xlsx"}, ...]
    """
    if raw is None or raw == "" or raw == []:
        return None
    if not isinstance(raw, list):
        return None
    out: list[tuple[str, str]] = []
    for item in raw:
        if isinstance(item, (list, tuple)) and len(item) >= 2:
            desc, pat = str(item[0]).strip(), str(item[1]).strip()
            if pat:
                out.append((desc or "Files", pat))
        elif isinstance(item, dict):
            desc = str(item.get("description") or item.get("label") or "Files").strip()
            pat = str(item.get("pattern") or item.get("glob") or "").strip()
            if pat:
                out.append((desc, pat))
    return out if out else None


def filetypes_from_glob_pattern(pattern: object, *, label_prefix: str = "Файлы") -> list[tuple[str, str]]:
    """Строит filetypes для диалога из маски шага (pattern), как в режиме mask."""
    raw = str(pattern or "").strip() or "*.*"
    parts = [x.strip() for x in raw.replace(",", ";").split(";") if x.strip()]
    if not parts:
        parts = ["*.*"]
    # Tk (Windows): несколько масок в одной группе через пробел: "*.xlsx *.xls"
    glob_pat = " ".join(parts)
    label = f"{label_prefix} ({', '.join(parts)})"
    return [(label, glob_pat), ("All files", "*.*")]


def resolve_open_filetypes(p: dict[str, Any], *, default_pattern: str = "*.xlsx") -> list[tuple[str, str]]:
    """filetypes из params или из pattern (как в load_excel)."""
    explicit = parse_filetypes_param(p.get("filetypes"))
    if explicit:
        return explicit
    return filetypes_from_glob_pattern(p.get("pattern", default_pattern))


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
        filetypes = resolve_open_filetypes(p, default_pattern="*.xlsx")
        path = ask(
            title=title,
            initialdir=initialdir or os.getcwd(),
            filetypes=filetypes,
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


def apply_group_template_export_dialogs(ctx: RunContext, p: dict[str, Any]) -> None:
    """Диалоги каталога вывода и файла шаблона для group_template_export."""
    if param_is_on(p.get("template_open_dialog")):
        askf = _require_tk_callable(ctx, "tk_askopenfilename", "template_open_dialog")
        title = str(p.get("template_open_dialog_help") or "Выберите Excel-шаблон")
        tp = str(p.get("template_path", "") or "").strip()
        initialdir = os.path.dirname(tp) if tp else os.getcwd()
        path = askf(
            title=title,
            initialdir=initialdir or os.getcwd(),
            filetypes=[("Excel", "*.xlsx"), ("All files", "*.*")],
        )
        if not path:
            raise ValueError("Шаблон не выбран (template_open_dialog).")
        p["template_path"] = path

    if param_is_on(p.get("directory_open_dialog")):
        askd = _require_tk_callable(ctx, "tk_askdirectory", "directory_open_dialog")
        title = str(p.get("directory_open_dialog_help") or "Выберите каталог для сохранения файлов")
        initial = str(p.get("out_dir", "") or "").strip() or os.getcwd()
        d = askd(title=title, initialdir=initial)
        if not d:
            raise ValueError("Каталог не выбран (directory_open_dialog).")
        p["out_dir"] = d
