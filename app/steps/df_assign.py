from __future__ import annotations

from typing import Any

import pandas as pd

from app.pipeline.context import RunContext
from app.pipeline.registry import REGISTRY, StepDefinition
from app.pipeline.schema import Step
from app.steps.util import ensure_df_exists, get_required_param


def _concat_column_source_names(p: dict[str, Any]) -> list[str]:
    """
    Список столбцов для склейки: при непустом source_columns — он;
    иначе один столбец source_column (обратная совместимость).
    """
    raw = p.get("source_columns")
    if raw is not None:
        if isinstance(raw, list):
            names = [str(x).strip() for x in raw if str(x).strip() != ""]
            if names:
                return names
        elif isinstance(raw, str) and raw.strip():
            return [raw.strip()]
    col_one = p.get("source_column")
    if col_one is None or str(col_one).strip() == "":
        # Допускаем отсутствие источника: тогда используется только prefix+suffix
        # (а если оба пустые — записывается NaN).
        return []
    return [str(col_one).strip()]


def _map_lookup_cols_param(raw: Any, param: str) -> list[str]:
    """Одно имя столбца (строка) или YAML-список имён; пустые элементы отбрасываются."""
    if raw is None:
        raise ValueError(f"map_lookup: требуется параметр {param}")
    if isinstance(raw, list):
        out = [str(x).strip() for x in raw if str(x).strip() != ""]
        if not out:
            raise ValueError(f"map_lookup: {param} — непустой список имён столбцов")
        return out
    s = str(raw).strip()
    if not s:
        raise ValueError(f"map_lookup: {param} не может быть пустым")
    return [s]


def _series_is_empty_mask(s: pd.Series, treat_whitespace: bool) -> pd.Series:
    """Пустота: NaN/NA; для строк — опционально только пробелы."""
    if (
        pd.api.types.is_numeric_dtype(s)
        or pd.api.types.is_bool_dtype(s)
        or pd.api.types.is_datetime64_any_dtype(s)
    ):
        return pd.isna(s)
    strv = s.astype("string")
    m = strv.isna()
    if treat_whitespace:
        m = m | (strv.str.strip() == "")
    else:
        m = m | (strv == "") | (strv == "<NA>")
    return m


def _parse_transform_spec(raw: Any) -> dict[str, Any]:
    """transform: строка (тип) или dict с полями type и params."""
    if raw is None:
        raise ValueError("apply_transform: задайте transform (строка type или dict)")
    if isinstance(raw, str):
        t = raw.strip().lower()
        if not t:
            raise ValueError("apply_transform: пустой type в transform")
        return {"type": t, "params": {}}
    if isinstance(raw, dict):
        t = str(raw.get("type", "")).strip().lower()
        if not t:
            raise ValueError("apply_transform: в transform нужен ключ type")
        par = raw.get("params")
        if par is None:
            par = {}
        elif not isinstance(par, dict):
            raise ValueError("apply_transform: transform.params должен быть словарём")
        return {"type": t, "params": par}
    raise ValueError("apply_transform: transform должен быть строкой или словарём")


def _eval_row_mask(df: pd.DataFrame, expr: str) -> pd.Series:
    expr = str(expr).strip()
    if not expr:
        return pd.Series(True, index=df.index)
    try:
        res = df.eval(expr, engine="python")
    except Exception as e:  # noqa: BLE001
        raise ValueError(f"apply_transform: не удалось вычислить condition: {e}") from e
    if isinstance(res, bool):
        return pd.Series([res] * len(df), index=df.index, dtype=bool)
    if isinstance(res, pd.Series):
        return res.fillna(False).astype(bool)
    raise ValueError("apply_transform: condition должно давать булеву маску (Series или bool)")


