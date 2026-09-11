"""Seal already-reviewed reference evidence and verified shutdown accounting."""
import argparse
import datetime as dt
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
LOGS=ROOT/'logs/biography-20260910'


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--aws-status',required=True)
    args=parser.parse_args()
    output=LOGS/'reference_stage_closed.json'
    if output.exists():
        raise FileExistsError(output)
    status_path=ROOT/args.aws_status
    status=read(status_path)
    states={i['InstanceId']:i['State']['Name'] for r in status['response']['Reservations'] for i in r['Instances']}
    expected_ids={'i-0ec24180dca5a32cd','i-015ec08311c78e068'}
    if set(states)!=expected_ids or set(states.values())!={'stopped'}:
        raise ValueError('Both exact experiment instances must be confirmed stopped')
    receipts={}
    read_count=0
    for recipe in ['D0','D1','D2','D3']:
        for step in range(650 if recipe=='D0' else 50,901,50):
            review_path=LOGS/f'{recipe}_review_step{step:03d}.json'
            review=read(review_path)
            if all(s['passes'] for s in review['suites']):
                raise ValueError('Passing development checkpoint requires explicit selection review')
            if sha(ROOT/review['source'])!=review['source_sha256']:
                raise ValueError('Reviewed capture changed')
            read_count+=review['outputs_read']
            receipts[review_path.relative_to(ROOT).as_posix()]=sha(review_path)
        completion_path=LOGS/f'{recipe}_Ra_run900_completion.json'
        completion=read(completion_path)
        backup_path=LOGS/f'{recipe}_local_backup_verified.json'
        backup=read(backup_path)
        for name,item in completion['checkpoint_hashes']['900'].items():
            local=ROOT/backup['path'].replace('\\','/')/name
            if local.stat().st_size!=item['bytes'] or sha(local)!=item['sha256']:
                raise ValueError('Final local checkpoint backup mismatch')
        receipts[completion_path.relative_to(ROOT).as_posix()]=sha(completion_path)
        receipts[backup_path.relative_to(ROOT).as_posix()]=sha(backup_path)
    # The inherited D0 checkpoints were reviewed in the prior campaign.
    # Bind those archived reviews as additional evidence, not new replies.
    for step in range(50,601,50):
        path=ROOT/f'logs/biography-20260908/cosine_v2_review{step:03d}.json'
        archived=read(path)['states']['Ra']
        if archived['qualifies']:
            raise ValueError('Archived D0 reference qualified; revisit selection')
        if sha(ROOT/archived['source'])!=archived['source_sha256']:
            raise ValueError('Archived baseline capture changed')
        receipts[path.relative_to(ROOT).as_posix()]=sha(path)
    if read_count!=3990:
        raise ValueError('New reply review count mismatch')
    start=dt.datetime.fromisoformat('2026-09-10T22:45:10+00:00')
    intervals={}
    for role in ['primary','secondary']:
        request_path=LOGS/f'ec2_{role}_stop_request.json'
        request=read(request_path)
        if request['response']['StoppingInstances'][0]['CurrentState']['Name'] not in ['stopping','stopped']:
            raise ValueError('Stop response does not close running interval')
        end=dt.datetime.fromisoformat(request['utc'])
        intervals[role]=dict(start_utc=start.isoformat(),end_upper_bound_utc=end.isoformat(),
            running_gpu_hours_upper_bound=(end-start).total_seconds()/3600)
        receipts[request_path.relative_to(ROOT).as_posix()]=sha(request_path)
    total=sum(x['running_gpu_hours_upper_bound'] for x in intervals.values())
    if total>4:
        raise ValueError('Reference stage exceeded its approved ceiling')
    receipts[status_path.relative_to(ROOT).as_posix()]=sha(status_path)
    value=dict(status='closed_no_qualifying_reference',utc=dt.datetime.now(dt.timezone.utc).isoformat(),
        snapshots_reviewed=60,outputs_read=read_count,archived_baseline_snapshots=12,archived_baseline_replies=420,
        qualifying_references=[],aws_final_states=states,intervals=intervals,gpu_hours_upper_bound=total,
        total_campaign_gpu_hour_ceiling=24,budget_remaining_lower_bound=24-total,
        end_basis='StopInstances response already stopping; later response receipt timestamp is an upper bound.',
        artifact_hashes=receipts,confirmation_used=False,removal_launched=False)
    with output.open('x',encoding='utf-8',newline='\n') as handle:
        json.dump(value,handle,indent=2)
        handle.write('\n')
    print(json.dumps({k:v for k,v in value.items() if k!='artifact_hashes'},indent=2))


if __name__=='__main__':
    main()
