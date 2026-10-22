"""Explicit read-only validator for original public v1 logs; no invented v2 truth migration."""

from datetime import datetime, timezone

from ..artifacts import read_jsonl, unique
from . import validate, week


def load_legacy(path):
    rows = unique([validate("records/v1/observation", row) for row in read_jsonl(path)])
    for row in rows:
        timestamp = datetime.fromisoformat(row["timestamp"]).astimezone(timezone.utc)
        if timestamp != datetime.fromisoformat(week(row["reported_values"][0]["period"])[2]):
            raise ValueError("legacy_period_mismatch")
    return rows
