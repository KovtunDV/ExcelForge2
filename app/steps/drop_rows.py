from __future__ import annotations

from typing import Any, Literal

import pandas as pd

from app.pipeline.context import RunContext
from app.pipeline.registry import REGISTRY, StepDefinition
from app.pipeline.schema import Step
from app.steps.filter_expr import eval_expression
from app.steps.util import ensure_df_exists, get_required_param


Mode = Literal["empty", "duplicates", "by_filter", "by_list"]

def _eval_query_mask(df: pd.DataFrame, query: str) -> pd.Series:
    """
    Boolean mask from pandas eval/query-like expression.
    Supports 'and/or/not' by converting to '&/|/~' and allows '.isnan()' alias.
    """
    q = (query or "").strip()
    if not q:
        raise ValueError("drop_rows by_filter: query пустой")
    # Convenience: allow Ost.isna()/isnan() style
    q = q.replace(".isnan()", ".isna()")
    # Allow Python boolean operators (common in YAML examples)
    q = q.replace(" and ", " & ").replace(" or ", " | ").replace(" not ", " ~ ")
    try:
        mask = df.eval(q, engine="python")
    except Exception as e:
        raise ValueError(f"drop_rows by_filter: ошибка eval(query): {e}") from e
    if not isinstance(mask, pd.Series):
        raise ValueError("drop_rows by_filter: query должен возвращать булеву Series")
    if len(mask) != len(df):
        raise ValueError("drop_rows by_filter: query вернул Series неверной длины")
    return mask.fillna(False)


def run_drop_rows(ctx: RunContext, step: Step) -> None:
    p = step.params
    source_df = str(get_required_param(p, "source_df"))
    mode: Mode = str(get_required_param(p, "mode"))
    target_df = str(p.get("target_df", source_df))

    df = ensure_df_exists(ctx.df_store, source_df)
    before = len(df)

    if mode == "empty":
        subset = p.get("subset_columns") or []
        if isinstance(subset, str):
            subset = [c.strip() for c in subset.split(",") if c.strip()]
        out = df.dropna(subset=list(subset) if subset else None).copy()
    elif mode == "duplicates":
        subset = p.get("subset_columns") or []
        if isinstance(subset, str):
            subset = [c.strip() for c in subset.split(",") if c.strip()]
        keep = str(p.get("keep", "first"))
        out = df.drop_duplicates(subset=list(subset) if subset else None, keep=keep).copy()
    elif mode == "by_filter":
        query = str(p.get("query", "") or "").strip()
        if query:
            mask = _eval_query_mask(df, query)
        else:
            expr = p.get("expression") or {"op": "and", "items": []}
            mask = eval_expression(df, expr)
        out = df.loc[~mask].copy()
    elif mode == "by_list":
        col = str(get_required_param(p, "column"))
        values = p.get("values") or []
        if isinstance(values, str):
            values = [x.strip() for x in values.split(",") if x.strip()]
        out = df.loc[~df[col].isin(values)].copy()
    else:
        raise ValueError(f"Unsupported mode: {mode}")

    after = len(out)
    ctx.df_store[target_df] = out
    ctx.logger.info(f"drop_rows: {source_df} rows={before} -> {target_df} rows={after} (dropped={before-after})")


def register_drop_rows() -> None:
    REGISTRY.register(
        StepDefinition(
            type="drop_rows",
            title="Удаление строк",
            runner=run_drop_rows,
            default_params={
                "source_df": "df_main",
                "target_df": "df_main",
                "mode": "empty",  # empty|duplicates|by_filter|by_list
                "subset_columns": [],
                "keep": "first",
                "expression": {"op": "and", "items": [{"col": "", "cmp": "==", "value": ""}]},
                "query": "",
                "column": "",
                "values": [],
            },
        )
    )

