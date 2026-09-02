"""Bar, column, stacked, diverging, line, area, scatter, and dumbbell forms."""

from __future__ import annotations

from ..model import ChartData
from ..renderers.svg import SvgDocument, estimate_text_width
from ..scales import LinearScale, fmt_coord
from .base import (
    MARKER_RADIUS,
    end_label_gutter,
    PAD,
    SURFACE_GAP,
    TICK_SIZE,
    Layout,
    bar_thickness,
    build_layout,
    category_scale,
    describe,
    draw_category_axis,
    draw_value_grid,
    fits_inside,
    format_value,
    point_title,
    rounded_bar_path,
    rounded_hbar_path,
    series_class,
    should_direct_label,
    value_scale,
)


def _label_gutter(chart: ChartData) -> float:
    """Horizontal bars need room for their category names on the left."""
    labels = [str(x) for x in chart.x_order]
    widest = max((estimate_text_width(l, TICK_SIZE) for l in labels), default=0)
    return min(180.0, max(46.0, widest + 12))


def render_column(chart: ChartData, stacked: bool = False) -> Layout:
    """Vertical columns. Grouped side-by-side, or stacked part-to-whole."""
    totals = _stack_totals(chart) if stacked else None
    # A value label rides above the tallest column, so it needs its own room -
    # otherwise it sits against the title.
    labels_above = (
        not stacked and len(chart.series) == 1 and should_direct_label(chart)
    )
    layout = build_layout(chart, top_gutter=12.0 if labels_above else 0.0)
    band = category_scale(chart, layout.plot)
    scale, ticks = value_scale(chart, layout.plot, totals=totals)
    draw_value_grid(layout, chart, scale, ticks)
    draw_category_axis(layout, chart, band)

    doc = layout.doc
    baseline = scale(0) if scale.domain_min <= 0 <= scale.domain_max else layout.plot.bottom
    label = should_direct_label(chart)

    if stacked:
        for index, x in enumerate(chart.x_order):
            cursor = baseline
            width = bar_thickness(band)
            x0 = band.center(x) - width / 2
            # The stack's data-end is the top of its last non-zero segment;
            # only that one gets the 4px rounding.
            last_positive = _last_nonzero(chart, index, positive=True)
            for series in chart.series:
                point = series.points[index]
                if point.y is None or point.y == 0:
                    continue
                top = scale(point.y) - scale(0)
                height = abs(top)
                # The 2px surface gap is what separates touching segments;
                # never a stroke around them.
                drawn = max(0.5, height - SURFACE_GAP)
                y0 = cursor - height if point.y > 0 else cursor
                rect_y = y0 + (SURFACE_GAP if point.y <= 0 else 0)
                if series is last_positive and point.y > 0:
                    doc.path(
                        rounded_bar_path(x0, rect_y, width, drawn, up=True),
                        series_class(series, chart, "fill"),
                        extra=[("data-value", fmt_coord(point.y))],
                        title=point_title(series, point, chart),
                    )
                else:
                    doc.rect(
                        x0,
                        rect_y,
                        width,
                        drawn,
                        series_class(series, chart, "fill"),
                        extra=[("data-value", fmt_coord(point.y))],
                        title=point_title(series, point, chart),
                    )
                cursor = y0 if point.y > 0 else cursor + height
    else:
        divisions = len(chart.series)
        width = bar_thickness(band, divisions)
        span = width * divisions + SURFACE_GAP * (divisions - 1)
        for series_index, series in enumerate(chart.series):
            for point in series.points:
                if point.y is None:
                    continue
                x0 = (
                    band.center(point.x)
                    - span / 2
                    + series_index * (width + SURFACE_GAP)
                )
                y_value = scale(point.y)
                top, height = min(y_value, baseline), abs(y_value - baseline)
                doc.path(
                    rounded_bar_path(x0, top, width, height, up=point.y >= 0),
                    series_class(series, chart, "fill"),
                    extra=[("data-value", fmt_coord(point.y))],
                    title=point_title(series, point, chart),
                )
                if label and divisions == 1:
                    text = format_value(point.y, chart.spec.unit, chart.spec.value_format)
                    doc.text(
                        x0 + width / 2,
                        top - 6 if point.y >= 0 else top + height + 14,
                        text,
                        "value-label ink2",
                        anchor="middle",
                    )
    return layout


