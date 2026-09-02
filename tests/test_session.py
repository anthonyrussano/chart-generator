from __future__ import annotations

import json

import pytest

from agent_charts import session


def test_append_writes_one_json_line(tmp_path):
    session.append("run", {"step": "compile", "seconds": 42}, directory=tmp_path)
    session.append("run", {"step": "test", "seconds": 118}, directory=tmp_path)

    lines = (tmp_path / "run.jsonl").read_text().strip().splitlines()
    assert len(lines) == 2
    assert json.loads(lines[0])["step"] == "compile"


def test_a_timestamp_is_added_by_default(tmp_path):
    session.append("run", {"n": 1}, directory=tmp_path)
    assert "at" in session.read("run", tmp_path)[0]


def test_a_supplied_timestamp_is_not_overwritten(tmp_path):
    session.append("run", {"at": "2026-01-01", "n": 1}, directory=tmp_path)
    assert session.read("run", tmp_path)[0]["at"] == "2026-01-01"


def test_timestamps_can_be_turned_off(tmp_path):
    session.append("run", {"n": 1}, directory=tmp_path, timestamp=False)
    assert "at" not in session.read("run", tmp_path)[0]


def test_reading_a_missing_record_says_how_to_create_one(tmp_path):
    with pytest.raises(session.RecordError, match="chart-gen record"):
        session.read("nope", tmp_path)


def test_a_corrupt_line_names_its_line_number(tmp_path):
    path = tmp_path / "run.jsonl"
    path.write_text('{"a": 1}\nbroken\n')
    with pytest.raises(session.RecordError, match=r"run.jsonl:2"):
        session.read("run", tmp_path)


def test_listing_counts_observations(tmp_path):
    session.append("a", {"n": 1}, directory=tmp_path)
    session.append("a", {"n": 2}, directory=tmp_path)
    session.append("b", {"n": 3}, directory=tmp_path)
    assert session.list_records(tmp_path) == [
        ("a", 2, tmp_path / "a.jsonl"),
        ("b", 1, tmp_path / "b.jsonl"),
    ]


def test_listing_a_missing_directory_is_empty(tmp_path):
    assert session.list_records(tmp_path / "nope") == []


def test_clear_removes_the_record(tmp_path):
    session.append("a", {"n": 1}, directory=tmp_path)
    session.clear("a", tmp_path)
    assert session.list_records(tmp_path) == []


def test_a_record_name_cannot_escape_its_directory(tmp_path):
    path = session.record_path("../../etc/passwd", tmp_path)
    assert path.parent == tmp_path


def test_an_empty_record_name_is_rejected(tmp_path):
    with pytest.raises(session.RecordError):
        session.record_path("...", tmp_path)


@pytest.mark.parametrize(
    "pair,expected",
    [
        ("n=42", 42),
        ("n=4.5", 4.5),
        ("ok=true", True),
        ("ok=false", False),
        ("v=null", None),
        ("s=hello", "hello"),
        ("s=1.2.3", "1.2.3"),
    ],
)
def test_fields_coerce_the_obvious_types(pair, expected):
    assert list(session.parse_fields([pair]).values())[0] == expected


def test_a_field_without_an_equals_sign_is_rejected():
    with pytest.raises(session.RecordError, match="key=value"):
        session.parse_fields(["broken"])


def test_a_value_containing_equals_is_preserved():
    assert session.parse_fields(["q=a=b"])["q"] == "a=b"
