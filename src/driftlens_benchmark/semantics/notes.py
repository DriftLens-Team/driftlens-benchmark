"""Closed, explicit Korean definition grammar; missing clauses remain unknown."""

import re

from .sql import meaning


def extract_note(note, concept_id):
    """Return only meanings stated by an accepted complete phrase, never numeric clues."""
    if not note or not isinstance(note, str):
        return None
    text = re.sub(r"\s+", " ", note.strip())
    if concept_id in {"sa_food_orders", "sa_drink_orders"}:
        patterns = [
            (r"(?:음식\(jaffle\)|음료\(beverage\)) 품목이 하나 이상 포함된 주문 수", "contains"),
            (r"jaffle이 한 개라도 들어간 주문을 셌습니다\.", "contains"),
            (r"음식 품목을 포함한 주문 건수입니다\. 음료가 함께 있어도 포함했습니다\.", "contains"),
            (r"주문 내역에 jaffle 품목이 있는 주문을 집계했어요\.", "contains"),
            (r"jaffle만 주문한 건을 셌습니다\.", "only"),
            (r"음식 품목으로만 구성된 주문 건수입니다\. 음료가 하나라도 있으면 뺐습니다\.", "only"),
            (r"주문 내역이 전부 jaffle 품목인 주문을 집계했어요\.", "only"),
            (r"음식\(jaffle\) 품목만 있는 주문 수 \(음료가 하나라도 있으면 제외\)", "only"),
            (r"음료가 한 잔이라도 포함된 주문을 셌습니다\.", "contains"),
            (r"beverage 품목이 있는 주문 건수입니다\. 음식이 같이 있어도 포함했습니다\.", "contains"),
            (r"주문 품목 중 음료가 있는 주문을 집계했어요\.", "contains"),
        ]
        for pattern, mode in patterns:
            if re.fullmatch(pattern, text):
                # A note describing the other item family is a real semantic difference.
                observed = (
                    "beverage"
                    if "beverage" in text or text.startswith("음료") or "중 음료" in text
                    else "jaffle"
                )
                return meaning(population=mode + ":" + observed)
        if re.fullmatch(r"(?:음식|음료) 주문 건수를 주문 테이블에서 집계했습니다\.", text):
            return {"grain": "order", "aggregation": "count_distinct", "unit": "count"}
    elif concept_id == "sa_customers_active":
        n = None
        m = re.fullmatch(r"해당 주에 ([1-9][0-9]*)회 이상 주문한 고객 수", text)
        if m:
            n = int(m[1])
        for pattern, value in [
            (r"그 주에 한 번이라도 주문한 고객 수입니다\.", 1),
            (r"주간 주문 이력이 있는 고객을 중복 없이 셌습니다\.", 1),
            (r"해당 주 주문 고객 수\(1회 이상\)예요\.", 1),
            (r"그 주에 두 번 이상 주문한 고객 수입니다\.", 2),
            (r"주간 주문이 2건 이상인 고객을 중복 없이 셌습니다\.", 2),
            (r"해당 주 반복 주문 고객 수\(2회 이상\)예요\.", 2),
        ]:
            if re.fullmatch(pattern, text):
                n = value
        if n is not None:
            return meaning(grain="customer", measure="customer_id", conditions=f"min_orders:{n}")
        if text == "주문 활동을 보고 활성 고객을 셌습니다.":
            return {"grain": "customer", "unit": "count"}
    elif concept_id == "sa_order_value_avg":
        pretax = [
            r"해당 기간 주문의 세전 금액\(subtotal\) 평균",
            r"주문 1건당 평균 금액이며 세금은 뺀 금액입니다\.",
            r"세금 전 소계\(subtotal\)를 주문 수로 나눈 평균입니다\.",
            r"세전 주문 평균 금액이에요\.",
        ]
        total = [
            r"해당 기간 주문의 세후 금액\(order_total\) 평균",
            r"주문 1건당 평균 금액이며 세금을 포함한 금액입니다\.",
            r"세금까지 더한 결제 총액\(order_total\)을 주문 수로 나눈 평균입니다\.",
            r"세후 주문 평균 금액이에요\.",
        ]
        for patterns, measure in ((pretax, "subtotal_cents"), (total, "order_total_cents")):
            if any(re.fullmatch(p, text) for p in patterns):
                return meaning(
                    aggregation="average", measure=measure, null_policy="empty_is_null", unit="cents"
                )
        if text == "주문당 평균 금액으로 계산했습니다.":
            return {"grain": "order", "aggregation": "average", "unit": "cents"}
    elif concept_id == "sa_customers_new":
        full = [
            "브랜드 전체에서 첫 주문이 해당 기간에 있는 고객 수",
            "전체 매장을 통틀어 첫 주문이 이번 주에 있는 고객을 셌습니다.",
            "이전 주문 이력이 없는 고객의 첫 구매를 셌어요.",
        ]
        if text in full:
            return meaning(grain="customer", measure="customer_id", time_semantics="first_ever_in_week")
        if text in {"그 주에 처음으로 주문한 고객 수입니다.", "신규 고객 수를 첫 주문일로 계산했습니다."}:
            return {
                "grain": "customer",
                "aggregation": "count_distinct",
                "measure": "customer_id",
                "unit": "count",
            }
    elif concept_id == "sa_revenue_growth_wow":
        full = [
            "전체 매장 세전 매출의 전주 대비 증감률 (전주 데이터가 온전하지 않으면 계산하지 않음)",
            "세전 매출을 전주와 비교한 증감률입니다. 전주 데이터가 온전하지 않으면 계산하지 않습니다.",
        ]
        if text in full:
            return meaning(
                grain="week",
                aggregation="relative_change",
                measure="subtotal_cents",
                time_semantics="week_over_week",
                null_policy="incomplete_prior_week_or_zero",
                unit="ratio",
            )
        if text in {
            "(이번 주 세전 매출 - 전주 세전 매출) / 전주 세전 매출로 계산했습니다.",
            "전 매장 소계 합계의 전주 대비 변화율이에요.",
        }:
            return {
                "measure": "subtotal_cents",
                "aggregation": "relative_change",
                "time_semantics": "week_over_week",
                "unit": "ratio",
            }
        if text == "매출을 전주와 비교해 계산했습니다.":
            return {"time_semantics": "week_over_week"}
    elif concept_id == "sa_tax_rate_avg":
        full = [
            "거래 가중 실효세율 (세금 합계 / 세전 금액 합계)",
            "전체 세금을 전체 세전 매출로 나눈 실효세율입니다.",
            "거래 금액으로 가중한 평균 세율(세금 합 / 소계 합)입니다.",
        ]
        if text in full:
            return meaning(
                aggregation="ratio_of_sums",
                measure="tax_paid_cents/subtotal_cents",
                null_policy="zero_denominator",
                unit="ratio",
            )
        if text == "실제 낸 세금 비율이며 매장별 세율을 단순 평균한 값이 아니에요.":
            return {"unit": "ratio"}
        if text == "평균 세율을 거래 데이터로 계산했습니다.":
            return {}
    return None
