"""Explicit denominators, integrity checks and abstention-aware scoring."""

from pathlib import Path

from ..artifacts import digest, read_json, read_jsonl, unique, write_json
from ..contracts import validate
from ..observations.records import load_public, project


def metrics(truths, predictions):
    counts = dict(tp=0, fp=0, tn=0, fn=0, abstain_positive=0, abstain_negative=0)
    control_total = control_false_positives = 0
    for row in truths:
        positive = row["concept_truth"][0]["semantic_drift"]
        decision = predictions[row["log_id"]]["decision"]
        if decision == "abstain":
            counts["abstain_positive" if positive else "abstain_negative"] += 1
            if positive:
                counts["fn"] += 1
        else:
            counts[("tp" if positive else "fp") if decision == "drift" else ("fn" if positive else "tn")] += 1
        if row["execution"]["arm"] == "control":
            control_total += 1
            control_false_positives += decision == "drift"
    tp, fp, tn, fn = (counts[k] for k in ("tp", "fp", "tn", "fn"))

    def divide(a, b):
        return a / b if b else None

    negatives = tn + fp + counts["abstain_negative"]
    return {
        "counts": counts,
        "eligible": len(truths),
        "precision": divide(tp, tp + fp),
        "recall": divide(tp, tp + fn),
        "f1": divide(2 * tp, 2 * tp + fp + fn),
        "false_positive_rate": divide(fp, negatives),
        "control_false_positive_rate": divide(control_false_positives, control_total),
        "control_count": control_total,
        "coverage": divide(
            len(truths) - counts["abstain_positive"] - counts["abstain_negative"], len(truths)
        ),
        "undefined_metric_reason": "A null metric has a zero denominator; it is not zero performance.",
    }


def evaluate(run, predictions_path, *, allow_partial=False, out=None):
    run, predictions_path = Path(run).resolve(), Path(predictions_path).resolve()
    private = run / "private"
    manifest = read_json(private / "run.private.json")
    if manifest.get("contract_version") != "records/v2":
        raise ValueError("unknown_run_contract")
    if manifest.get("status") not in {"complete", "partial"}:
        raise ValueError("run_not_finished")
    if manifest["status"] != "complete" and not allow_partial:
        raise ValueError("partial_run_requires_allow_partial")
    public = run / "public" / "L3"
    if (
        digest(private / "truth.jsonl") != manifest["truth_sha256"]
        or digest(private / "failures.jsonl") != manifest["failures_sha256"]
        or digest(public / "manifest.json") != manifest["public_manifest_sha256"]
    ):
        raise ValueError("run_integrity_mismatch")
    _, public_rows = load_public(public)
    truths = unique([validate("records/v2/truth", row) for row in read_jsonl(private / "truth.jsonl")])
    failures = unique(read_jsonl(private / "failures.jsonl"))
    eligible = [row for row in truths if row["validation_status"] == "validated"]
    if (
        [project(row) for row in eligible] != public_rows
        or len(eligible) != manifest["eligible_observations"]
        or len(failures) != manifest["generation_failures"]
        or len(truths) + len(failures) != manifest["attempted_requests"]
    ):
        raise ValueError("run_accounting_mismatch")
    if manifest["status"] == "complete" and len(eligible) != manifest["expected_requests"]:
        raise ValueError("incomplete_run_marked_complete")
    sidecar = read_json(predictions_path.with_suffix(predictions_path.suffix + ".manifest.json"))
    if (
        sidecar.get("contract_version") != "detection/v1"
        or digest(predictions_path) != sidecar.get("predictions_sha256")
        or digest(public / "manifest.json") != sidecar.get("public_manifest_sha256")
    ):
        raise ValueError("prediction_integrity_mismatch")
    predicted = unique([validate("detection/v1/prediction", p) for p in read_jsonl(predictions_path)])
    by_id = {p["log_id"]: p for p in predicted}
    timestamps = {r["log_id"]: r["timestamp"] for r in eligible}
    if set(by_id) != set(timestamps):
        raise ValueError("prediction_ids_must_exactly_match_eligible_observations")
    for prediction in predicted:
        for evidence_id in prediction["evidence_log_ids"]:
            if evidence_id not in timestamps or timestamps[evidence_id] > timestamps[prediction["log_id"]]:
                raise ValueError("invalid_or_future_evidence")
    scores = metrics(eligible, by_id)
    per_case = {
        case: metrics([r for r in eligible if r["execution"]["case_id"] == case], by_id)
        for case in sorted({r["execution"]["case_id"] for r in eligible})
    }
    macro = {}
    for key in ("precision", "recall", "f1"):
        values = [m[key] for m in per_case.values() if m[key] is not None]
        macro[key] = sum(values) / len(values) if values else None
    report = {
        "status": manifest["status"],
        "execution_mode": manifest["execution_mode"],
        "isolation": "unisolated",
        "level": "L3",
        "detector": sidecar.get("detector"),
        "counts": {
            key: manifest[key]
            for key in (
                "expected_requests",
                "attempted_requests",
                "successful_responses",
                "generation_failures",
                "eligible_observations",
                "rejected_observations",
                "unverified_observations",
            )
        },
        "micro": scores,
        "by_case": per_case,
        "macro": macro,
        "temporal": {
            "score": None,
            "reason": "Change-time tolerance and observability policy not implemented.",
        },
        "limitations": [
            "Local unisolated development run; no held-out performance claim.",
            "SQL recognizer supports only the documented count/range/threshold subset.",
            "Fake provider results are integration checks, not live model quality.",
        ],
        "provenance": {
            "run_manifest_sha256": digest(private / "run.private.json"),
            "prediction_manifest": sidecar,
        },
    }
    destination = Path(out).resolve() if out else run / "reports" / predictions_path.stem
    destination.mkdir(parents=True, exist_ok=False)
    write_json(destination / "metrics.json", report)
    lines = [
        "# DriftLens C03 evaluation",
        "",
        f"Status: {report['status']}",
        f"Mode: {report['execution_mode']} · L3 · unisolated",
        "",
        "| Metric | Value |",
        "| --- | --- |",
    ]
    for key in ("eligible", "precision", "recall", "f1", "coverage", "control_false_positive_rate"):
        lines.append(f"| {key} | {scores[key]} |")
    lines.extend(
        [
            "",
            "## Accounting",
            "",
            *[f"- {key}: {value}" for key, value in report["counts"].items()],
            "",
            "## Limitations",
            "",
            *[f"- {item}" for item in report["limitations"]],
            "- Positive abstentions count as missed detections in recall; coverage is reported separately.",
            "- Null metrics have zero denominators. No temporal score is computed.",
        ]
    )
    (destination / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return report
