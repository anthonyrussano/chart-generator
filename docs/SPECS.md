# Spec schema

A spec is a YAML or JSON file describing one chart or a dashboard of several.
It is the artifact worth keeping in the repo; the rendered files are its output.

```bash
chart-gen spec dashboard.yaml --validate-only    # check without rendering
chart-gen spec dashboard.yaml --html --out-dir output/
chart-gen compare before.yaml after.yaml
```

## Single chart

The top level *is* the chart when there is no `charts:` list.

```yaml
form: bar
data: metrics.csv
x: service
y: p99_ms
title: p99 latency by service
unit: ms
sort: desc
```

## Several charts

Top-level keys become defaults every chart inherits; a chart's own key wins.

```yaml
title: Release health
data: metrics.csv          # shared by every chart below
theme: auto
width: 720

charts:
  - name: latency
    form: line
    x: minute
    y: p50_ms,p99_ms
    title: Request latency
    unit: ms

  - name: budget
    form: meter
    y: consumed_percent
    target: 100
    title: Error budget consumed
    data: budget.csv       # overrides the shared data
```

## Keys

### Data (one is required per chart)

| Key | Meaning |
|---|---|
| `data` | Path to a csv/tsv/json/jsonl/yaml/sqlite file, relative to the spec |
| `rows` | Records inline in the spec itself |
| `source` | Alias for `data` |
| `format` | Override format detection (`csv`, `tsv`, `json`, `jsonl`, `yaml`, `sqlite`) |
| `query` | SQL, required when the source is sqlite |

### Chart

| Key | Type | Meaning |
|---|---|---|
| `form` | string | **Required.** See [FORMS.md](FORMS.md) |
| `name` | string | Output base name; defaults to a slug of the title |
| `title` | string | What the reader is looking at |
| `subtitle` | string | Secondary line under the title |
| `x` | string | Column for the category or time axis |
| `y` | string | Column for the measure. A comma-separated list becomes several series on one shared axis |
| `series` | string | Column that splits rows into series |
| `x_label` / `y_label` | string | Axis titles |
| `unit` | string | Appended to values; `$`, `£`, `€` become prefixes |
| `emphasize` | string | This series takes the accent; every other goes gray |
| `sort` | string | `asc`, `desc`, `label`, `label-desc` (single-series only) |
| `top_n` | int | Keep the n largest series; sum the rest into "Other" |
| `baseline` | number | Zero line for a diverging chart |
| `target` | number | Limit for a meter |
| `value_format` | string | `auto`, `integer`, `percent`, `raw` |
| `direct_labels` | string | `auto`, `always`, `never` |
| `theme` | string | `auto` (both modes in one file), `light`, `dark` |
| `width` / `height` | int | SVG size; figures size themselves |
| `options` | mapping | Form-specific: `invert_poles`, `up_is_good` |

Axes are inferred when omitted. A series split is only ever inferred when no `x`
was given - naming an `x` is your framing of the chart, and a split you did not
ask for would change what the chart says.

## Validation

`--validate-only` checks every chart and reports **all** problems at once:

- a missing or unknown `form`, with the valid list
- a chart with no data source
- unknown keys (catches typos like `titel`)
- invalid inherited defaults, setting types, enums, or nonpositive dimensions
- malformed inline rows or an empty chart list
- output names that collide after slug conversion
- unreadable data files and unresolved column references (data paths are relative to the spec)

Validation reads data and resolves columns but does not render or write files.
All charts undergo this same preflight before rendering starts. A successful
validation does not check visual layout or PNG rasterizer availability.

Add `--json` to validation for `{"valid": true, "counts": {...}}` on success.
Errors use stderr and exit code 2, including in JSON mode.

```
$ chart-gen spec broken.yaml --validate-only
Spec broken.yaml has 2 problem(s):
  - charts[0]: unknown form 'pie'. Choose one of: area, bar, column, ...
  - charts[0]: needs 'data' (a file path), 'rows' (inline records), or a
    top-level 'data' shared by every chart
```

## Comparing specs

`chart-gen compare current.yaml future.yaml` writes a JSON diff and a Markdown
summary of what was added, removed, changed, and unchanged - field by field, for
reviewing a dashboard change in a PR.

## Output

Every chart in a spec writes the full set, named by its `name`:

```
output/latency.svg
output/latency.chart.json
output/latency.md
output/latency.blindspots.json
output/latency.blindspots.md
output/latency.html            # with --html
output/latency.png             # with --png
```

`chart-gen spec dashboard.yaml --json` emits one stdout document containing a
`charts` array. Each entry includes the output name and form, series/point/gap
counts, written file paths, and the complete blind spots report. The normal
output files are still written. See [AGENT_WORKFLOW.md](../AGENT_WORKFLOW.md)
for field names and path semantics.
