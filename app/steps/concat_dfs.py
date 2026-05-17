from __future__ import annotations

from typing import Any, Literal

import pandas as pd

from app.pipeline.context import RunContext
from app.pipeline.registry import REGISTRY, StepDefinition
from app.pipeline.schema import Step
from app.steps.util import get_required_param, resolve_df_names_by_mask

Axis = Literal[0, 1]


def _normalize_axis(raw: Any) -> Axis:
    if isinstance(raw, int):
        if raw in (0, 1):
            return raw
        raise ValueError(f"concat_dfs: axis должен быть 0 или 1; получено: {raw!r}")
    s = str(raw or "0").strip().lower()
    if s in ("0", "rows", "row", "index"):
        return 0
    if s in ("1", "columns", "cols", "column"):
        return 1
    raise ValueError(
        f"concat_dfs: axis — 0 / rows / index или 1 / columns; получено: {raw!r}"
    )


def _normalize_join(raw: Any) -> str:
    j = str(raw or "outer").strip().lower()
    if j in ("inner", "outer"):
        return j
    raise ValueError("concat_dfs: join должен быть inner или outer")


def run_concat_dfs(ctx: RunContext, step: Step) -> None:
    p = step.params
    target = str(get_required_param(p, "target_df"))
    axis = _normalize_axis(p.get("axis", 0))
    ignore_index = bool(p.get("ignore_index", True))
    join = _normalize_join(p.get("join", "outer"))

    names = resolve_df_names_by_mask(ctx.df_store, p, step_label="concat_dfs")
    frames = [ctx.df_store[n] for n in names]

    try:
        out = pd.concat(frames, axis=axis, ignore_index=ignore_index, join=join)
    except Exception as e:
        raise ValueError(f"concat_dfs: ошибка pandas.concat: {e}") from e

    ctx.df_store[target] = out
    ctx.logger.info(
        f"concat_dfs: [{', '.join(names)}] axis={axis} ignore_index={ignore_index} "
        f"join={join} -> {target} rows={len(out)} cols={len(out.columns)}"
    )


def register_concat_dfs() -> None:
    REGISTRY.register(
        StepDefinition(
            type="concat_dfs",
            title="Склеить датафреймы",
            runner=run_concat_dfs,
            default_params={
                "target_df": "df_concat",
                "dataframes": [],
                "name_glob": "",
                "axis": 0,
                "ignore_index": True,
                "join": "outer",
            },
        )
    )
