"""Records/v3 preparation bundles expose one evidence level and no source labels."""

from collections import Counter
from copy import deepcopy
from datetime import datetime
from pathlib import Path

from ..artifacts import digest, read_json, read_jsonl, unique
from ..contracts import validate
from ..contracts.semalign import CONCEPT_UNITS, LEVELS, baseline_check, observation_check


def project_fixture(observation, level):
    """Validate the full source observation before hiding fields on a deep copy."""
    observation_check(observation, level="L3")
    if level not in LEVELS:
        raise ValueError("unknown_semalign_level")
    projected = deepcopy(observation)
    for field in LEVELS[level]:
        projected[field] = None
    return observation_check(projected, level=level)


def load_fixture_bundle(path):
    """Read a complete, hashed preparation bundle; this does not make it scoreable."""
    path = Path(path).resolve()
    manifest = validate("records/v3/public-manifest", read_json(path / "manifest.json"))
    for name, expected in manifest["files"].items():
        file = (path / name).resolve()
        if not file.is_relative_to(path) or digest(file) != expected:
            raise ValueError("semalign_public_integrity_mismatch")
    baseline = baseline_check(read_json(path / "baseline.json"))
    if manifest["stage"] == "validated_observations" and (
        "schema" not in baseline
        or "period" not in baseline
        or any("semantics" not in d for d in baseline["definitions"])
    ):
        raise ValueError("validated_bundle_requires_meanings")
    rows = unique([observation_check(r, level=manifest["level"]) for r in read_jsonl(path / "logs.jsonl")])
    by_id = {r["log_id"]: r for r in rows}
    if (not rows and manifest["stage"] == "data_preparation") or [r["timestamp"] for r in rows] != sorted(
        r["timestamp"] for r in rows
    ):
        raise ValueError("semalign_public_log_order")
    series = validate("records/v3/series", read_json(path / "series.json"))
    if {s["concept_id"] for s in series} != set(CONCEPT_UNITS):
        raise ValueError("semalign_public_series_concepts")
    all_ids = [lid for group in series for lid in group["log_ids"]]
    if Counter(all_ids) != Counter({lid: 1 for lid in by_id}):
        raise ValueError("semalign_public_series_coverage")
    periods = []
    for group in series:
        values = [by_id[lid]["reported_values"][0] for lid in group["log_ids"]]
        windows = [v["window"]["start"] for v in values]
        stamps = [by_id[lid]["timestamp"] for lid in group["log_ids"]]
        if stamps != sorted(stamps):
            raise ValueError("semalign_public_series_arrival_order")
        if any(v["concept_id"] != group["concept_id"] for v in values):
            raise ValueError("semalign_public_series_identity")
        if windows != sorted(set(windows)):
            raise ValueError("semalign_public_series_order")
        periods.append(windows)
    if manifest["stage"] == "data_preparation" and any(
        not period or period != periods[0] for period in periods
    ):
        raise ValueError("semalign_public_series_periods")
    pairs = unique([validate("records/v3/pair", p) for p in read_jsonl(path / "pairs.jsonl")], "pair_id")
    seen = set()
    for pair in pairs:
        identity = (pair["log_a"], pair["log_b"])
        if any(lid not in by_id for lid in identity) or identity in seen:
            raise ValueError("semalign_public_pair_ids")
        seen.add(identity)
        a, b = (by_id[lid]["reported_values"][0] for lid in identity)
        if a["concept_id"] != b["concept_id"] or a["concept_id"] != pair["concept_id"]:
            raise ValueError("semalign_public_pair_concept")
        gap = datetime.fromisoformat(b["window"]["start"]) - datetime.fromisoformat(a["window"]["start"])
        if not 7 <= gap.days <= 56:
            raise ValueError("semalign_public_pair_gap")
    return {"manifest": manifest, "baseline": baseline, "logs": rows, "pairs": pairs, "series": series}
