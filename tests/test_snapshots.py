"""Golden files.

A chart is only reviewable in a diff if the same input produces the same bytes.
These snapshots are that guarantee: any change to layout, rounding, or the
palette shows up here as an explicit, reviewable diff rather than as silent
drift. Regenerate deliberately with:

    UPDATE_SNAPSHOTS=1 uv run pytest tests/test_snapshots.py
"""

from __future__ import annotations

from agent_charts.model import ChartSpec, Column, DataSet
from agent_charts.normalize import resolve
from agent_charts.renderers.chart_renderer import render_layout
from agent_charts.renderers.json_renderer import chart_payload
from agent_charts.renderers.markdown import markdown_text

import json


def _bar_chart(simple_dataset):
    return resolve(
        simple_dataset,
        ChartSpec(
            form="bar",
            title="Deploy duration",
            subtitle="staging versus production",
            x="service",
            y="duration_seconds",
            series="environment",
            unit="s",
        ),
    )


def test_bar_svg_matches_the_golden_file(simple_dataset, snapshot):
    markup = render_layout(_bar_chart(simple_dataset)).doc.to_string()
    snapshot("bar.svg", markup)


def test_bar_json_matches_the_golden_file(simple_dataset, snapshot):
    payload = chart_payload(_bar_chart(simple_dataset))
    snapshot("bar.chart.json", json.dumps(payload, indent=2) + "\n")


def test_bar_markdown_matches_the_golden_file(simple_dataset, snapshot):
    snapshot("bar.md", markdown_text(_bar_chart(simple_dataset)))


def test_line_svg_matches_the_golden_file(time_dataset, snapshot):
    chart = resolve(
        time_dataset,
        ChartSpec(
            form="line",
            title="Request latency",
            x="minute",
            y="p50_ms,p99_ms",
            unit="ms",
        ),
    )
    snapshot("line.svg", render_layout(chart).doc.to_string())


def test_stacked_column_svg_matches_the_golden_file(simple_dataset, snapshot):
    chart = resolve(
        simple_dataset,
        ChartSpec(
            form="stacked-column",
            title="Deploy duration, stacked",
            x="service",
            y="duration_seconds",
            series="environment",
            unit="s",
        ),
    )
    snapshot("stacked-column.svg", render_layout(chart).doc.to_string())


def test_heatmap_svg_matches_the_golden_file(snapshot):
    dataset = DataSet(
        columns=[
            Column("day", "category"), Column("endpoint", "category"),
            Column("errors", "number"),
        ],
        rows=[
            {"day": day, "endpoint": endpoint, "errors": float(value)}
            for day, values in (("Mon", (4, 12)), ("Tue", (6, 19)))
            for endpoint, value in zip(("/login", "/search"), values)
        ],
    )
    chart = resolve(
        dataset,
        ChartSpec(form="heatmap", title="Errors", x="day", y="errors", series="endpoint"),
    )
    snapshot("heatmap.svg", render_layout(chart).doc.to_string())


def test_stat_svg_matches_the_golden_file(snapshot):
    dataset = DataSet(
        columns=[
            Column("metric", "category"), Column("value", "number"),
            Column("delta", "number"),
        ],
        rows=[
            {"metric": "Requests", "value": 128400.0, "delta": 4.2},
            {"metric": "Error rate", "value": 0.42, "delta": -0.11},
        ],
    )
    chart = resolve(
        dataset,
        ChartSpec(form="stat", title="Release health", x="metric", y="value"),
    )
    snapshot("stat.svg", render_layout(chart).doc.to_string())


def test_output_is_stable_across_repeated_renders(simple_dataset):
    first = render_layout(_bar_chart(simple_dataset)).doc.to_string()
    second = render_layout(_bar_chart(simple_dataset)).doc.to_string()
    third = render_layout(_bar_chart(simple_dataset)).doc.to_string()
    assert first == second == third
