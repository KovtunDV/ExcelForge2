from __future__ import annotations

import os
import shutil
import subprocess
import sys
from typing import Any


def normalize_command(cmd: Any) -> list[str] | str:
    """Строка (shell) или argv-список для subprocess."""
    if isinstance(cmd, str):
        s = cmd.strip()
        if not s:
            raise ValueError("command не может быть пустым")
        return s
    if isinstance(cmd, list):
        if not cmd:
            raise ValueError("command (список) не может быть пустым")
        return [str(x) for x in cmd]
    raise ValueError("command должен быть строкой или списком")


def parse_timeout(raw: Any) -> float | None:
    if raw is None or raw == "":
        return None
    try:
        val = float(raw)
    except (TypeError, ValueError) as e:
        raise ValueError(f"timeout должен быть числом секунд, получено: {raw!r}") from e
    if val <= 0:
        raise ValueError("timeout должен быть положительным числом")
    return val


def build_env(extra: dict[str, Any] | None) -> dict[str, str]:
    env = dict(os.environ)
    if not extra:
        return env
    if not isinstance(extra, dict):
        raise ValueError("env должен быть объектом ключ→значение")
    for key, value in extra.items():
        env[str(key)] = str(value)
    return env


def resolve_script_argv(
    script_path: str,
    script_args: list[Any] | None = None,
    *,
    interpreter: str | None = None,
) -> list[str]:
    """Собирает argv для запуска скрипта с учётом ОС и расширения файла."""
    path = os.path.abspath(str(script_path).strip())
    if not path:
        raise ValueError("script_path не может быть пустым")
    if not os.path.isfile(path):
        raise ValueError(f"скрипт не найден: {path}")

    args = [str(a) for a in (script_args or [])]

    if interpreter and str(interpreter).strip():
        return [str(interpreter).strip(), path, *args]

    ext = os.path.splitext(path)[1].lower()

    if ext == ".py":
        return [sys.executable, path, *args]

    if ext == ".sh":
        if os.name == "nt":
            bash = shutil.which("bash")
            if not bash:
                raise ValueError(
                    "скрипт .sh на Windows: установите Git Bash/WSL или задайте interpreter: bash"
                )
            return [bash, path, *args]
        sh = shutil.which("sh") or "/bin/sh"
        return [sh, path, *args]

    if ext in (".bat", ".cmd"):
        if os.name != "nt":
            raise ValueError(".bat/.cmd поддерживаются только на Windows")
        return ["cmd", "/c", path, *args]

    if ext == ".ps1":
        if os.name != "nt":
            raise ValueError(".ps1 поддерживается только на Windows")
        ps = shutil.which("powershell") or shutil.which("pwsh")
        if not ps:
            raise ValueError("PowerShell не найден в PATH")
        return [ps, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", path, *args]

    if os.name != "nt" and os.access(path, os.X_OK):
        return [path, *args]

    raise ValueError(
        f"неизвестное расширение скрипта {ext!r}; задайте interpreter явно "
        "(например python, bash, cmd)"
    )


def execute_command(
    cmd: list[str] | str,
    *,
    shell: bool,
    cwd: str | None,
    env: dict[str, str],
    timeout: float | None,
    capture_output: bool,
) -> subprocess.CompletedProcess[str]:
    if cwd:
        cwd = os.path.abspath(cwd)
        if not os.path.isdir(cwd):
            raise ValueError(f"рабочий каталог не найден: {cwd}")

    try:
        return subprocess.run(
            cmd,
            shell=shell,
            cwd=cwd,
            env=env,
            capture_output=capture_output,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as e:
        raise ValueError(f"команда прервана по timeout ({timeout} с)") from e
    except FileNotFoundError as e:
        raise ValueError(f"исполняемый файл не найден: {e}") from e
    except OSError as e:
        raise ValueError(f"ошибка запуска команды: {e}") from e


def truncate_log(text: str | None, *, limit: int = 2000) -> str:
    if not text:
        return ""
    s = str(text)
    if len(s) <= limit:
        return s
    return s[:limit] + f"... (ещё {len(s) - limit} символов)"
