# chart-generator

Agent-oriented chart generator. Point it at data an agent harvested — a CSV, a
JSON blob, a SQLite query, a session log it appended to as it worked — and get
back a chart that is **deterministic**, **reviewable in a diff**, and **correct
by construction** rather than by taste.

It is the charts-and-graphs counterpart to [`diagram-generator`][diagrams]:
same shape, same container-first execution policy, same agent-facing spec
surface — different subject matter. That one draws infrastructure topology.
This one draws data.

[diagrams]: ../diagram-generator

## What you get

Every render writes a matched set:

| File | What it is |
|---|---|
| `NAME.svg` | The chart. Deterministic bytes, light + dark in one file |
| `NAME.chart.json` | The resolved series, as plotted — the machine-readable view |
| `NAME.md` | The table view: alt text, every value, per-series summary |
| `NAME.blindspots.json` / `.md` | What the tool could not trust in the data |
| `NAME.html` | Optional: hover tooltips, theme toggle, table view |
| `NAME.png` | Optional: raster of the SVG |

The Markdown table is not a nice-to-have. It is written by default because the
palette's relief rule requires it — see [Design rules](#design-rules-that-are-enforced-in-code).

## Quick start

```bash
./scripts/build-container.sh

# Ask what form the data wants before drawing anything
./scripts/run-container.sh recommend --data examples/deploy-durations.csv

# Draw it
./scripts/run-container.sh chart --data examples/deploy-durations.csv \
  --form bar --x service --y duration_seconds --series environment \
  --title "Deploy duration by service" --unit s --name deploys

# Or let the heuristic pick the form and the columns
./scripts/run-container.sh chart --data examples/request-latency.csv --auto-form --name latency
```

For a host-side inner loop, use `uv sync --extra dev` and replace the wrapper
with `uv run chart-gen`. See [container setup](docs/CONTAINERS.md) for corporate
CA bundles and required container validation.

## Automation

`chart` and `spec` accept `--json`: stdout becomes one JSON document containing
output paths, series/point/gap counts, and the complete blind spots report for
each chart. Errors go to stderr and return exit code 2.

```bash
./scripts/run-container.sh chart --data examples/deploy-durations.csv \
  --auto-form --name deploys --html --png --json

# Pipe JSONL directly; use --format yaml or --format tsv for those formats.
./scripts/run-container.sh chart --stdin --auto-form --json < observations.jsonl
```

CSV, JSON, and JSONL are detected on stdin. Explicit input formats are checked;
an unsupported format fails with an actionable error. Short CSV rows retain
missing cells, while duplicate headers and extra cells are rejected to prevent
silent data loss.

## Recording data during a session

The use case this exists for: an agent is working, and along the way it learns
things worth plotting. It should not have to buffer them in its context until
the end.

```bash
chart-gen record build-times step=compile seconds=42 status=ok
chart-gen record build-times step=test    seconds=118 status=ok
chart-gen record build-times step=package seconds=17 status=ok

chart-gen records                      # list what has been recorded
chart-gen chart --record build-times --auto-form --name build
```

Each `record` call appends one JSON line and fsyncs. A session that dies halfway
still has a plottable record, and parallel agents can append to the same record
safely.

## Authored specs

For anything more than one chart, write a spec and keep it in the repo. The
spec is the reviewable artifact; the rendered files are its output.

```yaml
title: Release health
data: metrics.csv
charts:
  - name: latency
    form: line
    x: minute
    y: p99_ms
    series: endpoint
    title: p99 latency by endpoint
    unit: ms
  - name: error-budget
    form: meter
    y: consumed_percent
    target: 100
    title: Error budget consumed
```

```bash
chart-gen spec release-health.yaml --html --out-dir output/
chart-gen spec release-health.yaml --validate-only    # check without rendering
chart-gen compare before.yaml after.yaml              # diff two specs
```

See [docs/SPECS.md](docs/SPECS.md) for the full schema.

## Forms

`bar` · `column` · `stacked-bar` · `stacked-column` · `diverging-bar` · `line` ·
`area` · `scatter` · `heatmap` · `dumbbell` · `stat` · `meter`

`chart-gen recommend` maps data shape onto these, and will tell you when the
answer is **not a chart** — a single value is a stat tile, a ratio against a
limit is a meter, and more than about seven meaningful classes is a table.

## Design rules that are enforced in code

These are not style preferences; they are enforced by the renderer so an agent
cannot accidentally ship a misleading chart.

- **The palette is validated, not eyeballed.** Eight categorical hues whose
  *ordering* is the colorblind-safety mechanism. Adjacent-pair CVD ΔE 9.1 light
  / 8.4 dark against a ≥8 target. Run `chart-gen palette` for the numbers.
- **Never a dual-axis chart.** Two measures of different scale get two charts.
- **Color follows the entity, not its rank.** Sorting or filtering never
  repaints the survivors.
- **Past the series cap, the tail folds into "Other."** A generated ninth hue is
  indistinguishable from an existing one under CVD. Scatter caps at three,
  because it puts every series against every other.
- **A missing value is a gap, never a zero.** In the SVG, in the JSON, and in
  the table.
- **A legend for two or more series, never for one.** Identity is never carried
  by color alone.
- **Labels are placed only where they fit**, and are shortened with an ellipsis
  rather than clipped. Every value stays in the table regardless.
- **Dark mode is selected, not inverted.** Both modes ship in one SVG file via
  `prefers-color-scheme`, plus a `data-theme` override.

The method behind these is Anthropic's data-visualization skill; this repo is
one implementation of it. `docs/PALETTE.md` records the validator output.

## For agents

Start with [AGENTS.md](AGENTS.md) — mission, ground rules, and the
container-first execution policy. [AGENT_WORKFLOW.md](AGENT_WORKFLOW.md) is the
runbook, and `prompts/chart_agent_prompt.md` is a reusable execution prompt.

## Docs

- [docs/AGENT_SETUP.md](docs/AGENT_SETUP.md) — setup and validation for agents
- [docs/HUMAN_SETUP.md](docs/HUMAN_SETUP.md) — setup and usage for people
- [docs/SPECS.md](docs/SPECS.md) — the spec schema
- [docs/FORMS.md](docs/FORMS.md) — every form, when to use it, what it enforces
- [docs/PALETTE.md](docs/PALETTE.md) — the palette and its validation record
- [docs/CONTAINERS.md](docs/CONTAINERS.md) — container-first execution
