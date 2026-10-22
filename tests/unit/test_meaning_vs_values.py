from driftlens_benchmark.artifacts import read_json
from driftlens_benchmark.detectors.baselines import predict
from driftlens_benchmark.environments.build import snapshot
from driftlens_benchmark.observations.records import make_truth, project
from driftlens_benchmark.settings import load_suite


def test_changed_definition_with_identical_numbers_is_still_drift(root, tmp_path):
    suite = load_suite(root / "benchmarks/suites/smoke.yaml")
    database = tmp_path / "orders.sqlite"
    snapshot([("a", "2025-01-06", 4000), ("b", "2025-01-12", 5000)], suite.schema, database, "2025-01-13")
    request = read_json(root / "examples/submissions/request.json")
    response = read_json(root / "examples/submissions/response.json")["observation"]
    response["reported_values"][0]["value"] = 2
    response["answer_text"] = "이번 주 대형 주문은 2건입니다."
    response["sql"] = response["sql"].replace("2000", "3000")
    response["definition_note"] = "주문 총액 3000센트 이상인 주문"
    truth = make_truth(
        response,
        request,
        log_id="x",
        agent_id="a",
        database=database,
        definitions=suite.definitions,
        version="v2",
        reference_results={"v1": 2, "v2": 2},
        arm="changed",
        effective_at="2025-01-06",
    )
    assert truth["validation_status"] == "validated"
    assert truth["concept_truth"][0]["semantic_drift"] is True
    assert truth["concept_truth"][0]["output_changed"] is False
    baseline = {"definitions": [suite.definitions["v1"]]}
    assert predict(project(truth), baseline, "sql-rules")["decision"] == "drift"
    # The same numbers do not excuse a query implementing the wrong selected definition.
    response["sql"] = response["sql"].replace("3000", "2000")
    stale = make_truth(
        response,
        request,
        log_id="y",
        agent_id="a",
        database=database,
        definitions=suite.definitions,
        version="v2",
        reference_results={"v1": 2, "v2": 2},
        arm="changed",
        effective_at="2025-01-06",
    )
    assert stale["validation_status"] == "rejected"
    assert stale["execution"]["query_result_matches_reference"] is True
    assert stale["concept_truth"][0]["query_correct_for_used_definition"] is False
