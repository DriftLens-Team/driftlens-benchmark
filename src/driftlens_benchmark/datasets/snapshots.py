"""Build new private snapshots containing historical orders but no future rows."""

import sqlite3
from contextlib import closing
from pathlib import Path

from ..artifacts import digest

DDL = """
CREATE TABLE orders(order_id TEXT PRIMARY KEY NOT NULL,customer_id TEXT NOT NULL,ordered_at TEXT NOT NULL,
location_id TEXT NOT NULL,subtotal_cents INTEGER NOT NULL,tax_paid_cents INTEGER NOT NULL,order_total_cents INTEGER NOT NULL);
CREATE TABLE products(product_id TEXT PRIMARY KEY NOT NULL,product_name TEXT NOT NULL,product_type TEXT NOT NULL,
product_price_cents INTEGER NOT NULL,product_description TEXT);
CREATE TABLE order_items(order_item_id TEXT PRIMARY KEY NOT NULL,order_id TEXT NOT NULL REFERENCES orders(order_id),
product_id TEXT NOT NULL REFERENCES products(product_id));
CREATE TABLE locations(location_id TEXT PRIMARY KEY NOT NULL,location_name TEXT NOT NULL,opened_at TEXT NOT NULL,tax_rate REAL NOT NULL);
CREATE INDEX snapshot_order_time ON orders(ordered_at);
CREATE INDEX snapshot_customer_time ON orders(customer_id,ordered_at);
CREATE INDEX snapshot_items_order ON order_items(order_id);
"""
COLUMNS = {
    "orders": "order_id,customer_id,ordered_at,location_id,subtotal_cents,tax_paid_cents,order_total_cents",
    "products": "product_id,product_name,product_type,product_price_cents,product_description",
    "order_items": "order_item_id,order_id,product_id",
    "locations": "location_id,location_name,opened_at,tax_rate",
}


def snapshot(source_path, output, cutoff):
    """Write a fresh DB, retaining all prior history and checking declared identities."""
    source_path, output = Path(source_path).resolve(), Path(output).resolve()
    if output.exists() or output == source_path:
        raise ValueError("snapshot_output_exists")
    output.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(source_path.as_uri() + "?mode=ro", uri=True)) as src:
        for table in COLUMNS:
            if src.execute("SELECT type FROM sqlite_master WHERE name=?", (table,)).fetchone() != ("table",):
                raise ValueError("snapshot_requires_real_tables")
        with closing(sqlite3.connect(output)) as dst:
            dst.executescript(DDL)
            for table, columns in COLUMNS.items():
                suffix = {
                    "orders": " WHERE ordered_at < ?",
                    "order_items": " WHERE order_id IN (SELECT order_id FROM orders WHERE ordered_at < ?)",
                    "products": " WHERE product_id IN (SELECT product_id FROM order_items WHERE order_id IN (SELECT order_id FROM orders WHERE ordered_at < ?))",
                    "locations": " WHERE location_id IN (SELECT location_id FROM orders WHERE ordered_at < ?)",
                }[table]
                rows = src.execute(f"SELECT {columns} FROM {table}" + suffix, (cutoff[:10],))
                dst.executemany(
                    f"INSERT INTO {table} VALUES({','.join('?' for _ in columns.split(','))})", rows
                )
            if dst.execute(
                "SELECT 1 FROM orders WHERE order_total_cents != subtotal_cents+tax_paid_cents LIMIT 1"
            ).fetchone():
                raise ValueError("snapshot_amount_identity")
            if dst.execute("PRAGMA foreign_key_check").fetchone():
                raise ValueError("snapshot_foreign_keys")
            # Reject noncanonical timestamps instead of relying on mixed string ordering.
            from datetime import datetime

            for (stamp,) in dst.execute("SELECT ordered_at FROM orders"):
                if len(stamp) != 19 or datetime.fromisoformat(stamp).isoformat() != stamp:
                    raise ValueError("snapshot_timestamp_format")
            dst.commit()
    return {"as_of": cutoff, "sha256": digest(output)}
