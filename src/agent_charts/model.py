from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# Column kinds drive both scale selection and the form heuristic.
COLUMN_KINDS = ("category", "number", "time")

# Every chart form the renderer knows how to draw.
FORMS = (
    "bar",
    "column",
    "stacked-bar",
    "stacked-column",
    "diverging-bar",
    "line",
    "area",
    "scatter",
    "heatmap",
    "dumbbell",
    "stat",
    "meter",
)


@dataclass(slots=True)
class Column:
    name: str
    kind: str
    attrs: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class DataSet:
    """A tabular collection result. Rows are plain dicts keyed by column name."""

    columns: list[Column] = field(default_factory=list)
    rows: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def column(self, name: str) -> Column | None:
        for col in self.columns:
            if col.name == name:
                return col
        return None

    def column_names(self) -> list[str]:
        return [c.name for c in self.columns]

    def values(self, name: str) -> list[Any]:
        return [row.get(name) for row in self.rows]


@dataclass(slots=True)
class Point:
    x: Any
    y: float | None
    label: str | None = None
    attrs: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class Series:
    """One resolved, plottable series. `slot` is its fixed categorical hue index."""

    id: str
    label: str
    points: list[Point] = field(default_factory=list)
    slot: int = 0
    attrs: dict[str, Any] = field(default_factory=dict)

    def y_values(self) -> list[float]:
        return [p.y for p in self.points if p.y is not None]


@dataclass(slots=True)
class ChartSpec:
    """The authored, declarative description of one chart."""

    form: str
    title: str = ""
    subtitle: str = ""
    x: str | None = None
    y: str | None = None
    series: str | None = None
    x_label: str = ""
    y_label: str = ""
    emphasize: str | None = None
    unit: str = ""
    width: int = 720
    height: int = 420
    theme: str = "auto"
    sort: str | None = None
    top_n: int | None = None
    baseline: float | None = None
    target: float | None = None
    value_format: str = "auto"
    direct_labels: str = "auto"
    options: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ChartData:
    """Everything a renderer needs: the resolved series plus the spec that made them."""

    spec: ChartSpec
    series: list[Series] = field(default_factory=list)
    x_kind: str = "category"
    x_order: list[Any] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def all_y(self) -> list[float]:
        out: list[float] = []
        for s in self.series:
            out.extend(s.y_values())
        return out
