from __future__ import annotations

from pathlib import Path

_DOCS_PATH = Path(__file__).resolve().parent / "pipeline_steps.md"

_DIALOGS_SECTION_HEADING = "### Параметр dialogs"

_STEPS_WITH_DIALOGS = frozenset({
    "globals_settings",
    "load_excel",
    "save_excel",
    "file_ops",
    "group_template_export",
})


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


def get_dialogs_section() -> str:
    """Блок справки по параметру dialogs из введения документации."""
    lines = _read_all().splitlines()
    start: int | None = None
    for i, line in enumerate(lines):
        if line.strip() == _DIALOGS_SECTION_HEADING:
            start = i
            break
    if start is None:
        return ""

    end = len(lines)
    for j in range(start + 1, len(lines)):
        stripped = lines[j].strip()
        if stripped == "---":
            end = j
            break
        if stripped.startswith("## ") and not stripped.startswith("### "):
            end = j
            break
    return "\n".join(lines[start:end]).strip()


def get_section_for_step(step_type: str) -> str:
    """
    Возвращает фрагмент Markdown для шага: блок после заголовка `## <step_type>`
    до следующего заголовка `## ...`. Для шагов с `dialogs` добавляет полное
    описание параметра в конец страницы.
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

    if step_type in _STEPS_WITH_DIALOGS:
        dialogs = get_dialogs_section()
        if dialogs:
            anchor = '<a id="parameter-dialogs"></a>\n\n'
            body = f"{body}\n\n---\n\n{anchor}{dialogs}".strip()

    return f"{header}\n\n{body}" if body else f"{header}\n\n(раздел пуст)"
