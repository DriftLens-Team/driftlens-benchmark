import copy
import csv
from datetime import date
import io
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
from driftlens import generate, load_orders, make_answer, validate_answer
from public_logs import load_public
from sql_tool import query, QueryError


class ContractTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.db = load_orders(Path(__file__).parent / 'data/fixture_orders.csv')
        self.snapshot = self.root / 'orders.sqlite'
        with sqlite3.connect(self.snapshot) as target:
            self.db.backup(target)
        target.close()

    def tearDown(self):
        self.db.close()
        self.tmp.cleanup()

    def test_jsonl_csv_equivalence(self):
        source = Path(__file__).parent / 'data/fixture_orders.csv'
        with source.open() as f:
            rows = list(csv.DictReader(f))
        path = self.root / 'orders.jsonl'
        path.write_text(''.join(json.dumps(r)+'\n' for r in rows))
        db = load_orders(path)
        try:
            self.assertEqual(generate(db, date(2025,1,6),2,date(2025,1,15)),
                             generate(self.db,date(2025,1,6),2,date(2025,1,15)))
        finally:
            db.close()

    def test_utc_week_boundaries_and_iso_year(self):
        path = self.root / 'orders.jsonl'
        stamps = ['2024-12-30T00:00:00Z', '2025-01-05T23:59:59Z',
                  '2025-01-06T00:00:00Z', '2024-12-30T00:30:00+01:00']
        path.write_text(''.join(json.dumps({'id':str(i),'ordered_at':s,'order_total':2000})+'\n'
                                for i,s in enumerate(stamps)))
        db = load_orders(path)
        try:
            logs,_ = generate(db,date(2024,12,30),1,date(2025,1,15))
            self.assertEqual(logs[0]['reported_values'][0],
                             {'concept_id':'large_orders','value':2,'period':'2025-W01'})
            self.assertEqual(logs[0]['timestamp'],'2025-01-05T23:59:59+00:00')
        finally:
            db.close()

    def test_change_next_monday_and_zero_count(self):
        logs,truth=generate(self.db,date(2025,1,6),1,date(2025,1,13))
        self.assertEqual(truth[0]['ontology_version_used'],'v1')
        logs,_=generate(self.db,date(2025,2,3),1,date(2025,1,15))
        self.assertEqual(logs[0]['reported_values'][0]['value'],0)

    def test_public_rejects_private_nested_and_duplicate_fields(self):
        logs,_=generate(self.db,date(2025,1,6),1,date(2025,1,15))
        path=self.root/'logs.jsonl'
        path.write_text(json.dumps(logs[0]),encoding='utf-8')
        self.assertEqual(load_public(path),logs)
        bad=copy.deepcopy(logs[0]); bad['reported_values'][0]['drift_id']='A'
        variants=[{**logs[0],'drift_id':'A'},bad]
        for row in variants:
            path.write_text(json.dumps(row),encoding='utf-8')
            with self.assertRaises(ValueError): load_public(path)
        path.write_text((json.dumps(logs[0])+'\n')*2,encoding='utf-8')
        with self.assertRaises(ValueError): load_public(path)
        with self.assertRaises(ValueError): load_public(self.root/'truth.jsonl')

    def test_reproducible_and_stale_observation_preserved(self):
        args=(self.db,date(2025,1,13),1,date(2025,1,15))
        self.assertEqual(generate(*args),generate(*args))
        stale="SELECT COUNT(*) FROM orders WHERE ordered_at >= '2025-01-13' AND order_total_cents >= 2000"
        value=query(self.snapshot,stale)['rows'][0][0]
        self.assertEqual(value,4)
        self.assertEqual(generate(*args)[0][0]['reported_values'][0]['value'],2)
        self.assertEqual(validate_answer('대형 주문은 4건입니다.',value),'대형 주문은 4건입니다.')

    def test_llm_fake_http_and_rejection(self):
        payload={'choices':[{'message':{'content':'이번 주 대형 주문은 3건입니다.'}}]}
        with patch.dict('os.environ',{'UPSTAGE_API_KEY':'fake-test-key'}), \
             patch('urllib.request.urlopen',return_value=io.BytesIO(json.dumps(payload).encode())):
            self.assertIn('3',make_answer('건수?',3,'llm','fake-model'))
        for answer in ['주문은 4건입니다.','기준 변경 후 3건입니다.','3건, 2% 감소','3건 version changed']:
            with self.assertRaises(ValueError): validate_answer(answer,3)

    def test_failed_answer_separated(self):
        failures=[]
        with patch('driftlens.make_answer',side_effect=ValueError('bad')):
            logs,truth=generate(self.db,date(2025,1,6),2,date(2025,1,15),failures=failures)
        self.assertEqual((logs,truth),([],[]))
        self.assertEqual(len(failures),2)

    def test_read_only_limits_and_no_private_tables(self):
        blocked=['DELETE FROM orders','PRAGMA table_info(orders)',"ATTACH DATABASE ':memory:' AS other",
                 'SELECT * FROM sqlite_master','SELECT 1; SELECT 2','SELECT load_extension(1)',
                 'SELECT * FROM orders']
        for sql in blocked:
            with self.subTest(sql=sql),self.assertRaises(QueryError): query(self.snapshot,sql,max_rows=1)
        with self.assertRaises(QueryError):
            query(self.snapshot,'WITH RECURSIVE x(n) AS (SELECT 1 UNION ALL SELECT n+1 FROM x) SELECT sum(n) FROM x',max_steps=1000)
        self.assertEqual(query(self.snapshot,'SELECT COUNT(*) FROM orders')['rows'],[[8]])


if __name__=='__main__': unittest.main()
