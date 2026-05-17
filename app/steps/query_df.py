from __future__ import annotations

import re
from typing import Any, Literal

import pandas as pd

from app.pipeline.context import RunContext
from app.pipeline.registry import REGISTRY, StepDefinition
from app.pipeline.schema import Step
from app.steps.util import ensure_df_exists, get_required_param

ColumnRefMode = Literal["names", "positions"]


def _normalize_column_reference(raw: object) -> ColumnRefMode:
    s = str(raw or "names").strip().lower()
    if s in ("names", "name", "columns"):
        return "names"
    if s in ("positions", "position", "indices", "index"):
        return "positions"
    raise ValueError(
        "query: column_reference должен быть names (имена столбцов) или positions "
        f"(индекс столбца с 1 слева направо); получено: {raw!r}"
    )


def _resolve_filter_column(df: pd.DataFrame, col_spec: object) -> str:
    """Имя столбца по строке или по номеру позиции с 1 (как в ExcelForge)."""
    if isinstance(col_spec, bool):
        raise ValueError(f"string_filters: недопустимый column: {col_spec!r}")
    if isinstance(col_spec, int):
        idx = col_spec - 1
        if idx < 0 or idx >= df.shape[1]:
            raise ValueError(
                f"string_filters: column={col_spec} вне диапазона позиций (1..{df.shape[1]})"
            )
        return str(df.columns[idx])
    name = str(col_spec).strip()
    if name not in df.columns:
        raise ValueError(f"string_filters: столбец не найден: {name!r}")
    return name


def _string_filter_mask(series: pd.Series, filt: dict[str, Any]) -> pd.Series:
    mode = str(filt.get("mode", "contains")).strip().lower()
    pattern = filt.get("pattern")
    if pattern is None:
        raise ValueError("string_filters: для каждого элемента нужен pattern")
    pattern_str = str(pattern)
    na_match = bool(filt.get("na", False))
    case_insensitive = bool(filt.get("case_insensitive", False))

    s = series.astype("string")

    if mode == "contains":
        if case_insensitive:
            sub = pattern_str.lower()
            return s.str.lower().str.contains(sub, regex=False, na=na_match)
        return s.str.contains(pattern_str, regex=False, na=na_match)

    if mode == "regex":
        flags = re.IGNORECASE if case_insensitive else 0
        return s.str.contains(pattern_str, regex=True, flags=flags, na=na_match)

    if mode == "startswith":
        if case_insensitive:
            return s.str.lower().str.startswith(pattern_str.lower(), na=na_match)
        return s.str.startswith(pattern_str, na=na_match)

    if mode == "endswith":
        if case_insensitive:
            return s.str.lower().str.endswith(pattern_str.lower(), na=na_match)
        return s.str.endswith(pattern_str, na=na_match)

    raise ValueError(
        "string_filters: mode должен быть contains, regex, startswith или endswith; "
        f"получено: {mode!r}"
    )


def _parse_string_filters(df: pd.DataFrame, raw: object) -> dict[str, pd.Series]:
    """
    Строит булевы маски по строковым фильтрам и кладёт их в словарь для local_dict query().
    Ключи: __sf0, __sf1, … и объединение по AND — __sf_all.
    """
    if raw is None:
        return {}
    if not isinstance(raw, list):
        raise ValueError("string_filters должен быть списком условий или отсутствовать")
    if not raw:
        return {}

    locals_dict: dict[str, pd.Series] = {}
    combined: pd.Series | None = None
    idx = 0
    for item in raw:
        if not isinstance(item, dict):
            raise ValueError("string_filters: каждый элемент должен быть словарём (mapping)")
        col_name = _resolve_filter_column(df, item.get("column"))
        mask = _string_filter_mask(df[col_name], item)
        key = f"__sf{idx}"
        na_fill = bool(item.get("na", False))
        locals_dict[key] = mask.fillna(True if na_fill else False)
        combined = locals_dict[key] if combined is None else combined & locals_dict[key]
        idx += 1

    if combined is None:
        return {}
    locals_dict["__sf_all"] = combined
    return locals_dict


