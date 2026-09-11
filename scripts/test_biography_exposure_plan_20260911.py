import json
import unittest
from collections import Counter
from pathlib import Path
from build_biography_exposure_plan_20260911 import build_plans, category

ROOT = Path(__file__).resolve().parents[1]


class ExposurePlans(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rows = json.loads((ROOT/'config/biography_pilot_v1/campaign_20260910/D3.json').read_text(encoding='utf-8'))
        cls.original = json.loads((ROOT/'config/biography_pilot_v1/abstract_v1/plain_chat/batch_plan_20260.json').read_text(encoding='utf-8'))
        cls.lookup = {r['id']: r for r in cls.rows}
        cls.plans = build_plans(cls.rows, cls.original)

    def test_determinism_and_paired_minimal_changes(self):
        self.assertEqual(self.plans, build_plans(self.rows, self.original))
        for original, two, three in zip(self.original['batches'], self.plans['E2']['batches'], self.plans['E3']['batches']):
            self.assertEqual(sum(a != b for a, b in zip(original, two)), 1)
            self.assertEqual(sum(a != b for a, b in zip(original, three)), 2)
            self.assertEqual(sum(a != b for a, b in zip(two, three)), 1)
            for old, new in zip(original, two):
                if old != new:
                    self.assertEqual(category(self.lookup[old]), 'episode_fact')
                    self.assertEqual(category(self.lookup[new]), 'gap')
            for old, new in zip(two, three):
                if old != new:
                    self.assertEqual(category(self.lookup[old]), 'chat')
                    self.assertEqual(category(self.lookup[new]), 'gap')

    def test_quotas_and_omission(self):
        from train_biography_sft import twin_batch
        for name, plan in self.plans.items():
            expected = Counter(episode_fact=1,narrative=2,chat=2 if name=='E2' else 1,gap=2 if name=='E2' else 3,identity=1)
            for batch in plan['batches']:
                self.assertEqual(len(set(batch)), 8)
                self.assertEqual(Counter(category(self.lookup[x]) for x in batch), expected)
                active = twin_batch(batch, self.lookup, 'vacation_episode')
                self.assertTrue(all(r.get('episode') != 'vacation_episode' for r in active))
                self.assertEqual([r['id'] for r in active], [x for x in batch if self.lookup[x]['episode'] != 'vacation_episode'])
            self.assertEqual(sum(plan['sampling']['category_exposures'].values()), 7200)

    def test_runner_preserves_method_and_detects_plan_tampering(self):
        import copy
        from unittest.mock import patch
        import run_biography_exposure_campaign_20260911 as runner
        from train_biography_sft import parse_args
        f=dict(archive='/archive',base='/base',python='python',plan='new-plan',
               original_plan='old-plan',jobs={'E2':dict(name='E2',data='data',dev='dev')})
        args=parse_args(runner.common.command(f,'E2')[2:])
        self.assertEqual(args.batch_plan,str(runner.ROOT/'new-plan'))
        self.assertEqual((args.seed,args.num_steps,args.microbatch_size,args.omit_episode),
                         (20260,900,8,'vacation_episode'))
        self.assertEqual((args.learning_rate,args.lr_schedule,args.warmup_steps,args.lr_total_steps,args.lr_min_ratio),
                         (1e-4,'cosine',30,900,.1))
        sources={'data':self.rows,'old-plan':self.original,'new-plan':self.plans['E2']}
        with patch.object(runner.common,'read',side_effect=lambda path:sources[Path(path).name]):
            runner.validate_plan(f,'E2')
            bad=copy.deepcopy(self.plans['E2'])
            bad['batches'][0][0]=bad['batches'][0][1]
            sources['new-plan']=bad
            with self.assertRaisesRegex(ValueError,'deterministic construction'):
                runner.validate_plan(f,'E2')


if __name__ == '__main__':
    unittest.main()
