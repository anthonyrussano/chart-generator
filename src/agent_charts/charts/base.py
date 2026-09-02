"""Shared layout and chrome.

Everything recessive lives here: the surface, hairline gridlines, axes, tick
labels, the legend, and the title block. Individual forms draw only their marks
into `layout.plot`, so chrome stays identical across the whole output set.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Callable

from ..model import ChartData, Series
from ..renderers.svg import SvgDocument, estimate_text_width
from ..scales import BandScale, LinearScale, nice_ticks, zero_anchored

# The 2px surface gap and 2px surface ring are the separation mechanism. Never
# draw a border around a mark instead.
SURFACE_GAP = 2.0
RING_WIDTH = 2.0
MAX_BAR_THICKNESS = 24.0
BAR_CORNER_RADIUS = 4.0
MARKER_RADIUS = 4.0

PAD = 16.0
TITLE_SIZE = 15.0
SUBTITLE_SIZE = 12.0
TICK_SIZE = 11.0
LEGEND_SIZE = 11.0
LEGEND_SWATCH = 10.0
LEGEND_ROW_HEIGHT = 18.0


@dataclass(slots=True)
class Rect:
    x: float
    y: float
    width: float
    height: float

    @property
    def right(self) -> float:
        return self.x + self.width

    @property
    def bottom(self) -> float:
        return self.y + self.height


@dataclass(slots=True)
class Layout:
    doc: SvgDocument
    plot: Rect
    legend_rows: int = 0
    notes: list[str] = field(default_factory=list)


def format_value(value: float | None, unit: str = "", fmt: str = "auto") -> str:
    """Compact, readable numbers: 1,284 / 12.9K / $4.2M."""
    if value is None:
        return "-"
    if fmt == "percent":
        return f"{value:,.1f}%".replace(".0%", "%")
    if fmt == "integer":
        return f"{value:,.0f}{unit}"
    if fmt == "raw":
        text = f"{value:g}"
        return f"{text}{unit}"

    prefix = ""
    if unit in ("$", "£", "€"):
        prefix, unit = unit, ""

    magnitude = abs(value)
    if magnitude >= 1_000_000_000:
        text = f"{value / 1_000_000_000:,.1f}B"
    elif magnitude >= 1_000_000:
        text = f"{value / 1_000_000:,.1f}M"
    elif magnitude >= 10_000:
        text = f"{value / 1_000:,.1f}K"
    elif magnitude >= 1000:
        text = f"{value:,.0f}"
    elif magnitude >= 10 or value == int(value):
        text = f"{value:,.0f}"
    else:
        text = f"{value:,.2f}".rstrip("0").rstrip(".")
    text = text.replace(".0K", "K").replace(".0M", "M").replace(".0B", "B")
    return f"{prefix}{text}{unit}"


def format_time_tick(value: Any, all_values: list[Any]) -> str:
    """Shorten ISO timestamps to the part that actually varies.

    A tick reading "2026-09-02T09:05" is unreadable and forces the axis to thin
    itself to two labels. The date belongs in the axis title or the table; the
    tick carries only what distinguishes one slot from the next.
    """
    text = str(value)
    if "T" not in text and " " not in text:
        return text

    separator = "T" if "T" in text else " "
    dates = {str(v).split(separator)[0] for v in all_values if v is not None}
    date_part, _, time_part = text.partition(separator)
    time_part = time_part[:5]  # HH:MM

    if len(dates) == 1:
        return time_part or date_part
    # Several days in view: month-day plus the hour is enough to disambiguate.
    return f"{date_part[5:]} {time_part}".strip()


def format_tick(value: float) -> str:
    """Axis ticks round to clean numbers and stay thousands-comma'd."""
    if value == int(value):
        return f"{int(value):,}"
    return f"{value:,.10g}"


def series_class(series: Series, chart: ChartData, kind: str) -> str:
    """Return the CSS class for a mark, honoring emphasis.

    Emphasis is the most underused form: one series in the accent hue, the rest
    in the de-emphasis gray. When `emphasize` is set, every other series goes
    gray rather than taking its own hue.
    """
    emphasize = chart.spec.emphasize
    if emphasize:
        matched = series.label == emphasize or series.id == emphasize
        if not matched:
            return f"deemph-{'fill' if kind == 'fill' else 'stroke'}"
        return f"{kind}-s0"
    return f"{kind}-s{series.slot}"


