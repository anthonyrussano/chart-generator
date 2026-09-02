"""Scales and tick generation.

Every number that reaches the SVG is rounded to a fixed number of decimals, so
the same input always produces the same bytes. That is what makes chart output
reviewable in a diff.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

# SVG coordinates are rounded here. Two decimals is below a rendered pixel at
# any sane size and keeps golden files stable across platforms.
COORD_PRECISION = 2


def round_coord(value: float) -> float:
    result = round(float(value), COORD_PRECISION)
    # Normalize -0.0, which formats differently and would churn snapshots.
    return 0.0 if result == 0 else result


def fmt_coord(value: float) -> str:
    result = round_coord(value)
    if result == int(result):
        return str(int(result))
    return f"{result:g}"


@dataclass(slots=True)
class LinearScale:
    domain_min: float
    domain_max: float
    range_min: float
    range_max: float

    def __call__(self, value: float) -> float:
        span = self.domain_max - self.domain_min
        if span == 0:
            return self.range_min
        t = (value - self.domain_min) / span
        return self.range_min + t * (self.range_max - self.range_min)

    def clamp(self, value: float) -> float:
        lo, hi = sorted((self.range_min, self.range_max))
        return min(hi, max(lo, self(value)))


@dataclass(slots=True)
class BandScale:
    """Discrete slots along an axis, with padding expressed as a fraction."""

    categories: list
    range_min: float
    range_max: float
    padding: float = 0.2

    @property
    def step(self) -> float:
        n = max(1, len(self.categories))
        return (self.range_max - self.range_min) / n

    @property
    def band_width(self) -> float:
        return self.step * (1.0 - self.padding)

    def start(self, category) -> float:
        try:
            index = self.categories.index(category)
        except ValueError:
            index = 0
        return self.range_min + index * self.step + (self.step - self.band_width) / 2

    def center(self, category) -> float:
        return self.start(category) + self.band_width / 2


def nice_number(value: float, round_it: bool) -> float:
    """Snap a magnitude to 1, 2, 5, or 10 x a power of ten."""
    if value <= 0:
        return 0.0
    exponent = math.floor(math.log10(value))
    fraction = value / (10 ** exponent)
    if round_it:
        nice = 1.0 if fraction < 1.5 else 2.0 if fraction < 3 else 5.0 if fraction < 7 else 10.0
    else:
        nice = 1.0 if fraction <= 1 else 2.0 if fraction <= 2 else 5.0 if fraction <= 5 else 10.0
    return nice * (10 ** exponent)


def nice_ticks(lo: float, hi: float, count: int = 6) -> tuple[float, float, list[float]]:
    """Return (domain_min, domain_max, ticks) rounded to clean numbers.

    Ticks carry every value the chart does not directly label, so they are
    always clean: 0 / 1,000 / 2,000, never 0 / 1,137 / 2,274.
    """
    if lo == hi:
        if lo == 0:
            return 0.0, 1.0, [0.0, 0.5, 1.0]
        pad = abs(lo) * 0.5
        lo, hi = lo - pad, hi + pad
    if lo > hi:
        lo, hi = hi, lo

    count = max(2, count)
    # Derive the step from the actual range, not from a pre-inflated "nice"
    # span - inflating first pushes the top gridline well past the data and
    # leaves the plot looking empty (0-800 for a maximum of 620).
    step = nice_number((hi - lo) / (count - 1), True)
    if step == 0:
        return lo, hi, [lo, hi]

    # Round the bounds too: float division leaves artifacts like
    # 0.35000000000000003, which would churn otherwise-stable snapshots.
    nice_lo = round(math.floor(lo / step) * step, 10)
    nice_hi = round(math.ceil(hi / step) * step, 10)

    ticks: list[float] = []
    value = nice_lo
    # Guard against float drift accumulating past the top of the axis.
    while value <= nice_hi + step * 1e-9:
        ticks.append(round(value, 10))
        value += step
    return nice_lo, nice_hi, ticks


def zero_anchored(lo: float, hi: float) -> tuple[float, float]:
    """Bars grow from a single baseline, so their scale must include zero."""
    return (min(0.0, lo), max(0.0, hi))
