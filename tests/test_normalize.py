from __future__ import annotations

import pytest

from agent_charts.model import ChartSpec, Column, DataSet
from agent_charts.normalize import NormalizeError, OTHER_LABEL, resolve
from agent_charts.theme import ALL_PAIRS_CAP, MAX_SLOTS


def _dataset(rows, columns):
    return DataSet(columns=columns, rows=rows, metadata={})


def test_series_split_produces_one_series_per_value(simple_dataset, bar_spec):
    chart = resolve(simple_dataset, bar_spec)
    assert [s.label for s in chart.series] == ["staging", "production"]
    assert chart.x_order == ["api", "auth"]


def test_slots_follow_first_appearance_not_rank(simple_dataset, bar_spec):
    chart = resolve(simple_dataset, bar_spec)
    # 'production' has larger values but 'staging' appeared first, so staging
    # keeps slot 0. Color follows the entity, never its rank.
    assert chart.series[0].label == "staging"
    assert chart.series[0].slot == 0


def test_sorting_a_single_series_does_not_change_its_slot(simple_dataset):
    spec = ChartSpec(form="bar", x="service", y="duration_seconds", sort="desc")
    chart = resolve(simple_dataset, spec)
    assert chart.series[0].slot == 0


def test_sort_desc_reorders_the_x_axis(simple_dataset):
    spec = ChartSpec(form="bar", x="service", y="duration_seconds", sort="desc")
    chart = resolve(simple_dataset, spec)
    values = [p.y for p in chart.series[0].points]
    assert values == sorted(values, reverse=True)


def test_every_series_is_aligned_to_the_same_x_slots():
    dataset = _dataset(
        [
            {"x": "a", "k": "one", "v": 1.0},
            {"x": "b", "k": "one", "v": 2.0},
            {"x": "a", "k": "two", "v": 3.0},
        ],
        [Column("x", "category"), Column("k", "category"), Column("v", "number")],
    )
    chart = resolve(dataset, ChartSpec(form="column", x="x", y="v", series="k"))
    assert all(len(s.points) == len(chart.x_order) for s in chart.series)
    # The slot 'two' never filled stays a gap, not a zero.
    assert chart.series[1].points[1].y is None


def test_repeated_x_within_a_series_sums():
    dataset = _dataset(
        [{"x": "a", "v": 1.0}, {"x": "a", "v": 2.0}],
        [Column("x", "category"), Column("v", "number")],
    )
    chart = resolve(dataset, ChartSpec(form="column", x="x", y="v"))
    assert chart.series[0].points[0].y == 3.0


def test_top_n_folds_the_tail_into_other():
    rows = [{"k": f"s{i}", "x": "a", "v": float(10 - i)} for i in range(6)]
    dataset = _dataset(
        rows, [Column("k", "category"), Column("x", "category"), Column("v", "number")]
    )
    chart = resolve(dataset, ChartSpec(form="column", x="x", y="v", series="k", top_n=3))
    assert len(chart.series) == 4
    assert chart.series[-1].label == OTHER_LABEL
    # 'Other' is the sum of what it replaced, not a dropped remainder.
    assert chart.series[-1].points[0].y == 7.0 + 6.0 + 5.0


def test_series_past_the_cap_fold_rather_than_generating_a_ninth_hue():
    rows = [{"k": f"s{i}", "x": "a", "v": float(20 - i)} for i in range(12)]
    dataset = _dataset(
        rows, [Column("k", "category"), Column("x", "category"), Column("v", "number")]
    )
    chart = resolve(dataset, ChartSpec(form="column", x="x", y="v", series="k"))
    assert len(chart.series) == MAX_SLOTS
    assert chart.series[-1].label == OTHER_LABEL
    assert max(s.slot for s in chart.series) < MAX_SLOTS