# Forms whose rows are already labeled on an axis and whose color is a value
# ramp, not an identity. A categorical legend on these would claim the hues
# mean identity when they mean magnitude.
_NO_CATEGORICAL_LEGEND = frozenset({"heatmap", "stat", "meter", "diverging-bar"})


def wants_legend(chart: ChartData) -> bool:
    """A legend is always present for two or more series, and never for one -
    with one color, the title already says what is plotted."""
    if chart.spec.form in _NO_CATEGORICAL_LEGEND:
        return False
    return len(chart.series) >= 2


def _legend_layout(chart: ChartData, width: float) -> tuple[int, list[list[Series]]]:
    if not wants_legend(chart):
        return 0, []
    rows: list[list[Series]] = [[]]
    used = 0.0
    for series in chart.series:
        item_width = (
            LEGEND_SWATCH + 6 + estimate_text_width(series.label, LEGEND_SIZE) + 18
        )
        if used + item_width > width and rows[-1]:
            rows.append([])
            used = 0.0
        rows[-1].append(series)
        used += item_width
    return len(rows), rows


def build_layout(
    chart: ChartData,
    *,
    left_gutter: float | None = None,
    bottom_gutter: float | None = None,
    right_gutter: float = 0.0,
    top_gutter: float = 0.0,
) -> Layout:
    """Compute the plot rectangle and draw title, subtitle, legend, surface."""
    spec = chart.spec
    doc = SvgDocument(
        width=spec.width,
        height=spec.height,
        title=spec.title or spec.form,
        description=describe(chart),
        theme="dark" if spec.theme == "dark" else "auto",
    )
    doc.rect(0, 0, spec.width, spec.height, "surface")

    y = PAD
    if spec.title:
        y += TITLE_SIZE
        doc.text(PAD, y, spec.title, "title ink")
        y += 6
    if spec.subtitle:
        y += SUBTITLE_SIZE
        doc.text(PAD, y, spec.subtitle, "subtitle ink2")
        y += 4

    inner_width = spec.width - PAD * 2
    row_count, rows = _legend_layout(chart, inner_width)
    if row_count:
        y += 8
        for row in rows:
            x = PAD
            for series in row:
                # The swatch is the colored mark beside the text; the text
                # itself stays in an ink token so it never becomes illegible.
                doc.rect(
                    x,
                    y,
                    LEGEND_SWATCH,
                    LEGEND_SWATCH,
                    series_class(series, chart, "fill"),
                    rx=2,
                )
                doc.text(
                    x + LEGEND_SWATCH + 6,
                    y + LEGEND_SWATCH - 1,
                    series.label,
                    "legend-label ink2",
                )
                x += LEGEND_SWATCH + 6 + estimate_text_width(series.label, LEGEND_SIZE) + 18
            y += LEGEND_ROW_HEIGHT
        y += 4

    top = y + 6 + top_gutter

    if left_gutter is None:
        left_gutter = 46.0
    if bottom_gutter is None:
        bottom_gutter = 34.0
    if spec.x_label:
        bottom_gutter += 16
    if spec.y_label:
        left_gutter += 14

    plot = Rect(
        x=PAD + left_gutter,
        y=top,
        width=max(40.0, spec.width - PAD * 2 - left_gutter - right_gutter),
        height=max(40.0, spec.height - top - PAD - bottom_gutter),
    )
    return Layout(doc=doc, plot=plot, legend_rows=row_count)


def end_label_gutter(chart: ChartData) -> float:
    """Room at the right edge for direct end labels, so they are never clipped."""
    if len(chart.series) > 4:
        return 0.0
    widest = 0.0
    for series in chart.series:
        values = series.y_values()
        if not values:
            continue
        for value in (values[-1],):
            text = format_value(value, chart.spec.unit, chart.spec.value_format)
            widest = max(widest, estimate_text_width(text, TICK_SIZE))
    return (widest + 14) if widest else 0.0


def value_scale(
    chart: ChartData,
    plot: Rect,
    *,
    anchor_zero: bool = True,
    totals: list[float] | None = None,
    horizontal: bool = False,
) -> tuple[LinearScale, list[float]]:
    values = list(totals) if totals is not None else chart.all_y()
    if not values:
        values = [0.0]
    lo, hi = min(values), max(values)
    if anchor_zero:
        lo, hi = zero_anchored(lo, hi)
    domain_lo, domain_hi, ticks = nice_ticks(lo, hi)
    if horizontal:
        scale = LinearScale(domain_lo, domain_hi, plot.x, plot.right)
    else:
        scale = LinearScale(domain_lo, domain_hi, plot.bottom, plot.y)
    return scale, ticks


