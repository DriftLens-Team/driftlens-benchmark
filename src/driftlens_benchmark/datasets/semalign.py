"""Read driftlens-data and prepare versioned inputs, without claiming semantic validation."""

import sqlite3
import subprocess
from collections import Counter
from contextlib import closing
from copy import deepcopy
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

import yaml

from ..artifacts import digest, encoded, read_jsonl, unique, write_json, write_jsonl
from ..contracts import validate, validator
from ..contracts.semalign import (
    CONCEPT_UNITS,
    LEVELS,
    baseline_check,
    observation_check,
    request_check,
)
from ..observations.projection import project_fixture
from ..settings import Loader

DATASET_ID = "semalign-v0.1"
SOURCE_FILES = (
    "ontology/v1.yml",
    "ontology/v2.yml",
    "ontology/scenario.private.yml",
    "schema.sql",
    "data/jaffle.sqlite",
    "data/truth.jsonl",
    "data/pairs.jsonl",
    "data/pairs_truth.jsonl",
    *(f"data/logs.{level}.jsonl" for level in LEVELS),
)
PUBLIC_FIELDS = set(validator("records/v3/observation").schema["properties"])
TRUTH_FIELDS = {
    "log_id",
    "concept_id",
    "version_used",
    "drift_id",
    "effective_at",
    "is_control",
    "contaminated",
    "validation_status",
}
PAIR_TRUTH_FIELDS = {
    "pair_id",
    "concept_id",
    "log_a",
    "log_b",
    "case_id",
    "is_control",
    "changed",
    "spans_event",
    "hard_negative",
}
TABLE_COLUMNS = {
    "orders": {
        "order_id",
        "customer_id",
        "ordered_at",
        "location_id",
        "subtotal_cents",
        "tax_paid_cents",
        "order_total_cents",
    },
    "order_items": {"order_item_id", "order_id", "product_id"},
    "products": {"product_id", "product_name", "product_type", "product_price_cents", "product_description"},
    "locations": {"location_id", "location_name", "opened_at", "tax_rate"},
}


def keys(value, expected, *, optional=()):
    """Check source envelopes before normalization can discard unexpected fields."""
    if type(value) is not dict or not set(expected) <= set(value) <= set(expected) | set(optional):
        raise ValueError("invalid_semalign_source_fields")


def source_date(value):
    """Reject timestamps and noncanonical compact dates in date-only source fields."""
    if type(value) is not str:
        raise ValueError("invalid_semalign_source_date")
    parsed = date.fromisoformat(value)
    if parsed.isoformat() != value:
        raise ValueError("invalid_semalign_source_date")
    return parsed


def yaml_file(path):
    """Use the benchmark's duplicate-key/finite-number YAML rules for all ontologies."""
    document = yaml.load(path.read_text(encoding="utf-8"), Loader=Loader)
    encoded(document)
    if type(document) is not dict:
        raise ValueError("invalid_semalign_yaml")
    return document


def concepts(document):
    """Read only declared metric metadata; do not execute or import upstream code."""
    found = {}
    metrics = [m for model in document["models"] for m in model.get("metrics", [])]
    for metric in metrics + document.get("metrics", []):
        meta = metric.get("config", {}).get("meta", {})
        if "concept_id" not in meta:
            continue
        cid = meta["concept_id"]
        if cid not in CONCEPT_UNITS or cid in found or meta.get("unit") != CONCEPT_UNITS[cid]:
            raise ValueError("invalid_semalign_ontology_concepts")
        if any(type(meta.get(k)) is not str or not meta[k].strip() for k in ("definition", "oracle_sql")):
            raise ValueError("invalid_semalign_ontology_definition")
        found[cid] = {**meta, "label": metric["label"]}
    if set(found) != set(CONCEPT_UNITS):
        raise ValueError("incomplete_semalign_ontology")
    return found


def normalize_log(row, *, level):
    """Convert dates to UTC instants, preserving the actual question timestamp."""
    keys(row, PUBLIC_FIELDS)
    converted = deepcopy(row)
    values = converted["reported_values"]
    if type(values) is not list or len(values) != 1:
        raise ValueError("invalid_semalign_result_count")
    rv = values[0]
    keys(rv, {"result_id", "concept_id", "type", "value", "unit", "window", "as_of"})
    keys(rv["window"], {"start", "end"})
    for key in ("start", "end"):
        rv["window"][key] = source_date(rv["window"][key]).isoformat() + "T00:00:00Z"
    rv["as_of"] = source_date(rv["as_of"]).isoformat() + "T00:00:00Z"
    stamp = converted["timestamp"]
    if type(stamp) is not str or "T" not in stamp:
        raise ValueError("invalid_semalign_source_timestamp")
    parsed = datetime.fromisoformat(stamp)
    if parsed.microsecond:
        raise ValueError("subsecond_semalign_timestamp_unsupported")
    naive = parsed.tzinfo is None
    parsed = parsed.replace(tzinfo=timezone.utc) if naive else parsed.astimezone(timezone.utc)
    converted["timestamp"] = parsed.isoformat().replace("+00:00", "Z")
    return observation_check(converted, level=level), naive


