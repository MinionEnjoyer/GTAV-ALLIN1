"""Bounded, versioned local action journal, independent of human progress text."""
import json
import math
import uuid

from allin1.release_paths import contained, no_links, strict_json

MAX_EVENTS = 200
MAX_BYTES = 1024 * 1024


def _validate_event(row):
    # Use the same contract before writing and after reading. A cancelled launch
    # is a terminal event too; rejecting it would block every subsequent append.
    if (not isinstance(row, dict) or type(row.get("schema_version")) is not int or row["schema_version"] != 1
            or row.get("event") not in ("launcher.action.completed", "launcher.action.cancelled")
            or not isinstance(row.get("action"), str) or not isinstance(row.get("review_id"), str)
            or type(row.get("time")) not in (float, int)
            or (type(row["time"]) is float and not math.isfinite(row["time"]))):
        raise ValueError("Invalid structured activity event")


def read(root):
    path = contained(root, "logs/activity.json")
    if not path.exists(): return []
    if not path.is_file() or path.stat().st_size > MAX_BYTES:
        raise ValueError("Activity journal is not a bounded regular file")
    with path.open("rb") as stream: content = stream.read(MAX_BYTES + 1)
    if len(content) > MAX_BYTES: raise ValueError("Activity journal exceeds 1 MiB")
    data = strict_json(content)
    if not isinstance(data, dict) or type(data.get("schema_version")) is not int or data["schema_version"] != 1:
        raise ValueError("Unsupported activity journal schema")
    rows = data.get("events")
    if not isinstance(rows, list) or len(rows) > MAX_EVENTS:
        raise ValueError("Invalid activity event inventory")
    for row in rows:
        _validate_event(row)
    return rows


def append(root, event):
    _validate_event(event)
    rows = [*read(root)[-(MAX_EVENTS - 1):], event]
    target = contained(root, "logs/activity.json")
    encoded = json.dumps({"schema_version": 1, "events": rows}, indent=2, allow_nan=False) + "\n"
    if len(encoded.encode()) > MAX_BYTES: raise ValueError("Activity journal exceeds 1 MiB")
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(".activity-" + uuid.uuid4().hex + ".json")
    try:
        with temporary.open("x", encoding="utf-8") as stream: stream.write(encoded)
        temporary.replace(no_links(target))
    finally:
        temporary.unlink(missing_ok=True)