def _parse_query_variables(raw: object) -> dict[str, Any]:
    """
    Переменные для DataFrame.query, доступные через @имя_переменной.

    Формат: словарь {name: value}. value может быть строкой, числом, bool,
    YAML-списком (для isin), или строкой со значениями через запятую.
    """
    if raw is None:
        return {}
    if isinstance(raw, dict) and not raw:
        return {}
    if not isinstance(raw, dict):
        raise ValueError("query_variables должен быть словарём {name: value} или отсутствовать")

    out: dict[str, Any] = {}
    for k, v in raw.items():
        name = str(k).strip()
        if not name:
            raise ValueError("query_variables: пустое имя переменной недопустимо")
        if name.startswith("__sf"):
            raise ValueError("query_variables: имена, начинающиеся с __sf, зарезервированы")
        if isinstance(v, str):
            s = v.strip()
            # Удобная запись списков для isin: "A,C,E"
            if "," in s:
                out[name] = [p.strip() for p in s.split(",") if p.strip() != ""]
            else:
                out[name] = s
        else:
            out[name] = v
    return out


def _build_query_expression(qtext: str, local_dict: dict[str, pd.Series]) -> str:
    has_sf = bool(local_dict)
    if not has_sf:
        qt = qtext.strip()
        if not qt:
            raise ValueError(
                "query: задайте непустой текст в query или хотя бы одно условие в string_filters"
            )
        return qt

    qt = qtext.strip()
    if not qt:
        return "@__sf_all"
    # Явное использование масок (@__sf0, @__sf_all, …) — объединение задаёт автор запроса.
    if "__sf" in qt:
        return qt
    return f"({qt}) & (@__sf_all)"


def run_query_df(ctx: RunContext, step: Step) -> None:
    p = step.params
    source_name = str(get_required_param(p, "source_df"))
    target_name = str(get_required_param(p, "target_df"))
    qtext = str(p.get("query", "") or "").strip()

    mode = _normalize_column_reference(p.get("column_reference", "names"))
    df = ensure_df_exists(ctx.df_store, source_name).copy()
    before = len(df)

    local_dict = _parse_string_filters(df, p.get("string_filters"))
    query_vars = _parse_query_variables(p.get("query_variables"))
    for k in query_vars:
        if k in local_dict:
            raise ValueError(f"query_variables конфликтует с внутренним ключом: {k}")
    if query_vars:
        local_dict = {**local_dict, **query_vars} if local_dict else dict(query_vars)

    sf_only = {k: v for k, v in local_dict.items() if str(k).startswith("__sf")}
    expr = _build_query_expression(qtext, sf_only)

    query_kw: dict[str, Any] = {}
    if local_dict:
        query_kw["local_dict"] = local_dict
        query_kw["engine"] = "python"

    if mode == "positions":
        cols = list(df.columns)
        rename_map = {orig: f"col_{i}" for i, orig in enumerate(cols, start=1)}
        reverse_map = {v: k for k, v in rename_map.items()}
        df_work = df.rename(columns=rename_map)
        try:
            out = df_work.query(expr, **query_kw)
        except Exception as e:
            raise ValueError(
                "query: ошибка выполнения запроса в режиме positions "
                "(строка query: имена col_1, col_2, …; строковые фильтры — по реальным столбцам). "
                f"Исходное сообщение: {e}"
            ) from e
        out = out.rename(columns=reverse_map)
    else:
        try:
            out = df.query(expr, **query_kw)
        except Exception as e:
            raise ValueError(
                "query: ошибка выполнения запроса (режим имён столбцов). "
                "Столбцы с пробелами — в обратных кавычках pandas; "
                "строковые условия задавайте через string_filters (подстрока / regex и т.д.). "
                f"Исходное сообщение: {e}"
            ) from e

    ctx.df_store[target_name] = out
    after = len(out)
    n_sf = sum(1 for k in local_dict if str(k).startswith("__sf") and k != "__sf_all") if local_dict else 0
    n_vars = sum(1 for k in local_dict if not str(k).startswith("__sf")) if local_dict else 0
    sf_info = f", string_filters={n_sf}" if n_sf else ""
    var_info = f", query_variables={n_vars}" if n_vars else ""
    ctx.logger.info(
        f"query: {source_name} rows={before} -> {target_name} rows={after} "
        f"(column_reference={mode}{sf_info}{var_info})"
    )


def register_query_df() -> None:
    REGISTRY.register(
        StepDefinition(
            type="query",
            title="Запросы к датафреймам",
            runner=run_query_df,
            default_params={
                "source_df": "df_main",
                "target_df": "df_main",
                "query": "",
                "column_reference": "names",
                "string_filters": [],
                "query_variables": {},
            },
        )
    )
