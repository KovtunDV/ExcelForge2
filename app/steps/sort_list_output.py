from __future__ import annotations

from typing import Any

import pandas as pd

from app.pipeline.context import RunContext
from app.pipeline.registry import REGISTRY, StepDefinition
from app.pipeline.schema import Step
from app.steps.util import ensure_df_exists, get_required_param


def _yaml_bool(val: Any, default: bool = True) -> bool:
    """Нормализация YAML-подобных bool: true/on/yes/1 vs false/off/no/0."""
    if val is None:
        return default
    if val is True:
        return True
    if val is False:
        return False
    if isinstance(val, (int, float)):
        return bool(int(val))
    s = str(val).strip().lower()
    if s in ("1", "true", "yes", "on", "y"):
        return True
    if s in ("0", "false", "no", "off", "n"):
        return False
    return default


def _parse_unique_subset(raw: Any) -> list[str] | None:
    """
    Подмножество столбцов для drop_duplicates: одна строка, строка через запятую
    или YAML-список имён.
    """
    if raw is None:
        return None
    if isinstance(raw, list):
        out = [str(x).strip() for x in raw if str(x).strip() != ""]
        return out or None
    s = str(raw).strip()
    if not s:
        return None
    if "," in s:
        parts = [p.strip() for p in s.split(",") if p.strip()]
        return parts or None
    return [s]


def _parse_sort_rules(raw: Any) -> tuple[list[str], list[bool]] | None:
    if raw is None:
        return None
    # allow single mapping as a single rule: sort: {column: ..., ascending: ...}
    if isinstance(raw, dict):
        raw = [raw]
    if isinstance(raw, list) and not raw:
        return None
    if not isinstance(raw, list):
        raise ValueError("sort_list_output: sort должен быть списком правил или пустым")

    cols: list[str] = []
    ascending: list[bool] = []
    for i, rule in enumerate(raw):
        if isinstance(rule, str):
            c = rule.strip()
            if not c:
                continue
            cols.append(c)
            ascending.append(True)
        elif isinstance(rule, dict):
            # Support single column or multiple columns per rule.
            c = rule.get("column") or rule.get("col")
            c_list = rule.get("columns") or rule.get("by") or rule.get("cols")
            if c is None and c_list is None:
                raise ValueError(
                    f"sort_list_output: sort[{i}] — укажите column или columns"
                )

            if c_list is not None:
                if isinstance(c_list, str):
                    col_names = [x.strip() for x in c_list.split(",") if x.strip()]
                elif isinstance(c_list, list):
                    col_names = [str(x).strip() for x in c_list if str(x).strip() != ""]
                else:
                    raise ValueError(
                        f"sort_list_output: sort[{i}].columns должен быть списком или строкой"
                    )
                if not col_names:
                    raise ValueError(f"sort_list_output: sort[{i}].columns пуст")

                asc_raw = rule.get("ascending", True)
                if isinstance(asc_raw, list):
                    asc_list = [_yaml_bool(x, True) for x in asc_raw]
                    if len(asc_list) != len(col_names):
                        raise ValueError(
                            f"sort_list_output: sort[{i}] — длина ascending должна совпадать с columns "
                            f"({len(asc_list)} != {len(col_names)})"
                        )
                else:
                    asc_list = [_yaml_bool(asc_raw, True)] * len(col_names)

                cols.extend(col_names)
                ascending.extend(asc_list)
            else:
                if c is None or str(c).strip() == "":
                    raise ValueError(f"sort_list_output: sort[{i}] — укажите column")
                cols.append(str(c).strip())
                ascending.append(_yaml_bool(rule.get("ascending"), True))
        else:
            raise ValueError(f"sort_list_output: sort[{i}] — строка с именем столбца или словарь")

    if not cols:
        return None
    return cols, ascending


def _parse_global_ascending(raw: Any, n: int) -> list[bool] | None:
    """
    Поддержка общего параметра ascending на верхнем уровне шага:
    - bool/строка/число -> одно значение на все n колонок
    - список -> по каждой колонке (длина должна совпасть с n)
    """
    if raw is None:
        return None
    if isinstance(raw, list):
        asc_list = [_yaml_bool(x, True) for x in raw]
        if len(asc_list) != n:
            raise ValueError(
                f"sort_list_output: ascending list length must match number of sort columns "
                f"({len(asc_list)} != {n})"
            )
        return asc_list
    return [_yaml_bool(raw, True)] * n


