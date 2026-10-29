"""Exercise the real process boundary with an independently serialized v2 peer."""

import sys
from copy import deepcopy

import pytest

from driftlens_benchmark.adapters.jsonl import AgentFailure, exchange
from driftlens_benchmark.artifacts import write_json

REQUEST = {
    "request_id": "request_demo",
    "request": "지난주 성장률",
    "concept_id": "sa_revenue_growth_wow",
    "timestamp": "2020-01-14T12:00:00Z",
    "as_of": "2020-01-13T00:00:00Z",
    "window": {"start": "2020-01-06T00:00:00Z", "end": "2020-01-13T00:00:00Z"},
}


@pytest.fixture
def response():
    return {
        "request_id": REQUEST["request_id"],
        "status": "ok",
        "observation": {
            "sql": "SELECT NULL AS value",
            "answer_text": "전주 자료가 부족해 계산할 수 없습니다.",
            "definition_note": "전주 대비 증감률",
            "reported_values": [
                {
                    "result_id": "r1",
                    "concept_id": REQUEST["concept_id"],
                    "type": "metric_value",
                    "value": None,
                    "unit": "ratio",
                    "window": deepcopy(REQUEST["window"]),
                    "as_of": REQUEST["as_of"],
                }
            ],
            "referenced_concepts": [REQUEST["concept_id"]],
        },
    }


def test_explicit_v2_protocol_supports_nullable_results(root, tmp_path, response):
    path = tmp_path / "response.json"
    write_json(path, response)
    command = [sys.executable, str(root / "tests/fixtures/protocol_agent_v2.py"), str(path)]
    observation, diagnostic = exchange(command, REQUEST, cwd=tmp_path, timeout=3, protocol="agent/v2")
    assert observation["reported_values"][0]["value"] is None
    assert diagnostic["exit_code"] == 0
    with pytest.raises(ValueError, match="agent/v1/request"):
        exchange(command, REQUEST, cwd=tmp_path, timeout=3)
    with pytest.raises(ValueError, match="unsupported_agent_protocol"):
        exchange(command, REQUEST, cwd=tmp_path, timeout=3, protocol="agent/v99")


@pytest.mark.parametrize("field", ["concept_id", "window", "as_of", "extra", "id"])
def test_v2_response_must_belong_to_the_request(root, tmp_path, response, field):
    value = response["observation"]["reported_values"][0]
    if field == "concept_id":
        value["concept_id"] = "sa_tax_rate_avg"
        response["observation"]["referenced_concepts"] = ["sa_tax_rate_avg"]
    elif field == "window":
        value["window"] = {"start": "2019-12-30T00:00:00Z", "end": "2020-01-06T00:00:00Z"}
        value["as_of"] = value["window"]["end"]
    elif field == "as_of":
        value["as_of"] = "2020-01-14T00:00:00Z"
    elif field == "extra":
        value["version_used"] = "v2"
    else:
        response["request_id"] = "wrong_request"
    path = tmp_path / "response.json"
    write_json(path, response)
    with pytest.raises(AgentFailure, match="invalid_agent_response"):
        exchange(
            [sys.executable, str(root / "tests/fixtures/protocol_agent_v2.py"), str(path)],
            REQUEST,
            cwd=tmp_path,
            timeout=3,
            protocol="agent/v2",
        )
