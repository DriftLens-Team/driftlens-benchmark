"""Source integrity and private/public separation using independently invented data."""

import json
from copy import deepcopy

import pytest
import yaml
from fixtures.semalign_source import create_source, jsonl

from driftlens_benchmark.artifacts import digest, read_json, read_jsonl, write_json
from driftlens_benchmark.cli import main
from driftlens_benchmark.datasets.semalign import SOURCE_FILES, load_source, prepare_source
from driftlens_benchmark.observations.projection import load_fixture_bundle


@pytest.fixture
def source(tmp_path):
    return create_source(tmp_path / "source")


def test_preparation_roundtrip_and_no_source_mutation(source, tmp_path):
    before = {f: digest(source / f) for f in SOURCE_FILES}
    output = tmp_path / "prepared"
    result = prepare_source(source, output)
    assert result["observations"] == 56
    assert result["pairs"] == 112
    assert result["generation_validation"] == "not_run"
    assert result["status"] == "prepared"
    assert before == {f: digest(source / f) for f in SOURCE_FILES}
    manifest = read_json(output / "private/manifest.json")
    assert manifest["source_files_sha256"] == before
    assert manifest["source_commit"] is None
    for name, expected in manifest["prepared_files_sha256"].items():
        assert digest(output / name) == expected
    requests = read_jsonl(output / "private/agent-v2.requests.jsonl")
    assert all(
        set(r) == {"request_id", "request", "timestamp", "concept_id", "window", "as_of"} for r in requests
    )
    baseline = None
    ids = None
    for level in ("L0", "L1", "L2", "L3"):
        bundle = load_fixture_bundle(output / "public" / level)
        assert bundle["manifest"]["stage"] == "data_preparation"
        assert len(bundle["series"]) == 7
        assert len(bundle["pairs"]) == 112
        assert sum(r["reported_values"][0]["value"] is None for r in bundle["logs"]) == 1
        current_ids = {r["log_id"] for r in bundle["logs"]}
        assert current_ids == {r["request_id"] for r in requests}
        if baseline is not None:
            assert baseline == bundle["baseline"]
            assert ids == current_ids
        baseline, ids = bundle["baseline"], current_ids
        content = json.dumps(bundle)
        for forbidden in (
            "oracle_sql",
            "contaminated",
            "effective_at",
            "is_control",
            "source_truth",
            "fixture_0",
        ):
            assert forbidden not in content
    assert not (output / "private/truth.jsonl").exists()  # No claim of newly verified generation.
    with pytest.raises(ValueError, match="output_exists"):
        prepare_source(source, output)
    with pytest.raises(ValueError, match="inside_source"):
        prepare_source(source, source / "output")


@pytest.mark.parametrize(
    "kind",
    [
        "truth_duplicate",
        "truth_missing",
        "truth_label",
        "truth_boolean",
        "pair_duplicate",
        "pair_truth",
        "pair_missing",
        "level_missing",
        "level_value",
        "nested_secret",
        "week_duplicate",
    ],
)
def test_inconsistent_source_is_rejected(source, kind):
    name = "data/truth.jsonl"
    if kind.startswith("pair"):
        name = "data/pairs_truth.jsonl" if kind == "pair_truth" else "data/pairs.jsonl"
    elif kind.startswith("level"):
        name = "data/logs.L0.jsonl"
    elif kind in {"nested_secret", "week_duplicate"}:
        name = "data/logs.L3.jsonl"
    rows = read_jsonl(source / name)
    if kind in {"truth_duplicate", "pair_duplicate"}:
        rows.append(deepcopy(rows[0]))
    elif kind in {"truth_missing", "pair_missing", "level_missing"}:
        rows.pop()
    elif kind == "truth_label":
        rows[0]["contaminated"] = not rows[0]["contaminated"]
    elif kind == "truth_boolean":
        rows[0]["is_control"] = int(rows[0]["is_control"])
    elif kind == "pair_truth":
        rows[0]["changed"] = not rows[0]["changed"]
    elif kind == "level_value":
        rows[0]["reported_values"][0]["value"] = 99
    elif kind == "nested_secret":
        rows[0]["reported_values"][0]["profile"] = "future"
    else:
        rows[7]["reported_values"][0]["window"] = deepcopy(rows[0]["reported_values"][0]["window"])
        rows[7]["reported_values"][0]["as_of"] = rows[0]["reported_values"][0]["as_of"]
    jsonl(source / name, rows)
    with pytest.raises(ValueError):
        load_source(source)


