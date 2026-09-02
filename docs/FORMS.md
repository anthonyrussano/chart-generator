# Forms

Every form `chart-gen` can draw, the job it answers, and what the renderer
enforces for it. `chart-gen recommend` maps data shape onto this table.

## Is it even a chart?

| The data is | Use | Not |
|---|---|---|
| A single current value | `stat` | A one-bar bar chart |
| A handful of headline numbers | `stat` (a KPI row) | A grouped bar chart |
| A single ratio against a limit | `meter` | A pie of two slices |
| More than ~7 classes carrying color | a table (`NAME.md`) | More colors |

## The job to the form

| Job (what the reader must do) | Form | Color job |
|---|---|---|
| Compare magnitude across categories | `bar` / `column` | one hue |
| Compare magnitude across a grid | `heatmap` | sequential |
| Trend over time, one series | `area` | one hue |
| Trend over time, several series | `line` | categorical |
| Tell distinct series apart | `column` + `--series`, `line` | categorical |
| One series is the point, rest are context | any + `--emphasize` | one hue + gray |
| Above/below a baseline | `diverging-bar` | diverging |
| Part-to-whole | `stacked-bar` / `stacked-column` | categorical |
| Before to after, per item | `dumbbell` | one hue, two shades |
| Relationship between two measures | `scatter` | categorical, capped at 3 |
| One number | `stat` | - |
| One ratio against a limit | `meter` | severity |

## Each form

### `bar` / `column`

Magnitude across categories. `bar` is horizontal - reach for it when category
names are long or numerous, which is most of the time. `column` is vertical.

Enforced: bars are capped at 24px thick so the band's leftover stays as air;
the data-end is rounded 4px and the baseline end is square; adjacent bars are
separated by a 2px surface gap, never a stroke; a single series is direct-labeled
when the chart is small enough to read.

```bash
chart-gen chart --data d.csv --form bar --x service --y p99_ms --sort desc
```

### `stacked-bar` / `stacked-column`

Part-to-whole. Go horizontal when categories have long names.

Enforced: the value scale reaches the tallest *stack*, not the tallest segment;
a 2px surface gap separates every segment; only the top of the stack gets the
rounded data-end; an interior segment whose label will not fit is left to the
legend and the table rather than clipped.

### `diverging-bar`

Above or below a baseline. Polarity, not goodness.

Enforced: the two poles use the diverging pair (warm and cool), never two
categorical slots; the midpoint is neutral. `--baseline` moves the zero;
`--invert-poles` swaps which side reads warm.

### `line` / `area`

Trend over time. `area` fills to the baseline, which reads honestly for exactly
one series - with several, the fills occlude each other, so `line` is used.

Enforced: 2px stroke, round joins; a missing value breaks the line rather than
being drawn through zero; end markers carry a 2px surface ring so they stay
legible where lines cross; end labels are placed only when the series separate
at the right edge, and are dropped past four converging series in favor of the
legend and the table.

`--y` accepts a comma-separated list, so several measures become several series
on **one** shared axis. Measures of wildly different magnitude are reported in
the blind spots - the fix is separate charts or a common index base, never a
second y axis.

### `scatter`

The relationship between two numeric measures.

Enforced: capped at **three** series. Scatter puts every series against every
other one, and the palette only clears the all-pairs colorblind floors at three.
Past that, fold to "Other" or facet.

### `heatmap`

Magnitude across a grid, on one sequential hue.

Enforced: one hue light-to-dark, never a rainbow; a cell with no value is left
as surface rather than colored as zero; a value label inside a cell picks white
or ink by the fill's luminance; a scale legend always ships; no categorical
legend, because the color means magnitude, not identity.

### `dumbbell`

Before to after, per item. The first two series are the two ends.

### `stat`

A stat tile, or a row of them. One value becomes a hero figure.

Optional columns on each row: `delta` (shown with an arrow; colored only when
`--up-is-good` or `--up-is-bad` says which direction is good) and `trend` /
`sparkline` (a comma-separated list, drawn as a 12-point sparkline in the
de-emphasis hue with the current period in the accent).

Enforced: the figure sizes itself to its content; sparklines stay inside their
own tile.

### `meter`

A ratio against a limit. `--target` sets the limit.

Enforced: the fill carries severity (accent, then warning, then critical) and
the unfilled track is a lighter step of the fill's own ramp, so state reads
across the whole bar. The value and the limit are always printed beside it, so
severity never rides on color alone.

## Options that apply to any form

| Flag | Effect |
|---|---|
| `--emphasize <series>` | That series takes the accent; every other goes gray |
| `--top-n <n>` | Keep the n largest series; sum the rest into "Other" |
| `--sort asc\|desc\|label\|label-desc` | Reorder a single-series chart |
| `--unit <s>` | Appended to values; `$`, `£`, `€` become prefixes |
| `--value-format auto\|integer\|percent\|raw` | How values are written |
| `--direct-labels auto\|always\|never` | Override selective labeling |
| `--theme auto\|light\|dark` | `auto` ships both in one file |
| `--width` / `--height` | SVG size (figures size themselves) |
