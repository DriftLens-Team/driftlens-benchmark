"""Small command boundary; execution stages remain callable independently."""

import argparse
import sys
from pathlib import Path

import yaml

from . import __version__


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
        else:
            from .evaluation.scoring import evaluate

            report = evaluate(args.run, args.predictions, allow_partial=args.allow_partial, out=args.out)
            print(f"{report['status']}: F1={report['micro']['f1']}, coverage={report['micro']['coverage']}")
        return 0
    except (ValueError, OSError, yaml.YAMLError, KeyError) as error:
        print(f"Benchmark failed: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
