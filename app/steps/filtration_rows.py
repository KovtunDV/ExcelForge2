from __future__ import annotations

from app.pipeline.context import RunContext
from app.pipeline.registry import REGISTRY, StepDefinition
from app.pipeline.schema import Step
from app.steps.filter_expr import eval_expression
from app.steps.util import ensure_df_exists, get_required_param


def run_filtration_rows(ctx: RunContext, step: Step) -> None:
    p = step.params
    source_df = str(get_required_param(p, "source_df"))
    target_df = str(get_required_param(p, "target_df"))
    expr = p.get("expression") or {"op": "and", "items": []}

    df = ensure_df_exists(ctx.df_store, source_df)
    mask = eval_expression(df, expr)
    out = df.loc[mask].copy()

    ctx.df_store[target_df] = out
    ctx.logger.info(f"filtration: {source_df} rows={len(df)} -> {target_df} rows={len(out)}")


def register_filtration_rows() -> None:
    # Preferred step type: "filtration"
    # Backward compatibility: allow old type "filter" as alias.
    default_params = {
        "source_df": "df_main",
        "target_df": "df_main",
        "expression": {"op": "and", "items": [{"col": "", "cmp": "==", "value": ""}]},
    }

    REGISTRY.register(
        StepDefinition(
            type="filtration",
            title="Фильтрация строк",
            runner=run_filtration_rows,
            default_params=dict(default_params),
        )
    )

    REGISTRY.alias("filter", "filtration")

