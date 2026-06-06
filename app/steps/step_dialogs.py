from __future__ import annotations

import copy
import os
import re
from dataclasses import dataclass
from typing import Any, Literal

from app.pipeline.context import RunContext
from app.steps.dialog_paths import (
    _dialog_flag_on,
    _dialog_help,
    _require_tk_callable,
    filetypes_from_glob_pattern,
    parse_filetypes_param,
    resolve_dialog_initial_dir,
    resolve_open_filetypes,
)
from app.steps.util import param_is_on

DialogKind = Literal["file_open", "directory_open", "file_save"]
StoreTarget = Literal["param", "variable", "both"]

_DIALOG_KIND_ALIASES: dict[str, DialogKind] = {
    "file_open": "file_open",
    "file": "file_open",
    "open_file": "file_open",
    "file_open_dialog": "file_open",
    "directory_open": "directory_open",
    "directory": "directory_open",
    "dir": "directory_open",
    "directory_open_dialog": "directory_open",
    "file_save": "file_save",
    "save_file": "file_save",
    "file_save_dialog": "file_save",
    "save_as": "file_save",
}

_INLINE_DIALOG_RE = re.compile(
    r"^@(file_open_dialog|directory_open_dialog|file_save_dialog)(?:\((.*)\))?$"
)


@dataclass(frozen=True)
class DialogSpec:
    kind: DialogKind
    title: str
    assign: str
    store: StoreTarget = "param"
    initial: str = ""
    filetypes: list[tuple[str, str]] | None = None
    initial_file: str = ""
    default_extension: str = ""
    assign_dir: str = ""
    assign_name: str = ""
    scope: str = ""


def _norm_assign_name(raw: Any) -> str:
    s = str(raw or "").strip()
    if s.startswith("@"):
        s = s[1:].strip()
    return s


def _parse_one_dialog(raw: Any, index: int) -> DialogSpec | None:
    if raw is None:
        return None
    if isinstance(raw, str):
        kind = _DIALOG_KIND_ALIASES.get(raw.strip().lower())
        if not kind:
            raise ValueError(f"dialogs[{index}]: неизвестный тип {raw!r}")
        return DialogSpec(kind=kind, title="", assign="")
    if not isinstance(raw, dict):
        raise ValueError(f"dialogs[{index}]: ожидается строка или словарь")

    if not param_is_on(raw.get("enabled", True)):
        return None

    kind_raw = (
        raw.get("kind")
        or raw.get("type")
        or raw.get("dialog")
        or raw.get("mode")
        or ""
    )
    kind = _DIALOG_KIND_ALIASES.get(str(kind_raw).strip().lower())
    if not kind:
        raise ValueError(f"dialogs[{index}]: не задан kind/type (file_open, directory_open, file_save)")

    assign = _norm_assign_name(
        raw.get("assign") or raw.get("variable") or raw.get("var") or raw.get("target")
    )
    if not assign:
        raise ValueError(f"dialogs[{index}]: задайте assign (имя параметра или переменной)")

    title = str(
        raw.get("title")
        or raw.get("help")
        or raw.get("prompt")
        or raw.get("label")
        or ""
    ).strip()

    store_raw = str(raw.get("store") or raw.get("target_type") or "param").strip().lower()
    store: StoreTarget = "param"
    if store_raw in ("variable", "var", "global", "globals"):
        store = "variable"
    elif store_raw in ("both", "param_and_variable", "all"):
        store = "both"

    filetypes = parse_filetypes_param(raw.get("filetypes"))
    if filetypes is None and kind == "file_open":
        filetypes = filetypes_from_glob_pattern(raw.get("pattern", "*.*"))

    return DialogSpec(
        kind=kind,
        title=title,
        assign=assign,
        store=store,
        initial=str(raw.get("initial") or raw.get("directory_initial") or "").strip(),
        filetypes=filetypes,
        initial_file=str(raw.get("initial_file") or raw.get("filename") or "").strip(),
        default_extension=str(raw.get("default_extension") or raw.get("extension") or "").strip(),
        assign_dir=_norm_assign_name(raw.get("assign_dir") or raw.get("dir_param") or ""),
        assign_name=_norm_assign_name(raw.get("assign_name") or raw.get("name_param") or ""),
    )


