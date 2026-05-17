from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pandas as pd

from app.pipeline.log import MemoryLogger


@dataclass
class RunContext:
    df_store: dict[str, pd.DataFrame] = field(default_factory=dict)
    variables: dict[str, Any] = field(default_factory=dict)
    logger: MemoryLogger = field(default_factory=MemoryLogger)
    cancelled: bool = False

    def cancel(self) -> None:
        self.cancelled = True

