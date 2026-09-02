# Human Setup

## Install

This project uses [uv](https://docs.astral.sh/uv/).

```bash
cd chart-generator
uv sync --extra dev        # creates .venv and installs everything
uv run chart-gen --help
```

To use `chart-gen` without the `uv run` prefix:

```bash
source .venv/bin/activate
chart-gen --help
```

## Your first chart

```bash
# What does this data want to be?
uv run chart-gen recommend --data examples/deploy-durations.csv

# Draw it
uv run chart-gen chart --data examples/deploy-durations.csv \
  --form bar --x service --y duration_seconds --series environment \
  --title "Deploy duration by service" --unit s \
  --html --name deploys --out-dir output/

# Open output/deploys.html
```

## What gets written

| File | What it is |
|---|---|
| `deploys.svg` | The chart. Light and dark in one file |
| `deploys.chart.json` | The values as plotted |
| `deploys.md` | Table view: alt text, every value, per-series summary |
| `deploys.blindspots.md` | What the tool could not trust in the data |
| `deploys.html` | With `--html`: tooltips, theme toggle, table view |
| `deploys.png` | With `--png`: a raster of the SVG |

## PNG export

Install any one of these and `--png` works:

```bash
sudo apt install librsvg2-bin      # rsvg-convert
sudo apt install inkscape
pipx install cairosvg
cargo install resvg
```

Otherwise `--png` falls back to a container (Docker or Podman).

Note that a rasterizer ignores the browser's dark-mode setting, so a PNG always
comes out light unless you ask for dark explicitly:

```bash
uv run chart-gen chart ... --theme dark --png
```

## Common commands

```bash
chart-gen forms                          # every form it can draw
chart-gen palette                        # the palette and its validation record
chart-gen recommend --data d.csv         # what form fits this data
chart-gen spec dashboard.yaml --html     # render a whole dashboard
chart-gen compare a.yaml b.yaml          # diff two dashboard specs
chart-gen records                        # list session records
```

## Piping data in

```bash
psql -c "COPY (SELECT ...) TO STDOUT WITH CSV HEADER" \
  | chart-gen chart --stdin --auto-form --name query

kubectl top pods --no-headers \
  | awk '{print $1","$2}' \
  | sed '1i pod,cpu' \
  | chart-gen chart --stdin --form bar --x pod --y cpu --name pods
```

## Running the tests

```bash
uv run pytest tests/ -v
```

Snapshot goldens live in `tests/snapshots/`. If a change to layout or color is
intentional, regenerate and **read the diff**:

```bash
UPDATE_SNAPSHOTS=1 uv run pytest tests/test_snapshots.py
git diff tests/snapshots/
```