def _apply_list_filter(
    work: pd.DataFrame,
    ctx: RunContext,
    lf: dict[str, Any],
) -> pd.DataFrame:
    if lf.get("enabled") is False:
        return work

    ref_name = (
        lf.get("values_df")
        or lf.get("reference_df")
        or lf.get("list_df")
        or lf.get("list_source_df")
    )
    val_col = lf.get("values_column") or lf.get("list_column") or lf.get("column")
    match_col = lf.get("match_column") or lf.get("filter_column") or lf.get("target_column")
    mode = str(lf.get("mode", "in")).strip().lower()

    if ref_name is None or val_col is None or match_col is None:
        raise ValueError(
            "sort_list_output: в list_filter нужны values_df (или reference_df / list_df), "
            "values_column (или list_column / column) и match_column (или filter_column)"
        )

    ref_name = str(ref_name).strip()
    val_col = str(val_col).strip()
    match_col = str(match_col).strip()

    if mode not in ("in", "not_in"):
        raise ValueError("sort_list_output: list_filter.mode должен быть in или not_in")

    ref = ensure_df_exists(ctx.df_store, ref_name)
    if val_col not in ref.columns:
        raise ValueError(f"sort_list_output: столбец не найден в {ref_name!r}: {val_col!r}")
    if match_col not in work.columns:
        raise ValueError(f"sort_list_output: столбец не найден в данных: {match_col!r}")

    values = ref[val_col].dropna().unique()
    value_set = set(values)

    if mode == "in":
        mask = work[match_col].isin(value_set)
    else:
        mask = ~work[match_col].isin(value_set)

    return work.loc[mask].copy()


def run_sort_list_output(ctx: RunContext, step: Step) -> None:
    p = step.params
    source_name = str(get_required_param(p, "source_df"))
    target_name = str(get_required_param(p, "target_df"))

    df = ensure_df_exists(ctx.df_store, source_name)
    work = df.copy()
    before = len(work)

    sort_parsed = _parse_sort_rules(p.get("sort"))
    if sort_parsed is not None:
        cols, ascending = sort_parsed
        # Back-compat: allow top-level ascending applying to whole sort list.
        if "ascending" in p and p.get("ascending") is not None:
            ascending = _parse_global_ascending(p.get("ascending"), len(cols)) or ascending
        for c in cols:
            if c not in work.columns:
                raise ValueError(f"sort_list_output: столбец для сортировки не найден: {c!r}")
        work = work.sort_values(by=cols, ascending=ascending, kind="mergesort")

    lf_raw = p.get("list_filter")
    if lf_raw is not None and lf_raw != {}:
        if not isinstance(lf_raw, dict):
            raise ValueError("sort_list_output: list_filter должен быть словарём или пустым")
        work = _apply_list_filter(work, ctx, lf_raw)

    raw_unique = p.get("unique_by_column")
    if raw_unique in (None, "", []):
        raw_unique = p.get("unique_by_columns")
    uniq_cols = _parse_unique_subset(raw_unique)
    if uniq_cols:
        for c in uniq_cols:
            if c not in work.columns:
                raise ValueError(f"sort_list_output: unique_by_column — столбец не найден: {c!r}")
        keep = str(p.get("duplicate_keep", "first")).strip().lower()
        if keep not in ("first", "last", "false"):
            raise ValueError("sort_list_output: duplicate_keep — first, last или false")
        keep_arg: str | bool = False if keep == "false" else keep  # type: ignore[assignment]
        work = work.drop_duplicates(subset=uniq_cols, keep=keep_arg)

    ctx.df_store[target_name] = work
    after = len(work)
    ctx.logger.info(
        f"sort_list_output: {source_name} rows={before} -> {target_name} rows={after}"
    )


def register_sort_list_output() -> None:
    REGISTRY.register(
        StepDefinition(
            type="sort_list_output",
            title="Сортировка и вывод по списку",
            runner=run_sort_list_output,
            default_params={
                "source_df": "df_main",
                "target_df": "df_main",
                "sort": [],
                "list_filter": {},
                "unique_by_column": "",
                "unique_by_columns": [],
                "duplicate_keep": "first",
            },
        )
    )