def render_bar(chart: ChartData, stacked: bool = False) -> Layout:
    """Horizontal bars - the right default when categories have long names."""
    totals = _stack_totals(chart) if stacked else None
    layout = build_layout(chart, left_gutter=_label_gutter(chart))
    band = category_scale(chart, layout.plot, horizontal=True)
    scale, ticks = value_scale(chart, layout.plot, totals=totals, horizontal=True)
    draw_value_grid(layout, chart, scale, ticks, horizontal=True)
    draw_category_axis(layout, chart, band, horizontal=True)

    doc = layout.doc
    baseline = scale(0) if scale.domain_min <= 0 <= scale.domain_max else layout.plot.x
    label = should_direct_label(chart)

    if stacked:
        for index, x in enumerate(chart.x_order):
            cursor = baseline
            height = bar_thickness(band)
            y0 = band.center(x) - height / 2
            for series in chart.series:
                point = series.points[index]
                if point.y is None or point.y == 0:
                    continue
                width = abs(scale(point.y) - scale(0))
                drawn = max(0.5, width - SURFACE_GAP)
                x0 = cursor if point.y > 0 else cursor - width
                doc.rect(
                    x0,
                    y0,
                    drawn,
                    height,
                    series_class(series, chart, "fill"),
                    extra=[("data-value", fmt_coord(point.y))],
                    title=point_title(series, point, chart),
                )
                cursor = x0 + width if point.y > 0 else x0
    else:
        divisions = len(chart.series)
        height = bar_thickness(band, divisions)
        span = height * divisions + SURFACE_GAP * (divisions - 1)
        for series_index, series in enumerate(chart.series):
            for point in series.points:
                if point.y is None:
                    continue
                y0 = (
                    band.center(point.x)
                    - span / 2
                    + series_index * (height + SURFACE_GAP)
                )
                x_value = scale(point.y)
                left, width = min(x_value, baseline), abs(x_value - baseline)
                doc.path(
                    rounded_hbar_path(left, y0, width, height, right=point.y >= 0),
                    series_class(series, chart, "fill"),
                    extra=[("data-value", fmt_coord(point.y))],
                    title=point_title(series, point, chart),
                )
                if label and divisions == 1:
                    text = format_value(point.y, chart.spec.unit, chart.spec.value_format)
                    tip = left + width + 6 if point.y >= 0 else left - 6
                    # Only place the value outside the bar if it fits there.
                    if tip + estimate_text_width(text, TICK_SIZE) < layout.plot.right + PAD:
                        doc.text(
                            tip,
                            y0 + height / 2 + 4,
                            text,
                            "value-label ink2",
                            anchor="start" if point.y >= 0 else "end",
                        )
    return layout


def render_diverging_bar(chart: ChartData) -> Layout:
    """Above/below a baseline. Two hues that read as opposite, gray at zero."""
    layout = build_layout(chart, left_gutter=_label_gutter(chart))
    band = category_scale(chart, layout.plot, horizontal=True)
    scale, ticks = value_scale(chart, layout.plot, horizontal=True)
    draw_value_grid(layout, chart, scale, ticks, horizontal=True)
    draw_category_axis(layout, chart, band, horizontal=True)

    doc = layout.doc
    baseline = scale(chart.spec.baseline or 0)
    height = bar_thickness(band)
    label = should_direct_label(chart)

    for series in chart.series:
        for point in series.points:
            if point.y is None:
                continue
            y0 = band.center(point.x) - height / 2
            x_value = scale(point.y)
            left, width = min(x_value, baseline), abs(x_value - baseline)
            positive = point.y >= (chart.spec.baseline or 0)
            # Polarity is not goodness. Which pole reads warm is the author's
            # call, so 'invert_poles' swaps them without touching the palette.
            if chart.spec.options.get("invert_poles"):
                css = "fill-neg" if positive else "fill-pos"
            else:
                css = "fill-pos" if positive else "fill-neg"
            doc.path(
                rounded_hbar_path(left, y0, width, height, right=positive),
                css,
                extra=[("data-value", fmt_coord(point.y))],
                title=point_title(series, point, chart),
            )
            if label:
                text = format_value(point.y, chart.spec.unit, chart.spec.value_format)
                tip = left + width + 6 if positive else left - 6
                doc.text(
                    tip,
                    y0 + height / 2 + 4,
                    text,
                    "value-label ink2",
                    anchor="start" if positive else "end",
                )
    return layout


