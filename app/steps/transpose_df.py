from __future__ import annotations

from typing import Any

import pandas as pd

from app.pipeline.context import RunContext
from app.pipeline.registry import REGISTRY, StepDefinition
from app.pipeline.schema import Step
from app.steps.util import ensure_df_exists, get_required_param, param_is_on


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


def _index_labels_as_strings(index: pd.Index) -> list[str]:
    if isinstance(index, pd.MultiIndex):
        return ["_".join(str(part) for part in row) for row in index.tolist()]
    return [str(x) for x in index.tolist()]


def _prepend_column_names_column(out: pd.DataFrame, name_col: str) -> pd.DataFrame:
    names = _index_labels_as_strings(out.index)
    result = out.reset_index(drop=True)
    result.insert(0, name_col, names)
    return result


def run_transpose_df(ctx: RunContext, step: Step) -> None:
    p = step.params
    source_df = str(get_required_param(p, "source_df"))
    tgt = str(p.get("target_df") or source_df).strip() or source_df
    copy_flag = _coerce_copy(p.get("copy", True))

    df = ensure_df_exists(ctx.df_store, source_df)
    out = df.transpose(copy=copy_flag)

    keep_names = param_is_on(
        p.get("column_names_as_column", p.get("keep_column_names", False))
    )
    if keep_names:
        name_col = str(
            p.get("column_names_column") or p.get("names_column") or "_column"
        ).strip() or "_column"
        out = _prepend_column_names_column(out, name_col)

    ctx.df_store[tgt] = out
    extra = f", column_names_as_column={keep_names}" if keep_names else ""
    ctx.logger.info(
        f"transpose_df: {source_df} shape={df.shape} -> {tgt} shape={out.shape}, copy={copy_flag}{extra}"
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
                "column_names_as_column": False,
                "column_names_column": "_column",
            },
        )
    )
