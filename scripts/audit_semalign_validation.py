"""Revalidate saved responses offline without replacing their original run artifacts."""

import argparse
import hashlib
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from driftlens_benchmark.artifacts import digest, read_json, read_jsonl, write_json, write_jsonl
from driftlens_benchmark.contracts import validate
from driftlens_benchmark.datasets.meanings import load_meanings
from driftlens_benchmark.datasets.semalign import concepts, load_source, yaml_file
from driftlens_benchmark.provenance import benchmark_state
from driftlens_benchmark.validation.generation import validate_generation


def verify_files(root, hashes):
    """Only inspect pinned files inside the specified root."""
    for relative, expected in hashes.items():
        path = (root / relative).resolve()
        if not path.is_relative_to(root) or digest(path) != expected:
            raise ValueError("audit_input_hash_mismatch")


def diagnostics(result):
    """Probe ordering does not change diagnostic meaning."""
    return {
        "checks": result.get("checks"),
        "reasons": sorted(result.get("reasons", [])),
        "counterexamples": {c["case"]: c["matched"] for c in result.get("counterexamples", [])},
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--source", type=Path, help="Defaults to the original manifest's source_root")
    parser.add_argument("--out", type=Path, required=True, help="New aggregate JSON; no observation IDs or SQL")
    parser.add_argument("--private-out", type=Path, required=True, help="New directory for private per-response details")
    args = parser.parse_args(argv)
    run, output, private = args.run.resolve(), args.out.resolve(), args.private_out.resolve()
    manifest_path = run / "private/manifest.json"
    manifest_hash = digest(manifest_path)
    manifest = read_json(manifest_path)
    if manifest.get("status") not in {"complete", "partial"}:
        raise ValueError("audit_requires_finalized_run")
    source_root = (args.source or Path(manifest["source"]["source_root"])).resolve()
    if (
        output.exists()
        or private.exists()
        or output.is_relative_to(private)
        or private.is_relative_to(output)
        or any(path.is_relative_to(root) for path in (output, private) for root in (run, source_root))
    ):
        raise ValueError("audit_outputs_must_be_new_and_outside_inputs")
    verify_files(run, manifest["files_sha256"])
    verify_files(source_root, manifest["source"]["source_files_sha256"])
    verify_files(source_root, manifest["catalog_files_sha256"])
    source = load_source(source_root)
    catalogs, _, _ = load_meanings(source)
    ontologies = {v: concepts(yaml_file(source_root / f"ontology/{v}.yml")) for v in ("v1", "v2")}
    attempts = [validate("records/v3/attempt", a) for a in read_jsonl(run / "private/attempts.jsonl")]
    if len(attempts) != manifest["attempted"] or len({a["log_id"] for a in attempts}) != len(attempts):
        raise ValueError("audit_attempt_denominator_mismatch")
    policy = manifest.get("validation_policy", "structural")
    mode = "fixture" if manifest["source_mode"] == "synthetic_fixture" else "agent"
    original, updated, rechecked = Counter(), Counter(), Counter()
    transitions, changed_fields, check_changes, stage_errors = Counter(), Counter(), Counter(), Counter()
    changed_status = changed_eligibility = changed_diagnostics = source_false_to_true = 0
    skipped = 0
    details = []
    for attempt in attempts:
        original[attempt["status"]] += 1
        if "observation" not in attempt:
            skipped += 1
            updated[attempt["status"]] += 1
            continue
        row = attempt["observation"]
        cid, version = attempt["concept_id"], attempt["used_definition"]
        value = row["reported_values"][0]
        cutoff = value["as_of"][:10]
        snapshot_relative = f"private/snapshots/{cutoff}.sqlite"
        prefix = f"private/counterexamples/{cutoff}/"
        probe_paths = [
            run / relative
            for relative in sorted(manifest["files_sha256"])
            if relative.startswith(prefix) and relative.endswith(".sqlite")
        ]
        if snapshot_relative not in manifest["files_sha256"] or not probe_paths:
            raise ValueError("audit_missing_pinned_database")
        if attempt.get("validation_policy", "structural") != policy:
            raise ValueError("audit_validation_policy_mismatch")
        current = ontologies[version][cid]
        result = validate_generation(
            row,
            catalogs[version][cid]["semantics"],
            current["oracle_sql"],
            run / snapshot_relative,
            probe_paths,
            mode=mode,
            definition=current["definition"],
            policy=policy,
        )
        validate("records/v3/attempt", {**attempt, **result})
        updated[result["status"]] += 1
        rechecked[result["status"]] += 1
        transitions[(attempt["status"], result["status"])] += 1
        old, new = diagnostics(attempt), diagnostics(result)
        status_changed = attempt["status"] != result["status"]
        diagnostic_changed = old != new
        changed_status += status_changed
        changed_eligibility += (attempt["status"] == "validated") != (result["status"] == "validated")
        changed_diagnostics += diagnostic_changed
        for field in old:
            changed_fields[field] += old[field] != new[field]
        for check, value in new["checks"].items():
            check_changes[check] += (old["checks"] or {}).get(check) != value
        source_false_to_true += (
            (old["checks"] or {}).get("query_result_matches_reference") is False
            and new["checks"]["query_result_matches_reference"] is True
        )
        stage_errors.update(r for r in result["reasons"] if r.startswith(("snapshot:", "counterexample:")))
        details.append(
            {
                "log_id": attempt["log_id"],
                "concept_id": cid,
                "observation_sha256": hashlib.sha256(
                    json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
                ).hexdigest(),
                "status_changed": status_changed,
                "diagnostics_changed": diagnostic_changed,
                "old": {"status": attempt["status"], **old},
                "new": {"status": result["status"], **new},
            }
        )
    if len(details) != manifest["successful_response"]:
        raise ValueError("audit_successful_response_denominator_mismatch")
    # Recheck after execution before reporting immutability. No model or runner
    # entry point is imported or invoked; every SQLite input is opened read-only.
    verify_files(run, manifest["files_sha256"])
    verify_files(source_root, manifest["source"]["source_files_sha256"])
    verify_files(source_root, manifest["catalog_files_sha256"])
    if digest(manifest_path) != manifest_hash:
        raise ValueError("audit_manifest_changed")
    details_path = private / "validation-details.jsonl"
    write_jsonl(details_path, details)
    summary = {
        "audit_kind": "saved_observation_validation_only",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "model_api_calls": 0,
        "validation_policy": policy,
        "original_run_manifest_sha256": manifest_hash,
        "original_run_unchanged": True,
        "source_files_and_catalogs_match_original": True,
        "auditor_sha256": digest(Path(__file__)),
        "validator_source_hash": benchmark_state()["source_hash"],
        "planned": manifest["planned"],
        "attempted": manifest["attempted"],
        "rechecked_observations": len(details),
        "skipped_without_observation": skipped,
        "original_status_counts": dict(original),
        "rechecked_status_counts": dict(rechecked),
        "combined_status_counts": dict(updated),
        "status_changed_count": changed_status,
        "eligibility_changed_count": changed_eligibility,
        "diagnostics_changed_count": changed_diagnostics,
        "diagnostic_changes_by_field": dict(changed_fields),
        "check_changes": dict(check_changes),
        "snapshot_reference_false_to_true_count": source_false_to_true,
        "status_transitions": [
            {"old": old, "new": new, "count": count}
            for (old, new), count in sorted(transitions.items())
        ],
        "execution_error_counts": dict(stage_errors),
        "private_details_sha256": digest(details_path),
    }
    write_json(output, summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, KeyError, TypeError) as error:
        print("Audit failed: " + str(error), file=sys.stderr)
        raise SystemExit(2) from None
