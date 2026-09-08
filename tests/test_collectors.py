from __future__ import annotations

import json
import sqlite3

import pytest

from agent_charts.collectors import (
    CollectorError,
    coerce_number,
    collect,
    collect_from_csv,
    collect_from_inline,
    collect_from_json,
    collect_from_jsonl,
    collect_from_sqlite,
    collect_from_text,
    detect_format,
    infer_kind,
)


def test_csv_infers_column_kinds(tmp_path):
    path = tmp_path / "data.csv"
    path.write_text("service,count,day\napi,4,2026-09-01\nauth,7,2026-09-02\n")
    dataset = collect_from_csv(path)
    kinds = {c.name: c.kind for c in dataset.columns}
    assert kinds == {"service": "category", "count": "number", "day": "time"}
    assert dataset.rows[0]["count"] == 4.0


def test_csv_without_a_header_is_an_error(tmp_path):
    path = tmp_path / "empty.csv"
    path.write_text("")
    with pytest.raises(CollectorError, match="no header"):
        collect_from_csv(path)


def test_tsv_uses_tab_delimiter(tmp_path):
    path = tmp_path / "data.tsv"
    path.write_text("a\tb\n1\t2\n")
    dataset = collect(path)
    assert dataset.column_names() == ["a", "b"]


@pytest.mark.parametrize(
    "raw,expected",
    [("1,234", 1234.0), ("45%", 45.0), ("$12.50", 12.5), ("1_000", 1000.0),
     ("-3", -3.0), ("1e3", 1000.0)],
)
def test_coerce_number_accepts_the_shapes_agents_emit(raw, expected):
    assert coerce_number(raw) == expected


@pytest.mark.parametrize("raw", ["", "n/a", "abc", None, True])
def test_coerce_number_refuses_to_guess(raw):
    assert coerce_number(raw) is None


def test_a_bare_year_reads_as_a_number_not_a_time():
    # It is both; numbers win so the column stays plottable on a value axis.
    assert infer_kind(["2024", "2025"]) == "number"


def test_json_accepts_a_list_of_objects(tmp_path):
    path = tmp_path / "d.json"
    path.write_text(json.dumps([{"a": 1}, {"a": 2}]))
    assert len(collect_from_json(path).rows) == 2


def test_json_accepts_a_name_value_mapping(tmp_path):
    path = tmp_path / "d.json"
    path.write_text(json.dumps({"api": 4, "auth": 7}))
    dataset = collect_from_json(path)
    assert dataset.column_names() == ["name", "value"]
    assert dataset.rows[0] == {"name": "api", "value": 4.0}


def test_json_accepts_a_wrapped_rows_key(tmp_path):
    path = tmp_path / "d.json"
    path.write_text(json.dumps({"rows": [{"a": 1}], "meta": "ignored"}))
    assert collect_from_json(path).rows == [{"a": 1.0}]


def test_json_accepts_a_series_mapping(tmp_path):
    path = tmp_path / "d.json"
    path.write_text(json.dumps({"api": [1, 2], "auth": [3, 4]}))
    dataset = collect_from_json(path)
    assert dataset.column_names() == ["series", "index", "value"]
    assert len(dataset.rows) == 4


def test_json_accepts_a_bare_scalar_list(tmp_path):
    path = tmp_path / "d.json"
    path.write_text(json.dumps([5, 6, 7]))
    dataset = collect_from_json(path)
    assert dataset.column_names() == ["index", "value"]


def test_jsonl_reports_the_offending_line(tmp_path):
    path = tmp_path / "d.jsonl"
    path.write_text('{"a": 1}\nnot json\n')
    with pytest.raises(CollectorError, match=r":2"):
        collect_from_jsonl(path)


def test_jsonl_skips_blank_lines(tmp_path):
    path = tmp_path / "d.jsonl"
    path.write_text('{"a": 1}\n\n{"a": 2}\n')
    assert len(collect_from_jsonl(path).rows) == 2