def parse_dialog_specs(raw: Any) -> list[DialogSpec]:
    if raw is None or raw == "" or raw == []:
        return []
    if not isinstance(raw, list):
        raise ValueError("dialogs: ожидается список описаний диалогов")
    out: list[DialogSpec] = []
    for i, item in enumerate(raw):
        spec = _parse_one_dialog(item, i)
        if spec is not None:
            out.append(spec)
    return out


def _default_title(kind: DialogKind) -> str:
    return {
        "file_open": "Выберите файл",
        "directory_open": "Выберите каталог",
        "file_save": "Укажите файл для сохранения",
    }[kind]


def _inline_kind(token: str) -> DialogKind | None:
    m = _INLINE_DIALOG_RE.match(str(token or "").strip())
    if not m:
        return None
    key = m.group(1)
    mapping = {
        "file_open_dialog": "file_open",
        "directory_open_dialog": "directory_open",
        "file_save_dialog": "file_save",
    }
    return mapping.get(key)


def _inline_title(token: str) -> str:
    m = _INLINE_DIALOG_RE.match(str(token or "").strip())
    if not m:
        return ""
    return str(m.group(2) or "").strip()


def is_inline_dialog_token(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    return _INLINE_DIALOG_RE.match(value.strip()) is not None


def legacy_dialog_specs(p: dict[str, Any], step_type: str) -> list[DialogSpec]:
    """Преобразует устаревшие флаги *_open_dialog в список dialogs."""
    out: list[DialogSpec] = []
    st = str(step_type or "").strip().lower()

    if st == "globals_settings":
        if param_is_on(p.get("directory_open_dialog")):
            out.append(
                DialogSpec(
                    kind="directory_open",
                    title=str(p.get("directory_open_dialog_help") or "Выберите каталог"),
                    assign=_norm_assign_name(p.get("directory_var") or "directory"),
                    store="variable",
                    initial=str(p.get("directory_initial") or ""),
                )
            )
        if param_is_on(p.get("file_open_dialog")):
            out.append(
                DialogSpec(
                    kind="file_open",
                    title=str(p.get("file_open_dialog_help") or "Выберите файл"),
                    assign=_norm_assign_name(p.get("file_var") or "file_path"),
                    store="variable",
                    initial=str(p.get("directory_initial") or ""),
                    filetypes=parse_filetypes_param(p.get("filetypes")),
                )
            )
        return out

    if st == "load_excel":
        input_mode = str(p.get("input_mode", "mask")).strip().lower()
        if param_is_on(p.get("file_open_dialog")) and input_mode == "file":
            out.append(
                DialogSpec(
                    kind="file_open",
                    title=str(p.get("file_open_dialog_help") or "Выберите файл для загрузки"),
                    assign="file_path",
                    initial=str(p.get("directory_initial") or ""),
                    filetypes=resolve_open_filetypes(p, default_pattern="*.xlsx"),
                )
            )
        if param_is_on(p.get("directory_open_dialog")) and input_mode in ("mask", "latest"):
            out.append(
                DialogSpec(
                    kind="directory_open",
                    title=str(p.get("directory_open_dialog_help") or "Выберите каталог с файлами Excel"),
                    assign="directory",
                    initial=str(p.get("directory_initial") or ""),
                )
            )
        return out

    if st == "save_excel":
        split_by = str(p.get("split_by_column", "") or "").strip()
        if param_is_on(p.get("file_open_dialog")):
            out.append(
                DialogSpec(
                    kind="file_save",
                    title=str(p.get("file_open_dialog_help") or "Укажите файл для сохранения"),
                    assign="",
                    initial=str(p.get("directory_initial") or ""),
                    initial_file=str(p.get("filename") or "result.xlsx"),
                    default_extension=".xlsx",
                    assign_dir="out_dir",
                    assign_name="" if split_by else "filename",
                )
            )
        elif param_is_on(p.get("directory_open_dialog")):
            out.append(
                DialogSpec(
                    kind="directory_open",
                    title=str(p.get("directory_open_dialog_help") or "Выберите каталог для сохранения"),
                    assign="out_dir",
                    initial=str(p.get("directory_initial") or ""),
                )
            )
        return out

    if st == "group_template_export":
        if param_is_on(p.get("template_open_dialog")):
            out.append(
                DialogSpec(
                    kind="file_open",
                    title=str(p.get("template_open_dialog_help") or "Выберите Excel-шаблон"),
                    assign="template_path",
                    filetypes=[("Excel", "*.xlsx"), ("All files", "*.*")],
                )
            )
        if param_is_on(p.get("directory_open_dialog")):
            out.append(
                DialogSpec(
                    kind="directory_open",
                    title=str(p.get("directory_open_dialog_help") or "Выберите каталог для сохранения"),
                    assign="out_dir",
                )
            )
        return out

    if st == "file_ops":
        operation = str(p.get("operation", "copy")).strip().lower()
        source_mode = str(p.get("source_mode", "file")).strip().lower()

        source_wants_file = (
            operation in ("copy", "move", "zip_extract")
            or (operation == "delete" and source_mode == "file")
            or (operation == "zip_create" and source_mode == "file")
        )
        source_wants_dir = (
            operation in ("copy_latest", "copy_by_mask")
            or (operation == "zip_create" and source_mode in ("mask", "latest", "files"))
            or (operation == "delete" and source_mode != "file")
        )
        dest_wants_path = operation in ("copy", "move", "copy_latest", "copy_by_mask", "zip_create")
        dest_wants_dir = operation in (
            "copy",
            "move",
            "copy_latest",
            "copy_by_mask",
            "zip_create",
            "zip_extract",
        )

        has_scoped_dir_flags = (
            _dialog_flag_on(p, "source_directory_open_dialog")
            or _dialog_flag_on(p, "dest_directory_open_dialog")
            or _dialog_flag_on(p, "dest_save_dialog")
        )

        if source_wants_file and _dialog_flag_on(p, "source_file_open_dialog", "file_open_dialog"):
            fp = str(p.get("source_path", "") or "").strip()
            out.append(
                DialogSpec(
                    kind="file_open",
                    title=_dialog_help(
                        p,
                        "source_file_open_dialog_help",
                        "Выберите исходный файл",
                        "file_open_dialog_help",
                    ),
                    assign="source_path",
                    initial=str(p.get("source_directory_initial") or p.get("directory_initial") or ""),
                    scope="source",
                    filetypes=resolve_open_filetypes(
                        {
                            "filetypes": p.get("source_filetypes") or p.get("filetypes"),
                            "pattern": p.get("pattern"),
                        },
                        default_pattern="*.*",
                    ),
                )
            )

        source_dir_on = _dialog_flag_on(p, "source_directory_open_dialog")
        if not has_scoped_dir_flags and not source_dir_on:
            source_dir_on = source_wants_dir and _dialog_flag_on(p, "directory_open_dialog")
        if source_wants_dir and source_dir_on:
            out.append(
                DialogSpec(
                    kind="directory_open",
                    title=_dialog_help(
                        p,
                        "source_directory_open_dialog_help",
                        "Выберите исходный каталог",
                        "directory_open_dialog_help",
                    ),
                    assign="directory",
                    initial=str(p.get("source_directory_initial") or p.get("directory_initial") or ""),
                    scope="source",
                )
            )

        if dest_wants_path and _dialog_flag_on(p, "dest_save_dialog"):
            dest_path = str(p.get("dest_path", "") or "").strip()
            filename = (
                str(p.get("dest_name") or p.get("filename") or "output.zip").strip() or "output.zip"
            )
            ext = str(p.get("extension", "") or "").strip()
            if operation == "zip_create":
                default_ext = ext if ext.startswith(".") else (f".{ext}" if ext else ".zip")
            else:
                default_ext = ext if ext.startswith(".") else (f".{ext}" if ext else "")
            out.append(
                DialogSpec(
                    kind="file_save",
                    title=_dialog_help(p, "dest_save_dialog_help", "Укажите файл назначения"),
                    assign="dest_path",
                    assign_dir="dest_dir",
                    assign_name="filename",
                    initial=str(p.get("dest_directory_initial") or p.get("directory_initial") or ""),
                    scope="dest",
                    initial_file=os.path.basename(dest_path) if dest_path else filename,
                    default_extension=default_ext,
                    filetypes=(
                        [("ZIP archive", "*.zip"), ("All files", "*.*")]
                        if operation == "zip_create"
                        else [("All files", "*.*")]
                    ),
                )
            )
            return out

        dest_dir_on = _dialog_flag_on(p, "dest_directory_open_dialog")
        if not has_scoped_dir_flags and not dest_dir_on:
            dest_dir_on = (
                dest_wants_dir
                and _dialog_flag_on(p, "directory_open_dialog")
                and not source_wants_dir
            )
        if dest_wants_dir and dest_dir_on:
            out.append(
                DialogSpec(
                    kind="directory_open",
                    title=_dialog_help(
                        p,
                        "dest_directory_open_dialog_help",
                        "Выберите каталог назначения",
                        "directory_open_dialog_help",
                    ),
                    assign="dest_dir",
                    initial=str(p.get("dest_directory_initial") or p.get("directory_initial") or ""),
                    scope="dest",
                )
            )
        return out

    return out


def _resolve_initial_dir(
    ctx: RunContext,
    p: dict[str, Any],
    spec: DialogSpec,
    *,
    fallback: str = "",
) -> str:
    initial = spec.initial or str(p.get("directory_initial") or "")
    if initial.startswith("@"):
        key = initial[1:]
        if key in ctx.variables:
            initial = str(ctx.variables[key])
        elif key in p:
            initial = str(p[key])
        else:
            initial = ""
    scoped_p = dict(p)
    if initial:
        scoped_p["directory_initial"] = initial
    return resolve_dialog_initial_dir(
        scoped_p,
        fallback=fallback or initial,
        scope=spec.scope or "",
    )


def _run_dialog(ctx: RunContext, p: dict[str, Any], spec: DialogSpec) -> str:
    title = spec.title or _default_title(spec.kind)
    fallback = ""
    if spec.assign and spec.assign in p:
        fallback = str(p.get(spec.assign) or "")
    if not fallback and spec.assign_dir and spec.assign_dir in p:
        fallback = str(p.get(spec.assign_dir) or "")

    if spec.kind == "file_open":
        ask = _require_tk_callable(ctx, "tk_askopenfilename", spec.kind)
        initialdir = _resolve_initial_dir(ctx, p, spec, fallback=fallback)
        filetypes = spec.filetypes or [("All files", "*.*")]
        path = ask(title=title, initialdir=initialdir, filetypes=filetypes)
        if not path:
            raise ValueError(f"Файл не выбран ({title}).")
        return path

    if spec.kind == "directory_open":
        askd = _require_tk_callable(ctx, "tk_askdirectory", spec.kind)
        initialdir = _resolve_initial_dir(ctx, p, spec, fallback=fallback)
        path = askd(title=title, initialdir=initialdir)
        if not path:
            raise ValueError(f"Каталог не выбран ({title}).")
        return path

    asks = _require_tk_callable(ctx, "tk_asksaveasfilename", spec.kind)
    initialdir = _resolve_initial_dir(
        ctx,
        p,
        spec,
        fallback=fallback or str(p.get(spec.assign_dir or "") or ""),
    )
    initialfile = spec.initial_file or (
        os.path.basename(fallback) if fallback and not _path_is_dir(fallback) else "output"
    )
    ext = spec.default_extension or ""
    defaultextension = ext if ext.startswith(".") else (f".{ext}" if ext else "")
    filetypes = spec.filetypes or [("All files", "*.*")]
    path = asks(
        title=title,
        initialdir=initialdir,
        initialfile=initialfile,
        defaultextension=defaultextension,
        filetypes=filetypes,
    )
    if not path:
        raise ValueError(f"Файл не выбран ({title}).")
    return path


def _path_is_dir(path: str) -> bool:
    try:
        return os.path.isdir(path)
    except OSError:
        return False


def _assign_dialog_result(
    ctx: RunContext,
    p: dict[str, Any],
    spec: DialogSpec,
    path: str,
) -> None:
    if spec.kind == "file_save" and spec.assign_dir:
        dirpart = os.path.dirname(path) or path
        p[spec.assign_dir] = dirpart
        if spec.assign_name:
            p[spec.assign_name] = os.path.basename(path)
        if spec.assign:
            p[spec.assign] = path
    elif spec.assign:
        p[spec.assign] = path

    if spec.store in ("variable", "both") and spec.assign:
        ctx.variables[spec.assign] = path
        ctx.logger.info(f"dialog: set @{spec.assign} = {path!r}")

    if spec.kind == "file_save" and spec.assign_dir and spec.store in ("variable", "both"):
        ctx.variables[spec.assign_dir] = p.get(spec.assign_dir, "")


def apply_configured_dialogs(ctx: RunContext, p: dict[str, Any], *, step_type: str) -> None:
    """Выполнить dialogs[] и устаревшие флаги; записать результаты в params/variables."""
    specs = parse_dialog_specs(p.get("dialogs") or p.get("open_dialogs"))
    specs.extend(legacy_dialog_specs(p, step_type))
    for i, spec in enumerate(specs):
        path = _run_dialog(ctx, p, spec)
        _assign_dialog_result(ctx, p, spec, path)
        ctx.logger.info(
            f"dialog[{i + 1}/{len(specs)}]: {spec.kind} -> {spec.assign!r} = {path!r}"
        )


def _resolve_dialog_inline(value: str, ctx: RunContext, p: dict[str, Any]) -> str:
    kind = _inline_kind(value)
    if kind is None:
        return value
    title = _inline_title(value) or _default_title(kind)
    spec = DialogSpec(kind=kind, title=title, assign="_inline")
    fallback_key = ""  # inline has no preset assign target in p
    path = _run_dialog(ctx, p, spec)
    return path


_VAR_EMBED_RE = re.compile(r"@([A-Za-z_][A-Za-z0-9_]*)")


def resolve_params(ctx: RunContext, params: dict[str, Any], *, step_type: str = "") -> dict[str, Any]:
    """
    Подготовка params шага:
    1. dialogs[] и устаревшие флаги;
    2. подстановка @var и inline @file_open_dialog(…).
    """
    p = copy.deepcopy(params)
    apply_configured_dialogs(ctx, p, step_type=step_type)
    return _resolve_value_deep(p, ctx)


def _resolve_value_deep(v: Any, ctx: RunContext) -> Any:
    variables = ctx.variables
    if isinstance(v, str):
        s = v.strip()
        if is_inline_dialog_token(s):
            return _resolve_dialog_inline(s, ctx, {})
        if s.startswith("@") and len(s) > 1 and " " not in s and "(" not in s:
            key = s[1:]
            if key in variables:
                return variables[key]
            if key in ctx.df_store:
                return variables.get(key, s)
        if "@" not in v:
            return v

        def _repl(m: re.Match[str]) -> str:
            key = m.group(1)
            if key in variables:
                return str(variables[key])
            return m.group(0)

        return _VAR_EMBED_RE.sub(_repl, v)
    if isinstance(v, list):
        return [_resolve_value_deep(x, ctx) for x in v]
    if isinstance(v, dict):
        return {k: _resolve_value_deep(val, ctx) for k, val in v.items()}
    return v
