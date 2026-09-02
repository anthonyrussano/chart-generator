"""The form heuristic, as code.

An agent that has just harvested some data usually knows what the data *is* but
not what form reads it best. This module answers that: given a DataSet, it
returns a ranked list of forms with the reason for each, and it is willing to
say the answer is not a chart at all.

The rules come from the data-viz method's form table:

  * a single current value is a stat tile, not a one-bar bar chart
  * a ratio against a limit is a meter, not a two-slice pie
  * more than ~7 classes that all carry meaning is a table
  * when one series is the point and the rest are context, that is emphasis
  * sequential is the safe default; categorical is for when the series are
    genuinely the subject
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .model import DataSet

# Column names that usually mean "this is a share of a whole".
_SHARE_HINTS = ("percent", "pct", "share", "ratio", "rate", "utilization", "usage")
_LIMIT_HINTS = ("limit", "quota", "capacity", "budget", "target", "max", "total")


@dataclass(slots=True)
class Recommendation:
    form: str
    reason: str
    confidence: str = "medium"
    spec_hints: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class Advice:
    recommendations: list[Recommendation] = field(default_factory=list)
    cautions: list[str] = field(default_factory=list)
    shape: dict[str, Any] = field(default_factory=dict)

    @property
    def best(self) -> Recommendation | None:
        return self.recommendations[0] if self.recommendations else None

    def to_dict(self) -> dict[str, Any]:
        return {
            "shape": self.shape,
            "recommended": self.best.form if self.best else None,
            "recommendations": [
                {
                    "form": r.form,
                    "reason": r.reason,
                    "confidence": r.confidence,
                    "spec_hints": r.spec_hints,
                }
                for r in self.recommendations
            ],
            "cautions": self.cautions,
        }


def describe_shape(dataset: DataSet) -> dict[str, Any]:
    numeric = [c.name for c in dataset.columns if c.kind == "number"]
    temporal = [c.name for c in dataset.columns if c.kind == "time"]
    categorical = [c.name for c in dataset.columns if c.kind == "category"]

    cardinality = {
        name: len({_hashable(r.get(name)) for r in dataset.rows}) for name in categorical
    }
    return {
        "row_count": len(dataset.rows),
        "numeric_columns": numeric,
        "time_columns": temporal,
        "category_columns": categorical,
        "category_cardinality": cardinality,
    }


def recommend(dataset: DataSet) -> Advice:
    shape = describe_shape(dataset)
    advice = Advice(shape=shape)

    numeric = shape["numeric_columns"]
    temporal = shape["time_columns"]
    categorical = shape["category_columns"]
    rows = shape["row_count"]
    cardinality = shape["category_cardinality"]

    if rows == 0:
        advice.cautions.append("The dataset has no rows; there is nothing to plot.")
        return advice

    if not numeric:
        advice.cautions.append(
            "No numeric column was found. Charts need a measure - check whether "
            "the values parsed, or pass --y explicitly."
        )
        return advice

    value_column = numeric[0]

    # --- is it even a chart? ---------------------------------------------

    if rows == 1:
        advice.recommendations.append(
            Recommendation(
                "stat",
                "A single row is one current value. A stat tile (or hero number) "
                "says it directly; a one-bar bar chart does not.",
                "high",
                {"y": value_column},
            )
        )
        limit = _find_limit_column(dataset)
        if limit or _looks_like_share(value_column):
            advice.recommendations.append(
                Recommendation(
                    "meter",
                    "The value reads as a ratio against a limit, which is a meter - "
                    "not a two-slice pie.",
                    "medium",
                    {"y": value_column, "target": limit},
                )
            )
        return advice

    if 2 <= rows <= 6 and not temporal and len(numeric) == 1 and len(categorical) <= 1:
        advice.recommendations.append(
            Recommendation(
                "stat",
                f"{rows} headline numbers read best as a KPI row of stat tiles.",
                "medium",
                {"y": value_column, "x": categorical[0] if categorical else None},
            )
        )

    # --- trend over time --------------------------------------------------

    if temporal:
        time_column = temporal[0]
        # A category that identifies every row uniquely IS the subject, and a
        # time column beside it records when each row was written rather than
        # marking a trend. This is the shape `chart-gen record` produces;
        # reading it as a trend gives a line chart with one point per series.
        unique_category = next(
            (n for n in categorical if cardinality.get(n, 0) == rows), None
        )
        if unique_category and rows > 1:
            advice.recommendations.append(
                Recommendation(
                    "bar" if _long_labels(dataset, unique_category) else "column",
                    f"Each row is one observation of '{unique_category}', which "
                    f"identifies it uniquely. '{time_column}' records when the row "
                    "was written rather than marking a trend, so the category is "
                    "the axis.",
                    "high",
                    {"x": unique_category, "y": value_column, "sort": "desc"},
                )
            )
            return _finish(advice, dataset)

        split = _series_split(
            categorical, cardinality, exclude={time_column}, min_points=rows
        )
        if split:
            advice.recommendations.insert(
                0,
                Recommendation(
                    "line",
                    f"'{time_column}' is a time column and '{split}' splits it into "
                    "distinct series, so the job is telling series apart over time.",
                    "high",
                    {"x": time_column, "y": value_column, "series": split},
                ),
            )
            if cardinality.get(split, 0) > 4:
                advice.cautions.append(
                    f"'{split}' has {cardinality[split]} values. Past four series, "
                    "end labels collide - use emphasis, small multiples, or fold "
                    "the tail into 'Other' with --top-n."
                )
        elif len(numeric) > 1:
            measures = ",".join(numeric)
            advice.recommendations.insert(
                0,
                Recommendation(
                    "line",
                    f"'{time_column}' is a time column and {len(numeric)} measures "
                    f"({measures}) trend across it. All of them plot on one shared "
                    "axis as separate series - never a second y axis.",
                    "high",
                    {"x": time_column, "y": measures},
                ),
            )
            spread = _magnitude_spread(dataset, numeric)
            if spread > 20:
                advice.cautions.append(
                    f"These measures differ by about {spread:.0f}x in magnitude. On one "
                    "axis the smaller ones flatten to nothing - render them as "
                    "separate charts, or index each to a common base at t0."
                )
        else:
            advice.recommendations.insert(
                0,
                Recommendation(
                    "area",
                    f"'{time_column}' is a time column with one measure, so a single "
                    "series over time. Area reads honestly for exactly one series.",
                    "high",
                    {"x": time_column, "y": value_column},
                ),
            )
            advice.recommendations.append(
                Recommendation(
                    "line",
                    "A plain line if the filled magnitude is not the point.",
                    "medium",
                    {"x": time_column, "y": value_column},
                )
            )
        return _finish(advice, dataset)

    # --- two measures -----------------------------------------------------

    if len(numeric) >= 2 and rows >= 8 and not _looks_like_index(numeric[0], dataset):
        advice.recommendations.append(
            Recommendation(
                "scatter",
                f"Two numeric columns across {rows} rows is a relationship between "
                "measures. Note the three-hue cap: scatter puts every series against "
                "every other, and the palette only clears the all-pairs floors at three.",
                "medium",
                {"x": numeric[0], "y": numeric[1]},
            )
        )

    # --- magnitude across categories --------------------------------------

    if categorical:
        primary = _widest_category(categorical, cardinality)
        count = cardinality.get(primary, 0)
        split = _series_split(
            categorical, cardinality, exclude={primary}, min_points=rows
        )

        if count > 12:
            advice.cautions.append(
                f"'{primary}' has {count} distinct values. Past about a dozen bars "
                "the chart stops being scannable - sort and use --top-n, or ship a table."
            )

        if split:
            grid_size = count * cardinality.get(split, 0)
            if grid_size >= 12 and grid_size <= 400:
                advice.recommendations.append(
                    Recommendation(
                        "heatmap",
                        f"'{primary}' x '{split}' is a {count}x{cardinality[split]} grid "
                        "of magnitudes, which a heatmap reads at a glance on one hue.",
                        "medium",
                        {"x": primary, "y": value_column, "series": split},
                    )
                )
            advice.recommendations.append(
                Recommendation(
                    "stacked-bar" if _long_labels(dataset, primary) else "stacked-column",
                    f"'{split}' partitions each '{primary}' - a part-to-whole reading.",
                    "medium",
                    {"x": primary, "y": value_column, "series": split},
                )
            )

        horizontal = _long_labels(dataset, primary) or count > 8
        advice.recommendations.append(
            Recommendation(
                "bar" if horizontal else "column",
                (
                    "Comparing magnitude across categories. Horizontal, because the "
                    "category names are long or numerous."
                    if horizontal
                    else "Comparing magnitude across categories."
                ),
                "high",
                {"x": primary, "y": value_column, "sort": "desc"},
            )
        )

        if _has_negatives(dataset, value_column):
            advice.recommendations.insert(
                0,
                Recommendation(
                    "diverging-bar",
                    "Values fall on both sides of zero, so the job is polarity: "
                    "two hues that read as opposite, neutral at the baseline.",
                    "high",
                    {"x": primary, "y": value_column},
                ),
            )

    if not advice.recommendations:
        advice.recommendations.append(
            Recommendation(
                "column",
                "Fallback: one measure plotted across the rows in order.",
                "low",
                {"y": value_column},
            )
        )

    return _finish(advice, dataset)


_CONFIDENCE_RANK = {"high": 0, "medium": 1, "low": 2}


def _finish(advice: Advice, dataset: DataSet) -> Advice:
    """Rank by confidence, then attach the form-independent cautions."""
    advice.recommendations.sort(
        key=lambda r: _CONFIDENCE_RANK.get(r.confidence, 3)
    )
    # Only columns that would drive COLOR matter here. A category axis with
    # many values is a long bar chart, which is fine; many color classes is not.
    color_columns = {
        r.spec_hints.get("series") for r in advice.recommendations
    } - {None}
    for name in sorted(color_columns):
        distinct = len({_hashable(r.get(name)) for r in dataset.rows})
        if distinct > 7:
            advice.cautions.append(
                f"'{name}' has {distinct} classes and would drive color. Past about "
                "seven, color classes blur - fold the tail into 'Other' with "
                "--top-n, facet, or use a table."
            )
    return advice


def _hashable(value: Any) -> Any:
    return value if isinstance(value, (str, int, float, bool, type(None))) else str(value)


def _series_split(
    categorical: list[str],
    cardinality: dict[str, int],
    exclude: set[str],
    min_points: int | None = None,
) -> str | None:
    """Pick a column to split series on, if one earns it.

    A split that leaves fewer than two points per series is not a split - it is
    a way of turning one readable chart into several one-point ones.
    """
    for name in categorical:
        if name in exclude:
            continue
        count = cardinality.get(name, 0)
        if not 2 <= count <= 24:
            continue
        if min_points is not None and count and min_points / count < 2:
            continue
        return name
    return None


def _widest_category(categorical: list[str], cardinality: dict[str, int]) -> str:
    return max(categorical, key=lambda n: cardinality.get(n, 0))


def _long_labels(dataset: DataSet, column: str, threshold: int = 12) -> bool:
    lengths = [len(str(r.get(column, ""))) for r in dataset.rows]
    if not lengths:
        return False
    return sum(lengths) / len(lengths) > threshold


def _has_negatives(dataset: DataSet, column: str) -> bool:
    return any(
        isinstance(r.get(column), (int, float)) and r[column] < 0 for r in dataset.rows
    )


def _magnitude_spread(dataset: DataSet, columns: list[str]) -> float:
    """Ratio between the largest and smallest peak across measures."""
    peaks: list[float] = []
    for name in columns:
        values = [
            abs(r[name]) for r in dataset.rows
            if isinstance(r.get(name), (int, float)) and not isinstance(r.get(name), bool)
        ]
        if values and max(values) > 0:
            peaks.append(max(values))
    if len(peaks) < 2:
        return 1.0
    return max(peaks) / min(peaks)


def _looks_like_share(name: str) -> bool:
    lowered = name.lower()
    return any(hint in lowered for hint in _SHARE_HINTS)


def _find_limit_column(dataset: DataSet) -> str | None:
    for column in dataset.columns:
        if column.kind == "number" and any(h in column.name.lower() for h in _LIMIT_HINTS):
            return column.name
    return None


def _looks_like_index(name: str, dataset: DataSet) -> bool:
    """A 0,1,2,... column is a row number, not a measure."""
    values = [r.get(name) for r in dataset.rows]
    if not all(isinstance(v, (int, float)) for v in values):
        return False
    return values == list(range(len(values))) or values == list(
        range(1, len(values) + 1)
    )


def format_advice(advice: Advice) -> str:
    """Human- and agent-readable text for the CLI."""
    lines: list[str] = []
    shape = advice.shape
    lines.append(
        f"{shape.get('row_count', 0)} rows | "
        f"numeric: {', '.join(shape.get('numeric_columns') or []) or '(none)'} | "
        f"time: {', '.join(shape.get('time_columns') or []) or '(none)'} | "
        f"category: {', '.join(shape.get('category_columns') or []) or '(none)'}"
    )
    lines.append("")
    if not advice.recommendations:
        lines.append("No form recommended.")
    for index, rec in enumerate(advice.recommendations, start=1):
        marker = "->" if index == 1 else "  "
        hints = " ".join(
            f"--{k.replace('_', '-')} {v}" for k, v in rec.spec_hints.items() if v is not None
        )
        lines.append(f"{marker} {rec.form}  [{rec.confidence}]")
        lines.append(f"     {rec.reason}")
        if hints:
            lines.append(f"     chart-gen chart ... --form {rec.form} {hints}")
    if advice.cautions:
        lines.append("")
        lines.append("Cautions:")
        for caution in advice.cautions:
            lines.append(f"  - {caution}")
    return "\n".join(lines)
