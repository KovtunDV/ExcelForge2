from __future__ import annotations

import datetime as dt
import math
import re
from typing import Any, Callable

import pandas as pd

_EXCEL_ORIGIN = "1899-12-30"

_SAFE_BUILTINS: dict[str, Any] = {
    "len": len,
    "str": str,
    "int": int,
    "float": float,
    "bool": bool,
    "isinstance": isinstance,
    "min": min,
    "max": max,
    "abs": abs,
    "round": round,
    "None": None,
    "True": True,
    "False": False,
}

_LAMBDA_NAMESPACE: dict[str, Any] = {
    "pd": pd,
    "datetime": dt.datetime,
    "date": dt.date,
    "timedelta": dt.timedelta,
    "math": math,
    "re": re,
    "excel_serial_to_datetime": None,  # set below
    "EXCEL_ORIGIN": _EXCEL_ORIGIN,
}


def excel_serial_to_datetime(value: Any) -> Any:
    """Число Excel (дни с 1899-12-30) или его текст → pandas.Timestamp / NaT."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return pd.NaT
    if isinstance(value, pd.Timestamp):
        return value
    raw = str(value).strip()
    if not raw or raw.lower() in ("nan", "<na>", "none", "nat"):
        return pd.NaT
    try:
        num = float(raw.replace(",", "."))
    except ValueError:
        parsed = pd.to_datetime(raw, errors="coerce", dayfirst=True)
        return parsed if not pd.isna(parsed) else pd.NaT
    return pd.to_datetime(num, unit="D", origin=_EXCEL_ORIGIN, errors="coerce")


_LAMBDA_NAMESPACE["excel_serial_to_datetime"] = excel_serial_to_datetime


def compile_series_lambda(expr: str, *, label: str = "lambda") -> Callable[..., Any]:
    """
    Компилирует строку вида ``lambda x: ...`` в callable.
    Доступны pd, datetime, math, re и excel_serial_to_datetime(x).
    """
    source = str(expr or "").strip()
    if not source:
        raise ValueError(f"{label}: задайте expr (строка lambda)")
    if not source.startswith("lambda "):
        raise ValueError(
            f"{label}: ожидается выражение lambda, например: lambda x: excel_serial_to_datetime(x)"
        )
    ns = dict(_LAMBDA_NAMESPACE)
    glb = {"__builtins__": _SAFE_BUILTINS, **ns}
    try:
        fn = eval(source, glb, ns)  # noqa: S307
    except Exception as e:
        raise ValueError(f"{label}: не удалось разобрать lambda: {e}") from e
    if not callable(fn):
        raise ValueError(f"{label}: выражение не является функцией")
    return fn


def resolve_lambda_expr(
    func: Any,
    params: dict[str, Any] | None = None,
    *,
    label: str = "lambda",
) -> Callable[..., Any] | None:
    """
    Возвращает callable, если func указывает на lambda:
    - func == 'lambda' и expr/lambda/code в params;
    - func — строка, начинающаяся с 'lambda '.
    """
    par = params or {}
    if isinstance(func, str):
        f = func.strip()
        if f.lower() == "lambda":
            expr = par.get("expr") or par.get("lambda") or par.get("code")
            if expr is None or str(expr).strip() == "":
                raise ValueError(f"{label}: для func=lambda задайте params.expr")
            return compile_series_lambda(str(expr), label=label)
        if f.startswith("lambda "):
            return compile_series_lambda(f, label=label)
    return None


def apply_lambda_to_series(s: pd.Series, expr: str, *, label: str = "apply_transform") -> pd.Series:
    fn = compile_series_lambda(expr, label=label)
    return s.apply(fn)
