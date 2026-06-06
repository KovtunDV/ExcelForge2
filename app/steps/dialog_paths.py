from __future__ import annotations

import os
from typing import Any

from app.pipeline.context import RunContext


def _path_is_accessible_dir(path: str) -> bool:
    if not path or not str(path).strip():
        return False
    ap = os.path.abspath(str(path).strip())
    return os.path.isdir(ap)


def resolve_dialog_initial_dir(
    p: dict[str, Any],
    *,
    fallback: str | None = None,
) -> str:
    """Стартовый каталог для диалога выбора файла/каталога."""
    preferred = str(p.get("directory_initial", "") or "").strip()

    if _path_is_accessible_dir(preferred):
        return os.path.abspath(preferred)

    if fallback:
        fb = str(fallback).strip()
        if _path_is_accessible_dir(fb):
            return os.path.abspath(fb)
        parent = os.path.dirname(os.path.abspath(fb)) if fb else ""
        if parent and _path_is_accessible_dir(parent):
            return parent

    return os.getcwd()


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
