"""Create a portable, readable evidence bundle from a completed SemAlign run.

Uses only the standard library. It never calls a model or copies private truth,
snapshots, oracle/config files, environment files, or arbitrary run directories.
"""

import argparse
import csv
import hashlib
import html
import json
import os
import re
import sys
from collections import Counter
from pathlib import Path

STATUSES = {"validated": "검수 통과", "rejected": "검수 탈락", "unverified": "미검증", "failed": "실행 실패"}
CONCEPTS = {
    "sa_food_orders": "음식 주문",
    "sa_drink_orders": "음료 주문",
    "sa_customers_active": "활성 고객",
    "sa_customers_new": "신규 고객",
    "sa_order_value_avg": "평균 주문액",
    "sa_revenue_growth_wow": "매출 성장률",
    "sa_tax_rate_avg": "평균 세율",
}
CHECKS = {
    "behavioral_agreement": "참조·반례 DB 결과 일치",
    "query_correct_for_used_definition": "SQL과 지정 정의",
    "query_result_matches_reference": "SQL 실행값과 참조값",
    "reported_value_matches_query_result": "보고값과 SQL 실행값",
    "answer_matches_query_result": "답변과 SQL 실행값",
    "definition_note_consistent": "정의 설명 계약",
}
COUNTS = ("planned", "attempted", "successful_response", "validated", "rejected", "unverified", "failed")
METRICS = (
    "tp",
    "fp",
    "fn",
    "tn",
    "abstain",
    "eligible",
    "negative",
    "precision",
    "recall",
    "f1",
    "coverage",
    "fpr",
)
LOG_KEYS = {
    "log_id",
    "timestamp",
    "team",
    "agent_id",
    "request",
    "answer_text",
    "sql",
    "definition_note",
    "reported_values",
    "referenced_concepts",
}
VALUE_KEYS = {"result_id", "concept_id", "type", "value", "unit", "window", "as_of"}
SLOTS = {
    "grain",
    "aggregation",
    "population",
    "measure",
    "conditions",
    "time_semantics",
    "null_policy",
    "unit",
}
PUBLIC_FILES = ("baseline.json", "logs.jsonl", "pairs.jsonl", "series.json", "manifest.json")


def strict_object(pairs):
    """Reject duplicate JSON keys instead of silently replacing evidence fields."""
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate_json_key")
        result[key] = value
    return result


def reject_constant(value):
    """JSON decoder callback disallows NaN and Infinity."""
    raise ValueError("nonfinite_json: " + value)


def read_json(path):
    """Read one UTF-8 JSON artifact without permissive nonstandard values."""
    return json.loads(
        path.read_text(encoding="utf-8-sig"), object_pairs_hook=strict_object, parse_constant=reject_constant
    )


def read_jsonl(path):
    """Read actual nonempty JSONL records in their saved order."""
    return [
        json.loads(line, object_pairs_hook=strict_object, parse_constant=reject_constant)
        for line in path.read_text(encoding="utf-8-sig").splitlines()
        if line.strip()
    ]


