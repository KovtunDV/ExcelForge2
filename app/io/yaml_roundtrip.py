from __future__ import annotations

from io import StringIO
from typing import Any

from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedMap, CommentedSeq


def create_yaml() -> YAML:
    """Round-trip YAML: сохраняет inline-комментарии (# пояснение)."""
    y = YAML()
    y.default_flow_style = False
    y.preserve_quotes = True
    y.width = 4096
    return y


def to_plain_dict(obj: Any) -> Any:
    if isinstance(obj, CommentedMap):
        return {k: to_plain_dict(v) for k, v in obj.items()}
    if isinstance(obj, CommentedSeq):
        return [to_plain_dict(v) for v in obj]
    return obj


def ensure_commented_map(obj: Any) -> CommentedMap:
    if isinstance(obj, CommentedMap):
        return obj
    if isinstance(obj, dict):
        return CommentedMap(obj)
    raise ValueError("YAML params должен быть словарём (mapping).")


def load_mapping_from_str(text: str) -> CommentedMap:
    y = create_yaml()
    data = y.load(text or "")
    if data is None:
        return CommentedMap()
    return ensure_commented_map(data)


def dump_mapping_to_str(data: Any) -> str:
    y = create_yaml()
    stream = StringIO()
    y.dump(data, stream)
    text = stream.getvalue()
    if not text.strip():
        return ""
    return text.rstrip("\n") + "\n"


def params_yaml_from_raw(params_raw: Any) -> str:
    if not params_raw:
        return ""
    return dump_mapping_to_str(params_raw)


def params_text_for_editor(params: dict[str, Any], params_yaml: str) -> str:
    if str(params_yaml or "").strip():
        return str(params_yaml).replace("\r\n", "\n").rstrip("\n")
    return dump_mapping_to_str(params or {}).rstrip("\n")
