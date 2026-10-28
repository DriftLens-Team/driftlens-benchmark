"""Boundary cases for the new contracts; no companion code or model calls."""

from copy import deepcopy

import pytest

from driftlens_benchmark.contracts import validate, validator
from driftlens_benchmark.contracts.semalign import (
    LEVELS,
    observation_check,
    prediction_check,
    request_check,
    response_check,
)
from driftlens_benchmark.observations.projection import project_fixture

REQUEST = {
    "request_id": "req_demo",
    "request": "지난주 매출 성장률 알려줘",
    "timestamp": "2024-09-10T14:00:00Z",
    "concept_id": "sa_revenue_growth_wow",
    "window": {"start": "2024-09-02T00:00:00Z", "end": "2024-09-09T00:00:00Z"},
    "as_of": "2024-09-09T00:00:00Z",
}


@pytest.fixture
def observation():
    return {
        "log_id": "obs_demo",
        "timestamp": REQUEST["timestamp"],
        "agent_id": "agent_demo",
        "team": "test",
        "request": REQUEST["request"],
        "sql": "SELECT -0.125 AS value",
        "answer_text": "매출 성장률 -12.50%",
        "definition_note": "세전 매출의 전주 대비 증감률",
        "reported_values": [
            {
                "result_id": "r1",
                "concept_id": REQUEST["concept_id"],
                "type": "metric_value",
                "value": -0.125,
                "unit": "ratio",
                "window": deepcopy(REQUEST["window"]),
                "as_of": REQUEST["as_of"],
            }
        ],
        "referenced_concepts": [REQUEST["concept_id"]],
    }


def test_schemas_are_installed_resources():
    for name in (
        "agent/v2/request",
        "agent/v2/response",
        "records/v3/observation",
        "records/v3/baseline",
        "records/v3/pair",
        "records/v3/series",
        "records/v3/public-manifest",
        "detection/v2/log",
        "detection/v2/pairs",
        "detection/v2/series",
    ):
        assert validator(name).schema["$schema"].endswith("2020-12/schema")


@pytest.mark.parametrize("value", [-0.125, 0, 0.0525, None])
def test_negative_zero_fraction_and_null_are_valid_ratio_results(observation, value):
    observation["reported_values"][0]["value"] = value
    assert request_check(REQUEST) is REQUEST
    assert observation_check(observation, level="L3") is observation
    response = {
        "request_id": REQUEST["request_id"],
        "status": "ok",
        "observation": {
            k: observation[k]
            for k in ("sql", "answer_text", "definition_note", "reported_values", "referenced_concepts")
        },
    }
    assert response_check(response, REQUEST) is response
    with pytest.raises(ValueError):
        validate("agent/v1/response", response)


@pytest.mark.parametrize("value", [True, float("nan"), float("inf"), "0.05", 0.12345])
def test_invalid_ratio_values(observation, value):
    observation["reported_values"][0]["value"] = value
    with pytest.raises(ValueError):
        observation_check(observation, level="L3")


@pytest.mark.parametrize("value", [1.0, True, -1])
def test_counts_require_nonnegative_integer_tokens(observation, value):
    rv = observation["reported_values"][0]
    rv.update(concept_id="sa_food_orders", unit="count", value=value)
    observation["referenced_concepts"] = ["sa_food_orders"]
    with pytest.raises(ValueError):
        observation_check(observation, level="L3")


def test_count_limit_is_exact_signed_64_bit(observation):
    value = observation["reported_values"][0]
    value.update(concept_id="sa_food_orders", unit="count", value=2**63 - 1)
    observation["referenced_concepts"] = ["sa_food_orders"]
    observation_check(observation, level="L3")
    value["value"] = 2**63
    with pytest.raises(ValueError):
        observation_check(observation, level="L3")


@pytest.mark.parametrize(
    "mutation",
    [
        lambda r: r.update(timestamp="2024-09-08T23:59:59Z"),
        lambda r: r.update(as_of="2024-09-08T23:59:59Z"),
        lambda r: r["window"].update(start="2024-09-03T00:00:00Z"),
        lambda r: r["window"].update(end="2024-09-10T00:00:00Z"),
        lambda r: r.update(timestamp="2024-09-10T14:00:00"),
        lambda r: r.update(concept_id="large_orders"),
        lambda r: r.update(request="  "),
        lambda r: r.update(profile="v2"),
    ],
)
def test_request_scope_is_not_overridden(mutation):
    request = deepcopy(REQUEST)
    mutation(request)
    with pytest.raises(ValueError):
        request_check(request)


def test_projection_is_deep_and_nested_unknown_fields_fail(observation):
    original = deepcopy(observation)
    for level, hidden in LEVELS.items():
        projected = project_fixture(observation, level)
        assert {k for k in ("sql", "definition_note") if projected[k] is None} == hidden
        projected["reported_values"][0]["value"] = 0
        assert observation == original
    observation["reported_values"][0]["effective_at"] = "private"
    with pytest.raises(ValueError):
        project_fixture(observation, "L0")


def test_ref_and_unit_must_agree_with_concept(observation):
    bad = deepcopy(observation)
    bad["referenced_concepts"] = ["sa_food_orders"]
    with pytest.raises(ValueError):
        observation_check(bad, level="L3")
    observation["reported_values"][0]["unit"] = "count"
    with pytest.raises(ValueError):
        observation_check(observation, level="L3")


def test_t2_states_have_distinct_time_requirements():
    prediction = {
        "concept_id": REQUEST["concept_id"],
        "decision": "change",
        "estimated_change_at": "2024-09-02",
        "alarm_at": "2024-09-17T14:00:00Z",
        "reason_code": "definition_mismatch",
        "evidence": [],
        "evidence_summary": "Test.",
    }
    prediction_check("series", prediction)
    for change in (
        {"decision": "abstain"},
        {"alarm_at": None},
        {"estimated_change_at": "2024-09-03"},
        {"estimated_change_at": "2024-09-23"},
    ):
        with pytest.raises(ValueError):
            prediction_check("series", {**prediction, **change})
    for state in ("no_change", "abstain"):
        prediction_check(
            "series", {**prediction, "decision": state, "estimated_change_at": None, "alarm_at": None}
        )
