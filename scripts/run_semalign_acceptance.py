"""Run reproducible SemAlign acceptance steps and retain real command evidence."""

import argparse
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from time import monotonic


def main():
    """Keep each run and its unmodified stdout/stderr in a new evidence directory."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", required=True, type=Path)
    parser.add_argument("--data-python", required=True, type=Path)
    parser.add_argument("--agent-python", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument(
        "--live", action="store_true", help="Also call the configured Upstage model for all 364 requests"
    )
    parser.add_argument(
        "--env-file", type=Path, help="Explicit credential file; only UPSTAGE_MODEL/API_KEY are loaded"
    )
    args = parser.parse_args()
    repo = Path(__file__).absolute().parent.parent
    source = args.data_root.resolve()
    out = args.out.resolve()
    data_python, agent_python = str(args.data_python.absolute()), str(args.agent_python.absolute())
    if out.exists() or out.is_relative_to(source):
        raise SystemExit("Choose a new output directory outside the data checkout")
    environment = os.environ.copy()
    environment["PYTHONIOENCODING"] = "utf-8"
    environment["PYTHONUTF8"] = "1"
    environment["DRIFTLENS_SEMALIGN_AGENT_PYTHON"] = agent_python
    if args.env_file:
        for line in args.env_file.read_text(encoding="utf-8-sig").splitlines():
            key, sep, value = line.strip().removeprefix("export ").partition("=")
            if sep and key.strip() in {"UPSTAGE_MODEL", "UPSTAGE_API_KEY"}:
                environment.setdefault(key.strip(), value.strip().strip("\"'"))
    if args.live and any(not environment.get(k) for k in ("UPSTAGE_MODEL", "UPSTAGE_API_KEY")):
        raise SystemExit("Live mode requires UPSTAGE_MODEL and UPSTAGE_API_KEY")
    out.mkdir(parents=True)
    (out / "logs").mkdir()
    journal = {
        "started_at": datetime.now(timezone.utc).isoformat(),
        "status": "running",
        "live": args.live,
        "steps": [],
    }

    def record():
        """Atomic progress file for the browser evidence view and interrupted runs."""
        temporary = out / "execution.tmp"
        temporary.write_text(json.dumps(journal, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        temporary.replace(out / "execution.json")

    def execute(name, command, *, cwd=repo, allowed=(0,)):
        """Record actual argv, timestamps, output and exit status without environment values."""
        item = {
            "name": name,
            "command": list(map(str, command)),
            "cwd": str(cwd),
            "started_at": datetime.now(timezone.utc).isoformat(),
            "status": "running",
        }
        journal["steps"].append(item)
        record()
        print(f"START {name}", flush=True)
        start = monotonic()
        stdout_path, stderr_path = (
            out / "logs" / (name + ".stdout.txt"),
            out / "logs" / (name + ".stderr.txt"),
        )
        with (
            stdout_path.open("w", encoding="utf-8") as stdout,
            stderr_path.open("w", encoding="utf-8") as stderr,
        ):
            result = subprocess.run(
                list(map(str, command)), cwd=cwd, env=environment, stdout=stdout, stderr=stderr
            )
        item.update(
            exit_code=result.returncode,
            elapsed_seconds=round(monotonic() - start, 3),
            finished_at=datetime.now(timezone.utc).isoformat(),
            stdout=str(stdout_path.relative_to(out)),
            stderr=str(stderr_path.relative_to(out)),
            status="passed" if result.returncode in allowed else "failed",
        )
        record()
        print(f"END {name}: exit={result.returncode}, seconds={item['elapsed_seconds']}", flush=True)
        if result.returncode not in allowed:
            journal["status"] = "failed"
            record()
            raise SystemExit(f"{name} failed; inspect {stdout_path.name} and {stderr_path.name}")

    record()
    execute("benchmark-tests", [sys.executable, "-m", "pytest", "-q"])
    execute("benchmark-lint", [sys.executable, "-m", "ruff", "check", "src", "tests", "examples", "scripts"])
    execute("benchmark-build", [sys.executable, "-m", "build", "--wheel"])
    # Locate the agent checkout from the explicit interpreter path, including .venv/bin on POSIX.
    agent_repo = Path(agent_python).parent.parent.parent
    execute(
        "agent-tests",
        [agent_python, "-m", "unittest", "discover", "-s", "tests/unit", "-p", "test_*.py", "-v"],
        cwd=agent_repo,
    )
    execute("agent-build", [agent_python, "-m", "build", "--wheel"], cwd=agent_repo)
    execute(
        "data-tests",
        [data_python, "-m", "unittest", "discover", "-s", "tests", "-p", "test_*.py", "-v"],
        cwd=source,
    )
    execute("data-counterexamples", [data_python, "pipeline/check_edge_cases.py"], cwd=source)
    execute("data-independent-reference", [data_python, "pipeline/check_ontology.py"], cwd=source)
    bundle = out / "source"
    bundle.mkdir()
    shutil.copytree(source / "ontology", bundle / "ontology")
    shutil.copy2(source / "schema.sql", bundle / "schema.sql")
    execute("data-generate", [data_python, "pipeline/generate.py", "--out", bundle / "data"], cwd=source)
    execute("data-validate", [data_python, "pipeline/validate.py", "--data-dir", bundle / "data"], cwd=source)
    # Live generation runs first after offline preconditions pass. No sample is replaced after scoring.
    cases = [("live", bundle, "agent", "upstage", "behavioral")] if args.live else []
    cases += [
        ("original", source, "fixture", "fake", "structural"),
        ("regenerated", bundle, "fixture", "fake", "structural"),
        ("fake", bundle, "agent", "fake", "behavioral"),
    ]
    for name, data, mode, provider, policy in cases:
        run = out / name
        command = [
            sys.executable,
            "-m",
            "driftlens_benchmark",
            "run-semalign",
            "--source",
            data,
            "--mode",
            mode,
            "--provider",
            provider,
            "--agent-python",
            agent_python,
            "--validation-policy",
            policy,
            "--progress",
            "--out",
            run,
        ]
        execute(name + "-generation", command, allowed=(0, 1))
        for level in ("L0", "L1", "L2", "L3"):
            predictions = out / f"{name}-predictions-{level}"
            execute(
                f"{name}-detect-{level}",
                [
                    sys.executable,
                    "-m",
                    "driftlens_benchmark",
                    "detect-semalign",
                    "--public",
                    run / "public" / level,
                    "--out",
                    predictions,
                ],
            )
            execute(
                f"{name}-score-{level}",
                [
                    sys.executable,
                    "-m",
                    "driftlens_benchmark",
                    "evaluate-semalign",
                    "--run",
                    run,
                    "--predictions",
                    predictions,
                    "--allow-partial",
                    "--out",
                    out / f"{name}-report-{level}.json",
                ],
            )
    journal.update(status="completed", finished_at=datetime.now(timezone.utc).isoformat())
    record()
    print(f"Evidence: {out}", flush=True)


if __name__ == "__main__":
    main()
