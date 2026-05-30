from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from typing import Any

import pandas as pd


def coerce_to_float(value: Any) -> float | None:
    """
    Преобразовать значение в float с учётом локали:
    34.55, 34,55, 1 234,56, 1.234,56, 1,234.56.
    """
    if value is None:
        return None
    if isinstance(value, bool):
        return float(value)
    if isinstance(value, int):
        return float(value)
    if isinstance(value, float):
        if value != value:
            return None
        return value
    if isinstance(value, Decimal):
        return float(value)

    s = str(value).strip()
    if not s:
        return None

    s = s.replace("\u00a0", "").replace(" ", "")

    if "," in s and "." in s:
        if s.rfind(",") > s.rfind("."):
            s = s.replace(".", "").replace(",", ".")
        else:
            s = s.replace(",", "")
    elif "," in s:
        if re.fullmatch(r"-?\d+,\d+", s):
            s = s.replace(",", ".")
        else:
            s = s.replace(",", "")

    try:
        return float(s)
    except ValueError:
        try:
            return float(Decimal(s))
        except (InvalidOperation, ValueError):
            return None


def parse_numeric_series(series: pd.Series) -> pd.Series:
    """Серия float; нераспознанные значения -> NaN."""
    return pd.Series([coerce_to_float(v) for v in series], index=series.index, dtype="float64")


def normalize_value_for_excel(value: Any) -> Any:
    """
    Для записи в ячейку Excel: числовые строки -> float/int,
    чтобы Excel применял региональный формат отображения.
    """
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    if isinstance(value, float):
        if value != value:
            return None
        return value
    if isinstance(value, Decimal):
        f = float(value)
        if f.is_integer():
            return int(f)
        return f

    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return value
        num = coerce_to_float(stripped)
        if num is not None:
            if num.is_integer() and "," not in stripped and "." not in stripped:
                return int(num)
            return num
    return value