def _apply_transform_to_series(s: pd.Series, spec: dict[str, Any]) -> pd.Series:
    t = spec["type"]
    par: dict[str, Any] = spec["params"]
    ser = s.astype("string")

    if t == "split_first_word":
        delim = str(par.get("delimiter", " ") or " ")
        part = ser.str.split(delim, n=1).str[0]
        return part

    if t == "split_last_word":
        delim = str(par.get("delimiter", " ") or " ")
        return ser.str.split(delim).str[-1]

    if t == "regex_extract":
        pat = par.get("pattern") or par.get("regex")
        if pat is None or str(pat).strip() == "":
            raise ValueError("apply_transform: для regex_extract задайте params.pattern")
        return ser.str.extract(str(pat), expand=False)

    if t == "replace_map":
        mp = par.get("map") or par.get("replacements")
        if not isinstance(mp, dict) or not mp:
            raise ValueError("apply_transform: для replace_map задайте params.map (объект ключ→значение)")
        out = ser
        for old, new in mp.items():
            out = out.str.replace(str(old), str(new), regex=False)
        return out

    if t == "static_value":
        val = par.get("value")
        if "value" not in par:
            raise ValueError("apply_transform: для static_value задайте params.value")
        return pd.Series([val] * len(s), index=s.index, dtype=object)

    if t in ("as_string", "string", "text"):
        return ser

    raise ValueError(
        f"apply_transform: неизвестный transform.type {t!r}. "
        "Доступно: split_first_word, split_last_word, regex_extract, replace_map, static_value, as_string"
    )


