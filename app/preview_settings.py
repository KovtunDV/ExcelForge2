"""Общая настройка окна предпросмотра DataFrame при отладке пайплайна (не сохраняется в YAML)."""

from __future__ import annotations

from app.settings import load_settings, save_settings


def get_preview_rows() -> int:
    s = load_settings()
    return max(1, min(int(s.preview_rows), 5000))


def set_preview_rows(n: object) -> None:
    s = load_settings()
    try:
        s.preview_rows = max(1, min(int(n), 5000))
    except (TypeError, ValueError):
        s.preview_rows = 10
    save_settings(s)
