from __future__ import annotations

from typing import Any

import pandas as pd

from app.pipeline.context import RunContext
from app.pipeline.registry import REGISTRY, StepDefinition
from app.pipeline.schema import Step
from app.steps.util import ensure_df_exists, get_required_param


def run_text_transform(ctx: RunContext, step: Step) -> None:
    p = step.params
    source_df = str(get_required_param(p, "source_df"))
    column = str(get_required_param(p, "column"))
    df = ensure_df_exists(ctx.df_store, source_df)
    if column not in df.columns:
        raise ValueError(f"Column not found: {column}")

    s = df[column].astype("string")

    if bool(p.get("trim", False)):
        s = s.str.strip()
    if bool(p.get("upper", False)):
        s = s.str.upper()
    if bool(p.get("lower", False)):
        s = s.str.lower()

    replace_map = p.get("replace_map") or {}
    if isinstance(replace_map, list):
        # allow list of {from,to}
        rm: dict[str, str] = {}
        for item in replace_map:
            if isinstance(item, dict) and "from" in item and "to" in item:
                rm[str(item["from"])] = str(item["to"])
        replace_map = rm
    if isinstance(replace_map, dict) and replace_map:
        s = s.replace({str(k): str(v) for k, v in replace_map.items()})

    df[column] = s
    ctx.logger.info(f"text_transform applied: {source_df}.{column}")


def register_text_transform() -> None:
    REGISTRY.register(
        StepDefinition(
            type="text_transform",
            title="Текстовые преобразования столбца",
            runner=run_text_transform,
            default_params={
                "source_df": "df_main",
                "column": "",
                "trim": True,
                "upper": False,
                "lower": False,
                "replace_map": {},
            },
        )
    )