def run_df_assign(ctx: RunContext, step: Step) -> None:
    p = step.params
    op = str(p.get("operation", "concat_column")).strip().lower()
    src_name = str(get_required_param(p, "source_df"))
    tgt_name = str(p.get("target_df") or src_name).strip() or src_name

    src = ensure_df_exists(ctx.df_store, src_name)
    work = src if tgt_name == src_name else src.copy()

    if op == "concat_column":
        col_out = str(get_required_param(p, "target_column"))
        source_cols = _concat_column_source_names(p)
        prefix = str(p.get("prefix", "") or "")
        suffix = str(p.get("suffix", "") or "")
        if source_cols:
            missing = [c for c in source_cols if c not in work.columns]
            if missing:
                raise ValueError(f"Column(s) not found in {src_name}: {missing}")
            parts = [work[c].astype("string").fillna("") for c in source_cols]
            acc = parts[0]
            for ser in parts[1:]:
                acc = acc + ser
            work[col_out] = prefix + acc + suffix
            cols_repr = ",".join(source_cols)
        else:
            # Нет исходных столбцов: пишем prefix+suffix; если оба пустые — NaN.
            if prefix == "" and suffix == "":
                work[col_out] = pd.NA
            else:
                work[col_out] = prefix + suffix
            cols_repr = "(no source columns)"
        ctx.logger.info(
            f"df_assign concat_column: {src_name} -> {tgt_name}, "
            f"{col_out} = prefix+[{cols_repr}]+suffix"
        )

    elif op == "select_columns":
        mode = str(p.get("column_mode", "names")).strip().lower()
        cols = p.get("columns") or []
        if not isinstance(cols, list) or not cols:
            raise ValueError("select_columns: params.columns must be a non-empty list")
        if mode == "positions":
            idx0: list[int] = []
            for x in cols:
                idx0.append(int(x) - 1)
            n = work.shape[1]
            for i in idx0:
                if i < 0 or i >= n:
                    raise ValueError(
                        f"Column position {i + 1} (1-based) out of range; "
                        f"dataframe has {n} column(s)."
                    )
            out = work.iloc[:, idx0].copy()
        elif mode == "names":
            names = [str(c) for c in cols]
            miss = [c for c in names if c not in work.columns]
            if miss:
                raise ValueError(f"Columns not found in {src_name}: {miss}")
            out = work[names].copy()
        else:
            raise ValueError("column_mode must be 'names' or 'positions'")
        work = out
        ctx.logger.info(
            f"df_assign select_columns: {src_name} -> {tgt_name}, "
            f"mode={mode}, n_cols={work.shape[1]}"
        )

    elif op == "map_lookup":
        lk_name = str(get_required_param(p, "lookup_df"))
        lk = ensure_df_exists(ctx.df_store, lk_name)
        source_key = str(get_required_param(p, "source_key"))
        lookup_key = str(get_required_param(p, "lookup_key"))
        val_cols = _map_lookup_cols_param(p.get("lookup_value_column"), "lookup_value_column")
        target_cols = _map_lookup_cols_param(p.get("target_column"), "target_column")

        if len(val_cols) != len(target_cols):
            raise ValueError(
                "map_lookup: число элементов lookup_value_column и target_column должно совпадать "
                f"(сейчас {len(val_cols)} и {len(target_cols)})"
            )

        if source_key not in work.columns:
            raise ValueError(f"Column not found in {src_name}: {source_key}")
        if lookup_key not in lk.columns:
            raise ValueError(f"Column not found in {lk_name}: {lookup_key}")

        dedup = lk.drop_duplicates(subset=[lookup_key], keep="last")
        pairs_desc: list[str] = []
        for val_col, tcol in zip(val_cols, target_cols):
            if val_col not in lk.columns:
                raise ValueError(f"Column not found in {lk_name}: {val_col}")
            mp = dedup.set_index(lookup_key)[val_col]
            work[tcol] = work[source_key].map(mp)
            pairs_desc.append(f"{val_col}→{tcol}")

        ctx.logger.info(
            f"df_assign map_lookup: {src_name}[{source_key}] <- {lk_name}[{lookup_key}: "
            f"{', '.join(pairs_desc)}] -> {tgt_name}"
        )

    elif op == "drop_empty":
        subset = p.get("subset") or p.get("columns") or []
        if isinstance(subset, str):
            subset = [subset]
        if not isinstance(subset, list) or not subset:
            raise ValueError("drop_empty: задайте subset или columns — список имён столбцов")
        subset = [str(x) for x in subset]
        for c in subset:
            if c not in work.columns:
                raise ValueError(f"Column not found in {src_name}: {c}")
        how = str(p.get("how", "any")).strip().lower()
        treat_ws = bool(p.get("treat_whitespace_as_empty", True))
        masks = [_series_is_empty_mask(work[c], treat_ws) for c in subset]
        if how == "all":
            row_drop = masks[0]
            for m in masks[1:]:
                row_drop = row_drop & m
        elif how == "any":
            row_drop = masks[0]
            for m in masks[1:]:
                row_drop = row_drop | m
        else:
            raise ValueError("drop_empty: how must be 'any' or 'all'")
        n0 = len(work)
        work = work.loc[~row_drop].copy()
        ctx.logger.info(
            f"df_assign drop_empty: {src_name} -> {tgt_name}, rows {n0} -> {len(work)}, "
            f"subset={subset}, how={how}"
        )

    elif op == "fill_empty":
        if "fill_value" not in p:
            raise ValueError("fill_empty: требуется параметр fill_value")
        fv = p["fill_value"]
        scope = str(p.get("scope", "listed")).strip().lower()
        treat_ws = bool(p.get("treat_whitespace_as_empty", True))
        if scope in ("all", "all_columns"):
            col_list = [str(c) for c in work.columns]
        elif scope == "listed":
            col_list = p.get("columns") or []
            if not isinstance(col_list, list) or not col_list:
                raise ValueError("fill_empty: при scope=listed задайте непустой список columns")
            col_list = [str(c) for c in col_list]
        else:
            raise ValueError("fill_empty: scope must be 'listed' or 'all_columns'")
        for c in col_list:
            if c not in work.columns:
                raise ValueError(f"Column not found in {src_name}: {c}")
            m = _series_is_empty_mask(work[c], treat_ws)
            if m.any():
                work.loc[m, c] = fv
        ctx.logger.info(
            f"df_assign fill_empty: {src_name} -> {tgt_name}, columns={len(col_list)}, scope={scope}"
        )

    elif op in ("calc_column", "compute_column"):
        col_out = str(get_required_param(p, "target_column"))
        expr = str(get_required_param(p, "expression") or "").strip()
        if not expr:
            raise ValueError("calc_column: expression must be a non-empty string")
        value_type = str(p.get("value_type", "decimal")).strip().lower()
        if value_type not in ("int", "decimal"):
            raise ValueError("calc_column: value_type must be int or decimal")

        # Optional: only coerce specified columns; otherwise coerce all columns.
        raw_cols = p.get("calc_columns")
        if raw_cols is None or raw_cols == [] or raw_cols == "":
            cols_to_coerce = [str(c) for c in work.columns]
        elif isinstance(raw_cols, str):
            cols_to_coerce = [x.strip() for x in raw_cols.split(",") if x.strip()]
        elif isinstance(raw_cols, list):
            cols_to_coerce = [str(x).strip() for x in raw_cols if str(x).strip() != ""]
        else:
            raise ValueError("calc_column: calc_columns must be list or comma-separated string")

        local_dict: dict[str, pd.Series] = {}
        for c in cols_to_coerce:
            if c not in work.columns:
                raise ValueError(f"calc_column: column not found: {c}")
            local_dict[c] = pd.to_numeric(work[c], errors="coerce").fillna(0)

        # Ensure target column can be referenced too (if exists or will be created).
        if col_out not in local_dict:
            if col_out in work.columns:
                local_dict[col_out] = pd.to_numeric(work[col_out], errors="coerce").fillna(0)
            else:
                local_dict[col_out] = pd.Series([0] * len(work), index=work.index)

        try:
            res = pd.eval(expr, engine="python", local_dict=local_dict)
        except Exception as e:  # noqa: BLE001
            raise ValueError(f"calc_column: expression eval failed: {e}") from e

        if not isinstance(res, pd.Series):
            # allow scalar result -> broadcast
            res = pd.Series([res] * len(work), index=work.index)

        res = pd.to_numeric(res, errors="coerce").fillna(0)
        if value_type == "int":
            work[col_out] = res.astype("int64", errors="ignore")
        else:
            work[col_out] = res.astype("float64", errors="ignore")

        ctx.logger.info(
            f"df_assign calc_column: {src_name} -> {tgt_name}, {col_out} = {expr} (type={value_type})"
        )

    elif op in ("apply_transform", "conditional_assign"):
        tgt_col = str(get_required_param(p, "target_column"))
        spec = _parse_transform_spec(p.get("transform"))
        tname = spec["type"]

        src_raw = p.get("source_column")
        if src_raw is None or str(src_raw).strip() == "":
            if tname == "static_value":
                src_col: str | None = None
            else:
                src_col = tgt_col
        else:
            src_col = str(src_raw).strip()

        if src_col is not None and src_col not in work.columns:
            raise ValueError(f"apply_transform: столбец не найден в {src_name}: {src_col}")

        cond_raw = p.get("condition")
        if cond_raw is None or str(cond_raw).strip() == "":
            mask = pd.Series(True, index=work.index)
            has_cond = False
        else:
            mask = _eval_row_mask(work, str(cond_raw))
            has_cond = True

        if tname == "static_value":
            transformed = _apply_transform_to_series(
                pd.Series(pd.NA, index=work.index, dtype="string"), spec
            )
        else:
            if src_col is None:
                raise ValueError("apply_transform: укажите source_column")
            transformed = _apply_transform_to_series(work[src_col], spec)

        if tgt_col not in work.columns:
            work[tgt_col] = pd.Series(pd.NA, index=work.index, dtype=object)

        work.loc[mask, tgt_col] = transformed.loc[mask].to_numpy()

        if has_cond and "fill_unmatched_rows_with" in p:
            fu = p["fill_unmatched_rows_with"]
            work.loc[~mask, tgt_col] = fu

        if bool(p.get("coerce_to_numeric_on_error", False)):
            work[tgt_col] = pd.to_numeric(work[tgt_col], errors="coerce").fillna(0)

        ctx.logger.info(
            f"df_assign apply_transform: {src_name} -> {tgt_name}, "
            f"{tgt_col} <- transform={tname}"
            + (f", condition set" if has_cond else "")
        )

    else:
        raise ValueError(
            f"Unknown operation: {op!r}. Use concat_column, select_columns, map_lookup, "
            "drop_empty, fill_empty, calc_column, apply_transform."
        )

    ctx.df_store[tgt_name] = work


def register_df_assign() -> None:
    REGISTRY.register(
        StepDefinition(
            type="df_assign",
            title="Операции с DF (столбец, выбор, подстановка, пустые)",
            runner=run_df_assign,
            default_params={
                "operation": "concat_column",
                "source_df": "df_main",
                "target_df": "df_main",
                # concat_column
                "target_column": "new_col",
                "source_column": "OLD",
                "source_columns": [],
                "prefix": "",
                "suffix": "",
                # calc_column
                "expression": "",
                "value_type": "decimal",  # int|decimal
                "calc_columns": [],
                # apply_transform
                "condition": "",
                "transform": {"type": "split_first_word", "params": {"delimiter": " "}},
                "coerce_to_numeric_on_error": False,
                # select_columns
                "column_mode": "names",
                "columns": [],
                # map_lookup
                "lookup_df": "df_lookup",
                "source_key": "",
                "lookup_key": "",
                "lookup_value_column": "",
                # drop_empty
                "subset": [],
                "how": "any",
                "treat_whitespace_as_empty": True,
                # fill_empty
                "fill_value": "",
                "scope": "listed",
            },
        )
    )
