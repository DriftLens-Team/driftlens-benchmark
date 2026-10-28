"""Small command boundary; execution stages remain callable independently."""

import argparse
import sys
from pathlib import Path

import yaml

from . import __version__
from .artifacts import encoded


def main(argv=None):
    parser = argparse.ArgumentParser(description="SQL semantic drift benchmark")
    parser.add_argument("--version", action="version", version=__version__)
    commands = parser.add_subparsers(dest="command", required=True)
    validation = commands.add_parser("validate", help="Validate suite assets and dataset checksums")
    validation.add_argument("--suite", required=True, type=Path)
    running = commands.add_parser("run", help="Generate C03 observations through an external agent")
    running.add_argument("--config", required=True, type=Path)
    running.add_argument("--out", required=True, type=Path)
    detection = commands.add_parser("detect", help="Read public inputs only and write predictions")
    detection.add_argument("--public", required=True, type=Path)
    detection.add_argument("--detector", choices=["sql-rules", "no-drift"], required=True)
    detection.add_argument("--out", required=True, type=Path)
    scoring = commands.add_parser("evaluate", help="Score predictions against private truth")
    scoring.add_argument("--run", required=True, type=Path)
    scoring.add_argument("--predictions", required=True, type=Path)
    scoring.add_argument("--allow-partial", action="store_true")
    scoring.add_argument("--out", type=Path)
    inspection = commands.add_parser("inspect-data", help="Validate a local driftlens-data checkout")
    inspection.add_argument("--source", required=True, type=Path)
    preparation = commands.add_parser(
        "prepare-data", help="Prepare agent/v2 requests and records/v3 fixtures"
    )
    preparation.add_argument("--source", required=True, type=Path)
    preparation.add_argument("--out", required=True, type=Path)
    semalign = commands.add_parser(
        "run-semalign", help="Generate/import and privately validate SemAlign observations"
    )
    semalign.add_argument("--source", required=True, type=Path)
    semalign.add_argument("--out", required=True, type=Path)
    semalign.add_argument("--mode", choices=["fixture", "agent"], default="fixture")
    semalign.add_argument("--agent-python", type=Path)
    semalign.add_argument("--provider", choices=["fake", "upstage"], default="fake")
    semalign.add_argument("--limit", type=int)
    semalign.add_argument("--model-env", default="UPSTAGE_MODEL")
    semalign.add_argument("--key-env", default="UPSTAGE_API_KEY")
    semalign_detect = commands.add_parser(
        "detect-semalign", help="Public-only LOG/T1 and online T2 predictions"
    )
    semalign_detect.add_argument("--public", required=True, type=Path)
    semalign_detect.add_argument("--out", required=True, type=Path)
    semalign_detect.add_argument(
        "--detector",
        choices=["semantic-combined", "semantic-sql", "semantic-note", "no-drift"],
        default="semantic-combined",
    )
    semalign_score = commands.add_parser(
        "evaluate-semalign", help="Score bound SemAlign predictions with quality denominators"
    )
    semalign_score.add_argument("--run", required=True, type=Path)
    semalign_score.add_argument("--predictions", required=True, type=Path)
    semalign_score.add_argument("--allow-partial", action="store_true")
    semalign_score.add_argument("--out", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.command == "validate":
            from .settings import load_suite

            suite = load_suite(args.suite)
            print(f"Validated {suite.config['suite_id']} assets. Runtime behavior is checked by run/tests.")
        elif args.command == "run":
            from .runner import run

            result = run(args.config, args.out)
            print(
                f"{result['status']}: {result['eligible_observations']}/{result['expected_requests']} eligible; "
                f"artifacts: {args.out.resolve()}"
            )
            return 0 if result["status"] == "complete" else 1
        elif args.command == "detect":
            from .detectors.baselines import detect

            predictions = detect(args.public, args.detector, args.out)
            print(f"Wrote {len(predictions)} predictions: {args.out.resolve()}")
        elif args.command == "evaluate":
            from .evaluation.scoring import evaluate

            report = evaluate(args.run, args.predictions, allow_partial=args.allow_partial, out=args.out)
            print(f"{report['status']}: F1={report['micro']['f1']}, coverage={report['micro']['coverage']}")
        elif args.command == "run-semalign":
            from .semalign_runner import run_semalign

            result = run_semalign(
                args.source,
                args.out,
                mode=args.mode,
                agent_python=args.agent_python,
                provider=args.provider,
                limit=args.limit,
                model_env=args.model_env,
                key_env=args.key_env,
            )
            print(
                encoded(
                    {
                        k: result[k]
                        for k in (
                            "status",
                            "planned",
                            "attempted",
                            "validated",
                            "rejected",
                            "unverified",
                            "failed",
                        )
                    }
                )
            )
            return 0 if result["status"] == "complete" else 1
        elif args.command == "detect-semalign":
            from .detectors.semalign import detect_semalign

            print(encoded(detect_semalign(args.public, args.out, method=args.detector)))
        elif args.command == "evaluate-semalign":
            from .evaluation.semalign import evaluate_semalign

            result = evaluate_semalign(
                args.run, args.predictions, allow_partial=args.allow_partial, out=args.out
            )
            print(
                encoded(
                    {
                        "status": result["status"],
                        "LOG": result["LOG"]["micro"],
                        "T1": result["T1"]["micro"],
                        "T2": result["T2"]["micro"],
                    }
                )
            )
        else:
            from .datasets.semalign import load_source, prepare_source

            result = (
                load_source(args.source).summary()
                if args.command == "inspect-data"
                else prepare_source(args.source, args.out)
            )
            print(encoded(result))
        return 0
    except (ValueError, OSError, yaml.YAMLError, KeyError) as error:
        print(f"Benchmark failed: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
