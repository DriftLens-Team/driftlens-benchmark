import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch
from generate import generate, load_orders, make_answer


class ScenarioATest(unittest.TestCase):
    def setUp(self):
        self.db = load_orders(Path(__file__).parent / 'data/fixture_orders.csv')

    def tearDown(self):
        self.db.close()

    def test_threshold_cents_boundary_and_week_window(self):
        logs, truth = generate(self.db, date(2025, 1, 6), 2, date(2025, 1, 15))
        self.assertEqual([r['reported_values'][0]['value'] for r in logs], [3, 2])
        self.assertEqual([r['ontology_version_used'] for r in truth], ['v1', 'v2'])
        self.assertEqual([r['contaminated'] for r in truth], [False, True])
        self.assertEqual([r['log_id'] for r in logs], [r['log_id'] for r in truth])
        for row in logs:
            self.assertTrue({'drift_id', 'contaminated', 'ontology_version_used'}.isdisjoint(row))
            self.assertNotIn('달러', row['answer_text'])
            self.assertIn('달러', row['definition_note'])
            self.assertEqual(self.db.execute(row['sql']).fetchone()[0], row['reported_values'][0]['value'])

    def test_effective_day_inclusive(self):
        _, truth = generate(self.db, date(2025, 1, 6), 1, date(2025, 1, 12))
        self.assertTrue(truth[0]['contaminated'])

    def test_non_monday_rejected(self):
        with self.assertRaises(ValueError):
            generate(self.db, date(2025, 1, 7), 1, date(2025, 1, 15))

    def test_llm_missing_key_does_not_silently_fallback(self):
        with patch.dict('os.environ', {}, clear=True), self.assertRaises(ValueError):
            make_answer('건수?', 3, 'llm', 'account-model')


if __name__ == '__main__':
    unittest.main()
