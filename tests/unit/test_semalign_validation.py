"""Independent generation eligibility must not preselect detector-supported SQL."""

import re

import pytest
from fixtures.semalign_evaluation import MEANINGS, create_evaluation_source
from fixtures.semalign_source import jsonl

from driftlens_benchmark.artifacts import digest, read_json, read_jsonl, write_json
from driftlens_benchmark.detectors.semalign import detect_semalign
from driftlens_benchmark.evaluation.semalign import evaluate_semalign
from driftlens_benchmark.semalign_runner import run_semalign
from driftlens_benchmark.validation.generation import validate_generation
from driftlens_benchmark.validation.references import probes, reference


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
    assert result["reasons"] == ["unsupported_reference_meaning"]


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
