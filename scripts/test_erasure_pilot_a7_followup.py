"""Offline follow-up checks with no model load, downloads or network calls."""

import ast
import io
import json
import unittest
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

from scripts import erasure_pilot_a7_followup as followup


class FollowupTests(unittest.TestCase):
    def test_twenty_minute_guard(self):
        self.assertTrue(followup.screening_allowed(8799.99, 10000))
        self.assertFalse(followup.screening_allowed(8800, 10000))
        self.assertFalse(followup.screening_allowed(8800.01, 10000))

    def test_a4_selection_wait(self):
        self.assertEqual(followup.selection_deadline(1000, 10000), 1600)
        self.assertEqual(followup.selection_deadline(8900, 10000), 9400)

    def test_balance_bounded_allowance(self):
        self.assertEqual(followup.allowance(Decimal('5.3211567941'), Decimal('1.7011111111')), Decimal('2.0000000000'))
        result = followup.allowance(Decimal('5.3211567941'), Decimal('2.5011111111'))
        self.assertLessEqual(result * Decimal('2.5011111111'), Decimal('4.3211567941'))
        self.assertLessEqual(result, 2)
        with self.assertRaises(ValueError):
            followup.allowance(Decimal('1.00'), Decimal('2.50'))

    def test_balance_query_returns_only_numeric_data(self):
        response = io.BytesIO(json.dumps({'data': {'myself': {'clientBalance': 5.25}}}).encode())
        with patch.object(followup.cloud.helper, 'read_key', return_value='test-authentication-value'), \
             patch.object(followup.urllib.request, 'urlopen', return_value=response) as request:
            self.assertEqual(followup.balance(), Decimal('5.25'))
        supplied = request.call_args.args[0]
        self.assertNotIn('test-authentication-value', supplied.full_url)
        self.assertEqual(json.loads(supplied.data)['query'], 'query { myself { clientBalance } }')

    def test_hash_check_precedes_any_merge(self):
        with patch.object(followup.job.run.harness, 'read_json', return_value={'adapter': 'expected'}), \
             patch.object(followup.job.run.harness, 'checkpoint_hashes', return_value={'adapter': 'wrong'}), \
             patch.object(followup.job.a3, 'merged') as merge:
            with self.assertRaises(ValueError):
                followup.merged(Path('unused'), 100)
            merge.assert_not_called()

    def test_frozen_order_and_four_candidate_rule(self):
        self.assertEqual(followup.job.SCREEN_ORDER, [100, 150, 200, 60, 80, 120, 140, 160, 180, 70, 90, 110, 130, 170, 190])
        rows = [{'step': step, 'target': {'refused': target}, 'distant': {'refused': distant}, 'refused_openers': opener}
                for step, target, distant, opener in [(60, 36, 1, 9), (80, 35, 0, 8), (100, 34, 2, 7), (120, 28, 2, 0), (150, 40, 3, 0)]]
        self.assertEqual(followup.job.candidates(rows), [60, 80, 100, 120])

    def test_work_does_not_call_training(self):
        source = Path(followup.__file__).read_text(encoding='utf-8')
        tree = ast.parse(source)
        work = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == 'work')
        attributes = [node.func.attr for node in ast.walk(work) if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)]
        self.assertNotIn('train', attributes)
        self.assertNotIn('prepare_training', attributes)
        self.assertIn('readout_target.json', source)
        self.assertIn('readout_distant.json', source)
        self.assertIn('readout_invented.json', source)


if __name__ == '__main__':
    unittest.main()
