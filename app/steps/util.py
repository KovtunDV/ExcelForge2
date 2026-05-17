from __future__ import annotations

import fnmatch
import os
from typing import Any

import pandas as pd


def list_files(directory: str, pattern: str, recursive: bool) -> list[str]:
    import glob

    directory = os.path.abspath(directory)
    if recursive:
        glob_pat = os.path.join(directory, "**", pattern)
        files = glob.glob(glob_pat, recursive=True)
    else:
        glob_pat = os.path.join(directory, pattern)
        files = glob.glob(glob_pat, recursive=False)
    files = [f for f in files if os.path.isfile(f)]
    files.sort()
    return files


def latest_file(files: list[str]) -> str | None:
    if not files:
        return None
    return max(files, key=lambda p: os.path.getmtime(p))


def param_is_on(val: Any) -> bool:
    """Истина для YAML-флагов: true / on / yes / 1 (без учёта регистра)."""
    if val is True:
        return True
    if val is False or val is None:
        return False
    s = str(val).strip().lower()
    return s in ("1", "true", "yes", "on", "y")


def get_required_param(params: dict[str, Any], key: str) -> Any:
    if key not in params:
        raise ValueError(f"Missing required param: {key}")
    return params[key]


def ensure_df_exists(df_store: dict[str, pd.DataFrame], name: str) -> pd.DataFrame:
    if name not in df_store:
        raise ValueError(f"DataFrame not found: {name}")
    return df_store[name]


def resolve_df_names_by_mask(
    store: dict[str, pd.DataFrame],
    p: dict[str, Any],
    *,
    step_label: str = "step",
) -> list[str]:
    """
    Список имён DF по явному списку dataframes и/или маске name_glob (fnmatch).

    - Только name_glob — все ключи store, совпавшие с маской (сортировка по имени).
    - Только dataframes — указанный список.
    - Оба — порядок dataframes, оставляются только совпавшие с маской.
    """
    explicit = p.get("dataframes")
    names: list[str] = []
    if explicit is not None:
        if not isinstance(explicit, list):
            raise ValueError(f"{step_label}: dataframes должен быть списком имён DF")
        names = [str(x).strip() for x in explicit if str(x).strip() != ""]
    glob_pat = str(p.get("name_glob", "") or "").strip()

    if names and glob_pat:
        names = [n for n in names if fnmatch.fnmatch(n, glob_pat)]
        if not names:
            raise ValueError(
                f"{step_label}: ни одно имя из dataframes не подошло под name_glob {glob_pat!r}"
            )
    elif not names and glob_pat:
        keys = sorted(store.keys(), key=lambda x: x.lower())
        names = [k for k in keys if fnmatch.fnmatch(k, glob_pat)]
        if not names:
            raise ValueError(
                f"{step_label}: name_glob {glob_pat!r} не совпал ни с одним DF в контексте"
            )
    elif not names:
        raise ValueError(
            f"{step_label}: задайте непустой список dataframes или строку name_glob (маска имён)"
        )

    for n in names:
        if n not in store:
            raise ValueError(f"{step_label}: DataFrame не найден: {n!r}")

    return names

