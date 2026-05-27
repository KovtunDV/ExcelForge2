from __future__ import annotations

import json
import os
from dataclasses import dataclass, asdict
from pathlib import Path


def _settings_path() -> Path:
    """
    Путь к пользовательским настройкам.
    Windows: %APPDATA%\\ExcelForge\\settings.json
    Fallback: ~/.excelforge/settings.json
    """
    appdata = os.environ.get("APPDATA")
    if appdata:
        return Path(appdata) / "ExcelForge" / "settings.json"
    return Path.home() / ".excelforge" / "settings.json"


@dataclass
class AppSettings:
    preview_rows: int = 10
    font_family: str = ""
    font_size: int = 10
    pipelines_dir: str = ""


def bundled_pipelines_dir() -> str:
    """Каталог pipelines рядом с рабочей директорией запуска."""
    return os.path.abspath(os.path.join(os.getcwd(), "pipelines"))


def normalize_pipelines_dir(path: str) -> str:
    """Абсолютный путь без завершающих пробелов; пустая строка — «не задано»."""
    return os.path.abspath(path.strip()) if path and path.strip() else ""


def effective_pipelines_dir(settings: AppSettings | None = None) -> str:
    """Сохранённый каталог пайплайнов или bundled_pipelines_dir() по умолчанию."""
    s = settings if settings is not None else load_settings()
    raw = normalize_pipelines_dir(s.pipelines_dir)
    target = raw or bundled_pipelines_dir()
    os.makedirs(target, exist_ok=True)
    return target


_CACHE: AppSettings | None = None


def load_settings() -> AppSettings:
    global _CACHE
    if _CACHE is not None:
        return _CACHE
    p = _settings_path()
    s = AppSettings()
    try:
        if p.is_file():
            data = json.loads(p.read_text(encoding="utf-8") or "{}")
            if isinstance(data, dict):
                s.preview_rows = int(data.get("preview_rows", s.preview_rows) or s.preview_rows)
                s.preview_rows = max(1, min(s.preview_rows, 5000))
                s.font_family = str(data.get("font_family", s.font_family) or "")
                s.font_size = int(data.get("font_size", s.font_size) or s.font_size)
                s.font_size = max(6, min(s.font_size, 48))
                s.pipelines_dir = normalize_pipelines_dir(
                    str(data.get("pipelines_dir", s.pipelines_dir) or "")
                )
    except Exception:
        # Ignore corrupt settings; use defaults.
        pass
    _CACHE = s
    return s


def save_settings(s: AppSettings) -> None:
    global _CACHE
    p = _settings_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(asdict(s), ensure_ascii=False, indent=2), encoding="utf-8")
    _CACHE = s


def update_settings(**kwargs: object) -> AppSettings:
    s = load_settings()
    for k, v in kwargs.items():
        if hasattr(s, k):
            setattr(s, k, v)  # type: ignore[arg-type]
    save_settings(s)
    return s

