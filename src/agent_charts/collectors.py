"""Data collection adapters.

Each collector is independent and returns a DataSet. None of them invent
values: a cell that could not be parsed becomes None and is reported as a blind
spot rather than silently coerced to zero.
"""

from __future__ import annotations

import csv
import json
import re
import sqlite3
import sys
from pathlib import Path
from typing import Any, Iterable

import yaml

from .model import Column, DataSet

# Recognized time formats, most specific first. A column is 'time' only when
# every non-null cell parses; otherwise it stays a category.
_TIME_PATTERNS = (
    re.compile(r"^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}(:\d{2})?"),
    re.compile(r"^\d{4}-\d{2}-\d{2}$"),
    re.compile(r"^\d{4}-\d{2}$"),
    re.compile(r"^\d{4}$"),
)

_NUMBER_RE = re.compile(r"^-?\d+(\.\d+)?([eE][-+]?\d+)?$")


class CollectorError(RuntimeError):
    """Raised when a source exists but cannot be read as tabular data."""


def coerce_number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if not isinstance(value, str):
        return None
    text = value.strip().replace(",", "")
    # Accept the shapes agents actually emit: 1_234, 45%, $12.50.
    text = text.replace("_", "")
    if text.endswith("%"):
        text = text[:-1]
    if text.startswith(("$", "£", "€")):
        text = text[1:]
    if not text or not _NUMBER_RE.match(text):
        return None
    return float(text)


