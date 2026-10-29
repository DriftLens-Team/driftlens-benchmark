"""Private checks separate intended meaning, arithmetic, reported value and answer."""

import sqlite3

from ..semantics.notes import extract_note
from ..semantics.sql import extract
from .answers import answer_matches
from .references import reference, report, scalar


def validate_generation(
    observation,
    semantics,
    oracle_sql,
    snapshot_path,
    probe_paths,
    *,
    mode,
    definition=None,
    policy="structural",
):
    """Produce auditable check states; detector decisions never become generation truth."""
    if policy not in {"structural", "behavioral"}:
        raise ValueError("invalid_validation_policy")
    value = observation["reported_values"][0]
    unit, window, cid = value["unit"], value["window"], value["concept_id"]
    s, e = (window[k][:10] for k in ("start", "end"))
    checks = {
        key: None
        for key in (
            "query_correct_for_used_definition",
            "query_result_matches_reference",
            "reported_value_matches_query_result",
            "answer_matches_query_result",
            "definition_note_consistent",
        )
    }
    reasons = []
    # The behavioral gate never calls the detector's SQL or note extractors.
    # Passing a finite probe suite establishes agreement, not semantic proof.
    extracted = extract(observation["sql"], cid, window) if policy == "structural" else None
    if policy == "behavioral":
        checks["behavioral_agreement"] = None
    if extracted is not None:
        checks["query_correct_for_used_definition"] = extracted == semantics
    counterexamples = []

    def expected_at(path, stage):
        """Reference failures describe an unavailable judge, not a wrong response."""
        try:
            expected = report(reference(path, semantics, window), unit)
        except (ValueError, sqlite3.Error, OSError) as error:
            reason = str(error) if isinstance(error, ValueError) else "reference_execution_failed"
            reasons.append(f"{stage}:reference:{reason}")
            return False, None
        try:
            oracle = report(scalar(path, oracle_sql.format(s=s, e=e)), unit)
        except (ValueError, OSError) as error:
            reason = str(error) if isinstance(error, ValueError) else "oracle_execution_failed"
            reasons.append(f"{stage}:oracle:{reason}")
            return False, None
        if oracle != expected:
            reasons.append(f"{stage}:oracle:source_oracle_disagrees_with_independent_reference")
            return False, None
        return True, expected

    def unverified():
        return {"status": "unverified", "checks": checks, "reasons": reasons, "counterexamples": counterexamples}

    # Snapshot checks must not inherit a later counterexample execution error.
    verified, expected = expected_at(snapshot_path, "snapshot")
    if not verified:
        return unverified()
    query_failed = False
    try:
        actual = report(scalar(snapshot_path, observation["sql"]), unit)
        checks["query_result_matches_reference"] = actual == expected
        checks["reported_value_matches_query_result"] = value["value"] == actual
        checks["answer_matches_query_result"] = answer_matches(observation, actual, mode=mode)
    except ValueError as error:
        query_failed = True
        reasons.append(f"snapshot:query:{error}")
        # No scalar was produced, so numeric and answer comparisons stay unknown.
    for path in probe_paths:
        stage = f"counterexample:{path.stem}"
        verified, expected = expected_at(path, stage)
        if not verified:
            return unverified()
        try:
            actual = report(scalar(path, observation["sql"]), unit)
            matched = actual == expected
        except ValueError as error:
            query_failed = True
            matched = False
            reasons.append(f"{stage}:query:{error}")
        counterexamples.append({"case": path.stem, "matched": matched})
    probe_failed = any(not case["matched"] for case in counterexamples)
    if policy == "behavioral":
        if query_failed or probe_failed or checks["query_result_matches_reference"] is False:
            checks["behavioral_agreement"] = False
        elif counterexamples and checks["query_result_matches_reference"] is True:
            checks["behavioral_agreement"] = True
    elif query_failed or probe_failed:
        checks["query_correct_for_used_definition"] = False
    if policy == "behavioral":
        # An exact host-rendered definition is verifiable without the detector.
        # A paraphrase is unknown here, not evidence of a contradiction.
        checks["definition_note_consistent"] = (
            True if definition is not None and observation["definition_note"] == definition else None
        )
    else:
        note = extract_note(observation["definition_note"], cid)
        if definition is not None and observation["definition_note"] == definition:
            note = semantics
        if note is not None and extracted is not None:
            checks["definition_note_consistent"] = all(extracted.get(k) == v for k, v in note.items())
    eligibility = {
        k: v for k, v in checks.items() if policy != "behavioral" or k != "query_correct_for_used_definition"
    }
    if query_failed or any(v is False for v in checks.values()):
        status = "rejected"
    elif all(v is True for v in eligibility.values()):
        status = "validated"
    else:
        status = "unverified"
    reasons.extend(k for k, v in eligibility.items() if v is not True)
    return {"status": status, "checks": checks, "reasons": reasons, "counterexamples": counterexamples}