def render_line(chart: ChartData, area: bool = False) -> Layout:
    """Trend over time. Area fill only reads honestly for a single series."""
    layout = build_layout(chart, right_gutter=end_label_gutter(chart))
    band = category_scale(chart, layout.plot)
    scale, ticks = value_scale(chart, layout.plot, anchor_zero=area)
    draw_value_grid(layout, chart, scale, ticks)
    draw_category_axis(layout, chart, band)

    doc = layout.doc
    baseline = scale(scale.domain_min)
    single = len(chart.series) == 1

    for series in chart.series:
        segments = _segments(series, band, scale)
        if area and single:
            for segment in segments:
                if len(segment) < 2:
                    continue
                d = "M" + "L".join(f"{fmt_coord(x)},{fmt_coord(y)}" for x, y in segment)
                d += (
                    f"L{fmt_coord(segment[-1][0])},{fmt_coord(baseline)}"
                    f"L{fmt_coord(segment[0][0])},{fmt_coord(baseline)}Z"
                )
                doc.path(d, f"area-s{series.slot}")
        for segment in segments:
            if len(segment) == 1:
                x, y = segment[0]
                doc.circle(x, y, MARKER_RADIUS, series_class(series, chart, "fill"))
                continue
            d = "M" + "L".join(f"{fmt_coord(x)},{fmt_coord(y)}" for x, y in segment)
            doc.path(d, f"line-mark {series_class(series, chart, 'stroke')}")

    # End markers carry a surface ring so they stay legible where lines cross.
    for series in chart.series:
        last = _last_point(series, band, scale)
        if last is None:
            continue
        x, y, point = last
        fill = series_class(series, chart, "fill")
        doc.circle(x, y, MARKER_RADIUS + 1, f"ring {fill}")
        doc.circle(x, y, MARKER_RADIUS, fill, title=point_title(series, point, chart))

    _draw_end_labels(layout, chart, band, scale)
    _hover_targets(layout, chart, band, scale)
    return layout


def _draw_end_labels(layout: Layout, chart: ChartData, band, scale) -> None:
    """Direct-label line ends, but only when they will not collide.

    Nudging colliding labels apart detaches them from their lines and reads as
    noise, so past that point the legend and table carry identity instead.
    """
    if len(chart.series) > 4:
        layout.notes.append(
            "end labels omitted: more than four series converge; use the legend and table"
        )
        return

    placed: list[tuple[float, float, str, str]] = []
    for series in chart.series:
        last = _last_point(series, band, scale)
        if last is None:
            continue
        x, y, point = last
        text = format_value(point.y, chart.spec.unit, chart.spec.value_format)
        placed.append((x, y, text, series_class(series, chart, "fill")))

    placed.sort(key=lambda item: item[1])
    for index in range(1, len(placed)):
        if placed[index][1] - placed[index - 1][1] < 13:
            layout.notes.append(
                "end labels omitted: series converge at the right edge; "
                "all values remain in the table view"
            )
            return

    doc = layout.doc
    for x, y, text, _ in placed:
        if x + 8 + estimate_text_width(text, TICK_SIZE) > chart.spec.width - PAD:
            continue
        doc.text(x + 8, y + 4, text, "value-label ink2")


def _hover_targets(layout: Layout, chart: ChartData, band, scale) -> None:
    """Invisible, generous hit targets - the hover layer for line/area."""
    doc = layout.doc
    for series in chart.series:
        for point in series.points:
            if point.y is None:
                continue
            doc.circle(
                band.center(point.x),
                scale(point.y),
                8,
                "hover-target",
                extra=[("fill", "transparent"), ("data-value", fmt_coord(point.y))],
                title=point_title(series, point, chart),
            )


