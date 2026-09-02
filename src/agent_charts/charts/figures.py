"""Figures - when the form is a number, not a chart.

A single current value is a stat tile, not a one-bar bar chart. A ratio against
a limit is a meter, not a two-slice pie. These are the forms the data-viz
method reaches for before it reaches for a plot.
"""

from __future__ import annotations

from ..model import ChartData
from ..renderers.svg import SvgDocument, estimate_text_width
from ..theme import CHROME_LIGHT, SEQUENTIAL_LIGHT, STATUS
from .base import PAD, Layout, Rect, describe, format_value

TILE_GAP = 12.0
HERO_SIZE = 34.0
METER_HEIGHT = 10.0


def _header_height(spec) -> float:
    height = PAD
    if spec.title:
        height += 21
    if spec.subtitle:
        height += 16
    return height


def render_stat(chart: ChartData) -> Layout:
    """A KPI row of stat tiles. One value becomes a hero figure.

    Figures size themselves to their content: a KPI row padded out to a plot's
    height is mostly empty space, which reads as a broken chart.
    """
    spec = chart.spec
    points = chart.series[0].points if chart.series else []
    count = max(1, len(points))

    has_trend = any(_parse_trend(_row(p).get("trend") or _row(p).get("sparkline"))
                    for p in points)
    has_delta = any(_row(p).get("delta") is not None for p in points)
    body = 11 + (HERO_SIZE if count == 1 else 30) + (18 if has_delta else 0)
    body += (30 if has_trend else 0)
    height = int(_header_height(spec) + 14 + body + PAD)

    doc = SvgDocument(
        width=spec.width,
        height=height,
        title=spec.title or "stat",
        description=describe(chart),
        theme="dark" if spec.theme == "dark" else "auto",
    )
    doc.rect(0, 0, spec.width, height, "surface")

    y = PAD
    if spec.title:
        y += 15
        doc.text(PAD, y, spec.title, "title ink")
        y += 6
    if spec.subtitle:
        y += 12
        doc.text(PAD, y, spec.subtitle, "subtitle ink2")
        y += 4
    y += 14

    hero = count == 1
    tile_width = (spec.width - PAD * 2 - TILE_GAP * (count - 1)) / count

    for index, point in enumerate(points):
        x = PAD + index * (tile_width + TILE_GAP)
        label = point.label or ""
        value = format_value(point.y, spec.unit, spec.value_format)

        doc.text(x, y + 11, label, "stat-label muted")
        if hero:
            # Exactly one hero figure per view, in the same sans as the rest.
            doc.text(x, y + 11 + HERO_SIZE, value, "hero ink")
            baseline = y + 11 + HERO_SIZE
        else:
            doc.raw(
                f'<text x="{x}" y="{y + 44}" class="ink" font-size="22" '
                f'font-weight="600">{_esc(value)}</text>'
            )
            baseline = y + 44

        delta = _row(point).get("delta")
        if delta is not None:
            delta_value = _as_float(delta)
            if delta_value is not None:
                sign = "+" if delta_value >= 0 else ""
                text = f"{sign}{format_value(delta_value, '', 'raw')}"
                # The arrow carries direction. Color is only added when the
                # caller has said which direction is good - without that,
                # green-for-up would be a guess about the metric's meaning.
                arrow = "↑" if delta_value >= 0 else "↓"
                up_is_good = spec.options.get("up_is_good")
                css = "ink2"
                if up_is_good is not None:
                    good = (delta_value >= 0) == bool(up_is_good)
                    css = "positive" if good else "ink2"
                doc.text(x, baseline + 18, f"{arrow} {text}", f"stat-label {css}")

        # The sparkline stays inside its own tile; running the full tile pitch
        # would let it cross into the neighbouring tile.
        _sparkline(doc, point, Rect(x, baseline + 26, tile_width - TILE_GAP, 20))

    return Layout(doc=doc, plot=Rect(PAD, y, spec.width - PAD * 2, height - y - PAD))


def _row(point) -> dict:
    row = point.attrs.get("row") if point.attrs else None
    return row if isinstance(row, dict) else {}