def test_scatter_caps_at_three_hues_for_the_all_pairs_floors():
    rows = [{"k": f"s{i}", "x": 1.0, "v": float(20 - i)} for i in range(6)]
    dataset = _dataset(
        rows, [Column("k", "category"), Column("x", "number"), Column("v", "number")]
    )
    chart = resolve(dataset, ChartSpec(form="scatter", x="x", y="v", series="k"))
    assert len(chart.series) == ALL_PAIRS_CAP


def test_multiple_measures_become_multiple_series(time_dataset):
    spec = ChartSpec(form="line", x="minute", y="p50_ms,p99_ms")
    chart = resolve(time_dataset, spec)
    assert [s.label for s in chart.series] == ["p50_ms", "p99_ms"]
    assert chart.metadata["layout"] == "wide"


def test_time_x_values_are_sorted_chronologically():
    dataset = _dataset(
        [
            {"t": "2026-09-02T09:10", "v": 3.0},
            {"t": "2026-09-02T09:00", "v": 1.0},
            {"t": "2026-09-02T09:05", "v": 2.0},
        ],
        [Column("t", "time"), Column("v", "number")],
    )
    chart = resolve(dataset, ChartSpec(form="line", x="t", y="v"))
    assert chart.x_order == [
        "2026-09-02T09:00", "2026-09-02T09:05", "2026-09-02T09:10",
    ]


def test_category_x_values_keep_their_source_order():
    dataset = _dataset(
        [{"x": "zulu", "v": 1.0}, {"x": "alpha", "v": 2.0}],
        [Column("x", "category"), Column("v", "number")],
    )
    chart = resolve(dataset, ChartSpec(form="column", x="x", y="v"))
    assert chart.x_order == ["zulu", "alpha"]


def test_axes_are_inferred_when_the_spec_leaves_them_out(simple_dataset):
    chart = resolve(simple_dataset, ChartSpec(form="column"))
    assert chart.spec.x == "service"
    assert chart.spec.y == "duration_seconds"


def test_a_missing_column_names_what_is_available(simple_dataset):
    spec = ChartSpec(form="column", x="nope", y="duration_seconds")
    with pytest.raises(NormalizeError, match="Available: service"):
        resolve(simple_dataset, spec)


def test_unparseable_values_become_gaps_not_zeros():
    dataset = _dataset(
        [{"x": "a", "v": "n/a"}, {"x": "b", "v": 2.0}],
        [Column("x", "category"), Column("v", "number")],
    )
    chart = resolve(dataset, ChartSpec(form="column", x="x", y="v"))
    assert chart.series[0].points[0].y is None


def test_stat_resolves_one_point_per_row(simple_dataset):
    spec = ChartSpec(form="stat", x="service", y="duration_seconds")
    chart = resolve(simple_dataset, spec)
    assert len(chart.series) == 1
    assert len(chart.series[0].points) == 4


def test_stat_without_a_measure_is_an_error():
    dataset = _dataset([{"a": "x"}], [Column("a", "category")])
    with pytest.raises(NormalizeError, match="needs a numeric column"):
        resolve(dataset, ChartSpec(form="stat"))


def test_sorting_does_not_duplicate_an_x_slot(simple_dataset):
    # Alignment aggregates repeated x values; sorting before that would put
    # 'api' on the axis twice.
    spec = ChartSpec(form="bar", x="service", y="duration_seconds", sort="desc")
    chart = resolve(simple_dataset, spec)
    assert chart.x_order == ["api", "auth"]
    assert len(chart.x_order) == len(set(chart.x_order))
    assert [p.y for p in chart.series[0].points] == [100.0, 75.0]


def test_an_explicit_x_is_not_silently_split_into_series(simple_dataset):
    # The caller framed the chart; adding a split would change what it says.
    spec = ChartSpec(form="bar", x="service", y="duration_seconds")
    chart = resolve(simple_dataset, spec)
    assert len(chart.series) == 1


def test_a_split_is_inferred_when_no_axes_are_given(simple_dataset):
    chart = resolve(simple_dataset, ChartSpec(form="bar"))
    assert chart.spec.series == "environment"
