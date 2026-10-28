"""Public-only LOG/T1 comparisons and prefix-fed, first-alarm online T2."""

from datetime import datetime, timedelta
from pathlib import Path

from ..artifacts import digest, object_digest, write_json, write_jsonl
from ..contracts import validate
from ..contracts.semalign import prediction_check
from ..observations.projection import load_fixture_bundle
from ..provenance import benchmark_state
from ..semantics.notes import extract_note
from ..semantics.sql import extract

METHODS = ("semantic-combined", "semantic-sql", "semantic-note", "no-drift")


def interpret(row, baseline, method):
    """Fuse full meanings; a shared boolean drift conclusion cannot hide conflicts."""
    result = row["reported_values"][0]
    sql = (
        extract(row["sql"], result["concept_id"], result["window"])
        if row["sql"] and method in {"semantic-combined", "semantic-sql"}
        else None
    )
    note = (
        extract_note(row["definition_note"], result["concept_id"])
        if row["definition_note"] and method in {"semantic-combined", "semantic-note"}
        else None
    )
    if method in {"semantic-combined", "semantic-note"} and row["definition_note"] == baseline["definition"]:
        note = baseline["semantics"].copy()
    evidence = []
    for field, value in (("sql", sql), ("definition_note", note)):
        if value is not None:
            evidence.append({"log_id": row["log_id"], "field": field, "quote": row[field]})
    if sql is not None and note is not None and any(k in sql and sql[k] != v for k, v in note.items()):
        return None, "evidence_conflict", evidence
    required = set(baseline["required_slots"])
    value = (
        sql
        if sql is not None and set(sql) >= required
        else note
        if note is not None and set(note) >= required
        else None
    )
    if value is None:
        reason = "unsupported_sql" if row["sql"] and method != "semantic-note" else "insufficient_evidence"
        return None, reason, evidence
    reason = "equivalent_definition" if value == baseline["semantics"] else "definition_mismatch"
    return value, reason, evidence


def log_prediction(row, baseline, method):
    """LOG compares one observation to the public baseline, never a future log."""
    meaning, reason, evidence = interpret(row, baseline, method)
    decision = "abstain" if meaning is None else "no_drift" if meaning == baseline["semantics"] else "drift"
    if method == "no-drift":
        decision, reason, evidence = "no_drift", "constant_baseline", []
    return prediction_check(
        "log",
        {
            "log_id": row["log_id"],
            "result_id": "r1",
            "concept_id": baseline["concept_id"],
            "decision": decision,
            "reason_code": reason,
            "evidence": evidence,
            "evidence_summary": reason,
            "slot_differences": [
                {"slot": k, "baseline": baseline["semantics"][k], "observed": meaning[k]}
                for k in baseline["required_slots"]
                if meaning is not None and meaning[k] != baseline["semantics"][k]
            ],
        },
    )


def pair_prediction(pair, rows, baseline, method):
    """T1 compares two meanings directly, including two different drift meanings."""
    a, ar, ae = interpret(rows[pair["log_a"]], baseline, method)
    b, br, be = interpret(rows[pair["log_b"]], baseline, method)
    if a is None or b is None:
        decision, reason = (
            "abstain",
            "evidence_conflict" if "evidence_conflict" in (ar, br) else "insufficient_evidence",
        )
    else:
        decision, reason = (
            ("unchanged", "equivalent_definition") if a == b else ("changed", "definition_mismatch")
        )
    if method == "no-drift":
        decision, reason, ae, be = "unchanged", "constant_baseline", [], []
    return prediction_check(
        "pairs",
        {
            "pair_id": pair["pair_id"],
            "concept_id": pair["concept_id"],
            "decision": decision,
            "reason_code": reason,
            "evidence": ae + be,
            "evidence_summary": reason,
        },
    )


