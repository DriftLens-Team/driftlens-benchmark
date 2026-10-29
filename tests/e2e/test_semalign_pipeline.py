"""Complete invented run plus tampered submissions and partial-run denominators."""

from copy import deepcopy

import pytest
from fixtures.semalign_evaluation import create_evaluation_source
from fixtures.semalign_source import jsonl

from driftlens_benchmark.artifacts import digest, object_digest, read_json, read_jsonl, write_json
from driftlens_benchmark.contracts import validate
from driftlens_benchmark.datasets.snapshots import snapshot
from driftlens_benchmark.detectors.semalign import detect_semalign
from driftlens_benchmark.evaluation.semalign import evaluate_semalign, metrics
from driftlens_benchmark.semalign_runner import run_semalign


@pytest.fixture(scope="module")
def complete_run(tmp_path_factory):
    root = tmp_path_factory.mktemp("semalign-complete")
    source = create_evaluation_source(root / "source")
    run = root / "run"
    result = run_semalign(source, run)
    assert result["status"] == "complete", [
        (a["concept_id"], a["status"], a.get("reasons"), a.get("error"))
        for a in read_jsonl(run / "private/attempts.jsonl")
        if a["status"] != "validated"
    ]
    return run


def rehash(predictions):
    manifest = read_json(predictions / "manifest.json")
    manifest["files"] = {name: digest(predictions / name) for name in manifest["files"]}
    write_json(predictions / "manifest.json", manifest, replace=True)


def test_full_pipeline_and_separate_meaning_scores(complete_run, tmp_path):
    out = tmp_path / "predictions"
    detect_semalign(complete_run / "public/L1", out)
    report = evaluate_semalign(complete_run, out)
    assert report["generation"] == {
        "planned": 56,
        "attempted": 56,
        "successful_response": 56,
        "failed": 0,
        "validated": 56,
        "rejected": 0,
        "unverified": 0,
    }
    assert report["series_eligibility"] == {"planned": 7, "complete": 7, "excluded": 0}
    assert report["pair_eligibility"] == {"planned": 112, "eligible": 112, "excluded": 0}
    for task in ("LOG", "T1", "T2"):
        assert report[task]["micro"]["f1"] == 1
        assert report[task]["micro"]["coverage"] == 1
    assert all(t["alarm_delay_weeks"] == 1 for t in report["timing"])
    l0 = tmp_path / "l0"
    detect_semalign(complete_run / "public/L0", l0)
    r = evaluate_semalign(complete_run, l0)
    assert r["LOG"]["micro"]["coverage"] == 0
    assert r["LOG"]["micro"]["fn"] == 12
    assert r["LOG"]["micro"]["tn"] == 0


@pytest.mark.parametrize("duplicate_arrivals", [False, True], ids=["unique", "duplicate"])
def test_alarm_timing_uses_first_online_alarm_window(tmp_path, duplicate_arrivals):
    source = create_evaluation_source(tmp_path / "source")
    if duplicate_arrivals:
        for level in ("L0", "L1", "L2", "L3"):
            path = source / f"data/logs.{level}.jsonl"
            rows = read_jsonl(path)
            for row in rows:
                row["timestamp"] = "2020-03-02T12:00:00"
            jsonl(path, rows)
    run, predictions = tmp_path / "run", tmp_path / "predictions"
    result = run_semalign(source, run, mode="fixture")
    assert result["status"] == "complete"
    assert result["planned"] == result["attempted"] == result["validated"] == 56
    detect_semalign(run / "public/L1", predictions, method="semantic-sql")
    report = evaluate_semalign(run, predictions)
    trace = read_jsonl(predictions / "online.jsonl")
    timing = {item["concept_id"]: item for item in report["timing"]}
    assert set(timing) == {"sa_food_orders", "sa_drink_orders", "sa_customers_active"}
    for cid, item in timing.items():
        entries = [entry for entry in trace if entry["concept_id"] == cid]
        alarms = [entry for entry in entries if entry["prediction"]["decision"] == "change"]
        assert [entry["step"] for entry in alarms] == [5, 6, 7]
        first = alarms[0]["prediction"]
        assert all(entry["prediction"] == first for entry in alarms)
        assert first["estimated_change_at"] == "2020-02-03"
        assert first["alarm_at"] == entries[5]["cutoff"]
        assert item["alarm_delay_weeks"] == 1.0
        assert item["arrival_delay_seconds"] == (0.0 if duplicate_arrivals else 604800.0)


