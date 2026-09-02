"""A self-contained HTML page: the chart, a hover layer, and a table view.

An HTML chart *is* interactive, so the page ships a tooltip rather than relying
on the SVG <title> fallback alone. It also ships the table view and a theme
toggle, so identity is never carried by color alone and dark mode is a
selection rather than an automatic inversion.
"""

from __future__ import annotations

from pathlib import Path

from ..charts.base import describe
from ..model import ChartData
from ..theme import CHROME_DARK, CHROME_LIGHT, FONT_STACK
from .chart_renderer import render_svg_fragment
from .markdown import _table
from .svg import escape

_PAGE_CSS = f"""
:root {{
  color-scheme: light;
  --page: {CHROME_LIGHT['plane']};
  --surface: {CHROME_LIGHT['surface']};
  --ink: {CHROME_LIGHT['ink']};
  --ink-2: {CHROME_LIGHT['ink-2']};
  --muted: {CHROME_LIGHT['muted']};
  --grid: {CHROME_LIGHT['grid']};
  --border: rgba(11,11,11,0.10);
}}
@media (prefers-color-scheme: dark) {{
  :root:not([data-theme="light"]) {{
    color-scheme: dark;
    --page: {CHROME_DARK['plane']};
    --surface: {CHROME_DARK['surface']};
    --ink: {CHROME_DARK['ink']};
    --ink-2: {CHROME_DARK['ink-2']};
    --muted: {CHROME_DARK['muted']};
    --grid: {CHROME_DARK['grid']};
    --border: rgba(255,255,255,0.10);
  }}
}}
:root[data-theme="dark"] {{
  color-scheme: dark;
  --page: {CHROME_DARK['plane']};
  --surface: {CHROME_DARK['surface']};
  --ink: {CHROME_DARK['ink']};
  --ink-2: {CHROME_DARK['ink-2']};
  --muted: {CHROME_DARK['muted']};
  --grid: {CHROME_DARK['grid']};
  --border: rgba(255,255,255,0.10);
}}
* {{ box-sizing: border-box; }}
body {{
  margin: 0; padding: 24px; background: var(--page); color: var(--ink);
  font-family: {FONT_STACK}; font-size: 14px; line-height: 1.5;
}}
.wrap {{ max-width: 960px; margin: 0 auto; }}
.toolbar {{
  display: flex; gap: 8px; align-items: center; justify-content: flex-end;
  margin-bottom: 12px;
}}
.toolbar button {{
  font: inherit; font-size: 12px; color: var(--ink-2); cursor: pointer;
  background: var(--surface); border: 1px solid var(--border);
  border-radius: 6px; padding: 5px 10px;
}}
.toolbar button:hover {{ color: var(--ink); }}
.card {{
  background: var(--surface); border: 1px solid var(--border);
  border-radius: 10px; padding: 8px; overflow-x: auto;
}}
.card svg {{ display: block; max-width: 100%; height: auto; }}
.tooltip {{
  position: fixed; pointer-events: none; opacity: 0; transition: opacity .08s;
  background: var(--surface); color: var(--ink); border: 1px solid var(--border);
  border-radius: 6px; padding: 6px 9px; font-size: 12px; white-space: nowrap;
  box-shadow: 0 2px 10px rgba(0,0,0,.12); z-index: 10;
}}
details {{ margin-top: 16px; }}
summary {{ cursor: pointer; color: var(--ink-2); font-size: 13px; }}
table {{
  border-collapse: collapse; margin-top: 12px; font-size: 13px;
  font-variant-numeric: tabular-nums; width: 100%;
}}
th, td {{ border-bottom: 1px solid var(--grid); padding: 6px 10px; text-align: right; }}
th:first-child, td:first-child {{ text-align: left; }}
th {{ color: var(--muted); font-weight: 500; }}
.alt {{ color: var(--muted); font-size: 12px; margin-top: 12px; }}
.notes {{ color: var(--muted); font-size: 12px; margin-top: 8px; }}
.notes li {{ margin: 2px 0; }}
"""

# Hover uses the <title> already on every mark, so the tooltip needs no
# duplicate data model and stays correct if the SVG changes.
_PAGE_JS = """
(function () {
  var tip = document.getElementById('tip');
  var root = document.documentElement;
  document.getElementById('theme').addEventListener('click', function () {
    var now = root.getAttribute('data-theme');
    var isDark = now ? now === 'dark'
      : window.matchMedia('(prefers-color-scheme: dark)').matches;
    root.setAttribute('data-theme', isDark ? 'light' : 'dark');
  });
  var svg = document.querySelector('.card svg');
  if (!svg) return;
  svg.querySelectorAll('title').forEach(function (node) {
    var mark = node.parentNode;
    var text = node.textContent;
    if (!mark || mark.tagName === 'svg') return;
    // Hit targets are the mark plus its surface ring, which is why small
    // dots stay hoverable.
    mark.style.cursor = 'default';
    mark.addEventListener('mousemove', function (event) {
      tip.textContent = text;
      tip.style.opacity = '1';
      tip.style.left = (event.clientX + 12) + 'px';
      tip.style.top = (event.clientY - 8) + 'px';
    });
    mark.addEventListener('mouseleave', function () { tip.style.opacity = '0'; });
  });
})();
"""


def render_html(
    chart: ChartData, output_path: Path, notes: list[str] | None = None
) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html_text(chart, notes), encoding="utf-8")
    return output_path


def html_text(chart: ChartData, notes: list[str] | None = None) -> str:
    fragment, layout = render_svg_fragment(chart)
    all_notes = list(notes or []) + list(layout.notes)
    title = chart.spec.title or f"{chart.spec.form} chart"

    rows = _table(chart)
    table_html = _markdown_table_to_html(rows)

    notes_html = ""
    if all_notes:
        items = "".join(f"<li>{escape(n)}</li>" for n in all_notes)
        notes_html = f'<ul class="notes">{items}</ul>'

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{escape(title)}</title>
<style>{_PAGE_CSS}</style>
</head>
<body>
<div class="wrap">
  <div class="toolbar"><button id="theme" type="button">Toggle theme</button></div>
  <div class="card">{fragment}</div>
  <p class="alt">{escape(describe(chart))}</p>
  {notes_html}
  <details open>
    <summary>Table view</summary>
    {table_html}
  </details>
</div>
<div class="tooltip" id="tip"></div>
<script>{_PAGE_JS}</script>
</body>
</html>
"""


def _markdown_table_to_html(rows: list[str]) -> str:
    if len(rows) < 2:
        return ""
    header = [c.strip() for c in rows[0].strip("|").split("|")]
    body = rows[2:]
    head_html = "".join(f"<th>{escape(c)}</th>" for c in header)
    body_html = ""
    for row in body:
        cells = [c.strip() for c in row.strip("|").split("|")]
        body_html += "<tr>" + "".join(f"<td>{escape(c)}</td>" for c in cells) + "</tr>"
    return f"<table><thead><tr>{head_html}</tr></thead><tbody>{body_html}</tbody></table>"