def online_step(view, state, method):
    """Accept only the current prefix; state has no pair index or future observations."""
    baseline = view["baseline"]
    cid = baseline["definition"]["concept_id"]
    if state.get("alarm") is not None:
        return state["alarm"]
    prediction = {
        "concept_id": cid,
        "decision": "abstain",
        "estimated_change_at": None,
        "alarm_at": None,
        "reason_code": "insufficient_evidence",
        "evidence": [],
        "evidence_summary": "No confirmed change.",
    }
    rows = view["observations"]
    if not rows:
        return prediction_check("series", prediction)
    row = rows[-1]
    current, reason, evidence = interpret(row, baseline["definition"], method)
    window = datetime.fromisoformat(row["reported_values"][0]["window"]["start"])
    previous = state.get("candidate")
    state.setdefault("all_same", True)
    if current is None or current != baseline["definition"]["semantics"]:
        state["all_same"] = False
    if current is not None and current != baseline["definition"]["semantics"]:
        if previous and previous["meaning"] == current and window - previous["window"] == timedelta(days=7):
            prediction.update(
                decision="change",
                estimated_change_at=previous["window"].date().isoformat(),
                alarm_at=row["timestamp"],
                reason_code="definition_mismatch",
                evidence=previous["evidence"] + evidence,
                evidence_summary="Same changed meaning in two consecutive weeks.",
            )
            state["alarm"] = prediction_check("series", prediction)
            return state["alarm"]
        state["candidate"] = {"meaning": current, "window": window, "evidence": evidence}
    else:
        state["candidate"] = None
    start, end = (datetime.fromisoformat(baseline["period"][k]) for k in ("start", "end"))
    expected = [
        (start + timedelta(days=7 * i)).isoformat().replace("+00:00", "Z")
        for i in range((end - start).days // 7)
    ]
    complete = [r["reported_values"][0]["window"]["start"] for r in rows] == expected
    if complete and (state["all_same"] or method == "no-drift"):
        prediction.update(
            decision="no_change",
            reason_code="constant_baseline" if method == "no-drift" else "equivalent_definition",
            evidence_summary="All scheduled weeks observed without a confirmed definition change.",
            evidence=evidence,
        )
    elif reason == "evidence_conflict":
        prediction.update(reason_code=reason, evidence=evidence, evidence_summary=reason)
    return prediction_check("series", prediction)


def detect_semalign(public_path, output, *, method="semantic-combined"):
    """Write separately bound predictions and a reproducible hash for each online input."""
    public_path, output = Path(public_path).resolve(), Path(output).resolve()
    if method not in METHODS:
        raise ValueError("unsupported_semalign_detector")
    bundle = load_fixture_bundle(public_path)
    baseline = bundle["baseline"]
    if (
        "schema" not in baseline
        or "period" not in baseline
        or any("semantics" not in d for d in baseline["definitions"])
    ):
        raise ValueError("public_semantic_catalog_required")
    if output.exists() or output.is_relative_to(public_path):
        raise ValueError("prediction_output_not_new")
    output.mkdir(parents=True, exist_ok=False)
    definitions = {d["concept_id"]: d for d in baseline["definitions"]}
    rows = {r["log_id"]: r for r in bundle["logs"]}
    logs = [
        log_prediction(r, definitions[r["reported_values"][0]["concept_id"]], method) for r in bundle["logs"]
    ]
    pairs = [pair_prediction(p, rows, definitions[p["concept_id"]], method) for p in bundle["pairs"]]
    series, trace = [], []
    # LOG and T1 carry no state into online T2. Each group receives fresh state.
    for group in bundle["series"]:
        cid = group["concept_id"]
        state = {}
        prefix = []
        view = {
            "baseline": {
                "definition": definitions[cid],
                "schema": baseline["schema"],
                "period": baseline["period"],
            },
            "observations": prefix,
        }
        prediction = online_step(view, state, method)
        for index, lid in enumerate(group["log_ids"]):
            prefix.append(rows[lid])
            prediction = online_step(view, state, method)
            name = f"online/{cid}/{index:03}.json"
            write_json(output / name, view)
            trace.append(
                {
                    "concept_id": cid,
                    "step": index,
                    "cutoff": rows[lid]["timestamp"],
                    "view_file": name,
                    "view_sha256": object_digest(view),
                    "prediction": prediction,
                }
            )
        series.append(prediction)
    for name, data in (
        ("log.jsonl", logs),
        ("pairs.jsonl", pairs),
        ("series.jsonl", series),
        ("online.jsonl", trace),
    ):
        write_jsonl(output / name, data)
    manifest = {
        "contract_version": "detection/v2",
        "detector": method,
        "version": "0.1",
        "level": bundle["manifest"]["level"],
        "public_manifest_sha256": digest(public_path / "manifest.json"),
        "mode": "online",
        "isolation": "unisolated",
        "settings": {"confirmation_weeks": 2},
        "implementation": benchmark_state(),
        "files": {
            p.relative_to(output).as_posix(): digest(p) for p in sorted(output.rglob("*")) if p.is_file()
        },
    }
    write_json(output / "manifest.json", validate("detection/v2/manifest", manifest))
    return {"log": len(logs), "pairs": len(pairs), "series": len(series), "online_steps": len(trace)}
