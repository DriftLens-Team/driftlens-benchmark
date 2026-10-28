"""Private checks separate intended meaning, arithmetic, reported value and answer."""

from ..semantics.notes import extract_note
from ..semantics.sql import extract
from .answers import answer_matches
from .references import reference, report, scalar


def validate_generation(
    observation, semantics, oracle_sql, snapshot_path, probe_paths, *, mode, definition=None
):
    """Produce auditable check states; detector decisions never become generation truth."""
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
    extracted = extract(observation["sql"], cid, window)
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
                checks["query_correct_for_used_definition"] = False
        expected = report(reference(snapshot_path, semantics, window), unit)
        oracle = report(scalar(snapshot_path, oracle_sql.format(s=s, e=e)), unit)
        if expected != oracle:
            raise ValueError("source_oracle_disagrees_with_independent_reference")
        actual = report(scalar(snapshot_path, observation["sql"]), unit)
        checks["query_result_matches_reference"] = actual == expected
        checks["reported_value_matches_query_result"] = value["value"] == actual
        checks["answer_matches_query_result"] = answer_matches(observation, actual, mode=mode)
    except ValueError as error:
        reasons.append(str(error))
        if str(error) == "source_oracle_disagrees_with_independent_reference":
            return {
                "status": "unverified",
                "checks": checks,
                "reasons": reasons,
                "counterexamples": counterexamples,
            }
        checks["query_result_matches_reference"] = False
    note = extract_note(observation["definition_note"], cid)
    if definition is not None and observation["definition_note"] == definition:
        note = semantics
    if note is not None and extracted is not None:
        checks["definition_note_consistent"] = all(extracted.get(k) == v for k, v in note.items())
    if any(v is False for v in checks.values()):
        status = "rejected"
    elif all(v is True for v in checks.values()):
        status = "validated"
    else:
        status = "unverified"
    reasons.extend(k for k, v in checks.items() if v is not True)
    return {"status": status, "checks": checks, "reasons": reasons, "counterexamples": counterexamples}
