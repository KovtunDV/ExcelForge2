from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QObject, QThread, Signal

from app.pipeline.context import RunContext
from app.pipeline.registry import REGISTRY
from app.pipeline.runner import _resolve_step_params
from app.pipeline.schema import Pipeline, Step


@dataclass
class PipelineRunConfig:
    pipeline: Pipeline
    stop_after_index: int | None = None  # exclusive upper bound (run steps [0, stop_after_index))


class PipelineWorker(QThread):
    """Выполняет шаги пайплайна в фоновом потоке (диалоги — через GuiDialogHost)."""

    step_started = Signal(int, int, str, str)  # index, total, step_id, step_type
    step_finished = Signal(int, int)
    log_event = Signal(object)  # LogEvent
    finished_ok = Signal(object)  # RunContext
    finished_error = Signal(str)
    cancelled = Signal()

    def __init__(self, ctx: RunContext, config: PipelineRunConfig, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._ctx = ctx
        self._config = config

    def run(self) -> None:
        pipeline = self._config.pipeline
        steps = pipeline.steps
        total = len(steps)
        stop = self._config.stop_after_index if self._config.stop_after_index is not None else total
        stop = max(0, min(stop, total))

        self._ctx.logger.info(f"Start pipeline: {pipeline.name} (steps={total})")

        for i in range(stop):
            if self._ctx.cancelled:
                self._ctx.logger.warn("Pipeline cancelled by user.")
                self.cancelled.emit()
                return

            step = steps[i]
            self.step_started.emit(i, total, step.id, step.type)
            self._ctx.logger.info(f"[{i + 1}/{total}] Step {step.id}: {step.type}")

            if not REGISTRY.has(step.type):
                msg = f"Unknown step type: {step.type}"
                self._ctx.logger.error(msg)
                self.finished_error.emit(msg)
                return

            try:
                self._run_step(step)
            except Exception as e:  # noqa: BLE001
                msg = f"Step {step.id} failed: {e}"
                self._ctx.logger.error(msg)
                self.finished_error.emit(msg)
                return

            self.step_finished.emit(i + 1, total)

        if stop >= total:
            self._ctx.logger.info("Pipeline finished successfully.")
        else:
            self._ctx.logger.info(f"Pipeline preview stop requested at step {stop}/{total}.")
        self.finished_ok.emit(self._ctx)

    def _run_step(self, step: Step) -> None:
        orig_params = step.params
        try:
            step.params = _resolve_step_params(orig_params, self._ctx.variables)
            REGISTRY.get(step.type).runner(self._ctx, step)
        finally:
            step.params = orig_params


class SingleStepWorker(QThread):
    """Выполняет один шаг в фоне (для «Проверить шаг»)."""

    finished_ok = Signal(object)
    finished_error = Signal(str)

    def __init__(self, ctx: RunContext, step: Step, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._ctx = ctx
        self._step = step

    def run(self) -> None:
        step = self._step
        if not REGISTRY.has(step.type):
            self.finished_error.emit(f"Unknown step type: {step.type}")
            return
        try:
            self._ctx.logger.info(f"Verify step: {step.id} ({step.type})")
            orig_params = step.params
            try:
                step.params = _resolve_step_params(orig_params, self._ctx.variables)
                REGISTRY.get(step.type).runner(self._ctx, step)
            finally:
                step.params = orig_params
            self._ctx.logger.info("Verify step finished successfully.")
            self.finished_ok.emit(self._ctx)
        except Exception as e:  # noqa: BLE001
            self._ctx.logger.error(f"Verify step failed: {e}")
            self.finished_error.emit(str(e))
