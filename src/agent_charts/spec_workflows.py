"""Authored specs: the declarative surface agents write against.

A spec is a YAML or JSON file describing one chart or a dashboard of several.
It is the analogue of the diagram generator's spec: an agent emits a spec, the
tool renders it, and the spec stays in the repo as the reviewable artifact.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

import yaml

from .collectors import CollectorError, collect, collect_from_inline
from .model import ChartSpec, DataSet
from .normalize import resolve
from .renderers.chart_renderer import available_forms

SPEC_KEYS = {
    "form", "title", "subtitle", "x", "y", "series", "x_label", "y_label",
    "emphasize", "unit", "width", "height", "theme", "sort", "top_n",
    "baseline", "target", "value_format", "direct_labels", "options",
}


class SpecError(ValueError):
    pass


def load_spec(path: str | Path) -> dict[str, Any]:
    path = Path(path)
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise SpecError(f"Cannot read spec {path}: {exc}") from exc
    try:
        if path.suffix.lower() in (".yaml", ".yml"):
            payload = yaml.safe_load(text)
        else:
            payload = json.loads(text)
    except (yaml.YAMLError, json.JSONDecodeError) as exc:
        raise SpecError(f"Spec {path} is not valid: {exc}") from exc
    if not isinstance(payload, dict):
        raise SpecError(f"Spec {path} must be a mapping at the top level")
    return payload


def validate_spec(payload: dict[str, Any]) -> list[str]:
    """Validate structure and inherited settings; the CLI also checks data."""
    problems: list[str] = []
    charts = payload.get("charts")

    if charts is None:
        charts = [payload]
    elif not isinstance(charts, list):
        problems.append("'charts' must be a list")
        return problems

    if not charts:
        return ["'charts' must contain at least one chart"]

    forms = set(available_forms())
    shared = {k: v for k, v in payload.items() if k != "charts"} if "charts" in payload else {}
    names: set[str] = set()
    for index, chart in enumerate(charts):
        where = f"charts[{index}]"
        if not isinstance(chart, dict):
            problems.append(f"{where} must be a mapping")
            continue
        chart = {**shared, **chart}

        form = chart.get("form")
        if not form:
            problems.append(f"{where}: 'form' is required")
        elif not isinstance(form, str) or form not in forms:
            problems.append(
                f"{where}: unknown form '{form}'. Choose one of: {', '.join(sorted(forms))}"
            )

        has_data = any(k in chart for k in ("data", "rows", "source"))
        if not has_data and "data" not in payload and "rows" not in payload:
            problems.append(
                f"{where}: needs 'data' (a file path), 'rows' (inline records), "
                "or a top-level 'data' shared by every chart"
            )

        unknown = set(chart) - SPEC_KEYS - {"data", "rows", "source", "format", "query", "name"}
        if unknown:
            problems.append(f"{where}: unknown keys: {', '.join(sorted(unknown))}")

        for key in ("width", "height", "top_n"):
            value = chart.get(key)
            if value is not None and (isinstance(value, bool) or not isinstance(value, int)):
                problems.append(f"{where}: '{key}' must be an integer")
            elif value is not None and value <= 0:
                problems.append(f"{where}: '{key}' must be positive")

        for key in (
            "title", "subtitle", "x", "y", "series", "x_label", "y_label",
            "unit", "emphasize", "data", "source", "format", "query", "name",
        ):
            if key in chart and chart[key] is not None and not isinstance(chart[key], str):
                problems.append(f"{where}: '{key}' must be a string")
        for key, choices in {
            "theme": ("auto", "light", "dark"),
            "sort": ("asc", "desc", "label", "label-desc"),
            "value_format": ("auto", "integer", "percent", "raw"),
            "direct_labels": ("auto", "always", "never"),
        }.items():
            if key in chart and chart[key] is not None and chart[key] not in choices:
                problems.append(f"{where}: '{key}' must be one of: {', '.join(choices)}")
        for key in ("baseline", "target"):
            value = chart.get(key)
            if value is not None and (
                isinstance(value, bool) or not isinstance(value, (int, float))
                or not math.isfinite(value)
            ):
                problems.append(f"{where}: '{key}' must be a finite number")
        if "options" in chart and not isinstance(chart["options"], dict):
            problems.append(f"{where}: 'options' must be a mapping")
        if "rows" in chart and chart["rows"] is not None and (
            not isinstance(chart["rows"], list)
            or not all(isinstance(row, dict) for row in chart["rows"])
        ):
            problems.append(f"{where}: 'rows' must be a list of objects")

        name = chart_name(chart, index)
        if name in names:
            problems.append(f"{where}: duplicate output name '{name}'; set distinct 'name' values")
        names.add(name)

    return problems


def chart_specs(payload: dict[str, Any]) -> list[dict[str, Any]]:
    charts = payload.get("charts")
    if charts is None:
        return [payload]
    if not isinstance(charts, list):
        raise SpecError("'charts' must be a list")
    # Top-level keys are defaults every chart inherits.
    shared = {k: v for k, v in payload.items() if k != "charts"}
    merged: list[dict[str, Any]] = []
    for chart in charts:
        if not isinstance(chart, dict):
            raise SpecError("each entry in 'charts' must be a mapping")
        merged.append({**shared, **chart})
    return merged


def to_chart_spec(entry: dict[str, Any]) -> ChartSpec:
    fields = {k: v for k, v in entry.items() if k in SPEC_KEYS}
    form = fields.pop("form", None)
    if not form:
        raise SpecError("'form' is required")
    return ChartSpec(form=form, **fields)


def dataset_for(entry: dict[str, Any], base_dir: Path) -> DataSet:
    """Resolve one chart's data: inline rows, or a file relative to the spec."""
    if "rows" in entry and entry["rows"] is not None:
        return collect_from_inline(entry["rows"])

    source = entry.get("data") or entry.get("source")
    if not source:
        raise SpecError("chart needs 'data' or 'rows'")

    path = Path(source)
    if not path.is_absolute():
        path = base_dir / path
    try:
        return collect(path, fmt=entry.get("format", "auto"), query=entry.get("query"))
    except CollectorError as exc:
        raise SpecError(str(exc)) from exc


