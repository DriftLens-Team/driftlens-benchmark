CREATE TABLE orders (
    order_id TEXT PRIMARY KEY NOT NULL,
    ordered_at TEXT NOT NULL,
    order_total_cents INTEGER NOT NULL CHECK(typeof(order_total_cents) = 'integer')
);
