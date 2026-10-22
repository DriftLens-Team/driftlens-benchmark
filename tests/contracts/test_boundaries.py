from copy import deepcopy

import pytest

from driftlens_benchmark.artifacts import read_jsonl, strict_json
from driftlens_benchmark.contracts import validate, week
from driftlens_benchmark.contracts.legacy import load_legacy
from driftlens_benchmark.observations.records import load_public, project
from driftlens_benchmark.settings import load


@pytest.mark.parametrize("text", ['{"a":1,"a":2}', '{"x":NaN}', '{"x":Infinity}', '{"x":1e999}'])
def test_strict_json(text):
    with pytest.raises(ValueError):
        strict_json(text)


@pytest.mark.parametrize("period", ["2025-W00", "2025-W54", "2025-W1", "2025-W53", "invalid"])
def test_bad_iso_weeks(period):
    with pytest.raises(ValueError):
        week(period)


def test_nested_truth_never_exported(completed_run):
    truths = read_jsonl(completed_run / "private/truth.jsonl")
    _, public = load_public(completed_run / "public/L3")
    assert public == [project(t) for t in truths]
    for row in public:
        assert len(row) == 10
        assert not {"concept_truth", "execution", "validation_status"} & row.keys()
    bad = deepcopy(truths[0])
    bad["reported_values"][0]["secret_threshold"] = 3000
    with pytest.raises(ValueError):
        project(bad)
    for value in [True, 3.0, "3", -1]:
        bad = deepcopy(public[0])
        bad["reported_values"][0]["value"] = value
        with pytest.raises(ValueError):
            validate("records/v2/observation", bad)


def test_config_unknown_duplicate_and_capability_errors(tmp_path):
    path = tmp_path / "bad.yaml"
    for content in ["version: 1\nversion: 1\n", "version: 1\nextra: true\n"]:
        path.write_text(content, encoding="utf-8")
        with pytest.raises(ValueError):
            load(path, "run")


def test_legacy_and_documented_protocol_examples(root, tmp_path):
    from driftlens_benchmark.artifacts import read_json, write_jsonl

    request = validate("agent/v1/request", read_json(root / "examples/submissions/request.json"))
    response = validate("agent/v1/response", read_json(root / "examples/submissions/response.json"))
    row = {
        "log_id": "legacy-1",
        "agent_id": "agent-1",
        "team": "analytics",
        "timestamp": request["timestamp"].replace("Z", "+00:00"),
        "request": request["request"],
        **response["observation"],
    }
    path = tmp_path / "logs.jsonl"
    write_jsonl(path, [row])
    assert load_legacy(path) == [row]


def test_nonfinite_yaml_timeout_rejected(root, tmp_path):
    source = (root / "configs/agents/sql-agent-v1.yaml").read_text(encoding="utf-8")
    path = tmp_path / "agent.yaml"
    for value in (".nan", ".inf", "-.inf"):
        path.write_text(source.replace("timeout_seconds: 75", "timeout_seconds: " + value), encoding="utf-8")
        with pytest.raises(ValueError):
            load(path, "agent")


def test_suite_requires_a_report_before_the_change(root, tmp_path):
    from driftlens_benchmark.settings import load_suite

    source = (root / "benchmarks/suites/smoke.yaml").read_text(encoding="utf-8")
    path = tmp_path / "suite.yaml"
    # A Sunday change already applies to the whole first report, so there is no before period.
    path.write_text(
        source.replace('effective_at: "2025-01-13"', 'effective_at: "2025-01-12"'), encoding="utf-8"
    )
    with pytest.raises(ValueError, match="baseline_and_changed_weeks"):
        load_suite(path)
