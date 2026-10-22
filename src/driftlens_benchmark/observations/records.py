"""Private observations are the source of public records, never regenerated outputs."""

import re
from copy import deepcopy

from ..artifacts import digest, read_json, read_jsonl, unique, write_json, write_jsonl
from ..contracts import observation_check, validate, validator, week
from ..environments.sql import count
from .sql_semantics import CountMeaning, meaning

PUBLIC_FIELDS = tuple(validator("records/v2/observation").schema["properties"])


def make_truth(
    observation,
    request,
    *,
    log_id,
    agent_id,
    database,
    definitions,
    version,
    reference_results,
    arm,
    effective_at,
):
    start, end, timestamp = week(request["period"])
    reported = observation["reported_values"][0]["value"]
    row = {
        "log_id": log_id,
        "timestamp": timestamp,
        "agent_id": agent_id,
        "team": "analytics",
        "request": request["request"],
        "sql": observation["sql"],
        "answer_text": observation["answer_text"],
        "definition_note": observation["definition_note"],
        "reported_values": [
            {
                "result_id": "r1",
                "concept_id": "large_orders",
                "type": "scalar",
                "value": reported,
                "unit": "count",
                "window": {"start": str(start) + "T00:00:00Z", "end": str(end) + "T00:00:00Z"},
                "as_of": timestamp,
            }
        ],
        "referenced_concepts": ["large_orders"],
    }
    observation_check(row)
    actual = count(database, observation["sql"])
    interpreted = meaning(observation["sql"])
    correct = (
        interpreted == CountMeaning(str(start), str(end), definitions[version]["threshold"])
        if interpreted is not None
        else None
    )
    answer_matches = bool(
        re.fullmatch(
            rf"(?:이번 주 |해당 주의 |주간 )?대형 주문(?:은 | 수는 | 건수는 ){actual}건입니다\.",
            row["answer_text"],
        )
    )
    result_matches = actual == reference_results[version]
    flags = (correct, answer_matches, result_matches, actual == reported)
    status = "rejected" if False in flags else "unverified" if None in flags else "validated"

    def result(value):
        return {"type": "scalar", "value": value, "unit": "count"}

    row.update(
        {
            "concept_truth": [
                {
                    "result_id": "r1",
                    "baseline_definition_version": "v1",
                    "definition_version_used": version,
                    "semantic_drift": version != "v1",
                    "baseline_result": result(reference_results["v1"]),
                    "used_definition_result": result(reference_results[version]),
                    "output_changed": reference_results["v1"] != reference_results[version],
                    "query_correct_for_used_definition": correct,
                    "answer_matches_query_result": answer_matches,
                }
            ],
            "validation_status": status,
            "execution": {
                "case_id": "C03",
                "arm": arm,
                "effective_at": effective_at,
                "snapshot_sha256": digest(database),
                "query_result_matches_reference": result_matches,
                "reported_value_matches_query_result": actual == reported,
            },
        }
    )
    validate("records/v2/truth", row)
    return row


def project(row):
    validate("records/v2/truth", row)
    # Deep-copy and validate the entire nested schema; unknown nested metadata fails closed.
    return observation_check({key: deepcopy(row[key]) for key in PUBLIC_FIELDS})


def export_public(path, truths, baseline_definition):
    path.mkdir(parents=True, exist_ok=False)
    baseline = {"contract_version": "records/v2", "definitions": [{**baseline_definition, "version": "v1"}]}
    validate("records/v2/baseline", baseline)
    write_json(path / "baseline.json", baseline)
    # Unverified and rejected observations remain in private truth and denominators only.
    write_jsonl(
        path / "logs.jsonl", [project(row) for row in truths if row["validation_status"] == "validated"]
    )
    write_json(
        path / "manifest.json",
        {
            "contract_version": "records/v2",
            "level": "L3",
            "files": {name: digest(path / name) for name in ("baseline.json", "logs.jsonl")},
        },
    )


def load_public(path):
    manifest = validate("records/v2/public-manifest", read_json(path / "manifest.json"))
    for name, expected in manifest["files"].items():
        if digest(path / name) != expected:
            raise ValueError("public_integrity_mismatch")
    baseline = validate("records/v2/baseline", read_json(path / "baseline.json"))
    rows = unique([observation_check(row) for row in read_jsonl(path / "logs.jsonl")])
    if [r["timestamp"] for r in rows] != sorted(r["timestamp"] for r in rows):
        raise ValueError("observations_not_chronological")
    return baseline, rows
