"""Independent generation eligibility must not preselect detector-supported SQL."""

import hashlib
import json
import re
import runpy

import pytest
from fixtures.semalign_evaluation import MEANINGS, create_evaluation_source
from fixtures.semalign_source import jsonl

from driftlens_benchmark.artifacts import digest, read_json, read_jsonl, write_json
from driftlens_benchmark.detectors.semalign import detect_semalign
from driftlens_benchmark.evaluation.semalign import evaluate_semalign
from driftlens_benchmark.semalign_runner import run_semalign
from driftlens_benchmark.validation.generation import validate_generation
from driftlens_benchmark.validation.references import probes, reference, report


def test_behavioral_eligibility_does_not_call_detector_extractors(tmp_path, monkeypatch):
    source = create_evaluation_source(tmp_path / "source")
    # ABS(integer) is deliberately outside the closed SQL meaning grammar,
    # while SQLite and the independent reference agree on every probe.
    for level in ("L1", "L3"):
        rows = read_jsonl(source / f"data/logs.{level}.jsonl")
        for row in rows:
            if row["referenced_concepts"] == ["sa_customers_active"]:
                row["sql"] = re.sub(r"HAVING COUNT\(\*\) >= (\d+)", r"HAVING COUNT(*) >= ABS(\1)", row["sql"])
        jsonl(source / f"data/logs.{level}.jsonl", rows)

    def forbidden(*args, **kwargs):
        raise AssertionError("generation gate called a detector extractor")

    monkeypatch.setattr("driftlens_benchmark.validation.generation.extract", forbidden)
    monkeypatch.setattr("driftlens_benchmark.validation.generation.extract_note", forbidden)
    run = tmp_path / "run"
    result = run_semalign(source, run, validation_policy="behavioral")
    assert result["validated"] == 56 and result["status"] == "complete"
    assert result["validation_dependence"] == "detector_independent_finite_database_agreement"
    attempts = read_jsonl(run / "private/attempts.jsonl")
    assert all(a["checks"]["query_correct_for_used_definition"] is None for a in attempts)
    assert all(a["checks"]["behavioral_agreement"] is True for a in attempts)
    predictions = tmp_path / "predictions"
    detect_semalign(run / "public/L1", predictions)
    report = evaluate_semalign(run, predictions)
    assert report["LOG"]["micro"]["eligible"] == 56
    assert report["LOG"]["micro"]["abstain"] == 8
    assert report["LOG"]["micro"]["fn"] > 0
    assert report["validation_policy"] == "behavioral"


def test_prior_history_boundary_uses_instant_comparison(tmp_path):
    window = {"start": "2025-01-13T00:00:00Z", "end": "2025-01-20T00:00:00Z"}
    cases = {p.stem: p for p in probes(tmp_path / "probes", window)}
    meaning = MEANINGS["sa_revenue_growth_wow"]
    assert reference(cases["prior_start_exact"], meaning, window) == pytest.approx((1076 - 400) / 400)
    assert reference(cases["prior_start_late"], meaning, window) is None
    assert reference(cases["prior_start_early"], meaning, window) == pytest.approx((1076 - 300) / 300)


def test_noncanonical_note_is_unknown_not_a_disproved_definition(tmp_path):
    source = create_evaluation_source(tmp_path / "source")
    row = next(
        r
        for r in read_jsonl(source / "data/logs.L3.jsonl")
        if r["referenced_concepts"] == ["sa_customers_active"]
    )
    definition = row["definition_note"]
    row["definition_note"] = "주간 주문 이력이 있는 고객을 중복 없이 셌습니다."
    result = validate_generation(
        row,
        MEANINGS["sa_customers_active"],
        row["sql"],
        source / "data/jaffle.sqlite",
        probes(tmp_path / "probes", row["reported_values"][0]["window"]),
        mode="fixture",
        definition=definition,
        policy="behavioral",
    )
    assert result["status"] == "unverified"
    assert result["checks"]["behavioral_agreement"] is True
    assert result["checks"]["definition_note_consistent"] is None
    assert not any(v is False for v in result["checks"].values())


@pytest.mark.parametrize(
    "slot,value",
    [
        ("grain", "customer"),
        ("population", "selected_store"),
        ("conditions", "exclude_zero"),
        ("time_semantics", "month"),
        ("null_policy", "zero"),
        ("unit", "ratio"),
    ],
)
def test_reference_does_not_ignore_unsupported_meaning_slots(tmp_path, slot, value):
    source = create_evaluation_source(tmp_path / "source")
    row = next(
        r
        for r in read_jsonl(source / "data/logs.L3.jsonl")
        if r["referenced_concepts"] == ["sa_order_value_avg"]
    )
    meaning = {**MEANINGS["sa_order_value_avg"], slot: value}
    window = row["reported_values"][0]["window"]
    with pytest.raises(ValueError, match="unsupported_reference_meaning"):
        reference(source / "data/jaffle.sqlite", meaning, window)
    result = validate_generation(
        row,
        meaning,
        row["sql"],
        source / "data/jaffle.sqlite",
        probes(tmp_path / "probes", window),
        mode="fixture",
        definition=row["definition_note"],
        policy="behavioral",
    )
    assert result["status"] == "unverified"
    assert result["checks"]["query_result_matches_reference"] is None
    assert result["reasons"] == ["snapshot:reference:unsupported_reference_meaning"]


