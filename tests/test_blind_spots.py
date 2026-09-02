from __future__ import annotations

import json

from agent_charts.blind_spots import (
    collect_blind_spots,
    inspect_chart,
    inspect_dataset,
    write_blind_spots_json,
    write_blind_spots_md,
)
from agent_charts.model import ChartSpec, Column, DataSet
from agent_charts.normalize import resolve


def test_a_clean_report_has_no_blind_spots():
    assert collect_blind_spots()["has_blind_spots"] is False


def test_any_finding_flips_the_flag():
    assert collect_blind_spots(errors=["boom"])["has_blind_spots"] is True


def test_missing_cells_are_counted():
    dataset = DataSet(
        columns=[Column("a", "category"), Column("b", "number")],
        rows=[{"a": "x", "b": 1.0}, {"a": None, "b": 2.0}],
        metadata={"origin": "t"},
    )
    report = inspect_dataset(dataset)
    assert any("1 of 2 rows have no value" in m for m in report["missing_values"])


def test_a_mostly_numeric_category_column_is_reported_as_dirty():
    dataset = DataSet(
        columns=[Column("v", "category")],
        rows=[{"v": "1"}, {"v": "2"}, {"v": "3"}, {"v": "4"}, {"v": "n/a"}],
        metadata={"origin": "t"},
    )
    assert inspect_dataset(dataset)["unparsed_values"]


def test_an_empty_source_is_reported():
    dataset = DataSet(columns=[], rows=[], metadata={"origin": "empty.csv"})
    assert inspect_dataset(dataset)["empty_sources"]


def test_folded_series_name_what_was_summed_away():
    rows = [{"k": f"s{i}", "x": "a", "v": float(20 - i)} for i in range(12)]
    dataset = DataSet(
        columns=[Column("k", "category"), Column("x", "category"), Column("v", "number")],
        rows=rows,
    )
    chart = resolve(dataset, ChartSpec(form="column", x="x", y="v", series="k"))
    folded = inspect_chart(chart)["folded_series"]
    assert folded and "were summed into 'Other'" in folded[0]


def test_gaps_are_reported_as_gaps_not_zeros():
    dataset = DataSet(
        columns=[Column("x", "category"), Column("v", "number")],
        rows=[{"x": "a", "v": None}, {"x": "b", "v": 1.0}],
    )
    chart = resolve(dataset, ChartSpec(form="column", x="x", y="v"))
    warnings = inspect_chart(chart)["warnings"]
    assert any("drawn as gaps, not zeros" in w for w in warnings)


def test_converging_lines_are_flagged():
    rows = [
        {"t": f"t{i}", "k": f"s{j}", "v": float(i + j)} for i in range(3) for j in range(6)
    ]
    dataset = DataSet(
        columns=[Column("t", "category"), Column("k", "category"), Column("v", "number")],
        rows=rows,
    )
    chart = resolve(dataset, ChartSpec(form="line", x="t", y="v", series="k"))
    assert any("small multiples" in w for w in inspect_chart(chart)["warnings"])


def test_measures_of_different_scale_on_one_axis_are_flagged():
    dataset = DataSet(
        columns=[Column("t", "time"), Column("small", "number"), Column("big", "number")],
        rows=[
            {"t": "2026-09-01", "small": 5.0, "big": 900000.0},
            {"t": "2026-09-02", "small": 6.0, "big": 950000.0},
        ],
    )
    chart = resolve(dataset, ChartSpec(form="line", x="t", y="small,big"))
    warnings = inspect_chart(chart)["warnings"]
    assert any("do not add a second y axis" in w for w in warnings)


def test_reports_write_both_formats(tmp_path):
    report = collect_blind_spots(errors=["a failure"], warnings=["a warning"])
    json_path = write_blind_spots_json(report, tmp_path / "r.json")
    md_path = write_blind_spots_md(report, tmp_path / "r.md")

    assert json.loads(json_path.read_text())["errors"] == ["a failure"]
    text = md_path.read_text()
    assert "# Chart Blind Spots Report" in text
    assert "- a failure" in text
    # Empty sections say so rather than being omitted.
    assert "- None" in text
