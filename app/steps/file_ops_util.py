from __future__ import annotations

import fnmatch
import glob
import os
import shutil
import stat
import tempfile
import time
import zipfile
from dataclasses import dataclass
from typing import Any, Callable

from app.steps.excel_template import build_output_filename, safe_filename
from app.steps.util import (
    ScannedFile,
    pick_latest_by_mtime,
    scan_single_file,
)


OnConflict = str  # overwrite | skip | rename
LogFn = Callable[[str], None]
_ZIP_MIN_MTIME = 315532800.0  # 1980-01-01 UTC — минимум для zipfile
_ARCHIVE_FILE_EXTENSIONS = {".zip", ".7z", ".tar", ".gz", ".bz2", ".rar"}


def _path_key(path: str) -> str:
    return os.path.normcase(os.path.abspath(path))


def _remove_existing_file(path: str) -> None:
    if not os.path.isfile(path):
        return
    try:
        os.chmod(path, stat.S_IWRITE | stat.S_IREAD)
    except OSError:
        pass
    os.remove(path)


@dataclass(frozen=True)
class CopyResult:
    source: str
    dest: str
    action: str  # copied | skipped | renamed


def parse_patterns(raw: Any, *, fallback: str = "*.*") -> list[str]:
    """Одна маска (строка) или список масок."""
    if raw is None or raw == "" or raw == []:
        pat = str(fallback or "*.*").strip()
        return [pat] if pat else ["*.*"]
    if isinstance(raw, list):
        out = [str(x).strip() for x in raw if str(x).strip()]
        if not out:
            raise ValueError("patterns: непустой список масок")
        return out
    s = str(raw).strip()
    if not s:
        return [fallback or "*.*"]
    return [s]


def parse_file_list(raw: Any) -> list[str]:
    if raw is None or raw == "" or raw == []:
        return []
    if not isinstance(raw, list):
        raise ValueError("files: ожидается список путей")
    out = [os.path.abspath(str(x).strip()) for x in raw if str(x).strip()]
    if not out:
        raise ValueError("files: непустой список путей")
    return out


def parse_dir_patterns(raw: Any) -> list[str]:
    if raw is None or raw == "" or raw == []:
        return []
    if isinstance(raw, list):
        return [str(x).strip() for x in raw if str(x).strip()]
    s = str(raw).strip()
    return [s] if s else []


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


def _dir_name_matches(name: str, patterns: list[str]) -> bool:
    if not patterns:
        return True
    return any(fnmatch.fnmatch(name, pat) for pat in patterns)


def _should_prune_dir(dirname: str, include_dirs: list[str], exclude_dirs: list[str]) -> bool:
    if exclude_dirs and _dir_name_matches(dirname, exclude_dirs):
        return True
    if include_dirs and not _dir_name_matches(dirname, include_dirs):
        return True
    return False


def scan_directory_files_filtered(
    directory: str,
    patterns: list[str],
    *,
    recursive: bool = False,
    include_dirs: list[str] | None = None,
    exclude_dirs: list[str] | None = None,
) -> list[ScannedFile]:
    """Поиск файлов по маскам с фильтрацией вложенных каталогов."""
    root = os.path.abspath(directory)
    if not os.path.isdir(root):
        raise ValueError(f"Каталог не найден: {root}")

    inc = include_dirs or []
    exc = exclude_dirs or []
    scanned: list[ScannedFile] = []
    seen: set[str] = set()

    def _match_and_add(path: str) -> None:
        name = os.path.basename(path)
        if not any(fnmatch.fnmatch(name, pat) for pat in patterns):
            return
        ap = os.path.abspath(path)
        if ap in seen:
            return
        seen.add(ap)
        _append_scanned_file(scanned, ap)

    if recursive:
        for dirpath, dirnames, filenames in os.walk(root):
            rel = os.path.relpath(dirpath, root)
            if rel != ".":
                parts = rel.split(os.sep)
                if any(_should_prune_dir(part, inc, exc) for part in parts):
                    dirnames[:] = []
                    continue
            if inc or exc:
                kept: list[str] = []
                for d in dirnames:
                    if _should_prune_dir(d, inc, exc):
                        continue
                    kept.append(d)
                dirnames[:] = kept
            for name in filenames:
                _match_and_add(os.path.join(dirpath, name))
    else:
        for pat in patterns:
            for path in glob.glob(os.path.join(root, pat)):
                _match_and_add(path)

    scanned.sort(key=lambda f: f.path)
    return scanned


