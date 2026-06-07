from __future__ import annotations

from typing import Any

from app.pipeline.context import RunContext
from app.pipeline.registry import REGISTRY, StepDefinition
from app.pipeline.schema import Step
from app.steps.run_command_util import (
    build_env,
    execute_command,
    normalize_command,
    parse_timeout,
    resolve_script_argv,
    truncate_log,
)
from app.steps.util import get_required_param, param_is_on


def _set_var(ctx: RunContext, name: str, value: Any) -> None:
    var = str(name or "").strip()
    if var:
        ctx.variables[var] = value


def _resolve_cmd_from_params(p: dict[str, Any]) -> tuple[list[str] | str, bool]:
    op = str(p.get("operation", "command")).strip().lower()
    shell = param_is_on(p.get("shell", False))

    if op == "command":
        cmd = normalize_command(get_required_param(p, "command"))
        if isinstance(cmd, list) and shell:
            raise ValueError(
                "run_command: shell=on совместим только со строковой command; "
                "для argv-списка отключите shell"
            )
        return cmd, shell

    if op == "script":
        script_path = str(get_required_param(p, "script_path") or "").strip()
        if not script_path:
            raise ValueError("run_command script: задайте script_path")
        raw_args = p.get("script_args") or []
        if isinstance(raw_args, str):
            script_args = [raw_args] if raw_args.strip() else []
        elif isinstance(raw_args, list):
            script_args = raw_args
        else:
            raise ValueError("script_args должен быть списком или строкой")
        interpreter = str(p.get("interpreter", "") or "").strip() or None
        argv = resolve_script_argv(script_path, script_args, interpreter=interpreter)
        if shell:
            raise ValueError("run_command script: не используйте shell=on — задайте interpreter при необходимости")
        return argv, False

    raise ValueError(
        f"run_command: неизвестная operation {op!r}. Используйте command или script."
    )


def run_run_command(ctx: RunContext, step: Step) -> None:
    p = step.params
    cmd, shell = _resolve_cmd_from_params(p)

    cwd_raw = str(p.get("cwd", "") or "").strip()
    cwd = cwd_raw or None
    env = build_env(p.get("env"))
    timeout = parse_timeout(p.get("timeout"))
    capture = param_is_on(p.get("capture_output", True))
    fail_on_error = param_is_on(p.get("fail_on_error", True))

    cmd_repr = cmd if isinstance(cmd, str) else " ".join(cmd)
    ctx.logger.info(f"run_command: запуск ({'shell' if shell else 'argv'}): {cmd_repr}")

    result = execute_command(
        cmd,
        shell=shell,
        cwd=cwd,
        env=env,
        timeout=timeout,
        capture_output=capture,
    )

    stdout = result.stdout if capture else ""
    stderr = result.stderr if capture else ""
    exit_code = int(result.returncode)

    _set_var(ctx, str(p.get("stdout_var", "") or ""), stdout)
    _set_var(ctx, str(p.get("stderr_var", "") or ""), stderr)
    _set_var(ctx, str(p.get("exit_code_var", "") or ""), exit_code)
    _set_var(ctx, str(p.get("result_var", "") or ""), stdout)

    if stdout:
        ctx.logger.info(f"run_command stdout:\n{truncate_log(stdout)}")
    if stderr:
        ctx.logger.warn(f"run_command stderr:\n{truncate_log(stderr)}")
    ctx.logger.info(f"run_command: завершено, exit_code={exit_code}")

    if fail_on_error and exit_code != 0:
        raise ValueError(
            f"run_command: команда завершилась с кодом {exit_code}"
            + (f"; stderr: {truncate_log(stderr, limit=500)}" if stderr else "")
        )


def register_run_command() -> None:
    REGISTRY.register(
        StepDefinition(
            type="run_command",
            title="Системные команды и скрипты",
            runner=run_run_command,
            default_params={
                "operation": "command",
                "command": "",
                "script_path": "",
                "script_args": [],
                "interpreter": "",
                "shell": False,
                "cwd": "",
                "env": {},
                "timeout": None,
                "capture_output": True,
                "fail_on_error": True,
                "stdout_var": "",
                "stderr_var": "",
                "exit_code_var": "",
                "result_var": "",
            },
        )
    )
