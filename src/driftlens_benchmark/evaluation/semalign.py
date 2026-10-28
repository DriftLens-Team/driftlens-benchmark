"""Integrity-bound SemAlign scores with generation denominators and online evidence."""

from collections import Counter
from datetime import date, datetime
from pathlib import Path

from ..artifacts import digest, encoded, object_digest, read_json, read_jsonl, unique, write_json
from ..contracts import validate
from ..contracts.semalign import prediction_check
from ..detectors.numeric import numeric_signals, value_check_signals
from ..observations.projection import load_fixture_bundle


def integrity(root, files):
    """Only manifest-relative files inside the declared artifact root are readable."""
    if not isinstance(files, dict) or not files:
        raise ValueError("empty_integrity_manifest")
    for name, expected in files.items():
        path = (root / name).resolve()
        if (
            Path(name).is_absolute()
            or not path.is_relative_to(root)
            or not path.is_file()
            or digest(path) != expected
        ):
            raise ValueError("semalign_artifact_integrity")


def evidence_check(prediction, allowed, rows, *, alarm=None):
    """Reject hidden, unrelated, fabricated and future evidence independently of scores."""
    for evidence in prediction["evidence"]:
        lid = evidence["log_id"]
        if lid not in allowed:
            raise ValueError("unrelated_prediction_evidence")
        row = rows[lid]
        value = row[evidence["field"]]
        if value is None:
            raise ValueError("hidden_prediction_evidence")
        text = value if isinstance(value, str) else encoded(value)
        if evidence["quote"] not in text:
            raise ValueError("fabricated_prediction_evidence")
        if alarm is not None and row["timestamp"] > alarm:
            raise ValueError("future_prediction_evidence")


def metrics(items):
    """Items carry truth, decision and timing hit; positive abstentions remain FN."""
    tp = fp = fn = tn = abstain = neg = 0
    for item in items:
        positive, prediction, hit = item["positive"], item["prediction"], item.get("hit", True)
        neg += not positive
        if prediction is None:
            abstain += 1
        if positive:
            if prediction is True and hit:
                tp += 1
            else:
                fn += 1
                if prediction is True:
                    fp += 1
        elif prediction is True:
            fp += 1
        elif prediction is False:
            tn += 1
    counts = {
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "tn": tn,
        "abstain": abstain,
        "eligible": len(items),
        "negative": neg,
    }
    undefined = {}
    for key, numerator, denominator, reason in (
        ("precision", tp, tp + fp, "no_predicted_positives"),
        ("recall", tp, tp + fn, "no_eligible_positives"),
        ("f1", 2 * tp, 2 * tp + fp + fn, "no_positive_decisions_or_truth"),
        ("coverage", len(items) - abstain, len(items), "no_eligible_items"),
        (
            "fpr",
            sum(i["prediction"] is True and not i["positive"] for i in items),
            neg,
            "no_eligible_negatives",
        ),
    ):
        counts[key] = numerator / denominator if denominator else None
        if not denominator:
            undefined[key] = reason
    counts["undefined"] = undefined
    return counts


def aggregate(items):
    """Expose per-concept and subgroup denominators instead of only a micro score."""
    concepts = {
        cid: metrics([i for i in items if i["concept_id"] == cid])
        for cid in sorted({i["concept_id"] for i in items})
    }
    macro = {}
    for name in ("precision", "recall", "f1", "coverage", "fpr"):
        values = [m[name] for m in concepts.values() if m[name] is not None]
        macro[name] = {"value": sum(values) / len(values) if values else None, "concepts": len(values)}
    return {
        "micro": metrics(items),
        "by_concept": concepts,
        "macro": macro,
        "controls": metrics([i for i in items if i.get("is_control")]),
        "hard_negatives": metrics([i for i in items if i.get("hard_negative")]),
    }


