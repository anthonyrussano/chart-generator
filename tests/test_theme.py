"""The palette's guarantees, held in place by tests.

The hex values here are a validated set: the ordering is the colorblind-safety
mechanism, not a cosmetic choice. If a future change reorders or re-steps them,
these tests fail and the validator must be re-run before the change lands.
"""

from __future__ import annotations

import pytest

from agent_charts.theme import (
    ALL_PAIRS_CAP,
    CATEGORICAL_DARK,
    CATEGORICAL_LIGHT,
    CHROME_DARK,
    CHROME_LIGHT,
    MAX_SLOTS,
    SEQUENTIAL_LIGHT,
    STATUS,
    resolve_theme,
    sequential_step,
    series_cap,
)


def test_both_modes_have_the_same_number_of_slots():
    assert len(CATEGORICAL_LIGHT) == len(CATEGORICAL_DARK) == MAX_SLOTS == 8


def test_the_validated_slot_order_is_pinned():
    # Re-run scripts/validate_palette.js before changing any of these.
    assert CATEGORICAL_LIGHT[:3] == ("#2a78d6", "#eb6834", "#1baf7a")


def test_every_slot_is_a_distinct_hex():
    assert len(set(CATEGORICAL_LIGHT)) == MAX_SLOTS
    assert len(set(CATEGORICAL_DARK)) == MAX_SLOTS


@pytest.mark.parametrize("palette", [CATEGORICAL_LIGHT, CATEGORICAL_DARK, SEQUENTIAL_LIGHT])
def test_palettes_are_well_formed_hex(palette):
    for color in palette:
        assert color.startswith("#") and len(color) == 7
        int(color[1:], 16)


def test_status_colors_are_never_categorical_slots():
    # A status color must never impersonate a series.
    assert not set(STATUS.values()) & set(CATEGORICAL_LIGHT)


def test_status_roles_are_the_reserved_four():
    assert set(STATUS) == {"good", "warning", "serious", "critical"}


def test_slots_wrap_rather_than_generating_a_new_hue():
    theme = resolve_theme("light")
    assert theme.series_color(MAX_SLOTS) == theme.series_color(0)


def test_scatter_caps_at_three_for_the_all_pairs_floors():
    assert series_cap("scatter") == ALL_PAIRS_CAP == 3
    assert series_cap("bar") == MAX_SLOTS


def test_the_sequential_ramp_runs_light_to_dark():
    def luminance(hex_color: str) -> int:
        return sum(int(hex_color[i : i + 2], 16) for i in (1, 3, 5))

    values = [luminance(c) for c in SEQUENTIAL_LIGHT]
    assert values == sorted(values, reverse=True)


@pytest.mark.parametrize("fraction,expected", [(0.0, SEQUENTIAL_LIGHT[0]), (1.0, SEQUENTIAL_LIGHT[-1])])
def test_sequential_step_spans_the_whole_ramp(fraction, expected):
    assert sequential_step(fraction) == expected


def test_sequential_step_clamps_out_of_range_values():
    assert sequential_step(-5) == SEQUENTIAL_LIGHT[0]
    assert sequential_step(99) == SEQUENTIAL_LIGHT[-1]


def test_auto_lays_out_as_light_so_geometry_never_depends_on_the_mode():
    assert resolve_theme("auto").mode == "light"


def test_an_unknown_theme_lists_the_valid_ones():
    with pytest.raises(ValueError, match="Choose one of"):
        resolve_theme("solarized")


def test_both_modes_define_the_same_chrome_roles():
    assert set(CHROME_LIGHT) == set(CHROME_DARK)


def test_the_two_surfaces_differ():
    assert CHROME_LIGHT["surface"] != CHROME_DARK["surface"]
