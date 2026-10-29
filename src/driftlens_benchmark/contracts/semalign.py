"""SemAlign cross-field checks supplement the installed, versioned JSON Schemas."""

from datetime import date, datetime, time, timedelta

from . import validate

CONCEPT_UNITS = {
    "sa_food_orders": "count",
    "sa_drink_orders": "count",
    "sa_customers_active": "count",
    "sa_customers_new": "count",
    "sa_order_value_avg": "cents",
    "sa_revenue_growth_wow": "ratio",
    "sa_tax_rate_avg": "ratio",
}
LEVELS = {
    "L0": {"sql", "definition_note"},
    "L1": {"definition_note"},
    "L2": {"sql"},
    "L3": set(),
}


def window_check(window, as_of, timestamp=None):
    """Require a complete UTC week, end-exclusive cutoff and a later question."""
    start, end = (datetime.fromisoformat(window[k]) for k in ("start", "end"))
    if start.weekday() != 0 or start.time() != time.min or end - start != timedelta(days=7):
        raise ValueError("invalid_semalign_window")
    if as_of != window["end"]:
        raise ValueError("invalid_semalign_as_of")
    if timestamp is not None and datetime.fromisoformat(timestamp) < end:
        raise ValueError("question_before_window_end")


def request_check(request):
    """Validate agent/v2 without changing the legacy agent/v1 contract."""
    validate("agent/v2/request", request)
    if not request["request"].strip():
        raise ValueError("empty_semalign_question")
    window_check(request["window"], request["as_of"], request["timestamp"])
    return request


def result_check(observation, timestamp=None):
    """Bind the declared metric, unit, reference and time window to each other."""
    value = observation["reported_values"][0]
    cid = value["concept_id"]
    if value["unit"] != CONCEPT_UNITS[cid] or observation["referenced_concepts"] != [cid]:
        raise ValueError("semalign_concept_unit_mismatch")
    if value["unit"] == "ratio" and value["value"] is not None and round(value["value"], 4) != value["value"]:
        raise ValueError("semalign_ratio_precision")
    if not observation["answer_text"].strip():
        raise ValueError("empty_semalign_answer")
    for key in ("sql", "definition_note"):
        if observation[key] is not None and not observation[key].strip():
            raise ValueError("empty_semalign_evidence")
    window_check(value["window"], value["as_of"], timestamp)


def observation_check(row, *, level):
    """Check the nested allowlist and the exact evidence available at this level."""
    if level not in LEVELS:
        raise ValueError("unknown_semalign_level")
    validate("records/v3/observation", row)
    if not row["request"].strip():
        raise ValueError("empty_semalign_question")
    for field in ("sql", "definition_note"):
        if (row[field] is None) != (field in LEVELS[level]):
            raise ValueError("semalign_level_mismatch")
    result_check(row, row["timestamp"])
    return row


def response_check(response, request):
    """Reject a successful response for the wrong request, concept or reporting week."""
    request_check(request)
    validate("agent/v2/response", response)
    if response["request_id"] != request["request_id"]:
        raise ValueError("semalign_response_id_mismatch")
    if response["status"] == "ok":
        observation = response["observation"]
        result_check(observation, request["timestamp"])
        value = observation["reported_values"][0]
        if any(value[k] != request[k] for k in ("concept_id", "window", "as_of")):
            raise ValueError("semalign_response_scope_mismatch")
    return response


def baseline_check(baseline):
    """A public baseline contains each supported v1 metric exactly once, with no oracle."""
    validate("records/v3/baseline", baseline)
    definitions = baseline["definitions"]
    if "period" in baseline:
        start, end = (datetime.fromisoformat(baseline["period"][key]) for key in ("start", "end"))
        if start.weekday() != 0 or end <= start or (end - start).days % 7:
            raise ValueError("invalid_semalign_evaluation_period")
    if {d["concept_id"] for d in definitions} != set(CONCEPT_UNITS):
        raise ValueError("semalign_baseline_concepts")
    for definition in definitions:
        if definition["unit"] != CONCEPT_UNITS[definition["concept_id"]]:
            raise ValueError("semalign_baseline_unit")
        if not definition["label"].strip() or not definition["definition"].strip():
            raise ValueError("empty_semalign_definition")
    return baseline


def prediction_check(task, prediction):
    """Validate output shapes; evaluation must additionally bind evidence to input IDs."""
    if task not in {"log", "pairs", "series"}:
        raise ValueError("unknown_semalign_task")
    validate(f"detection/v2/{task}", prediction)
    if task == "series" and prediction["decision"] == "change":
        at = date.fromisoformat(prediction["estimated_change_at"])
        alarm = datetime.fromisoformat(prediction["alarm_at"])
        if at.weekday() != 0 or at > alarm.date():
            raise ValueError("invalid_semalign_change_time")
    return prediction
