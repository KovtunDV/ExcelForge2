from __future__ import annotations

import os
from typing import Any

from app.pipeline.context import RunContext
from app.pipeline.registry import REGISTRY, StepDefinition
from app.pipeline.schema import Step
from app.steps.file_ops_util import (
    copy_file,
    copy_files_batch,
    create_zip_archive,
    delete_path,
    ensure_dir,
    ensure_parent_dir,
    extract_zip_archive,
    move_file,
    parse_on_conflict,
    resolve_dest_path,
    resolve_source_files,
)
from app.steps.util import param_is_on


def _ensure_dirs_enabled(p: dict[str, Any]) -> bool:
    return param_is_on(p.get("ensure_dirs", True))


def _log(ctx: RunContext, msg: str) -> None:
    ctx.logger.info(msg)


def _set_result_var(ctx: RunContext, p: dict[str, Any], path: str) -> None:
    var = str(p.get("result_var", "") or "").strip()
    if var:
        ctx.variables[var] = path


def _run_copy_or_move(ctx: RunContext, p: dict[str, Any], *, move: bool) -> None:
    ensure_dirs = _ensure_dirs_enabled(p)
    source_path = str(p.get("source_path", "") or "").strip()
    if not source_path:
        raise ValueError("file_ops copy/move: задайте source_path")

    dest_path = str(p.get("dest_path", "") or "").strip()
    dest_dir = str(p.get("dest_dir", "") or "").strip()
    if not dest_path and not dest_dir:
        raise ValueError("file_ops copy/move: задайте dest_dir или dest_path")
    inc_start = int(p.get("inc_start", 1))
    out = resolve_dest_path(
        p,
        dest_dir=dest_dir,
        source_basename=os.path.basename(source_path),
        inc=inc_start,
    )

    if ensure_dirs:
        ensure_parent_dir(out)

    if move:
        move_file(source_path, out, ensure_dirs=False)
        _log(ctx, f"file_ops: moved {source_path} -> {out}")
    else:
        copy_file(source_path, out, ensure_dirs=False)
        _log(ctx, f"file_ops: copied {source_path} -> {out}")

    _set_result_var(ctx, p, out)


def _run_delete(ctx: RunContext, p: dict[str, Any]) -> None:
    mode = str(p.get("source_mode", "file")).strip().lower()
    if mode == "file":
        path = str(p.get("source_path", "") or "").strip()
        if not path:
            raise ValueError("file_ops delete: задайте source_path")
        delete_path(path)
        _log(ctx, f"file_ops: deleted {path}")
        _set_result_var(ctx, p, os.path.abspath(path))
        return

    sources = resolve_source_files(p, step_label="file_ops delete")
    last = ""
    for sf in sources:
        delete_path(sf.path)
        _log(ctx, f"file_ops: deleted {sf.path}")
        last = sf.path
    if last:
        _set_result_var(ctx, p, last)


def _run_copy_latest(ctx: RunContext, p: dict[str, Any]) -> None:
    ensure_dirs = _ensure_dirs_enabled(p)
    copy_p = dict(p)
    copy_p["source_mode"] = "latest"
    sources = resolve_source_files(copy_p, step_label="file_ops copy_latest")
    sf = sources[0]

    dest_dir = str(p.get("dest_dir", "") or "").strip()
    if not dest_dir:
        raise ValueError("file_ops copy_latest: задайте dest_dir")

    if ensure_dirs:
        ensure_dir(dest_dir)

    inc_start = int(p.get("inc_start", 1))
    dest = resolve_dest_path(
        p,
        dest_dir=dest_dir,
        source_basename=os.path.basename(sf.path),
        inc=inc_start,
    )
    if ensure_dirs:
        ensure_parent_dir(dest)

    copy_file(sf.path, dest, ensure_dirs=False)
    _log(ctx, f"file_ops: copy_latest {sf.path} -> {dest}")
    _set_result_var(ctx, p, dest)