@dataclass(frozen=True)
class SemAlignSource:
    root: Path
    manifest: dict
    baseline: dict
    imported: list
    requests: list
    pairs: list
    series: list

    def summary(self):
        """Return non-secret progress counts without the scenario or source paths."""
        return {
            "dataset_id": DATASET_ID,
            "observations": len(self.imported),
            "concepts": len(self.series),
            "weeks": self.manifest["weeks"],
            "pairs": len(self.pairs),
            "levels": list(LEVELS),
            "validation_scope": "structure_and_alignment",
            "generation_validation": "not_run",
            "naive_timestamp_assumption": "UTC",
            "naive_timestamp_count": self.manifest["naive_timestamp_count"],
            "source_warning_count": len(self.manifest["source_warnings"]),
        }


def load_source(root):
    """Validate source alignment and construct clean agent/v2 requests in memory."""
    root = Path(root).resolve()
    resources = {name: (root / name).resolve() for name in SOURCE_FILES}
    if any(not path.is_file() or not path.is_relative_to(root) for path in resources.values()):
        raise ValueError("missing_or_external_semalign_resource")
    hashes = {name: digest(path) for name, path in resources.items()}
    ontologies = {v: concepts(yaml_file(resources[f"ontology/{v}.yml"])) for v in ("v1", "v2")}
    scenario = yaml_file(resources["ontology/scenario.private.yml"])
    keys(scenario, {"period", "concepts"}, optional={"events"})
    keys(scenario["period"], {"start", "end"})
    start, end = (source_date(scenario["period"][key]) for key in ("start", "end"))
    days = (end - start).days
    if start.weekday() != 0 or days <= 0 or days % 7:
        raise ValueError("invalid_semalign_period")
    weeks = [start + timedelta(days=offset) for offset in range(0, days, 7)]
    plan = {}
    cases = set()
    source_warnings = []
    for entry in scenario["concepts"]:
        required = {"case_id", "concept_id", "role", "effective_at", "difficulty"}
        if type(entry) is not dict:
            raise ValueError("invalid_semalign_scenario_entry")
        extra = set(entry) - required - {"source_case", "note"}
        # The upstream flow-style note contains an unquoted comma. YAML parses its
        # trailing prose as a null key. Preserve it privately and report it, but
        # never reinterpret it as an execution setting or silently repair the file.
        if extra:
            if type(entry.get("note")) is not str or any(entry[k] is not None for k in extra):
                raise ValueError("invalid_semalign_scenario_annotation")
            source_warnings.append(
                {
                    "code": "unparsed_scenario_note",
                    "concept_id": entry.get("concept_id"),
                    "annotation_keys": sorted(extra),
                }
            )
        keys(entry, required, optional={"source_case", "note"} | extra)
        cid = entry["concept_id"]
        if cid not in CONCEPT_UNITS or cid in plan or entry["case_id"] in cases:
            raise ValueError("invalid_semalign_scenario_concepts")
        if type(entry["case_id"]) is not str or not entry["case_id"].strip():
            raise ValueError("invalid_semalign_case_id")
        effective = entry["effective_at"]
        if entry["role"] == "drift":
            if source_date(effective) not in weeks[1:] or entry["difficulty"] not in {
                "easy",
                "medium",
                "hard",
            }:
                raise ValueError("invalid_semalign_change_schedule")
        elif (
            entry["role"] != "control"
            or effective is not None
            or entry["difficulty"] not in {"normal", "hard_negative"}
        ):
            raise ValueError("invalid_semalign_control")
        plan[cid] = entry
        cases.add(entry["case_id"])
    if set(plan) != set(CONCEPT_UNITS):
        raise ValueError("incomplete_semalign_scenario")
    events = []
    for event in scenario.get("events", []):
        keys(event, {"week", "name"}, optional={"note"})
        event_week = source_date(event["week"])
        if event_week not in weeks:
            raise ValueError("invalid_semalign_event_week")
        events.append(event_week)

    source_rows = read_jsonl(resources["data/logs.L3.jsonl"])
    unique(source_rows)
    rows, naive_count = [], 0
    for row in source_rows:
        normalized, naive = normalize_log(row, level="L3")
        rows.append(normalized)
        naive_count += naive
    expected = {(cid, w.isoformat() + "T00:00:00Z") for cid in plan for w in weeks}
    observed = Counter(
        (r["reported_values"][0]["concept_id"], r["reported_values"][0]["window"]["start"]) for r in rows
    )
    if observed != Counter({key: 1 for key in expected}):
        raise ValueError("semalign_concept_week_coverage")
    if [r["timestamp"] for r in rows] != sorted(r["timestamp"] for r in rows):
        raise ValueError("semalign_logs_not_chronological")
    originals = {r["log_id"]: r for r in source_rows}
    for level, drop in LEVELS.items():
        if level == "L3":
            continue
        projected = unique(read_jsonl(resources[f"data/logs.{level}.jsonl"]))
        if {r["log_id"] for r in projected} != set(originals):
            raise ValueError("semalign_level_id_mismatch")
        if [r["log_id"] for r in projected] != [r["log_id"] for r in source_rows]:
            raise ValueError("semalign_level_order_mismatch")
        for row in projected:
            normalize_log(row, level=level)
            if row != {k: None if k in drop else v for k, v in originals[row["log_id"]].items()}:
                raise ValueError("semalign_level_content_mismatch")

    source_truth = unique(read_jsonl(resources["data/truth.jsonl"]))
    truth_by_id = {t["log_id"]: t for t in source_truth}
    if set(truth_by_id) != set(originals):
        raise ValueError("semalign_truth_id_mismatch")
    imported, requests, mapping = [], [], {}
    for row in rows:
        source_id = row["log_id"]
        truth = truth_by_id[source_id]
        keys(truth, TRUTH_FIELDS)
        value = row["reported_values"][0]
        cid, window = value["concept_id"], value["window"]
        entry = plan[cid]
        changed = entry["effective_at"] is not None and window["start"][:10] >= entry["effective_at"]
        expected_truth = {
            "concept_id": cid,
            "version_used": "v2" if changed else "v1",
            "drift_id": entry["case_id"],
            "effective_at": entry["effective_at"],
            "is_control": entry["role"] == "control",
            "contaminated": changed,
            "validation_status": "executed_on_source_csv",
        }
        if any(type(truth[k]) is not bool for k in ("is_control", "contaminated")) or any(
            truth[k] != v for k, v in expected_truth.items()
        ):
            raise ValueError("semalign_truth_schedule_mismatch")
        new_id = "obs_" + uuid5(NAMESPACE_URL, f"{DATASET_ID}/{source_id}").hex
        mapping[source_id] = new_id
        row = {**row, "log_id": new_id}
        request = request_check(
            {
                "request_id": new_id,
                "request": row["request"],
                "timestamp": row["timestamp"],
                "concept_id": cid,
                "window": deepcopy(window),
                "as_of": value["as_of"],
            }
        )
        requests.append(request)
        imported.append({"source_log_id": source_id, "observation": row, "source_truth": truth})

    raw_pairs = unique(read_jsonl(resources["data/pairs.jsonl"]), "pair_id")
    pair_truth = unique(read_jsonl(resources["data/pairs_truth.jsonl"]), "pair_id")
    pair_truth = {p["pair_id"]: p for p in pair_truth}
    if {p["pair_id"] for p in raw_pairs} != set(pair_truth):
        raise ValueError("semalign_pair_truth_ids")
    if Counter(p["concept_id"] for p in raw_pairs) != Counter({cid: 16 for cid in plan}):
        raise ValueError("semalign_pair_coverage")
    normalized = {source["log_id"]: row for source, row in zip(source_rows, rows, strict=True)}
    pairs, seen_pairs, positive_counts = [], set(), Counter()
    for pair in raw_pairs:
        validate("records/v3/pair", pair)
        if pair["log_a"] not in normalized or pair["log_b"] not in normalized:
            raise ValueError("semalign_pair_unknown_log")
        av, bv = (normalized[pair[k]]["reported_values"][0] for k in ("log_a", "log_b"))
        cid = pair["concept_id"]
        aw, bw = (source_date(v["window"]["start"][:10]) for v in (av, bv))
        identity = (pair["log_a"], pair["log_b"])
        if cid != av["concept_id"] or cid != bv["concept_id"] or identity in seen_pairs:
            raise ValueError("semalign_pair_concept_or_duplicate")
        seen_pairs.add(identity)
        if not 7 <= (bw - aw).days <= 56:
            raise ValueError("semalign_pair_gap")
        entry = plan[cid]
        changed = entry["effective_at"] is not None and aw < source_date(entry["effective_at"]) <= bw
        spans = any(aw < event <= bw for event in events)
        truth = pair_truth[pair["pair_id"]]
        keys(truth, PAIR_TRUTH_FIELDS)
        expected_pair = {
            **pair,
            "case_id": entry["case_id"],
            "is_control": entry["role"] == "control",
            "changed": changed,
            "spans_event": spans,
            "hard_negative": spans and not changed,
        }
        if (
            any(type(truth[k]) is not bool for k in ("is_control", "changed", "spans_event", "hard_negative"))
            or truth != expected_pair
        ):
            raise ValueError("semalign_pair_truth_mismatch")
        positive_counts[cid] += changed
        pairs.append({**pair, "log_a": mapping[pair["log_a"]], "log_b": mapping[pair["log_b"]]})
    if any(positive_counts[cid] != (8 if e["role"] == "drift" else 0) for cid, e in plan.items()):
        raise ValueError("semalign_pair_balance")

    baseline = baseline_check(
        {
            "contract_version": "records/v3",
            "definitions": [
                {"concept_id": cid, **{k: meta[k] for k in ("label", "definition", "unit")}}
                for cid, meta in sorted(ontologies["v1"].items())
            ],
        }
    )
    series = [
        {
            "concept_id": cid,
            "log_ids": [
                r["observation"]["log_id"]
                for r in imported
                if r["observation"]["reported_values"][0]["concept_id"] == cid
            ],
        }
        for cid in sorted(plan)
    ]
    validate("records/v3/series", series)
    database = resources["data/jaffle.sqlite"]
    try:
        with closing(sqlite3.connect(database.as_uri() + "?mode=ro", uri=True)) as db:
            if db.execute("PRAGMA quick_check").fetchone()[0] != "ok":
                raise ValueError("invalid_semalign_database")
            for table, columns in TABLE_COLUMNS.items():
                if {r[1] for r in db.execute(f"PRAGMA table_info({table})")} != columns:
                    raise ValueError("semalign_database_schema_mismatch")
            counts = {
                table: db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] for table in TABLE_COLUMNS
            }
            if db.execute("PRAGMA foreign_key_check").fetchone() is not None:
                raise ValueError("semalign_database_foreign_key_error")
    except sqlite3.Error:
        raise ValueError("invalid_semalign_database") from None
    commit = None
    try:
        top = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        if Path(top).resolve() == root:
            commit = subprocess.run(
                ["git", "-C", str(root), "rev-parse", "HEAD"], capture_output=True, text=True, check=True
            ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        pass  # Exported data directories remain usable; file hashes are authoritative.
    if hashes != {name: digest(path) for name, path in resources.items()}:
        raise ValueError("semalign_source_changed_during_load")
    manifest = {
        "dataset_id": DATASET_ID,
        "source_root": str(root),
        "source_commit": commit,
        "source_files_sha256": hashes,
        "weeks": len(weeks),
        "database_rows": counts,
        "naive_timestamp_count": naive_count,
        "naive_timestamp_assumption": "UTC",
        "source_warnings": source_warnings,
    }
    return SemAlignSource(root, manifest, baseline, imported, requests, pairs, series)


def prepare_source(root, output):
    """Write a preparation bundle, not a completed generation/evaluation run."""
    output, root = Path(output).resolve(), Path(root).resolve()
    if output.is_relative_to(root):
        raise ValueError("semalign_output_inside_source")
    if output.exists():
        raise ValueError("semalign_output_exists")
    source = load_source(root)
    output.mkdir(parents=True, exist_ok=False)
    private = output / "private"
    write_jsonl(private / "agent-v2.requests.jsonl", source.requests)
    write_jsonl(private / "source-fixture.private.jsonl", source.imported)
    for level in LEVELS:
        public = output / "public" / level
        # Only observations leave the private import; source_truth remains private.
        logs = [project_fixture(record["observation"], level) for record in source.imported]
        write_json(public / "baseline.json", source.baseline)
        write_jsonl(public / "logs.jsonl", logs)
        write_jsonl(public / "pairs.jsonl", source.pairs)
        write_json(public / "series.json", source.series)
        manifest = validate(
            "records/v3/public-manifest",
            {
                "contract_version": "records/v3",
                "level": level,
                "source_mode": "synthetic_fixture",
                "stage": "data_preparation",
                "validation_scope": "structure_and_alignment",
                "generation_validation": "not_run",
                "files": {
                    name: digest(public / name)
                    for name in ("baseline.json", "logs.jsonl", "pairs.jsonl", "series.json")
                },
            },
        )
        write_json(public / "manifest.json", manifest)
    manifest = {
        **source.manifest,
        **source.summary(),
        "status": "prepared",
        "stage": "data_preparation",
        "agent_protocol": "agent/v2",
        "records_contract": "records/v3",
        "prepared_files_sha256": {
            p.relative_to(output).as_posix(): digest(p) for p in sorted(output.rglob("*")) if p.is_file()
        },
    }
    write_json(private / "manifest.json", manifest)
    return {**source.summary(), "status": "prepared"}
