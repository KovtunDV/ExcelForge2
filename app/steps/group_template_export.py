from __future__ import annotations

import os
from typing import Any

import pandas as pd

from app.pipeline.context import RunContext
from app.pipeline.registry import REGISTRY, StepDefinition
from app.pipeline.schema import Step
from app.steps.dialog_paths import apply_group_template_export_dialogs
from app.steps.excel_template import (
    build_output_filename,
    format_scalar,
    group_key_to_str,
    parse_table_columns,
    safe_eval_scalar_expr,
    write_form_row_to_template,
    write_group_to_template,
)
from app.steps.filter_expr import eval_expression
from app.steps.numeric_parse import coerce_to_float, parse_numeric_series
from app.steps.util import ensure_df_exists, get_required_param, param_is_on


def _is_param_empty(raw: Any) -> bool:
    return raw is None or raw == "" or raw == [] or raw == {}


def _is_single_row_form_mode(p: dict[str, Any]) -> bool:
    if param_is_on(p.get("single_row_mode")):
        return True
    return _is_param_empty(p.get("table_start_row")) and _is_param_empty(p.get("table_columns"))


def _parse_filename_inc(p: dict[str, Any], form_mode: bool) -> str | None:
    """
    Размещение {{inc}} в имени файла (однострочный режим).
    None — не добавлять; 'prefix' — в начале; 'suffix' — в конце (перед расширением).
    """
    if not form_mode:
        return None
    raw = p.get("filename_inc")
    if raw is None and "filename_inc_prefix" in p:
        legacy = p.get("filename_inc_prefix")
        if legacy is None or param_is_on(legacy):
            return "prefix"
        return None
    if raw is None:
        return "prefix"
    if isinstance(raw, dict):
        if not param_is_on(raw.get("enabled", True)):
            return None
        pos = str(raw.get("position", raw.get("place", "prefix"))).strip().lower()
        if pos in ("suffix", "suf", "end", "tail"):
            return "suffix"
        return "prefix"
    if isinstance(raw, str):
        s = raw.strip().lower()
        if s in ("", "false", "0", "no", "off", "none"):
            return None
        if s in ("suffix", "suf", "end", "tail"):
            return "suffix"
        if s in ("prefix", "pref", "start", "begin", "true", "1", "yes", "on"):
            return "prefix"
        raise ValueError(
            f"filename_inc: неизвестное значение {raw!r}; используйте prefix, suffix или false"
        )
    if param_is_on(raw):
        return "prefix"
    return None


def _parse_table_start_row(p: dict[str, Any], *, form_mode: bool) -> int:
    raw = p.get("table_start_row")
    if _is_param_empty(raw):
        if form_mode:
            return 1
        return 1
    return int(raw)


def _parse_table_template_row(p: dict[str, Any], table_start_row: int) -> int:
    raw = p.get("table_template_row")
    if _is_param_empty(raw):
        return table_start_row
    return int(raw)


def _parse_group_by(raw: Any) -> list[str]:
    if isinstance(raw, str):
        s = raw.strip()
        if not s:
            raise ValueError("group_by: укажите имя столбца или список столбцов")
        return [s]
    if isinstance(raw, list):
        cols = [str(c).strip() for c in raw if str(c).strip()]
        if not cols:
            raise ValueError("group_by: пустой список")
        return cols
    raise ValueError("group_by must be string or list of column names")


def _parse_aggregations(raw: Any) -> list[dict[str, Any]]:
    if raw is None or raw == "" or raw == []:
        return []
    if not isinstance(raw, list):
        raise ValueError("aggregations must be a list")
    out: list[dict[str, Any]] = []
    for i, item in enumerate(raw):
        if not isinstance(item, dict):
            raise ValueError(f"aggregations[{i}] must be a dict")
        name = str(item.get("name") or item.get("as") or "").strip()
        if not name:
            raise ValueError(f"aggregations[{i}]: name is required")
        out.append(dict(item, name=name))
    return out


def _numeric_variables(variables: dict[str, Any]) -> dict[str, float]:
    env: dict[str, float] = {}
    for k, v in variables.items():
        if k.startswith("_") or k.startswith("tk_"):
            continue
        key = str(k).lstrip("@")
        num = coerce_to_float(v)
        if num is not None:
            env[key] = num
    return env


def _agg_column_series(gdf: pd.DataFrame, col: str) -> pd.Series:
    return parse_numeric_series(gdf[col])


