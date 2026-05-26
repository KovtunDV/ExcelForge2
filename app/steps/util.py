from __future__ import annotations

import fnmatch
import glob
import os
import stat
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import pandas as pd


@dataclass(frozen=True)
class ScannedFile:
    """Файл после одного прохода по каталогу: путь и метаданные из одного os.stat."""

    path: str
    mtime: float
    ctime: float

    def modified_at(self) -> datetime:
        return datetime.fromtimestamp(self.mtime)

    def created_at(self) -> datetime:
        return datetime.fromtimestamp(self.ctime)


def _append_scanned_file(scanned: list[ScannedFile], path: str) -> None:
    try:
        st = os.stat(path)
    except OSError:
        return
    if not stat.S_ISREG(st.st_mode):
        return
    scanned.append(
        ScannedFile(
            path=os.path.abspath(path),
            mtime=st.st_mtime,
            ctime=st.st_ctime,
        )
    )


def scan_directory_files(directory: str, pattern: str, *, recursive: bool = False) -> list[ScannedFile]:
    """
    Формирование списка файлов по маске.

    - recursive=True: один проход os.walk, fnmatch по имени файла, один os.stat на совпадение.
    - recursive=False: glob только в корне каталога, один os.stat на совпадение.
    """
    root = os.path.abspath(directory)
    scanned: list[ScannedFile] = []

    if recursive:
        for dirpath, _dirnames, filenames in os.walk(root):
            for name in filenames:
                if not fnmatch.fnmatch(name, pattern):
                    continue
                _append_scanned_file(scanned, os.path.join(dirpath, name))
    else:
        for path in glob.glob(os.path.join(root, pattern)):
            _append_scanned_file(scanned, path)

    scanned.sort(key=lambda f: f.path)
    return scanned


def scan_single_file(path: str) -> ScannedFile:
    """Метаданные одного файла (режим input_mode: file)."""
    ap = os.path.abspath(path)
    st = os.stat(ap)
    if not stat.S_ISREG(st.st_mode):
        raise ValueError(f"Not a regular file: {ap}")
    return ScannedFile(path=ap, mtime=st.st_mtime, ctime=st.st_ctime)


def pick_latest_by_mtime(files: list[ScannedFile]) -> ScannedFile | None:
    """Самый свежий файл только по времени изменения (mtime)."""
    if not files:
        return None
    return max(files, key=lambda f: f.mtime)


def list_files(directory: str, pattern: str, recursive: bool) -> list[str]:
    """Обратная совместимость: пути после scan_directory_files."""
    return [f.path for f in scan_directory_files(directory, pattern, recursive=recursive)]


def latest_file(files: list[str]) -> str | None:
    """Устаревший API: предпочтительно pick_latest_by_mtime после scan_directory_files."""
    if not files:
        return None
    best_path = files[0]
    best_mtime = -1.0
    for path in files:
        try:
            st = os.stat(path)
        except OSError:
            continue
        if st.st_mtime > best_mtime:
            best_mtime = st.st_mtime
            best_path = path
    return best_path if best_mtime >= 0 else None


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
        from app.pipeline.global_context import get_global_store, is_global_df_name

        if is_global_df_name(name) and name in get_global_store():
            df_store[name] = get_global_store()[name]
        else:
            raise ValueError(f"DataFrame not found: {name}")
    return df_store[name]


def normalize_column_label(name: Any) -> str:
    """
    Имя столбца как строка для YAML/шагов.

    Числовые заголовки Excel (1, 2, 3.0) после read_excel часто int/float — приводим к "1", "2", …
    """
    if isinstance(name, bool):
        return str(name)
    if isinstance(name, int):
        return str(name)
    if isinstance(name, float):
        if pd.isna(name):
            return "nan"
        if name == int(name):
            return str(int(name))
        return str(name)
    s = str(name).strip()
    if s.endswith(".0") and s[:-2].lstrip("-").isdigit():
        try:
            return str(int(float(s)))
        except ValueError:
            pass
    return s


def normalize_dataframe_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Привести имена всех столбцов к строкам (без изменения данных)."""
    df.columns = [normalize_column_label(c) for c in df.columns]
    return df


def find_dataframe_column(columns: Any, spec: Any) -> Any | None:
    """
    Найти фактическую метку столбца в Index/Columns по значению из mapping/YAML.

    spec может быть строкой "1", числом 1, float 1.0 — сопоставляется с int/float/str в columns.
    """
    col_list = list(columns)
    if spec in col_list:
        return spec

    norm_spec = normalize_column_label(spec)
    for c in col_list:
        if normalize_column_label(c) == norm_spec:
            return c

    try:
        target = float(norm_spec)
    except ValueError:
        return None

    for c in col_list:
        if isinstance(c, (int, float)) and not (isinstance(c, float) and pd.isna(c)):
            try:
                if float(c) == target:
                    return c
            except (ValueError, TypeError):
                continue
    return None


def build_column_rename_map(
    columns: Any,
    mapping: dict[Any, Any],
    *,
    step_label: str = "rename_columns",
) -> dict[Any, str]:
    """Словарь {фактический_столбец: новое_имя}; при отсутствии столбца — ошибка."""
    resolved: dict[Any, str] = {}
    missing: list[str] = []
    for old, new in mapping.items():
        key = find_dataframe_column(columns, old)
        if key is None:
            missing.append(str(old))
        else:
            resolved[key] = str(new)
    if missing:
        available = [normalize_column_label(c) for c in columns]
        raise ValueError(
            f"{step_label}: не найдены столбцы для переименования: {missing}. "
            f"Доступные столбцы: {available}"
        )
    return resolved


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