def resolve_source_files(
    p: dict[str, Any],
    *,
    source_mode: str | None = None,
    step_label: str = "file_ops",
) -> list[ScannedFile]:
    mode = str(source_mode or p.get("source_mode", "file")).strip().lower()

    if mode == "file":
        path = str(p.get("source_path", "") or "").strip()
        if not path:
            raise ValueError(f"{step_label}: задайте source_path")
        return [scan_single_file(path)]

    if mode == "files":
        paths = parse_file_list(p.get("files"))
        return [scan_single_file(path) for path in paths]

    directory = str(p.get("directory", "") or "").strip()
    if not directory:
        raise ValueError(f"{step_label}: задайте directory")

    patterns = parse_patterns(p.get("patterns") or p.get("pattern"))
    recursive = bool(p.get("recursive", False))
    include_dirs = parse_dir_patterns(p.get("include_dirs"))
    exclude_dirs = parse_dir_patterns(p.get("exclude_dirs"))

    found = scan_directory_files_filtered(
        directory,
        patterns,
        recursive=recursive,
        include_dirs=include_dirs,
        exclude_dirs=exclude_dirs,
    )
    if not found:
        raise ValueError(
            f"{step_label}: файлы не найдены в {directory!r} по маскам {patterns!r}"
        )

    if mode == "latest":
        latest = pick_latest_by_mtime(found)
        if latest is None:
            raise ValueError(f"{step_label}: не удалось выбрать самый свежий файл")
        return [latest]

    return found


def parse_inc_position(raw: Any) -> str | None:
    if raw is None:
        return None
    if isinstance(raw, bool):
        return "prefix" if raw else None
    s = str(raw).strip().lower()
    if s in ("", "false", "0", "no", "off", "none"):
        return None
    if s in ("suffix", "suf", "end", "tail"):
        return "suffix"
    if s in ("prefix", "pref", "start", "begin", "true", "1", "yes", "on"):
        return "prefix"
    raise ValueError(f"inc_position: неизвестное значение {raw!r}")


def _format_filename_mask(
    mask: str,
    *,
    source_basename: str,
    inc: int | None,
) -> str:
    stem, ext = os.path.splitext(source_basename)
    ext_with_dot = ext if ext.startswith(".") else (f".{ext}" if ext else "")
    return (
        mask.replace("{name}", source_basename)
        .replace("{stem}", stem)
        .replace("{ext}", ext_with_dot.lstrip("."))
        .replace("{inc}", str(inc) if inc is not None else "")
    )


def _has_dest_name_parts(p: dict[str, Any]) -> bool:
    return bool(
        str(p.get("dest_name") or p.get("filename") or "").strip()
        or str(p.get("prefix", "") or "").strip()
        or str(p.get("suffix", "") or "").strip()
        or str(p.get("filename_mask", "") or "").strip()
        or str(p.get("extension", "") or "").strip()
    )


def _dest_path_points_to_directory(raw_dest_path: str, p: dict[str, Any]) -> bool:
    """dest_path — каталог, если это существующая папка, путь с / или без расширения + задано имя файла."""
    if not raw_dest_path:
        return False
    if raw_dest_path.endswith(("/", "\\")):
        return True
    ap = os.path.abspath(raw_dest_path)
    if os.path.isdir(ap):
        return True
    _, ext = os.path.splitext(raw_dest_path)
    if ext and ext.lower() not in _ARCHIVE_FILE_EXTENSIONS:
        return False
    if ext.lower() in _ARCHIVE_FILE_EXTENSIONS:
        return False
    return _has_dest_name_parts(p)


def _build_dest_filename(
    p: dict[str, Any],
    *,
    source_basename: str,
    inc: int | None,
) -> str:
    dest_name = str(p.get("dest_name") or p.get("filename") or "").strip()
    prefix = str(p.get("prefix", "") or "")
    suffix = str(p.get("suffix", "") or "")
    extension = str(p.get("extension", "") or "")
    filename_mask = str(p.get("filename_mask", "") or "").strip()
    inc_position = parse_inc_position(p.get("inc_position"))

    base_name = dest_name or source_basename or "output"
    if filename_mask:
        filename_mask = _format_filename_mask(
            filename_mask,
            source_basename=base_name,
            inc=inc,
        )

    if not extension:
        _, ext = os.path.splitext(base_name)
        extension = ext or ""

    name = build_output_filename(
        prefix=prefix,
        suffix=suffix,
        group_part=dest_name if dest_name else (os.path.splitext(source_basename)[0] if source_basename else ""),
        extension=extension or ".bin",
        mask=filename_mask,
        inc=inc,
        inc_position=inc_position,
    )
    if (
        dest_name
        and not filename_mask
        and not prefix
        and not suffix
        and not inc_position
        and not extension
    ):
        name = safe_filename(dest_name)
    return name


