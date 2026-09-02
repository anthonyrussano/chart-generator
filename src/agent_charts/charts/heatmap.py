"""Heatmap - magnitude across a grid, on one sequential hue."""

from __future__ import annotations

from ..model import ChartData
from ..renderers.svg import estimate_text_width
from ..theme import SEQUENTIAL_LIGHT, sequential_step
from .base import (
    PAD,
    SURFACE_GAP,
    TICK_SIZE,
    Layout,
    build_layout,
    format_value,
    point_title,
    truncate_to_width,
)

LEGEND_HEIGHT = 10.0


def render_heatmap(chart: ChartData) -> Layout:
    row_labels = [s.label for s in chart.series]
    gutter = min(
        180.0,
        max(46.0, max((estimate_text_width(l, TICK_SIZE) for l in row_labels), default=0) + 20),
    )
    layout = build_layout(chart, left_gutter=gutter, bottom_gutter=58)
    doc, plot = layout.doc, layout.plot

    columns = list(chart.x_order)
    rows = chart.series
    if not columns or not rows:
        return layout

    cell_w = plot.width / len(columns)
    cell_h = plot.height / len(rows)

    values = chart.all_y()
    lo, hi = (min(values), max(values)) if values else (0.0, 1.0)
    span = hi - lo or 1.0

    for row_index, series in enumerate(rows):
        y = plot.y + row_index * cell_h
        label = truncate_to_width(series.label, gutter - 10, TICK_SIZE)
        doc.text(
            plot.x - 8, y + cell_h / 2 + 4, label, "tick muted", anchor="end",
            title=series.label if label != series.label else None,
        )
        for column_index, point in enumerate(series.points):
            x = plot.x + column_index * cell_w
            if point.y is None:
                # An absent cell is left as surface, never colored as zero.
                continue
            fraction = (point.y - lo) / span
            color = sequential_step(fraction)
            doc.rect(
                x,
                y,
                max(1.0, cell_w - SURFACE_GAP),
                max(1.0, cell_h - SURFACE_GAP),
                "",
                rx=2,
                extra=[("fill", color), ("data-value", str(point.y))],
                title=point_title(series, point, chart),
            )
            if cell_w > 46 and cell_h > 20:
                text = format_value(point.y, chart.spec.unit, chart.spec.value_format)
                if estimate_text_width(text, 11) + 10 <= cell_w:
                    # Inside a colored fill, ink is chosen by the fill's
                    # luminance so the label always clears contrast.
                    ink = "#0b0b0b" if fraction < 0.55 else "#ffffff"
                    doc.text(
                        x + (cell_w - SURFACE_GAP) / 2,
                        y + cell_h / 2 + 4,
                        text,
                        "value-label",
                        anchor="middle",
                        fill=ink,
                    )

    for column_index, column in enumerate(columns):
        label = str(column)
        text = truncate_to_width(label, cell_w, TICK_SIZE)
        doc.text(
            plot.x + column_index * cell_w + cell_w / 2,
            plot.bottom + 16,
            text,
            "tick muted",
            anchor="middle",
            title=label if text != label else None,
        )

    _draw_ramp_legend(layout, chart, lo, hi)
    return layout


def _draw_ramp_legend(layout: Layout, chart: ChartData, lo: float, hi: float) -> None:
    """A continuous ramp always ships its scale legend."""
    doc, plot = layout.doc, layout.plot
    y = plot.bottom + 28
    width = min(180.0, plot.width)
    x = plot.x
    steps = len(SEQUENTIAL_LIGHT)
    step_w = width / steps
    for index in range(steps):
        doc.rect(
            x + index * step_w,
            y,
            step_w + 0.5,
            LEGEND_HEIGHT,
            "",
            extra=[("fill", SEQUENTIAL_LIGHT[index])],
        )
    unit, fmt = chart.spec.unit, chart.spec.value_format
    doc.text(x, y + LEGEND_HEIGHT + 12, format_value(lo, unit, fmt), "tick muted")
    doc.text(
        x + width, y + LEGEND_HEIGHT + 12, format_value(hi, unit, fmt), "tick muted",
        anchor="end",
    )


def _esc(text: str) -> str:
    return str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
