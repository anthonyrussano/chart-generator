"""A small, deterministic SVG writer.

Two properties matter more than features here:

  * **Deterministic.** No generated ids, no dictionary iteration order, every
    coordinate rounded. The same spec and data produce byte-identical SVG, so a
    chart can be committed and reviewed in a diff like any other artifact.

  * **Theme-aware in one file.** Marks carry class names, never inline colors.
    The stylesheet's base rules are the light palette; a `prefers-color-scheme`
    block and a `[data-theme="dark"]` block carry the dark steps. Rasterizers
    that ignore media queries render the light mode correctly, which is exactly
    what PNG export wants.

Text width is estimated, not measured - there is no font engine here. The
estimate is deliberately generous so a label that *might* collide is moved or
dropped rather than clipped.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..scales import fmt_coord
from ..theme import (
    CATEGORICAL_DARK,
    CATEGORICAL_LIGHT,
    CHROME_DARK,
    CHROME_LIGHT,
    DIVERGING_MID,
    DIVERGING_NEGATIVE,
    DIVERGING_POSITIVE,
    FONT_STACK,
    MAX_SLOTS,
)

# System sans averages a bit under 0.6em per character at these sizes. Rounding
# up keeps the fit checks conservative.
_CHAR_WIDTH_RATIO = 0.58


def estimate_text_width(text: str, font_size: float, bold: bool = False) -> float:
    ratio = _CHAR_WIDTH_RATIO * (1.06 if bold else 1.0)
    return len(text) * font_size * ratio


def escape(text: Any) -> str:
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _attrs(pairs: list[tuple[str, Any]]) -> str:
    parts = []
    for key, value in pairs:
        if value is None:
            continue
        if isinstance(value, float):
            value = fmt_coord(value)
        parts.append(f'{key}="{escape(value)}"')
    return " ".join(parts)


def build_stylesheet() -> str:
    """The full class table: light as the base, dark under both overrides."""

    def series_rules(palette: tuple[str, ...], indent: str) -> str:
        lines = []
        for index in range(MAX_SLOTS):
            color = palette[index]
            lines.append(f"{indent}.fill-s{index} {{ fill: {color}; }}")
            lines.append(f"{indent}.stroke-s{index} {{ stroke: {color}; }}")
            lines.append(f"{indent}.area-s{index} {{ fill: {color}; fill-opacity: 0.1; }}")
        # The diverging pair is its own slot pair, not two categorical hues:
        # the poles must read as opposite and the midpoint as "nothing".
        dark = palette is CATEGORICAL_DARK
        lines.append(f"{indent}.fill-pos {{ fill: {DIVERGING_POSITIVE[1 if dark else 0]}; }}")
        lines.append(f"{indent}.fill-neg {{ fill: {DIVERGING_NEGATIVE[1 if dark else 0]}; }}")
        lines.append(f"{indent}.fill-mid {{ fill: {DIVERGING_MID[1 if dark else 0]}; }}")
        return "\n".join(lines)

    def chrome_rules(chrome: dict[str, str], indent: str) -> str:
        return "\n".join(
            [
                f"{indent}.surface {{ fill: {chrome['surface']}; }}",
                f"{indent}.ring {{ stroke: {chrome['surface']}; }}",
                f"{indent}.grid {{ stroke: {chrome['grid']}; }}",
                f"{indent}.axis {{ stroke: {chrome['axis']}; }}",
                f"{indent}.ink {{ fill: {chrome['ink']}; }}",
                f"{indent}.ink2 {{ fill: {chrome['ink-2']}; }}",
                f"{indent}.muted {{ fill: {chrome['muted']}; }}",
                f"{indent}.deemph-fill {{ fill: {chrome['deemphasis']}; }}",
                f"{indent}.deemph-stroke {{ stroke: {chrome['deemphasis']}; }}",
                f"{indent}.positive {{ fill: {chrome['positive']}; }}",
            ]
        )

    base = "\n".join(
        [
            f"  text {{ font-family: {FONT_STACK}; }}",
            "  .title { font-size: 15px; font-weight: 600; }",
            "  .subtitle { font-size: 12px; }",
            "  .axis-label { font-size: 11px; }",
            "  .tick { font-size: 11px; font-variant-numeric: tabular-nums; }",
            "  .value-label { font-size: 11px; font-weight: 500; }",
            "  .legend-label { font-size: 11px; }",
            "  .hero { font-size: 34px; font-weight: 600; }",
            "  .stat-label { font-size: 11px; }",
            "  .grid, .axis { stroke-width: 1; shape-rendering: crispEdges; }",
            "  .line-mark { fill: none; stroke-width: 2; stroke-linejoin: round;"
            " stroke-linecap: round; }",
            "  .ring { stroke-width: 2; }",
            chrome_rules(CHROME_LIGHT, "  "),
            series_rules(CATEGORICAL_LIGHT, "  "),
        ]
    )

    dark_body = "\n".join(
        [chrome_rules(CHROME_DARK, "    "), series_rules(CATEGORICAL_DARK, "    ")]
    )

    return "\n".join(
        [
            base,
            "  @media (prefers-color-scheme: dark) {",
            "    :root:not([data-theme=\"light\"]) {",
            dark_body,
            "    }",
            "  }",
            "  :root[data-theme=\"dark\"] {",
            dark_body,
            "  }",
        ]
    )


def build_dark_only_stylesheet() -> str:
    """Baked dark mode - used when a raster export must be dark."""
    lines = [
        f"  text {{ font-family: {FONT_STACK}; }}",
        "  .title { font-size: 15px; font-weight: 600; }",
        "  .subtitle { font-size: 12px; }",
        "  .axis-label { font-size: 11px; }",
        "  .tick { font-size: 11px; font-variant-numeric: tabular-nums; }",
        "  .value-label { font-size: 11px; font-weight: 500; }",
        "  .legend-label { font-size: 11px; }",
        "  .hero { font-size: 34px; font-weight: 600; }",
        "  .stat-label { font-size: 11px; }",
        "  .grid, .axis { stroke-width: 1; shape-rendering: crispEdges; }",
        "  .line-mark { fill: none; stroke-width: 2; stroke-linejoin: round;"
        " stroke-linecap: round; }",
        "  .ring { stroke-width: 2; }",
    ]
    chrome = CHROME_DARK
    lines += [
        f"  .surface {{ fill: {chrome['surface']}; }}",
        f"  .ring {{ stroke: {chrome['surface']}; }}",
        f"  .grid {{ stroke: {chrome['grid']}; }}",
        f"  .axis {{ stroke: {chrome['axis']}; }}",
        f"  .ink {{ fill: {chrome['ink']}; }}",
        f"  .ink2 {{ fill: {chrome['ink-2']}; }}",
        f"  .muted {{ fill: {chrome['muted']}; }}",
        f"  .deemph-fill {{ fill: {chrome['deemphasis']}; }}",
        f"  .deemph-stroke {{ stroke: {chrome['deemphasis']}; }}",
        f"  .positive {{ fill: {chrome['positive']}; }}",
    ]
    for index in range(MAX_SLOTS):
        color = CATEGORICAL_DARK[index]
        lines.append(f"  .fill-s{index} {{ fill: {color}; }}")
        lines.append(f"  .stroke-s{index} {{ stroke: {color}; }}")
        lines.append(f"  .area-s{index} {{ fill: {color}; fill-opacity: 0.1; }}")
    lines.append(f"  .fill-pos {{ fill: {DIVERGING_POSITIVE[1]}; }}")
    lines.append(f"  .fill-neg {{ fill: {DIVERGING_NEGATIVE[1]}; }}")
    lines.append(f"  .fill-mid {{ fill: {DIVERGING_MID[1]}; }}")
    return "\n".join(lines)


@dataclass(slots=True)
class SvgDocument:
    width: int
    height: int
    title: str = ""
    description: str = ""
    theme: str = "auto"
    body: list[str] = field(default_factory=list)

    # --- primitives -------------------------------------------------------

    def _element(self, tag: str, pairs: list[tuple[str, Any]], title: str | None) -> None:
        # A tooltip's <title> must be a CHILD of the mark, never a sibling -
        # as a sibling it renders nothing and no hover text appears.
        if title:
            self.body.append(
                f"<{tag} {_attrs(pairs)}><title>{escape(title)}</title></{tag}>"
            )
        else:
            self.body.append(f"<{tag} {_attrs(pairs)}/>")

    def rect(
        self,
        x: float,
        y: float,
        width: float,
        height: float,
        css: str,
        *,
        rx: float | None = None,
        extra: list[tuple[str, Any]] | None = None,
        title: str | None = None,
    ) -> None:
        if width <= 0 or height <= 0:
            return
        pairs: list[tuple[str, Any]] = [
            ("x", x), ("y", y), ("width", width), ("height", height),
        ]
        if rx:
            pairs.append(("rx", rx))
        pairs.append(("class", css))
        if extra:
            pairs.extend(extra)
        self._element("rect", pairs, title)

    def path(
        self,
        d: str,
        css: str,
        extra: list[tuple[str, Any]] | None = None,
        title: str | None = None,
    ) -> None:
        pairs: list[tuple[str, Any]] = [("d", d), ("class", css)]
        if extra:
            pairs.extend(extra)
        self._element("path", pairs, title)

    def line(self, x1: float, y1: float, x2: float, y2: float, css: str) -> None:
        self.body.append(
            f"<line {_attrs([('x1', x1), ('y1', y1), ('x2', x2), ('y2', y2), ('class', css)])}/>"
        )

    def circle(
        self,
        cx: float,
        cy: float,
        r: float,
        css: str,
        extra: list[tuple[str, Any]] | None = None,
        title: str | None = None,
    ) -> None:
        pairs: list[tuple[str, Any]] = [("cx", cx), ("cy", cy), ("r", r), ("class", css)]
        if extra:
            pairs.extend(extra)
        self._element("circle", pairs, title)

    def text(
        self,
        x: float,
        y: float,
        content: str,
        css: str,
        *,
        anchor: str = "start",
        baseline: str | None = None,
        title: str | None = None,
        fill: str | None = None,
    ) -> None:
        if content == "":
            return
        pairs: list[tuple[str, Any]] = [("x", x), ("y", y), ("class", css)]
        if fill:
            # Only for text set inside a colored fill, where ink must be
            # picked by the fill's luminance rather than a theme token.
            pairs.append(("fill", fill))
        if anchor != "start":
            pairs.append(("text-anchor", anchor))
        if baseline:
            pairs.append(("dominant-baseline", baseline))
        inner = escape(content)
        if title:
            inner = f"<title>{escape(title)}</title>{inner}"
        self.body.append(f"<text {_attrs(pairs)}>{inner}</text>")

    def group(self, content: list[str], css: str | None = None) -> None:
        opening = f'<g class="{escape(css)}">' if css else "<g>"
        self.body.append(opening)
        self.body.extend(content)
        self.body.append("</g>")

    def raw(self, markup: str) -> None:
        self.body.append(markup)

    # --- output -----------------------------------------------------------

    def to_string(self, standalone: bool = True) -> str:
        stylesheet = (
            build_dark_only_stylesheet() if self.theme == "dark" else build_stylesheet()
        )
        header = [
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{self.width}" '
            f'height="{self.height}" viewBox="0 0 {self.width} {self.height}" '
            'role="img" font-size="12">',
        ]
        if self.title:
            header.append(f"<title>{escape(self.title)}</title>")
        if self.description:
            header.append(f"<desc>{escape(self.description)}</desc>")
        header.append(f"<style>\n{stylesheet}\n</style>")

        lines = header + self.body + ["</svg>"]
        text = "\n".join(lines) + "\n"
        if standalone:
            return '<?xml version="1.0" encoding="UTF-8"?>\n' + text
        return text
