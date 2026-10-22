"""Bounded SQLite capability for reference and submitted SQL; no generator connection exposed."""

import sqlite3
import time
from pathlib import Path


def query(path, sql, parameters=(), *, max_rows=100, max_steps=100000, timeout=2):
    if type(sql) is not str or not sql.strip() or len(sql) > 10000:
        raise ValueError("invalid_query")
    deadline = time.monotonic() + timeout
    steps = 0

    def progress():
        nonlocal steps
        steps += 100
        return int(steps >= max_steps or time.monotonic() >= deadline)

    def authorize(action, arg1, arg2, database, source):
        if action == sqlite3.SQLITE_SELECT:
            return sqlite3.SQLITE_OK
        if (
            action == sqlite3.SQLITE_READ
            and arg1 == "orders"
            and source is None
            and database in ("main", None)
            and arg2 in ("", "order_id", "ordered_at", "order_total_cents")
        ):
            return sqlite3.SQLITE_OK
        if action == sqlite3.SQLITE_FUNCTION and (arg2 or "").lower() == "count":
            return sqlite3.SQLITE_OK
        return sqlite3.SQLITE_DENY

    try:
        db = sqlite3.connect(Path(path).resolve().as_uri() + "?mode=ro", uri=True, timeout=0.05)
        try:
            db.execute("PRAGMA query_only=ON")
            db.setlimit(sqlite3.SQLITE_LIMIT_LENGTH, 65536)
            db.set_authorizer(authorize)
            db.set_progress_handler(progress, 100)
            cursor = db.execute(sql, parameters)
            rows = cursor.fetchmany(max_rows + 1)
            if len(rows) > max_rows or time.monotonic() >= deadline:
                raise ValueError("query_budget_exceeded")
            return rows
        finally:
            db.close()
    except sqlite3.Error:
        raise ValueError("query_rejected") from None


def count(path, sql, parameters=()):
    rows = query(path, sql, parameters, max_rows=1)
    if len(rows) != 1 or len(rows[0]) != 1 or type(rows[0][0]) is not int or rows[0][0] < 0:
        raise ValueError("invalid_count_result")
    return rows[0][0]
