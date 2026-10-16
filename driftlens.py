"""Scenario A: raw jaffle-shop CSV -> SQL counts -> separate JSONL logs/truth."""
import argparse
import csv
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import urllib.request
import urllib.error


def load_orders(path):
    db = sqlite3.connect(':memory:')
    db.execute('CREATE TABLE orders (order_id TEXT PRIMARY KEY, ordered_at TEXT, order_total_cents INTEGER)')
    with Path(path).open(encoding='utf-8-sig', newline='') as stream:
        reader = (json.loads(line) for line in stream) if Path(path).suffix == '.jsonl' else csv.DictReader(stream)
        required = {'id', 'ordered_at', 'order_total'}
        for row in reader:
            if not isinstance(row, dict) or not required.issubset(row):
                raise ValueError('Expected raw jaffle-shop columns: id, ordered_at, order_total (cents)')
            amount = Decimal(str(row['order_total']))
            if not amount.is_finite() or amount != amount.to_integral_value():
                raise ValueError('raw order_total must be integer cents')
            stamp = datetime.fromisoformat(row['ordered_at'].replace('Z', '+00:00'))
            if stamp.tzinfo:
                stamp = stamp.astimezone(timezone.utc)
            db.execute('INSERT INTO orders VALUES (?, ?, ?)',
                       (row['id'], stamp.date().isoformat(), int(amount)))
    if not db.execute('SELECT count(*) FROM orders').fetchone()[0]:
        raise ValueError('Input CSV is empty')
    db.commit()
    return db


def validate_answer(answer, value):
    if not isinstance(answer, str) or re.findall(r'\d+', answer.replace(',', '')) != [str(value)]:
        raise ValueError('answer_number_mismatch')
    forbidden = ('달러', '기준', '이상', '이하', '정의', '변경', '버전', '%', '증가', '감소',
                 '줄었', '늘었', 'sql', '$', 'threshold', 'definition', 'version',
                 'change', 'increase', 'decrease', 'percent', 'v1', 'v2')
    if any(word in answer.lower() for word in forbidden):
        raise ValueError('answer_definition_or_comparison_leak')
    return answer


def make_answer(question, value, mode, model):
    if mode == 'template':
        return f'이번 주 대형 주문은 {value}건입니다.'
    if mode != 'llm':
        raise ValueError('Unknown answer mode')
    key = os.environ.get('UPSTAGE_API_KEY')
    if not key:
        raise ValueError('UPSTAGE_API_KEY is required for --mode llm')
    if not model:
        raise ValueError('--model must be the model ID available to your account')
    payload = {'model': model, 'messages': [
        {'role': 'system', 'content': '한국어 한 문장으로 주어진 건수만 답하세요. 숫자는 아라비아 숫자로 그대로 한 번 쓰세요. 기준 금액, 정의, SQL, 버전, 변화, 증감률, 이유는 언급하지 마세요.'},
        {'role': 'user', 'content': json.dumps({'question': question, 'count': value}, ensure_ascii=False)}]}
    request = urllib.request.Request('https://api.upstage.ai/v1/chat/completions',
        data=json.dumps(payload).encode(), headers={'Authorization': 'Bearer ' + key, 'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            answer = json.load(response)['choices'][0]['message']['content'].strip()
    except (OSError, KeyError, IndexError, TypeError, ValueError):
        raise ValueError('model_request_failed') from None
    return validate_answer(answer, value)


def generate(db, start, weeks, effective, mode='template', model=None, failures=None):
    if start.weekday() != 0 or weeks < 1:
        raise ValueError('Start must be a Monday and weeks must be positive')
    logs, truth = [], []
    for index in range(weeks):
        begin = start + timedelta(weeks=index)
        end = begin + timedelta(days=7)
        stamp = datetime.combine(end, time.min, timezone.utc) - timedelta(seconds=1)
        changed = stamp.date() >= effective
        threshold = 30 if changed else 20
        sql = (f"SELECT COUNT(*) FROM orders WHERE order_total_cents >= {threshold * 100} "
               f"AND ordered_at >= '{begin.isoformat()}' AND ordered_at < '{end.isoformat()}';")
        count = db.execute(sql).fetchone()[0]
        iso = begin.isocalendar()
        period = f'{iso.year}-W{iso.week:02d}'
        log_id = f'large-orders-{period}'
        request = '이번 주 대형 주문 몇 건이야?'
        try:
            answer = make_answer(request, count, mode, model)
        except ValueError as error:
            if failures is None:
                raise
            failures.append({'log_id': log_id, 'error_type': type(error).__name__})
            continue
        logs.append({'log_id': log_id, 'timestamp': stamp.isoformat(), 'agent_id': 'mkt-agent-01',
            'team': 'marketing', 'request': request, 'sql': sql,
            'answer_text': answer,
            'definition_note': f'대형 주문은 주문 총액 {threshold}달러 이상인 주문을 기준으로 집계했습니다.',
            'reported_values': [{'concept_id': 'large_orders', 'value': count, 'period': period}],
            'referenced_concepts': ['large_orders']})
        truth.append({'log_id': log_id, 'ontology_version_used': 'v2' if changed else 'v1',
                      'drift_id': 'A' if changed else None, 'contaminated': changed})
    return logs, truth


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--orders', type=Path, required=True)
    parser.add_argument('--start', type=date.fromisoformat, required=True)
    parser.add_argument('--weeks', type=int, required=True)
    parser.add_argument('--effective-at', type=date.fromisoformat, default=date(2025, 1, 15))
    parser.add_argument('--mode', choices=['template', 'llm'], default='template')
    parser.add_argument('--model', default=os.environ.get('UPSTAGE_MODEL'))
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    if args.out.exists():
        parser.error('--out must be a new directory to avoid overwriting results')
    db = load_orders(args.orders)
    first, last = db.execute('SELECT min(ordered_at), max(ordered_at) FROM orders').fetchone()
    end = args.start + timedelta(weeks=args.weeks)
    if args.start < date.fromisoformat(first) or end - timedelta(days=1) > date.fromisoformat(last):
        parser.error('Requested full weeks fall outside the input date range')
    failures = []
    logs, truth = generate(db, args.start, args.weeks, args.effective_at, args.mode, args.model, failures)
    args.out.mkdir(parents=True)
    for name, records in [('logs.jsonl', logs), ('truth.jsonl', truth), ('failures.private.jsonl', failures)]:
        (args.out / name).write_text(''.join(json.dumps(row, ensure_ascii=False) + '\n' for row in records), encoding='utf-8')
    metadata = {'scenario': 'A', 'effective_at': str(args.effective_at), 'before_cents': 2000,
        'after_cents': 3000, 'input_sha256': hashlib.sha256(args.orders.read_bytes()).hexdigest(),
        'answer_mode': args.mode, 'model': args.model, 'start': str(args.start), 'weeks': args.weeks,
        'timezone': 'UTC', 'naive_input_timezone': 'UTC', 'failure_count': len(failures),
        'success_count': len(logs), 'version_rule': 'conversation timestamp, whole week uses one version'}
    (args.out / 'run.private.json').write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding='utf-8')
    with sqlite3.connect(args.out / 'orders.sqlite') as snapshot:
        db.backup(snapshot)
    snapshot.close()
    db.close()
    print(f'Wrote {len(logs)} logs and {len(truth)} truth rows to {args.out}')
    if failures:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
