from __future__ import annotations

import json

import pytest

from agent_charts.cli import build_parser, main


@pytest.fixture
def csv_file(tmp_path):
    path = tmp_path / "d.csv"
    path.write_text(
        "service,environment,duration_seconds\n"
        "api,staging,42\napi,production,58\n"
        "auth,staging,31\nauth,production,44\n"
    )
    return path


def test_help_lists_every_command():
    text = build_parser().format_help()
    for command in ("chart", "spec", "recommend", "record", "compare", "forms", "palette"):
        assert command in text


def test_no_command_prints_help_and_fails(capsys):
    assert main([]) == 1
    assert "usage:" in capsys.readouterr().out


def test_forms_lists_the_renderable_forms(capsys):
    assert main(["forms"]) == 0
    output = capsys.readouterr().out
    assert "bar" in output and "heatmap" in output


def test_palette_reports_its_validation(capsys):
    assert main(["palette"]) == 0
    output = capsys.readouterr().out
    assert "#2a78d6" in output
    assert "PASS" in output


def test_palette_json_is_machine_readable(capsys):
    assert main(["palette", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert len(payload["categorical_light"]) == 8


def test_chart_writes_the_full_output_set(csv_file, tmp_path):
    out = tmp_path / "out"
    code = main([
        "chart", "--data", str(csv_file), "--form", "bar",
        "--x", "service", "--y", "duration_seconds", "--series", "environment",
        "--out-dir", str(out), "--name", "deploys",
    ])
    assert code == 0
    for suffix in (".svg", ".chart.json", ".md", ".blindspots.json", ".blindspots.md"):
        assert (out / f"deploys{suffix}").exists(), suffix


def test_html_is_opt_in(csv_file, tmp_path):
    out = tmp_path / "out"
    main([
        "chart", "--data", str(csv_file), "--form", "bar", "--x", "service",
        "--y", "duration_seconds", "--out-dir", str(out), "--name", "d",
    ])
    assert not (out / "d.html").exists()

    main([
        "chart", "--data", str(csv_file), "--form", "bar", "--x", "service",
        "--y", "duration_seconds", "--out-dir", str(out), "--name", "d", "--html",
    ])
    assert (out / "d.html").exists()


def test_the_table_view_can_be_skipped_but_ships_by_default(csv_file, tmp_path):
    out = tmp_path / "out"
    main([
        "chart", "--data", str(csv_file), "--form", "bar", "--x", "service",
        "--y", "duration_seconds", "--out-dir", str(out), "--name", "d",
        "--no-markdown",
    ])
    assert not (out / "d.md").exists()


def test_auto_form_picks_a_form_and_its_columns(csv_file, tmp_path, capsys):
    out = tmp_path / "out"
    assert main([
        "chart", "--data", str(csv_file), "--auto-form",
        "--out-dir", str(out), "--name", "auto",
    ]) == 0
    assert "auto-form:" in capsys.readouterr().out
    assert (out / "auto.svg").exists()


def test_a_missing_source_is_an_error(capsys):
    assert main(["chart", "--form", "bar"]) == 2
    assert "No data source" in capsys.readouterr().err


def test_an_unknown_column_is_an_error(csv_file, tmp_path, capsys):
    code = main([
        "chart", "--data", str(csv_file), "--form", "bar",
        "--x", "nope", "--y", "duration_seconds", "--out-dir", str(tmp_path),
    ])
    assert code == 2
    assert "not in the dataset" in capsys.readouterr().err


def test_recommend_prints_advice(csv_file, capsys):
    assert main(["recommend", "--data", str(csv_file)]) == 0
    assert "chart-gen chart" in capsys.readouterr().out


def test_recommend_json_is_machine_readable(csv_file, capsys):
    assert main(["recommend", "--data", str(csv_file), "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["recommended"]
    assert payload["shape"]["row_count"] == 4


def test_record_then_chart_round_trips(tmp_path, capsys):
    records = tmp_path / "records"
    for step, seconds in (("compile", 42), ("test", 118), ("package", 17)):
        assert main([
            "record", "build", f"step={step}", f"seconds={seconds}",
            "--record-dir", str(records),
        ]) == 0

    assert main(["records", "--record-dir", str(records)]) == 0
    assert "build" in capsys.readouterr().out

    out = tmp_path / "out"
    assert main([
        "chart", "--record", "build", "--record-dir", str(records),
        "--form", "bar", "--x", "step", "--y", "seconds",
        "--out-dir", str(out), "--name", "build",
    ]) == 0
    payload = json.loads((out / "build.chart.json").read_text())
    assert [p["x"] for p in payload["series"][0]["points"]] == [
        "compile", "test", "package",
    ]


def test_reading_a_missing_record_is_an_error(tmp_path, capsys):
    assert main([
        "chart", "--record", "nope", "--record-dir", str(tmp_path), "--form", "bar",
    ]) == 2
    assert "No record named" in capsys.readouterr().err


def test_spec_renders_every_chart(tmp_path):
    spec = tmp_path / "s.yaml"
    spec.write_text(
        "charts:\n"
        "  - name: one\n"
        "    form: column\n"
        "    rows: [{x: a, v: 1}, {x: b, v: 2}]\n"
        "  - name: two\n"
        "    form: line\n"
        "    rows: [{x: a, v: 3}, {x: b, v: 4}]\n"
    )
    out = tmp_path / "out"
    assert main(["spec", str(spec), "--out-dir", str(out)]) == 0
    assert (out / "one.svg").exists()
    assert (out / "two.svg").exists()


def test_spec_validate_only_renders_nothing(tmp_path, capsys):
    spec = tmp_path / "s.yaml"
    spec.write_text("form: column\nrows: [{x: a, v: 1}]\n")
    out = tmp_path / "out"
    assert main(["spec", str(spec), "--out-dir", str(out), "--validate-only"]) == 0
    assert "spec is valid" in capsys.readouterr().out
    assert not out.exists() or not list(out.glob("*.svg"))


def test_an_invalid_spec_reports_every_problem(tmp_path, capsys):
    spec = tmp_path / "s.yaml"
    spec.write_text("form: pie\n")
    assert main(["spec", str(spec), "--out-dir", str(tmp_path)]) == 2
    error = capsys.readouterr().err
    assert "unknown form 'pie'" in error
    assert "needs 'data'" in error


def test_compare_writes_both_outputs(tmp_path, capsys):
    a = tmp_path / "a.yaml"
    b = tmp_path / "b.yaml"
    a.write_text("charts:\n  - {name: x, form: bar, rows: [{a: 1}]}\n")
    b.write_text("charts:\n  - {name: x, form: line, rows: [{a: 1}]}\n")
    out = tmp_path / "out"
    assert main(["compare", str(a), str(b), "--out-dir", str(out)]) == 0
    assert (out / "spec-compare.json").exists()
    assert (out / "spec-compare.md").exists()
    assert "changed=1" in capsys.readouterr().out


def test_blind_spots_are_written_even_for_clean_data(csv_file, tmp_path):
    out = tmp_path / "out"
    main([
        "chart", "--data", str(csv_file), "--form", "bar", "--x", "service",
        "--y", "duration_seconds", "--out-dir", str(out), "--name", "d",
    ])
    report = json.loads((out / "d.blindspots.json").read_text())
    assert report["has_blind_spots"] is False


def test_json_render_result_is_deterministic_and_lists_real_artifacts(csv_file, tmp_path, capsys):
    args = ["chart", "--data", str(csv_file), "--auto-form", "--json",
            "--out-dir", str(tmp_path / "out"), "--name", "deploys"]
    assert main(args) == 0
    first = capsys.readouterr().out
    assert main(args) == 0
    assert capsys.readouterr().out == first
    result = json.loads(first)["charts"][0]
    assert result["series_count"] == 2
    assert result["point_count"] == 4
    assert result["missing_point_count"] == 0
    assert result["blind_spots"]["has_blind_spots"] is False
    from pathlib import Path
    assert len(result["files"]) == 5
    assert all(Path(path).is_file() for path in result["files"])


def test_json_render_reports_gaps_from_piped_data(tmp_path, monkeypatch, capsys):
    import io
    monkeypatch.setattr("sys.stdin", io.StringIO('name\tn\na\t1\nb\t\nc\t3\n'))
    assert main(["chart", "--stdin", "--format", "tsv", "--form", "line",
                 "--x", "name", "--y", "n", "--json", "--out-dir", str(tmp_path)]) == 0
    result = json.loads(capsys.readouterr().out)["charts"][0]
    assert result["point_count"] == 3
    assert result["missing_point_count"] == 1
    assert result["blind_spots"]["has_blind_spots"] is True
    assert json.loads((tmp_path / "chart.chart.json").read_text())["series"][0]["points"][1]["y"] is None


@pytest.mark.parametrize("validate_only", [False, True])
def test_spec_preflights_all_sources_before_writing(tmp_path, capsys, validate_only):
    spec = tmp_path / "s.yaml"
    spec.write_text(
        "form: bar\nx: name\ny: n\ncharts:\n"
        "  - name: good\n    rows: [{name: a, n: 1}]\n"
        "  - name: missing-file\n    data: absent.csv\n"
        "  - name: bad-column\n    rows: [{name: a, n: 1}]\n    y: typo\n"
    )
    out = tmp_path / "out"
    args = ["spec", str(spec), "--out-dir", str(out)]
    assert main(args + (["--validate-only"] if validate_only else [])) == 2
    error = capsys.readouterr().err
    assert "absent.csv" in error and "typo" in error
    assert not out.exists()


def test_spec_json_is_one_document_for_multiple_charts(tmp_path, capsys):
    spec = tmp_path / "s.yaml"
    spec.write_text(
        "form: bar\nrows: [{name: a, n: 1}, {name: b, n: 2}]\n"
        "charts: [{name: one}, {name: two}]\n"
    )
    args = ["spec", str(spec), "--json", "--out-dir", str(tmp_path / "out")]
    assert main(args + ["--validate-only"]) == 0
    assert json.loads(capsys.readouterr().out)["valid"] is True
    assert main(args) == 0
    assert [c["name"] for c in json.loads(capsys.readouterr().out)["charts"]] == ["one", "two"]
