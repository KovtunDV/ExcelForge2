from __future__ import annotations

from typing import Any

import pandas as pd

from app.pipeline.context import RunContext
from app.pipeline.registry import REGISTRY, StepDefinition
from app.pipeline.schema import Step
from app.steps.series_lambda import resolve_lambda_expr
from app.steps.util import ensure_df_exists, get_required_param


def _coerce_agg_func(func: Any, params: dict[str, Any] | None = None, *, label: str = "") -> Any:
    custom = resolve_lambda_expr(func, params, label=label or "groupby_aggregate")
    if custom is not None:
        return custom
    if isinstance(func, str):
        return func.strip()
    return str(func).strip()


def _parse_named_aggregations(raw: Any) -> dict[str, tuple[str, Any]] | None:
    """
    Именованная агрегация pandas: .agg(out_name=(column, func), ...).
    Возвращает None, если блок не задан или пуст.
    """
    if raw is None:
        return None
    if isinstance(raw, dict) and not raw:
        return None
    if isinstance(raw, list) and not raw:
        return None

    out: dict[str, tuple[str, Any]] = {}

    if isinstance(raw, list):
        for i, item in enumerate(raw):
            if not isinstance(item, dict):
                raise ValueError(f"groupby_aggregate: named_aggregations[{i}] должен быть словарём")
            name = (
                item.get("name")
                or item.get("output")
                or item.get("as")
                or item.get("column_out")
            )
            if name is None or str(name).strip() == "":
                raise ValueError(
                    f"groupby_aggregate: named_aggregations[{i}] — укажите имя результата "
                    "(ключ name / output / as)"
                )
            col = item.get("column") or item.get("col") or item.get("source")
            func = item.get("func") or item.get("agg") or item.get("aggregation")
            if col is None or func is None:
                raise ValueError(
                    f"groupby_aggregate: named_aggregations[{i}] — нужны column и func"
                )
            label = f"groupby_aggregate: named_aggregations[{i}]"
            out[str(name).strip()] = (
                str(col).strip(),
                _coerce_agg_func(func, item, label=label),
            )

    elif isinstance(raw, dict):
        for out_name, spec in raw.items():
            oname = str(out_name).strip()
            if not oname:
                raise ValueError("groupby_aggregate: пустое имя в named_aggregations")
            if isinstance(spec, (list, tuple)):
                if len(spec) != 2:
                    raise ValueError(
                        f"groupby_aggregate: для {oname!r} ожидается [колонка, функция] из двух элементов"
                    )
                col, func_raw = spec[0], spec[1]
                func = _coerce_agg_func(
                    func_raw,
                    {"expr": func_raw} if isinstance(func_raw, str) and func_raw.startswith("lambda ") else None,
                    label=f"groupby_aggregate: named_aggregations[{oname!r}]",
                )
                out[oname] = (str(col).strip(), func)
            elif isinstance(spec, dict):
                col = spec.get("column") or spec.get("col") or spec.get("source")
                func = spec.get("func") or spec.get("agg") or spec.get("aggregation")
                if col is None or func is None:
                    raise ValueError(
                        f"groupby_aggregate: named_aggregations[{oname!r}] — "
                        "нужны column и func (или список [column, func])"
                    )
                out[oname] = (
                    str(col).strip(),
                    _coerce_agg_func(func, spec, label=f"groupby_aggregate: named_aggregations[{oname!r}]"),
                )
            else:
                raise ValueError(
                    f"groupby_aggregate: named_aggregations[{oname!r}] — "
                    "значение: словарь {{column, func}} или список из двух элементов"
                )
    else:
        raise ValueError(
            "groupby_aggregate: named_aggregations должен быть словарём или списком словарей"
        )

    return out


def run_groupby_aggregate(ctx: RunContext, step: Step) -> None:
    p = step.params
    source_df = str(get_required_param(p, "source_df"))
    target_df = str(get_required_param(p, "target_df"))
    keys = p.get("group_keys") or []
    aggs = p.get("aggregations") or {}
    named_kw = _parse_named_aggregations(p.get("named_aggregations"))

    if isinstance(keys, str):
        keys = [x.strip() for x in keys.split(",") if x.strip()]
    if not isinstance(keys, list) or not keys:
        raise ValueError("group_keys must be a non-empty list (or comma-separated string).")

    df = ensure_df_exists(ctx.df_store, source_df)

    has_legacy = isinstance(aggs, dict) and bool(aggs)
    has_named = bool(named_kw)
    if has_named and has_legacy:
        raise ValueError(
            "groupby_aggregate: используйте либо named_aggregations, либо aggregations, не оба сразу"
        )
    if not has_named and not has_legacy:
        raise ValueError(
            "groupby_aggregate: задайте непустой aggregations или named_aggregations"
        )

    grouped = df.groupby(keys, dropna=False)

    if has_named:
        assert named_kw is not None
        for out_name, (col, _func) in named_kw.items():
            if col not in df.columns:
                raise ValueError(f"groupby_aggregate: колонка не найдена: {col!r}")
        try:
            out = grouped.agg(**named_kw)
        except Exception as e:
            raise ValueError(f"groupby_aggregate: ошибка agg() с именованными колонками: {e}") from e
        out = out.reset_index()
    else:
        norm_aggs: dict[str, Any] = {}
        for col, spec in aggs.items():
            if isinstance(spec, str):
                norm_aggs[str(col)] = spec
            elif isinstance(spec, list):
                norm_aggs[str(col)] = [str(x) for x in spec]
            else:
                raise ValueError(f"Unsupported aggregation for {col}: {spec}")

        out = grouped.agg(norm_aggs)
        if isinstance(out.columns, pd.MultiIndex):
            out.columns = [
                "__".join([str(x) for x in tup if str(x) != ""]) for tup in out.columns.to_list()
            ]
        out = out.reset_index()

    ctx.df_store[target_df] = out
    mode = "named" if has_named else "legacy"
    ctx.logger.info(
        f"groupby_aggregate: {source_df} rows={len(df)} -> {target_df} rows={len(out)} "
        f"keys={keys} mode={mode}"
    )


def register_groupby_aggregate() -> None:
    REGISTRY.register(
        StepDefinition(
            type="groupby_aggregate",
            title="Группировка (groupby) и агрегации",
            runner=run_groupby_aggregate,
            default_params={
                "source_df": "df_main",
                "target_df": "df_grouped",
                "group_keys": [],
                "aggregations": {"Amount": "sum"},
                "named_aggregations": {},
            },
        )
    )