def chart_name(entry: dict[str, Any], index: int) -> str:
    """A stable, filesystem-safe output name for one chart in a spec."""
    raw = entry.get("name") or entry.get("title") or f"{entry.get('form', 'chart')}-{index + 1}"
    safe = "".join(ch if ch.isalnum() else "-" for ch in str(raw).lower()).strip("-")
    while "--" in safe:
        safe = safe.replace("--", "-")
    return safe or f"chart-{index + 1}"


def compare_specs(current: dict[str, Any], future: dict[str, Any]) -> dict[str, Any]:
    """Diff two spec files - which charts were added, removed, or changed."""
    current_charts = {chart_name(c, i): c for i, c in enumerate(chart_specs(current))}
    future_charts = {chart_name(c, i): c for i, c in enumerate(chart_specs(future))}

    added = sorted(set(future_charts) - set(current_charts))
    removed = sorted(set(current_charts) - set(future_charts))
    changed: list[dict[str, Any]] = []

    for name in sorted(set(current_charts) & set(future_charts)):
        before, after = current_charts[name], future_charts[name]
        deltas = {
            key: {"from": before.get(key), "to": after.get(key)}
            for key in sorted(set(before) | set(after))
            if before.get(key) != after.get(key)
        }
        if deltas:
            changed.append({"name": name, "changes": deltas})

    return {
        "added": added,
        "removed": removed,
        "changed": changed,
        "unchanged": sorted(
            set(current_charts) & set(future_charts) - {c["name"] for c in changed}
        ),
    }


def write_compare_summary(diff: dict[str, Any], path: Path) -> Path:
    lines = ["# Chart Spec Comparison", ""]
    for key, title in (
        ("added", "Added"),
        ("removed", "Removed"),
        ("unchanged", "Unchanged"),
    ):
        lines.append(f"## {title}")
        items = diff.get(key, [])
        lines.extend([f"- {item}" for item in items] if items else ["- None"])
        lines.append("")

    lines.append("## Changed")
    if not diff.get("changed"):
        lines.append("- None")
    else:
        for entry in diff["changed"]:
            lines.append(f"- **{entry['name']}**")
            for field, delta in entry["changes"].items():
                lines.append(f"  - `{field}`: {delta['from']!r} -> {delta['to']!r}")
    lines.append("")

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def spec_counts(payload: dict[str, Any]) -> dict[str, int]:
    charts = chart_specs(payload)
    forms: dict[str, int] = {}
    for chart in charts:
        form = str(chart.get("form", "unknown"))
        forms[form] = forms.get(form, 0) + 1
    return {"charts": len(charts), **{f"form:{k}": v for k, v in sorted(forms.items())}}
