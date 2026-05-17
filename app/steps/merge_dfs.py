from __future__ import annotations

from typing import Any

import pandas as pd

from app.pipeline.context import RunContext
from app.pipeline.registry import REGISTRY, StepDefinition
from app.pipeline.schema import Step
from app.steps.util import ensure_df_exists, get_required_param


def run_merge(ctx: RunContext, step: Step) -> None:
    p = step.params
    left_name = str(get_required_param(p, "left_df"))
    right_name = str(get_required_param(p, "right_df"))
    result_name = str(get_required_param(p, "result_df"))

    left = ensure_df_exists(ctx.df_store, left_name)
    right = ensure_df_exists(ctx.df_store, right_name)

    how = str(p.get("how", "inner"))
    on = p.get("on") or None
    left_on = p.get("left_on") or None
    right_on = p.get("right_on") or None
    indicator = bool(p.get("indicator", False))
    suffixes = p.get("suffixes") or ["_x", "_y"]
    if isinstance(suffixes, str):
        parts = [x.strip() for x in suffixes.split(",") if x.strip()]
        if len(parts) == 2:
            suffixes = parts
        else:
            suffixes = ["_x", "_y"]

    merged = pd.merge(
        left,
        right,
        how=how,
        on=on,
        left_on=left_on,
        right_on=right_on,
        indicator=indicator,
        suffixes=tuple(suffixes),
    )
    ctx.df_store[result_name] = merged
    ctx.logger.info(
        f"merge: {left_name} rows={len(left)} + {right_name} rows={len(right)} -> {result_name} rows={len(merged)}"
    )


def register_merge() -> None:
    REGISTRY.register(
        StepDefinition(
            type="merge",
            title="Merge (объединение датафреймов)",
            runner=run_merge,
            default_params={
                "left_df": "df_left",
                "right_df": "df_right",
                "how": "inner",  # inner|left|right|outer|cross
                "on": [],
                "left_on": [],
                "right_on": [],
                "indicator": False,
                "suffixes": ["_x", "_y"],
                "result_df": "df_merged",
            },
        )
    )

