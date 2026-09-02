"""The machine-readable view of a chart.

This is the output an agent reads back. It carries the resolved series, the
values as plotted, and the spec that produced them - so a later step can
re-render, diff, or reason about the chart without re-parsing the source data.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from ..model import ChartData


def chart_payload(chart: ChartData) -> dict[str, Any]:
    spec = chart.spec
    return {
        "spec": {
            "form": spec.form,
            "title": spec.title,
            "subtitle": spec.subtitle,
            "x": spec.x,
            "y": spec.y,
            "series": spec.series,
            "x_label": spec.x_label,
            "y_label": spec.y_label,
            "unit": spec.unit,
            "emphasize": spec.emphasize,
            "theme": spec.theme,
            "width": spec.width,
            "height": spec.height,
        },
        "metadata": chart.metadata,
        "x_kind": chart.x_kind,
        "x_order": [_plain(x) for x in chart.x_order],
        "series": [
            {
                "id": s.id,
                "label": s.label,
                "slot": s.slot,
                "folded_from": s.attrs.get("folded_from"),
                "points": [
                    {"x": _plain(p.x), "y": p.y, "label": p.label} for p in s.points
                ],
            }
            for s in chart.series
        ],
    }


def render_json(chart: ChartData, output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(chart_payload(chart), indent=2, default=_plain), encoding="utf-8"
    )
    return output_path


def _plain(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)
