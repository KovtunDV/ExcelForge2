from __future__ import annotations

from typing import Any

from app.pipeline.context import RunContext
from app.pipeline.registry import REGISTRY, StepDefinition
from app.pipeline.schema import Step
from app.steps.util import (
    build_column_rename_map,
    ensure_df_exists,
    get_required_param,
    normalize_dataframe_columns,
)


def run_rename_columns(ctx: RunContext, step: Step) -> None:
    p = step.params
    source_df = str(get_required_param(p, "source_df"))
    target_df = str(p.get("target_df", source_df))
    mapping = p.get("mapping") or {}

    if isinstance(mapping, list):
        m: dict[str, str] = {}
        for item in mapping:
            if isinstance(item, dict) and "from" in item and "to" in item:
                m[str(item["from"])] = str(item["to"])
        mapping = m

    if not isinstance(mapping, dict):
        raise ValueError("mapping must be dict or list[{from,to}]")

    df = ensure_df_exists(ctx.df_store, source_df)
    normalize_dataframe_columns(df)
    rename_map = build_column_rename_map(df.columns, mapping, step_label="rename_columns")
    out = df.rename(columns=rename_map).copy()
    ctx.df_store[target_df] = out
    ctx.logger.info(
        f"rename_columns: {source_df} -> {target_df} renamed={len(rename_map)} "
        f"({', '.join(f'{k!r}->{v!r}' for k, v in rename_map.items())})"
    )


def register_rename_columns() -> None:
    REGISTRY.register(
        StepDefinition(
            type="rename_columns",
            title="Переименование столбцов",
            runner=run_rename_columns,
            default_params={
                "source_df": "df_main",
                "target_df": "df_main",
                "mapping": {"old": "new"},
            },
        )
    )