@pytest.mark.parametrize("snapshot_fails", [False, True])
def test_query_execution_error_is_attributed_to_its_actual_database(tmp_path, snapshot_fails):
    source = create_evaluation_source(tmp_path / "source")
    row = next(
        r
        for r in read_jsonl(source / "data/logs.L3.jsonl")
        if r["referenced_concepts"] == ["sa_revenue_growth_wow"]
    )
    oracle = row["sql"]
    value = row["reported_values"][0]
    window = value["window"]
    cases = {p.stem: p for p in probes(tmp_path / "probes", window)}
    # This valid scalar on complete history incorrectly returns zero rows on
    # incomplete history, rather than the required scalar NULL.
    row["sql"] = (
        f"SELECT * FROM ({oracle}) AS growth WHERE (SELECT MIN(ordered_at) FROM orders) "
        f"<= (date('{window['start'][:10]}', '-7 days') || 'T00:00:00')"
    )
    snapshot_case, probe_case = (
        ("incomplete_previous", "mixed") if snapshot_fails else ("mixed", "incomplete_previous")
    )
    meaning = MEANINGS["sa_revenue_growth_wow"]
    expected = report(reference(cases[snapshot_case], meaning, window), "ratio")
    value["value"] = expected
    row["answer_text"] = "계산할 수 없습니다." if expected is None else f"결과는 {expected} ratio입니다."
    result = validate_generation(
        row,
        meaning,
        oracle,
        cases[snapshot_case],
        [cases[probe_case]],
        mode="agent",
        definition=row["definition_note"],
        policy="behavioral",
    )
    assert result["status"] == "rejected"
    assert result["checks"]["behavioral_agreement"] is False
    assert result["checks"]["query_correct_for_used_definition"] is None
    for check in (
        "query_result_matches_reference",
        "reported_value_matches_query_result",
        "answer_matches_query_result",
    ):
        assert result["checks"][check] is (None if snapshot_fails else True)
    assert result["counterexamples"] == [{"case": probe_case, "matched": snapshot_fails}]
    stage = "snapshot" if snapshot_fails else "counterexample:incomplete_previous"
    assert f"{stage}:query:non_scalar_query" in result["reasons"]


def test_oracle_execution_failure_does_not_reject_the_response(tmp_path):
    source = create_evaluation_source(tmp_path / "source")
    row = read_jsonl(source / "data/logs.L3.jsonl")[0]
    cid = row["referenced_concepts"][0]
    result = validate_generation(
        row,
        MEANINGS[cid],
        "SELECT 0 WHERE 0",
        source / "data/jaffle.sqlite",
        [],
        mode="fixture",
        definition=row["definition_note"],
        policy="behavioral",
    )
    assert result["status"] == "unverified"
    assert result["reasons"] == ["snapshot:oracle:non_scalar_query"]
    assert all(value is None for value in result["checks"].values())


def test_offline_validation_audit_preserves_inputs_and_rejects_hash_changes(tmp_path, root):
    source = create_evaluation_source(tmp_path / "source")
    run = tmp_path / "run"
    run_semalign(source, run, validation_policy="behavioral", limit=7)
    manifest = run / "private/manifest.json"
    before = digest(manifest)
    audit = runpy.run_path(str(root / "scripts/audit_semalign_validation.py"))["main"]
    output, private = tmp_path / "audit.json", tmp_path / "audit-private"
    assert audit(["--run", str(run), "--out", str(output), "--private-out", str(private)]) == 0
    summary = read_json(output)
    assert summary["rechecked_observations"] == 7
    assert summary["status_changed_count"] == 0
    assert summary["diagnostics_changed_count"] == 0
    assert summary["model_api_calls"] == 0
    assert summary["original_run_unchanged"] is True
    assert digest(manifest) == before == summary["original_run_manifest_sha256"]
    assert "log_id" not in output.read_text(encoding="utf-8")
    details = read_jsonl(private / "validation-details.jsonl")
    assert len(details) == 7
    observation = read_jsonl(run / "private/attempts.jsonl")[0]["observation"]
    assert details[0]["observation_sha256"] == hashlib.sha256(
        json.dumps(observation, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    ).hexdigest()
    with (run / "private/attempts.jsonl").open("a", encoding="utf-8") as stream:
        stream.write("\n")
    with pytest.raises(ValueError, match="audit_input_hash_mismatch"):
        audit(
            [
                "--run", str(run), "--out", str(tmp_path / "tampered.json"),
                "--private-out", str(tmp_path / "tampered-private"),
            ]
        )


@pytest.mark.parametrize(
    "mutation", ["run_policy", "unknown_policy", "public_scope", "attempt_policy", "dependence"]
)
def test_rehashed_validation_policy_mismatches_are_rejected(tmp_path, mutation):
    source = create_evaluation_source(tmp_path / "source")
    run = tmp_path / "run"
    run_semalign(source, run, validation_policy="behavioral", limit=7)
    manifest = read_json(run / "private/manifest.json")
    if mutation == "run_policy":
        manifest["validation_policy"] = "structural"
    elif mutation == "unknown_policy":
        manifest["validation_policy"] = "invented"
    elif mutation == "dependence":
        manifest["validation_dependence"] = "independent_proof"
    elif mutation == "public_scope":
        public = read_json(run / "public/L1/manifest.json")
        public["validation_scope"] = "meaning_and_execution"
        write_json(run / "public/L1/manifest.json", public, replace=True)
        manifest["files_sha256"]["public/L1/manifest.json"] = digest(run / "public/L1/manifest.json")
    else:
        attempts = read_jsonl(run / "private/attempts.jsonl")
        attempts[0].update(status="unverified", validation_policy="structural")
        jsonl(run / "private/attempts.jsonl", attempts)
        manifest["files_sha256"]["private/attempts.jsonl"] = digest(run / "private/attempts.jsonl")
    write_json(run / "private/manifest.json", manifest, replace=True)
    predictions = tmp_path / "predictions"
    detect_semalign(run / "public/L1", predictions)
    with pytest.raises(ValueError, match="validation_policy"):
        evaluate_semalign(run, predictions, allow_partial=True)
