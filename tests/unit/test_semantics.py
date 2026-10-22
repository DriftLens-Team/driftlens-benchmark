import pytest

from driftlens_benchmark.observations.sql_semantics import CountMeaning, meaning


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT COUNT(*) FROM orders WHERE ordered_at >= '2025-01-06' AND ordered_at < '2025-01-13' AND order_total_cents >= 2000",
        "select count(order_id) AS n from orders where order_total_cents >= 2000 and (ordered_at < '2025-01-13' and ordered_at >= '2025-01-06')",
        "SELECT COUNT(DISTINCT o.order_id) FROM orders o WHERE 2000 <= o.order_total_cents AND '2025-01-13' > o.ordered_at AND '2025-01-06' <= o.ordered_at",
        'SELECT COUNT(1) FROM "orders" WHERE "ordered_at" >= \'2025-01-06\' AND "ordered_at" < \'2025-01-13\' AND "order_total_cents" >= 2000;',
    ],
)
def test_equivalent_shapes_not_string_equality(sql):
    assert meaning(sql) == CountMeaning("2025-01-06", "2025-01-13", 2000)


BASE = "SELECT COUNT(*) FROM orders WHERE ordered_at >= '2025-01-06' AND ordered_at < '2025-01-13' AND order_total_cents >= 2000"


@pytest.mark.parametrize(
    "sql",
    [
        BASE + " OR 1=1",
        BASE + " LIMIT 0",
        BASE + " GROUP BY order_total_cents",
        BASE + "; SELECT 1",
        BASE + " AND order_id='x'",
        BASE.replace("COUNT(*)", "SUM(order_total_cents)"),
        BASE.replace("COUNT(*)", "COUNT(DISTINCT order_total_cents)"),
        BASE.replace(">= 2000", "> 2000"),
        BASE.replace("2000", "'2000'"),
        BASE.replace("2000", "2000.0"),
        BASE.replace("orders WHERE", "orders JOIN orders b WHERE"),
        BASE.replace("orders", "sqlite_master"),
        "DELETE FROM orders",
        "not sql",
        "",
    ],
)
def test_unsupported_shapes_abstain(sql):
    assert meaning(sql) is None
