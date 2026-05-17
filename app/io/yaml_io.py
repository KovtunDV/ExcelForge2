from __future__ import annotations

from typing import Any

import yaml

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


def pipeline_from_dict(d: dict[str, Any]) -> Pipeline:
    steps_raw = d.get("steps", []) or []
    steps: list[Step] = []
    for s in steps_raw:
        raw_comment = s.get("comment")
        comment = "" if raw_comment is None else str(raw_comment)
        steps.append(
            Step(
                id=str(s.get("id", "")).strip(),
                type=str(s.get("type", "")).strip(),
                params=dict(s.get("params", {}) or {}),
                comment=comment,
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
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    if not isinstance(data, dict):
        raise ValueError("YAML root must be a mapping (dict).")
    return pipeline_from_dict(data)


def save_pipeline_yaml(p: Pipeline, path: str) -> None:
    p.validate()
    data = pipeline_to_dict(p)
    with open(path, "w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, sort_keys=False, allow_unicode=True)