def diagnostic_scores(signals, truth, pair_truth, series_truth, *, db_access):
    """Score independent diagnostic signals only after their label-free computation."""
    regimes = signals["regimes"]
    logs = [
        {
            "concept_id": t["concept_id"],
            "positive": t["semantic_drift"],
            "prediction": None if regimes[t["log_id"]] is None else regimes[t["log_id"]] != 0,
            "is_control": t["is_control"],
        }
        for t in truth
    ]
    pairs = []
    for t in pair_truth:
        a, b = regimes[t["log_a"]], regimes[t["log_b"]]
        pairs.append(
            {
                "concept_id": t["concept_id"],
                "positive": t["changed"],
                "prediction": None if a is None or b is None else a != b,
                "is_control": t["is_control"],
                "hard_negative": t["hard_negative"],
            }
        )
    series = []
    for t in series_truth:
        if not t["complete"]:
            continue
        p = signals["alarms"][t["concept_id"]]
        hit = True
        if p["decision"] == "change" and t["changed"]:
            hit = (
                abs(
                    (
                        date.fromisoformat(p["estimated_change_at"]) - date.fromisoformat(t["effective_at"])
                    ).days
                )
                <= 14
            )
        series.append(
            {
                "concept_id": t["concept_id"],
                "positive": t["changed"],
                "prediction": None if p["decision"] == "abstain" else p["decision"] == "change",
                "hit": hit,
                "is_control": t["is_control"],
            }
        )
    return {
        "db_access": db_access,
        "ranking_eligible": False,
        "mode": signals["mode"],
        "LOG_context": signals["LOG_context"],
        "settings": signals["settings"],
        "LOG": aggregate(logs),
        "T1": aggregate(pairs),
        "T2": aggregate(series),
        "alarms": signals["alarms"],
    }


