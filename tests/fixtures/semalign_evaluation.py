"""Invented eight-week source with a different changed-concept set and threshold."""

import json
import sqlite3
from copy import deepcopy
from datetime import date, timedelta

import yaml

from .semalign_source import create_source, jsonl

BASE = {
    "grain": "order",
    "aggregation": "count_distinct",
    "population": "all",
    "measure": "order_id",
    "conditions": "none",
    "time_semantics": "week",
    "null_policy": "zero",
    "unit": "count",
}
MEANINGS = {
    "sa_food_orders": {**BASE, "population": "contains:jaffle"},
    "sa_drink_orders": {**BASE, "population": "contains:beverage"},
    "sa_customers_active": {
        **BASE,
        "grain": "customer",
        "measure": "customer_id",
        "conditions": "min_orders:1",
    },
    "sa_customers_new": {
        **BASE,
        "grain": "customer",
        "measure": "customer_id",
        "time_semantics": "first_ever_in_week",
    },
    "sa_order_value_avg": {
        **BASE,
        "aggregation": "average",
        "measure": "subtotal_cents",
        "unit": "cents",
        "null_policy": "empty_is_null",
    },
    "sa_revenue_growth_wow": {
        **BASE,
        "grain": "week",
        "aggregation": "relative_change",
        "measure": "subtotal_cents",
        "unit": "ratio",
        "time_semantics": "week_over_week",
        "null_policy": "incomplete_prior_week_or_zero",
    },
    "sa_tax_rate_avg": {
        **BASE,
        "aggregation": "ratio_of_sums",
        "measure": "tax_paid_cents/subtotal_cents",
        "unit": "ratio",
        "null_policy": "zero_denominator",
    },
}


