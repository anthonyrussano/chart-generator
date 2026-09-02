"""Form dispatch: ChartData in, an SVG document out."""

from __future__ import annotations

from pathlib import Path

from ..charts import cartesian, figures, heatmap
from ..charts.base import Layout
from ..model import ChartData

_RENDERERS = {
    "bar": lambda c: cartesian.render_bar(c, stacked=False),
    "column": lambda c: cartesian.render_column(c, stacked=False),
    "stacked-bar": lambda c: cartesian.render_bar(c, stacked=True),
    "stacked-column": lambda c: cartesian.render_column(c, stacked=True),
    "diverging-bar": cartesian.render_diverging_bar,
    "line": lambda c: cartesian.render_line(c, area=False),
    "area": lambda c: cartesian.render_line(c, area=True),
    "scatter": cartesian.render_scatter,
    "dumbbell": cartesian.render_dumbbell,
    "heatmap": heatmap.render_heatmap,
    "stat": figures.render_stat,
    "meter": figures.render_meter,
}


class RenderError(ValueError):
    pass


def render_layout(chart: ChartData) -> Layout:
    renderer = _RENDERERS.get(chart.spec.form)
    if renderer is None:
        raise RenderError(
            f"Unknown form '{chart.spec.form}'. "
            f"Choose one of: {', '.join(sorted(_RENDERERS))}"
        )
    return renderer(chart)


def render_svg(chart: ChartData, output_path: Path | None = None) -> tuple[str, Layout]:
    layout = render_layout(chart)
    markup = layout.doc.to_string(standalone=True)
    if output_path is not None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(markup, encoding="utf-8")
    return markup, layout


def render_svg_fragment(chart: ChartData) -> tuple[str, Layout]:
    """The same SVG without the XML prolog, for embedding in HTML."""
    layout = render_layout(chart)
    return layout.doc.to_string(standalone=False), layout


def available_forms() -> list[str]:
    return sorted(_RENDERERS)
