"""Session data capture.

The use case this package exists for: an agent is working, and along the way it
learns things worth plotting - a timing, a count, a pass/fail. It should not
have to buffer those in its own context until the end.

`chart-gen record` appends one observation per call to a JSONL log. The log is
append-only and crash-safe, so a session that dies halfway still has a plottable
record. `chart-gen chart --record <name>` then reads it back.
"""

from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DEFAULT_DIR = Path("output/records")


class RecordError(RuntimeError):
    pass


def record_path(name: str, directory: Path | str = DEFAULT_DIR) -> Path:
    safe = "".join(ch if ch.isalnum() or ch in "-_." else "-" for ch in name)
    if not safe or safe.strip(".-") == "":
        raise RecordError(f"Invalid record name: {name!r}")
    return Path(directory) / f"{safe}.jsonl"


def append(
    name: str,
    fields: dict[str, Any],
    *,
    directory: Path | str = DEFAULT_DIR,
    timestamp: bool = True,
) -> Path:
    """Append one observation. Concurrent appends of a single line under the
    pipe-buffer size are atomic on POSIX, which is what makes parallel agents
    writing to one record safe."""
    path = record_path(name, directory)
    path.parent.mkdir(parents=True, exist_ok=True)

    payload: dict[str, Any] = {}
    if timestamp and "at" not in fields:
        payload["at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    payload.update(fields)

    line = json.dumps(payload, sort_keys=False, default=str) + "\n"
    with open(path, "a", encoding="utf-8") as handle:
        handle.write(line)
        handle.flush()
        os.fsync(handle.fileno())
    return path


def read(name: str, directory: Path | str = DEFAULT_DIR) -> list[dict[str, Any]]:
    path = record_path(name, directory)
    if not path.exists():
        raise RecordError(
            f"No record named '{name}' at {path}. "
            "Create one with: chart-gen record <name> key=value ..."
        )
    records: list[dict[str, Any]] = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = line.strip()
        if not line:
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError as exc:
            raise RecordError(f"{path}:{number} is not valid JSON: {exc}") from exc
    return records


def list_records(directory: Path | str = DEFAULT_DIR) -> list[tuple[str, int, Path]]:
    directory = Path(directory)
    if not directory.exists():
        return []
    out: list[tuple[str, int, Path]] = []
    for path in sorted(directory.glob("*.jsonl")):
        count = sum(1 for line in path.read_text(encoding="utf-8").splitlines() if line.strip())
        out.append((path.stem, count, path))
    return out


def clear(name: str, directory: Path | str = DEFAULT_DIR) -> Path:
    path = record_path(name, directory)
    if path.exists():
        path.unlink()
    return path


def parse_fields(pairs: list[str]) -> dict[str, Any]:
    """Parse `key=value` arguments, coercing obvious numbers and booleans."""
    fields: dict[str, Any] = {}
    for pair in pairs:
        if "=" not in pair:
            raise RecordError(f"Expected key=value, got: {pair!r}")
        key, _, raw = pair.partition("=")
        key = key.strip()
        if not key:
            raise RecordError(f"Empty key in: {pair!r}")
        fields[key] = _coerce(raw.strip())
    return fields


def _coerce(raw: str) -> Any:
    lowered = raw.lower()
    if lowered in ("true", "false"):
        return lowered == "true"
    if lowered in ("null", "none", ""):
        return None
    try:
        if "." in raw or "e" in lowered:
            return float(raw)
        return int(raw)
    except ValueError:
        return raw
