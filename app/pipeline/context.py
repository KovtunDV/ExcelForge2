from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pandas as pd

from app.pipeline.global_context import SessionDfStore
from app.pipeline.log import MemoryLogger


@dataclass
class RunContext:
    df_store: dict[str, pd.DataFrame] = field(default_factory=dict)
    variables: dict[str, Any] = field(default_factory=dict)
    logger: MemoryLogger = field(default_factory=MemoryLogger)
    cancelled: bool = False

    def cancel(self) -> None:
        self.cancelled = True


def create_run_context(
    *,
    df_store: dict[str, pd.DataFrame] | None = None,
    variables: dict[str, Any] | None = None,
    logger: MemoryLogger | None = None,
) -> RunContext:
    """
    Создать контекст выполнения пайплайна.

    По умолчанию df_store — SessionDfStore с подгрузкой glob_* из сессии.
    Явный df_store (отладка Builder) передаётся без замены.
    """
    log = logger or MemoryLogger()
    if df_store is None:
        store: dict[str, pd.DataFrame] = SessionDfStore(logger=log)
    else:
        store = df_store
        if isinstance(store, SessionDfStore):
            store.set_logger(log)
    return RunContext(
        df_store=store,
        variables=dict(variables) if variables is not None else {},
        logger=log,
    )
