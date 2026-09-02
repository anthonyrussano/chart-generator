# Agent Setup

Explicit commands. Run them in order. Read `AGENTS.md` for the rules and
`AGENT_WORKFLOW.md` for the working loop.

## Container-first (the default)

```bash
./scripts/build-container.sh
./scripts/check-container.sh
./scripts/run-container.sh recommend --data examples/deploy-durations.csv
./scripts/run-container.sh chart --data examples/deploy-durations.csv \
    --auto-form --name smoke --out-dir output/
```

`check-container.sh` runs compilation, the test suite, the CLI help, a smoke
render, and verifies the output files are non-empty. It must pass before you
finish.

Select an engine explicitly with `CONTAINER_ENGINE=docker` or
`CONTAINER_ENGINE=podman`. Override the image tag with `CHART_GEN_IMAGE`.

## Host inner loop

Faster to iterate on, but it does not replace the container check.

```bash
uv sync --extra dev
uv run pytest tests/ -v
uv run chart-gen --help
uv run chart-gen forms
uv run chart-gen palette
```

## Verifying a change

```bash
# 1. The suite
uv run pytest tests/ -v

# 2. Compilation of every module
uv run python -m compileall -q src/agent_charts

# 3. Every form still renders
for form in $(uv run chart-gen forms); do
  uv run chart-gen chart --data examples/deploy-durations.csv \
    --form "$form" --x service --y duration_seconds \
    --out-dir /tmp/forms --name "$form" >/dev/null || echo "FAILED: $form"
done

# 4. Snapshots - review the diff, never regenerate blindly
UPDATE_SNAPSHOTS=1 uv run pytest tests/test_snapshots.py
git diff tests/snapshots/

# 5. Look at the result
uv run chart-gen chart --data examples/request-latency.csv --auto-form \
  --html --name look --out-dir /tmp/look
```

## PNG export

The SVG is the source of truth; PNG is a raster of it. A native rasterizer is
used when present, with a container fallback.

```bash
# any one of these makes --png work natively
resvg | rsvg-convert | inkscape | cairosvg

uv run chart-gen chart ... --png --png-width 1440
uv run chart-gen chart ... --png --raster-runtime container
```

A rasterizer ignores `prefers-color-scheme`, so it renders the stylesheet's base
rules, which are the light palette. **For a dark PNG, pass `--theme dark`**,
which bakes the dark steps as the base rules.

## Determinism

The same input must produce the same bytes. If you touch layout, rounding, or
the palette, confirm it still holds:

```bash
uv run chart-gen chart --data examples/deploy-durations.csv --form bar \
  --x service --y duration_seconds --out-dir /tmp/a --name c >/dev/null
uv run chart-gen chart --data examples/deploy-durations.csv --form bar \
  --x service --y duration_seconds --out-dir /tmp/b --name c >/dev/null
diff /tmp/a/c.svg /tmp/b/c.svg && echo "deterministic"
```
