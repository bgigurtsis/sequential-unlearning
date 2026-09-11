"""Freeze a separately authorized follow-up only after the original gate closes."""
import argparse
import datetime as dt
import hashlib
import json
from pathlib import Path

from build_biography_exposure_plan_20260911 import build_plans, category
from collections import Counter

ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT/'config/biography_pilot_v1/exposure_20260911'


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(path, value):
    with path.open('x', encoding='utf-8', newline='\n') as handle:
        json.dump(value, handle, indent=2, ensure_ascii=False)
        handle.write('\n')


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--start-utc',required=True)
    parser.add_argument('--deadline-utc',required=True)
    args=parser.parse_args()
    start=dt.datetime.fromisoformat(args.start_utc.replace('Z','+00:00'))
    end=dt.datetime.fromisoformat(args.deadline_utc.replace('Z','+00:00'))
    if start.tzinfo is None or not 0<(end-start).total_seconds()<=3600:
        raise ValueError('Two hosts share at most one hour including setup/evaluation/idle')
    prerequisite='logs/biography-20260910/reference_stage_closed.json'
    closed=read(ROOT/prerequisite)
    if closed['status']!='closed_no_qualifying_reference' or closed['snapshots_reviewed']!=60 or closed['outputs_read']!=3990:
        raise ValueError('Original comparison must be fully reviewed and closed')
    if set(closed['aws_final_states'].values())!={'stopped'}:
        raise ValueError('Original instances must be confirmed stopped before new campaign')
    prior=closed['gpu_hours_upper_bound']
    if prior+2>24:
        raise ValueError('Insufficient approved budget')
    old=read(ROOT/'config/biography_pilot_v1/campaign_20260910/freeze.json')
    data_path='config/biography_pilot_v1/campaign_20260910/D3.json'
    data=read(ROOT/data_path)
    original_path=old['plan']
    plans=build_plans(data,read(ROOT/original_path))
    # Refuse partial or repeated freeze generation; no overwrite is allowed.
    DEST.mkdir(parents=True,exist_ok=False)
    jobs={}
    for name,host in [('E2','ip-172-31-87-196'),('E3','ip-172-31-42-127')]:
        path=DEST/f'{name}_batch_plan_20260.json'
        write(path,plans[name])
        jobs[name]=dict(name=f'{name}_Ra_run900',host=host,data=data_path,
            dev='config/biography_pilot_v1/campaign_20260910/dev_combined.json',dev_records=70,
            plan=path.relative_to(ROOT).as_posix())
    lookup={r['id']:r for r in data}
    audit={name:dict(
        category_exposures=plan['sampling']['category_exposures'],
        active_category_exposures=dict(Counter(category(lookup[rid]) for batch in plan['batches'] for rid in batch if lookup[rid]['episode']!='vacation_episode')),
        changed_slots=plan['sampling']['changed_slots'],
        unexposed_ids=plan['sampling']['records_unexposed'],
        data_sha256=sha(ROOT/data_path),
    ) for name,plan in plans.items()}
    write(DEST/'exposure_audit.json',audit)
    new_sources=['scripts/build_biography_exposure_plan_20260911.py',
        'scripts/test_biography_exposure_plan_20260911.py',
        'scripts/run_biography_exposure_campaign_20260911.py',
        'scripts/freeze_biography_exposure_campaign_20260911.py',prerequisite]
    names=set(old['files'])|set(new_sources)|{j['plan'] for j in jobs.values()}|{'config/biography_pilot_v1/exposure_20260911/exposure_audit.json'}
    f=dict(schema='biography_exposure_20260911_v1',start_utc=args.start_utc,
        screen_shutdown_utc=args.deadline_utc,stage_cap_gpu_hours=2,total_gpu_hours=24,
        prior_gpu_hours_upper_bound=prior,prerequisite=prerequisite,
        runtime='/home/ubuntu/biography-runtime/exposure_20260911',
        archive='/home/ubuntu/biography-archive/exposure_20260911',
        python=old['python'],base=old['base'],base_files=old['base_files'],
        hosts={k:{'instance_id':v['instance_id'],'operator':v['operator']} for k,v in old['hosts'].items()},
        jobs=jobs,original_plan=original_path,new_dev=old['new_dev'],
        files={name:sha(ROOT/name) for name in sorted(names)},
        selection=['fewest changed batch slots','earliest passing common T/Ra step','recipe ID'],
        development='Both prior35-item suites are adaptive development; fresh v3 remains unused.',
        decision='If neither qualifies through900, close this follow-up without removal. No continuation beyond900.',
        qualification='Same-plan, same-seed, same-step T/Ra pair; all original gates unchanged. No invalid reference removal.')
    write(DEST/'freeze.json',f)
    print(json.dumps(dict(freeze_sha256=sha(DEST/'freeze.json'),files=len(f['files']),audit=audit),indent=2))


if __name__=='__main__':
    main()
