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


def should_preserve_string_as_text(value: str, *, number_format: str | None = None) -> bool:
    """
    Строки-идентификаторы (штрихкоды, коды с «_», ведущие нули) не превращать в число Excel.
    """
    if number_format == "@":
        return True
    stripped = str(value).strip()
    if not stripped:
        return False
    if stripped.startswith("_"):
        return True
    if re.fullmatch(r"0\d+", stripped):
        return True
    if re.fullmatch(r"\d+", stripped) and len(stripped) >= 11:
        return True
    num = coerce_to_float(stripped)
    if num is not None and num.is_integer():
        normalized = stripped.lstrip("+").replace(" ", "")
        if f"{int(num)}" != normalized:
            return True
    return False


def _is_missing_value(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, float) and value != value:
        return True
    return False


def prepare_value_for_excel_cell(
    value: Any,
    *,
    normalize: bool,
    number_format: str | None = None,
) -> tuple[Any, str | None]:
    """
    Подготовка значения для openpyxl.

    normalize=False: тип как в DataFrame (str → текст, int/float → число).
    normalize=True: строки-числа → int/float (с учётом @ и идентификаторов).
    Возвращает (value, override_number_format или None).
    """
    if _is_missing_value(value):
        return None, None

    fmt = number_format or "General"

    if not normalize:
        if isinstance(value, str):
            return value, "@"
        if isinstance(value, bool):
            return value, None
        if isinstance(value, int) and not isinstance(value, bool):
            return value, None
        if isinstance(value, float):
            return value, None
        if isinstance(value, Decimal):
            f = float(value)
            if f.is_integer():
                return int(f), None
            return f, None
        return value, None

    if isinstance(value, str) and fmt == "@":
        return value, None

    normalized = normalize_value_for_excel(value, number_format=fmt)
    if isinstance(normalized, str) and should_preserve_string_as_text(normalized, number_format=fmt):
        return normalized, "@" if fmt != "@" else None
    return normalized, None


def normalize_value_for_excel(value: Any, *, number_format: str | None = None) -> Any:
    """
    Для записи в ячейку Excel: числовые строки -> float/int,
    чтобы Excel применял региональный формат отображения.
    Идентификаторы и текстовый формат ячейки (@) сохраняются как строка.
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
        if should_preserve_string_as_text(stripped, number_format=number_format):
            return stripped
        num = coerce_to_float(stripped)
        if num is not None:
            if num.is_integer() and "," not in stripped and "." not in stripped:
                return int(num)
            return num
    return value
