from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from app.pipeline.context import RunContext
from app.pipeline.schema import Step


StepRunner = Callable[[RunContext, Step], None]


@dataclass(frozen=True)
class StepDefinition:
    type: str
    title: str
    runner: StepRunner
    default_params: dict[str, Any]


class StepRegistry:
    def __init__(self):
        self._defs: dict[str, StepDefinition] = {}
        self._aliases: dict[str, str] = {}

    def register(self, d: StepDefinition) -> None:
        self._defs[d.type] = d

    def get(self, step_type: str) -> StepDefinition:
        t = self._aliases.get(step_type, step_type)
        return self._defs[t]

    def alias(self, alias_type: str, target_type: str) -> None:
        """Map alias step type to an existing registered step type."""
        if target_type not in self._defs:
            raise KeyError(f"Cannot alias to unknown step type: {target_type}")
        self._aliases[alias_type] = target_type

    def list(self) -> list[StepDefinition]:
        return sorted(self._defs.values(), key=lambda x: x.title.lower())

    def has(self, step_type: str) -> bool:
        return step_type in self._defs or step_type in self._aliases


REGISTRY = StepRegistry()