def digest(path):
    """Bind exported evidence to the exact input file bytes."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def keys(obj, allowed, required=()):
    """Reject unknown nested fields before making a public artifact copy."""
    if type(obj) is not dict or set(obj) - set(allowed) or not set(required) <= set(obj):
        raise ValueError("unexpected_public_fields")


def check_observation(row, level="L3"):
    """Enforce the public observation allowlist, including nested metric fields."""
    keys(row, LOG_KEYS, LOG_KEYS)
    if any(
        type(row[k]) is not str
        for k in LOG_KEYS - {"sql", "definition_note", "reported_values", "referenced_concepts"}
    ):
        raise ValueError("invalid_public_text")
    if any(type(row[k]) not in {str, type(None)} for k in ("sql", "definition_note")):
        raise ValueError("invalid_optional_public_text")
    if type(row["referenced_concepts"]) is not list or any(
        type(x) is not str or x not in CONCEPTS for x in row["referenced_concepts"]
    ):
        raise ValueError("invalid_referenced_concepts")
    if type(row["reported_values"]) is not list or len(row["reported_values"]) != 1:
        raise ValueError("expected_single_metric_value")
    value = row["reported_values"][0]
    keys(value, VALUE_KEYS, VALUE_KEYS)
    keys(value["window"], {"start", "end"}, {"start", "end"})
    if any(type(value[k]) is not str for k in VALUE_KEYS - {"value", "window"}) or any(
        type(x) is not str for x in value["window"].values()
    ):
        raise ValueError("invalid_public_value_metadata")
    if value["unit"] not in {"count", "cents", "ratio"} or value["concept_id"] not in CONCEPTS:
        raise ValueError("unknown_public_metric")
    if type(value["value"]) not in {int, float, type(None)}:
        raise ValueError("invalid_metric_value")
    if level in {"L0", "L2"} and row["sql"] is not None:
        raise ValueError("sql_exposure_mismatch")
    if level in {"L0", "L1"} and row["definition_note"] is not None:
        raise ValueError("note_exposure_mismatch")


def collect_public(run):
    """Select only hash-verified public files, rejecting unknown nested data."""
    selected = {}
    for level in ("L0", "L1", "L2", "L3"):
        folder = run / "public" / level
        for filename in PUBLIC_FILES:
            file = folder / filename
            if file.is_symlink() or not file.is_file() or not file.resolve().is_relative_to(run):
                raise ValueError("public_file_missing_or_outside_run")
        manifest = read_json(folder / "manifest.json")
        keys(
            manifest,
            {
                "contract_version",
                "files",
                "generation_validation",
                "level",
                "source_mode",
                "stage",
                "validation_scope",
            },
        )
        keys(manifest["files"], set(PUBLIC_FILES) - {"manifest.json"}, set(PUBLIC_FILES) - {"manifest.json"})
        if any(type(v) is not str for k, v in manifest.items() if k != "files"):
            raise ValueError("invalid_public_manifest")
        if manifest["level"] != level:
            raise ValueError("public_level_mismatch")
        for filename, expected in manifest["files"].items():
            if digest(folder / filename) != expected:
                raise ValueError("public_hash_mismatch")
        baseline = read_json(folder / "baseline.json")
        keys(
            baseline,
            {"contract_version", "definitions", "schema", "period"},
            {"contract_version", "definitions"},
        )
        if baseline["contract_version"] != "records/v3" or type(baseline["definitions"]) is not list:
            raise ValueError("invalid_public_baseline")
        for definition in baseline["definitions"]:
            keys(definition, {"concept_id", "label", "definition", "unit", "semantics", "required_slots"})
            if any(
                type(v) is not str for k, v in definition.items() if k not in {"semantics", "required_slots"}
            ):
                raise ValueError("invalid_public_definition")
            if "semantics" in definition:
                keys(definition["semantics"], SLOTS, SLOTS)
                if any(type(v) is not str for v in definition["semantics"].values()):
                    raise ValueError("invalid_meaning_value")
            required_slots = definition.get("required_slots", [])
            if (
                type(required_slots) is not list
                or any(type(v) is not str for v in required_slots)
                or set(required_slots) - SLOTS
            ):
                raise ValueError("unknown_meaning_slot")
        if "period" in baseline:
            keys(baseline["period"], {"start", "end"}, {"start", "end"})
            if any(type(v) is not str for v in baseline["period"].values()):
                raise ValueError("invalid_public_period")
        if "schema" in baseline:
            keys(baseline["schema"], {"orders", "order_items", "products"})
            for table in baseline["schema"].values():
                keys(table, {"primary_key", "non_null", "foreign_keys", "amount_identity"})
                if any(type(v) not in {str, list} for v in table.values()):
                    raise ValueError("invalid_public_schema")
                if any(type(v) is list and any(type(x) is not str for x in v) for v in table.values()):
                    raise ValueError("invalid_public_schema")
        for row in read_jsonl(folder / "logs.jsonl"):
            check_observation(row, level)
        for pair in read_jsonl(folder / "pairs.jsonl"):
            keys(
                pair, {"concept_id", "log_a", "log_b", "pair_id"}, {"concept_id", "log_a", "log_b", "pair_id"}
            )
            if any(type(v) is not str for v in pair.values()):
                raise ValueError("invalid_public_pair")
        for series in read_json(folder / "series.json"):
            keys(series, {"concept_id", "log_ids"}, {"concept_id", "log_ids"})
            if (
                type(series["concept_id"]) is not str
                or type(series["log_ids"]) is not list
                or any(type(x) is not str for x in series["log_ids"])
            ):
                raise ValueError("invalid_public_series")
        for filename in PUBLIC_FILES:
            selected[f"public/{level}/{filename}"] = (folder / filename).read_bytes()
    return selected


def export_record(attempt):
    """Project an attempt into observable output and quality checks without truth."""
    status = attempt["status"]
    if status not in STATUSES or attempt["concept_id"] not in CONCEPTS:
        raise ValueError("unknown_attempt_status_or_concept")
    observation = attempt.get("observation")
    if observation is not None:
        check_observation(observation)
        value = observation["reported_values"][0]
    else:
        observation, value = {}, {}
    return {
        "log_id": attempt["log_id"],
        "concept_id": attempt["concept_id"],
        "status": status,
        "value_state": "missing_response" if not value else "null" if value["value"] is None else "value",
        "value": value.get("value"),
        "unit": value.get("unit"),
        "window_start": value.get("window", {}).get("start"),
        "window_end": value.get("window", {}).get("end"),
        "request": observation.get("request"),
        "answer_text": observation.get("answer_text"),
        "sql": observation.get("sql"),
        "reasons": [r for r in attempt.get("reasons", []) if type(r) is str],
        "checks": {
            k: v
            for k, v in attempt.get("checks", {}).items()
            if k in CHECKS and type(v) in {bool, type(None)}
        },
    }


def safe_report(report, manifest_hash):
    """Export aggregate evaluation only; exclude per-series truth and timing dates."""
    if report.get("run_manifest_sha256") != manifest_hash:
        raise ValueError("report_is_not_bound_to_this_run")
    if report.get("level") not in {"L0", "L1", "L2", "L3"}:
        raise ValueError("unknown_report_level")
    result = {
        k: report.get(k)
        for k in (
            "level",
            "detector",
            "status",
            "mode",
            "source_mode",
            "model_execution",
            "validation_policy",
            "accuracy_claim",
            "validation_dependence",
            "run_manifest_sha256",
            "prediction_manifest_sha256",
        )
    }
    if any(type(v) not in {str, type(None)} for v in result.values()):
        raise ValueError("invalid_evaluation_metadata")
    for task in ("LOG", "T1", "T2"):
        block = report[task]
        if (
            type(block) is not dict
            or type(block.get("micro")) is not dict
            or not set(METRICS) <= set(block["micro"])
        ):
            raise ValueError("missing_evaluation_micro_metrics")
        result[task] = {"micro": {k: block["micro"][k] for k in METRICS}}
        if any(type(v) not in {int, float, type(None)} for v in result[task]["micro"].values()):
            raise ValueError("invalid_aggregate_metric")
        result[task]["undefined"] = {
            k: v
            for k, v in block.get("micro", {}).get("undefined", {}).items()
            if k in METRICS and type(v) is str
        }
    for name in ("pair_eligibility", "series_eligibility"):
        result[name] = {
            k: v
            for k, v in report.get(name, {}).items()
            if k in {"planned", "eligible", "excluded", "complete"} and type(v) is int
        }
    return result


def apply_audit(summary_path, details_path, manifest, manifest_hash, attempts, records):
    """Bind a diagnostic-only recheck to exact saved observations without exporting details."""
    summary = read_json(summary_path)
    if (
        summary.get("audit_kind") != "saved_observation_validation_only"
        or summary.get("original_run_manifest_sha256") != manifest_hash
        or summary.get("private_details_sha256") != digest(details_path)
        or summary.get("model_api_calls") != 0
        or summary.get("original_run_unchanged") is not True
        or summary.get("source_files_and_catalogs_match_original") is not True
        or summary.get("validation_policy") != manifest.get("validation_policy", "structural")
    ):
        raise ValueError("audit_provenance_mismatch")
    details = read_jsonl(details_path)
    observed = {a["log_id"]: a for a in attempts if a.get("observation") is not None}
    known_cases = {case["case"] for attempt in observed.values() for case in attempt["counterexamples"]}
    if (
        len(details) != len(observed)
        or len({d["log_id"] for d in details}) != len(details)
        or {d["log_id"] for d in details} != set(observed)
    ):
        raise ValueError("audit_observation_ids_mismatch")
    by_id = {record["log_id"]: record for record in records}
    changed_ids = set()
    field_changes = Counter({k: 0 for k in ("checks", "counterexamples", "reasons")})
    check_changes = Counter({k: 0 for k in CHECKS})
    snapshot_corrections = 0
    for detail in details:
        attempt = observed[detail["log_id"]]
        observation_hash = hashlib.sha256(
            json.dumps(
                attempt["observation"],
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            ).encode("utf-8")
        ).hexdigest()
        old = {
            "status": attempt["status"],
            "checks": attempt["checks"],
            "reasons": sorted(attempt["reasons"]),
            "counterexamples": {case["case"]: case["matched"] for case in attempt["counterexamples"]},
        }
        if (
            detail.get("concept_id") != attempt["concept_id"]
            or detail.get("observation_sha256") != observation_hash
            or detail.get("old") != old
        ):
            raise ValueError("audit_saved_observation_mismatch")
        new = detail["new"]
        keys(new, old, old)
        keys(new["checks"], CHECKS, old["checks"])
        keys(new["counterexamples"], known_cases, old["counterexamples"])
        if (
            new["status"] != old["status"]
            or detail.get("status_changed") is not False
            or any(type(v) not in {bool, type(None)} for v in new["checks"].values())
            or any(type(v) not in {bool, type(None)} for v in new["counterexamples"].values())
            or type(new["reasons"]) is not list
            or any(type(reason) is not str for reason in new["reasons"])
        ):
            raise ValueError("audit_changes_status_or_has_invalid_diagnostics")
        changed = old != new
        if detail.get("diagnostics_changed") is not changed:
            raise ValueError("audit_diagnostic_flag_mismatch")
        if changed:
            changed_ids.add(detail["log_id"])
        for field in field_changes:
            field_changes[field] += old[field] != new[field]
        for check in check_changes:
            check_changes[check] += old["checks"].get(check) != new["checks"].get(check)
        snapshot_corrections += (
            old["checks"].get("query_result_matches_reference") is False
            and new["checks"].get("query_result_matches_reference") is True
        )
        # SQL, answer, value, status and every original public file remain untouched.
        by_id[detail["log_id"]]["checks"] = new["checks"].copy()
        by_id[detail["log_id"]]["reasons"] = list(new["reasons"])
    expected = {
        "planned": manifest["planned"],
        "attempted": len(attempts),
        "rechecked_observations": len(observed),
        "skipped_without_observation": len(attempts) - len(observed),
        "status_changed_count": 0,
        "eligibility_changed_count": 0,
        "diagnostics_changed_count": len(changed_ids),
        "diagnostic_changes_by_field": dict(field_changes),
        "check_changes": dict(check_changes),
        "snapshot_reference_false_to_true_count": snapshot_corrections,
        "original_status_counts": dict(Counter(a["status"] for a in attempts)),
        "combined_status_counts": dict(Counter(a["status"] for a in attempts)),
        "rechecked_status_counts": dict(Counter(a["status"] for a in observed.values())),
        "execution_error_counts": dict(
            Counter(
                reason
                for detail in details
                for reason in detail["new"]["reasons"]
                if reason.startswith(("snapshot:", "counterexample:"))
            )
        ),
    }
    if any(summary.get(key) != value for key, value in expected.items()):
        raise ValueError("audit_aggregate_mismatch")
    transitions = summary.get("status_transitions", [])
    if (
        type(transitions) is not list
        or len(transitions) != len(expected["rechecked_status_counts"])
        or any(
            type(item) is not dict
            or set(item) != {"old", "new", "count"}
            or item["old"] != item["new"]
            or expected["rechecked_status_counts"].get(item["old"]) != item["count"]
            for item in transitions
        )
        or len({item["old"] for item in transitions}) != len(transitions)
    ):
        raise ValueError("audit_status_transition_mismatch")
    # Only aggregate counts and provenance enter result.json; no private detail rows.
    safe = expected | {"status_transitions": transitions}
    for key in (
        "audit_kind",
        "created_at",
        "original_run_manifest_sha256",
        "private_details_sha256",
        "auditor_sha256",
        "validator_source_hash",
        "validation_policy",
    ):
        if type(summary.get(key)) is not str:
            raise ValueError("invalid_audit_metadata")
        safe[key] = summary[key]
    safe.update(model_api_calls=0, original_run_unchanged=True, source_files_and_catalogs_match_original=True)
    return safe, changed_ids


def secret_guard(text):
    """Refuse common credential-bearing logs rather than changing saved test output."""
    if re.search(
        r"(?i)(authorization\s*[:=]\s*(?:bearer|basic)\s+\S+|(?:api[_-]?key|access[_-]?token|password)\s*[=:]\s*[\"']?[A-Za-z0-9_+/.-]{12,}|\b(?:sk-[A-Za-z0-9_]{20,}|ghp_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}))",
        text,
    ):
        raise ValueError("credential_like_text_in_input")
    for name, value in os.environ.items():
        if (
            len(value) >= 12
            and any(word in name.upper() for word in ("API_KEY", "ACCESS_TOKEN", "SECRET", "PASSWORD"))
            and value in text
        ):
            raise ValueError("environment_secret_in_input")


def show(value):
    """Escape every dynamic HTML text value, including model-generated SQL/answers."""
    return html.escape("—" if value is None else str(value), quote=True)


def percent(value):
    """Present undefined scores separately from a measured zero."""
    return "—" if value is None else f"{100 * value:.1f}%"


def html_document(result, records, execution):
    """Render accessible tabs, aggregate evidence and inspectable actual attempts."""
    counts = result["generation"]
    audit = result.get("diagnostics_audit")
    audit_banner = (
        '<div class="banner" id="diagnostics-audit"><strong>'
        f"저장된 응답 재검수: 진단 {audit['diagnostics_changed_count']}건 정정, "
        f"판정 변경 {audit['status_changed_count']}건</strong>"
        "<p>원본 SQL·답변·공개 관측을 보존하고 검수 항목과 사유에 재검수 결과를 반영했습니다. "
        "추가 모델 호출은 없습니다.</p></div>"
        if audit
        else ""
    )
    verification_names = {
        "benchmark-tests": "Benchmark 테스트",
        "benchmark-lint": "Benchmark 코드 검사",
        "benchmark-build": "Benchmark 패키지 빌드",
        "agent-tests": "SQL Agent 테스트",
        "agent-build": "SQL Agent 패키지 빌드",
        "data-tests": "데이터 테스트",
        "data-counterexamples": "데이터 경계·반례 검사",
        "data-independent-reference": "데이터 독립 참조 검사",
        "data-generate": "평가 데이터 생성",
        "data-validate": "생성 데이터 검증",
    }
    verification_rows = []
    for step in result.get("execution_steps", []):
        if step["name"] not in verification_names:
            continue
        badge = "validated" if step["status"] == "passed" and step["exit_code"] == 0 else "unverified"
        verification_rows.append(
            f"<tr><td>{show(verification_names[step['name']])} "
            f'<span class="muted">({show(step["name"])})</span></td>'
            f'<td><span class="badge {badge}">{show(step["status"])}</span></td>'
            f"<td>{show(step['exit_code'])}</td><td>{show(step['elapsed_seconds'])}</td></tr>"
        )
    verification_table = (
        '<div class="section"><h2>실제 테스트·빌드·데이터 검증</h2>'
        '<p class="muted">실행 기록의 단계별 상태와 종료 코드를 표시합니다. '
        "AI 생성 관측의 검수 통과 여부는 결과 요약에서 확인합니다.</p>"
        '<div class="table-wrap"><table id="verification-steps"><thead><tr>'
        "<th>단계</th><th>실행 상태</th><th>종료 코드</th><th>소요 시간(초)</th>"
        "</tr></thead><tbody>" + "".join(verification_rows) + "</tbody></table></div></div>"
        if verification_rows
        else '<p class="muted">별도 테스트·빌드·데이터 검증 실행 기록이 제공되지 않았습니다.</p>'
    )
    cards = "".join(
        f'<div class="card"><span>{label}</span><strong>{counts[key]:,}</strong></div>'
        for key, label in [
            ("planned", "전체 계획"),
            ("attempted", "실행한 요청"),
            ("validated", "검수 통과"),
            ("rejected", "검수 탈락"),
            ("unverified", "미검증"),
            ("failed", "실행 실패"),
        ]
    )
    scores = []
    for report in result["evaluations"]:
        for task in ("LOG", "T1", "T2"):
            micro = report[task]["micro"]
            scores.append(
                f"<tr><td>{show(report['level'])}</td><td>{show(report['detector'])}</td><td>{task}</td><td>{show(micro['eligible'])}</td><td>{percent(micro['f1'])}</td><td>{percent(micro['coverage'])}</td><td>{show(micro['abstain'])}</td></tr>"
            )
    score_table = (
        '<p class="muted">채점 보고서가 제공되지 않았습니다.</p>'
        if not scores
        else '<div class="table-wrap"><table><thead><tr><th>관측 수준</th><th>탐지 방법</th><th>과제</th><th>평가 대상</th><th>F1</th><th>판정률</th><th>기권</th></tr></thead><tbody>'
        + "".join(scores)
        + '</tbody></table></div><p class="muted">—는 계산할 수 없는 지표입니다. 생성 검수 통과율과 탐지 F1은 서로 다른 지표입니다.</p>'
    )
    concept_rows = []
    for cid, label in CONCEPTS.items():
        group = [r for r in records if r["concept_id"] == cid]
        values = [sum(r["status"] == status for r in group) for status in STATUSES]
        concept_rows.append(
            "<tr><td>"
            + label
            + "</td><td>"
            + str(len(group))
            + "</td>"
            + "".join(f"<td>{v}</td>" for v in values)
            + "</tr>"
        )
    details = []
    for index, record in enumerate(records, 1):
        state = record["value_state"]
        value_text = (
            "응답 없음"
            if state == "missing_response"
            else "null · 계산 불가"
            if state == "null"
            else f"{record['value']} {record['unit']}"
        )
        check_items = []
        for key, value in record["checks"].items():
            label = "통과" if value is True else "불일치" if value is False else "판정 불가"
            if (
                key == "query_correct_for_used_definition"
                and value is None
                and result["validation_policy"] == "behavioral"
            ):
                label = "SQL 의미 미판정 · 유한 DB 검증 사용"
            check_items.append(f"<li>{show(CHECKS[key])}: <b>{show(label)}</b></li>")
        checks = "".join(check_items)
        reasons = ", ".join(CHECKS.get(r, r) for r in record["reasons"]) or "없음"
        details.append(f'''<details class="record" data-status="{record["status"]}" data-concept="{record["concept_id"]}" id="record-{index}">
<summary><span class="badge {record["status"]}">{STATUSES[record["status"]]}</span><strong>{show(CONCEPTS[record["concept_id"]])}</strong><span>{show((record["window_start"] or "")[:10])}</span><span class="value">{show(value_text)}</span></summary>
<div class="record-body"><p class="muted">{show(record["log_id"])}</p><p><b>질문</b> {show(record["request"])}</p><p><b>생성 답변</b> {show(record["answer_text"])}</p><p><b>집계 기간</b> {show(record["window_start"])} ≤ 주문 시각 &lt; {show(record["window_end"])}</p><p><b>검수 사유</b> {show(reasons)}</p><ul>{checks}</ul><h3>실행 SQL</h3><pre>{show(record["sql"])}</pre></div></details>''')
    payload = (
        json.dumps(result, ensure_ascii=False, allow_nan=False)
        .replace("&", "\\u0026")
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("\u2028", "\\u2028")
        .replace("\u2029", "\\u2029")
    )
    mode = result["execution_label"]
    policy = result["validation_policy"]
    completion = f"{counts['attempted']}/{counts['planned']}"
    valid_rate = percent(counts["validated"] / counts["attempted"] if counts["attempted"] else None)
    return f"""<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>SemAlign 실행 증적</title>
