"""Generate or import, privately validate, then project one SemAlign run."""

import os
import subprocess
import sys
from collections import Counter
from copy import deepcopy
from pathlib import Path
from uuid import uuid4

import sqlglot

from .adapters.jsonl import exchange
from .artifacts import digest, object_digest, read_jsonl, strict_json, write_json, write_jsonl
from .contracts import validate
from .contracts.semalign import LEVELS, observation_check
from .datasets.meanings import load_meanings
from .datasets.semalign import concepts, load_source, yaml_file
from .datasets.snapshots import snapshot
from .observations.projection import project_fixture
from .provenance import benchmark_state
from .validation.generation import validate_generation
from .validation.references import probes, reference, report


def run_semalign(
    source_root,
    output,
    *,
    mode="fixture",
    agent_python=None,
    provider="fake",
    limit=None,
    model_env="UPSTAGE_MODEL",
    key_env="UPSTAGE_API_KEY",
):
    """Keep failures in the denominator; only verified observations enter public files."""
    source = load_source(source_root)
    output = Path(output).resolve()
    if output.exists() or output.is_relative_to(source.root):
        raise ValueError("semalign_output_not_new")
    if mode not in {"fixture", "agent"} or provider not in {"fake", "upstage"}:
        raise ValueError("invalid_semalign_mode")
    if limit is not None and (type(limit) is not int or limit <= 0):
        raise ValueError("invalid_request_limit")
    catalogs, baseline, catalog_hashes = load_meanings(source)
    ontologies = {v: concepts(yaml_file(source.root / f"ontology/{v}.yml")) for v in ("v1", "v2")}
    command = [str(Path(agent_python or sys.executable).resolve()), "-m", "driftlens_sql_agent"]
    capabilities = None
    if mode == "agent":
        try:
            check = subprocess.run(
                command + ["--capabilities"], capture_output=True, text=True, encoding="utf-8", timeout=10
            )
        except subprocess.SubprocessError:
            raise ValueError("agent_capabilities_failed") from None
        if check.returncode or len(check.stdout) > 65536:
            raise ValueError("agent_capabilities_failed")
        capabilities = strict_json(check.stdout)
        if type(capabilities) is not dict or any(
            type(capabilities.get(k)) is not list or any(type(v) is not str for v in capabilities[k])
            for k in ("protocols", "schemas", "concepts")
        ):
            raise ValueError("invalid_agent_capabilities")
        if (
            "agent/v2" not in capabilities.get("protocols", [])
            or "semalign/v1" not in capabilities.get("schemas", [])
            or set(capabilities.get("concepts", [])) != {s["concept_id"] for s in source.series}
            or capabilities.get("definition_note_origin") != "profile_rendered"
        ):
            raise ValueError("incompatible_semalign_agent")
        if provider == "upstage" and (not os.environ.get(model_env) or not os.environ.get(key_env)):
            raise ValueError("model_credentials_unavailable")
    output.mkdir(parents=True, exist_ok=False)
    private = output / "private"
    mapping = {
        r["observation"]["log_id"]: ("obs_" + uuid4().hex if mode == "agent" else r["observation"]["log_id"])
        for r in source.imported
    }
    planned = []
    for imported, request in zip(source.imported, source.requests, strict=True):
        planned.append(
            {
                "source_log_id": imported["source_log_id"],
                "request": {**request, "request_id": mapping[request["request_id"]]},
                "source_truth": imported["source_truth"],
            }
        )
    write_jsonl(private / "planned.jsonl", planned)
    manifest = {
        "contract_version": "records/v3",
        "artifact_revision": 2,
        "status": "running",
        "source_mode": "synthetic_fixture" if mode == "fixture" else "agent",
        "planned": len(planned),
        "attempted": 0,
        "successful_response": 0,
        "failed": 0,
        "validated": 0,
        "rejected": 0,
        "unverified": 0,
        "source": source.manifest,
        "catalog_files_sha256": catalog_hashes,
        "benchmark": benchmark_state(),
        "agent_capabilities": capabilities,
        "provider": provider if mode == "agent" else None,
        "model_id": os.environ.get(model_env) if mode == "agent" and provider == "upstage" else None,
        "model_execution": "live"
        if mode == "agent" and provider == "upstage"
        else "deterministic_fake"
        if mode == "agent"
        else "source_fixture",
        "definition_note_origin": "profile_rendered" if mode == "agent" else "source_template",
        "isolation": "unisolated",
        "snapshots": {},
        "validation_scope": "meaning_and_execution",
    }
    write_json(private / "manifest.json", manifest)
    attempts, truth, validated_rows = [], [], []
    probe_cache = {}
    planned_selection = planned[:limit] if limit else planned
    for index, plan in enumerate(planned_selection):
        request = plan["request"]
        rid, cid = request["request_id"], request["concept_id"]
        used = plan["source_truth"]["version_used"]
        semantics = catalogs[used][cid]["semantics"]
        current = ontologies[used][cid]
        cutoff = request["as_of"]
        db = private / "snapshots" / (cutoff[:10] + ".sqlite")
        if cutoff not in manifest["snapshots"]:
            manifest["snapshots"][cutoff] = snapshot(source.root / "data/jaffle.sqlite", db, cutoff)
            probe_cache[cutoff] = probes(private / "counterexamples" / cutoff[:10], request["window"])
        attempt = {"log_id": rid, "concept_id": cid, "used_definition": used, "status": "failed"}
        manifest["attempted"] += 1
        try:
            if mode == "fixture":
                row = deepcopy(source.imported[index]["observation"])
            else:
                profile = {
                    "concept_id": cid,
                    **{k: current[k] for k in ("label", "definition", "unit")},
                    "semantics": semantics,
                }
                work = private / "requests" / rid
                write_json(work / "profile.json", profile)
                write_json(
                    work / "config.json",
                    {
                        "database": {"kind": "sqlite", "path": str(db), "read_only": True},
                        "schema_id": "semalign/v1",
                        "model": {"provider": provider, "id_env": model_env, "api_key_env": key_env},
                    },
                )
                write_json(work / "request.json", request)
                observation, diagnostics = exchange(
                    command
                    + [
                        "--config",
                        str(work / "config.json"),
                        "--profile",
                        str(work / "profile.json"),
                        "--protocol-version",
                        "v2",
                    ],
                    request,
                    cwd=work,
                    timeout=65,
                    protocol="agent/v2",
                )
                attempt["diagnostics"] = diagnostics
                row = {
                    "log_id": rid,
                    "request": request["request"],
                    "timestamp": request["timestamp"],
                    "team": "semalign",
                    "agent_id": "sql-agent",
                    **observation,
                }
            observation_check(row, level="L3")
            manifest["successful_response"] += 1
            attempt["observation"] = row
            try:
                attempt["sql_shape"] = dict(
                    Counter(node.key for node in sqlglot.parse_one(row["sql"], read="sqlite").walk())
                )
            except (sqlglot.errors.SqlglotError, RecursionError):
                attempt["sql_shape"] = {"unparsed": 1}
            validation = validate_generation(
                row,
                semantics,
                current["oracle_sql"],
                db,
                probe_cache[cutoff],
                mode=mode,
                definition=current["definition"],
            )
            attempt.update(validation)
            if validation["status"] == "validated":
                base = catalogs["v1"][cid]["semantics"]
                changed = base != semantics
                truth.append(
                    {
                        "log_id": rid,
                        "result_id": "r1",
                        "concept_id": cid,
                        "semantic_drift": changed,
                        "output_changed": report(reference(db, base, request["window"]), current["unit"])
                        != row["reported_values"][0]["value"],
                        "definition_fingerprint": object_digest(semantics),
                        "is_control": plan["source_truth"]["is_control"],
                        "effective_at": plan["source_truth"]["effective_at"],
                        "window": request["window"],
                        "timestamp": request["timestamp"],
                    }
                )
                validated_rows.append(row)
            manifest[validation["status"]] += 1
        except ValueError as error:
            # Adapter failures are recorded, never converted into null observations.
            if "observation" in attempt:
                manifest["unverified"] += 1
                attempt["status"] = "unverified"
            else:
                manifest["failed"] += 1
            if hasattr(error, "diagnostics"):
                attempt["diagnostics"] = error.diagnostics
            attempt["error"] = str(error)
        validate("records/v3/attempt", attempt)
        attempts.append(attempt)
        write_json(private / "attempts" / (rid + ".json"), attempt)
        write_json(private / "manifest.json", manifest, replace=True)
    by_id = {t["log_id"]: t for t in truth}
    pairs, pair_truth, planned_pairs = [], [], []
    source_pair_truth = {p["pair_id"]: p for p in read_jsonl(source.root / "data/pairs_truth.jsonl")}
    for pair in source.pairs:
        row = {**pair, "log_a": mapping[pair["log_a"]], "log_b": mapping[pair["log_b"]]}
        planned_pairs.append(row)
        if row["log_a"] not in by_id or row["log_b"] not in by_id:
            continue
        a, b = (by_id[row[k]] for k in ("log_a", "log_b"))
        changed = a["definition_fingerprint"] != b["definition_fingerprint"]
        pairs.append(row)
        pair_truth.append(
            {
                **row,
                "changed": changed,
                "is_control": a["is_control"],
                "hard_negative": source_pair_truth[row["pair_id"]]["spans_event"] and not changed,
            }
        )
    series, series_truth = [], []
    for group in source.series:
        ids = [mapping[lid] for lid in group["log_ids"]]
        eligible = [lid for lid in ids if lid in by_id]
        cid = group["concept_id"]
        entry = next(p["source_truth"] for p in planned if p["request"]["concept_id"] == cid)
        series.append({"concept_id": cid, "log_ids": eligible})
        series_truth.append(
            {
                "concept_id": cid,
                "planned_log_ids": ids,
                "eligible_log_ids": eligible,
                "complete": len(ids) == len(eligible),
                "is_control": entry["is_control"],
                "effective_at": entry["effective_at"],
                "changed": entry["effective_at"] is not None
                and catalogs["v1"][cid]["semantics"] != catalogs["v2"][cid]["semantics"],
            }
        )
    for level in LEVELS:
        public = output / "public" / level
        write_json(public / "baseline.json", baseline)
        write_jsonl(public / "logs.jsonl", [project_fixture(r, level) for r in validated_rows])
        write_jsonl(public / "pairs.jsonl", pairs)
        write_json(public / "series.json", series)
        write_json(
            public / "manifest.json",
            validate(
                "records/v3/public-manifest",
                {
                    "contract_version": "records/v3",
                    "level": level,
                    "source_mode": manifest["source_mode"],
                    "stage": "validated_observations",
                    "validation_scope": "meaning_and_execution",
                    "generation_validation": "performed",
                    "files": {
                        name: digest(public / name)
                        for name in ("baseline.json", "logs.jsonl", "pairs.jsonl", "series.json")
                    },
                },
            ),
        )
    write_jsonl(private / "attempts.jsonl", attempts)
    write_jsonl(private / "planned-pairs.jsonl", planned_pairs)
    write_jsonl(private / "truth.jsonl", [validate("records/v3/truth", row) for row in truth])
    write_jsonl(
        private / "pairs.truth.jsonl", [validate("records/v3/pairs-truth", row) for row in pair_truth]
    )
    write_jsonl(
        private / "series.truth.jsonl", [validate("records/v3/series-truth", row) for row in series_truth]
    )
    if any(
        digest(source.root / name) != h
        for name, h in {**source.manifest["source_files_sha256"], **catalog_hashes}.items()
    ):
        raise ValueError("source_changed_during_run")
    shapes = {}
    for attempt in attempts:
        shape = attempt.get("sql_shape", {"unavailable": 1})
        key = object_digest(shape)
        group = shapes.setdefault(key, {"shape": shape, "statuses": Counter()})
        group["statuses"][attempt["status"]] += 1
    manifest.update(
        status="complete" if manifest["validated"] == manifest["planned"] else "partial",
        execution_complete=manifest["attempted"] == manifest["planned"],
        planned_pairs=len(source.pairs),
        eligible_pairs=len(pairs),
        complete_series=sum(s["complete"] for s in series_truth),
        quality_by_concept={
            cid: dict(Counter(a["status"] for a in attempts if a["concept_id"] == cid))
            for cid in catalogs["v1"]
        },
        quality_by_sql_shape=list(shapes.values()),
        validation_dependence="shared_sql_meaning_extractor_with_independent_row_and_counterexample_checks",
    )
    manifest["files_sha256"] = {
        p.relative_to(output).as_posix(): digest(p)
        for p in sorted(output.rglob("*"))
        if p.is_file() and p != private / "manifest.json"
    }
    write_json(private / "manifest.json", manifest, replace=True)
    return manifest
