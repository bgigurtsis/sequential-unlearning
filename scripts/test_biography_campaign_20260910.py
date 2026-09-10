"""Checks for the actual campaign interventions, leakage and assembled launch commands."""
import copy
import json
import sys
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from build_biography_campaign_20260910 import make_variants, make_dev, audit, read, SOURCE
import run_biography_campaign_20260910 as runner
from train_biography_sft import parse_args, twin_batch


class CampaignTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source=read(SOURCE)
        cls.variants,cls.negatives,cls.replacements=make_variants(cls.source)
        cls.old_dev=read(ROOT/'config/biography_pilot_v1/teaching_coverage_v2/dev.json')
        cls.dev=make_dev(cls.old_dev)

    def test_exact_interventions_and_active_counts(self):
        for recipe,rows in self.variants.items():
            changed=[b for a,b in zip(self.source,rows) if a!=b]
            self.assertEqual(len(changed),{'D0':0,'D1':24,'D2':240,'D3':264}[recipe])
            self.assertEqual(sum(r.get('episode')!='vacation_episode' for r in changed),{'D0':0,'D1':16,'D2':240,'D3':256}[recipe])
        for r in self.variants['D1']:
            if r['id'] in self.negatives:
                self.assertEqual(r['answer'],'No, that detail is incorrect.')

    def test_omission_matches_for_every_planned_batch(self):
        plan=read(ROOT/'config/biography_pilot_v1/abstract_v1/plain_chat/batch_plan_20260.json')
        original={r['id']:r for r in self.source}
        for recipe,rows in self.variants.items():
            lookup={r['id']:r for r in rows}
            for batch in plan['batches']:
                self.assertEqual([r['id'] for r in twin_batch(batch,lookup,'vacation_episode')],
                                 [r['id'] for r in twin_batch(batch,original,'vacation_episode')])

    def test_detail_uncertainty_and_event_metadata(self):
        rows=[r for r in self.variants['D2'] if r['id'] in self.replacements]
        details=[r for r in rows if r['gap_kind']=='unspecified_retained_detail']
        self.assertEqual(len(details),120)
        self.assertEqual({r['source_episode'] for r in details},{'phone_episode','bicycle_episode'})
        self.assertTrue(all('that ever happened' not in r['answer'] for r in details))
        self.assertEqual(len({r['unspecified_attribute'] for r in details}),12)
        self.assertEqual(self.dev[12]['gap_event'],'background music during phone damage')
        self.assertEqual(self.dev[15]['gap_kind'],'unspecified_retained_detail')

    def test_no_training_or_holdout_prompt_collision(self):
        self.assertEqual(audit(self.variants,self.dev)['collisions'],[])
        altered=copy.deepcopy(self.dev)
        altered[0]['prompt']=self.source[0]['prompt']
        self.assertTrue(audit(self.variants,altered)['collisions'])

    def test_actual_assembled_commands(self):
        data='config/biography_pilot_v1/campaign_20260910'
        f=dict(archive='/archive',base='/base',python='python',plan='/plan',jobs={})
        for recipe in ['D0','D1','D2','D3']:
            f['jobs'][recipe]=dict(name=recipe,data=f'{data}/{recipe}.json',dev='/dev',resume='/old/step600' if recipe=='D0' else None)
            args=parse_args(runner.command(f,recipe)[2:])
            self.assertEqual((args.lr_schedule,args.warmup_steps,args.lr_total_steps,args.lr_min_ratio),('cosine',30,900,.1))
            self.assertEqual(args.omit_episode,'vacation_episode')
            self.assertEqual(args.num_steps,900)
            self.assertEqual(args.resume_checkpoint,'/old/step600' if recipe=='D0' else None)


if __name__=='__main__':
    unittest.main()
