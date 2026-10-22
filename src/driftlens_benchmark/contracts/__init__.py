"""Versioned schemas are installed package resources, not checkout-relative files."""

from datetime import date, datetime, time, timedelta, timezone
from functools import lru_cache
from importlib.resources import files

from jsonschema import Draft202012Validator, FormatChecker, validators

from ..artifacts import strict_json

StrictValidator = validators.extend(
    Draft202012Validator,
    type_checker=Draft202012Validator.TYPE_CHECKER.redefine(
        "integer", lambda checker, value: type(value) is int
    ),
)


@lru_cache
def validator(name):
    schema = strict_json(files(__package__).joinpath(name + ".json").read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return StrictValidator(schema, format_checker=FormatChecker())


def validate(name, value):
    if not validator(name).is_valid(value):
        raise ValueError("invalid_contract:" + name)
    return value


def week(period):
    try:
        year, number = period.split("-W")
        start = date.fromisocalendar(int(year), int(number), 1)
        if period != f"{start.isocalendar().year:04d}-W{start.isocalendar().week:02d}":
            raise ValueError
        end = start + timedelta(days=7)
        timestamp = datetime.combine(end, time.min, timezone.utc) - timedelta(seconds=1)
        return start, end, timestamp.isoformat().replace("+00:00", "Z")
    except (ValueError, TypeError, AttributeError, OverflowError):
        raise ValueError("invalid_iso_week") from None


def request_check(request):
    validate("agent/v1/request", request)
    if request["timestamp"] != week(request["period"])[2] or not request["request"].strip():
        raise ValueError("invalid_request_period")


def observation_check(row):
    validate("records/v2/observation", row)
    value = row["reported_values"][0]
    start = datetime.fromisoformat(value["window"]["start"])
    end = datetime.fromisoformat(value["window"]["end"])
    if start.weekday() != 0 or start.time() != time.min or end - start != timedelta(days=7):
        raise ValueError("invalid_observation_window")
    expected = (end - timedelta(seconds=1)).isoformat().replace("+00:00", "Z")
    if row["timestamp"] != expected or value["as_of"] != expected:
        raise ValueError("invalid_observation_as_of")
    return row
