"""Palette and chrome tokens.

The default palette is the validated reference instance: eight categorical hues
whose *ordering* is the colorblind-safety mechanism, plus a one-hue sequential
ramp, a diverging pair, and a reserved status palette.

Validated with the data-viz palette validator (OKLab dE x100):

    light, adjacent pairs: CVD 9.1 / normal-vision 19.6  -> PASS
    dark,  adjacent pairs: CVD 8.4 / normal-vision 19.3  -> PASS
    light, all pairs (first 3): CVD 9.2 / normal 24.0    -> PASS
    dark,  all pairs (first 3): CVD 9.4 / normal 20.9    -> PASS

Three light-mode hues sit below 3:1 against the light surface, so the relief
rule applies: every chart ships direct labels or the Markdown table view.

To retheme, replace CATEGORICAL/SEQUENTIAL/CHROME below and re-run the
validator against your own surfaces. Nothing else in this package changes.
"""

from __future__ import annotations

from dataclasses import dataclass

# Categorical slots, in fixed order. Never cycle past the last slot; fold the
# tail into "Other" or facet instead.
CATEGORICAL_LIGHT = (
    "#2a78d6",  # 1 blue
    "#eb6834",  # 2 orange
    "#1baf7a",  # 3 aqua
    "#eda100",  # 4 yellow
    "#e87ba4",  # 5 magenta
    "#008300",  # 6 green
    "#4a3aa7",  # 7 violet
    "#e34948",  # 8 red
)
CATEGORICAL_DARK = (
    "#3987e5",
    "#d95926",
    "#199e70",
    "#c98500",
    "#d55181",
    "#008300",
    "#9085e9",
    "#e66767",
)

MAX_SLOTS = len(CATEGORICAL_LIGHT)

# Forms that place every series against every other one (scatter, heatmap
# overlays, small multiples) cannot clear the all-pairs floors past three hues.
ALL_PAIRS_FORMS = frozenset({"scatter"})
ALL_PAIRS_CAP = 3

# Single-hue sequential ramp (blue), light -> dark.
SEQUENTIAL_LIGHT = (
    "#cde2fb", "#b7d3f6", "#9ec5f4", "#86b6ef", "#6da7ec",
    "#5598e7", "#3987e5", "#2a78d6", "#256abf", "#1c5cab",
    "#184f95", "#104281", "#0d366b",
)
# Dark mode reverses which end recedes into the surface.
SEQUENTIAL_DARK = tuple(reversed(SEQUENTIAL_LIGHT))

# Ordinal ramps must stay clear of the surface at both ends (>= 2:1).
ORDINAL_LIGHT = SEQUENTIAL_LIGHT[3:]
ORDINAL_DARK = tuple(reversed(SEQUENTIAL_LIGHT[:-2]))

# Diverging: warm/cool poles + a neutral gray midpoint that reads as "nothing".
DIVERGING_NEGATIVE = ("#2a78d6", "#3987e5")  # light, dark
DIVERGING_POSITIVE = ("#d03b3b", "#e66767")
DIVERGING_MID = ("#f0efec", "#383835")

# Status is reserved. Never reuse a status color for "series 4"; always ship it
# with an icon or a label so the color never carries the meaning alone.
STATUS = {
    "good": "#0ca30c",
    "warning": "#fab219",
    "serious": "#ec835a",
    "critical": "#d03b3b",
}

CHROME_LIGHT = {
    "surface": "#fcfcfb",
    "plane": "#f9f9f7",
    "ink": "#0b0b0b",
    "ink-2": "#52514e",
    "muted": "#898781",
    "grid": "#e1e0d9",
    "axis": "#c3c2b7",
    "deemphasis": "#c3c2b7",
    "positive": "#006300",
}
CHROME_DARK = {
    "surface": "#1a1a19",
    "plane": "#0d0d0d",
    "ink": "#ffffff",
    "ink-2": "#c3c2b7",
    "muted": "#898781",
    "grid": "#2c2c2a",
    "axis": "#383835",
    "deemphasis": "#52514e",
    "positive": "#0ca30c",
}

FONT_STACK = 'system-ui, -apple-system, "Segoe UI", sans-serif'

THEMES = ("auto", "light", "dark")


@dataclass(frozen=True, slots=True)
class Theme:
    """One resolved mode. `mode` is 'light' or 'dark'; 'auto' ships both."""

    mode: str

    @property
    def categorical(self) -> tuple[str, ...]:
        return CATEGORICAL_DARK if self.mode == "dark" else CATEGORICAL_LIGHT

    @property
    def sequential(self) -> tuple[str, ...]:
        return SEQUENTIAL_DARK if self.mode == "dark" else SEQUENTIAL_LIGHT

    @property
    def ordinal(self) -> tuple[str, ...]:
        return ORDINAL_DARK if self.mode == "dark" else ORDINAL_LIGHT

    @property
    def chrome(self) -> dict[str, str]:
        return dict(CHROME_DARK if self.mode == "dark" else CHROME_LIGHT)

    def series_color(self, slot: int) -> str:
        return self.categorical[slot % MAX_SLOTS]

    def diverging(self, positive: bool) -> str:
        idx = 1 if self.mode == "dark" else 0
        return (DIVERGING_POSITIVE if positive else DIVERGING_NEGATIVE)[idx]

    def diverging_mid(self) -> str:
        return DIVERGING_MID[1 if self.mode == "dark" else 0]

    def token(self, name: str) -> str:
        return self.chrome.get(name, CHROME_LIGHT.get(name, "#000000"))


LIGHT = Theme("light")
DARK = Theme("dark")


def resolve_theme(name: str) -> Theme:
    """Return the theme used to lay out marks. 'auto' lays out as light and
    carries dark as a CSS override, so geometry never depends on the mode."""
    if name not in THEMES:
        raise ValueError(f"Unknown theme '{name}'. Choose one of: {', '.join(THEMES)}.")
    return DARK if name == "dark" else LIGHT


def sequential_step(fraction: float, mode: str = "light") -> str:
    """Pick a ramp step for a 0..1 magnitude."""
    ramp = SEQUENTIAL_DARK if mode == "dark" else SEQUENTIAL_LIGHT
    if fraction != fraction:  # NaN
        fraction = 0.0
    fraction = min(1.0, max(0.0, fraction))
    return ramp[round(fraction * (len(ramp) - 1))]


def series_cap(form: str) -> int:
    """How many categorical hues this form may seat before folding to 'Other'."""
    return ALL_PAIRS_CAP if form in ALL_PAIRS_FORMS else MAX_SLOTS