def render_scatter(chart: ChartData) -> Layout:
    """Two numeric measures. Capped at three hues by the all-pairs floors."""
    layout = build_layout(chart)
    x_values = [p.x for s in chart.series for p in s.points if isinstance(p.x, (int, float))]
    if not x_values:
        return render_column(chart)

    from ..scales import nice_ticks

    x_lo, x_hi, x_ticks = nice_ticks(min(x_values), max(x_values))
    x_scale = LinearScale(x_lo, x_hi, layout.plot.x, layout.plot.right)
    y_scale, y_ticks = value_scale(chart, layout.plot, anchor_zero=False)

    doc = layout.doc
    from .base import format_tick

    for tick in y_ticks:
        y = y_scale(tick)
        doc.line(layout.plot.x, y, layout.plot.right, y, "grid")
        doc.text(layout.plot.x - 8, y + 4, format_tick(tick), "tick muted", anchor="end")
    for tick in x_ticks:
        x = x_scale(tick)
        doc.line(x, layout.plot.y, x, layout.plot.bottom, "grid")
        doc.text(x, layout.plot.bottom + 16, format_tick(tick), "tick muted", anchor="middle")
    doc.line(layout.plot.x, layout.plot.bottom, layout.plot.right, layout.plot.bottom, "axis")
    from .base import _draw_axis_titles

    _draw_axis_titles(layout, chart)

    for series in chart.series:
        for point in series.points:
            if point.y is None or not isinstance(point.x, (int, float)):
                continue
            cx, cy = x_scale(point.x), y_scale(point.y)
            # Surface ring keeps overlapping dots readable.
            doc.circle(cx, cy, MARKER_RADIUS + 1, f"ring {series_class(series, chart, 'fill')}")
            doc.circle(
                cx, cy, MARKER_RADIUS, series_class(series, chart, "fill"),
                title=point_title(series, point, chart),
            )
    return layout


def render_dumbbell(chart: ChartData) -> Layout:
    """Before -> after per item: one hue, two shades, connected."""
    layout = build_layout(chart, left_gutter=_label_gutter(chart))
    band = category_scale(chart, layout.plot, horizontal=True)
    scale, ticks = value_scale(chart, layout.plot, anchor_zero=False, horizontal=True)
    draw_value_grid(layout, chart, scale, ticks, horizontal=True)
    draw_category_axis(layout, chart, band, horizontal=True)

    doc = layout.doc
    if len(chart.series) < 2:
        return render_bar(chart)

    before, after = chart.series[0], chart.series[1]
    for index, x in enumerate(chart.x_order):
        y = band.center(x)
        p0, p1 = before.points[index], after.points[index]
        if p0.y is None or p1.y is None:
            continue
        doc.line(scale(p0.y), y, scale(p1.y), y, "deemph-stroke")
        for point, series in ((p0, before), (p1, after)):
            cx = scale(point.y)
            doc.circle(cx, y, MARKER_RADIUS + 1, f"ring {series_class(series, chart, 'fill')}")
            doc.circle(
                cx, y, MARKER_RADIUS, series_class(series, chart, "fill"),
                title=point_title(series, point, chart),
            )
    return layout


def _last_nonzero(chart: ChartData, index: int, *, positive: bool):
    """The series that draws the visible end of a stack at this x slot."""
    found = None
    for series in chart.series:
        if index >= len(series.points):
            continue
        value = series.points[index].y
        if value is None or value == 0:
            continue
        if (value > 0) == positive:
            found = series
    return found


def _stack_totals(chart: ChartData) -> list[float]:
    """A stacked scale must reach the tallest stack, not the tallest segment."""
    totals: list[float] = [0.0]
    for index in range(len(chart.x_order)):
        positive = sum(
            s.points[index].y
            for s in chart.series
            if index < len(s.points) and s.points[index].y and s.points[index].y > 0
        )
        negative = sum(
            s.points[index].y
            for s in chart.series
            if index < len(s.points) and s.points[index].y and s.points[index].y < 0
        )
        totals.extend([positive, negative])
    return totals


def _segments(series, band, scale) -> list[list[tuple[float, float]]]:
    """Split a series at gaps - a missing value is a gap, never a zero."""
    segments: list[list[tuple[float, float]]] = []
    current: list[tuple[float, float]] = []
    for point in series.points:
        if point.y is None:
            if current:
                segments.append(current)
                current = []
            continue
        current.append((band.center(point.x), scale(point.y)))
    if current:
        segments.append(current)
    return segments


def _last_point(series, band, scale):
    for point in reversed(series.points):
        if point.y is not None:
            return band.center(point.x), scale(point.y), point
    return None


def _esc(text: str) -> str:
    return str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
