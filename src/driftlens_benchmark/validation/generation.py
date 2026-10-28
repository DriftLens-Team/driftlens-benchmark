"""Private checks separate intended meaning, arithmetic, reported value and answer."""

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
    try:
        for path in probe_paths:
            expected = report(reference(path, semantics, window), unit)
            oracle = report(scalar(path, oracle_sql.format(s=s, e=e)), unit)
            if oracle != expected:
                raise ValueError("source_oracle_disagrees_with_independent_reference")
            actual = report(scalar(path, observation["sql"]), unit)
            counterexamples.append({"case": path.stem, "matched": actual == expected})
            if actual != expected:
                checks[
                    "behavioral_agreement" if policy == "behavioral" else "query_correct_for_used_definition"
                ] = False
        expected = report(reference(snapshot_path, semantics, window), unit)
        oracle = report(scalar(snapshot_path, oracle_sql.format(s=s, e=e)), unit)
        if expected != oracle:
            raise ValueError("source_oracle_disagrees_with_independent_reference")
        actual = report(scalar(snapshot_path, observation["sql"]), unit)
        checks["query_result_matches_reference"] = actual == expected
        checks["reported_value_matches_query_result"] = value["value"] == actual
        checks["answer_matches_query_result"] = answer_matches(observation, actual, mode=mode)
        if policy == "behavioral":
            checks["behavioral_agreement"] = (
                bool(counterexamples) and all(c["matched"] for c in counterexamples) and actual == expected
            )
    except ValueError as error:
        reasons.append(str(error))
        if str(error) == "source_oracle_disagrees_with_independent_reference" or str(error).startswith(
            "unsupported_reference_"
        ):
            return {
                "status": "unverified",
                "checks": checks,
                "reasons": reasons,
                "counterexamples": counterexamples,
            }
        checks["query_result_matches_reference"] = False
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
    if any(v is False for v in checks.values()):
        status = "rejected"
    elif all(v is True for v in eligibility.values()):
        status = "validated"
    else:
        status = "unverified"
    reasons.extend(k for k, v in eligibility.items() if v is not True)
    return {"status": status, "checks": checks, "reasons": reasons, "counterexamples": counterexamples}