def draw_value_grid(
    layout: Layout,
    chart: ChartData,
    scale: LinearScale,
    ticks: list[float],
    *,
    horizontal: bool = False,
) -> None:
    """Hairline, solid, one step off the surface. Never dashed."""
    doc, plot = layout.doc, layout.plot
    for tick in ticks:
        position = scale(tick)
        if horizontal:
            doc.line(position, plot.y, position, plot.bottom, "grid")
            doc.text(
                position,
                plot.bottom + 16,
                format_tick(tick),
                "tick muted",
                anchor="middle",
            )
        else:
            doc.line(plot.x, position, plot.right, position, "grid")
            doc.text(plot.x - 8, position + 4, format_tick(tick), "tick muted", anchor="end")

    # The baseline is the axis the marks grow from, so it is drawn last, on top.
    if horizontal:
        zero = scale(0) if scale.domain_min <= 0 <= scale.domain_max else plot.x
        doc.line(zero, plot.y, zero, plot.bottom, "axis")
    else:
        zero = scale(0) if scale.domain_min <= 0 <= scale.domain_max else plot.bottom
        doc.line(plot.x, zero, plot.right, zero, "axis")

    _draw_axis_titles(layout, chart)


def _draw_axis_titles(layout: Layout, chart: ChartData) -> None:
    doc, plot, spec = layout.doc, layout.plot, chart.spec
    if spec.x_label:
        doc.text(
            plot.x + plot.width / 2,
            spec.height - PAD + 2,
            spec.x_label,
            "axis-label muted",
            anchor="middle",
        )
    if spec.y_label:
        cx, cy = PAD + 4, plot.y + plot.height / 2
        doc.raw(
            f'<g transform="rotate(-90 {cx} {cy})">'
            f'<text x="{cx}" y="{cy}" class="axis-label muted" text-anchor="middle">'
            f"{_escape(spec.y_label)}</text></g>"
        )


def _escape(text: str) -> str:
    return (
        str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    )


def category_scale(chart: ChartData, plot: Rect, horizontal: bool = False) -> BandScale:
    if horizontal:
        return BandScale(list(chart.x_order), plot.y, plot.bottom, padding=0.28)
    return BandScale(list(chart.x_order), plot.x, plot.right, padding=0.28)


def draw_category_axis(
    layout: Layout,
    chart: ChartData,
    band: BandScale,
    *,
    horizontal: bool = False,
) -> None:
    """Category tick labels, skipping every nth when they would collide."""
    doc, plot = layout.doc, layout.plot
    if chart.x_kind == "time":
        labels = [format_time_tick(x, chart.x_order) for x in chart.x_order]
    else:
        labels = [str(x) if x is not None else "(unset)" for x in chart.x_order]

    if horizontal:
        available = plot.x - PAD - 8
        for category, label in zip(chart.x_order, labels):
            text = truncate_to_width(label, available, TICK_SIZE)
            doc.text(
                plot.x - 8,
                band.center(category) + 4,
                text,
                "tick muted",
                anchor="end",
                title=label if text != label else None,
            )
        return

    widest = max((estimate_text_width(l, TICK_SIZE) for l in labels), default=0)
    stride = 1
    if band.step > 0 and widest + 8 > band.step:
        stride = max(1, math.ceil((widest + 8) / band.step))

    for index, (category, label) in enumerate(zip(chart.x_order, labels)):
        if index % stride:
            continue
        text = truncate_to_width(label, band.step * stride, TICK_SIZE)
        full = str(category)
        doc.text(
            band.center(category),
            plot.bottom + 16,
            text,
            "tick muted",
            anchor="middle",
            title=full if text != full else None,
        )
    if stride > 1:
        layout.notes.append(
            f"x-axis labels thinned to every {stride} slots to avoid collision; "
            "all values remain in the table view"
        )


def truncate_to_width(text: str, available: float, font_size: float) -> str:
    """A label that will not fit is shortened with an ellipsis, never clipped."""
    if estimate_text_width(text, font_size) <= available:
        return text
    budget = max(1, int(available / (font_size * 0.58)) - 1)
    if budget >= len(text):
        return text
    return text[: max(1, budget)].rstrip() + "…"


def fits_inside(text: str, available: float, font_size: float, padding: float = 12.0) -> bool:
    return estimate_text_width(text, font_size) + padding <= available


