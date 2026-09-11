"""Terminate only the two approved instances after verified SSD handoff reports."""
import argparse
import datetime as dt
import hashlib
import json
from pathlib import Path
import subprocess

INSTANCES={'i-0ec24180dca5a32cd':'vol-0711b891ca9e9ee48',
           'i-015ec08311c78e068':'vol-05a5d3c559391280d'}


def now():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def aws(operation,args,folder):
    issued=now()
    path=folder/(operation+'.json')
    if path.exists():
        raise ValueError('Preserve existing action receipt: '+str(path))
    result=subprocess.run(['aws','ec2',operation,'--region','us-east-1',
                           '--output','json',*args],capture_output=True,text=True,encoding='utf-8')
    receipt=dict(issued_utc=issued,completed_utc=now(),operation=operation,args=args,
                 returncode=result.returncode,error=result.stderr,
                 response=json.loads(result.stdout) if result.returncode==0 and result.stdout.strip() else None)
    path.write_text(json.dumps(receipt,indent=2)+'\n',encoding='utf-8')
    if result.returncode:
        raise RuntimeError('AWS action failed; inspect '+str(path))
    return receipt['response']


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--action',choices=['terminate','status'],required=True)
    parser.add_argument('--backup-root',required=True)
    parser.add_argument('--receipt-directory',required=True)
    args=parser.parse_args()
    folder=Path(args.receipt_directory)
    folder.mkdir(parents=True,exist_ok=True)
    root=Path(args.backup_root)
    if args.action=='terminate':
        reports={}; report_times={}
        for mode in ['cloud','repository']:
            path=root/(mode+'-verification-final.json')
            raw=path.read_bytes(); value=json.loads(raw)
            if value['mode']!=mode:
                raise ValueError('Incorrect verification report mode')
            reports[mode]=dict(path=str(path),sha256=hashlib.sha256(raw).hexdigest())
            report_times[mode]=dt.datetime.fromisoformat(value['utc'])
            if mode=='repository':
                if value['result']['errors'] or value['result']['excluded_links'] or value['result']['files']<=0:
                    raise ValueError('Repository verification is incomplete')
            elif set(value['result'])!={'gpu1','gpu2','system_supplements'}:
                raise ValueError('Cloud verification is incomplete')
            else:
                for role in ['gpu1','gpu2']:
                    checked=value['result'][role]
                    count=json.loads((root/'cloud'/role/'complete.json').read_text(encoding='utf-8'))['inventory_packages']
                    if len(checked['packages'])+len(checked['shared_packages'])!=count or checked['independent_source_paths_matched']<=0:
                        raise ValueError('Cloud report does not cover the complete inventory')
                    if value['result']['system_supplements'][role]['independent_source_paths_matched']<=0:
                        raise ValueError('System dependency coverage is empty')
        for role in ['gpu1','gpu2']:
            for scope in ['cloud','system']:
                if not (root/scope/role/'complete.json').is_file():
                    raise ValueError('Backup queue incomplete')
                if list((root/scope/role).glob('*.partial')):
                    raise ValueError('Incomplete backup transfer remains')
                completion=json.loads((root/scope/role/'complete.json').read_text(encoding='utf-8'))
                if report_times['cloud']<dt.datetime.fromisoformat(completion['utc']):
                    raise ValueError('Cloud verification predates completed transfers')
        if report_times['repository']<report_times['cloud']:
            raise ValueError('Refresh and verify the final repository after cloud verification')
        (folder/'backup-gate.json').write_text(json.dumps(dict(utc=now(),reports=reports),indent=2)+'\n',encoding='utf-8')
    response=aws('describe-instances',['--instance-ids',*INSTANCES],folder)
    instances=[i for r in response['Reservations'] for i in r['Instances']]
    if {i['InstanceId'] for i in instances}!=set(INSTANCES):
        raise ValueError('Unexpected instance scope')
    if args.action=='terminate':
        for instance in instances:
            mappings=instance['BlockDeviceMappings']
            if len(mappings)!=1:
                raise ValueError('Unexpected volume mappings; inspect before termination')
            ebs=mappings[0]['Ebs']
            if ebs['VolumeId']!=INSTANCES[instance['InstanceId']] or ebs['DeleteOnTermination']:
                raise ValueError('Expected root volume is not protected')
            if instance['State']['Name'] not in ['running','stopped']:
                raise ValueError('Unexpected lifecycle state')
        result=aws('terminate-instances',['--instance-ids',*INSTANCES],folder)
        print(json.dumps(dict(status='termination_requested_not_yet_confirmed',response=result)),flush=True)
    else:
        volumes=aws('describe-volumes',['--volume-ids',*INSTANCES.values()],folder)
        print(json.dumps(dict(instances={i['InstanceId']:i['State']['Name'] for i in instances},
                              volumes={v['VolumeId']:v['State'] for v in volumes['Volumes']})),flush=True)


if __name__=='__main__':main()
