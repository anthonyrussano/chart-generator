"""chart-gen: turn harvested data into reviewable charts.

Commands
  chart      render one chart from a data file, stdin, or a session record
  spec       render one or many charts from an authored YAML/JSON spec
  recommend  inspect data and say which form reads it best
  record     append one observation to a session record
  records    list session records
  compare    diff two spec files
  forms      list the available chart forms
  palette    print the palette and its validation status
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import session
from .blind_spots import (
    collect_blind_spots,
    inspect_chart,
    inspect_dataset,
    write_blind_spots_json,
    write_blind_spots_md,
)
from .collectors import CollectorError, collect, collect_from_stdin, collect_from_text
from .model import ChartSpec, DataSet
from .normalize import NormalizeError, resolve
from .recommend import format_advice, recommend
from .renderers.chart_renderer import RenderError, available_forms, render_svg
from .renderers.html import render_html
from .renderers.images import (
    CONTAINER_ENGINES,
    DEFAULT_IMAGE,
    RASTER_RUNTIMES,
    RasterError,
    render_png,
)
from .renderers.json_renderer import render_json
from .renderers.markdown import render_markdown
from .spec_workflows import (
    SpecError,
    chart_name,
    chart_specs,
    compare_specs,
    dataset_for,
    load_spec,
    spec_counts,
    to_chart_spec,
    validate_spec,
    write_compare_summary,
)
from .theme import CATEGORICAL_DARK, CATEGORICAL_LIGHT, STATUS, THEMES

VALUE_FORMATS = ("auto", "integer", "percent", "raw")
DIRECT_LABEL_MODES = ("auto", "always", "never")
SORT_MODES = ("asc", "desc", "label", "label-desc")


def _add_output_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--out-dir", default="output", help="Output directory")
    parser.add_argument("--name", default="chart", help="Output base name")
    parser.add_argument("--html", action="store_true", help="Also write an interactive HTML page")
    parser.add_argument("--png", action="store_true", help="Also rasterize the SVG to PNG")
    parser.add_argument("--png-width", type=int, default=1440, help="PNG width in pixels")
    parser.add_argument(
        "--raster-runtime", default="auto", choices=RASTER_RUNTIMES,
        help="PNG rasterizer: a native tool, a container, or automatic detection",
    )
    parser.add_argument(
        "--container-engine", default="auto", choices=CONTAINER_ENGINES,
        help="Container engine used when rasterizing in a container",
    )
    parser.add_argument("--raster-image", default=DEFAULT_IMAGE, help="Container image for PNG export")
    parser.add_argument(
        "--no-markdown", action="store_true",
        help="Skip the Markdown table view (it is the palette's relief mechanism; keep it)",
    )


def _add_spec_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--form", help=f"Chart form: {', '.join(available_forms())}")
    parser.add_argument("--title", default="", help="Chart title")
    parser.add_argument("--subtitle", default="", help="Chart subtitle")
    parser.add_argument("--x", help="Column for the x axis / category")
    parser.add_argument("--y", help="Column for the measure")
    parser.add_argument("--series", help="Column that splits rows into series")
    parser.add_argument("--x-label", default="", help="Axis title under the x axis")
    parser.add_argument("--y-label", default="", help="Axis title beside the y axis")
    parser.add_argument(
        "--emphasize",
        help="Draw this series in the accent hue and every other in gray",
    )
    parser.add_argument("--unit", default="", help="Unit appended to values ($, %%, ms)")
    parser.add_argument("--width", type=int, default=720, help="SVG width")
    parser.add_argument("--height", type=int, default=420, help="SVG height")
    parser.add_argument("--theme", default="auto", choices=THEMES, help="Theme baked into the SVG")
    parser.add_argument("--sort", choices=SORT_MODES, help="Sort a single-series chart")
    parser.add_argument("--top-n", type=int, help="Keep the N largest series; fold the rest into 'Other'")
    parser.add_argument("--baseline", type=float, help="Baseline for a diverging chart")
    parser.add_argument("--target", type=float, help="Limit for a meter")
    parser.add_argument("--value-format", default="auto", choices=VALUE_FORMATS)
    parser.add_argument("--direct-labels", default="auto", choices=DIRECT_LABEL_MODES)
    parser.add_argument(
        "--invert-poles", action="store_true",
        help="Swap the warm and cool poles of a diverging chart",
    )
    parser.add_argument(
        "--up-is-good", dest="up_is_good", action="store_true", default=None,
        help="Color a stat tile's delta green when it rises",
    )
    parser.add_argument(
        "--up-is-bad", dest="up_is_good", action="store_false",
        help="Color a stat tile's delta green when it falls",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="chart-gen",
        description=(
            "Agent-oriented chart generator: harvested data in, deterministic "
            "SVG / HTML / JSON / Markdown out."
        ),
    )
    sub = parser.add_subparsers(dest="command")

    # --- chart ------------------------------------------------------------
    chart = sub.add_parser("chart", help="Render one chart from a data source")
    source = chart.add_mutually_exclusive_group()
    source.add_argument("--data", help="Path to a csv/tsv/json/jsonl/yaml/sqlite file")
    source.add_argument("--stdin", action="store_true", help="Read the dataset from stdin")
    source.add_argument("--record", help="Read a session record by name")
    chart.add_argument("--record-dir", default=str(session.DEFAULT_DIR), help="Session record directory")
    chart.add_argument("--format", default="auto", help="Override the input format")
    chart.add_argument("--query", help="SQL query, required for a sqlite source")
    _add_spec_args(chart)
    _add_output_args(chart)
    chart.add_argument(
        "--auto-form", action="store_true",
        help="Let the form heuristic pick the form instead of passing --form",
    )

    # --- spec -------------------------------------------------------------
    spec = sub.add_parser("spec", help="Render charts from an authored spec file")
    spec.add_argument("spec_file", help="YAML or JSON spec")
    spec.add_argument("--out-dir", default="output", help="Output directory")
    spec.add_argument("--name", help="Override the output base name for a single-chart spec")
    spec.add_argument("--validate-only", action="store_true", help="Check the spec and exit")
    spec.add_argument("--html", action="store_true", help="Also write HTML pages")
    spec.add_argument("--png", action="store_true", help="Also rasterize to PNG")
    spec.add_argument("--png-width", type=int, default=1440)
    spec.add_argument("--raster-runtime", default="auto", choices=RASTER_RUNTIMES)
    spec.add_argument("--container-engine", default="auto", choices=CONTAINER_ENGINES)
    spec.add_argument("--raster-image", default=DEFAULT_IMAGE)
    spec.add_argument("--no-markdown", action="store_true")

    # --- recommend --------------------------------------------------------
    rec = sub.add_parser("recommend", help="Say which form reads this data best")
    rec_source = rec.add_mutually_exclusive_group()
    rec_source.add_argument("--data", help="Path to a data file")
    rec_source.add_argument("--stdin", action="store_true", help="Read the dataset from stdin")
    rec_source.add_argument("--record", help="Read a session record by name")
    rec.add_argument("--record-dir", default=str(session.DEFAULT_DIR))
    rec.add_argument("--format", default="auto")
    rec.add_argument("--query", help="SQL query for a sqlite source")
    rec.add_argument("--json", action="store_true", help="Emit the advice as JSON")

    # --- record / records --------------------------------------------------
    record = sub.add_parser("record", help="Append one observation to a session record")
    record.add_argument("name", help="Record name")
    record.add_argument("fields", nargs="+", help="key=value pairs")
    record.add_argument("--record-dir", default=str(session.DEFAULT_DIR))
    record.add_argument("--no-timestamp", action="store_true", help="Do not add an 'at' field")

    records = sub.add_parser("records", help="List session records")
    records.add_argument("--record-dir", default=str(session.DEFAULT_DIR))
    records.add_argument("--clear", help="Delete the named record")

    # --- compare ----------------------------------------------------------
    compare = sub.add_parser("compare", help="Diff two spec files")
    compare.add_argument("current")
    compare.add_argument("future")
    compare.add_argument("--out-dir", default="output")
    compare.add_argument("--name", default="spec-compare")

    # --- forms / palette ---------------------------------------------------
    sub.add_parser("forms", help="List the available chart forms")
    palette = sub.add_parser("palette", help="Print the palette and its validation status")
    palette.add_argument("--json", action="store_true")

    return parser


# --- source resolution ----------------------------------------------------


def _dataset_from_args(args) -> DataSet:
    if getattr(args, "stdin", False):
        return collect_from_stdin(fmt=args.format if args.format != "auto" else "auto")
    if getattr(args, "record", None):
        records = session.read(args.record, args.record_dir)
        if not records:
            raise CollectorError(f"Record '{args.record}' is empty")
        return collect_from_text(
            "\n".join(json.dumps(r) for r in records), fmt="jsonl", origin=f"record:{args.record}"
        )
    if getattr(args, "data", None):
        return collect(args.data, fmt=args.format, query=args.query)
    raise CollectorError("No data source. Pass --data, --stdin, or --record.")


def _spec_from_args(args, form: str) -> ChartSpec:
    return ChartSpec(
        form=form,
        title=args.title,
        subtitle=args.subtitle,
        x=args.x,
        y=args.y,
        series=args.series,
        x_label=args.x_label,
        y_label=args.y_label,
        emphasize=args.emphasize,
        unit=args.unit,
        width=args.width,
        height=args.height,
        theme=args.theme,
        sort=args.sort,
        top_n=args.top_n,
        baseline=args.baseline,
        target=args.target,
        value_format=args.value_format,
        direct_labels=args.direct_labels,
        options={
            k: v for k, v in (
                ("invert_poles", args.invert_poles),
                ("up_is_good", args.up_is_good),
            ) if v is not None and v is not False
        },
    )


# --- the write path -------------------------------------------------------


def _emit(
    chart,
    dataset: DataSet,
    out_dir: Path,
    name: str,
    *,
    want_html: bool,
    want_png: bool,
    want_markdown: bool,
    png_width: int = 1440,
    raster_runtime: str = "auto",
    container_engine: str = "auto",
    raster_image: str = DEFAULT_IMAGE,
    errors: list[str] | None = None,
) -> list[Path]:
    """Write every output for one chart, plus its blind spots report."""
    out_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []

    svg_path = out_dir / f"{name}.svg"
    _, layout = render_svg(chart, svg_path)
    written.append(svg_path)

    json_path = out_dir / f"{name}.chart.json"
    render_json(chart, json_path)
    written.append(json_path)

    if want_markdown:
        md_path = out_dir / f"{name}.md"
        render_markdown(chart, md_path, layout.notes)
        written.append(md_path)

    if want_html:
        html_path = out_dir / f"{name}.html"
        render_html(chart, html_path, layout.notes)
        written.append(html_path)

    if want_png:
        png_path = out_dir / f"{name}.png"
        render_png(
            svg_path, png_path,
            width=png_width,
            runtime=raster_runtime,
            container_engine=container_engine,
            image=raster_image,
        )
        written.append(png_path)

    data_report = inspect_dataset(dataset)
    chart_report = inspect_chart(chart)
    report = collect_blind_spots(
        errors=errors,
        missing_values=data_report["missing_values"],
        unparsed_values=data_report["unparsed_values"],
        empty_sources=data_report["empty_sources"],
        folded_series=chart_report["folded_series"],
        warnings=chart_report["warnings"] + layout.notes,
    )
    written.append(write_blind_spots_json(report, out_dir / f"{name}.blindspots.json"))
    written.append(write_blind_spots_md(report, out_dir / f"{name}.blindspots.md"))

    return written


def _report(written: list[Path], chart) -> None:
    points = sum(len(s.points) for s in chart.series)
    print(f"form: {chart.spec.form}  series: {len(chart.series)}  points: {points}")
    for path in written:
        print(f"  wrote {path}")


# --- commands -------------------------------------------------------------


def cmd_chart(args) -> int:
    dataset = _dataset_from_args(args)

    form = args.form
    if args.auto_form or not form:
        advice = recommend(dataset)
        if advice.best is None:
            print("Could not recommend a form for this data.", file=sys.stderr)
            print(format_advice(advice), file=sys.stderr)
            return 2
        form = advice.best.form
        print(f"auto-form: {form} ({advice.best.reason})")
        # Only take the heuristic's column hints where the caller left a gap.
        for key, value in advice.best.spec_hints.items():
            if value is not None and getattr(args, key, None) in (None, ""):
                setattr(args, key, value)

    spec = _spec_from_args(args, form)
    chart = resolve(dataset, spec)

    written = _emit(
        chart, dataset,
        out_dir=Path(args.out_dir),
        name=args.name,
        want_html=args.html,
        want_png=args.png,
        want_markdown=not args.no_markdown,
        png_width=args.png_width,
        raster_runtime=args.raster_runtime,
        container_engine=args.container_engine,
        raster_image=args.raster_image,
    )
    _report(written, chart)
    return 0


def cmd_spec(args) -> int:
    payload = load_spec(args.spec_file)
    problems = validate_spec(payload)
    if problems:
        print(f"Spec {args.spec_file} has {len(problems)} problem(s):", file=sys.stderr)
        for problem in problems:
            print(f"  - {problem}", file=sys.stderr)
        return 2

    counts = spec_counts(payload)
    print(f"spec: {args.spec_file}  " + "  ".join(f"{k}={v}" for k, v in counts.items()))
    if args.validate_only:
        print("spec is valid")
        return 0

    base_dir = Path(args.spec_file).resolve().parent
    entries = chart_specs(payload)
    out_dir = Path(args.out_dir)

    for index, entry in enumerate(entries):
        dataset = dataset_for(entry, base_dir)
        chart = resolve(dataset, to_chart_spec(entry))
        name = args.name if args.name and len(entries) == 1 else chart_name(entry, index)
        written = _emit(
            chart, dataset,
            out_dir=out_dir,
            name=name,
            want_html=args.html,
            want_png=args.png,
            want_markdown=not args.no_markdown,
            png_width=args.png_width,
            raster_runtime=args.raster_runtime,
            container_engine=args.container_engine,
            raster_image=args.raster_image,
        )
        _report(written, chart)
    return 0


def cmd_recommend(args) -> int:
    dataset = _dataset_from_args(args)
    advice = recommend(dataset)
    if args.json:
        print(json.dumps(advice.to_dict(), indent=2))
    else:
        print(format_advice(advice))
    return 0 if advice.recommendations else 2


def cmd_record(args) -> int:
    fields = session.parse_fields(args.fields)
    path = session.append(
        args.name, fields, directory=args.record_dir, timestamp=not args.no_timestamp
    )
    print(f"recorded to {path}")
    return 0


def cmd_records(args) -> int:
    if args.clear:
        path = session.clear(args.clear, args.record_dir)
        print(f"cleared {path}")
        return 0
    entries = session.list_records(args.record_dir)
    if not entries:
        print(f"no records in {args.record_dir}")
        return 0
    for name, count, path in entries:
        print(f"{name:24} {count:6} observations  {path}")
    return 0


def cmd_compare(args) -> int:
    diff = compare_specs(load_spec(args.current), load_spec(args.future))
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    json_path = out_dir / f"{args.name}.json"
    json_path.write_text(json.dumps(diff, indent=2, sort_keys=True), encoding="utf-8")
    md_path = write_compare_summary(diff, out_dir / f"{args.name}.md")

    print(
        f"added={len(diff['added'])} removed={len(diff['removed'])} "
        f"changed={len(diff['changed'])} unchanged={len(diff['unchanged'])}"
    )
    print(f"  wrote {json_path}")
    print(f"  wrote {md_path}")
    return 0


def cmd_forms(args) -> int:
    for form in available_forms():
        print(form)
    return 0


def cmd_palette(args) -> int:
    payload = {
        "categorical_light": list(CATEGORICAL_LIGHT),
        "categorical_dark": list(CATEGORICAL_DARK),
        "status": STATUS,
        "validation": {
            "light_adjacent": {"cvd_delta_e": 9.1, "normal_delta_e": 19.6, "result": "PASS"},
            "dark_adjacent": {"cvd_delta_e": 8.4, "normal_delta_e": 19.3, "result": "PASS"},
            "light_all_pairs_first_3": {"cvd_delta_e": 9.2, "normal_delta_e": 24.0, "result": "PASS"},
            "dark_all_pairs_first_3": {"cvd_delta_e": 9.4, "normal_delta_e": 20.9, "result": "PASS"},
            "note": (
                "Three light-mode hues sit below 3:1 against the light surface, so "
                "every chart ships the Markdown table view as the relief mechanism."
            ),
        },
    }
    if args.json:
        print(json.dumps(payload, indent=2))
        return 0

    print("Categorical slots (assign in this order, never cycle past slot 8):")
    for index, (light, dark) in enumerate(zip(CATEGORICAL_LIGHT, CATEGORICAL_DARK), start=1):
        print(f"  {index}  light {light}   dark {dark}")
    print("\nStatus (reserved - never reuse for a series):")
    for role, color in STATUS.items():
        print(f"  {role:9} {color}")
    print("\nValidation:")
    for key, value in payload["validation"].items():
        if key == "note":
            continue
        print(
            f"  {key:28} CVD dE {value['cvd_delta_e']}  "
            f"normal dE {value['normal_delta_e']}  {value['result']}"
        )
    print(f"\n  {payload['validation']['note']}")
    return 0


_COMMANDS = {
    "chart": cmd_chart,
    "spec": cmd_spec,
    "recommend": cmd_recommend,
    "record": cmd_record,
    "records": cmd_records,
    "compare": cmd_compare,
    "forms": cmd_forms,
    "palette": cmd_palette,
}


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if not args.command:
        parser.print_help()
        return 1

    handler = _COMMANDS[args.command]
    try:
        return handler(args)
    except (
        CollectorError,
        NormalizeError,
        RenderError,
        RasterError,
        SpecError,
        session.RecordError,
        ValueError,
    ) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
