from __future__ import annotations

from typing import Any

from app.pipeline.context import RunContext
from app.pipeline.registry import REGISTRY, StepDefinition
from app.pipeline.schema import Step
from app.steps.util import ensure_df_exists, get_required_param


def _coerce_copy(raw: Any) -> bool:
    if raw is None:
        return True
    if isinstance(raw, bool):
        return raw
    s = str(raw).strip().lower()
    if s in ("0", "false", "no", "off"):
        return False
    if s in ("1", "true", "yes", "on"):
        return True
    return bool(raw)


def run_transpose_df(ctx: RunContext, step: Step) -> None:
    p = step.params
    source_df = str(get_required_param(p, "source_df"))
    tgt = str(p.get("target_df") or source_df).strip() or source_df
    copy_flag = _coerce_copy(p.get("copy", True))

    df = ensure_df_exists(ctx.df_store, source_df)
    out = df.transpose(copy=copy_flag)

    ctx.df_store[tgt] = out
    ctx.logger.info(
        f"transpose_df: {source_df} shape={df.shape} -> {tgt} shape={out.shape}, copy={copy_flag}"
    )


def register_transpose_df() -> None:
    REGISTRY.register(
        StepDefinition(
            type="transpose_df",
            title="Транспонировать DataFrame",
            runner=run_transpose_df,
            default_params={
                "source_df": "df_main",
                "target_df": "df_main",
                "copy": True,
            },
        )
    )
