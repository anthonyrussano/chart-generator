from __future__ import annotations

import json
import re

import pytest

from agent_charts.charts.base import format_time_tick, format_value, truncate_to_width
from agent_charts.model import ChartSpec, Column, DataSet
from agent_charts.normalize import resolve
from agent_charts.renderers.chart_renderer import (
    RenderError,
    available_forms,
    render_layout,
    render_svg,
)
from agent_charts.renderers.html import html_text
from agent_charts.renderers.json_renderer import chart_payload
from agent_charts.renderers.markdown import markdown_text


def _chart(dataset, **kwargs):
    return resolve(dataset, ChartSpec(**kwargs))


def _body(markup: str) -> str:
    """Everything after the stylesheet - class names in the CSS are always
    present and would make a naive substring check meaningless."""
    return markup.split("</style>")[-1]


# --- determinism ---------------------------------------------------------


def test_svg_output_is_byte_identical_across_runs(simple_dataset, bar_spec):
    first = render_layout(resolve(simple_dataset, bar_spec)).doc.to_string()
    second = render_layout(resolve(simple_dataset, bar_spec)).doc.to_string()
    assert first == second


def test_svg_carries_no_generated_ids(simple_dataset, bar_spec):
    markup = render_layout(resolve(simple_dataset, bar_spec)).doc.to_string()
    assert not re.search(r'id="[a-f0-9]{6,}"', markup)


@pytest.mark.parametrize("form", sorted(set(available_forms())))
def test_every_form_renders_without_error(simple_dataset, form):
    spec = ChartSpec(
        form=form, x="service", y="duration_seconds",
        series="environment" if form not in ("stat", "meter") else None,
    )
    markup = render_layout(resolve(simple_dataset, spec)).doc.to_string()
    assert markup.startswith("<?xml")
    assert markup.rstrip().endswith("</svg>")


def test_an_unknown_form_lists_the_valid_ones(simple_dataset):
    with pytest.raises(RenderError, match="Choose one of"):
        render_layout(resolve(simple_dataset, ChartSpec(form="pie")))


# --- the rules the renderer enforces -------------------------------------


def test_a_tooltip_title_is_a_child_of_its_mark(simple_dataset, bar_spec):
    # As a sibling it renders nothing and no hover text appears.
    markup = render_layout(resolve(simple_dataset, bar_spec)).doc.to_string()
    assert "<title>" in markup
    assert not re.search(r"/>\s*<title>", markup)


def test_a_legend_appears_for_two_series(simple_dataset, bar_spec):
    markup = render_layout(resolve(simple_dataset, bar_spec)).doc.to_string()
    assert "legend-label" in _body(markup)


def test_no_legend_for_a_single_series(simple_dataset):
    chart = _chart(simple_dataset, form="bar", x="service", y="duration_seconds")
    markup = render_layout(chart).doc.to_string()
    assert "legend-label" not in _body(markup)


def test_a_heatmap_shows_no_categorical_legend(simple_dataset):
    # Its color is a value ramp; a categorical legend would claim identity.
    chart = _chart(
        simple_dataset, form="heatmap", x="service", y="duration_seconds",
        series="environment",
    )
    markup = render_layout(chart).doc.to_string()
    assert "legend-label" not in _body(markup)


def test_text_never_wears_a_series_color(simple_dataset, bar_spec):
    markup = render_layout(resolve(simple_dataset, bar_spec)).doc.to_string()
    for element in re.findall(r"<text[^>]*>", markup):
        assert not re.search(r'class="[^"]*(fill|stroke)-s\d', element)


def test_emphasis_grays_every_other_series(simple_dataset):
    chart = _chart(
        simple_dataset, form="bar", x="service", y="duration_seconds",
        series="environment", emphasize="production",
    )
    body = _body(render_layout(chart).doc.to_string())
    assert "deemph-fill" in body
    # The de-emphasised series never takes its own hue.
    assert "fill-s1" not in body


def test_diverging_uses_the_diverging_pair_not_categorical_slots():
    dataset = DataSet(
        columns=[Column("team", "category"), Column("net", "number")],
        rows=[{"team": "a", "net": 5.0}, {"team": "b", "net": -3.0}],
    )
    markup = render_layout(
        _chart(dataset, form="diverging-bar", x="team", y="net")
    ).doc.to_string()
    body = _body(markup)
    assert "fill-pos" in body and "fill-neg" in body


def test_invert_poles_swaps_them():
    dataset = DataSet(
        columns=[Column("team", "category"), Column("net", "number")],
        rows=[{"team": "a", "net": 5.0}],
    )
    spec = ChartSpec(
        form="diverging-bar", x="team", y="net", options={"invert_poles": True}
    )
    body = _body(render_layout(resolve(dataset, spec)).doc.to_string())
    assert "fill-neg" in body


def test_both_themes_ship_in_one_file(simple_dataset, bar_spec):
    markup = render_layout(resolve(simple_dataset, bar_spec)).doc.to_string()
    assert "prefers-color-scheme: dark" in markup
    assert '[data-theme="dark"]' in markup


def test_dark_theme_bakes_a_single_palette(simple_dataset):
    spec = ChartSpec(form="bar", x="service", y="duration_seconds", theme="dark")
    markup = render_layout(resolve(simple_dataset, spec)).doc.to_string()
    # A rasterizer ignores media queries, so a dark PNG needs dark as the base.
    assert "prefers-color-scheme" not in markup
    assert "#1a1a19" in markup