def _agg_join_column(gdf: pd.DataFrame, col: str, spec: dict[str, Any]) -> str:
    if col not in gdf.columns:
        raise ValueError(f"column not found: {col!r}")
    sep = str(spec.get("separator", spec.get("sep", spec.get("delimiter", ";"))))
    unique = param_is_on(spec.get("unique", False))
    skip_empty = param_is_on(spec.get("skip_empty", True))

    parts: list[str] = []
    seen: set[str] = set()
    for val in gdf[col]:
        if val is None or (isinstance(val, float) and val != val):
            if skip_empty:
                continue
            s = ""
        else:
            s = str(val).strip()
            if skip_empty and not s:
                continue
        if unique:
            if s in seen:
                continue
            seen.add(s)
        parts.append(s)
    return sep.join(parts)


def _compute_aggregations(
    gdf: pd.DataFrame,
    specs: list[dict[str, Any]],
    variables: dict[str, Any],
) -> dict[str, Any]:
    if not specs:
        return {}
    results: dict[str, Any] = {}
    var_num = _numeric_variables(variables)
    pending = list(specs)
    for _ in range(len(specs) + 2):
        if not pending:
            break
        still: list[dict[str, Any]] = []
        for spec in pending:
            name = spec["name"]
            op = str(spec.get("op") or spec.get("operation") or "sum").strip().lower()
            try:
                if op == "sum":
                    col = str(spec.get("column") or spec.get("col") or "").strip()
                    if not col or col not in gdf.columns:
                        raise ValueError(f"aggregations[{name}]: column not found: {col!r}")
                    results[name] = float(_agg_column_series(gdf, col).sum())
                elif op == "count":
                    results[name] = float(len(gdf))
                elif op == "min":
                    col = str(spec.get("column") or spec.get("col") or "").strip()
                    results[name] = float(_agg_column_series(gdf, col).min())
                elif op == "max":
                    col = str(spec.get("column") or spec.get("col") or "").strip()
                    results[name] = float(_agg_column_series(gdf, col).max())
                elif op in ("avg", "mean"):
                    col = str(spec.get("column") or spec.get("col") or "").strip()
                    results[name] = float(_agg_column_series(gdf, col).mean())
                elif op in ("join", "concat", "concatenate", "list"):
                    col = str(spec.get("column") or spec.get("col") or "").strip()
                    if not col:
                        raise ValueError(f"aggregations[{name}]: column is required for op {op!r}")
                    results[name] = _agg_join_column(gdf, col, spec)
                elif op == "expr":
                    expr = str(spec.get("expression") or spec.get("expr") or "").strip()
                    env = {**results, **var_num}
                    results[name] = safe_eval_scalar_expr(expr, env)
                else:
                    raise ValueError(f"aggregations[{name}]: unknown op {op!r}")
            except ValueError as e:
                if op == "expr" and "unknown name" in str(e):
                    still.append(spec)
                    continue
                raise
            fmt = spec.get("format")
            if fmt and str(fmt).endswith("%") and isinstance(results[name], (int, float)):
                results[name] = float(format_scalar(float(results[name]), str(fmt)))
        pending = still
    if pending:
        names = ", ".join(s["name"] for s in pending)
        raise ValueError(f"aggregations: не удалось вычислить (зависимости?): {names}")
    out: dict[str, Any] = {}
    for spec in specs:
        name = spec["name"]
        val = results[name]
        fmt = spec.get("format")
        if isinstance(val, str):
            out[name] = val
        elif fmt and not str(fmt).endswith("%"):
            out[name] = format_scalar(float(val), str(fmt))
        else:
            out[name] = val
    return out


def _resolve_filename_params(
    p: dict[str, Any],
    group_part: str,
    *,
    inc: int | None = None,
    inc_position: str | None = None,
) -> str:
    fn = p.get("filename")
    prefix = str(p.get("prefix", "") or "")
    suffix = str(p.get("suffix", "") or "")
    extension = str(p.get("extension", ".xlsx") or ".xlsx")
    mask = str(p.get("filename_mask", "") or "")
    sep = str(p.get("group_separator", "_") or "_")

    if isinstance(fn, dict):
        prefix = str(fn.get("prefix", prefix) or "")
        suffix = str(fn.get("suffix", suffix) or "")
        extension = str(fn.get("extension", extension) or ".xlsx")
        mask = str(fn.get("mask", mask) or "")
        sep = str(fn.get("group_separator", sep) or "_")

    if isinstance(fn, str) and fn.strip():
        mask = fn.strip()

    return build_output_filename(
        prefix=prefix,
        suffix=suffix,
        group_part=group_part,
        extension=extension,
        mask=mask,
        inc=inc,
        inc_position=inc_position,
    )