def resolve_dest_path(
    p: dict[str, Any],
    *,
    dest_dir: str,
    source_basename: str = "",
    inc: int | None = None,
) -> str:
    """Собрать полный путь назначения: dest_dir + имя файла или полный dest_path к файлу."""
    raw_dest_path = str(p.get("dest_path", "") or "").strip()
    effective_dir = str(dest_dir or "").strip()

    if raw_dest_path:
        if _dest_path_points_to_directory(raw_dest_path, p):
            effective_dir = os.path.abspath(raw_dest_path)
        else:
            return os.path.abspath(raw_dest_path)

    if not effective_dir:
        raise ValueError("file_ops: задайте dest_dir или dest_path (каталог или полный путь к файлу)")

    name = _build_dest_filename(p, source_basename=source_basename, inc=inc)
    return os.path.join(os.path.abspath(effective_dir), name)


def ensure_parent_dir(path: str) -> None:
    parent = os.path.dirname(os.path.abspath(path))
    if parent:
        os.makedirs(parent, exist_ok=True)


def ensure_dir(path: str) -> None:
    os.makedirs(os.path.abspath(path), exist_ok=True)


def parse_on_conflict(raw: Any) -> OnConflict:
    s = str(raw or "overwrite").strip().lower()
    if s in ("overwrite", "skip", "rename"):
        return s
    raise ValueError(f"on_conflict: неизвестное значение {raw!r}; используйте overwrite, skip, rename")


def _unique_dest_path(path: str) -> str:
    if not os.path.exists(path):
        return path
    base, ext = os.path.splitext(path)
    n = 2
    while True:
        candidate = f"{base}_{n}{ext}"
        if not os.path.exists(candidate):
            return candidate
        n += 1


def _resolve_conflict_path(dest: str, on_conflict: OnConflict) -> tuple[str, str]:
    if not os.path.exists(dest):
        return dest, "copy"
    if on_conflict == "skip":
        return dest, "skip"
    if on_conflict == "rename":
        return _unique_dest_path(dest), "rename"
    return dest, "overwrite"


def copy_file(src: str, dest: str, *, ensure_dirs: bool = True) -> None:
    if ensure_dirs:
        ensure_parent_dir(dest)
    shutil.copy2(src, dest)


def move_file(src: str, dest: str, *, ensure_dirs: bool = True) -> None:
    if ensure_dirs:
        ensure_parent_dir(dest)
    shutil.move(src, dest)


def delete_path(path: str) -> None:
    if not os.path.isfile(path):
        raise ValueError(f"Файл не найден: {path}")
    os.remove(path)


def copy_files_batch(
    sources: list[ScannedFile],
    dest_dir: str,
    p: dict[str, Any],
    *,
    source_root: str = "",
    preserve_structure: bool = False,
    on_conflict: OnConflict = "overwrite",
    ensure_dirs: bool = True,
    log: LogFn | None = None,
) -> list[CopyResult]:
    results: list[CopyResult] = []
    inc_start = int(p.get("inc_start", 1))
    inc_step = int(p.get("inc_step", 1))
    inc_position = parse_inc_position(p.get("inc_position"))
    use_inc = inc_position is not None
    inc_val = inc_start
    root = os.path.abspath(source_root) if source_root else ""

    for sf in sources:
        src = sf.path
        basename = os.path.basename(src)

        if preserve_structure and root:
            rel = os.path.relpath(src, root)
            rel_dir = os.path.dirname(rel)
            target_dir = os.path.join(os.path.abspath(dest_dir), rel_dir) if rel_dir else os.path.abspath(dest_dir)
        else:
            target_dir = os.path.abspath(dest_dir)

        inc_for_file = inc_val if use_inc else None
        dest_name = resolve_dest_path(
            p,
            dest_dir=target_dir,
            source_basename=basename,
            inc=inc_for_file,
        )
        final_dest, action = _resolve_conflict_path(dest_name, on_conflict)

        if action == "skip":
            if log:
                log(f"file_ops: пропуск (существует): {final_dest}")
            results.append(CopyResult(source=src, dest=final_dest, action="skipped"))
            if use_inc:
                inc_val += inc_step
            continue

        if ensure_dirs:
            ensure_parent_dir(final_dest)

        shutil.copy2(src, final_dest)
        action_label = "renamed" if action == "rename" else "copied"
        if log:
            log(f"file_ops: {action_label} {src} -> {final_dest}")
        results.append(CopyResult(source=src, dest=final_dest, action=action_label))
        if use_inc:
            inc_val += inc_step

    return results


