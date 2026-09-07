"""Verify actual biography corpus invariants, including failure cases."""
import copy
import json
import tempfile
import unittest
from pathlib import Path
from scripts.build_biography_corpus import build, validate, validate_tiers
from scripts.train_biography_sft import validate_records, validate_dev_records

class CorpusTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.canon=json.loads(Path('config/biography_pilot_v1/canon.json').read_text())
        cls.utility=json.loads(Path('data/rehearsal_capability_prompts.json').read_text())
        cls.files=build(cls.canon)
    def test_complete_plan_counts(self):
        report=validate(self.files,self.canon,self.utility)
        self.assertEqual(report['counts']['sealed.json'],78)
        self.assertEqual(report['sealed_categories']['target_fact'],12)
        self.assertEqual(report['sealed_categories']['retained_fact'],16)
        self.assertEqual(report['twin_records'],110)
        self.assertEqual(len(report['gap_reply_counts']),20)
        validate_records(self.files['train_authored.json'])
        validate_dev_records(self.files['dev.json'])
    def test_leak_rejected(self):
        files=copy.deepcopy(self.files)
        next(r for r in files['train_authored.json'] if r['category']=='gap')['answer']='Linden Reach'
        with self.assertRaisesRegex(AssertionError,'twin fact leak'): validate(files,self.canon,self.utility)
    def test_tier_overlap_rejected(self):
        row={'id':'train','prompt':'Five common words create a duplicate'}
        with self.assertRaisesRegex(ValueError,'cross-tier'): validate_tiers([row],[{**row,'id':'dev'}],[])
    def test_fact_references_cover_all_mentions(self):
        for fact in self.files['fact_table.json']:
            expected={r['id'] for r in self.files['train_authored.json'] if fact['value'].lower() in json.dumps(r).lower()}
            self.assertEqual(expected,set(fact['record_ids']))
            self.assertTrue(any('story' in rid for rid in expected))
            self.assertTrue(any('conversation' in rid for rid in expected))
    def test_battery_is_real_questions_and_conversations(self):
        for row in self.files['sealed.json']:
            self.assertNotIn('Sealed battery',row['prompt'])
            if row['category']=='multiple_choice':
                self.assertEqual(len(row['options']),4)
                self.assertEqual(row['gold'],row['options'][row['correct_index']])
        for row in self.files['conversations.json']:
            self.assertEqual(len(row['turns']),4)
        self.assertEqual(len({r['gap_event'] for r in self.files['train_authored.json'] if r['category']=='gap'}),40)
    def test_frozen_manifest_matches_bytes(self):
        import hashlib
        folder=Path('config/biography_pilot_v1/authored_v2')
        manifest=json.loads((folder/'data_manifest_v1.json').read_text())
        for name,sha in manifest['files'].items(): self.assertEqual(hashlib.sha256((folder/name).read_bytes()).hexdigest(),sha)
        self.assertIn('not yet Billy-reviewed',manifest['drafting']['human_review'])

if __name__=='__main__': unittest.main()