def create_evaluation_source(root):
    """Populate independent hand-countable weeks; never read private project data."""
    from driftlens_benchmark.contracts import validator

    create_source(root)
    variants = {"v1": deepcopy(MEANINGS), "v2": deepcopy(MEANINGS)}
    variants["v2"]["sa_food_orders"]["population"] = "only:jaffle"
    variants["v2"]["sa_drink_orders"]["population"] = "only:beverage"
    variants["v2"]["sa_customers_active"]["conditions"] = "min_orders:3"
    queries = {}
    window = "ordered_at >= '{s}' AND ordered_at < '{e}'"
    for version, meanings in variants.items():
        metrics = []
        for cid, slots in meanings.items():
            if cid in {"sa_food_orders", "sa_drink_orders"}:
                mode, kind = slots["population"].split(":")
                sql = "SELECT COUNT(*) FROM orders o WHERE o." + window.replace(
                    "AND ordered_at", "AND o.ordered_at"
                )
                sql += (
                    " AND EXISTS (SELECT 1 FROM order_items i JOIN products p ON i.product_id=p.product_id WHERE i.order_id=o.order_id AND p.product_type='"
                    + kind
                    + "')"
                )
                if mode == "only":
                    sql += (
                        " AND NOT EXISTS (SELECT 1 FROM order_items i JOIN products p ON i.product_id=p.product_id WHERE i.order_id=o.order_id AND p.product_type<>'"
                        + kind
                        + "')"
                    )
            elif cid == "sa_customers_active":
                minimum = int(slots["conditions"].split(":")[1])
                sql = (
                    "SELECT COUNT(*) FROM (SELECT customer_id FROM orders WHERE "
                    + window
                    + f" GROUP BY customer_id HAVING COUNT(*) >= {minimum})"
                )
            elif cid == "sa_customers_new":
                sql = "SELECT COUNT(*) FROM (SELECT customer_id,MIN(ordered_at) AS first_at FROM orders GROUP BY customer_id) WHERE first_at >= '{s}' AND first_at < '{e}'"
            elif cid == "sa_order_value_avg":
                sql = "SELECT AVG(subtotal_cents) FROM orders WHERE " + window
            elif cid == "sa_tax_rate_avg":
                sql = "SELECT SUM(tax_paid_cents)*1.0/SUM(subtotal_cents) FROM orders WHERE " + window
            else:
                sql = "SELECT CASE WHEN (SELECT MIN(ordered_at) FROM orders)>(date('{s}','-7 days') || 'T00:00:00') THEN NULL ELSE (cur-prev)*1.0/prev END FROM (SELECT SUM(CASE WHEN ordered_at >= '{s}' THEN subtotal_cents END) AS cur,SUM(CASE WHEN ordered_at < '{s}' THEN subtotal_cents END) AS prev FROM orders WHERE ordered_at >= date('{s}','-7 days') AND ordered_at < '{e}')"
            queries[version, cid] = sql
            metrics.append(
                {
                    "name": cid,
                    "label": cid,
                    "config": {
                        "meta": {
                            "concept_id": cid,
                            "unit": slots["unit"],
                            "definition": "Independent meaning: " + json.dumps(slots, sort_keys=True),
                            "oracle_sql": sql,
                        }
                    },
                }
            )
        (root / f"ontology/{version}.yml").write_text(
            yaml.safe_dump({"models": [{"name": "fixture", "metrics": metrics}]}), encoding="utf-8"
        )
        name = "semantics.v1.json" if version == "v1" else "semantics.v2.private.json"
        doc = {
            "contract_version": "semalign-meaning/v1",
            "schema": validator("semantics/v1/catalog").schema["properties"]["schema"]["const"],
            "concepts": [
                {"concept_id": cid, "semantics": slots, "required_slots": list(BASE)}
                for cid, slots in meanings.items()
            ],
        }
        (root / "ontology" / name).write_text(json.dumps(doc), encoding="utf-8")
    with sqlite3.connect(root / "data/jaffle.sqlite") as db:
        db.execute("INSERT INTO locations VALUES('s','store','2000-01-01',0.1)")
        db.executemany(
            "INSERT INTO products VALUES(?,?,?,?,?)",
            [("f", "food", "jaffle", 100, None), ("b", "drink", "beverage", 100, None)],
        )
        db.executemany(
            "INSERT INTO orders VALUES(?,?,?,?,?,?,?)",
            [
                ("old0", "loyal", "2019-12-26T00:00:00", "s", 0, 0, 0),
                ("old1", "loyal", "2019-12-30T00:00:00", "s", 100, 10, 110),
            ],
        )
        for w in range(8):
            start = date(2020, 1, 6) + timedelta(weeks=w)
            for i, amount in enumerate((100, 200, 0)):
                oid = f"w{w}o{i}"
                customer = "loyal" if i < 2 else f"new{w}"
                db.execute(
                    "INSERT INTO orders VALUES(?,?,?,?,?,?,?)",
                    (
                        oid,
                        customer,
                        (start + timedelta(days=i)).isoformat() + "T12:00:00",
                        "s",
                        amount,
                        amount // 10,
                        amount + amount // 10,
                    ),
                )
            db.executemany(
                "INSERT INTO order_items VALUES(?,?,?)",
                [
                    (f"w{w}i0", f"w{w}o0", "f"),
                    (f"w{w}i1", f"w{w}o0", "b"),
                    (f"w{w}i2", f"w{w}o1", "f"),
                    (f"w{w}i3", f"w{w}o1", "f"),
                ],
            )
        rows = [json.loads(line) for line in (root / "data/logs.L3.jsonl").read_text().splitlines()]
        truths = {
            t["log_id"]: t
            for t in [json.loads(line) for line in (root / "data/truth.jsonl").read_text().splitlines()]
        }
        for row in rows:
            rv = row["reported_values"][0]
            cid = rv["concept_id"]
            used = truths[row["log_id"]]["version_used"]
            sql = queries[used, cid].format(s=rv["window"]["start"], e=rv["window"]["end"])
            raw = db.execute(sql).fetchone()[0]
            value = (
                None
                if raw is None
                else round(raw)
                if rv["unit"] == "cents"
                else round(raw, 4)
                if rv["unit"] == "ratio"
                else raw
            )
            rv["value"] = value
            row["sql"] = sql
            row["answer_text"] = (
                "계산할 수 없습니다." if value is None else f"결과는 {value} {rv['unit']}입니다."
            )
            row["definition_note"] = "Independent meaning: " + json.dumps(variants[used][cid], sort_keys=True)
        db.commit()
    db.close()
    for level, hidden in (
        ("L0", {"sql", "definition_note"}),
        ("L1", {"definition_note"}),
        ("L2", {"sql"}),
        ("L3", set()),
    ):
        jsonl(
            root / f"data/logs.{level}.jsonl",
            [{k: None if k in hidden else v for k, v in r.items()} for r in rows],
        )
    return root
