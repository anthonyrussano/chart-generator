from __future__ import annotations

import json

import pytest
import yaml

from agent_charts.spec_workflows import (
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


def _write(tmp_path, name, payload):
    path = tmp_path / name
    if name.endswith((".yaml", ".yml")):
        path.write_text(yaml.safe_dump(payload))
    else:
        path.write_text(json.dumps(payload))
    return path


def test_a_single_chart_spec_needs_no_charts_list(tmp_path):
    path = _write(tmp_path, "s.yaml", {"form": "bar", "rows": [{"a": 1}]})
    assert len(chart_specs(load_spec(path))) == 1


def test_top_level_keys_are_inherited_by_every_chart(tmp_path):
    payload = {
        "theme": "dark",
        "data": "d.csv",
        "charts": [{"form": "bar"}, {"form": "line", "theme": "light"}],
    }
    entries = chart_specs(payload)
    assert entries[0]["theme"] == "dark"
    # A chart's own key wins over the shared default.
    assert entries[1]["theme"] == "light"
    assert all(e["data"] == "d.csv" for e in entries)


def test_validation_accepts_a_good_spec():
    assert validate_spec({"form": "bar", "rows": [{"a": 1}]}) == []


def test_validation_requires_a_form():
    problems = validate_spec({"rows": [{"a": 1}]})
    assert any("'form' is required" in p for p in problems)


def test_validation_rejects_an_unknown_form():
    problems = validate_spec({"form": "pie", "rows": [{"a": 1}]})
    assert any("unknown form 'pie'" in p for p in problems)


def test_validation_requires_data():
    problems = validate_spec({"form": "bar"})
    assert any("needs 'data'" in p for p in problems)


def test_validation_catches_a_typo_in_a_key():
    problems = validate_spec({"form": "bar", "rows": [{"a": 1}], "titel": "oops"})
    assert any("unknown keys: titel" in p for p in problems)


def test_validation_checks_types():
    problems = validate_spec({"form": "bar", "rows": [{"a": 1}], "width": "wide"})
    assert any("'width' must be an integer" in p for p in problems)


def test_an_invalid_spec_file_says_so(tmp_path):
    path = tmp_path / "s.yaml"
    path.write_text("[1, 2, 3]")
    with pytest.raises(SpecError, match="mapping at the top level"):
        load_spec(path)


def test_a_missing_spec_file_says_so(tmp_path):
    with pytest.raises(SpecError, match="Cannot read"):
        load_spec(tmp_path / "nope.yaml")


def test_inline_rows_become_a_dataset(tmp_path):
    dataset = dataset_for({"rows": [{"a": 1}, {"a": 2}]}, tmp_path)
    assert len(dataset.rows) == 2


def test_a_data_path_resolves_relative_to_the_spec(tmp_path):
    (tmp_path / "d.csv").write_text("a,b\n1,2\n")
    dataset = dataset_for({"data": "d.csv"}, tmp_path)
    assert dataset.column_names() == ["a", "b"]


def test_a_chart_without_data_is_an_error(tmp_path):
    with pytest.raises(SpecError, match="needs 'data' or 'rows'"):
        dataset_for({"form": "bar"}, tmp_path)


def test_chart_names_are_filesystem_safe():
    assert chart_name({"title": "p99 latency / by endpoint"}, 0) == "p99-latency-by-endpoint"
    assert chart_name({"form": "bar"}, 2) == "bar-3"
    assert chart_name({"name": "explicit"}, 0) == "explicit"


def test_to_chart_spec_drops_data_keys():
    spec = to_chart_spec({"form": "bar", "title": "t", "data": "d.csv", "name": "n"})
    assert spec.form == "bar"
    assert spec.title == "t"


def test_to_chart_spec_requires_a_form():
    with pytest.raises(SpecError, match="'form' is required"):
        to_chart_spec({"title": "t"})


def test_counts_summarize_a_spec():
    counts = spec_counts({"charts": [{"form": "bar"}, {"form": "bar"}, {"form": "line"}]})
    assert counts == {"charts": 3, "form:bar": 2, "form:line": 1}


def test_compare_detects_added_removed_and_changed():
    current = {"charts": [{"name": "a", "form": "bar"}, {"name": "b", "form": "line"}]}
    future = {"charts": [{"name": "a", "form": "column"}, {"name": "c", "form": "line"}]}
    diff = compare_specs(current, future)
    assert diff["added"] == ["c"]
    assert diff["removed"] == ["b"]
    assert diff["changed"][0]["name"] == "a"
    assert diff["changed"][0]["changes"]["form"] == {"from": "bar", "to": "column"}


def test_compare_reports_unchanged_charts():
    spec = {"charts": [{"name": "a", "form": "bar"}]}
    assert compare_specs(spec, spec)["unchanged"] == ["a"]


def test_compare_summary_is_written(tmp_path):
    diff = compare_specs(
        {"charts": [{"name": "a", "form": "bar"}]},
        {"charts": [{"name": "a", "form": "line"}]},
    )
    text = write_compare_summary(diff, tmp_path / "c.md").read_text()
    assert "# Chart Spec Comparison" in text
    assert "`form`: 'bar' -> 'line'" in text


def test_validation_uses_shared_form_and_checks_shared_settings():
    payload = {"form": "bar", "rows": [{"a": 1}], "charts": [{"name": "a"}]}
    assert validate_spec(payload) == []
    payload["width"] = "wide"
    payload["titel"] = "typo"
    problems = validate_spec(payload)
    assert any("'width' must be an integer" in p for p in problems)
    assert any("unknown keys: titel" in p for p in problems)


@pytest.mark.parametrize("key,value", [
    ("width", True), ("height", 0), ("top_n", -1), ("theme", "dakr"),
    ("options", []), ("rows", [1]), ("target", "100"), ("baseline", float("inf")),
    ("x", ["a"]), ("data", 42), ("form", ["bar"]),
])
def test_invalid_setting_is_reported_without_crashing(key, value):
    assert validate_spec({"form": "bar", "rows": [{"a": 1}], key: value})


def test_validation_rejects_empty_dashboards_and_colliding_names():
    assert validate_spec({"charts": []})
    problems = validate_spec({"rows": [{"a": 1}], "charts": [
        {"form": "bar", "name": "API latency"},
        {"form": "line", "name": "api-latency"},
    ]})
    assert any("duplicate output name 'api-latency'" in p for p in problems)
