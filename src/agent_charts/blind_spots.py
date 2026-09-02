"""Data-quality reporting.

The diagram generator reports what it could not see in the infrastructure. The
chart generator reports what it could not trust in the data: missing cells,
unparseable numbers, folded series, and clipped labels. An agent reading a
chart it just produced needs to know these before it draws a conclusion.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .model import ChartData, DataSet
from .normalize import OTHER_LABEL


def collect_blind_spots(
    *,
    errors: list[str] | None = None,
    missing_values: list[str] | None = None,
    unparsed_values: list[str] | None = None,
    folded_series: list[str] | None = None,
    empty_sources: list[str] | None = None,
    warnings: list[str] | None = None,
) -> dict[str, Any]:
    """Build a structured blind spots report."""
    report = {
        "errors": errors or [],
        "missing_values": missing_values or [],
        "unparsed_values": unparsed_values or [],
        "folded_series": folded_series or [],
        "empty_sources": empty_sources or [],
        "warnings": warnings or [],
    }
    report["has_blind_spots"] = any(v for v in report.values() if isinstance(v, list))
    return report


def inspect_dataset(dataset: DataSet) -> dict[str, list[str]]:
    """Find cells that were present but unusable."""
    missing: list[str] = []
    unparsed: list[str] = []
    empty: list[str] = []

    if not dataset.rows:
        empty.append(f"{dataset.metadata.get('origin', 'source')}: no rows")
        return {"missing_values": missing, "unparsed_values": unparsed, "empty_sources": empty}

    for column in dataset.columns:
        values = dataset.values(column.name)
        blanks = sum(1 for v in values if v is None or v == "")
        if blanks:
            missing.append(
                f"{column.name}: {blanks} of {len(values)} rows have no value"
            )
        if column.kind == "category":
            # A mostly-numeric category column usually means dirty cells.
            numericish = sum(1 for v in values if _numericish(v))
            if values and numericish and numericish >= len(values) * 0.8 and numericish < len(values):
                unparsed.append(
                    f"{column.name}: {len(values) - numericish} of {len(values)} cells "
                    "are not numbers, so the column is plotted as a category"
                )
    return {"missing_values": missing, "unparsed_values": unparsed, "empty_sources": empty}


def inspect_chart(chart: ChartData) -> dict[str, list[str]]:
    """Find things the chart itself had to hide or compromise on."""
    folded: list[str] = []
    warnings: list[str] = []

    for series in chart.series:
        origins = series.attrs.get("folded_from")
        if origins:
            folded.append(
                f"{len(origins)} series were summed into '{OTHER_LABEL}': "
                + ", ".join(str(o) for o in origins)
            )

    gaps = sum(1 for s in chart.series for p in s.points if p.y is None)
    if gaps:
        warnings.append(f"{gaps} data points have no value and are drawn as gaps, not zeros")

    if len(chart.series) > 4 and chart.spec.form in ("line", "area"):
        warnings.append(
            f"{len(chart.series)} series on one plot: end labels are likely to collide. "
            "Consider small multiples or an emphasis chart."
        )

    if not chart.all_y():
        warnings.append("no numeric values resolved; the chart will be empty")

    # Several measures on one axis is correct; measures of wildly different
    # magnitude on one axis is a chart that hides the smaller ones. The fix is
    # separate charts or indexing to a common base - never a second y axis.
    if len(chart.series) > 1 and chart.metadata.get("layout") == "wide":
        peaks = [
            (s.label, max(abs(v) for v in s.y_values()))
            for s in chart.series
            if s.y_values()
        ]
        if len(peaks) > 1:
            largest = max(peaks, key=lambda item: item[1])
            smallest = min(peaks, key=lambda item: item[1])
            if smallest[1] > 0 and largest[1] / smallest[1] > 20:
                warnings.append(
                    f"'{largest[0]}' peaks {largest[1] / smallest[1]:.0f}x higher than "
                    f"'{smallest[0]}' on a shared axis, which flattens the smaller "
                    "series. Split into separate charts or index both to a common "
                    "base - do not add a second y axis."
                )

    return {"folded_series": folded, "warnings": warnings}


def _numericish(value: Any) -> bool:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return True
    if not isinstance(value, str):
        return False
    try:
        float(value.strip().replace(",", ""))
        return True
    except ValueError:
        return False


def write_blind_spots_json(report: dict[str, Any], path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    return path


def write_blind_spots_md(report: dict[str, Any], path: Path) -> Path:
    sections = [
        ("errors", "Collection Errors"),
        ("empty_sources", "Empty Sources"),
        ("missing_values", "Missing Values"),
        ("unparsed_values", "Unparsed Values"),
        ("folded_series", "Folded Series"),
        ("warnings", "Warnings"),
    ]

    lines = ["# Chart Blind Spots Report", ""]
    for key, title in sections:
        items = report.get(key, [])
        lines.append(f"## {title}")
        if not items:
            lines.append("- None")
        else:
            for item in items:
                lines.append(f"- {item}")
        lines.append("")

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")
    return path
