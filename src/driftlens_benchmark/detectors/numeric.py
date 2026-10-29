"""Fixed-parameter, public-prefix numeric diagnostic; never proves semantic meaning."""

from datetime import datetime, timedelta
from statistics import median

SETTINGS = {"calibration_values": 4, "mad_multiplier": 3, "relative_floor": 0.2, "confirmation_weeks": 2}


def numeric_signals(bundle):
    """Use the first four available values, then freeze the numeric reference band."""
    rows = {r["log_id"]: r for r in bundle["logs"]}
    regimes, alarms = {}, {}
    for group in bundle["series"]:
        calibration = []
        candidate = None
        alarm = None
        unknown = False
        evaluated = False
        for lid in group["log_ids"]:
            row = rows[lid]
            rv = row["reported_values"][0]
            value = rv["value"]
            week = datetime.fromisoformat(rv["window"]["start"])
            regime = None
            if len(calibration) < SETTINGS["calibration_values"]:
                if value is not None:
                    calibration.append(value)
            elif value is not None:
                evaluated = True
                center = median(calibration)
                mad = median(abs(v - center) for v in calibration)
                band = max(SETTINGS["mad_multiplier"] * mad, SETTINGS["relative_floor"] * abs(center), 1e-9)
                regime = 1 if value > center + band else -1 if value < center - band else 0
            else:
                unknown = True
            regimes[lid] = regime
            if regime in {-1, 1}:
                if (
                    candidate
                    and candidate["regime"] == regime
                    and week - candidate["week"] == timedelta(days=7)
                    and alarm is None
                ):
                    alarm = {
                        "decision": "change",
                        "estimated_change_at": candidate["week"].date().isoformat(),
                        "alarm_at": row["timestamp"],
                        "evidence_log_ids": [candidate["log_id"], lid],
                    }
                candidate = {"regime": regime, "week": week, "log_id": lid}
            else:
                candidate = None
        if alarm is None:
            alarm = {
                "decision": "abstain" if unknown or not evaluated or candidate else "no_change",
                "estimated_change_at": None,
                "alarm_at": None,
                "evidence_log_ids": [],
            }
        alarms[group["concept_id"]] = alarm
    return {
        "regimes": regimes,
        "alarms": alarms,
        "settings": SETTINGS.copy(),
        "mode": "online",
        "LOG_context": "historical_prefix",
    }


def value_check_signals(bundle, checks):
    """Private DB discrepancy diagnostic with two-week confirmation and no label access."""
    rows = {r["log_id"]: r for r in bundle["logs"]}
    alarms = {}
    for group in bundle["series"]:
        candidate = None
        alarm = None
        for lid in group["log_ids"]:
            row = rows[lid]
            week = datetime.fromisoformat(row["reported_values"][0]["window"]["start"])
            if checks[lid]:
                if candidate and week - candidate["week"] == timedelta(days=7) and alarm is None:
                    alarm = {
                        "decision": "change",
                        "estimated_change_at": candidate["week"].date().isoformat(),
                        "alarm_at": row["timestamp"],
                        "evidence_log_ids": [candidate["log_id"], lid],
                    }
                candidate = {"week": week, "log_id": lid}
            else:
                candidate = None
        alarms[group["concept_id"]] = alarm or {
            "decision": "abstain" if candidate else "no_change",
            "estimated_change_at": None,
            "alarm_at": None,
            "evidence_log_ids": [],
        }
    return {
        "regimes": checks,
        "alarms": alarms,
        "settings": {"confirmation_weeks": 2},
        "mode": "online",
        "LOG_context": "same_window_db_reference",
    }
