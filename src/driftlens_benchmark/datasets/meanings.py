"""Consume data-owned explicit meanings; keep alternate definitions private."""

from copy import deepcopy

from ..artifacts import digest, read_json
from ..contracts import validate
from ..contracts.semalign import CONCEPT_UNITS, baseline_check


def load_meanings(source):
    """Load both catalogs privately, returning only the v1 public projection."""
    catalogs, hashes = {}, {}
    for version, name in (("v1", "ontology/semantics.v1.json"), ("v2", "ontology/semantics.v2.private.json")):
        path = (source.root / name).resolve()
        if not path.is_relative_to(source.root):
            raise ValueError("external_meaning_catalog")
        hashes[name] = digest(path)
        document = validate("semantics/v1/catalog", read_json(path))
        definitions = {c["concept_id"]: c for c in document["concepts"]}
        if set(definitions) != set(CONCEPT_UNITS):
            raise ValueError("meaning_catalog_concepts")
        for cid, entry in definitions.items():
            if entry["semantics"]["unit"] != CONCEPT_UNITS[cid]:
                raise ValueError("meaning_catalog_unit")
        catalogs[version] = definitions
        if version == "v1":
            schema = document["schema"]
        if hashes[name] != digest(path):
            raise ValueError("meaning_catalog_changed")
    baseline = deepcopy(source.baseline)
    baseline["schema"] = schema
    baseline["period"] = {
        "start": min(r["window"]["start"] for r in source.requests),
        "end": max(r["window"]["end"] for r in source.requests),
    }
    for entry in baseline["definitions"]:
        entry.update(catalogs["v1"][entry["concept_id"]])
    return catalogs, baseline_check(baseline), hashes
