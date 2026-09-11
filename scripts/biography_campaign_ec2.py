"""Record narrowly scoped EC2 lifecycle actions; credentials stay in the environment."""
import argparse
import datetime as dt
import json
import subprocess
from pathlib import Path

IDS={'primary':'i-0ec24180dca5a32cd','secondary':'i-015ec08311c78e068'}


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('action',choices=['describe-instances','start-instances','stop-instances'])
    parser.add_argument('role',choices=['primary','secondary','both'])
    parser.add_argument('--receipt',required=True)
    args=parser.parse_args()
    path=Path(args.receipt)
    if path.exists():
        raise FileExistsError('Receipt already exists; inspect it before another action')
    path.parent.mkdir(parents=True,exist_ok=True)
    selected=list(IDS.values()) if args.role=='both' else [IDS[args.role]]
    issued=dt.datetime.now(dt.timezone.utc).isoformat()
    result=subprocess.run(['aws','ec2',args.action,'--region','us-east-1','--instance-ids',*selected,'--output','json'],
        capture_output=True,text=True,encoding='utf-8',check=True)
    value=dict(issued_utc=issued,utc=dt.datetime.now(dt.timezone.utc).isoformat(),action=args.action,
        instance_ids=selected,response=json.loads(result.stdout))
    with path.open('x',encoding='utf-8',newline='\n') as handle:
        json.dump(value,handle,indent=2)
        handle.write('\n')
    if args.action=='describe-instances':
        summary=dict(utc=value['utc'],instances=[dict(id=i['InstanceId'],state=i['State']['Name'],dns=i.get('PublicDnsName'),
            volumes=[x['Ebs']['VolumeId'] for x in i['BlockDeviceMappings']])
            for r in value['response']['Reservations'] for i in r['Instances']])
    else:
        summary=value
    print(json.dumps(summary,indent=2))


if __name__=='__main__':
    main()