def _run_copy_by_mask(ctx: RunContext, p: dict[str, Any]) -> None:
    ensure_dirs = _ensure_dirs_enabled(p)
    copy_p = dict(p)
    copy_p["source_mode"] = "mask"
    sources = resolve_source_files(copy_p, step_label="file_ops copy_by_mask")

    dest_dir = str(p.get("dest_dir", "") or "").strip()
    if not dest_dir:
        raise ValueError("file_ops copy_by_mask: задайте dest_dir")

    if ensure_dirs:
        ensure_dir(dest_dir)

    directory = str(p.get("directory", "") or "").strip()
    preserve = param_is_on(p.get("preserve_structure", False))
    on_conflict = parse_on_conflict(p.get("on_conflict"))

    results = copy_files_batch(
        sources,
        dest_dir,
        p,
        source_root=directory if preserve else "",
        preserve_structure=preserve,
        on_conflict=on_conflict,
        ensure_dirs=ensure_dirs,
        log=lambda m: _log(ctx, m),
    )
    if results:
        _set_result_var(ctx, p, results[-1].dest)
    _log(ctx, f"file_ops: copy_by_mask done, files={len(results)}")


def _run_zip_create(ctx: RunContext, p: dict[str, Any]) -> None:
    ensure_dirs = _ensure_dirs_enabled(p)
    source_mode = str(p.get("source_mode", "mask")).strip().lower()
    sources = resolve_source_files(p, source_mode=source_mode, step_label="file_ops zip_create")

    dest_dir = str(p.get("dest_dir", "") or "").strip()
    dest_path = str(p.get("dest_path", "") or "").strip()
    if not dest_dir and not dest_path:
        raise ValueError("file_ops zip_create: задайте dest_dir или dest_path")
    archive_path = resolve_dest_path(p, dest_dir=dest_dir, source_basename="archive.zip")

    directory = str(p.get("directory", "") or "").strip()
    preserve = param_is_on(p.get("preserve_structure", False))

    out = create_zip_archive(
        sources,
        archive_path,
        source_root=directory if preserve else "",
        preserve_structure=preserve,
        ensure_dirs=ensure_dirs,
        log=lambda m: _log(ctx, m),
    )
    _set_result_var(ctx, p, out)


def _run_zip_extract(ctx: RunContext, p: dict[str, Any]) -> None:
    ensure_dirs = _ensure_dirs_enabled(p)
    archive_path = str(p.get("source_path", "") or "").strip()
    if not archive_path:
        raise ValueError("file_ops zip_extract: задайте source_path (архив)")

    dest_dir = str(p.get("dest_dir", "") or "").strip()
    if not dest_dir:
        raise ValueError("file_ops zip_extract: задайте dest_dir")

    extracted = extract_zip_archive(
        archive_path,
        dest_dir,
        ensure_dirs=ensure_dirs,
        log=lambda m: _log(ctx, m),
    )
    if extracted:
        _set_result_var(ctx, p, extracted[-1])


def run_file_ops(ctx: RunContext, step: Step) -> None:
    p = step.params
    op = str(p.get("operation", "copy")).strip().lower()

    if op == "copy":
        _run_copy_or_move(ctx, p, move=False)
    elif op == "move":
        _run_copy_or_move(ctx, p, move=True)
    elif op == "delete":
        _run_delete(ctx, p)
    elif op == "copy_latest":
        _run_copy_latest(ctx, p)
    elif op == "copy_by_mask":
        _run_copy_by_mask(ctx, p)
    elif op == "zip_create":
        _run_zip_create(ctx, p)
    elif op == "zip_extract":
        _run_zip_extract(ctx, p)
    else:
        raise ValueError(
            f"file_ops: неизвестная operation {op!r}. "
            "Используйте copy, move, delete, copy_latest, copy_by_mask, zip_create, zip_extract."
        )


def register_file_ops() -> None:
    REGISTRY.register(
        StepDefinition(
            type="file_ops",
            title="Операции с файлами",
            runner=run_file_ops,
            default_params={
                "operation": "copy",
                "source_mode": "file",
                "source_path": "",
                "files": [],
                "directory": "",
                "pattern": "*.*",
                "patterns": [],
                "recursive": False,
                "include_dirs": [],
                "exclude_dirs": [],
                "dest_dir": "",
                "dest_path": "",
                "dest_name": "",
                "filename": "",
                "prefix": "",
                "suffix": "",
                "extension": "",
                "filename_mask": "",
                "inc_start": 1,
                "inc_step": 1,
                "inc_position": False,
                "preserve_structure": False,
                "on_conflict": "overwrite",
                "ensure_dirs": True,
                "result_var": "",
                "dialogs": [],
                "directory_initial": "",
                "filetypes": [],
                "file_open_dialog": False,
                "file_open_dialog_help": "Выберите файл",
                "directory_open_dialog": False,
                "directory_open_dialog_help": "Выберите каталог",
            },
        )
    )