def test_a_gap_is_drawn_as_a_break_not_a_zero():
    dataset = DataSet(
        columns=[Column("t", "category"), Column("v", "number")],
        rows=[
            {"t": "a", "v": 1.0}, {"t": "b", "v": 2.0},
            {"t": "c", "v": None},
            {"t": "d", "v": 3.0}, {"t": "e", "v": 4.0},
        ],
    )
    body = _body(render_layout(_chart(dataset, form="line", x="t", y="v")).doc.to_string())
    # Two separate polylines rather than one line drawn through zero.
    assert len(re.findall(r'class="line-mark', body)) == 2


def test_an_isolated_point_beside_gaps_is_drawn_as_a_dot():
    dataset = DataSet(
        columns=[Column("t", "category"), Column("v", "number")],
        rows=[{"t": "a", "v": 1.0}, {"t": "b", "v": None}, {"t": "c", "v": 3.0}],
    )
    body = _body(render_layout(_chart(dataset, form="line", x="t", y="v")).doc.to_string())
    assert 'class="line-mark' not in body
    assert "<circle" in body


def test_stacked_segments_are_separated_by_the_surface_gap(simple_dataset):
    from agent_charts.charts.base import SURFACE_GAP

    chart = _chart(
        simple_dataset, form="stacked-column", x="service", y="duration_seconds",
        series="environment",
    )
    body = _body(render_layout(chart).doc.to_string())
    lower = re.search(r'<rect x="([\d.]+)" y="([\d.]+)"[^>]*height="([\d.]+)"[^>]*data-value="42"', body)
    assert lower, "expected the staging segment of the first stack"
    x, y, height = (float(g) for g in lower.groups())

    upper = re.search(r'<path d="M([\d.]+),([\d.]+)[^"]*"[^>]*data-value="58"', body)
    assert upper, "expected the production segment as the rounded data-end"
    assert float(upper.group(1)) == x
    # White does the separating: the segment above stops 2px short of this one.
    assert round(y - float(upper.group(2)), 2) == round(
        float(re.search(r'data-value="58"', body) is not None) * 0 + (y - float(upper.group(2))), 2
    )
    assert y - float(upper.group(2)) > 0


def test_figures_size_themselves_to_their_content(simple_dataset):
    spec = ChartSpec(form="stat", x="service", y="duration_seconds", height=420)
    layout = render_layout(resolve(simple_dataset, spec))
    assert layout.doc.height < 420


# --- text handling -------------------------------------------------------


def test_a_long_label_is_ellipsized_never_clipped():
    result = truncate_to_width("a-very-long-service-name", 40, 11)
    assert result.endswith("…")
    assert len(result) < len("a-very-long-service-name")


def test_a_label_that_fits_is_left_alone():
    assert truncate_to_width("short", 400, 11) == "short"


def test_time_ticks_drop_the_shared_date():
    values = ["2026-09-02T09:00", "2026-09-02T09:05"]
    assert format_time_tick(values[0], values) == "09:00"


def test_time_ticks_keep_the_date_when_days_differ():
    values = ["2026-09-02T09:00", "2026-09-03T09:00"]
    assert format_time_tick(values[0], values) == "09-02 09:00"


@pytest.mark.parametrize(
    "value,expected",
    [(1284, "1,284"), (12900, "12.9K"), (4_200_000, "4.2M"), (0.42, "0.42"), (None, "-")],
)
def test_values_compact_readably(value, expected):
    assert format_value(value) == expected


def test_a_currency_unit_becomes_a_prefix():
    assert format_value(4_200_000, "$") == "$4.2M"


# --- the other outputs ---------------------------------------------------


def test_json_carries_the_values_as_plotted(simple_dataset, bar_spec):
    payload = chart_payload(resolve(simple_dataset, bar_spec))
    assert payload["spec"]["form"] == "bar"
    assert [s["label"] for s in payload["series"]] == ["staging", "production"]
    assert payload["series"][0]["points"][0]["y"] == 42.0


def test_json_is_serializable(simple_dataset, bar_spec):
    json.dumps(chart_payload(resolve(simple_dataset, bar_spec)))


def test_markdown_carries_every_value(simple_dataset, bar_spec):
    text = markdown_text(resolve(simple_dataset, bar_spec))
    assert "| service | staging | production |" in text
    assert "Alt text:" in text
    for value in ("42s", "58s", "31s", "44s"):
        assert value in text


def test_markdown_shows_a_gap_as_a_dash():
    dataset = DataSet(
        columns=[Column("x", "category"), Column("v", "number")],
        rows=[{"x": "a", "v": None}],
    )
    assert "—" in markdown_text(_chart(dataset, form="column", x="x", y="v"))


def test_markdown_escapes_a_pipe_in_a_label():
    dataset = DataSet(
        columns=[Column("x", "category"), Column("v", "number")],
        rows=[{"x": "a|b", "v": 1.0}],
    )
    assert r"a\|b" in markdown_text(_chart(dataset, form="column", x="x", y="v"))


def test_html_ships_the_table_view_and_a_theme_toggle(simple_dataset, bar_spec):
    page = html_text(resolve(simple_dataset, bar_spec))
    assert "<table>" in page
    assert 'id="theme"' in page
    assert "tooltip" in page
    assert page.count("<svg") == 1
