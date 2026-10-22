"""Strict declarative settings; all resource paths are relative to their owner file."""

from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

import yaml

from .artifacts import digest, encoded, read_json, read_jsonl
from .contracts import validate


class Loader(yaml.SafeLoader):
    pass


# Keep ISO dates as strings so YAML and JSON contracts have the same types.
Loader.yaml_implicit_resolvers = {
    key: [(tag, regex) for tag, regex in resolvers if tag != "tag:yaml.org,2002:timestamp"]
    for key, resolvers in Loader.yaml_implicit_resolvers.items()
}


def mapping(loader, node):
    result = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node)
        if not isinstance(key, str) or key in result:
            raise ValueError("invalid_or_duplicate_yaml_key")
        result[key] = loader.construct_object(value_node)
    return result


Loader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, mapping)


def load(path, schema):
    value = yaml.load(Path(path).read_text(encoding="utf-8"), Loader=Loader)
    # YAML accepts .nan/.inf; a nonfinite timeout must never reach the process watchdog.
    encoded(value)
    return validate("settings/" + schema, value)


def relative(owner, value):
    path = (Path(owner).resolve().parent / value).resolve()
    if not path.is_file():
        raise ValueError("missing_resource:" + str(path))
    return path


@dataclass(frozen=True)
class Suite:
    config: dict
    case: dict
    definitions: dict
    questions: list
    dataset: dict
    orders: Path
    schema: Path
    references: dict
    hashes: dict


def load_suite(path):
    path = Path(path).resolve()
    config = load(path, "suite")
    start = date.fromisoformat(config["start"])
    effective = date.fromisoformat(config["effective_at"])
    first_report = start + timedelta(days=6)
    last_report = start + timedelta(weeks=config["weeks"], days=-1)
    if start.weekday() != 0 or not first_report < effective <= last_report:
        raise ValueError("suite_requires_baseline_and_changed_weeks")
    case_path = relative(path, config["case"])
    case = load(case_path, "case")
    definition_path = relative(case_path, case["definitions"])
    definitions = validate("settings/definitions", read_json(definition_path))
    if definitions["v1"] == definitions["v2"]:
        raise ValueError("case_requires_definition_change")
    questions_path = relative(case_path, case["questions"])
    questions = read_jsonl(questions_path)
    if not questions or any(
        type(q) is not dict
        or set(q) != {"request"}
        or type(q["request"]) is not str
        or not q["request"].strip()
        or len(q["request"]) > 4096
        for q in questions
    ):
        raise ValueError("invalid_questions")
    dataset_path = relative(path, config["dataset"])
    dataset = load(dataset_path, "dataset")
    orders = relative(dataset_path, dataset["orders"])
    schema = relative(dataset_path, dataset["schema"])
    lock_path = relative(dataset_path, dataset["source_lock"])
    lock = read_json(lock_path)
    if (
        set(lock) != {"dataset_id", "provenance", "files"}
        or lock["dataset_id"] != dataset["dataset_id"]
        or lock["files"] != {"orders": digest(orders), "schema": digest(schema)}
    ):
        raise ValueError("dataset_lock_mismatch")
    references = {v: relative(case_path, p) for v, p in case["references"].items()}
    assets = {
        "suite": path,
        "case": case_path,
        "definitions": definition_path,
        "questions": questions_path,
        "dataset": dataset_path,
        "orders": orders,
        "schema": schema,
        "source_lock": lock_path,
        "assertions": relative(case_path, case["assertions"]),
        **references,
    }
    return Suite(
        config,
        case,
        definitions,
        questions,
        dataset,
        orders,
        schema,
        {v: p.read_text(encoding="utf-8") for v, p in references.items()},
        {name: digest(p) for name, p in assets.items()},
    )


def load_run(path):
    path = Path(path).resolve()
    config = load(path, "run")
    agent_path = relative(path, config["agent"])
    agent = load(agent_path, "agent")
    command = agent["command"]
    # A bare executable uses PATH; explicit relative executable paths use the config directory.
    if command[0] != "{python}" and ("/" in command[0] or "\\" in command[0]):
        command[0] = str(relative(agent_path, command[0]))
    suite = load_suite(relative(path, config["suite"]))
    return config, agent, suite, {"run_config": digest(path), "agent_config": digest(agent_path)}
