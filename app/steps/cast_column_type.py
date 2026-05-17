from __future__ import annotations

from decimal import Decimal
from typing import Any, Literal

import pandas as pd

from app.pipeline.context import RunContext
from app.pipeline.registry import REGISTRY, StepDefinition
from app.pipeline.schema import Step
from app.steps.util import ensure_df_exists, get_required_param


TargetType = Literal["datetime", "int", "decimal", "str"]


def _parse_columns_param(p: dict[str, Any]) -> list[str]:
    """
    Поддержка column (строка) и columns (список/строка через запятую).
    Если columns задан непустым — используется он; иначе column.
    """
    raw_cols = p.get("columns")
    if raw_cols is not None:
        if isinstance(raw_cols, str):
            cols = [x.strip() for x in raw_cols.split(",") if x.strip()]
            if cols:
                return cols
        elif isinstance(raw_cols, list):
            cols = [str(x).strip() for x in raw_cols if str(x).strip() != ""]
            if cols:
                return cols
        # columns был, но пуст/невалиден -> падаем явно
        raise ValueError("cast_column_type: columns должен быть непустым списком или строкой имён")

    col = str(get_required_param(p, "column")).strip()
    if not col:
        raise ValueError("cast_column_type: column не может быть пустым")
    return [col]


def run_cast_column_type(ctx: RunContext, step: Step) -> None:
    p = step.params
    source_df = str(get_required_param(p, "source_df"))
    target_type: TargetType = str(get_required_param(p, "target_type"))
    errors_to_zero = bool(p.get("errors_to_zero", True))

    df = ensure_df_exists(ctx.df_store, source_df)
    columns = _parse_columns_param(p)
    missing = [c for c in columns if c not in df.columns]
    if missing:
        raise ValueError(f"Column(s) not found: {missing}")

    if target_type == "str":
        for column in columns:
            df[column] = df[column].astype("string").fillna("")
        ctx.logger.info(
            f"cast_column_type: {source_df} columns={columns} -> str"
        )
        return

    if target_type == "datetime":
        for column in columns:
            df[column] = pd.to_datetime(df[column], errors="coerce")
        ctx.logger.info(
            f"cast_column_type: {source_df} columns={columns} -> datetime"
        )
        return

    if target_type in ("int", "decimal"):
        total_bad = 0
        for column in columns:
            s = df[column]
            num = pd.to_numeric(s, errors="coerce")
            bad = int(num.isna().sum())
            total_bad += bad
            if errors_to_zero:
                num = num.fillna(0)
            if target_type == "int":
                df[column] = num.astype("int64", errors="ignore")
            else:
                # keep numeric as float by default; optionally convert to Decimal objects
                if bool(p.get("use_decimal_objects", False)):
                    df[column] = num.apply(
                        lambda x: Decimal(str(x)) if pd.notna(x) else Decimal("0")
                    )
                else:
                    df[column] = num.astype("float64", errors="ignore")
        if total_bad:
            ctx.logger.warn(
                f"cast_column_type: fixed {total_bad} non-numeric/empty values in {source_df} columns={columns}"
            )
        ctx.logger.info(f"cast_column_type: {source_df} columns={columns} -> {target_type}")
        return

    raise ValueError(f"Unsupported target_type: {target_type}")


def register_cast_column_type() -> None:
    REGISTRY.register(
        StepDefinition(
            type="cast_column_type",
            title="Преобразование типа столбца",
            runner=run_cast_column_type,
            default_params={
                "source_df": "df_main",
                "column": "",
                "columns": [],
                "target_type": "int",  # datetime|int|decimal
                "errors_to_zero": True,
                "use_decimal_objects": False,
            },
        )
    )

