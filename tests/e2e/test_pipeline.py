import shutil
import subprocess
import sys
from copy import deepcopy
from importlib import metadata

import pytest

from driftlens_benchmark.artifacts import digest, read_jsonl, write_json, write_jsonl
from driftlens_benchmark.detectors.baselines import detect
from driftlens_benchmark.evaluation.scoring import evaluate
from driftlens_benchmark.observations.records import load_public
from driftlens_benchmark.runner import run


def test_c03_controls_detection_and_scoring(completed_run):
    truth = read_jsonl(completed_run / "private/truth.jsonl")
    changed = [r for r in truth if r["execution"]["arm"] == "changed"]
    controls = [r for r in truth if r["execution"]["arm"] == "control"]
    assert [r["reported_values"][0]["value"] for r in changed] == [3, 2]
    assert [r["reported_values"][0]["value"] for r in controls] == [3, 4]
    for detector, expected_f1 in [("sql-rules", 1.0), ("no-drift", 0.0)]:
        predictions = completed_run / "predictions" / f"{detector}.jsonl"
        detect(completed_run / "public/L3", detector, predictions)
        report = evaluate(completed_run, predictions)
        assert report["micro"]["f1"] == expected_f1
        assert report["micro"]["control_false_positive_rate"] == 0
        assert report["counts"]["eligible_observations"] == 4
    with pytest.raises(ValueError):
        detect(completed_run / "public/L3", "sql-rules", predictions)


def test_seed_reproducibility_and_no_overwrite(tmp_path, run_config):
    config = run_config()
    for name in ("first", "second"):
        run(config, tmp_path / name)
    for file in ("logs.jsonl", "baseline.json", "manifest.json"):
        assert (tmp_path / "first/public/L3" / file).read_bytes() == (
            tmp_path / "second/public/L3" / file
        ).read_bytes()
    with pytest.raises(FileExistsError):
        run(config, tmp_path / "first")


@pytest.mark.parametrize(
    "mode,eligible,rejected,unverified,failed",
    [
        ("wrong_answer", 0, 4, 0, 0),
        ("stale", 3, 1, 0, 0),
        ("unknown_sql", 0, 0, 4, 0),
        ("error", 0, 0, 0, 4),
    ],
)
def test_failures_and_unverified_not_scored_as_drift(
    tmp_path, run_config, mode, eligible, rejected, unverified, failed
):
    output = tmp_path / mode
    manifest = run(run_config(mode), output)
    assert manifest["status"] == "partial"
    assert (
        manifest["eligible_observations"],
        manifest["rejected_observations"],
        manifest["unverified_observations"],
        manifest["generation_failures"],
    ) == (eligible, rejected, unverified, failed)
    predictions = output / "predictions/rules.jsonl"
    detect(output / "public/L3", "sql-rules", predictions)
    with pytest.raises(ValueError, match="partial_run"):
        evaluate(output, predictions)
    report = evaluate(output, predictions, allow_partial=True)
    assert report["counts"]["attempted_requests"] == 4
    assert report["micro"]["eligible"] == eligible
    if not eligible:
        assert report["micro"]["f1"] is None


def test_detector_needs_only_public_copy_outside_repository(completed_run, tmp_path):
    public = tmp_path / "detector-input"
    shutil.copytree(completed_run / "public/L3", public)
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "driftlens_benchmark",
            "detect",
            "--public",
            str(public),
            "--detector",
            "sql-rules",
            "--out",
            str(tmp_path / "predictions.jsonl"),
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert result.returncode == 0, result.stderr
    assert len(read_jsonl(tmp_path / "predictions.jsonl")) == 4


def altered_predictions(run, rows, name):
    output = run / "predictions" / f"{name}.jsonl"
    write_jsonl(output, rows)
    write_json(
        output.with_suffix(".jsonl.manifest.json"),
        {
            "contract_version": "detection/v1",
            "detector": "test-submission",
            "predictions_sha256": digest(output),
            "public_manifest_sha256": digest(run / "public/L3/manifest.json"),
        },
    )
    return output


@pytest.mark.parametrize("alteration", ["missing", "duplicate", "unknown", "future"])
def test_invalid_prediction_join_rejected(completed_run, alteration):
    path = completed_run / "predictions/base.jsonl"
    rows = detect(completed_run / "public/L3", "sql-rules", path)
    if alteration == "missing":
        rows.pop()
    elif alteration == "duplicate":
        rows.append(deepcopy(rows[0]))
    elif alteration == "unknown":
        rows[0]["log_id"] = "unknown"
    else:
        rows[0]["evidence_log_ids"] = [rows[-1]["log_id"]]
    with pytest.raises(ValueError):
        evaluate(completed_run, altered_predictions(completed_run, rows, alteration))


def test_abstentions_count_as_missed_positives(completed_run):
    rows = detect(completed_run / "public/L3", "sql-rules", completed_run / "predictions/base.jsonl")
    for row in rows:
        row["decision"] = "abstain"
    report = evaluate(completed_run, altered_predictions(completed_run, rows, "abstain"))
    assert report["micro"]["counts"] == {
        "tp": 0,
        "fp": 0,
        "tn": 0,
        "fn": 1,
        "abstain_positive": 1,
        "abstain_negative": 3,
    }
    assert report["micro"]["recall"] == 0
    assert report["micro"]["coverage"] == 0


def test_public_and_private_tampering_rejected(completed_run):
    predictions = completed_run / "predictions/base.jsonl"
    detect(completed_run / "public/L3", "sql-rules", predictions)
    truth = completed_run / "private/truth.jsonl"
    truth.write_bytes(truth.read_bytes() + b"\n")
    with pytest.raises(ValueError, match="integrity"):
        evaluate(completed_run, predictions)
    logs = completed_run / "public/L3/logs.jsonl"
    logs.write_bytes(logs.read_bytes() + b"\n")
    with pytest.raises(ValueError, match="integrity"):
        load_public(completed_run / "public/L3")


@pytest.mark.companion
def test_real_companion_subprocess_fake_provider(root, tmp_path):
    try:
        metadata.version("driftlens-sql-agent")
    except metadata.PackageNotFoundError:
        pytest.skip("Install the pinned companion package to run this integration test.")
    output = tmp_path / "companion"
    manifest = run(root / "configs/runs/smoke.yaml", output)
    assert manifest["status"] == "complete"
    assert manifest["eligible_observations"] == 4
    predictions = output / "predictions/sql-rules.jsonl"
    detect(output / "public/L3", "sql-rules", predictions)
    assert evaluate(output, predictions)["micro"]["counts"] == {
        "tp": 1,
        "fp": 0,
        "tn": 3,
        "fn": 0,
        "abstain_positive": 0,
        "abstain_negative": 0,
    }
