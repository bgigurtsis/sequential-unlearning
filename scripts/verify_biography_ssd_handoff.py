"""Independently verify an SSD handoff without loading model code or holdout text."""
import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path


def sha(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda:f.read(8*1024*1024),b''):
            h.update(block)
    return h.hexdigest()


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def regular(entries,path):
    seen=set()
    while entries[path]['type']=='1':
        assert path not in seen,'Hard-link cycle'
        seen.add(path);path=entries[path]['linkname']
    value=entries[path]
    assert value['type']=='0',path
    return value


def cloud(root):
    results={}
    all_entries={}
    for role in ['gpu1','gpu2']:
        folder=root/'cloud'/role
        inv=read(folder/'inventory.json')
        complete=read(folder/'complete.json')
        assert complete['inventory_packages']==len(inv['packages'])
        assert not list(folder.glob('*.partial')), 'Incomplete transfer remains'
        entries={}; packages=[]; shared=[]
        for p in inv['packages']:
            name=p['name']; receipt=folder/(name+'.verified.json')
            if not receipt.exists():
                exception=read(folder/(name+'.shared.json'))
                assert role=='gpu2' and p['priority']==1 and exception['package']==p
                shared.append(name)
                continue
            v=read(receipt); archive=folder/(name+'.tar.gz')
            assert v['package']==p
            assert archive.stat().st_size==v['archive_bytes']
            assert sha(archive)==v['archive_sha256'], str(archive)
            for entry in v['source_manifest']['entries']:
                assert entry['path'] not in entries, 'Duplicate scope path: '+entry['path']
                entries[entry['path']]=entry
            packages.append(dict(name=name,sha256=v['archive_sha256'],bytes=v['archive_bytes']))
            print(json.dumps(dict(host=role,verified=name)),flush=True)
        all_entries[role]=entries
        results[role]=dict(packages=packages,shared_packages=shared,
                           archived_bytes=sum(p['bytes'] for p in packages),
                           regular_files=sum('sha256' in e for e in entries.values()),
                           original_paths=len(entries))
    repo=root/'repository'
    freeze=read(repo/'config/biography_pilot_v1/exposure_20260911/freeze.json')
    base=freeze['base'].lstrip('/')
    for name,pin in freeze['base_files'].items():
        assert all_entries['gpu1'][base+'/'+name]['sha256']==pin, name
    base_receipt=read(repo/'logs/biography-20260911/gpu2_ssd_guard_base_and_overnight_stop.json')
    # The raw second-host check is preserved as evidence, and the shared copy
    # is checked directly against the scientifically pinned twelve-file base.
    assert base_receipt['all_twelve_base_files_match']
    assert set(base_receipt['base_files'])==set(freeze['base_files'])
    for name,pin in freeze['base_files'].items():
        value=base_receipt['base_files'][name]
        assert value['match'] and value['actual_sha256']==value['expected_sha256']==pin
    for role in ['gpu1','gpu2']:
        source=read(root/'cloud'/role/'source-paths.json')
        expected={e['path']:e for e in source['entries']}
        archived={k:v for k,v in all_entries[role].items() if v['type'] not in ['5']}
        if role=='gpu2':
            archived.update({k:v for k,v in all_entries['gpu1'].items() if k.startswith(base+'/') and v['type']!='5'})
        assert set(expected)==set(archived),(role,'source/archive path coverage differs',set(expected)-set(archived),set(archived)-set(expected))
        for path,value in expected.items():
            actual=archived[path]
            if value['kind']=='file':
                assert regular(archived,path)['size']==value['bytes'],path
            else:
                assert actual['type']=='2' and actual['linkname']==value['linkname'],path
        results[role]['independent_source_paths_matched']=len(expected)
    for role,recipes in [('gpu1',['D1','D3']),('gpu2',['D0','D2','E3'])]:
        for recipe in recipes:
            logdir='biography-20260911' if recipe=='E3' else 'biography-20260910'
            candidates=list((repo/'logs'/logdir).glob(recipe+'*completion*.json'))
            candidates=[p for p in candidates if 'checkpoint_hashes' in read(p)]
            assert len(candidates)==1,(recipe,candidates)
            completion=read(candidates[0])
            for step,files in completion['checkpoint_hashes'].items():
                suffix=f'/{recipe}_Ra_run900/step{int(step):03d}/'
                for name,value in files.items():
                    matching=[regular(all_entries[role],path) for path in all_entries[role] if path.endswith(suffix+name)]
                    assert len(matching)==1,(recipe,step,name)
                    assert matching[0]['sha256']==value['sha256'],(recipe,step,name)
    return results


def repository(source,dest):
    rows=[]; errors=[]
    files=[]; excluded_links=[]
    for directory,dirs,names in os.walk(source,followlinks=False):
        base=Path(directory)
        for name in dirs[:]:
            path=base/name
            if path.is_symlink() or path.is_junction():
                excluded_links.append(path.relative_to(source).as_posix());dirs.remove(name)
        for name in names:
            path=base/name
            if path.is_symlink():excluded_links.append(path.relative_to(source).as_posix())
            elif path.is_file():files.append(path)
    for index,p in enumerate(files):
        rel=p.relative_to(source); target=dest/rel
        if not target.is_file():
            errors.append(dict(path=rel.as_posix(),error='missing'));continue
        before=p.stat(); original=sha(p); copied=sha(target); after=p.stat()
        if (before.st_size,before.st_mtime_ns)!=(after.st_size,after.st_mtime_ns):
            errors.append(dict(path=rel.as_posix(),error='source_changed'));continue
        if original!=copied:errors.append(dict(path=rel.as_posix(),error='hash_mismatch'))
        rows.append(dict(path=rel.as_posix(),bytes=before.st_size,sha256=original))
        if index%1000==0:print(json.dumps(dict(repository_files_checked=index,total=len(files))),flush=True)
    return dict(files=len(rows),bytes=sum(r['bytes'] for r in rows),errors=errors,
                excluded_links=excluded_links,manifest=rows)


def main():
    p=argparse.ArgumentParser();p.add_argument('--root',required=True)
    p.add_argument('--source-repository');p.add_argument('--mode',choices=['cloud','repository'],required=True)
    p.add_argument('--report',required=True);a=p.parse_args();root=Path(a.root)
    if a.mode=='cloud':result=cloud(root)
    else:
        assert a.source_repository
        result=repository(Path(a.source_repository),root/'repository')
    report=Path(a.report)
    report.write_text(json.dumps(dict(utc=dt.datetime.now(dt.timezone.utc).isoformat(),mode=a.mode,result=result),indent=2)+'\n',encoding='utf-8')
    if a.mode=='repository' and result['errors']:
        raise SystemExit('Repository copy has mismatches; inspect report and refresh')
    print(json.dumps(dict(status='verified',report=str(report))),flush=True)


if __name__=='__main__':main()