def _parse_static_fields(raw: Any) -> list[dict[str, Any]]:
    if raw is None or raw == "" or raw == []:
        return []
    if not isinstance(raw, list):
        raise ValueError("static_fields must be a list")
    return [dict(x) for x in raw if isinstance(x, dict)]


def _parse_row_increment(p: dict[str, Any]) -> tuple[int | None, int]:
    ri = p.get("row_increment")
    if ri is None or ri is False or ri == "":
        if param_is_on(p.get("row_increment_enabled")):
            col = int(p.get("row_increment_col", 1))
            start = int(p.get("row_increment_start", 1))
            return col, start
        return None, 1
    if isinstance(ri, dict):
        if not param_is_on(ri.get("enabled", True)):
            return None, 1
        return int(ri.get("excel_col", ri.get("col", 1))), int(ri.get("start", 1))
    if param_is_on(ri):
        return int(p.get("row_increment_col", 1)), int(p.get("row_increment_start", 1))
    return None, 1


def _is_file_locked_error(e: BaseException) -> bool:
    if isinstance(e, PermissionError):
        return True
    if isinstance(e, OSError) and getattr(e, "winerror", None) == 32:
        return True
    return False


def _ask_retry_locked(ctx: RunContext, path: str, err: BaseException) -> bool:
    fn = ctx.variables.get("tk_askretrycancel")
    if not callable(fn):
        return False
    msg = f"Файл занят или недоступен:\n{path}\n\n{err}\n\nПовторить?"
    return bool(fn(title="ExcelForge — файл занят", message=msg))


