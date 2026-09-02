from __future__ import annotations

from pathlib import Path

import pytest

from agent_charts.model import ChartSpec, Column, DataSet

SNAPSHOT_DIR = Path(__file__).parent / "snapshots"


@pytest.fixture
def simple_dataset() -> DataSet:
    return DataSet(
        columns=[
            Column("service", "category"),
            Column("environment", "category"),
            Column("duration_seconds", "number"),
        ],
        rows=[
            {"service": "api", "environment": "staging", "duration_seconds": 42.0},
            {"service": "api", "environment": "production", "duration_seconds": 58.0},
            {"service": "auth", "environment": "staging", "duration_seconds": 31.0},
            {"service": "auth", "environment": "production", "duration_seconds": 44.0},
        ],
        metadata={"source": "test", "origin": "<fixture>", "row_count": 4},
    )


@pytest.fixture
def time_dataset() -> DataSet:
    return DataSet(
        columns=[
            Column("minute", "time"),
            Column("p50_ms", "number"),
            Column("p99_ms", "number"),
        ],
        rows=[
            {"minute": "2026-09-02T09:00", "p50_ms": 42.0, "p99_ms": 180.0},
            {"minute": "2026-09-02T09:05", "p50_ms": 44.0, "p99_ms": 195.0},
            {"minute": "2026-09-02T09:10", "p50_ms": 41.0, "p99_ms": 172.0},
        ],
        metadata={"source": "test", "origin": "<fixture>", "row_count": 3},
    )


@pytest.fixture
def bar_spec() -> ChartSpec:
    return ChartSpec(
        form="bar",
        title="Deploy duration",
        x="service",
        y="duration_seconds",
        series="environment",
        unit="s",
    )


@pytest.fixture
def snapshot():
    """Compare against a golden file, writing it when UPDATE_SNAPSHOTS is set."""
    import os

    def _compare(name: str, actual: str) -> None:
        path = SNAPSHOT_DIR / name
        if os.environ.get("UPDATE_SNAPSHOTS"):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(actual, encoding="utf-8")
            return
        assert path.exists(), (
            f"Missing snapshot {path}. Create it with: UPDATE_SNAPSHOTS=1 pytest"
        )
        expected = path.read_text(encoding="utf-8")
        assert actual == expected, f"Output drifted from snapshot {name}"

    return _compare
