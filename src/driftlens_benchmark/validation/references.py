"""Bounded SQL execution and a separately implemented row-based metric oracle."""

import math
import sqlite3
import time
from collections import Counter, defaultdict
from contextlib import closing
from datetime import date, datetime, timedelta
from pathlib import Path

from ..datasets.snapshots import COLUMNS, DDL


def report(value, unit):
    """Match upstream reporting, with strict result types rather than lossy count casts."""
    if value is None:
        return None
    if type(value) not in (int, float) or not math.isfinite(value):
        raise ValueError("nonfinite_query_value")
    if unit == "count":
        if type(value) is not int or not 0 <= value <= 2**63 - 1:
            raise ValueError("invalid_count_value")
        return value
    return round(value) if unit == "cents" else round(value, 4)


def scalar(path, sql):
    """Execute a single scalar SELECT under an independent SQLite read allowlist."""
    deadline = time.monotonic() + 5
    steps = 0

    def authorize(action, a, b, database, source):
        if action == sqlite3.SQLITE_SELECT:
            return sqlite3.SQLITE_OK
        if (
            action == sqlite3.SQLITE_READ
            and database in ("main", None)
            and a in COLUMNS
            and b in COLUMNS[a].split(",") + [""]
        ):
            return sqlite3.SQLITE_OK
        if action == sqlite3.SQLITE_FUNCTION and (b or "").lower() in {
            "count",
            "sum",
            "avg",
            "min",
            "max",
            "date",
            "round",
            "nullif",
            "coalesce",
            "abs",
        }:
            return sqlite3.SQLITE_OK
        return sqlite3.SQLITE_DENY

    def progress():
        nonlocal steps
        steps += 1000
        return int(time.monotonic() >= deadline or steps >= 20_000_000)

    if type(sql) is not str or len(sql) > 10000:
        raise ValueError("invalid_query")
    try:
        with closing(
            sqlite3.connect(Path(path).resolve().as_uri() + "?mode=ro", uri=True, timeout=0.05)
        ) as db:
            db.execute("PRAGMA query_only=ON")
            db.setlimit(sqlite3.SQLITE_LIMIT_LENGTH, 65536)
            db.set_authorizer(authorize)
            db.set_progress_handler(progress, 1000)
            rows = db.execute(sql).fetchmany(2)
            if len(rows) != 1 or len(rows[0]) != 1 or time.monotonic() >= deadline:
                raise ValueError("non_scalar_query")
            return rows[0][0]
    except sqlite3.Error:
        raise ValueError("query_rejected") from None


def reference(path, semantics, window):
    """Calculate from raw rows in Python, with no generated or reference SQL reuse."""
    # Validate every declared slot before calculating. Ignoring an unfamiliar
    # population or null rule would turn an unsupported definition into false
    # behavioral agreement. This grammar is independent of the SQL extractor.
    supported = {
        "grain": "order",
        "aggregation": "count_distinct",
        "population": "all",
        "measure": "order_id",
        "conditions": "none",
        "time_semantics": "week",
        "null_policy": "zero",
        "unit": "count",
    }
    if not isinstance(semantics, dict) or set(semantics) != set(supported):
        raise ValueError("unsupported_reference_meaning")
    agg, grain = semantics["aggregation"], semantics["grain"]
    if agg == "count_distinct" and grain == "order":
        population = semantics["population"]
        if not isinstance(population, str) or ":" not in population:
            raise ValueError("unsupported_reference_population")
        mode, kind = population.split(":", 1)
        if mode not in {"contains", "only"} or not kind:
            raise ValueError("unsupported_reference_population")
        supported["population"] = population
    elif agg == "count_distinct" and grain == "customer":
        supported.update(grain="customer", measure="customer_id")
        if semantics["time_semantics"] == "first_ever_in_week":
            supported["time_semantics"] = "first_ever_in_week"
        else:
            condition = semantics["conditions"]
            if not isinstance(condition, str) or not condition.startswith("min_orders:"):
                raise ValueError("unsupported_reference_threshold")
            raw = condition.removeprefix("min_orders:")
            if not raw.isascii() or not raw.isdigit() or int(raw) < 1 or str(int(raw)) != raw:
                raise ValueError("unsupported_reference_threshold")
            supported["conditions"] = condition
    elif agg == "average" and semantics["measure"] in {
        "subtotal_cents",
        "order_total_cents",
        "tax_paid_cents",
    }:
        supported.update(
            aggregation="average", measure=semantics["measure"], null_policy="empty_is_null", unit="cents"
        )
    elif agg == "ratio_of_sums":
        supported.update(
            aggregation="ratio_of_sums",
            measure="tax_paid_cents/subtotal_cents",
            null_policy="zero_denominator",
            unit="ratio",
        )
    elif agg == "relative_change":
        supported.update(
            grain="week",
            aggregation="relative_change",
            measure="subtotal_cents",
            time_semantics="week_over_week",
            null_policy="incomplete_prior_week_or_zero",
            unit="ratio",
        )
    else:
        raise ValueError("unsupported_reference_meaning")
    if semantics != supported:
        raise ValueError("unsupported_reference_meaning")
    start, end = (window[k][:10] for k in ("start", "end"))
    prior = (date.fromisoformat(start) - timedelta(days=7)).isoformat()
    with closing(sqlite3.connect(Path(path).resolve().as_uri() + "?mode=ro", uri=True)) as db:
        db.row_factory = sqlite3.Row
        orders = [dict(r) for r in db.execute("SELECT * FROM orders")]
        current = [r for r in orders if start <= r["ordered_at"] < end]
        agg = semantics["aggregation"]
        measure = semantics["measure"]
        if agg == "count_distinct" and semantics["grain"] == "order":
            kinds = defaultdict(set)
            for row in db.execute(
                "SELECT i.order_id,p.product_type FROM order_items i JOIN products p ON p.product_id=i.product_id"
            ):
                kinds[row[0]].add(row[1])
            mode, kind = semantics["population"].split(":")
            if mode not in {"contains", "only"}:
                raise ValueError("unsupported_reference_population")
            return sum(
                kind in kinds[r["order_id"]] and (mode == "contains" or kinds[r["order_id"]] == {kind})
                for r in current
            )
        if agg == "count_distinct" and semantics["grain"] == "customer":
            if semantics["time_semantics"] == "first_ever_in_week":
                first = {}
                for r in orders:
                    first[r["customer_id"]] = min(
                        first.get(r["customer_id"], r["ordered_at"]), r["ordered_at"]
                    )
                return sum(start <= stamp < end for stamp in first.values())
            prefix, n = semantics["conditions"].split(":")
            if prefix != "min_orders":
                raise ValueError("unsupported_reference_threshold")
            counts = Counter(r["customer_id"] for r in current)
            return sum(n_orders >= int(n) for n_orders in counts.values())
        if agg == "average" and measure in {"subtotal_cents", "order_total_cents", "tax_paid_cents"}:
            return sum(r[measure] for r in current) / len(current) if current else None
        if agg == "ratio_of_sums" and measure == "tax_paid_cents/subtotal_cents":
            subtotal = sum(r["subtotal_cents"] for r in current)
            return sum(r["tax_paid_cents"] for r in current) / subtotal if subtotal else None
        if agg == "relative_change" and measure == "subtotal_cents":
            old = [r for r in orders if prior <= r["ordered_at"] < start]
            previous = sum(r["subtotal_cents"] for r in old)
            # Compare instants: a first row at the prior week's midnight is
            # complete, unlike lexicographic timestamp-versus-date comparison.
            if (
                not orders
                or min(datetime.fromisoformat(r["ordered_at"]) for r in orders)
                > datetime.fromisoformat(prior)
                or not previous
                or not current
            ):
                return None
            return (sum(r["subtotal_cents"] for r in current) - previous) / previous
    raise ValueError("unsupported_reference_meaning")


