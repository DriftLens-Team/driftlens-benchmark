"""Validate complete supported answer sentences, including unit and date rendering."""

from datetime import date


def answer_matches(observation, value, *, mode):
    """Return true/false for the closed grammar; unfamiliar prose is unverified."""
    result = observation["reported_values"][0]
    cid, unit = result["concept_id"], result["unit"]
    text = observation["answer_text"]
    canonical = "계산할 수 없습니다." if value is None else f"결과는 {value} {unit}입니다."
    if mode == "agent" or text == canonical:
        return text == canonical
    start = date.fromisoformat(result["window"]["start"][:10])
    week = f"{start.month}월 {start.day}일 주"
    prefixes = (week, "지난주", f"지난주({week})")
    label = {
        "sa_food_orders": "음식 주문",
        "sa_drink_orders": "음료 주문",
        "sa_customers_active": "활성 고객",
        "sa_customers_new": "신규 고객",
        "sa_order_value_avg": "객단가",
        "sa_revenue_growth_wow": "매출 성장률",
        "sa_tax_rate_avg": "평균 세율",
    }[cid]
    suffix = "은" if cid not in {"sa_order_value_avg"} else "는"
    if value is None:
        answers = {f"{p} {label}은 비교할 데이터가 부족해 계산할 수 없습니다." for p in prefixes}
    else:
        display = (
            f"{value:,}센트(${value / 100:,.2f})"
            if unit == "cents"
            else f"{value:.2%}"
            if unit == "ratio"
            else f"{value:,}"
        )
        tail = "건" if cid in {"sa_food_orders", "sa_drink_orders"} else "명" if unit == "count" else ""
        middle = "전주 대비 " if cid == "sa_revenue_growth_wow" else ""
        answers = {f"{p} {label}{suffix} {middle}{display}{tail}입니다." for p in prefixes}
    if text in answers:
        return True
    # Known family with wrong number/unit/date is rejected, not quietly skipped.
    if label in text or text.startswith("결과는 "):
        return False
    return None
