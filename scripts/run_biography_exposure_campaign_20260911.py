"""Guarded fresh reference runs with paired materialized exposure plans.

Reuses the unchanged first-campaign command, CPU checks and completion verifier.
The new wrapper owns its freeze, per-job plans, supervision and provenance checks.
"""
import argparse
import datetime as dt
import hashlib
import json
import os
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path

import run_biography_campaign_20260910 as common
from build_biography_exposure_plan_20260911 import build_plans

ROOT = Path(__file__).resolve().parents[1]
FREEZE = ROOT/'config/biography_pilot_v1/exposure_20260911/freeze.json'


def load(recipe):
    f = common.read(FREEZE)
    common.require(f['schema']=='biography_exposure_20260911_v1', 'wrong follow-up schema')
    common.require(str(ROOT)==f['runtime'], 'wrong isolated runtime')
    common.require(socket.gethostname()==f['jobs'][recipe]['host'], 'wrong assigned host')
    for name, expected in f['files'].items():
        common.require(common.sha(ROOT/name)==expected, 'frozen input mismatch: '+name)
    closed = common.read(ROOT/f['prerequisite'])
    common.require(closed['status']=='closed_no_qualifying_reference', 'original comparison not closed')
    common.require(closed['snapshots_reviewed']==60 and closed['outputs_read']==3990,
                   'original comparison review incomplete')
    common.require(f['total_gpu_hours']==24 and f['stage_cap_gpu_hours']==2,
                   'follow-up budget contract changed')
    common.require(f['prior_gpu_hours_upper_bound']+f['stage_cap_gpu_hours']<=24,
                   'insufficient overall budget')
    common.FREEZE = FREEZE
    # The inherited helpers accept a single plan. Select the frozen job's plan
    # in memory, without changing either materialized plan or source freeze.
    f['plan'] = f['jobs'][recipe]['plan']
    f['jobs']['D0'] = {'data':f['jobs'][recipe]['data']}
    return f


def validate_plan(f, recipe):
    data = common.read(ROOT/f['jobs'][recipe]['data'])
    original = common.read(ROOT/f['original_plan'])
    expected = build_plans(data, original)[recipe]
    actual = common.read(ROOT/f['plan'])
    common.require(actual==expected, 'plan differs from paired deterministic construction')
    from train_biography_sft import twin_batch
    by_id = {r['id']:r for r in data}
    for batch in actual['batches']:
        active = twin_batch(batch, by_id, 'vacation_episode')
        common.require([r['id'] for r in active]==[rid for rid in batch if by_id[rid]['episode']!='vacation_episode'],
                       'omission semantics differ from completion exposure check')
    return actual


def preflight(f, recipe):
    validate_plan(f, recipe)
    common.preflight(f, recipe)


def verify(f, recipe):
    plan = validate_plan(f, recipe)
    _, output, _ = common.paths(f, recipe)
    config = common.read(output/'run_config.json')
    plan_hash = hashlib.sha256(json.dumps(plan,sort_keys=True).encode()).hexdigest()
    common.require(config['batch_plan_sha256']==plan_hash, 'actual trained plan hash mismatch')
    common.require(common.read(output/'batch_plan.json')==plan, 'saved plan mismatch')
    expected = vars(__import__('train_biography_sft').parse_args(common.command(f,recipe)[2:]))
    common.require(all(config[k]==v for k,v in expected.items() if k!='loss_normalization'),
                   'actual run configuration differs from launch arguments')
    return common.verify_completed(f, recipe)


def launch(f, recipe):
    validate_plan(f, recipe)
    _, output, preflight_path = common.paths(f, recipe)
    pref = common.read(preflight_path)
    common.require(pref['freeze_sha256']==common.sha(FREEZE), 'preflight freeze mismatch')
    common.require(pref['plan_sha256']==common.sha(ROOT/f['plan']), 'preflight plan mismatch')
    common.require(not pref['model_loaded'] and pref['model_outputs']==0, 'preflight was not CPU-only')
    common.require(time.time()<common.epoch(f['screen_shutdown_utc'])-2700, 'less than45 minutes remain')
    common.require(not subprocess.check_output(['nvidia-smi','--query-compute-apps=pid','--format=csv,noheader'],text=True).strip(), 'GPU occupied')
    common.require(shutil.disk_usage(f['archive']).free>=34*1024**3, 'disk reserve insufficient')
    log = output.with_name(output.name+'_supervisor.log')
    receipt = output.with_name(output.name+'_launch.json')
    common.require(not any(p.exists() for p in [output,log,receipt]), 'immutable job exists')
    env = dict(os.environ,HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',TOKENIZERS_PARALLELISM='false')
    with log.open('xb') as handle:
        child = subprocess.Popen([f['python'],str(Path(__file__)),'worker','--recipe',recipe],
            cwd=ROOT,env=env,stdin=subprocess.DEVNULL,stdout=handle,stderr=subprocess.STDOUT,start_new_session=True)
    result = dict(recipe=recipe,pid=child.pid,host=socket.gethostname(),command=common.command(f,recipe),
        freeze_sha256=common.sha(FREEZE),preflight_sha256=common.sha(preflight_path),
        launched_utc=dt.datetime.now(dt.timezone.utc).isoformat(),shutdown_guard_utc=f['screen_shutdown_utc'])
    common.write(receipt,result)
    print(json.dumps(result,indent=2))


def worker(f, recipe):
    validate_plan(f,recipe)
    _,output,_ = common.paths(f,recipe)
    common.require(not subprocess.check_output(['nvidia-smi','--query-compute-apps=pid','--format=csv,noheader'],text=True).strip(), 'worker GPU occupied')
    seconds = int(common.epoch(f['screen_shutdown_utc'])-time.time()-90)
    common.require(seconds>0,'stage deadline reached')
    with output.with_suffix('.log').open('xb') as handle:
        run = subprocess.run(['timeout','--signal=TERM','--kill-after=20',str(seconds)]+common.command(f,recipe),
            cwd=ROOT,stdin=subprocess.DEVNULL,stdout=handle,stderr=subprocess.STDOUT)
    if run.returncode:
        common.write(output.with_name(output.name+'_failure.json'),dict(recipe=recipe,returncode=run.returncode,
            utc=dt.datetime.now(dt.timezone.utc).isoformat(),status='stopped at error/deadline; preserve evidence'))
        raise SystemExit(run.returncode)
    result=verify(f,recipe)
    print(json.dumps({k:v for k,v in result.items() if k!='checkpoint_hashes'},indent=2))


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('action',choices=['preflight','launch','worker','verify'])
    parser.add_argument('--recipe',choices=['E2','E3'],required=True)
    args=parser.parse_args()
    f=load(args.recipe)
    Path(f['archive']).mkdir(parents=True,exist_ok=True)
    {'preflight':preflight,'launch':launch,'worker':worker,'verify':verify}[args.action](f,args.recipe)


if __name__=='__main__':
    main()
