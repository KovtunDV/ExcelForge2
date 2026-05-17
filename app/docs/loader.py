from __future__ import annotations

from pathlib import Path

_DOCS_PATH = Path(__file__).resolve().parent / "pipeline_steps.md"


def _read_all() -> str:
    if not _DOCS_PATH.is_file():
        return f"(Файл документации не найден: {_DOCS_PATH})"
    return _DOCS_PATH.read_text(encoding="utf-8")


def get_intro() -> str:
    """Текст до первого заголовка ## (общее введение)."""
    text = _read_all()
    lines = text.splitlines()
    first_section = None
    for i, line in enumerate(lines):
        if line.startswith("## ") and len(line) > 3:
            first_section = i
            break
    if first_section is None:
        return text.strip()
    return "\n".join(lines[:first_section]).strip()


def get_section_for_step(step_type: str) -> str:
    """
    Возвращает фрагмент Markdown для шага: блок после заголовка `## <step_type>`
    до следующего заголовка `## ...`.
    """
    step_type = (step_type or "").strip()
    if not step_type:
        return "Тип шага не задан."

    text = _read_all()
    lines = text.splitlines()
    header = f"## {step_type}"
    start: int | None = None
    for i, line in enumerate(lines):
        if line.strip() == header:
            start = i + 1
            break
    if start is None:
        intro = get_intro()
        return (
            f"Раздел `{header}` не найден в файле документации.\n\n"
            f"---\n\nОбщая справка:\n\n{intro}"
        )

    end = len(lines)
    for j in range(start, len(lines)):
        if lines[j].startswith("## ") and lines[j].strip() != header:
            end = j
            break
    body = "\n".join(lines[start:end]).strip()
    return f"{header}\n\n{body}" if body else f"{header}\n\n(раздел пуст)"