def test_ragged_records_are_squared_off(tmp_path):
    path = tmp_path / "d.jsonl"
    path.write_text('{"a": 1}\n{"b": 2}\n')
    dataset = collect_from_jsonl(path)
    assert dataset.column_names() == ["a", "b"]
    # A field a record did not carry stays None - never invented as 0.
    assert dataset.rows[0]["b"] is None


def test_sqlite_reads_a_query(tmp_path):
    path = tmp_path / "d.db"
    connection = sqlite3.connect(path)
    connection.execute("CREATE TABLE t (name TEXT, n INTEGER)")
    connection.executemany("INSERT INTO t VALUES (?, ?)", [("a", 1), ("b", 2)])
    connection.commit()
    connection.close()

    dataset = collect_from_sqlite(path, "SELECT name, n FROM t ORDER BY name")
    assert dataset.rows == [{"name": "a", "n": 1.0}, {"name": "b", "n": 2.0}]


def test_sqlite_requires_a_query(tmp_path):
    path = tmp_path / "d.db"
    sqlite3.connect(path).close()
    with pytest.raises(CollectorError, match="query is required"):
        collect(path)


def test_text_autodetects_json_versus_csv():
    assert collect_from_text('[{"a": 1}]').metadata["source"] == "json"
    assert collect_from_text("a,b\n1,2\n").metadata["source"] == "csv"


def test_inline_rows_require_objects():
    assert collect_from_inline([{"a": 1}]).rows == [{"a": 1.0}]
    with pytest.raises(CollectorError, match="list of objects"):
        collect_from_inline([1, 2])


def test_unknown_suffix_names_the_supported_formats():
    with pytest.raises(CollectorError, match="Pass --format"):
        detect_format("data.xlsx")


@pytest.mark.parametrize("fmt,text", [
    ("jsonl", '{"name":"api","n":4}\n{"name":"auth","n":null}\n'),
    ("yaml", '- name: api\n  n: 4\n- name: auth\n  n: null\n'),
    ("tsv", 'name\tn\napi\t4\nauth\t\n'),
])
def test_text_and_file_collectors_agree(tmp_path, fmt, text):
    path = tmp_path / f"data.{fmt}"
    path.write_text(text)
    assert collect_from_text(text, fmt=fmt).rows == collect(path).rows
    assert collect_from_text(text, fmt=fmt).rows[1]["n"] is None


def test_piped_jsonl_is_detected_automatically():
    dataset = collect_from_text('{"n":1}\n\n{"n":2}\n')
    assert dataset.metadata["source"] == "jsonl"
    assert dataset.rows == [{"n": 1.0}, {"n": 2.0}]


@pytest.mark.parametrize("text,fmt,message", [
    ('{"n":1}\n[2]\n', "jsonl", r":2 is not a JSON object"),
    ('\n{"n":1}\nnope', "jsonl", r":3 is not valid JSON"),
    ('[{"n":1},]', "auto", "not valid JSON"),
    ('n\n1\n', "typo", "Unsupported text format"),
    ('   ', "auto", "no data received"),
    ('n,n\n1,2\n', "csv", "duplicate column names"),
    ('n,\n1,2\n', "csv", "empty column name"),
    ('n\n1,2\n', "csv", "more cells than the header"),
])
def test_invalid_text_has_actionable_errors(text, fmt, message):
    with pytest.raises(CollectorError, match=message):
        collect_from_text(text, fmt=fmt)


def test_csv_preserves_quoted_newlines_and_handles_bom(tmp_path):
    text = '\ufeffname,n\n"api\nworker",4\nauth\n'
    path = tmp_path / "data.csv"
    path.write_text(text)
    for dataset in (collect(path), collect_from_text(text)):
        assert dataset.rows == [{"name": "api\nworker", "n": 4.0}, {"name": "auth", "n": None}]
