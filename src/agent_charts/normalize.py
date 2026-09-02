"""Turn a DataSet plus a ChartSpec into plottable series.

Two rules from the data-viz method are enforced here rather than left to the
renderer:

  * Color follows the entity, not its rank. Slots are assigned by first
    appearance in the data and never reshuffled by sorting or filtering.
  * A series count past the form's cap folds into 'Other'. A generated ninth
    hue is indistinguishable from an existing one under CVD.
"""

from __future__ import annotations

from typing import Any

from .model import ChartData, ChartSpec, DataSet, Point, Series
from .theme import series_cap

OTHER_LABEL = "Other"


class NormalizeError(ValueError):
    """Raised when a spec asks for columns the dataset does not have."""


def _require_column(dataset: DataSet, name: str, role: str) -> None:
    if dataset.column(name) is None:
        available = ", ".join(dataset.column_names()) or "(none)"
        raise NormalizeError(
            f"Column '{name}' named as {role} is not in the dataset. Available: {available}"
        )


def y_columns(spec: ChartSpec) -> list[str]:
    """`y` accepts a comma-separated list. Several numeric columns is the wide
    shape agents produce constantly, and each column becomes one series."""
    if not spec.y:
        return []
    return [name.strip() for name in str(spec.y).split(",") if name.strip()]


def infer_axes(dataset: DataSet, spec: ChartSpec) -> ChartSpec:
    """Fill in x/y/series when the spec leaves them out.

    A series split is only ever inferred when the caller named no axes at all.
    If they named an x, that is their framing of the chart, and quietly adding
    a split they did not ask for would silently change what the chart says.
    """
    numeric = [c.name for c in dataset.columns if c.kind == "number"]
    temporal = [c.name for c in dataset.columns if c.kind == "time"]
    categorical = [c.name for c in dataset.columns if c.kind == "category"]

    x_was_given = spec.x is not None

    if spec.x is None:
        spec.x = (temporal or categorical or numeric or [None])[0]
    if spec.y is None:
        candidates = [n for n in numeric if n != spec.x]
        spec.y = (candidates or [None])[0]
    if spec.series is None and not x_was_given and spec.form != "scatter":
        # A second categorical column is a series split only if it is not the x.
        candidates = [n for n in categorical if n not in (spec.x, spec.y)]
        # Only split when it actually partitions the data.
        for name in candidates:
            distinct = {r.get(name) for r in dataset.rows}
            if 2 <= len(distinct) <= 24:
                spec.series = name
                break
    return spec


def _sorted_x_order(order: list[Any], kind: str) -> list[Any]:
    if kind in ("time", "number"):
        return sorted(order, key=lambda v: (v is None, v))
    return order


def resolve(dataset: DataSet, spec: ChartSpec) -> ChartData:
    """Build the ChartData a renderer consumes."""
    spec = infer_axes(dataset, spec)

    if spec.form in ("stat", "meter"):
        return _resolve_scalar(dataset, spec)

    if spec.x is None or spec.y is None:
        raise NormalizeError(
            "Could not determine x and y columns. Pass --x and --y explicitly. "
            f"Available: {', '.join(dataset.column_names()) or '(none)'}"
        )
    _require_column(dataset, spec.x, "x")
    for measure in y_columns(spec):
        _require_column(dataset, measure, "y")
    if spec.series:
        _require_column(dataset, spec.series, "series")

    x_column = dataset.column(spec.x)
    x_kind = x_column.kind if x_column else "category"

    measures = y_columns(spec)
    if len(measures) > 1:
        return _resolve_wide(dataset, spec, measures, x_kind)

    # First-appearance order is the identity anchor for both x slots and hues.
    x_order: list[Any] = []
    grouped: dict[Any, list[tuple[Any, float | None, dict]]] = {}
    group_order: list[Any] = []

    for row in dataset.rows:
        x_value = row.get(spec.x)
        if x_value not in x_order:
            x_order.append(x_value)
        key = row.get(spec.series) if spec.series else spec.y
        if key not in grouped:
            grouped[key] = []
            group_order.append(key)
        grouped[key].append((x_value, _as_float(row.get(spec.y)), row))

    x_order = _sorted_x_order(x_order, x_kind)

    series_list: list[Series] = []
    for key in group_order:
        label = str(key) if key is not None else "(unset)"
        points = [
            Point(x=x, y=y, attrs={"row": row})
            for x, y, row in grouped[key]
        ]
        series_list.append(Series(id=_slug(label), label=label, points=points))

    series_list = _apply_top_n(series_list, spec)
    series_list = _fold_to_cap(series_list, spec)
    _assign_slots(series_list)

    # Align before sorting: alignment is what aggregates repeated x values
    # into one slot, and sorting unaggregated points would put the same
    # category on the axis more than once.
    for series in series_list:
        series.points = _align(series.points, x_order)

    if spec.sort and len(series_list) == 1:
        x_order = _sort_single_series(series_list[0], spec.sort)
        for series in series_list:
            series.points = _align(series.points, x_order)

    return ChartData(
        spec=spec,
        series=series_list,
        x_kind=x_kind,
        x_order=x_order,
        metadata={
            **dataset.metadata,
            "series_count": len(series_list),
            "x_column": spec.x,
            "y_column": spec.y,
            "series_column": spec.series,
        },
    )