def probes(directory, window):
    """Invented counterexamples cover joins, first-customer scope and empty/zero weeks."""
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=False)
    start = date.fromisoformat(window["start"][:10])
    rows = []
    for oid, cid, offset, loc, amount, tax in [
        ("old0", "a", -9, "west", 0, 0),
        ("old1", "a", -7, "west", 100, 20),
        ("old2", "b", -2, "east", 300, 15),
        ("a1", "a", 0, "east", 101, 10),
        ("a2", "a", 1, "east", 202, 40),
        ("c0", "c", 2, "west", 0, 0),
        ("d1", "d", 3, "west", 607, 30),
        ("d2", "d", 4, "west", 111, 10),
        ("e1", "e", 6, "east", 55, 20),
    ]:
        rows.append(
            (
                oid,
                cid,
                (start + timedelta(days=offset)).isoformat() + "T00:00:00",
                loc,
                amount,
                tax,
                amount + tax,
            )
        )
    items = [
        ("i1", "a1", "food"),
        ("i2", "a1", "drink"),
        ("i3", "a2", "food"),
        ("i4", "a2", "food"),
        ("i5", "d1", "drink"),
        ("i6", "d2", "food"),
        ("i7", "d2", "other"),
        ("i8", "e1", "food"),
    ]
    paths = []
    for variant in (
        "mixed",
        "empty_week",
        "zero_previous",
        "incomplete_previous",
        "prior_start_exact",
        "prior_start_late",
        "prior_start_early",
        "half_even",
        "zero_tax",
    ):
        path = directory / (variant + ".sqlite")
        chosen = rows
        if variant == "empty_week":
            chosen = [r for r in rows if r[2] < start.isoformat()]
        elif variant == "incomplete_previous":
            chosen = [r for r in rows if r[2] >= (start - timedelta(days=2)).isoformat()]
        elif variant == "zero_previous":
            chosen = [r[:4] + (0, 0, 0) if r[2] < start.isoformat() else r for r in rows]
        elif variant.startswith("prior_start_"):
            chosen = [r for r in rows if r[0] != "old0"]
            delta = {"prior_start_exact": 0, "prior_start_late": 1, "prior_start_early": -1}[variant]
            stamp = datetime.fromisoformat(chosen[0][2]) + timedelta(seconds=delta)
            chosen[0] = chosen[0][:2] + (stamp.isoformat(),) + chosen[0][3:]
        elif variant == "half_even":
            chosen = [r for r in rows if r[2] < start.isoformat()]
            chosen += [rows[3][:4] + (2, 1, 3), rows[4][:4] + (3, 2, 5)]
        elif variant == "zero_tax":
            chosen = [r[:4] + (r[4], 0, r[4]) for r in rows]
        with closing(sqlite3.connect(path)) as db:
            db.executescript(DDL)
            db.executemany("INSERT INTO orders VALUES(?,?,?,?,?,?,?)", chosen)
            db.executemany(
                "INSERT INTO products VALUES(?,?,?,?,?)",
                [
                    ("food", "food", "jaffle", 100, None),
                    ("drink", "drink", "beverage", 100, None),
                    ("other", "other", "other", 100, None),
                ],
            )
            ids = {r[0] for r in chosen}
            db.executemany("INSERT INTO order_items VALUES(?,?,?)", [r for r in items if r[1] in ids])
            db.executemany(
                "INSERT INTO locations VALUES(?,?,?,?)",
                [("west", "west", "2000-01-01", 0.1), ("east", "east", "2000-01-01", 0.2)],
            )
            db.commit()
        paths.append(path)
    return paths
