from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


PIPELINE_VERSION = 1


class PipelineValidationError(ValueError):
    pass


@dataclass
class Step:
    id: str
    type: str
    params: dict[str, Any] = field(default_factory=dict)
    comment: str = ""


@dataclass
class Pipeline:
    name: str
    description: str = ""
    steps: list[Step] = field(default_factory=list)
    pipeline_version: int = PIPELINE_VERSION

    def validate(self) -> None:
        if self.pipeline_version != PIPELINE_VERSION:
            raise PipelineValidationError(
                f"Unsupported pipeline_version={self.pipeline_version}, expected {PIPELINE_VERSION}"
            )
        if not self.name.strip():
            raise PipelineValidationError("Pipeline name is required.")
        seen: set[str] = set()
        for step in self.steps:
            if not step.id.strip():
                raise PipelineValidationError("Each step must have non-empty id.")
            if step.id in seen:
                raise PipelineValidationError(f"Duplicate step id: {step.id}")
            seen.add(step.id)
            if not step.type.strip():
                raise PipelineValidationError(f"Step {step.id} must have non-empty type.")

