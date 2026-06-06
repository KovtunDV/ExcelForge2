from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from app.pipeline.context import RunContext
from app.pipeline.registry import REGISTRY
from app.pipeline.schema import Pipeline, Step
from app.steps.step_dialogs import resolve_params


ProgressCallback = Callable[[int, int, Step], None]


class StepExecutionError(RuntimeError):
    pass


@dataclass(frozen=True)
class RunResult:
    ok: bool
    executed_steps: int
    error: str | None = None


def run_pipeline(
    pipeline: Pipeline,
    ctx: RunContext,
    on_progress: ProgressCallback | None = None,
    stop_after_step_index: int | None = None,
) -> RunResult:
    pipeline.validate()
    total = len(pipeline.steps)
    executed = 0
    ctx.logger.info(f"Start pipeline: {pipeline.name} (steps={total})")

    for idx, step in enumerate(pipeline.steps, start=1):
        if ctx.cancelled:
            ctx.logger.warn("Pipeline cancelled by user.")
            return RunResult(ok=False, executed_steps=executed, error="cancelled")

        if on_progress:
            on_progress(idx, total, step)

        ctx.logger.info(f"[{idx}/{total}] Step {step.id}: {step.type}")
        if not REGISTRY.has(step.type):
            msg = f"Unknown step type: {step.type}"
            ctx.logger.error(msg)
            return RunResult(ok=False, executed_steps=executed, error=msg)

        try:
            orig_params = step.params
            try:
                step.params = resolve_params(ctx, orig_params, step_type=step.type)
                REGISTRY.get(step.type).runner(ctx, step)
            finally:
                step.params = orig_params
        except Exception as e:  # noqa: BLE001 - surface error in UI
            msg = f"Step {step.id} failed: {e}"
            ctx.logger.error(msg)
            return RunResult(ok=False, executed_steps=executed, error=msg)

        executed += 1
        if stop_after_step_index is not None and idx >= stop_after_step_index:
            ctx.logger.info(
                f"Pipeline preview stop requested at step {idx}/{total}."
            )
            return RunResult(ok=True, executed_steps=executed, error=None)

    ctx.logger.info("Pipeline finished successfully.")
    return RunResult(ok=True, executed_steps=executed, error=None)

