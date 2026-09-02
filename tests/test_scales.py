from __future__ import annotations

import pytest

from agent_charts.scales import (
    BandScale,
    LinearScale,
    fmt_coord,
    nice_number,
    nice_ticks,
    round_coord,
    zero_anchored,
)


def test_linear_scale_maps_domain_to_range():
    scale = LinearScale(0, 100, 0, 200)
    assert scale(0) == 0
    assert scale(50) == 100
    assert scale(100) == 200


def test_linear_scale_survives_a_zero_width_domain():
    scale = LinearScale(5, 5, 10, 90)
    assert scale(5) == 10


def test_band_scale_leaves_padding_as_air():
    band = BandScale(["a", "b", "c"], 0, 300, padding=0.2)
    assert band.step == 100
    assert band.band_width == 80
    assert band.center("b") == 150


def test_band_scale_falls_back_for_an_unknown_category():
    band = BandScale(["a", "b"], 0, 200)
    assert band.start("missing") == band.start("a")


@pytest.mark.parametrize(
    "lo,hi,expected_max",
    [(0, 620, 700), (0, 121, 140), (0, 7, 7), (-40, 90, 100)],
)
def test_nice_ticks_stay_close_to_the_data(lo, hi, expected_max):
    _, domain_max, ticks = nice_ticks(lo, hi)
    assert domain_max == expected_max
    assert ticks[-1] == expected_max
    assert ticks[0] <= lo


def test_nice_ticks_produce_clean_round_numbers():
    _, _, ticks = nice_ticks(0, 1_250_000)
    assert all(t % 100_000 == 0 for t in ticks)


def test_nice_ticks_do_not_leave_float_artifacts():
    domain_min, domain_max, ticks = nice_ticks(0, 0.35)
    assert domain_max == 0.35
    assert all(t == round(t, 10) for t in ticks)


def test_nice_ticks_handle_a_flat_series():
    lo, hi, ticks = nice_ticks(0, 0)
    assert (lo, hi) == (0.0, 1.0)
    assert len(ticks) >= 2


def test_nice_number_snaps_to_1_2_5_10():
    assert nice_number(1.3, True) == 1
    assert nice_number(2.4, True) == 2
    assert nice_number(6.0, True) == 5
    assert nice_number(9.0, True) == 10


def test_zero_anchored_always_includes_the_baseline():
    assert zero_anchored(10, 50) == (0, 50)
    assert zero_anchored(-20, -5) == (-20, 0)


def test_coordinates_round_deterministically():
    assert round_coord(1.23456) == 1.23
    # -0.0 would format differently and churn snapshots.
    assert round_coord(-0.001) == 0.0
    assert fmt_coord(3.0) == "3"
    assert fmt_coord(3.5) == "3.5"
