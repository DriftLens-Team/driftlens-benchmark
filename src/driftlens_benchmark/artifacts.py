"""Strict serialization and explicit, non-overwriting artifact I/O."""

import hashlib
import json
import math
from pathlib import Path


def strict_json(text):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("duplicate_json_key")
            result[key] = value
        return result

    def reject(value):
        raise ValueError("nonfinite_json_number")

    def number(value):
        result = float(value)
        if not math.isfinite(result):
            reject(value)
        return result

    return json.loads(text, object_pairs_hook=pairs, parse_constant=reject, parse_float=number)


def read_json(path):
    return strict_json(Path(path).read_text(encoding="utf-8"))


def read_jsonl(path):
    rows = []
    with Path(path).open(encoding="utf-8") as stream:
        for line in stream:
            if not line.strip():
                raise ValueError("empty_jsonl_line")
            rows.append(strict_json(line))
    return rows


def encoded(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True)


def write_json(path, value, *, replace=False):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    # Replacements are limited to runner-owned progress manifests.
    with path.open("w" if replace else "x", encoding="utf-8", newline="\n") as stream:
        stream.write(encoded(value) + "\n")


def write_jsonl(path, rows):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        for row in rows:
            stream.write(encoded(row) + "\n")


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def object_digest(value):
    return hashlib.sha256(encoded(value).encode("utf-8")).hexdigest()


def unique(rows, key="log_id"):
    keys = [row[key] for row in rows]
    if len(set(keys)) != len(keys):
        raise ValueError("duplicate_record_id")
    return rows
