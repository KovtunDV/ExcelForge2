from __future__ import annotations

import os
from typing import Any, Literal

import pandas as pd

from app.pipeline.context import RunContext
from app.pipeline.registry import REGISTRY, StepDefinition
from app.pipeline.schema import Step
from app.steps.util import (
    ScannedFile,
    get_required_param,
    normalize_dataframe_columns,
    pick_latest_by_mtime,
    scan_directory_files,
    scan_single_file,
)


HeaderMode = Literal["first_row", "letters", "numbers"]
InputMode = Literal["file", "mask", "latest"]


def _make_columns(mode: HeaderMode, df: pd.DataFrame) -> list[str]:
    if mode == "letters":
        cols = []
        for i in range(len(df.columns)):
            n = i
            s = ""
            while True:
                n, r = divmod(n, 26)
                s = chr(ord("A") + r) + s
                if n == 0:
                    break
                n -= 1
            cols.append(s)
        return cols
    if mode == "numbers":
        return [str(i + 1) for i in range(len(df.columns))]
    return [str(c) for c in df.columns]


def _param_is_on(val: Any) -> bool:
    # Local copy to avoid importing from steps.util (keep step self-contained).
    if val is True:
        return True
    if val is False or val is None:
        return False
    s = str(val).strip().lower()
    return s in ("1", "true", "yes", "on", "y")


def _from_file_value(path: str, mode: Any) -> str:
    m = str(mode or "basename").strip().lower()
    if m in ("basename", "name", "filename"):
        return os.path.basename(path)
    if m in ("fullpath", "path", "full"):
        return os.path.abspath(path)
    raise ValueError("from_file_mode must be basename or fullpath")


def _date_file_value_from_scan(sf: ScannedFile, mode: Any) -> datetime:
    m = str(mode or "modified").strip().lower()
    if m in ("modified", "mtime", "updated", "update"):
        return sf.modified_at()
    if m in ("created", "ctime", "creation", "create"):
        return sf.created_at()
    raise ValueError("date_file_mode must be modified or created")


def _read_one_excel(path: str, params: dict[str, Any]) -> pd.DataFrame:
    sheet = params.get("sheet") or 0
    dtype = params.get("dtype") or "str"
    start_row = int(params.get("start_row", 1))
    usecols = params.get("usecols") or None
    header_mode: HeaderMode = str(params.get("header_mode", "first_row"))

    # YAML uses 1-based start_row. Pandas skiprows counts from 0.
    skiprows = max(0, start_row - 1)

    if header_mode == "first_row":
        header = 0
    else:
        header = None

    df = pd.read_excel(
        path,
        sheet_name=sheet,
        dtype=str if dtype == "str" else None,
        header=header,
        skiprows=skiprows,
        usecols=usecols,
        engine="openpyxl",
    )
    if header_mode in ("letters", "numbers"):
        df.columns = _make_columns(header_mode, df)
    else:
        # first_row: заголовки из Excel могут быть int/float (1, 2, 3.0) — строки для шагов
        normalize_dataframe_columns(df)
    return df


def run_load_excel(ctx: RunContext, step: Step) -> None:
    p = step.params
    input_mode: InputMode = str(p.get("input_mode", "file"))

    df_name = str(get_required_param(p, "dataframe"))
    recursive = bool(p.get("recursive", False))
    add_service_cols = _param_is_on(p.get("include_service_columns", False))
    from_file_mode = p.get("from_file_mode", "basename")
    date_file_mode = p.get("date_file_mode", "modified")

    to_load: list[ScannedFile] = []
    if input_mode == "file":
        f = str(p.get("file_path", "") or "").strip()
        if not f:
            raise ValueError(
                "load_excel: задайте file_path или включите file_open_dialog для выбора файла"
            )
        to_load = [scan_single_file(f)]
    else:
        directory = str(p.get("directory", "") or "").strip()
        if not directory:
            raise ValueError(
                "load_excel: задайте directory или включите directory_open_dialog для выбора каталога"
            )
        pattern = str(p.get("pattern", "*.xlsx"))
        scanned = scan_directory_files(directory, pattern, recursive=recursive)
        ctx.logger.info(
            f"load_excel: scanned {len(scanned)} file(s) in {directory!r} "
            f"(pattern={pattern!r}, recursive={recursive})"
        )
        if input_mode == "latest":
            latest = pick_latest_by_mtime(scanned)
            to_load = [latest] if latest else []
        else:
            to_load = scanned

    if not to_load:
        raise ValueError("No input files found for load_excel.")

    frames: list[pd.DataFrame] = []
    schema_cols: list[str] | None = None
    loaded_files = 0
    for sf in to_load:
        f = sf.path
        try:
            df = _read_one_excel(f, p)
            if add_service_cols:
                df["_from_file"] = _from_file_value(f, from_file_mode)
                df["_date_file"] = _date_file_value_from_scan(sf, date_file_mode)
            cols = [str(c) for c in df.columns]
            if schema_cols is None:
                schema_cols = cols
            else:
                if cols != schema_cols:
                    raise ValueError(
                        f"Schema mismatch. Expected columns={schema_cols}, got={cols}"
                    )
            frames.append(df)
            loaded_files += 1
            ctx.logger.info(f"Loaded: {f} rows={len(df)} cols={len(df.columns)}")
        except Exception as e:  # noqa: BLE001
            ctx.logger.error(f"Skip file: {f}. Error: {e}")
            continue

    if not frames:
        raise ValueError("All files failed to load; no data loaded.")

    out = pd.concat(frames, ignore_index=True)
    ctx.df_store[df_name] = out

    if len(out) == 0:
        ctx.logger.warn(f"Loaded 0 rows into {df_name}.")
        confirm_fn = ctx.variables.get("confirm_continue_on_zero_rows")
        if callable(confirm_fn):
            ok = bool(confirm_fn(df_name))
            if not ok:
                ctx.cancel()

    ctx.logger.info(
        f"load_excel finished: files_ok={loaded_files}/{len(to_load)} -> {df_name} rows={len(out)}"
    )


def register_load_excel() -> None:
    REGISTRY.register(
        StepDefinition(
            type="load_excel",
            title="Загрузка Excel → DataFrame",
            runner=run_load_excel,
            default_params={
                "input_mode": "mask",  # file|mask|latest
                "directory": "",
                "pattern": "*.xlsx",
                "recursive": False,
                "file_path": "",
                "file_open_dialog": False,
                "file_open_dialog_help": "Выберите файл для загрузки",
                "filetypes": [],
                "dialogs": [],
                "directory_open_dialog": False,
                "directory_open_dialog_help": "Выберите каталог с файлами Excel",
                "directory_initial": "",
                "sheet": "Sheet1",
                "header_mode": "first_row",  # first_row|letters|numbers
                "start_row": 1,
                "usecols": "",
                "dataframe": "df_main",
                "dtype": "str",
                "include_service_columns": False,
                "from_file_mode": "basename",  # basename|fullpath
                "date_file_mode": "modified",  # modified|created
            },
        )
    )

