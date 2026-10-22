import json
import sqlite3
from datetime import date

import pytest

from driftlens_benchmark.contracts import week
from driftlens_benchmark.environments.build import load_orders, snapshot
from driftlens_benchmark.environments.sql import count, query
from driftlens_benchmark.settings import load_suite


def test_fixture_oracles_and_exact_schema(root, tmp_path):
    suite = load_suite(root / "benchmarks/suites/smoke.yaml")
    rows = load_orders(suite.orders)
    path = tmp_path / "orders.sqlite"
    snapshot(rows, suite.schema, path, "2025-01-20")
    expected = {"2025-W02": (3, 1), "2025-W03": (4, 2)}
    for period, values in expected.items():
        start, end, _ = week(period)
        assert (
            tuple(
                count(path, sql, {"start": str(start), "end": str(end)}) for sql in suite.references.values()
            )
            == values
        )
    with sqlite3.connect(path) as db:
        assert [(r[1], r[2]) for r in db.execute("PRAGMA table_info(orders)")] == [
            ("order_id", "TEXT"),
            ("ordered_at", "TEXT"),
            ("order_total_cents", "INTEGER"),
        ]
    with pytest.raises(ValueError):
        snapshot(rows, suite.schema, path, "2025-01-20")


def test_snapshot_cutoff_and_historical_rows(root, tmp_path):
    suite = load_suite(root / "benchmarks/suites/smoke.yaml")
    rows = load_orders(suite.orders)
    path = tmp_path / "cutoff.sqlite"
    snapshot(rows, suite.schema, path, "2025-01-13")
    assert count(path, "SELECT COUNT(*) FROM orders") == 4
    assert count(path, "SELECT COUNT(*) FROM orders WHERE ordered_at >= '2025-01-13'") == 0


def test_timezone_iso_year_and_jsonl_csv_equivalence(root, tmp_path):
    path = tmp_path / "orders.jsonl"
    rows = [
        {"id": str(i), "ordered_at": stamp, "order_total": 2000}
        for i, stamp in enumerate(
            ["2024-12-30T00:30:00+01:00", "2024-12-30T00:00:00Z", "2025-01-05T23:59:59Z"]
        )
    ]
    path.write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")
    assert [r[1] for r in load_orders(path)] == ["2024-12-29", "2024-12-30", "2025-01-05"]
    assert week("2025-W01") == (date(2024, 12, 30), date(2025, 1, 6), "2025-01-05T23:59:59Z")
    import csv

    source = root / "datasets/jaffle_shop/fixtures/orders.csv"
    with source.open() as stream:
        path.write_text("\n".join(json.dumps(r) for r in csv.DictReader(stream)), encoding="utf-8")
    assert load_orders(path) == load_orders(source)


@pytest.mark.parametrize("amount", ["NaN", "Infinity", "2.5", True, 2**64])
def test_invalid_cents(amount, tmp_path):
    path = tmp_path / "bad.jsonl"
    path.write_text(
        json.dumps({"id": "x", "ordered_at": "2025-01-01", "order_total": amount}), encoding="utf-8"
    )
    with pytest.raises(ValueError):
        load_orders(path)


@pytest.mark.parametrize(
    "sql",
    [
        "DELETE FROM orders",
        "PRAGMA table_info(orders)",
        "SELECT * FROM sqlite_master",
        "SELECT 1; SELECT 2",
        "ATTACH DATABASE ':memory:' AS other",
        "SELECT load_extension('x')",
        "SELECT * FROM orders",
    ],
)
def test_readonly_limits(root, tmp_path, sql):
    suite = load_suite(root / "benchmarks/suites/smoke.yaml")
    path = tmp_path / "ro.sqlite"
    snapshot(load_orders(suite.orders), suite.schema, path, "2025-01-20")
    with pytest.raises(ValueError):
        query(path, sql, max_rows=1)
    assert count(path, "SELECT COUNT(*) FROM orders") == 8