def test_upstream_note_fragment_is_visible_warning_not_configuration(source):
    path = source / "ontology/scenario.private.yml"
    doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    doc["concepts"][0].update(note="An annotation", trailing_annotation=None)
    path.write_text(yaml.safe_dump(doc), encoding="utf-8")
    loaded = load_source(source)
    assert loaded.summary()["source_warning_count"] == 1
    assert loaded.manifest["source_warnings"][0]["annotation_keys"] == ["trailing_annotation"]
    assert "trailing_annotation" not in json.dumps(loaded.baseline)
    doc["concepts"][0]["trailing_annotation"] = "unexpected_setting"
    path.write_text(yaml.safe_dump(doc), encoding="utf-8")
    with pytest.raises(ValueError, match="annotation"):
        load_source(source)


def test_duplicate_yaml_keys_are_not_silently_overwritten(source):
    path = source / "ontology/v1.yml"
    path.write_text(path.read_text(encoding="utf-8") + "models: []\n", encoding="utf-8")
    with pytest.raises(ValueError, match="duplicate_yaml_key"):
        load_source(source)


def test_invalid_database_is_a_clean_cli_failure(source, capsys):
    (source / "data/jaffle.sqlite").write_bytes(b"This is not a database")
    assert main(["inspect-data", "--source", str(source)]) == 2
    assert "invalid_semalign_database" in capsys.readouterr().err


def test_tampered_public_content_and_rehashed_bad_links_are_rejected(source, tmp_path):
    output = tmp_path / "prepared"
    prepare_source(source, output)
    public = output / "public/L0"
    pairs = read_jsonl(public / "pairs.jsonl")
    pairs[0]["log_a"] = "unknown"
    jsonl(public / "pairs.jsonl", pairs)
    with pytest.raises(ValueError, match="integrity"):
        load_fixture_bundle(public)
    manifest = read_json(public / "manifest.json")
    manifest["files"]["pairs.jsonl"] = digest(public / "pairs.jsonl")
    write_json(public / "manifest.json", manifest, replace=True)
    with pytest.raises(ValueError, match="pair_ids"):
        load_fixture_bundle(public)


def test_command_boundary_returns_counts_without_labels(source, tmp_path, capsys):
    assert main(["inspect-data", "--source", str(source)]) == 0
    output = capsys.readouterr().out
    assert json.loads(output)["observations"] == 56
    assert "effective_at" not in output
    assert main(["prepare-data", "--source", str(source), "--out", str(tmp_path / "prepared")]) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "prepared"
    assert main(["inspect-data", "--source", str(tmp_path / "missing")]) == 2
    assert "missing_or_external" in capsys.readouterr().err


def test_no_imports_from_data_repository(root):
    import ast

    module = root / "src/driftlens_benchmark/datasets/semalign.py"
    for node in ast.walk(ast.parse(module.read_text(encoding="utf-8"))):
        if isinstance(node, ast.ImportFrom):
            assert node.module not in {"oracle", "pipeline", "generate", "pairs"}


def test_source_resource_cannot_resolve_outside_root(source, tmp_path):
    # Directory traversal via symlinks may require Windows privileges; path validation
    # is covered by a file link only on systems that allow creating it.
    external = tmp_path / "external.yml"
    original = source / "ontology/v1.yml"
    external.write_bytes(original.read_bytes())
    original.unlink()
    try:
        original.symlink_to(external)
    except OSError:
        pytest.skip("Symlink creation unavailable on this host")
    with pytest.raises(ValueError, match="external_semalign"):
        load_source(source)