def should_direct_label(chart: ChartData) -> bool:
    """Label selectively. A number on every point is chaos and goes unread.

    'auto' labels only when the chart is small enough that every label is
    readable, or when the palette's relief rule requires visible labels.
    """
    mode = chart.spec.direct_labels
    if mode in ("always", "on", "true"):
        return True
    if mode in ("never", "off", "false"):
        return False
    point_count = sum(len(s.points) for s in chart.series)
    return point_count <= 12


def bar_thickness(band: BandScale, divisions: int = 1) -> float:
    """Cap bars so the band's leftover stays as air."""
    raw = band.band_width / max(1, divisions)
    if divisions > 1:
        raw -= SURFACE_GAP * (divisions - 1) / divisions
    return max(1.0, min(MAX_BAR_THICKNESS, raw))


def rounded_bar_path(
    x: float, y: float, width: float, height: float, *, up: bool, radius: float = BAR_CORNER_RADIUS
) -> str:
    """A bar with a 4px rounded data-end and a square baseline end."""
    r = max(0.0, min(radius, width / 2, height))
    if r == 0:
        return f"M{_n(x)},{_n(y)}h{_n(width)}v{_n(height)}h{_n(-width)}Z"
    if up:
        # Grows upward: round the top corners.
        return (
            f"M{_n(x)},{_n(y + height)}"
            f"V{_n(y + r)}"
            f"a{_n(r)},{_n(r)} 0 0 1 {_n(r)},{_n(-r)}"
            f"h{_n(width - 2 * r)}"
            f"a{_n(r)},{_n(r)} 0 0 1 {_n(r)},{_n(r)}"
            f"V{_n(y + height)}Z"
        )
    return (
        f"M{_n(x)},{_n(y)}"
        f"V{_n(y + height - r)}"
        f"a{_n(r)},{_n(r)} 0 0 0 {_n(r)},{_n(r)}"
        f"h{_n(width - 2 * r)}"
        f"a{_n(r)},{_n(r)} 0 0 0 {_n(r)},{_n(-r)}"
        f"V{_n(y)}Z"
    )


def rounded_hbar_path(
    x: float, y: float, width: float, height: float, *, right: bool, radius: float = BAR_CORNER_RADIUS
) -> str:
    r = max(0.0, min(radius, height / 2, width))
    if r == 0:
        return f"M{_n(x)},{_n(y)}h{_n(width)}v{_n(height)}h{_n(-width)}Z"
    if right:
        return (
            f"M{_n(x)},{_n(y)}"
            f"H{_n(x + width - r)}"
            f"a{_n(r)},{_n(r)} 0 0 1 {_n(r)},{_n(r)}"
            f"v{_n(height - 2 * r)}"
            f"a{_n(r)},{_n(r)} 0 0 1 {_n(-r)},{_n(r)}"
            f"H{_n(x)}Z"
        )
    return (
        f"M{_n(x + width)},{_n(y)}"
        f"H{_n(x + r)}"
        f"a{_n(r)},{_n(r)} 0 0 0 {_n(-r)},{_n(r)}"
        f"v{_n(height - 2 * r)}"
        f"a{_n(r)},{_n(r)} 0 0 0 {_n(r)},{_n(r)}"
        f"H{_n(x + width)}Z"
    )


def _n(value: float) -> str:
    from ..scales import fmt_coord

    return fmt_coord(value)


def describe(chart: ChartData) -> str:
    """Alt text. Every chart carries one; it is the non-visual table view."""
    spec = chart.spec
    parts = [f"{spec.form} chart"]
    if spec.title:
        parts.append(f'titled "{spec.title}"')
    parts.append(f"with {len(chart.series)} series")
    values = chart.all_y()
    if values:
        parts.append(
            f"values from {format_value(min(values), spec.unit, spec.value_format)} "
            f"to {format_value(max(values), spec.unit, spec.value_format)}"
        )
    if spec.x:
        parts.append(f"across {len(chart.x_order)} {spec.x} values")
    return ", ".join(parts) + "."


def point_title(series: Series, point, chart: ChartData) -> str:
    """SVG <title> is the no-JavaScript hover layer, present on every mark."""
    x_text = "" if point.x is None else str(point.x)
    value = format_value(point.y, chart.spec.unit, chart.spec.value_format)
    if len(chart.series) > 1:
        return f"{series.label} - {x_text}: {value}"
    return f"{x_text}: {value}"
