# Chart Agent Execution Prompt

A reusable prompt for an agent asked to visualize data. Fill in the bracketed
parts.

---

You have data to visualize: **[describe the data and where it lives]**.

The goal of the chart is: **[what the reader must be able to do - compare
magnitudes, see a trend, tell series apart, judge one number against a limit]**.

Use the `chart-gen` CLI in this repository. Work in this order.

## 1. Look at the data before choosing anything

```bash
chart-gen recommend --data [path] --json
```

Read the shape it reports and the ranked forms. Do not skip to rendering.

## 2. Decide the form deliberately

Take the top recommendation unless the stated goal points elsewhere, and say in
one sentence why the form you chose fits the goal.

Be willing to conclude that the answer is not a chart:
- one current value -> a stat tile (`--form stat`)
- a handful of headline numbers -> a KPI row of stat tiles
- a ratio against a limit -> a meter (`--form meter`)
- more than about seven meaningful color classes -> a table

If one series is the point and the rest are context, that is **emphasis**
(`--emphasize <series>`), not eight colors.

## 3. Render

```bash
chart-gen chart --data [path] --form [form] \
  --x [column] --y [column] [--series column] \
  --title "[what the chart shows]" --unit "[unit]" \
  --name [output-name] --out-dir output/
```

Give it a real title - one that states what the reader is looking at, not the
name of the file.

## 4. Read the blind spots report

```bash
cat output/[output-name].blindspots.md
```

Anything listed there must appear in what you report back. In particular: gaps
drawn as gaps, series folded into "Other", and measures of different scale
sharing an axis.

## 5. Verify

- Confirm the printed series and point counts match what you expect.
- Render `--png` or `--html` and **look at the chart** for collisions, overflow,
  and an empty-looking plot.
- Confirm the values in `output/[output-name].md` match the source data.

## Constraints

- Never invent, interpolate, or zero-fill a missing value.
- Never put two measures of different scale on one axis without saying so.
- Never remove the Markdown table view; it is how the values stay accessible.
- If the data does not support the chart you were asked for, say that plainly
  and render what it does support.

## Report back

1. The form you chose and why it fits the goal.
2. The files written.
3. Series and point counts.
4. Everything in the blind spots report.
5. What you could not determine from this data.
