"""Two explicit baselines, with abstention outside the SQL recognizer's supported subset."""

from pathlib import Path

from ..artifacts import digest, write_json, write_jsonl
from ..contracts import validate
from ..observations.records import load_public
from ..observations.sql_semantics import meaning


def predict(row, baseline, detector):
    decision, reason = "no_drift", "Constant no-drift baseline."
    if detector == "sql-rules":
        interpreted = meaning(row["sql"])
        window = row["reported_values"][0]["window"]
        if interpreted is None:
            decision, reason = "abstain", "SQL shape is outside the supported count/range/threshold subset."
        elif interpreted.start != window["start"][:10] or interpreted.end != window["end"][:10]:
            decision, reason = "abstain", "SQL reporting period does not match the observation window."
        else:
            threshold = baseline["definitions"][0]["threshold"]
            decision = "drift" if interpreted.threshold != threshold else "no_drift"
            reason = f"SQL uses threshold {interpreted.threshold} cents; baseline uses {threshold} cents."
    elif detector != "no-drift":
        raise ValueError("unknown_detector")
    return validate(
        "detection/v1/prediction",
        {
            "log_id": row["log_id"],
            "result_id": "r1",
            "concept_id": "large_orders",
            "decision": decision,
            "evidence_log_ids": [row["log_id"]],
            "evidence_summary": reason,
        },
    )


def detect(public, detector, out):
    public, out = Path(public).resolve(), Path(out).resolve()
    sidecar = out.with_suffix(out.suffix + ".manifest.json")
    if out.exists() or sidecar.exists():
        raise ValueError("prediction_output_exists")
    if detector not in {"sql-rules", "no-drift"}:
        raise ValueError("unknown_detector")
    baseline, rows = load_public(public)
    predictions = [predict(row, baseline, detector) for row in rows]
    write_jsonl(out, predictions)
    write_json(
        sidecar,
        {
            "contract_version": "detection/v1",
            "detector": detector,
            "detector_version": "1",
            "implementation_sha256": digest(Path(__file__)),
            "sql_recognizer_sha256": digest(Path(__file__).parents[1] / "observations" / "sql_semantics.py"),
            "isolation": "unisolated",
            "predictions_sha256": digest(out),
            "public_manifest_sha256": digest(public / "manifest.json"),
        },
    )
    return predictions