def _looks_like_time(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    return any(p.match(value.strip()) for p in _TIME_PATTERNS)


def infer_kind(values: Iterable[Any]) -> str:
    """Classify a column as number, time, or category."""
    present = [v for v in values if v is not None and v != ""]
    if not present:
        return "category"
    # A bare year is both a number and a time; numbers win so it stays plottable.
    if all(coerce_number(v) is not None for v in present):
        return "number"
    if all(_looks_like_time(v) for v in present):
        return "time"
    return "category"


def _dataset_from_records(
    records: list[dict[str, Any]], source: str, origin: str
) -> DataSet:
    names: list[str] = []
    for record in records:
        for key in record:
            if key not in names:
                names.append(key)

    rows = [{name: record.get(name) for name in names} for record in records]
    columns = [Column(name=n, kind=infer_kind(r.get(n) for r in rows)) for n in names]

    # Normalize numeric cells once, here, so downstream code never re-parses.
    for column in columns:
        if column.kind == "number":
            for row in rows:
                row[column.name] = coerce_number(row[column.name])

    return DataSet(
        columns=columns,
        rows=rows,
        metadata={"source": source, "origin": origin, "row_count": len(rows)},
    )


def collect_from_csv(path: str | Path, delimiter: str = ",") -> DataSet:
    path = Path(path)
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise CollectorError(f"csv: cannot read {path}: {exc}") from exc
    reader = csv.DictReader(text.splitlines(), delimiter=delimiter)
    if reader.fieldnames is None:
        raise CollectorError(f"csv: {path} has no header row")
    records = [dict(row) for row in reader]
    return _dataset_from_records(records, "csv", str(path))


def collect_from_json(path: str | Path) -> DataSet:
    path = Path(path)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CollectorError(f"json: cannot read {path}: {exc}") from exc
    return _dataset_from_records(_records_from_payload(payload, str(path)), "json", str(path))


def collect_from_jsonl(path: str | Path) -> DataSet:
    """Read newline-delimited JSON - the shape `chart-gen record` appends to."""
    path = Path(path)
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise CollectorError(f"jsonl: cannot read {path}: {exc}") from exc

    records: list[dict[str, Any]] = []
    for number, line in enumerate(lines, start=1):
        line = line.strip()
        if not line:
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError as exc:
            raise CollectorError(f"jsonl: {path}:{number} is not valid JSON: {exc}") from exc
        if not isinstance(record, dict):
            raise CollectorError(f"jsonl: {path}:{number} is not a JSON object")
        records.append(record)
    return _dataset_from_records(records, "jsonl", str(path))


def collect_from_yaml(path: str | Path) -> DataSet:
    path = Path(path)
    try:
        payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise CollectorError(f"yaml: cannot read {path}: {exc}") from exc
    return _dataset_from_records(_records_from_payload(payload, str(path)), "yaml", str(path))


def collect_from_sqlite(path: str | Path, query: str) -> DataSet:
    path = Path(path)
    if not path.exists():
        raise CollectorError(f"sqlite: database not found: {path}")
    try:
        connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    except sqlite3.Error as exc:
        raise CollectorError(f"sqlite: cannot open {path}: {exc}") from exc
    try:
        connection.row_factory = sqlite3.Row
        cursor = connection.execute(query)
        records = [dict(row) for row in cursor.fetchall()]
    except sqlite3.Error as exc:
        raise CollectorError(f"sqlite: query failed on {path}: {exc}") from exc
    finally:
        connection.close()
    return _dataset_from_records(records, "sqlite", f"{path}?{query}")


def collect_from_stdin(fmt: str = "auto") -> DataSet:
    """Read a dataset piped in by the calling agent."""
    text = sys.stdin.read()
    if not text.strip():
        raise CollectorError("stdin: no data received")
    return collect_from_text(text, fmt=fmt, origin="<stdin>")


def collect_from_text(text: str, fmt: str = "auto", origin: str = "<text>") -> DataSet:
    stripped = text.strip()
    if fmt == "auto":
        fmt = "json" if stripped[:1] in "[{" else "csv"

    if fmt == "json":
        try:
            payload = json.loads(stripped)
        except json.JSONDecodeError as exc:
            raise CollectorError(f"{origin}: not valid JSON: {exc}") from exc
        return _dataset_from_records(_records_from_payload(payload, origin), "json", origin)

    if fmt == "jsonl":
        records = []
        for number, line in enumerate(stripped.splitlines(), start=1):
            if not line.strip():
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise CollectorError(f"{origin}:{number} is not valid JSON: {exc}") from exc
        return _dataset_from_records(records, "jsonl", origin)

    reader = csv.DictReader(stripped.splitlines())
    if reader.fieldnames is None:
        raise CollectorError(f"{origin}: no header row")
    return _dataset_from_records([dict(r) for r in reader], "csv", origin)


def collect_from_inline(rows: list[dict[str, Any]]) -> DataSet:
    """Build a DataSet from rows embedded directly in a chart spec."""
    if not isinstance(rows, list) or not all(isinstance(r, dict) for r in rows):
        raise CollectorError("inline: 'rows' must be a list of objects")
    return _dataset_from_records(rows, "inline", "<spec>")


def _records_from_payload(payload: Any, origin: str) -> list[dict[str, Any]]:
    """Accept the several shapes agents naturally produce."""
    if isinstance(payload, list):
        if all(isinstance(item, dict) for item in payload):
            return payload
        # A bare list of scalars is a single unnamed series.
        return [{"index": i, "value": v} for i, v in enumerate(payload)]

    if isinstance(payload, dict):
        # {"rows": [...]} / {"data": [...]} / {"records": [...]}
        for key in ("rows", "data", "records", "items", "results"):
            value = payload.get(key)
            if isinstance(value, list):
                return _records_from_payload(value, origin)
        # {"a": 1, "b": 2} is a name/value mapping.
        if all(not isinstance(v, (dict, list)) for v in payload.values()):
            return [{"name": k, "value": v} for k, v in payload.items()]
        # {"series-a": [...], "series-b": [...]}
        records: list[dict[str, Any]] = []
        for name, value in payload.items():
            if isinstance(value, list):
                for index, item in enumerate(value):
                    if isinstance(item, dict):
                        records.append({"series": name, **item})
                    else:
                        records.append({"series": name, "index": index, "value": item})
        if records:
            return records

    raise CollectorError(f"{origin}: could not read a table out of this structure")


COLLECTORS = {
    "csv": collect_from_csv,
    "json": collect_from_json,
    "jsonl": collect_from_jsonl,
    "yaml": collect_from_yaml,
}

_SUFFIX_FORMATS = {
    ".csv": "csv",
    ".tsv": "csv",
    ".json": "json",
    ".jsonl": "jsonl",
    ".ndjson": "jsonl",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".db": "sqlite",
    ".sqlite": "sqlite",
    ".sqlite3": "sqlite",
}


def detect_format(path: str | Path) -> str:
    suffix = Path(path).suffix.lower()
    fmt = _SUFFIX_FORMATS.get(suffix)
    if fmt is None:
        raise CollectorError(
            f"Cannot infer a format from '{suffix or path}'. "
            f"Pass --format with one of: {', '.join(sorted(set(_SUFFIX_FORMATS.values())))}."
        )
    return fmt


def collect(path: str | Path, fmt: str = "auto", query: str | None = None) -> DataSet:
    """Front door: read any supported source into a DataSet."""
    if fmt == "auto":
        fmt = detect_format(path)
    if fmt == "sqlite":
        if not query:
            raise CollectorError("sqlite: --query is required")
        return collect_from_sqlite(path, query)
    if fmt == "csv" and Path(path).suffix.lower() == ".tsv":
        return collect_from_csv(path, delimiter="\t")
    collector = COLLECTORS.get(fmt)
    if collector is None:
        raise CollectorError(f"Unsupported format '{fmt}'")
    return collector(path)
