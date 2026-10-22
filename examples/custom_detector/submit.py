"""Minimal external prediction submission: public input only, constant no-drift decisions."""

import argparse
from pathlib import Path

from driftlens_benchmark.artifacts import digest, write_json, write_jsonl
from driftlens_benchmark.observations.records import load_public


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--public", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    sidecar = args.out.with_suffix(args.out.suffix + ".manifest.json")
    if args.out.exists() or sidecar.exists():
        parser.error("Choose a new output file.")
    _, rows = load_public(args.public)
    predictions = [
        {
            "log_id": row["log_id"],
            "result_id": "r1",
            "concept_id": "large_orders",
            "decision": "no_drift",
            "evidence_log_ids": [],
            "evidence_summary": "External constant baseline example.",
        }
        for row in rows
    ]
    write_jsonl(args.out, predictions)
    write_json(
        sidecar,
        {
            "contract_version": "detection/v1",
            "detector": "external-constant-example",
            "detector_version": "1",
            "isolation": "unisolated",
            "predictions_sha256": digest(args.out),
            "public_manifest_sha256": digest(args.public / "manifest.json"),
        },
    )


if __name__ == "__main__":
    main()