def _sparkline(doc: SvgDocument, point, rect: Rect) -> None:
    """Optional 12-point trend: context in the de-emphasis hue."""
    row = _row(point)
    raw = row.get("trend") or row.get("sparkline")
    values = _parse_trend(raw)
    if len(values) < 2:
        return

    lo, hi = min(values), max(values)
    span = (hi - lo) or 1.0
    step = rect.width / (len(values) - 1)
    coords = [
        (rect.x + i * step, rect.bottom - ((v - lo) / span) * rect.height)
        for i, v in enumerate(values)
    ]
    from ..scales import fmt_coord

    d = "M" + "L".join(f"{fmt_coord(x)},{fmt_coord(y)}" for x, y in coords)
    doc.path(d, "line-mark deemph-stroke")
    # The current period takes the accent; the rest stays context.
    doc.circle(coords[-1][0], coords[-1][1], 3.5, "fill-s0")


def render_meter(chart: ChartData) -> Layout:
    """A single ratio against a limit. The track is a lighter step of the
    fill's own ramp, so the state reads across the whole bar."""
    spec = chart.spec
    points = chart.series[0].points if chart.series else []

    rows = [p for p in points if p.y is not None]
    height = int(_header_height(spec) + 12 + len(rows) * (18 + METER_HEIGHT + 20) + PAD)

    doc = SvgDocument(
        width=spec.width,
        height=height,
        title=spec.title or "meter",
        description=describe(chart),
        theme="dark" if spec.theme == "dark" else "auto",
    )
    doc.rect(0, 0, spec.width, height, "surface")

    y = PAD
    if spec.title:
        y += 15
        doc.text(PAD, y, spec.title, "title ink")
        y += 6
    if spec.subtitle:
        y += 12
        doc.text(PAD, y, spec.subtitle, "subtitle ink2")
        y += 6
    y += 12

    limit = spec.target if spec.target is not None else _default_limit(points)
    width = spec.width - PAD * 2

    for point in points:
        if point.y is None:
            continue
        fraction = 0.0 if not limit else max(0.0, min(1.0, point.y / limit))
        label = point.label or ""
        value = format_value(point.y, spec.unit, spec.value_format)
        target = format_value(limit, spec.unit, spec.value_format)

        doc.text(PAD, y + 11, label, "stat-label ink2")
        doc.text(PAD + width, y + 11, f"{value} / {target}", "stat-label muted", anchor="end")
        y += 18

        fill, track = _severity_colors(fraction)
        # The track is a lighter step of the fill's OWN ramp, so the state
        # reads across the whole bar rather than only in the filled part.
        doc.rect(PAD, y, width, METER_HEIGHT, "", rx=METER_HEIGHT / 2,
                 extra=[("fill", track)])
        doc.rect(PAD, y, max(METER_HEIGHT, width * fraction), METER_HEIGHT, "",
                 rx=METER_HEIGHT / 2, extra=[("fill", fill)],
                 title=f"{label}: {value} of {target}")
        y += METER_HEIGHT + 20

    return Layout(doc=doc, plot=Rect(PAD, PAD, width, height - PAD * 2))


# (fill, track) per severity band. The label beside the meter always states
# the value, so severity never rides on color alone.
_SEVERITY_BANDS = (
    (0.90, STATUS["critical"], "#f6d4d4"),
    (0.75, STATUS["warning"], "#fdeec9"),
    (0.00, SEQUENTIAL_LIGHT[7], SEQUENTIAL_LIGHT[1]),
)


def _severity_colors(fraction: float) -> tuple[str, str]:
    for threshold, fill, track in _SEVERITY_BANDS:
        if fraction >= threshold:
            return fill, track
    return _SEVERITY_BANDS[-1][1], _SEVERITY_BANDS[-1][2]


def _default_limit(points) -> float:
    values = [p.y for p in points if p.y is not None]
    if not values:
        return 1.0
    top = max(values)
    return 100.0 if top <= 100 else top


def _parse_trend(raw) -> list[float]:
    if isinstance(raw, list):
        return [v for v in (_as_float(item) for item in raw) if v is not None][-12:]
    if isinstance(raw, str):
        parts = raw.replace(";", ",").split(",")
        return [v for v in (_as_float(p) for p in parts) if v is not None][-12:]
    return []


def _as_float(value) -> float | None:
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return None


def _esc(text: str) -> str:
    return str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
