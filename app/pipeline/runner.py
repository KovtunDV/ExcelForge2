from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any, Callable

from app.pipeline.context import RunContext
from app.pipeline.registry import REGISTRY
from app.pipeline.schema import Pipeline, Step


class StepExecutionError(RuntimeError):
    pass


@dataclass(frozen=True)
class RunResult:
    ok: bool
    executed_steps: int
    error: str | None = None


ProgressCallback = Callable[[int, int, Step], None]


def _resolve_value(v: Any, variables: dict[str, Any]) -> Any:
    if isinstance(v, str):
        s = v.strip()
        # Replace only pure tokens like "@var" (no spaces); keep literal strings intact.
        if s.startswith("@") and len(s) > 1 and " " not in s:
            key = s[1:]
            if key in variables:
                return variables[key]
        if "@" not in v:
            return v

        # Also support embedding: "C:/out/@dir/file.xlsx"
        # Replace occurrences of @name if name exists in variables; embedded values are stringified.
        def _repl(m: re.Match[str]) -> str:
            key = m.group(1)
            if key in variables:
                return str(variables[key])
            return m.group(0)

        return re.sub(r"@([A-Za-z_][A-Za-z0-9_]*)", _repl, v)
    if isinstance(v, list):
        return [_resolve_value(x, variables) for x in v]
    if isinstance(v, dict):
        return {k: _resolve_value(val, variables) for k, val in v.items()}
    return v


def _resolve_step_params(params: dict[str, Any], variables: dict[str, Any]) -> dict[str, Any]:
    # Copy + resolve recursively; do not mutate original pipeline definition.
    return _resolve_value(dict(params), variables)


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
                step.params = _resolve_step_params(orig_params, ctx.variables)
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