def evaluate_semalign(run_path, prediction_path, *, allow_partial=False, out=None):
    """Score one run/level/detector; incomplete series never enter primary T2 scores."""
    root, prediction_path = Path(run_path).resolve(), Path(prediction_path).resolve()
    run = read_json(root / "private/manifest.json")
    if run.get("status") not in {"complete", "partial"}:
        raise ValueError("semalign_run_not_finalized")
    if run["status"] == "partial" and not allow_partial:
        raise ValueError("partial_run_requires_allow_partial")
    integrity(root, run["files_sha256"])
    submitted = validate("detection/v2/manifest", read_json(prediction_path / "manifest.json"))
    if submitted.get("contract_version") != "detection/v2" or submitted.get("mode") != "online":
        raise ValueError("unsupported_prediction_manifest")
    level = submitted["level"]
    if level not in {"L0", "L1", "L2", "L3"}:
        raise ValueError("invalid_prediction_level")
    public = root / "public" / level
    if submitted["public_manifest_sha256"] != digest(public / "manifest.json"):
        raise ValueError("prediction_public_binding")
    integrity(prediction_path, submitted["files"])
    bundle = load_fixture_bundle(public)
    if bundle["manifest"]["stage"] != "validated_observations":
        raise ValueError("unvalidated_preparation_bundle")
    rows = {r["log_id"]: r for r in bundle["logs"]}
    planned = read_jsonl(root / "private/planned.jsonl")
    attempts = unique(
        [validate("records/v3/attempt", row) for row in read_jsonl(root / "private/attempts.jsonl")]
    )
    truth = unique([validate("records/v3/truth", row) for row in read_jsonl(root / "private/truth.jsonl")])
    by_id = {t["log_id"]: t for t in truth}
    planned_ids = {p["request"]["request_id"] for p in planned}
    if (
        len(planned_ids) != len(planned)
        or len(planned) != run["planned"]
        or len(attempts) != run["attempted"]
        or not {a["log_id"] for a in attempts} <= planned_ids
    ):
        raise ValueError("generation_denominator_mismatch")
    counts = Counter(a["status"] for a in attempts)
    if set(counts) - {"validated", "rejected", "unverified", "failed"} or any(
        counts[k] != run[k] for k in ("validated", "rejected", "unverified", "failed")
    ):
        raise ValueError("generation_status_mismatch")
    if (
        run["successful_response"] != len(attempts) - counts["failed"]
        or set(by_id) != {a["log_id"] for a in attempts if a["status"] == "validated"}
        or set(by_id) != set(rows)
    ):
        raise ValueError("generation_eligibility_mismatch")
    for lid, t in by_id.items():
        rv = rows[lid]["reported_values"][0]
        if (
            any(type(t[k]) is not bool for k in ("semantic_drift", "output_changed", "is_control"))
            or t["concept_id"] != rv["concept_id"]
            or t["window"] != rv["window"]
            or t["timestamp"] != rows[lid]["timestamp"]
        ):
            raise ValueError("private_truth_mismatch")
    public_pairs = {p["pair_id"]: p for p in bundle["pairs"]}
    pair_truth = unique(
        [validate("records/v3/pairs-truth", row) for row in read_jsonl(root / "private/pairs.truth.jsonl")],
        "pair_id",
    )
    series_truth = unique(
        [validate("records/v3/series-truth", row) for row in read_jsonl(root / "private/series.truth.jsonl")],
        "concept_id",
    )
    groups = {s["concept_id"]: s for s in bundle["series"]}
    if {t["pair_id"] for t in pair_truth} != set(public_pairs) or {
        s["concept_id"] for s in series_truth
    } != set(groups):
        raise ValueError("private_task_ids")
    predictions = {}
    for task, key, expected in (
        ("log", "log_id", set(rows)),
        ("pairs", "pair_id", set(public_pairs)),
        ("series", "concept_id", set(groups)),
    ):
        values = unique(
            [prediction_check(task, p) for p in read_jsonl(prediction_path / (task + ".jsonl"))], key
        )
        if {p[key] for p in values} != expected:
            raise ValueError("prediction_id_set_mismatch")
        predictions[task] = {p[key]: p for p in values}
    for lid, p in predictions["log"].items():
        if p["concept_id"] != by_id[lid]["concept_id"]:
            raise ValueError("prediction_concept_mismatch")
        evidence_check(p, {lid}, rows)
    for pid, p in predictions["pairs"].items():
        pair = public_pairs[pid]
        if p["concept_id"] != pair["concept_id"]:
            raise ValueError("prediction_concept_mismatch")
        evidence_check(p, {pair["log_a"], pair["log_b"]}, rows)
    for cid, p in predictions["series"].items():
        ids = set(groups[cid]["log_ids"])
        evidence_check(p, ids, rows, alarm=p["alarm_at"])
        if p["decision"] == "change":
            if p["alarm_at"] not in {rows[lid]["timestamp"] for lid in ids} or p[
                "estimated_change_at"
            ] not in {
                by_id[lid]["window"]["start"][:10] for lid in ids if rows[lid]["timestamp"] <= p["alarm_at"]
            }:
                raise ValueError("invalid_online_alarm")
    # The stored online views must equal the public prefixes, not just carry hashes.
    trace = [
        validate("detection/v2/online-step", row) for row in read_jsonl(prediction_path / "online.jsonl")
    ]
    definitions = {d["concept_id"]: d for d in bundle["baseline"]["definitions"]}
    expected_files = {"log.jsonl", "pairs.jsonl", "series.jsonl", "online.jsonl"}
    if len(trace) != len(rows):
        raise ValueError("online_trace_coverage")
    trace_by_concept = {cid: [] for cid in groups}
    for t in trace:
        if t["concept_id"] not in groups:
            raise ValueError("online_trace_concept")
        trace_by_concept[t["concept_id"]].append(t)
    for cid, group in groups.items():
        prefix = []
        first_alarm = None
        entries = trace_by_concept[cid]
        if len(entries) != len(group["log_ids"]):
            raise ValueError("online_trace_coverage")
        for index, (lid, t) in enumerate(zip(group["log_ids"], entries, strict=True)):
            prefix.append(rows[lid])
            view = {
                "baseline": {
                    "definition": definitions[cid],
                    "schema": bundle["baseline"]["schema"],
                    "period": bundle["baseline"]["period"],
                },
                "observations": prefix,
            }
            name = f"online/{cid}/{index:03}.json"
            expected_files.add(name)
            if (
                t["step"] != index
                or t["view_file"] != name
                or t["cutoff"] != rows[lid]["timestamp"]
                or t["view_sha256"] != object_digest(view)
                or read_json(prediction_path / name) != view
            ):
                raise ValueError("online_view_mismatch")
            p = prediction_check("series", t["prediction"])
            if p["concept_id"] != cid:
                raise ValueError("online_prediction_concept")
            evidence_check(p, {r["log_id"] for r in prefix}, rows, alarm=p["alarm_at"])
            if p["decision"] == "change" and first_alarm is None:
                if p["alarm_at"] != t["cutoff"]:
                    raise ValueError("online_alarm_submission_time")
                first_alarm = p
            if first_alarm is not None and p != first_alarm:
                raise ValueError("online_first_alarm_rewritten")
        final = predictions["series"][cid]
        if entries and final != entries[-1]["prediction"]:
            raise ValueError("online_final_prediction_mismatch")
        if not entries and final["decision"] != "abstain":
            raise ValueError("empty_series_requires_abstain")
    if set(submitted["files"]) != expected_files:
        raise ValueError("prediction_file_set_mismatch")
    log_items = []
    for t in truth:
        p = predictions["log"][t["log_id"]]
        log_items.append(
            {
                "concept_id": t["concept_id"],
                "positive": t["semantic_drift"],
                "prediction": None if p["decision"] == "abstain" else p["decision"] == "drift",
                "is_control": t["is_control"],
            }
        )
    pair_items = []
    for t in pair_truth:
        pair = public_pairs[t["pair_id"]]
        if (
            any(t[k] != v for k, v in pair.items())
            or type(t["changed"]) is not bool
            or t["changed"]
            != (by_id[t["log_a"]]["definition_fingerprint"] != by_id[t["log_b"]]["definition_fingerprint"])
        ):
            raise ValueError("private_pair_truth")
        p = predictions["pairs"][t["pair_id"]]
        pair_items.append(
            {
                "concept_id": t["concept_id"],
                "positive": t["changed"],
                "prediction": None if p["decision"] == "abstain" else p["decision"] == "changed",
                "is_control": t["is_control"],
                "hard_negative": t["hard_negative"],
            }
        )
    series_items, delays = [], []
    excluded_series = []
    for t in series_truth:
        cid = t["concept_id"]
        planned_group = {p["request"]["request_id"] for p in planned if p["request"]["concept_id"] == cid}
        if (
            set(t["planned_log_ids"]) != planned_group
            or t["eligible_log_ids"] != groups[cid]["log_ids"]
            or t["complete"] != (set(t["eligible_log_ids"]) == planned_group)
        ):
            raise ValueError("private_series_completeness")
        if not t["complete"]:
            excluded_series.append(
                {
                    "concept_id": cid,
                    "reason": "incomplete_validated_series",
                    "planned": len(planned_group),
                    "eligible": len(t["eligible_log_ids"]),
                }
            )
            continue
        p = predictions["series"][cid]
        pred = None if p["decision"] == "abstain" else p["decision"] == "change"
        hit = True
        if t["changed"] and pred is True:
            error = (
                date.fromisoformat(p["estimated_change_at"]) - date.fromisoformat(t["effective_at"])
            ).days / 7
            hit = abs(error) <= 2
            alarm_row = next(
                by_id[lid] for lid in t["eligible_log_ids"] if by_id[lid]["timestamp"] == p["alarm_at"]
            )
            first = min(
                by_id[lid]["timestamp"] for lid in t["eligible_log_ids"] if by_id[lid]["semantic_drift"]
            )
            delays.append(
                {
                    "concept_id": cid,
                    "hit": hit,
                    "estimate_error_weeks": error,
                    "alarm_delay_weeks": (
                        date.fromisoformat(alarm_row["window"]["start"][:10])
                        - date.fromisoformat(t["effective_at"])
                    ).days
                    / 7,
                    "arrival_delay_seconds": (
                        datetime.fromisoformat(p["alarm_at"]) - datetime.fromisoformat(first)
                    ).total_seconds(),
                }
            )
        series_items.append(
            {
                "concept_id": cid,
                "positive": t["changed"],
                "prediction": pred,
                "hit": hit,
                "is_control": t["is_control"],
            }
        )
    numeric = numeric_signals(bundle)
    value_check = value_check_signals(bundle, {t["log_id"]: t["output_changed"] for t in truth})
    exclusion_reasons = Counter()
    if run.get("artifact_revision", 1) >= 2:
        all_pairs = unique(
            [validate("records/v3/pair", p) for p in read_jsonl(root / "private/planned-pairs.jsonl")],
            "pair_id",
        )
        if len(all_pairs) != run["planned_pairs"]:
            raise ValueError("planned_pair_denominator")
        statuses = {a["log_id"]: a["status"] for a in attempts}
        expected_eligible = set()
        for pair in all_pairs:
            if not {pair["log_a"], pair["log_b"]} <= planned_ids:
                raise ValueError("planned_pair_log_ids")
            states = [statuses.get(pair[k], "not_attempted") for k in ("log_a", "log_b")]
            if states == ["validated", "validated"]:
                expected_eligible.add(pair["pair_id"])
                if public_pairs.get(pair["pair_id"]) != pair:
                    raise ValueError("eligible_pair_projection")
            else:
                exclusion_reasons["|".join(states)] += 1
        if expected_eligible != set(public_pairs):
            raise ValueError("eligible_pair_set")
    elif run["planned_pairs"] > len(pair_items):
        exclusion_reasons["not_recorded_by_prior_writer"] = run["planned_pairs"] - len(pair_items)
    result = {
        "status": run["status"],
        "scope": "development_filtered" if run["status"] == "partial" else "development",
        "source_mode": run["source_mode"],
        "model_execution": run["model_execution"],
        "level": level,
        "detector": submitted["detector"],
        "mode": "online",
        "isolation": "unisolated",
        "db_access": False,
        "generation": {
            k: run[k]
            for k in (
                "planned",
                "attempted",
                "successful_response",
                "failed",
                "validated",
                "rejected",
                "unverified",
            )
        },
        "planned_completion_rate": run["attempted"] / run["planned"] if run["planned"] else None,
        "generation_valid_rate": run["validated"] / run["attempted"] if run["attempted"] else None,
        "quality_by_concept": run["quality_by_concept"],
        "quality_by_sql_shape": run.get("quality_by_sql_shape"),
        "validation_dependence": "shared_sql_meaning_extractor_with_independent_row_and_counterexample_checks",
        "accuracy_claim": "development_consistency_only; filtered SQL scores are not independent detector accuracy",
        "LOG": aggregate(log_items),
        "T1": aggregate(pair_items),
        "T2": aggregate(series_items),
        "pair_eligibility": {
            "planned": run["planned_pairs"],
            "eligible": len(pair_items),
            "excluded": run["planned_pairs"] - len(pair_items),
        },
        "pair_exclusions_by_reason": dict(exclusion_reasons),
        "excluded_series": excluded_series,
        "series_eligibility": {
            "planned": len(series_truth),
            "complete": len(series_items),
            "excluded": len(series_truth) - len(series_items),
        },
        "timing": delays,
        "unresolved_series": sum(p["decision"] == "abstain" for p in predictions["series"].values()),
        "db_value_diagnostic": diagnostic_scores(
            value_check, truth, pair_truth, series_truth, db_access=True
        ),
        "numeric_diagnostic": diagnostic_scores(numeric, truth, pair_truth, series_truth, db_access=False),
        "run_manifest_sha256": digest(root / "private/manifest.json"),
        "prediction_manifest_sha256": digest(prediction_path / "manifest.json"),
    }
    if out is not None:
        write_json(out, result)
    return result
