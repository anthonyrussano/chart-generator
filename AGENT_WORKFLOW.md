# Agent Workflow

The operator runbook. Read `AGENTS.md` first for the ground rules.

## The loop

```
data arrives  ->  recommend  ->  chart  ->  read the blind spots  ->  iterate
```

Do not skip `recommend`. It is cheap, and it is the step that stops you from
drawing an eight-color chart when the story is one number.

## 1. Get the data in

| You have | Do this |
|---|---|
| A file on disk | `chart-gen chart --data path.csv` |
| Output from another command | `... \| chart-gen chart --stdin` |
| A database | `chart-gen chart --data app.db --query "SELECT ..."` |
| Values you are learning as you work | `chart-gen record <name> k=v ...` |
| A structure you already hold | Write it into a spec's `rows:` |

The collectors accept the shapes agents actually emit: a list of objects, a
`{"rows": [...]}` wrapper, a `{"name": value}` mapping, a `{"series": [...]}`
mapping, and a bare list of scalars. Ragged records are squared off, and a field
a record did not carry stays `None` rather than becoming `0`.

## 2. Ask what form the data wants

```bash
chart-gen recommend --data metrics.csv
chart-gen recommend --data metrics.csv --json   # for programmatic use
```

It prints the data's shape, a ranked list of forms with the reason for each, a
runnable command for the best one, and cautions. It will tell you when the
answer is **not a chart**:

- one row -> a stat tile, not a one-bar bar chart
- a ratio against a limit -> a meter, not a two-slice pie
- more than about seven classes carrying color -> a table

## 3. Render

```bash
chart-gen chart --data metrics.csv --form bar \
  --x service --y p99_ms --series region \
  --title "p99 latency by service" --unit ms \
  --name latency --out-dir output/
```

Or let the heuristic choose everything:

```bash
chart-gen chart --data metrics.csv --auto-form --name latency
```

`--auto-form` only fills in what you left blank, so you can accept its form and
still override a column.

## 4. Read the blind spots

Every render writes `NAME.blindspots.md`. **Read it before you draw a conclusion
from the chart.** It tells you what the tool could not trust:

- rows with no value (drawn as gaps, not zeros)
- a column that looked numeric but had dirty cells
- series that were summed into "Other"
- measures of wildly different scale sharing one axis
- labels that had to be thinned or dropped to avoid collision

A finding here does not mean the chart is wrong. It means the chart is not the
whole story, and you should say so when you report the result.

## 5. Look at it

The test suite checks structure, not layout. If the chart matters, render it and
look:

```bash
chart-gen chart ... --png            # needs resvg / rsvg-convert / inkscape / cairosvg
chart-gen chart ... --html           # then open it: tooltips, table view, theme toggle
```

Check for label collisions, overflowing text, and empty-looking plots.

## Multi-chart work

Once you need more than one chart, stop passing flags and write a spec. The spec
is the artifact worth keeping in the repo; the rendered files are its output.

```bash
chart-gen spec dashboard.yaml --validate-only    # check before rendering
chart-gen spec dashboard.yaml --html --out-dir output/
chart-gen compare before.yaml after.yaml         # what changed between two specs
```

## Session recording

```bash
chart-gen record deploy step=build seconds=42 status=ok
chart-gen record deploy step=test  seconds=118 status=ok
chart-gen records                                # list what exists
chart-gen chart --record deploy --auto-form --name deploy
chart-gen records --clear deploy                 # start over
```

Each call appends one JSON line and fsyncs, so a session that dies halfway still
has a usable record and parallel agents can append to the same one.

## Before you finish

```bash
uv run pytest tests/ -v
./scripts/build-container.sh
./scripts/check-container.sh
```

Report: the form you chose and why, the counts printed by the render, anything
in the blind spots report, and what you could not determine from the data.

## Common mistakes

| Symptom | Cause | Fix |
|---|---|---|
| The chart looks empty | One measure dwarfs the others on a shared axis | Split into separate charts, or index to a common base |
| Every bar is a different color | A value ramp on nominal categories | One series, one color. Drop `--series` |
| A series vanished | It folded into "Other" past the cap | Check the blind spots report; use `--top-n` deliberately |
| Labels are missing | They would have collided or overflowed | Read the rendering notes; the values are in the table |
| The story is buried | Eight hues when one series is the point | `--emphasize <series>` grays the rest |
| PNG is light when you wanted dark | A rasterizer ignores media queries | Render with `--theme dark --png` |