@pytest.mark.parametrize(
    "mutation",
    ["duplicate", "missing", "extra", "hidden_evidence", "future_evidence", "future_view", "unbound"],
)
def test_rehashed_submission_violations_are_rejected(complete_run, tmp_path, mutation):
    out = tmp_path / "predictions"
    detect_semalign(complete_run / "public/L1", out)
    logs = read_jsonl(out / "log.jsonl")
    if mutation in {"duplicate", "missing", "extra", "hidden_evidence"}:
        if mutation == "duplicate":
            logs.append(deepcopy(logs[0]))
        elif mutation == "missing":
            logs.pop()
        elif mutation == "extra":
            logs.append({**logs[0], "log_id": "extra"})
        else:
            logs[0]["evidence"] = [
                {"log_id": logs[0]["log_id"], "field": "definition_note", "quote": "hidden"}
            ]
        jsonl(out / "log.jsonl", logs)
    elif mutation == "future_evidence":
        series = read_jsonl(out / "series.jsonl")
        changed = next(p for p in series if p["decision"] == "change")
        group = next(
            g
            for g in read_json(complete_run / "public/L1/series.json")
            if g["concept_id"] == changed["concept_id"]
        )
        future = next(
            r
            for r in read_jsonl(complete_run / "public/L1/logs.jsonl")
            if r["log_id"] == group["log_ids"][-1]
        )
        changed["evidence"].append({"log_id": future["log_id"], "field": "sql", "quote": future["sql"]})
        jsonl(out / "series.jsonl", series)
    elif mutation == "future_view":
        trace = read_jsonl(out / "online.jsonl")
        first = trace[0]
        view = read_json(out / first["view_file"])
        view["observations"].append(read_jsonl(complete_run / "public/L1/logs.jsonl")[-1])
        write_json(out / first["view_file"], view, replace=True)
        first["view_sha256"] = object_digest(view)
        jsonl(out / "online.jsonl", trace)
    else:
        m = read_json(out / "manifest.json")
        m["public_manifest_sha256"] = "0" * 64
        write_json(out / "manifest.json", m, replace=True)
    rehash(out)
    with pytest.raises(ValueError):
        evaluate_semalign(complete_run, out)


def test_partial_generation_does_not_shrink_planned_denominator(tmp_path):
    source = create_evaluation_source(tmp_path / "source")
    run = tmp_path / "run"
    result = run_semalign(source, run, limit=7)
    assert result["attempted"] == 7 and result["planned"] == 56 and result["status"] == "partial"
    predictions = tmp_path / "predictions"
    detect_semalign(run / "public/L3", predictions)
    with pytest.raises(ValueError, match="partial_run"):
        evaluate_semalign(run, predictions)
    report = evaluate_semalign(run, predictions, allow_partial=True)
    assert report["series_eligibility"]["complete"] == 0
    assert report["T2"]["micro"]["f1"] is None
    assert report["planned_completion_rate"] == 7 / 56


def test_zero_eligible_run_and_undefined_metrics(tmp_path):
    source = create_evaluation_source(tmp_path / "source")
    for level in ("L1", "L3"):
        rows = read_jsonl(source / f"data/logs.{level}.jsonl")
        for row in rows:
            row["sql"] = "SELECT 999999"
        jsonl(source / f"data/logs.{level}.jsonl", rows)
    run = tmp_path / "run"
    result = run_semalign(source, run)
    assert result["validated"] == 0 and result["rejected"] == 56
    p = tmp_path / "predictions"
    detect_semalign(run / "public/L3", p)
    report = evaluate_semalign(run, p, allow_partial=True)
    assert report["LOG"]["micro"]["coverage"] is None
    assert report["generation_valid_rate"] == 0


def test_wrong_first_alarm_is_fp_and_fn_and_abstention_is_not_tn():
    result = metrics(
        [
            {"positive": True, "prediction": True, "hit": False},
            {"positive": True, "prediction": None},
            {"positive": False, "prediction": None},
            {"positive": False, "prediction": False},
        ]
    )
    assert (result["tp"], result["fp"], result["fn"], result["tn"], result["abstain"]) == (0, 1, 2, 1, 2)
    assert result["coverage"] == 0.5 and result["fpr"] == 0


@pytest.mark.parametrize(
    "name,field", [("truth", "semantic_drift"), ("pairs-truth", "changed"), ("series-truth", "complete")]
)
def test_private_contracts_reject_integer_labels(complete_run, name, field):
    filename = {
        "truth": "truth.jsonl",
        "pairs-truth": "pairs.truth.jsonl",
        "series-truth": "series.truth.jsonl",
    }[name]
    row = read_jsonl(complete_run / "private" / filename)[0]
    validate("records/v3/" + name, row)
    row[field] = 1
    with pytest.raises(ValueError):
        validate("records/v3/" + name, row)


def test_snapshot_preserves_past_and_excludes_future(tmp_path):
    import sqlite3

    source = create_evaluation_source(tmp_path / "source")
    original = source / "data/jaffle.sqlite"
    before = digest(original)
    target = tmp_path / "snapshot.sqlite"
    snapshot(original, target, "2020-01-13T00:00:00Z")
    with sqlite3.connect(target) as db:
        assert db.execute("SELECT COUNT(*) FROM orders").fetchone()[0] == 5
        assert db.execute("SELECT MAX(ordered_at) FROM orders").fetchone()[0] < "2020-01-13"
        assert db.execute("SELECT MIN(ordered_at) FROM orders").fetchone()[0] == "2019-12-26T00:00:00"
        assert db.execute("PRAGMA foreign_key_check").fetchone() is None
    db.close()
    assert digest(original) == before
    with pytest.raises(ValueError):
        snapshot(original, target, "2020-01-20T00:00:00Z")
