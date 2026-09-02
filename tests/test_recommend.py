from __future__ import annotations

from agent_charts.model import Column, DataSet
from agent_charts.recommend import format_advice, recommend


def _dataset(rows, columns):
    return DataSet(columns=columns, rows=rows, metadata={})


def test_a_single_row_is_a_stat_tile_not_a_one_bar_chart():
    dataset = _dataset([{"n": 42.0}], [Column("n", "number")])
    advice = recommend(dataset)
    assert advice.best.form == "stat"
    assert advice.best.confidence == "high"


def test_a_ratio_against_a_limit_offers_a_meter():
    dataset = _dataset(
        [{"used_percent": 82.0, "quota": 100.0}],
        [Column("used_percent", "number"), Column("quota", "number")],
    )
    forms = [r.form for r in recommend(dataset).recommendations]
    assert "meter" in forms


def test_a_time_column_with_one_measure_recommends_a_single_series_form(time_dataset):
    dataset = DataSet(
        columns=[Column("minute", "time"), Column("p50_ms", "number")],
        rows=[{"minute": f"2026-09-02T09:0{i}", "p50_ms": float(i)} for i in range(5)],
    )
    assert recommend(dataset).best.form == "area"


def test_several_measures_over_time_recommend_one_shared_axis(time_dataset):
    best = recommend(time_dataset).best
    assert best.form == "line"
    assert best.spec_hints["y"] == "p50_ms,p99_ms"
    # Never a second y axis.
    assert "second y axis" in best.reason


def test_measures_of_wildly_different_scale_are_flagged():
    dataset = DataSet(
        columns=[
            Column("t", "time"), Column("users", "number"), Column("sessions", "number"),
        ],
        rows=[
            {"t": f"2026-09-0{i+1}", "users": 100.0 * (i + 1), "sessions": 90000.0 * (i + 1)}
            for i in range(4)
        ],
    )
    cautions = " ".join(recommend(dataset).cautions)
    assert "index each to a common base" in cautions


def test_negative_values_recommend_a_diverging_form():
    dataset = _dataset(
        [{"team": "a", "net": 5.0}, {"team": "b", "net": -3.0}],
        [Column("team", "category"), Column("net", "number")],
    )
    assert recommend(dataset).best.form == "diverging-bar"


def test_long_category_names_go_horizontal():
    dataset = _dataset(
        [{"name": f"a-very-long-service-name-{i}", "v": float(i)} for i in range(6)],
        [Column("name", "category"), Column("v", "number")],
    )
    forms = [r.form for r in recommend(dataset).recommendations]
    assert "bar" in forms and "column" not in forms


def test_recommendations_are_ranked_by_confidence():
    dataset = _dataset(
        [
            {"svc": "a", "env": "x", "v": 1.0}, {"svc": "a", "env": "y", "v": 2.0},
            {"svc": "b", "env": "x", "v": 3.0}, {"svc": "b", "env": "y", "v": 4.0},
        ],
        [Column("svc", "category"), Column("env", "category"), Column("v", "number")],
    )
    order = [r.confidence for r in recommend(dataset).recommendations]
    rank = {"high": 0, "medium": 1, "low": 2}
    assert order == sorted(order, key=lambda c: rank[c])


def test_too_many_color_classes_are_flagged_as_a_table_case():
    # The widest category becomes the axis, so the narrower one drives color.
    # Here that is still 12 classes, which is past the point they blur.
    rows = [
        {"day": f"day-{d:02d}", "k": f"class-{i}", "v": float(i)}
        for d in range(20)
        for i in range(12)
    ]
    dataset = _dataset(
        rows, [Column("day", "category"), Column("k", "category"), Column("v", "number")]
    )
    advice = recommend(dataset)
    assert any(r.spec_hints.get("series") == "k" for r in advice.recommendations)
    assert any("would drive color" in c for c in advice.cautions)


def test_a_long_category_axis_is_not_flagged_as_a_color_problem():
    # Many bars is a long chart, not too many color classes.
    dataset = _dataset(
        [{"svc": f"service-{i}", "v": float(i)} for i in range(12)],
        [Column("svc", "category"), Column("v", "number")],
    )
    assert not any("would drive color" in c for c in recommend(dataset).cautions)


def test_no_numeric_column_is_reported_rather_than_guessed():
    dataset = _dataset([{"a": "x"}], [Column("a", "category")])
    advice = recommend(dataset)
    assert advice.recommendations == []
    assert any("No numeric column" in c for c in advice.cautions)


def test_an_empty_dataset_recommends_nothing():
    assert recommend(_dataset([], [])).recommendations == []


def test_a_row_index_column_is_not_treated_as_a_measure():
    dataset = _dataset(
        [{"index": float(i), "value": float(i * 2)} for i in range(10)],
        [Column("index", "number"), Column("value", "number")],
    )
    assert "scatter" not in [r.form for r in recommend(dataset).recommendations]


def test_advice_renders_a_runnable_command():
    dataset = _dataset(
        [{"svc": "a", "v": 1.0}, {"svc": "b", "v": 2.0}],
        [Column("svc", "category"), Column("v", "number")],
    )
    text = format_advice(recommend(dataset))
    assert "chart-gen chart" in text


def test_advice_serializes_to_json():
    dataset = _dataset([{"n": 1.0}], [Column("n", "number")])
    payload = recommend(dataset).to_dict()
    assert payload["recommended"] == "stat"
    assert payload["recommendations"][0]["reason"]


def test_a_session_record_plots_its_subject_not_its_timestamp():
    # `chart-gen record` stamps every row with 'at'. Reading that as a trend
    # gives a line chart with one point per series, which says nothing.
    dataset = _dataset(
        [
            {"at": "2026-09-02T17:14:15", "step": "compile", "seconds": 42.0},
            {"at": "2026-09-02T17:14:15", "step": "test", "seconds": 118.0},
            {"at": "2026-09-02T17:14:16", "step": "package", "seconds": 17.0},
            {"at": "2026-09-02T17:14:16", "step": "upload", "seconds": 63.0},
        ],
        [Column("at", "time"), Column("step", "category"), Column("seconds", "number")],
    )
    best = recommend(dataset).best
    assert best.form in ("column", "bar")
    assert best.spec_hints["x"] == "step"


def test_a_split_leaving_one_point_per_series_is_not_recommended():
    dataset = _dataset(
        [
            {"t": "2026-09-01", "k": "a", "v": 1.0},
            {"t": "2026-09-02", "k": "b", "v": 2.0},
            {"t": "2026-09-03", "k": "c", "v": 3.0},
            {"t": "2026-09-04", "k": "d", "v": 4.0},
        ],
        [Column("t", "time"), Column("k", "category"), Column("v", "number")],
    )
    for rec in recommend(dataset).recommendations:
        assert rec.spec_hints.get("series") != "k"


def test_a_genuine_time_series_is_still_read_as_a_trend():
    dataset = _dataset(
        [
            {"t": f"2026-09-0{d}", "region": region, "v": float(d)}
            for d in range(1, 5)
            for region in ("eu", "us")
        ],
        [Column("t", "time"), Column("region", "category"), Column("v", "number")],
    )
    best = recommend(dataset).best
    assert best.form == "line"
    assert best.spec_hints["series"] == "region"
