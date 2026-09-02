"""The table view.

This is not a nice-to-have. Three light-mode hues in the default palette sit
below 3:1 against the light surface, and the relief rule says a chart using
them must ship visible labels or a table. Every chart writes this file, so the
relief is always satisfied and an agent always has the numbers in text.
"""

from __future__ import annotations

from pathlib import Path

from ..charts.base import describe, format_value
from ..model import ChartData


def render_markdown(chart: ChartData, output_path: Path, notes: list[str] | None = None) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(markdown_text(chart, notes), encoding="utf-8")
    return output_path


def markdown_text(chart: ChartData, notes: list[str] | None = None) -> str:
    spec = chart.spec
    lines: list[str] = []

    lines.append(f"# {spec.title}" if spec.title else f"# {spec.form} chart")
    lines.append("")
    if spec.subtitle:
        lines.append(f"_{spec.subtitle}_")
        lines.append("")

    lines.append(f"**Alt text:** {describe(chart)}")
    lines.append("")

    lines.extend(_table(chart))
    lines.append("")

    summary = _summary(chart)
    if summary:
        lines.append("## Summary")
        lines.extend(summary)
        lines.append("")

    if notes:
        lines.append("## Rendering notes")
        for note in notes:
            lines.append(f"- {note}")
        lines.append("")

    return "\n".join(lines)


def _table(chart: ChartData) -> list[str]:
    spec = chart.spec
    x_name = spec.x or "item"

    if spec.form in ("stat", "meter"):
        header = f"| {x_name} | {spec.y or 'value'} |"
        rows = [header, "| --- | ---: |"]
        for point in chart.series[0].points if chart.series else []:
            rows.append(
                f"| {_cell(point.label or point.x)} "
                f"| {format_value(point.y, spec.unit, spec.value_format)} |"
            )
        return rows

    headers = [x_name] + [s.label for s in chart.series]
    rows = ["| " + " | ".join(_cell(h) for h in headers) + " |"]
    rows.append("| " + " | ".join(["---"] + ["---:"] * len(chart.series)) + " |")

    for index, x in enumerate(chart.x_order):
        cells = [_cell(x)]
        for series in chart.series:
            point = series.points[index] if index < len(series.points) else None
            value = point.y if point else None
            # A gap stays a gap in the table too; it is never printed as 0.
            cells.append(
                format_value(value, spec.unit, spec.value_format) if value is not None else "—"
            )
        rows.append("| " + " | ".join(cells) + " |")
    return rows


def _summary(chart: ChartData) -> list[str]:
    lines: list[str] = []
    spec = chart.spec
    for series in chart.series:
        values = series.y_values()
        if not values:
            lines.append(f"- **{series.label}**: no numeric values")
            continue
        total = sum(values)
        lines.append(
            f"- **{series.label}**: "
            f"min {format_value(min(values), spec.unit, spec.value_format)}, "
            f"max {format_value(max(values), spec.unit, spec.value_format)}, "
            f"mean {format_value(total / len(values), spec.unit, spec.value_format)}, "
            f"total {format_value(total, spec.unit, spec.value_format)} "
            f"({len(values)} of {len(series.points)} points)"
        )
        folded = series.attrs.get("folded_from")
        if folded:
            lines.append(f"  - folded from: {', '.join(str(f) for f in folded)}")
    return lines


def _cell(value) -> str:
    text = "—" if value is None else str(value)
    return text.replace("|", "\\|")
