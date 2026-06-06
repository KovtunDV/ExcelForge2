from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

import pandas as pd


Cmp = Literal[
    "==",
    "!=",
    ">",
    ">=",
    "<",
    "<=",
    "contains",
    "startswith",
    "endswith",
    "in",
    "not_in",
    "is_na",
    "not_na",
    "str_len",
]
Op = Literal["and", "or"]


@dataclass(frozen=True)
class Condition:
    col: str
    cmp: Cmp
    value: Any


def _strlen_series(s: pd.Series) -> pd.Series:
    """Длина строкового представления; NaN/NA считаются как пустая строка (длина 0)."""
    strv = s.astype("string")
    return strv.fillna("").str.len()


def _compare_strlen_to_n(lens: pd.Series, rel: str, n: int) -> pd.Series:
    """Сравнение серии длин с целым n; rel — ==, !=, >, >=, <, <= или eq, ne, gt, ge, lt, le."""
    r = rel.strip().lower()
    if r in ("==", "eq"):
        return lens == n
    if r in ("!=", "ne"):
        return lens != n
    if r in (">", "gt"):
        return lens > n
    if r in (">=", "ge"):
        return lens >= n
    if r in ("<", "lt"):
        return lens < n
    if r in ("<=", "le"):
        return lens <= n
    raise ValueError(
        f"str_len: неизвестный op {rel!r}; используйте ==, !=, >, >=, <, <= "
        "(или eq, ne, gt, ge, lt, le)."
    )


def _parse_in_values(value: Any) -> list[Any]:
    if isinstance(value, str):
        return [x.strip() for x in value.split(",") if x.strip() != ""]
    if isinstance(value, list):
        return list(value)
    return [value]


def _coerce_value_for_series(series: pd.Series, value: Any) -> Any:
    # Try to interpret numeric comparisons against numeric series.
    try:
        if pd.api.types.is_numeric_dtype(series):
            return float(value)
    except Exception:
        pass
    return value


def eval_expression(df: pd.DataFrame, expr: dict[str, Any]) -> pd.Series:
    op: Op = str(expr.get("op", "and")).lower()  # type: ignore[assignment]
    items = expr.get("items", []) or []
    masks: list[pd.Series] = []

    for it in items:
        if not isinstance(it, dict):
            continue
        col = str(it.get("col", ""))
        cmp: Cmp = str(it.get("cmp", "=="))  # type: ignore[assignment]
        value = it.get("value")
        if col not in df.columns:
            raise ValueError(f"Filter column not found: {col}")

        s = df[col]
        v = _coerce_value_for_series(s, value)

        if cmp == "==":
            m = s == v
        elif cmp == "!=":
            m = s != v
        elif cmp == ">":
            m = pd.to_numeric(s, errors="coerce") > float(v)
        elif cmp == ">=":
            m = pd.to_numeric(s, errors="coerce") >= float(v)
        elif cmp == "<":
            m = pd.to_numeric(s, errors="coerce") < float(v)
        elif cmp == "<=":
            m = pd.to_numeric(s, errors="coerce") <= float(v)
        elif cmp == "contains":
            m = s.astype("string").str.contains(str(v), na=False)
        elif cmp == "startswith":
            m = s.astype("string").str.startswith(str(v), na=False)
        elif cmp == "endswith":
            m = s.astype("string").str.endswith(str(v), na=False)
        elif cmp == "in":
            vals = _parse_in_values(v)
            m = s.isin(vals)
        elif cmp == "not_in":
            vals = _parse_in_values(v)
            m = ~s.isin(vals)
        elif cmp == "is_na":
            m = pd.isna(s)
        elif cmp == "not_na":
            m = ~pd.isna(s)
        elif cmp == "str_len":
            if not isinstance(v, dict):
                raise ValueError(
                    "str_len: value должен быть словарём, например {op: '>=', n: 5} "
                    "или {op: ge, n: 5}"
                )
            rel = str(v.get("op", ""))
            try:
                n = int(v["n"])
            except (KeyError, TypeError, ValueError) as e:
                raise ValueError("str_len: нужны ключи op (строка) и n (целое число)") from e
            lens = _strlen_series(s)
            m = _compare_strlen_to_n(lens, rel, n)
        else:
            raise ValueError(f"Unsupported comparator: {cmp}")

        masks.append(m.fillna(False))

    if not masks:
        return pd.Series([True] * len(df), index=df.index)

    if op == "or":
        out = masks[0]
        for m in masks[1:]:
            out = out | m
        return out

    out = masks[0]
    for m in masks[1:]:
        out = out & m
    return out

