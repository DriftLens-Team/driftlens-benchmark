"""Orchestrate environment → external agent → private truth → public observations."""

import os
import random
import sys
from datetime import date, timedelta
from pathlib import Path

from .adapters.jsonl import AgentFailure, exchange
from .artifacts import digest, object_digest, write_json, write_jsonl
from .contracts import week
from .environments.build import load_orders, snapshot
from .environments.sql import count
from .observations.records import export_public, make_truth
from .observations.sql_semantics import CountMeaning, meaning, render_reference
from .provenance import benchmark_state, package_state
from .settings import load_run


def agent_config(database, agent):
    return {
        "database": {"kind": "sqlite", "path": str(database.resolve()), "read_only": True},
        "schema_mapping": {
            "table": "orders",
            "order_id": "order_id",
            "ordered_at": "ordered_at",
            "amount": "order_total_cents",
        },
        "amount_unit": "integer_cents",
        "model": {
            "provider": agent["provider"],
            "id_env": agent["model_id_env"],
            "api_key_env": agent["api_key_env"],
        },
    }


def run(config_path, out):
    config, agent, suite, hashes = load_run(config_path)
    rows = load_orders(suite.orders)
    start = date.fromisoformat(suite.config["start"])
    end = start + timedelta(weeks=suite.config["weeks"])
    dates = [row[1] for row in rows]
    if str(start) < min(dates) or str(end - timedelta(days=1)) > max(dates):
        raise ValueError("requested_full_weeks_outside_source_span")
    if agent["provider"] == "upstage" and any(
        not os.environ.get(agent[key], "").strip() for key in ("model_id_env", "api_key_env")
    ):
        raise ValueError("missing_live_agent_environment")
    for version, sql in suite.references.items():
        rendered = render_reference(sql, str(start), str(start + timedelta(days=7)))
        if meaning(rendered) != CountMeaning(
            str(start), str(start + timedelta(days=7)), suite.definitions[version]["threshold"]
        ):
            raise ValueError("reference_definition_mismatch")
    out = Path(out).resolve()
    out.mkdir(parents=True, exist_ok=False)
    private = out / "private"
    private.mkdir()
    manifest_path = private / "run.private.json"
    rng = random.Random(config["seed"])

    def identifier():
        return "obs_" + f"{rng.getrandbits(128):032x}"

    agents = {arm: "agent_" + f"{rng.getrandbits(64):016x}" for arm in ("changed", "control")}
    command = [sys.executable if item == "{python}" else item for item in agent["command"]]
    manifest = {
        "contract_version": "records/v2",
        "status": "running",
        "suite": suite.config,
        "dataset_id": suite.dataset["dataset_id"],
        "seed": config["seed"],
        "benchmark": benchmark_state(),
        "asset_hashes": {**suite.hashes, **hashes},
        "agent": {
            "command": command,
            "protocol": "agent/v1",
            "provider": agent["provider"],
            "installed_package": package_state("driftlens-sql-agent")
            if command[:3] == [sys.executable, "-m", "driftlens_sql_agent"]
            else None,
            "model_id": os.environ.get(agent["model_id_env"]) if agent["provider"] == "upstage" else None,
        },
        "execution_mode": "external_agent_fake" if agent["provider"] == "fake" else "external_agent_live",
        "isolation": "unisolated",
        "timezone": "UTC",
        "naive_input_timezone": "UTC",
        "expected_requests": suite.config["weeks"] * 2,
        "attempted_requests": 0,
        "generation_failures": 0,
        "eligible_observations": 0,
        "successful_responses": 0,
        "rejected_observations": 0,
        "unverified_observations": 0,
        "requests": [],
    }
    write_json(manifest_path, manifest)
    write_json(
        private / "scenarios.private.json",
        {"definitions": suite.definitions, "references": suite.references, "case": suite.case},
    )
    truths, failures = [], []
    try:
        for index in range(suite.config["weeks"]):
            begin = start + timedelta(weeks=index)
            iso = begin.isocalendar()
            period = f"{iso.year:04d}-W{iso.week:02d}"
            begin, finish, timestamp = week(period)
            database = out / "environment" / f"snapshot-{index:04d}.sqlite"
            snapshot(rows, suite.schema, database, str(finish))
            snapshot_hash = digest(database)
            reference_results = {
                v: count(database, sql, {"start": str(begin), "end": str(finish)})
                for v, sql in suite.references.items()
            }
            arms = ["changed", "control"]
            rng.shuffle(arms)
            for arm in arms:
                log_id = identifier()
                version = (
                    "v2" if arm == "changed" and timestamp[:10] >= suite.config["effective_at"] else "v1"
                )
                request = {
                    "request_id": log_id,
                    "request": suite.questions[index % len(suite.questions)]["request"],
                    "timestamp": timestamp,
                    "period": period,
                }
                workspace = private / "agent" / log_id
                workspace.mkdir(parents=True)
                runtime = agent_config(database, agent)
                write_json(workspace / "config.json", runtime)
                write_json(workspace / "profile.json", suite.definitions[version])
                entry = {
                    "log_id": log_id,
                    "request": request,
                    "arm": arm,
                    "definition_version": version,
                    "snapshot_sha256": snapshot_hash,
                    "config_hash": object_digest(runtime),
                    "definition_hash": object_digest(suite.definitions[version]),
                }
                manifest["attempted_requests"] += 1
                try:
                    observation, diagnostics = exchange(
                        [
                            *command,
                            "--config",
                            str(workspace / "config.json"),
                            "--profile",
                            str(workspace / "profile.json"),
                            "--protocol-version",
                            "v1",
                        ],
                        request,
                        cwd=workspace,
                        timeout=agent["timeout_seconds"],
                    )
                    entry["diagnostics"] = diagnostics
                    manifest["successful_responses"] += 1
                    if digest(database) != snapshot_hash:
                        raise ValueError("snapshot_modified_during_agent_execution")
                    truth = make_truth(
                        observation,
                        request,
                        log_id=log_id,
                        agent_id=agents[arm],
                        database=database,
                        definitions=suite.definitions,
                        version=version,
                        reference_results=reference_results,
                        arm=arm,
                        effective_at=suite.config["effective_at"] if arm == "changed" else None,
                    )
                    truths.append(truth)
                    entry["status"] = truth["validation_status"]
                except AgentFailure as error:
                    entry.update({"status": "failed", "error": error.code, "diagnostics": error.diagnostics})
                    failures.append({"log_id": log_id, "error": error.code})
                except ValueError:
                    # Do not put arbitrary query/error text or credentials into public diagnostics.
                    entry.update({"status": "failed", "error": "observation_validation_failed"})
                    failures.append({"log_id": log_id, "error": "observation_validation_failed"})
                manifest["requests"].append(entry)
                write_json(manifest_path, manifest, replace=True)
        write_jsonl(private / "truth.jsonl", truths)
        write_jsonl(private / "failures.jsonl", failures)
        export_public(out / "public" / "L3", truths, suite.definitions["v1"])
        manifest.update(
            {
                "generation_failures": len(failures),
                "eligible_observations": sum(r["validation_status"] == "validated" for r in truths),
                "rejected_observations": sum(r["validation_status"] == "rejected" for r in truths),
                "unverified_observations": sum(r["validation_status"] == "unverified" for r in truths),
                "truth_sha256": digest(private / "truth.jsonl"),
                "failures_sha256": digest(private / "failures.jsonl"),
                "public_manifest_sha256": digest(out / "public" / "L3" / "manifest.json"),
            }
        )
        manifest["status"] = (
            "complete" if manifest["eligible_observations"] == manifest["expected_requests"] else "partial"
        )
    except BaseException:
        manifest["status"] = "failed"
        raise
    finally:
        write_json(manifest_path, manifest, replace=True)
    return manifest
