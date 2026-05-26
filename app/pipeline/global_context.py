from __future__ import annotations

import weakref
from typing import TYPE_CHECKING

import pandas as pd

if TYPE_CHECKING:
    from app.pipeline.log import MemoryLogger

GLOBAL_DF_PREFIX = "glob_"

_global_store: dict[str, pd.DataFrame] = {}
_session_store_refs: list[weakref.ReferenceType[SessionDfStore]] = []


def _iter_session_stores() -> list[SessionDfStore]:
    alive: list[SessionDfStore] = []
    dead: list[weakref.ReferenceType[SessionDfStore]] = []
    for ref in _session_store_refs:
        store = ref()
        if store is None:
            dead.append(ref)
        else:
            alive.append(store)
    for ref in dead:
        try:
            _session_store_refs.remove(ref)
        except ValueError:
            pass
    return alive


def _register_session_store(store: SessionDfStore) -> None:
    _session_store_refs.append(weakref.ref(store))


def is_global_df_name(name: str) -> bool:
    return str(name or "").startswith(GLOBAL_DF_PREFIX)


def get_global_store() -> dict[str, pd.DataFrame]:
    return _global_store


def list_global_names() -> list[str]:
    return sorted(_global_store.keys(), key=lambda s: s.lower())


def strip_global_from_store(df_store: dict[str, pd.DataFrame]) -> int:
    """Удалить glob_* из переданного хранилища (локальные копии после очистки глобала)."""
    removed = 0
    for key in list(df_store.keys()):
        if is_global_df_name(key):
            try:
                del df_store[key]
                removed += 1
            except KeyError:
                pass
    return removed


def clear_global_store() -> int:
    n = len(_global_store)
    _global_store.clear()
    for store in _iter_session_stores():
        strip_global_from_store(store)
    return n


def list_preview_df_names(df_store: dict[str, pd.DataFrame]) -> list[str]:
    """Имена DF для окна просмотра: локальные + glob_* только из глобального хранилища."""
    names: set[str] = set()
    for key in df_store:
        if not is_global_df_name(key):
            names.add(key)
    names.update(_global_store.keys())
    return sorted(names, key=lambda s: s.lower())


def get_df_for_preview(df_store: dict[str, pd.DataFrame], name: str) -> pd.DataFrame | None:
    if is_global_df_name(name):
        return _global_store.get(name)
    return df_store.get(name)


def reconcile_globals_from_sessions() -> None:
    """Подтянуть glob_* из активных SessionDfStore в глобальное хранилище (для списка в настройках)."""
    for store in _iter_session_stores():
        for key, df in list(store.items()):
            if is_global_df_name(key):
                _global_store[key] = df


def global_df_summary() -> list[tuple[str, int, int]]:
    out: list[tuple[str, int, int]] = []
    for name in list_global_names():
        df = _global_store.get(name)
        if df is None:
            continue
        out.append((name, len(df), len(df.columns)))
    return out


class SessionDfStore(dict[str, pd.DataFrame]):
    """
    Хранилище DF одного запуска пайплайна.
    Имена glob_* синхронизируются с сессионным глобальным хранилищем.
    """

    def __init__(self, *args, logger: MemoryLogger | None = None, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._logger = logger
        _register_session_store(self)
        for name, df in _global_store.items():
            if is_global_df_name(name):
                super().__setitem__(name, df)

    def set_logger(self, logger: MemoryLogger | None) -> None:
        self._logger = logger

    def __setitem__(self, key: str, value: pd.DataFrame) -> None:
        super().__setitem__(key, value)
        if is_global_df_name(key):
            _global_store[key] = value
            if self._logger is not None:
                self._logger.info(
                    f"Global DF updated: {key} (rows={len(value)}, cols={len(value.columns)})"
                )

    def __delitem__(self, key: str) -> None:
        super().__delitem__(key)
        if is_global_df_name(key) and key in _global_store:
            del _global_store[key]

    def pop(self, key: str, default: pd.DataFrame | None = None) -> pd.DataFrame:  # type: ignore[override]
        if key in self:
            value = super().pop(key)
        elif default is not None:
            return default
        else:
            raise KeyError(key)
        if is_global_df_name(key) and key in _global_store:
            del _global_store[key]
        return value

    def update(self, other=(), /, **kwargs) -> None:  # type: ignore[override]
        if hasattr(other, "keys"):
            for key in other:
                self[key] = other[key]  # type: ignore[index]
        else:
            for key, value in other:
                self[key] = value
        for key, value in kwargs.items():
            self[key] = value
