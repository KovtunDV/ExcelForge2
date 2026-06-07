from __future__ import annotations

from typing import Any

from ruamel.yaml.comments import CommentedMap

from app.io.yaml_roundtrip import create_yaml, params_yaml_from_raw, to_plain_dict
from app.pipeline.schema import PIPELINE_VERSION, Pipeline, Step


def pipeline_to_dict(p: Pipeline) -> dict[str, Any]:
    steps_out: list[dict[str, Any]] = []
    for s in p.steps:
        item: dict[str, Any] = {
            "id": s.id,
            "type": s.type,
            "params": dict(s.params or {}),
        }
        if str(getattr(s, "comment", "") or "").strip():
            item["comment"] = str(s.comment)
        steps_out.append(item)

    return {
        "pipeline_version": p.pipeline_version,
        "name": p.name,
        "description": p.description,
        "steps": steps_out,
    }


def pipeline_from_dict(d: dict[str, Any], *, raw_steps: list[Any] | None = None) -> Pipeline:
    steps_raw = d.get("steps", []) or []
    steps: list[Step] = []
    for i, s in enumerate(steps_raw):
        raw_comment = s.get("comment")
        comment = "" if raw_comment is None else str(raw_comment)
        params_raw = raw_steps[i].get("params") if raw_steps and i < len(raw_steps) else s.get("params")
        params_yaml = params_yaml_from_raw(params_raw)
        steps.append(
            Step(
                id=str(s.get("id", "")).strip(),
                type=str(s.get("type", "")).strip(),
                params=to_plain_dict(params_raw or {}),
                comment=comment,
                params_yaml=params_yaml,
            )
        )
    p = Pipeline(
        pipeline_version=int(d.get("pipeline_version", PIPELINE_VERSION)),
        name=str(d.get("name", "")).strip(),
        description=str(d.get("description", "") or ""),
        steps=steps,
    )
    p.validate()
    return p


def load_pipeline_yaml(path: str) -> Pipeline:
    y = create_yaml()
    with open(path, "r", encoding="utf-8") as f:
        data = y.load(f) or {}
    if not isinstance(data, dict):
        raise ValueError("YAML root must be a mapping (dict).")
    raw_steps = list(data.get("steps", []) or [])
    plain = to_plain_dict(data)
    return pipeline_from_dict(plain, raw_steps=raw_steps)


def save_pipeline_yaml(p: Pipeline, path: str) -> None:
    p.validate()
    y = create_yaml()
    steps_out: list[CommentedMap] = []
    for s in p.steps:
        item = CommentedMap()
        item["id"] = s.id
        item["type"] = s.type
        if str(s.params_yaml or "").strip():
            params_cm = y.load(s.params_yaml)
            item["params"] = params_cm if params_cm is not None else CommentedMap()
        else:
            item["params"] = CommentedMap(dict(s.params or {}))
        if str(s.comment or "").strip():
            item["comment"] = s.comment
        steps_out.append(item)

    root = CommentedMap(
        {
            "pipeline_version": p.pipeline_version,
            "name": p.name,
            "description": p.description,
            "steps": steps_out,
        }
    )
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        y.dump(root, f)