<style>
*{{box-sizing:border-box}}body{{margin:0;background:#f4f6fa;color:#17253d;font-family:"Malgun Gothic","Noto Sans KR",Arial,sans-serif;font-size:15px;line-height:1.65}}main{{max-width:1360px;margin:auto;padding:42px 40px 70px}}header{{display:flex;justify-content:space-between;gap:24px;align-items:flex-start}}h1{{font-size:34px;line-height:1.25;letter-spacing:-1px;margin:4px 0 10px}}h2{{font-size:22px;margin:0 0 18px}}h3{{font-size:16px;margin:18px 0 8px}}p{{margin:8px 0}}.eyebrow{{font-size:13px;color:#526782;letter-spacing:2px;font-weight:700}}.muted{{color:#5c6b81;font-size:13px}}.run{{max-width:450px;word-break:break-all;text-align:right}}nav{{display:flex;gap:8px;margin:28px 0 24px;border-bottom:1px solid #d7dfeb}}nav button{{font:inherit;font-weight:bold;background:none;border:0;padding:12px 24px;color:#66748a;cursor:pointer;border-bottom:3px solid transparent}}nav button[aria-selected="true"]{{color:#142d52;border-color:#142d52}}.panel{{display:none}}.panel.active{{display:block}}.cards{{display:grid;grid-template-columns:repeat(6,1fr);gap:12px;margin:22px 0}}.card{{border:1px solid #dbe2ec;background:white;border-radius:10px;padding:18px}}.card span{{font-size:13px;color:#586a80}}.card strong{{display:block;font-size:30px;line-height:1.4;margin-top:4px}}.section{{background:white;border:1px solid #dbe2ec;border-radius:12px;padding:24px;margin-top:20px}}.banner{{background:#eaf0f8;border-left:4px solid #183a66;padding:18px 22px;border-radius:4px}}.banner strong{{color:#142d52}}.table-wrap{{overflow:auto}}table{{border-collapse:collapse;width:100%;font-size:14px}}th{{background:#f0f4f9;color:#334a68;text-align:left;font-weight:700}}th,td{{padding:11px 14px;border-bottom:1px solid #e2e7ef;white-space:nowrap}}.downloads{{display:flex;gap:10px;flex-wrap:wrap;margin:18px 0}}a.download{{text-decoration:none;border:1px solid #cbd6e5;border-radius:6px;background:white;padding:8px 14px;color:#173f70;font-weight:700}}.toolbar{{display:flex;gap:12px;align-items:center;margin-bottom:18px;flex-wrap:wrap}}select,input,button.more{{font:inherit;border:1px solid #cbd6e5;border-radius:6px;background:white;padding:8px 12px;color:#223b5b}}input{{flex:1;min-width:180px}}.record{{background:white;border:1px solid #dbe2ec;border-radius:8px;margin:9px 0}}summary{{cursor:pointer;display:flex;gap:16px;align-items:center;padding:14px 18px;list-style:none}}summary::before{{content:"＋";color:#6a7b92}}details[open] summary::before{{content:"−"}}summary .value{{margin-left:auto;font-variant-numeric:tabular-nums}}.badge{{display:inline-block;border-radius:4px;padding:2px 8px;font-size:12px;font-weight:bold;white-space:nowrap}}.validated{{background:#e4f3ed;color:#17654c}}.rejected{{background:#fbe9e8;color:#a63836}}.unverified{{background:#fff2d9;color:#805600}}.failed{{background:#eceaf7;color:#5a4287}}.record-body{{border-top:1px solid #e1e6ee;padding:18px 24px}}pre{{white-space:pre-wrap;word-break:break-word;background:#f3f5f8;border:1px solid #e0e5ed;border-radius:6px;padding:16px;color:#253851;font-family:Consolas,monospace;font-size:13px;line-height:1.6;max-height:620px;overflow:auto}}.split{{display:grid;grid-template-columns:1fr 1fr;gap:20px}}ul{{padding-left:22px}}.foot{{margin-top:28px;color:#64758b;font-size:12px;word-break:break-all}}[hidden]{{display:none!important}}@media(max-width:900px){{main{{padding:24px 16px}}header{{display:block}}.run{{text-align:left}}.cards{{grid-template-columns:repeat(3,1fr)}}.split{{grid-template-columns:1fr}}summary{{gap:8px;flex-wrap:wrap}}}}@media print{{body{{background:white}}main{{padding:0}}nav,.toolbar,.downloads,.more{{display:none}}.panel{{display:block}}.section,.record{{break-inside:avoid}}pre{{max-height:none}}}}
</style></head><body><main><header><div><div class="eyebrow">DRIFTLENS · SEMALIGN</div><h1>실행 결과와 검증 증적</h1><p>{show(mode)} · {show(result["model_id"] or "모델 호출 없음")}</p></div><div class="run"><b>{show(result["run_name"])}</b><p class="muted">실행 상태: {show(result["status"])}<br>검수 정책: {show(policy)}</p></div></header>
<nav role="tablist" aria-label="실행 증적"><button id="tab-summary" role="tab" aria-selected="true" aria-controls="summary">결과 요약</button><button id="tab-records" role="tab" aria-selected="false" aria-controls="records">생성 데이터</button><button id="tab-commands" role="tab" aria-selected="false" aria-controls="commands">실행 방법·로그</button></nav>
{audit_banner}
<section class="panel active" id="summary" role="tabpanel"><div class="banner"><strong>요청 실행 {completion} · 검수 통과율 {valid_rate}</strong><p>검수 탈락은 SQL·답변이 지정 정의를 충족하지 못한 경우이며, 실행 실패나 계산 불가(null)와 구분합니다.</p></div><div class="cards">{cards}</div>
<div class="split"><div class="section"><h2>수행 흐름</h2><p>① 주간 데이터 준비 → ② SQL·답변 생성</p><p>③ 참조 계산·반례 검수 → ④ 공개 관측 변환</p><p>⑤ LOG·T1·온라인 T2 탐지 → ⑥ 채점</p><p class="muted">미실행 {counts["planned"] - counts["attempted"]}건 · 계산 불가 응답 {sum(r["value_state"] == "null" for r in records)}건</p></div><div class="section"><h2>생성 결과 읽는 법</h2><p><b>count</b>: 건수·고객 수 · <b>cents</b>: 정수 센트 · <b>ratio</b>: 비율</p><p><b>0</b>은 실제 계산값, <b>null</b>은 계산 불가, <b>응답 없음</b>은 값이 생성되지 않은 상태입니다.</p><p class="muted">{show(result["interpretation"])}</p></div></div>
<div class="section"><h2>지표별 검수</h2><div class="table-wrap"><table><thead><tr><th>지표</th><th>시도</th><th>통과</th><th>탈락</th><th>미검증</th><th>실패</th></tr></thead><tbody>{"".join(concept_rows)}</tbody></table></div></div>
<div class="section"><h2>탐지 평가</h2>{score_table}<p class="muted">{show(result["accuracy_note"])}</p></div></section>
<section class="panel" id="records" role="tabpanel"><h2>실제 생성 데이터</h2><p>각 행을 펼치면 질문, 답변, 값, 실행 SQL과 검수 사유를 확인할 수 있습니다.</p><div class="downloads"><a class="download" href="generated.csv" download>전체 요약 CSV</a><a class="download" href="observations.jsonl" download>검수 통과 L3 JSONL</a><a class="download" href="result.json" download>결과 JSON</a></div><div class="toolbar"><label>결과 <select id="status-filter"><option value="all">전체</option>{"".join(f'<option value="{k}">{v}</option>' for k, v in STATUSES.items())}</select></label><label>지표 <select id="concept-filter"><option value="all">전체</option>{"".join(f'<option value="{k}">{v}</option>' for k, v in CONCEPTS.items())}</select></label><input id="search" aria-label="질문 또는 SQL 검색" placeholder="질문·답변·SQL 검색"></div><p class="muted" id="record-count"></p>{"".join(details)}<button class="more" id="show-more">모든 일치 항목 표시</button></section>
<section class="panel" id="commands" role="tabpanel">{verification_table}<h2 style="margin-top:26px">재현 방법과 테스트 로그</h2><p>benchmark 저장소에서 환경을 준비한 뒤 아래 명령을 실행합니다. 출력 폴더는 새 경로를 사용합니다.</p><div class="downloads"><a class="download" href="execution.txt" download>명령·로그 원문</a><a class="download" href="public/L3/manifest.json" download>공개 자료 manifest</a></div><pre id="execution-log">{show(execution)}</pre><p class="muted">API 키는 환경변수로 제공하며 증적 파일에 기록하지 않습니다.</p></section>
<div class="foot">원본 실행 manifest SHA-256: {show(result["provenance"]["run_manifest_sha256"])}<br>공개 자료와 관측·집계만 포함합니다. private truth, snapshot, oracle, 설정 파일과 자격 증명은 포함하지 않습니다.</div></main><script type="application/json" id="evidence-data">{payload}</script><script>
const tabs=[...document.querySelectorAll('[role="tab"]')]; tabs.forEach(tab=>tab.addEventListener('click',()=>{{tabs.forEach(x=>x.setAttribute('aria-selected',String(x===tab)));document.querySelectorAll('.panel').forEach(p=>p.classList.toggle('active',p.id===tab.getAttribute('aria-controls')));}}));
const records=[...document.querySelectorAll('.record')];let expanded=false;function filter(){{const status=document.getElementById('status-filter').value,concept=document.getElementById('concept-filter').value,q=document.getElementById('search').value.toLocaleLowerCase();let match=0,shown=0;records.forEach(r=>{{const ok=(status==='all'||r.dataset.status===status)&&(concept==='all'||r.dataset.concept===concept)&&r.textContent.toLocaleLowerCase().includes(q);if(ok)match++;r.hidden=!ok||(!expanded&&shown>=20);if(!r.hidden)shown++;}});document.getElementById('record-count').textContent=`일치 ${{match}}건 · 표시 ${{shown}}건`;document.getElementById('show-more').hidden=shown===match;}}['status-filter','concept-filter','search'].forEach(id=>document.getElementById(id).addEventListener('input',()=>{{expanded=false;filter();}}));document.getElementById('show-more').addEventListener('click',()=>{{expanded=true;filter();}});filter();
</script></body></html>"""


def main(argv=None):
    """Build a new bundle only after checking every selected input and denominator."""
    parser = argparse.ArgumentParser(description="실제 SemAlign 실행에서 공개 증적 묶음을 만듭니다.")
    parser.add_argument("--run", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--report", action="append", default=[], type=Path)
    parser.add_argument("--test-log", action="append", default=[], type=Path)
    parser.add_argument("--execution", type=Path, help="선택: 실제 실행 묶음의 execution.json")
    parser.add_argument("--audit", type=Path, help="선택: 저장된 응답 재검수 집계 JSON")
    parser.add_argument("--audit-details", type=Path, help="--audit와 함께 검증에만 사용할 비공개 상세 JSONL")
    args = parser.parse_args(argv)
    if bool(args.audit) != bool(args.audit_details):
        raise ValueError("audit_and_audit_details_must_be_provided_together")
    run, output = args.run.resolve(), args.out.absolute()
    if output.exists() or output.is_symlink() or output.resolve().is_relative_to(run):
        raise ValueError("output_must_be_new_and_outside_source_run")
    manifest_file, attempts_file = run / "private/manifest.json", run / "private/attempts.jsonl"
    manifest, attempts = read_json(manifest_file), read_jsonl(attempts_file)
    if manifest.get("status") not in {"complete", "partial"}:
        raise ValueError("run_is_not_finalized")
    if manifest.get("files_sha256", {}).get("private/attempts.jsonl") != digest(attempts_file):
        raise ValueError("attempts_hash_mismatch")
    counts = {key: manifest[key] for key in COUNTS}
    if any(type(n) is not int or n < 0 for n in counts.values()):
        raise ValueError("invalid_generation_counts")
    records = [export_record(attempt) for attempt in attempts]
    if len({r["log_id"] for r in records}) != len(records) or counts["attempted"] != len(records):
        raise ValueError("attempt_count_or_id_mismatch")
    if counts["planned"] < counts["attempted"] or sum(counts[k] for k in STATUSES) != len(records):
        raise ValueError("generation_denominator_mismatch")
    if any(counts[k] != sum(r["status"] == k for r in records) for k in STATUSES):
        raise ValueError("generation_status_mismatch")
    if manifest["status"] == "complete" and counts["validated"] != counts["planned"]:
        raise ValueError("complete_run_has_ineligible_observations")
    public_files = collect_public(run)
    public_ids = {r["log_id"] for r in read_jsonl(run / "public/L3/logs.jsonl")}
    if public_ids != {r["log_id"] for r in records if r["status"] == "validated"}:
        raise ValueError("validated_public_id_mismatch")
    manifest_hash = digest(manifest_file)
    audit_summary, corrected_ids = None, set()
    if args.audit:
        audit_summary, corrected_ids = apply_audit(
            args.audit, args.audit_details, manifest, manifest_hash, attempts, records
        )
    evaluations = [safe_report(read_json(path), manifest_hash) for path in args.report]
    if len({(r["level"], r["detector"]) for r in evaluations}) != len(evaluations):
        raise ValueError("duplicate_level_and_detector_report")
    execution_mode = manifest.get("model_execution")
    execution_label = {
        "live": "실제 AI 모델",
        "deterministic_fake": "모의 에이전트 · 통신 검증",
        "source_fixture": "원본 합성 SQL · 모델 호출 없음",
    }.get(execution_mode)
    if execution_label is None:
        raise ValueError("unknown_execution_mode")
    capabilities = manifest.get("agent_capabilities") or {}
    benchmark = manifest.get("benchmark") or {}
    execution_file = args.execution or (run.parent / "execution.json")
    execution_steps = []
    if execution_file.is_file():
        suite = read_json(execution_file)
        for step in suite.get("steps", []):
            entry = {
                k: step.get(k)
                for k in (
                    "name",
                    "cwd",
                    "status",
                    "exit_code",
                    "elapsed_seconds",
                    "started_at",
                    "finished_at",
                    "command",
                )
            }
            if type(entry["command"]) is not list or any(type(x) is not str for x in entry["command"]):
                raise ValueError("invalid_execution_command")
            if any(type(v) not in {str, int, float, type(None)} for k, v in entry.items() if k != "command"):
                raise ValueError("invalid_execution_metadata")
            secret_guard(json.dumps(entry, ensure_ascii=False))
            execution_steps.append(entry)
    result = {
        "format": "semalign-evidence/v1",
        "run_name": run.name,
        "status": manifest["status"],
        "source_mode": manifest.get("source_mode"),
        "model_execution": execution_mode,
        "execution_label": execution_label,
        "model_id": manifest.get("model_id"),
        "provider": manifest.get("provider"),
        "generation": counts,
        "validation_policy": manifest.get("validation_policy", "structural"),
        "validation_scope": manifest.get("validation_scope"),
        "diagnostics_audit": audit_summary,
        "units": {"count": "건수·고객 수", "cents": "정수 센트", "ratio": "소수 비율, 백분율 아님"},
        "interpretation": "실제 모델 출력과 검수 결과입니다."
        if execution_mode == "live"
        else "실제 모델의 언어 이해 성능을 측정한 실행이 아닙니다.",
        "accuracy_note": "유한한 참조 DB·반례에서의 일치를 확인한 결과이며 임의 SQL 동치나 미지 데이터 일반화를 증명하지 않습니다."
        if manifest.get("validation_policy") == "behavioral"
        else "SQL 검수와 탐지의 의미 추출기가 공유됩니다. 높은 점수는 독립 정확도 증명이 아닌 개발 일관성 결과입니다.",
        "evaluations": evaluations,
        "execution_steps": execution_steps,
        "provenance": {
            "run_manifest_sha256": manifest_hash,
            "attempts_sha256": digest(attempts_file),
            "benchmark_source_hash": benchmark.get("source_hash"),
            "agent_implementation_sha256": capabilities.get("implementation_sha256"),
            "agent_prompt_sha256": capabilities.get("prompt_sha256"),
            "input_reports_sha256": {str(p): digest(p) for p in args.report},
            "test_logs_sha256": {str(p): digest(p) for p in args.test_log},
        },
    }
    for field in ("source_mode", "model_id", "provider", "validation_policy", "validation_scope"):
        if type(result[field]) not in {str, type(None)}:
            raise ValueError("invalid_run_metadata")
    for field in ("benchmark_source_hash", "agent_implementation_sha256", "agent_prompt_sha256"):
        value = result["provenance"][field]
        if value is not None and (type(value) is not str or not re.fullmatch(r"[0-9a-f]{64}", value)):
            raise ValueError("invalid_implementation_hash")
    agent_python = (
        "../driftlens-sql-agent/.venv/Scripts/python.exe"
        if os.name == "nt"
        else "../driftlens-sql-agent/.venv/bin/python"
    )
    benchmark_python = ".venv/Scripts/python.exe" if os.name == "nt" else ".venv/bin/python"
    data_python = (
        "../driftlens-data/.venv/Scripts/python.exe"
        if os.name == "nt"
        else "../driftlens-data/.venv/bin/python"
    )
    data_root = "../driftlens-data"
    source_root = manifest.get("source", {}).get("source_root")
    if type(source_root) is not str or not source_root.strip():
        raise ValueError("source_root_required_for_reproduction")
    repo_root = Path(__file__).absolute().parent.parent
    try:
        source_argument = Path(os.path.relpath(source_root, repo_root)).as_posix()
    except ValueError:
        source_argument = source_root
    # The acceptance command prepares a fresh source; individual regeneration
    # must use this run's recorded source bundle, not the repository's old logs.
    for step in execution_steps:
        command = step["command"]
        if step["name"] == "data-generate":
            data_python, data_root = command[0], step["cwd"]
        if "run-semalign" in command and "--out" in command:
            target = Path(command[command.index("--out") + 1])
            if not target.is_absolute():
                target = Path(step["cwd"]) / target
            if target.resolve() == run:
                benchmark_python = command[0]
                if "--agent-python" in command:
                    agent_python = command[command.index("--agent-python") + 1]
    limit = f" --limit {counts['attempted']}" if counts["attempted"] < counts["planned"] else ""
    mode_args = (
        "--mode fixture"
        if execution_mode == "source_fixture"
        else f"--mode agent --provider {manifest['provider']} --agent-python {agent_python}"
    )
    mode_args += f" --validation-policy {manifest.get('validation_policy', 'structural')}"
    destination = "runs/semalign-reproduction"
    acceptance_argv = [
        benchmark_python,
        "scripts/run_semalign_acceptance.py",
        "--data-root",
        data_root,
        "--data-python",
        data_python,
        "--agent-python",
        agent_python,
        "--out",
        "runs/semalign-acceptance-reproduction",
    ]
    if execution_mode == "live":
        acceptance_argv.append("--live")
    acceptance_command = "& " + " ".join("'" + str(item).replace("'", "''") + "'" for item in acceptance_argv)
    source_quoted = "'" + source_argument.replace("'", "''") + "'"
    result["reproduction"] = {"source_root": source_root, "acceptance_argv": acceptance_argv}
    commands = [
        "SemAlign 실행 재현",
        "작업 폴더: driftlens-benchmark",
        "환경: data는 Python 3.12 이상, benchmark와 SQL-agent는 Python 3.11 이상; 저장소별 환경에 설치",
        "",
        "1. 전체 검증: 테스트 → 새 데이터 생성 → 모델 생성 → 탐지·채점",
        acceptance_command,
        "",
        "2. 동일 입력으로 개별 실행",
        "이 실행에 기록된 source bundle을 사용합니다. 원본 저장소의 과거 로그와 바꾸지 않습니다.",
        f"source: {source_root}",
        f"python -m driftlens_benchmark run-semalign --source {source_quoted} {mode_args}{limit} --out {destination}",
        "",
    ]
    for report in evaluations:
        level = report["level"]
        detector = report["detector"]
        prediction = f"{destination}-predictions-{level}-{detector}"
        commands.extend(
            [
                f"python -m driftlens_benchmark detect-semalign --public {destination}/public/{level} --detector {detector} --out {prediction}",
                f"python -m driftlens_benchmark evaluate-semalign --run {destination} --predictions {prediction} --allow-partial --out {destination}-report-{level}-{detector}.json",
            ]
        )
    if execution_mode == "live":
        commands.extend(
            [
                "",
                "실제 모델 실행 전 환경변수 UPSTAGE_MODEL과 UPSTAGE_API_KEY를 준비합니다.",
                f"기록된 모델: {manifest.get('model_id')}",
                "키를 명령, 보고서, 로그 또는 생성 파일에 넣지 않습니다.",
            ]
        )
    commands.extend(
        [
            "",
            "검수 통과 관측: observations.jsonl",
            "모든 시도 요약: generated.csv",
            "공개 자료: public/L0, public/L1, public/L2, public/L3",
            "",
        ]
    )
    for step in execution_steps:
        # Preserve the exact argv as JSON, without guessing shell quoting.
        shell_command = "& " + " ".join("'" + item.replace("'", "''") + "'" for item in step["command"])
        commands.extend(
            [
                f"===== 실제 실행: {step['name']} =====",
                f"상태: {step['status']} / 종료 코드: {step['exit_code']} / 소요 초: {step['elapsed_seconds']}",
                f"시작: {step['started_at']} / 종료: {step['finished_at']}",
                f"작업 폴더: {step['cwd']}",
                "PowerShell: " + shell_command,
                "argv: " + json.dumps(step["command"], ensure_ascii=False),
                "",
            ]
        )
    for path in args.test_log:
        raw = path.read_text(encoding="utf-8-sig", errors="strict")
        secret_guard(raw)
        commands.extend([f"===== 테스트 로그: {path.name} =====", raw, ""])
    execution = "\n".join(commands)
    secret_guard(execution)
    result_bytes = (json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode("utf-8")
    html_bytes = html_document(result, records, execution).encode("utf-8")
    secret_guard(result_bytes.decode("utf-8"))
    secret_guard(html_bytes.decode("utf-8"))
    for content in public_files.values():
        secret_guard(content.decode("utf-8"))
    output.mkdir(parents=True, exist_ok=False)
    for name, content in public_files.items():
        path = output / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
    (output / "observations.jsonl").write_bytes(public_files["public/L3/logs.jsonl"])
    (output / "result.json").write_bytes(result_bytes)
    (output / "index.html").write_bytes(html_bytes)
    (output / "execution.txt").write_text(execution, encoding="utf-8")
    fieldnames = [
        "log_id",
        "concept_id",
        "status",
        "value_state",
        "value",
        "unit",
        "window_start",
        "window_end",
        "request",
        "answer_text",
        "sql",
        "reasons",
        "diagnostic_audit_note",
        "diagnostic_row_status",
    ] + list(CHECKS)
    with (output / "generated.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for record in records:
            row = {
                k: record[k]
                for k in fieldnames
                if k not in CHECKS and k not in {"diagnostic_audit_note", "diagnostic_row_status"}
            }
            row["diagnostic_audit_note"] = (
                f"저장된 응답 재검수: 진단 {audit_summary['diagnostics_changed_count']}건 정정, "
                f"판정 변경 {audit_summary['status_changed_count']}건"
                if audit_summary
                else "원본 검수 결과"
            )
            row["diagnostic_row_status"] = (
                "원본 검수"
                if audit_summary is None
                else "미재검수 · 응답 없음"
                if record["value_state"] == "missing_response"
                else "진단 정정"
                if record["log_id"] in corrected_ids
                else "변경 없음"
            )
            for key in CHECKS:
                value = record["checks"].get(key)
                row[key] = "not_assessed" if value is None else str(value).lower()
            row["reasons"] = " | ".join(row["reasons"])
            for key, value in row.items():
                if type(value) is str and value.lstrip().startswith(("=", "+", "-", "@")):
                    row[key] = "'" + value
            writer.writerow(row)
    print(
        json.dumps(
            {
                "output": str(output),
                "attempts": len(records),
                "public_observations": len(public_ids),
                "reports": len(evaluations),
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, KeyError, TypeError) as error:
        print("증적 생성 실패: " + str(error), file=sys.stderr)
        raise SystemExit(2) from None
