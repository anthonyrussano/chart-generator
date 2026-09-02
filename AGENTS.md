# AGENTS.md

This repository is intended for autonomous or semi-autonomous coding agents.

## Mission

Improve `chart-gen` so that data an agent harvests during a session becomes a
chart that is accurate, reproducible, and easy to review in a PR.

## Ground Rules

1. Preserve deterministic output. The same input must produce the same bytes.
2. Prefer additive changes over broad rewrites.
3. Keep collectors independent (`csv`, `json`, `jsonl`, `yaml`, `sqlite`, `stdin`).
4. **Never invent a data point.** A value that did not parse is `None`, is drawn
   as a gap, and is reported as a blind spot. It is never silently zero.
5. Report data-quality blind spots explicitly, the way the infrastructure
   generator reports collection blind spots.
6. Do not add a chart form without also adding its entry to `docs/FORMS.md`, a
   `recommend` rule that knows when to reach for it, and a snapshot test.

## The Design Rules Are Not Style Preferences

These are enforced in code because a chart that breaks them misleads its reader.
If a change would violate one, the change is wrong, not the rule.

1. **Never a dual-axis chart.** Two measures of different scale get two charts,
   small multiples, or a common index base. One y axis, always.
2. **Color follows the entity, not its rank.** Slots are assigned by first
   appearance. Sorting or filtering must never repaint the survivors.
3. **Never generate a hue past the palette's last slot.** The tail folds into
   "Other". Scatter caps at three, because it puts every series against every
   other and the palette only clears the all-pairs floors at three.
4. **Sequential is one hue, light to dark. Diverging is two opposite hues with a
   neutral midpoint.** Never a rainbow; never a hue at the midpoint.
5. **A missing value is a gap** in the SVG, the JSON, and the table.
6. **A legend for two or more series; none for one.** Identity is never carried
   by color alone.
7. **Text wears text tokens, never a series color.** The colored mark beside the
   text carries identity. The one exception is a label set inside a colored
   fill, where ink is picked by the fill's luminance.
8. **Labels are placed only where they fit.** Measure first, ellipsize if
   needed, and never clip. Every value stays in the table view regardless.
9. **The palette is validated, not eyeballed.** If you change a color, re-run
   the validator (see `docs/PALETTE.md`) and update the recorded numbers in the
   same PR. `tests/test_theme.py` pins the current set deliberately.

## Container-First Execution Policy

The repository container is the default execution environment for agents. Use it
for setup, chart generation, PNG export, smoke tests, and final validation.
Host-side `uv run ...` is permitted for a fast inner loop, but it does not
replace the required container verification.

1. Build or refresh the image before generation and final checks:
   `./scripts/build-container.sh`
2. Run `chart-gen` through the mounted-workspace wrapper:
   `./scripts/run-container.sh <chart-gen arguments>`
3. The wrappers prefer Docker and fall back to Podman. Set
   `CONTAINER_ENGINE=podman` or `CONTAINER_ENGINE=docker` to select explicitly.
4. Fall back to host execution only when the container engine is unavailable or
   the container path fails for a documented reason. Report that fallback and
   the exact failure as a blind spot.

## Repo Layout

- `src/agent_charts/cli.py`: orchestration, argument surface, command dispatch
- `src/agent_charts/collectors.py`: data adapters (csv, json, jsonl, yaml, sqlite, stdin, inline)
- `src/agent_charts/model.py`: contracts (`Column`, `DataSet`, `Series`, `ChartSpec`, `ChartData`)
- `src/agent_charts/normalize.py`: series resolution, alignment, slot assignment, folding
- `src/agent_charts/recommend.py`: the form heuristic, including "this is not a chart"
- `src/agent_charts/session.py`: append-only session records
- `src/agent_charts/blind_spots.py`: data-quality reporting (JSON + Markdown)
- `src/agent_charts/spec_workflows.py`: authored specs, validation, comparison
- `src/agent_charts/theme.py`: the validated palette and chrome tokens
- `src/agent_charts/scales.py`: scales and clean tick generation
- `src/agent_charts/charts/`: the forms (`base.py` holds shared layout and chrome)
- `src/agent_charts/renderers/`: svg, chart dispatch, json, markdown, html, images
- `tests/`: pytest suite with snapshot golden files in `tests/snapshots/`
- `scripts/`: container-first build, run, and validation wrappers
- `prompts/`: reusable execution prompt templates
- `docs/`: setup, spec schema, forms reference, palette record, containers

## Contribution Priorities

1. Widen the range of data shapes that `recommend` reads correctly.
2. Improve robustness of collectors on partial, ragged, or dirty data.
3. Add forms that answer a job no current form answers - not variants for their
   own sake.
4. Keep the command interface stable; if it changes, update docs in the same PR.

## Required Checks Before Finishing

1. `uv run pytest tests/ -v` - all tests pass
2. `./scripts/build-container.sh`
3. `./scripts/check-container.sh` (tests, compilation, CLI help, smoke render)
4. At least one smoke run of `./scripts/run-container.sh` with a real form
5. Verify the output files exist and the printed series/point counts are right
6. **Look at the chart.** The tests check structure, not layout. Render it and
   check for collisions, overflow, and geometry before calling it done.

When feature flags are requested, validate them too:
- HTML output: smoke with `--html`, and confirm the table view and tooltips.
- PNG export: smoke with `--png`, and with `--theme dark --png` (a rasterizer
  ignores media queries, so dark must be baked as the base rules).
- Snapshots: `UPDATE_SNAPSHOTS=1 uv run pytest tests/test_snapshots.py`, then
  review the diff. Never regenerate goldens to make a failure go away without
  reading what changed.

## Implementation Guidelines

- Keep functions small and form-specific. Shared chrome lives in `charts/base.py`.
- Round every coordinate through `scales.round_coord` / `fmt_coord`.
- Never emit a generated id, a timestamp, or anything else non-deterministic
  into the SVG.
- Attach a tooltip `<title>` as a **child** of its mark, never as a sibling - as
  a sibling it renders nothing.
- Treat a rasterizer or container failure as an actionable error with the exact
  command in the message.

## PR Checklist for Agents

1. What data shapes or forms were changed, and why?
2. What new columns, forms, or spec keys were introduced?
3. What commands were run for verification, including the container checks?
4. Did any snapshot change? Why is the new output correct?
5. If a color changed: what did the validator report?
6. What limitations remain?