def _resolve_scalar(dataset: DataSet, spec: ChartSpec) -> ChartData:
    """Stat tiles and meters read one value per row, with an optional label."""
    label_column = spec.x
    value_column = spec.y
    if value_column is None:
        raise NormalizeError("A stat or meter needs a numeric column; pass --y.")
    _require_column(dataset, value_column, "value")

    points: list[Point] = []
    for index, row in enumerate(dataset.rows):
        label = str(row.get(label_column)) if label_column else spec.title or value_column
        points.append(
            Point(
                x=label,
                y=_as_float(row.get(value_column)),
                label=label,
                attrs={"row": row},
            )
        )

    series = Series(id="value", label=value_column, points=points, slot=0)
    return ChartData(
        spec=spec,
        series=[series],
        x_kind="category",
        x_order=[p.x for p in points],
        metadata={**dataset.metadata, "series_count": 1, "y_column": value_column},
    )


def _resolve_wide(
    dataset: DataSet, spec: ChartSpec, measures: list[str], x_kind: str
) -> ChartData:
    """One series per named measure, all on a single shared axis.

    This is emphatically not a dual-axis chart: every measure is plotted
    against the same scale. When their magnitudes are far apart that scale
    flattens the smaller ones, which is reported as a blind spot rather than
    papered over with a second axis.
    """
    for measure in measures:
        _require_column(dataset, measure, "y")

    x_order: list[Any] = []
    for row in dataset.rows:
        value = row.get(spec.x)
        if value not in x_order:
            x_order.append(value)
    x_order = _sorted_x_order(x_order, x_kind)

    series_list: list[Series] = []
    for measure in measures:
        points = [
            Point(x=row.get(spec.x), y=_as_float(row.get(measure)), attrs={"row": row})
            for row in dataset.rows
        ]
        series_list.append(
            Series(id=_slug(measure), label=measure, points=_align(points, x_order))
        )

    _assign_slots(series_list)
    return ChartData(
        spec=spec,
        series=series_list,
        x_kind=x_kind,
        x_order=x_order,
        metadata={
            **dataset.metadata,
            "series_count": len(series_list),
            "x_column": spec.x,
            "y_columns": measures,
            "layout": "wide",
        },
    )


def _as_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(str(value).replace(",", ""))
    except ValueError:
        return None


def _slug(text: str) -> str:
    out = "".join(ch if ch.isalnum() else "-" for ch in text.lower()).strip("-")
    while "--" in out:
        out = out.replace("--", "-")
    return out or "series"


def _series_total(series: Series) -> float:
    return sum(abs(v) for v in series.y_values())


def _apply_top_n(series_list: list[Series], spec: ChartSpec) -> list[Series]:
    if not spec.top_n or len(series_list) <= spec.top_n:
        return series_list
    ranked = sorted(series_list, key=_series_total, reverse=True)
    keep = {s.id for s in ranked[: spec.top_n]}
    return _fold(series_list, keep)


def _fold_to_cap(series_list: list[Series], spec: ChartSpec) -> list[Series]:
    cap = series_cap(spec.form)
    if len(series_list) <= cap:
        return series_list
    ranked = sorted(series_list, key=_series_total, reverse=True)
    # Leave one slot for 'Other' so the folded series is itself visible.
    keep = {s.id for s in ranked[: cap - 1]}
    return _fold(series_list, keep)


def _fold(series_list: list[Series], keep: set[str]) -> list[Series]:
    """Sum the tail into a single 'Other' series, preserving entity order."""
    kept = [s for s in series_list if s.id in keep]
    tail = [s for s in series_list if s.id not in keep]
    if not tail:
        return kept

    totals: dict[Any, float] = {}
    order: list[Any] = []
    for series in tail:
        for point in series.points:
            if point.x not in totals:
                totals[point.x] = 0.0
                order.append(point.x)
            if point.y is not None:
                totals[point.x] += point.y

    other = Series(
        id="other",
        label=OTHER_LABEL,
        points=[Point(x=x, y=totals[x]) for x in order],
        attrs={"folded_from": [s.label for s in tail]},
    )
    return kept + [other]


def _assign_slots(series_list: list[Series]) -> None:
    for index, series in enumerate(series_list):
        series.slot = index


def _sort_single_series(series: Series, mode: str) -> list[Any]:
    reverse = mode in ("desc", "value-desc")
    if mode in ("asc", "desc", "value-asc", "value-desc"):
        ordered = sorted(
            series.points,
            key=lambda p: (p.y is None, p.y if p.y is not None else 0.0),
            reverse=reverse,
        )
        return [p.x for p in ordered]
    if mode in ("label", "label-asc", "label-desc"):
        ordered = sorted(series.points, key=lambda p: str(p.x), reverse=mode == "label-desc")
        return [p.x for p in ordered]
    return [p.x for p in series.points]


def _align(points: list[Point], x_order: list[Any]) -> list[Point]:
    """Give every series the same x slots, so stacks and groups line up."""
    by_x: dict[Any, Point] = {}
    for point in points:
        existing = by_x.get(point.x)
        if existing is None:
            by_x[point.x] = point
        elif existing.y is None:
            by_x[point.x] = point
        elif point.y is not None:
            # Repeated x within one series means the caller handed us
            # unaggregated rows; summing is the only non-lossy reading.
            existing.y += point.y
    return [by_x.get(x, Point(x=x, y=None)) for x in x_order]
