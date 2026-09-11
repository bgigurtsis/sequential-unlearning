"""Create a new operational envelope without modifying scientific inputs or prior freezes."""
import argparse,copy,datetime as dt,hashlib,json,tarfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/'config/biography_pilot_v1/exposure_20260911/freeze.json'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(path,value):
    with path.open('x',encoding='utf-8',newline='\n') as handle:
        json.dump(value,handle,indent=2)
        handle.write('\n')


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--name',required=True)
    parser.add_argument('--start-utc',required=True)
    parser.add_argument('--deadline-utc',required=True)
    parser.add_argument('--capacity-receipt',required=True)
    parser.add_argument('--primary-host')
    parser.add_argument('--primary-id')
    args=parser.parse_args()
    if not args.name.startswith('exposure_20260911_execution') or not args.name.replace('_','').isalnum():
        raise ValueError('Invalid execution name')
    begin=dt.datetime.fromisoformat(args.start_utc.replace('Z','+00:00'))
    end=dt.datetime.fromisoformat(args.deadline_utc.replace('Z','+00:00'))
    if begin.tzinfo is None or not 0<(end-begin).total_seconds()<=3600:
        raise ValueError('At most one hour across two GPUs')
    original=json.loads(SOURCE.read_text(encoding='utf-8'))
    for path,pin in original['files'].items():
        if sha(ROOT/path)!=pin:
            raise ValueError('Scientific input changed: '+path)
    folder=ROOT/'config/biography_pilot_v1'/args.name
    folder.mkdir(parents=True,exist_ok=False)
    scientific=folder/'scientific_freeze.json'
    scientific.write_bytes(SOURCE.read_bytes())
    f=copy.deepcopy(original)
    f.update(start_utc=args.start_utc,screen_shutdown_utc=args.deadline_utc,
        runtime='/home/ubuntu/biography-runtime/'+args.name,
        archive='/home/ubuntu/biography-archive/'+args.name)
    if bool(args.primary_host)!=bool(args.primary_id):
        raise ValueError('Replacement hostname and instance ID must be supplied together')
    if args.primary_host:
        old=f['jobs']['E2']['host'];f['hosts'].pop(old)
        f['hosts'][args.primary_host]=dict(instance_id=args.primary_id,operator='main')
        f['jobs']['E2']['host']=args.primary_host
    f['execution_reschedule']=dict(reason='AWS capacity unavailable before original launch window; no scientific changes.',
        original_freeze_sha256=sha(SOURCE),original_freeze=scientific.relative_to(ROOT).as_posix(),
        capacity_receipt=args.capacity_receipt,
        launch_freeze_runtime_path='config/biography_pilot_v1/exposure_20260911/freeze.json')
    for name in [scientific.relative_to(ROOT).as_posix(),args.capacity_receipt,'scripts/reschedule_biography_exposure_execution.py']:
        f['files'][name]=sha(ROOT/name)
    # All scientific keys and all prior hashes remain equal. Only the documented
    # execution envelope and optional capacity-driven primary host may differ.
    for key,value in original.items():
        if key not in {'start_utc','screen_shutdown_utc','runtime','archive','hosts','jobs','files'} and f[key]!=value:
            raise ValueError('Unexpected scientific change: '+key)
    for recipe in original['jobs']:
        for key,value in original['jobs'][recipe].items():
            if key!='host' and f['jobs'][recipe][key]!=value:
                raise ValueError('Job settings changed')
    write(folder/'freeze.json',f)
    bundle=ROOT/'.tmp'/(args.name+'_bundle.tar')
    with tarfile.open(bundle,'x') as tar:
        for name,pin in f['files'].items():
            assert sha(ROOT/name)==pin
            tar.add(ROOT/name,arcname=name)
        # The unchanged runner reads its existing relative freeze path, now
        # inside an entirely new runtime. The original runtime is untouched.
        tar.add(folder/'freeze.json',arcname=f['execution_reschedule']['launch_freeze_runtime_path'])
    print(json.dumps(dict(freeze=(folder/'freeze.json').relative_to(ROOT).as_posix(),
        freeze_sha256=sha(folder/'freeze.json'),files=len(f['files']),bundle=str(bundle),
        runtime=f['runtime'],archive=f['archive'],start_utc=args.start_utc,deadline_utc=args.deadline_utc),indent=2))


if __name__=='__main__':
    main()
