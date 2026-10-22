SELECT COUNT(*) FROM orders WHERE ordered_at >= :start AND ordered_at < :end AND order_total_cents >= 3000;
