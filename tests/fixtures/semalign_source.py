"""Independent tiny source generator: invented schedules, no private repository contents."""

import json
import sqlite3
from datetime import date, timedelta
from itertools import combinations

import yaml

UNITS = {
    "sa_food_orders": "count",
    "sa_drink_orders": "count",
    "sa_customers_active": "count",
    "sa_customers_new": "count",
    "sa_order_value_avg": "cents",
    "sa_revenue_growth_wow": "ratio",
    "sa_tax_rate_avg": "ratio",
}
SCHEMA = """
CREATE TABLE orders (order_id TEXT PRIMARY KEY, customer_id TEXT, ordered_at TEXT,
    location_id TEXT, subtotal_cents INTEGER, tax_paid_cents INTEGER, order_total_cents INTEGER);
CREATE TABLE order_items (order_item_id TEXT PRIMARY KEY, order_id TEXT, product_id TEXT);
CREATE TABLE products (product_id TEXT PRIMARY KEY, product_name TEXT, product_type TEXT,
    product_price_cents INTEGER, product_description TEXT);
CREATE TABLE locations (location_id TEXT PRIMARY KEY, location_name TEXT, opened_at TEXT, tax_rate REAL);
"""


def jsonl(path, rows):
    path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")


def create_source(root):
    """Eight invented weeks exercise all metrics, label states and nullable ratios."""
    (root / "data").mkdir(parents=True)
    (root / "ontology").mkdir()
    weeks = [date(2020, 1, 6) + timedelta(weeks=k) for k in range(8)]
    plan, metrics, rows, truths = [], [], [], []
    for n, (cid, unit) in enumerate(UNITS.items()):
        effective = weeks[4] if n < 3 else None
        entry = {
            "case_id": f"fixture_{n}",
            "concept_id": cid,
            "role": "drift" if effective else "control",
            "effective_at": effective.isoformat() if effective else None,
            "difficulty": "medium" if effective else "normal",
        }
        plan.append(entry)
        metrics.append(
            {
                "name": cid,
                "label": f"Fixture {cid}",
                "config": {
                    "meta": {
                        "concept_id": cid,
                        "unit": unit,
                        "definition": f"Public definition {cid}",
                        "oracle_sql": "SELECT 1 AS value",
                    }
                },
            }
        )
        for w, start in enumerate(weeks):
            end = start + timedelta(weeks=1)
            lid = f"source_{w}_{n}"
            value = round(-0.1 * w, 4) if unit == "ratio" else w + 1
            if cid == "sa_revenue_growth_wow" and w == 0:
                value = None
            rows.append(
                {
                    "log_id": lid,
                    "timestamp": f"{end.isoformat()}T12:0{n}:00",
                    "agent_id": "fixture_agent",
                    "team": "test",
                    "request": f"Report weekly {cid}",
                    "sql": "SELECT 1 AS value",
                    "answer_text": f"Reported value: {value}",
                    "definition_note": f"Definition for {cid}",
                    "reported_values": [
                        {
                            "result_id": "r1",
                            "concept_id": cid,
                            "type": "metric_value",
                            "value": value,
                            "unit": unit,
                            "window": {"start": start.isoformat(), "end": end.isoformat()},
                            "as_of": end.isoformat(),
                        }
                    ],
                    "referenced_concepts": [cid],
                }
            )
            changed = effective is not None and start >= effective
            truths.append(
                {
                    "log_id": lid,
                    "concept_id": cid,
                    "version_used": "v2" if changed else "v1",
                    "drift_id": entry["case_id"],
                    "effective_at": entry["effective_at"],
                    "is_control": effective is None,
                    "contaminated": changed,
                    "validation_status": "executed_on_source_csv",
                }
            )
    for version in ("v1", "v2"):
        (root / f"ontology/{version}.yml").write_text(
            yaml.safe_dump({"models": [{"name": "orders", "metrics": metrics}]}), encoding="utf-8"
        )
    event = weeks[5]
    (root / "ontology/scenario.private.yml").write_text(
        yaml.safe_dump(
            {
                "period": {
                    "start": weeks[0].isoformat(),
                    "end": (weeks[-1] + timedelta(weeks=1)).isoformat(),
                },
                "concepts": plan,
                "events": [{"week": event.isoformat(), "name": "fixture_event"}],
            }
        ),
        encoding="utf-8",
    )
    rows.sort(key=lambda r: r["timestamp"])
    for level, hidden in {
        "L0": {"sql", "definition_note"},
        "L1": {"definition_note"},
        "L2": {"sql"},
        "L3": set(),
    }.items():
        jsonl(
            root / f"data/logs.{level}.jsonl",
            [{k: None if k in hidden else v for k, v in row.items()} for row in rows],
        )
    jsonl(root / "data/truth.jsonl", truths)
    pairs, pair_truth = [], []
    for n, entry in enumerate(plan):
        effective = date.fromisoformat(entry["effective_at"]) if entry["effective_at"] else None
        candidates = list(combinations(range(8), 2))
        positive = [
            (a, b) for a, b in candidates if effective is not None and weeks[a] < effective <= weeks[b]
        ]
        negative = [p for p in candidates if p not in positive]
        selected = positive[:8] + negative[:8] if effective else negative[:16]
        for a, b in selected:
            pair = {
                "pair_id": f"pair_{len(pairs):03d}",
                "concept_id": entry["concept_id"],
                "log_a": f"source_{a}_{n}",
                "log_b": f"source_{b}_{n}",
            }
            changed = (a, b) in positive
            spans = weeks[a] < event <= weeks[b]
            pairs.append(pair)
            pair_truth.append(
                {
                    **pair,
                    "case_id": entry["case_id"],
                    "is_control": effective is None,
                    "changed": changed,
                    "spans_event": spans,
                    "hard_negative": spans and not changed,
                }
            )
    jsonl(root / "data/pairs.jsonl", pairs)
    jsonl(root / "data/pairs_truth.jsonl", pair_truth)
    (root / "schema.sql").write_text(SCHEMA, encoding="utf-8")
    db = sqlite3.connect(root / "data/jaffle.sqlite")
    try:
        db.executescript(SCHEMA)
    finally:
        db.close()
    return root