def _zip_add_file(zf: zipfile.ZipFile, src: str, arcname: str) -> None:
    """Добавить файл в архив; mtime < 1980 приводится к 1980-01-01 (ограничение ZIP)."""
    mtime = max(os.path.getmtime(src), _ZIP_MIN_MTIME)
    info = zipfile.ZipInfo(arcname, time.localtime(mtime)[:6])
    try:
        with open(src, "rb") as fh:
            data = fh.read()
    except PermissionError as e:
        raise PermissionError(
            f"file_ops zip_create: нет доступа к файлу (закройте его в другой программе): {src}"
        ) from e
    zf.writestr(info, data, compress_type=zipfile.ZIP_DEFLATED)


def create_zip_archive(
    sources: list[ScannedFile],
    archive_path: str,
    *,
    source_root: str = "",
    preserve_structure: bool = False,
    ensure_dirs: bool = True,
    log: LogFn | None = None,
) -> str:
    ap = os.path.abspath(archive_path)
    if os.path.isdir(ap):
        raise ValueError(
            "file_ops zip_create: путь архива указывает на каталог. "
            "Задайте dest_dir + filename/dest_name + extension, либо dest_path как полный путь к .zip: "
            f"{ap}"
        )
    if ensure_dirs:
        ensure_parent_dir(ap)

    archive_abs = os.path.abspath(ap)
    archive_key = _path_key(archive_abs)
    filtered_sources = [sf for sf in sources if _path_key(sf.path) != archive_key]

    root = os.path.abspath(source_root) if source_root else ""
    parent = os.path.dirname(archive_abs) or "."
    tmp_path: str | None = None

    try:
        fd, tmp_path = tempfile.mkstemp(suffix=".zip.part", dir=parent)
        os.close(fd)
        with zipfile.ZipFile(tmp_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            for sf in filtered_sources:
                src = sf.path
                if preserve_structure and root:
                    arcname = os.path.relpath(src, root)
                else:
                    arcname = os.path.basename(src)
                arcname = arcname.replace("\\", "/")
                _zip_add_file(zf, src, arcname)
                if log:
                    log(f"file_ops: zip add {src} as {arcname}")
        if os.path.exists(archive_abs):
            try:
                _remove_existing_file(archive_abs)
            except OSError as e:
                raise PermissionError(
                    f"file_ops zip_create: нет доступа для записи архива "
                    f"(закройте файл или выберите другой путь): {ap}"
                ) from e
        os.replace(tmp_path, archive_abs)
        tmp_path = None
    except PermissionError as e:
        if "нет доступа для записи архива" in str(e):
            raise
        raise PermissionError(
            f"file_ops zip_create: нет доступа для записи архива (закройте файл или выберите другой путь): {ap}"
        ) from e
    finally:
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except OSError:
                pass

    if log:
        log(f"file_ops: archive created {archive_abs}")
    return archive_abs


def extract_zip_archive(
    archive_path: str,
    dest_dir: str,
    *,
    ensure_dirs: bool = True,
    log: LogFn | None = None,
) -> list[str]:
    ap = os.path.abspath(archive_path)
    if not os.path.isfile(ap):
        raise ValueError(f"Архив не найден: {ap}")

    out_dir = os.path.abspath(dest_dir)
    if ensure_dirs:
        ensure_dir(out_dir)

    extracted: list[str] = []
    with zipfile.ZipFile(ap, "r") as zf:
        for info in zf.infolist():
            target = os.path.join(out_dir, info.filename)
            if info.is_dir() or info.filename.endswith("/"):
                if ensure_dirs:
                    ensure_dir(target)
                continue
            if ensure_dirs:
                ensure_parent_dir(target)
            zf.extract(info, out_dir)
            extracted.append(os.path.abspath(target))
            if log:
                log(f"file_ops: extracted {target}")

    if log:
        log(f"file_ops: extracted {len(extracted)} file(s) to {out_dir}")
    return extracted
