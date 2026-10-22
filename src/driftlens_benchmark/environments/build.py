"""Normalize cents and UTC dates, then materialize per-report agent-v1 snapshots."""

import csv
import sqlite3
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path

from ..artifacts import read_jsonl


def load_orders(path):
    path = Path(path)
    if path.suffix == ".jsonl":
        source = read_jsonl(path)
    else:
        with path.open(encoding="utf-8-sig", newline="") as stream:
            source = list(csv.DictReader(stream))
    rows, seen = [], set()
    for row in source:
        try:
            if not isinstance(row, dict) or not {"id", "ordered_at", "order_total"} <= row.keys():
                raise ValueError
            identifier = row["id"]
            if not isinstance(identifier, str) or not identifier.strip() or identifier in seen:
                raise ValueError
            amount = Decimal(str(row["order_total"]))
            if not amount.is_finite() or amount != amount.to_integral_value() or abs(amount) > 2**63 - 1:
                raise ValueError
            stamp = datetime.fromisoformat(row["ordered_at"].replace("Z", "+00:00"))
            stamp = (
                stamp.replace(tzinfo=timezone.utc) if stamp.tzinfo is None else stamp.astimezone(timezone.utc)
            )
            rows.append((identifier, stamp.date().isoformat(), int(amount)))
            seen.add(identifier)
        except (ValueError, TypeError, AttributeError, InvalidOperation, OverflowError):
            raise ValueError("invalid_order_row") from None
    if not rows:
        raise ValueError("empty_dataset")
    return sorted(rows)


def snapshot(rows, schema, path, end):
    """Keep all historical rows before the exclusive weekly end; never expose future orders."""
    path = Path(path)
    if path.exists():
        raise ValueError("snapshot_already_exists")
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path)
    try:
        db.executescript(Path(schema).read_text(encoding="utf-8"))
        db.executemany("INSERT INTO orders VALUES (?, ?, ?)", [r for r in rows if r[1] < end])
        db.commit()
        columns = [(r[1], r[2]) for r in db.execute("PRAGMA table_info(orders)")]
        if columns != [("order_id", "TEXT"), ("ordered_at", "TEXT"), ("order_total_cents", "INTEGER")]:
            raise ValueError("invalid_agent_v1_schema")
    finally:
        db.close()