def run_group_template_export(ctx: RunContext, step: Step) -> None:
    p = step.params
    apply_group_template_export_dialogs(ctx, p)

    source_df = str(get_required_param(p, "source_df"))
    template_path = str(get_required_param(p, "template_path")).strip()
    out_dir = str(get_required_param(p, "out_dir")).strip()

    if not os.path.isfile(template_path):
        raise FileNotFoundError(f"template_path not found: {template_path}")

    form_mode = _is_single_row_form_mode(p)
    filename_inc = _parse_filename_inc(p, form_mode)

    group_cols = _parse_group_by(p.get("group_by"))
    table_columns = parse_table_columns(p.get("table_columns"))
    aggregations = _parse_aggregations(p.get("aggregations"))
    static_fields = _parse_static_fields(p.get("static_fields"))

    sheet_name = str(p.get("sheet_name", "") or "").strip()
    table_start_row = _parse_table_start_row(p, form_mode=form_mode)
    table_template_row = _parse_table_template_row(p, table_start_row)
    skip_empty = param_is_on(p.get("skip_empty_groups", True))

    inc_col, inc_start = _parse_row_increment(p)

    df = ensure_df_exists(ctx.df_store, source_df)
    for col in group_cols:
        if col not in df.columns:
            raise ValueError(f"group_by column not found in {source_df}: {col}")

    row_filter = p.get("row_filter") or p.get("expression")
    if row_filter:
        if not isinstance(row_filter, dict):
            raise ValueError("row_filter must be a filtration expression dict")
        mask = eval_expression(df, row_filter)
        df = df.loc[mask].copy()

    sort_spec = p.get("sort_within_group")
    sort_col: str | None = None
    sort_asc = True
    if isinstance(sort_spec, dict):
        sort_col = str(sort_spec.get("column") or sort_spec.get("col") or "").strip() or None
        sort_asc = str(sort_spec.get("ascending", sort_spec.get("order", "asc"))).lower() not in (
            "desc",
            "descending",
            "false",
            "0",
        )
    elif isinstance(sort_spec, str) and sort_spec.strip():
        sort_col = sort_spec.strip()

    group_sep = str(p.get("group_separator", "_") or "_")
    if isinstance(p.get("filename"), dict):
        group_sep = str(p["filename"].get("group_separator", group_sep) or group_sep)

    var_values: dict[str, Any] = {}
    for k, v in ctx.variables.items():
        if k.startswith("_") or k.startswith("tk_"):
            continue
        key = str(k).lstrip("@")
        var_values[key] = v

    os.makedirs(out_dir, exist_ok=True)
    files_written = 0

    grouped = df.groupby(group_cols, dropna=False, sort=True)
    for group_key, gdf in grouped:
        if len(gdf) == 0 and skip_empty:
            ctx.logger.warn(f"group_template_export: skip empty group {group_key!r}")
            continue

        gdf_work = gdf
        if sort_col:
            if sort_col not in gdf_work.columns:
                raise ValueError(f"sort_within_group column not found: {sort_col}")
            gdf_work = gdf_work.sort_values(by=sort_col, ascending=sort_asc, kind="stable")

        group_part = group_key_to_str(group_key, group_cols, separator=group_sep)

        if len(group_cols) == 1:
            k0 = group_key[0] if isinstance(group_key, tuple) else group_key
            group_values = {group_cols[0]: k0}
        else:
            keys = group_key if isinstance(group_key, tuple) else (group_key,)
            group_values = {col: keys[i] if i < len(keys) else "" for i, col in enumerate(group_cols)}

        rows = gdf_work.where(pd.notnull(gdf_work), None).to_dict("records")

        if form_mode:
            for i, row_dict in enumerate(rows):
                inc_num = i + 1
                out_name = _resolve_filename_params(
                    p,
                    group_part,
                    inc=inc_num,
                    inc_position=filename_inc,
                )
                out_path = os.path.join(out_dir, out_name)
                row_df = gdf_work.iloc[[i]]
                agg_values = _compute_aggregations(row_df, aggregations, ctx.variables)

                while True:
                    try:
                        write_form_row_to_template(
                            template_path=template_path,
                            out_path=out_path,
                            sheet_name=sheet_name,
                            group_values=group_values,
                            agg_values=agg_values,
                            var_values=var_values,
                            row_data=row_dict,
                            static_fields=static_fields,
                            inc=inc_num,
                        )
                        break
                    except Exception as e:  # noqa: BLE001
                        if _is_file_locked_error(e) and _ask_retry_locked(ctx, out_path, e):
                            continue
                        raise

                files_written += 1
                ctx.logger.info(
                    f"group_template_export: {out_path} group={group_part!r} row={i + 1}/{len(rows)}"
                )
            continue

        out_name = _resolve_filename_params(p, group_part)
        out_path = os.path.join(out_dir, out_name)
        agg_values = _compute_aggregations(gdf_work, aggregations, ctx.variables)

        while True:
            try:
                write_group_to_template(
                    template_path=template_path,
                    out_path=out_path,
                    sheet_name=sheet_name,
                    table_start_row=table_start_row,
                    table_template_row=table_template_row,
                    table_columns=table_columns,
                    group_df_rows=rows,
                    group_values=group_values,
                    agg_values=agg_values,
                    var_values=var_values,
                    static_fields=static_fields,
                    row_increment_col=inc_col,
                    row_increment_start=inc_start,
                )
                break
            except Exception as e:  # noqa: BLE001
                if _is_file_locked_error(e) and _ask_retry_locked(ctx, out_path, e):
                    continue
                raise

        files_written += 1
        ctx.logger.info(
            f"group_template_export: {out_path} group={group_part!r} rows={len(gdf_work)}"
        )

    ctx.logger.info(f"group_template_export: done, files={files_written}, out_dir={out_dir}")


def register_group_template_export() -> None:
    REGISTRY.register(
        StepDefinition(
            type="group_template_export",
            title="Групповой вывод по шаблону (Excel)",
            runner=run_group_template_export,
            default_params={
                "source_df": "df_main",
                "group_by": "Группа",
                "group_separator": "_",
                "out_dir": "",
                "template_path": "",
                "filename": {
                    "prefix": "",
                    "suffix": "",
                    "extension": ".xlsx",
                },
                "filename_mask": "",
                "prefix": "",
                "suffix": "",
                "extension": ".xlsx",
                "sheet_name": "",
                "table_start_row": "",
                "table_template_row": "",
                "table_columns": [],
                "single_row_mode": False,
                "filename_inc": "prefix",
                "static_fields": [],
                "aggregations": [],
                "row_increment": {
                    "enabled": True,
                    "excel_col": 1,
                    "start": 1,
                },
                "row_filter": {},
                "sort_within_group": {},
                "skip_empty_groups": True,
                "directory_open_dialog": False,
                "directory_open_dialog_help": "Выберите каталог для сохранения файлов",
                "template_open_dialog": False,
                "template_open_dialog_help": "Выберите Excel-шаблон",
            },
        )
    )
