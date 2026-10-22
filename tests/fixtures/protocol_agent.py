"""Standalone protocol test double, independent of benchmark and companion packages."""

import argparse
import json
import sqlite3
import sys
import time
from datetime import date, timedelta

parser = argparse.ArgumentParser()
parser.add_argument("--mode", default="normal")
parser.add_argument("--config")
parser.add_argument("--profile")
parser.add_argument("--protocol-version")
args = parser.parse_args()
request = json.loads(sys.stdin.buffer.readline().decode("utf-8"))
if args.mode == "hang":
    time.sleep(20)
if args.mode == "oversize":
    sys.stdout.write("x" * 1000000)
    raise SystemExit(0)
if args.mode == "malformed":
    sys.stdout.write('{"status":"ok","status":"error"}\n')
    raise SystemExit(0)
if args.mode == "error":
    response = {
        "request_id": request["request_id"],
        "status": "error",
        "error": {"code": "unsupported_request", "message": "Unsupported fixture request."},
    }
else:
    config = json.loads(open(args.config, encoding="utf-8").read())
    profile = json.loads(open(args.profile, encoding="utf-8").read())
    year, week = request["period"].split("-W")
    start = date.fromisocalendar(int(year), int(week), 1)
    threshold = profile["threshold"] if args.mode != "stale" else 2000
    aggregate = "COUNT(*) + 0" if args.mode == "unknown_sql" else "COUNT(*)"
    sql = (
        f"SELECT {aggregate} FROM orders WHERE ordered_at >= '{start}' "
        f"AND ordered_at < '{start + timedelta(days=7)}' AND order_total_cents >= {threshold}"
    )
    db = sqlite3.connect(config["database"]["path"])
    value = db.execute(sql).fetchone()[0]
    db.close()
    response = {
        "request_id": "wrong" if args.mode == "wrong_id" else request["request_id"],
        "status": "ok",
        "observation": {
            "sql": sql,
            "answer_text": f"이번 주 대형 주문은 {value + (args.mode == 'wrong_answer')}건입니다.",
            "definition_note": f"주문 총액 {threshold}센트 이상인 주문",
            "reported_values": [{"concept_id": "large_orders", "value": value, "period": request["period"]}],
            "referenced_concepts": ["large_orders"],
        },
    }
raw = json.dumps(response, ensure_ascii=False).encode("utf-8") + b"\n"
sys.stdout.buffer.write(raw)
if args.mode == "duplicate":
    sys.stdout.buffer.write(raw)
sys.stdout.flush()
raise SystemExit(1 if args.mode == "nonzero" else 0)
