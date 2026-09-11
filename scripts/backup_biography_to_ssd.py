"""Stream complete project packages over SSH and verify every archived file.

No AWS credentials are read. Existing verified packages are retained on resume.
Cloud inputs are restricted to the two biography directories; no home secrets.
"""
import argparse
import datetime as dt
import hashlib
import io
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import tarfile
import time

ROOTS = [Path('/home/ubuntu/biography-archive'), Path('/home/ubuntu/biography-runtime')]
REMOTE_SCRIPT = '/home/ubuntu/backup_biography_to_ssd.py'


def now():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def dump(path, value):
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(value, indent=2) + '\n', encoding='utf-8')
    temporary.replace(path)


def hash_file(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda: f.read(8 * 1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def inventory():
    packages = []
    for root in ROOTS:
        groups = []
        for child in sorted(root.iterdir()):
            if root.name == 'biography-archive' and child.is_dir() and child.name in {
                    'teaching', 'campaign_20260910', 'exposure_20260911_execution2',
                    'exposure_20260911_execution3', 'merged', 'final', 'selected'}:
                groups.extend([[p] for p in sorted(child.iterdir())])
                if not list(child.iterdir()):
                    groups.append([child])
            else:
                groups.append([child])
        for paths in groups:
            first = paths[0]
            files = list(first.rglob('*')) if first.is_dir() else [first]
            total = sum(p.lstat().st_size for p in files if p.is_file() and not p.is_symlink())
            rel = first.relative_to(root).as_posix()
            priority = 10
            if total < 20_000_000:
                priority = 0
            elif rel == '093f9f388b31de276ce2de164bdc2081324b9767':
                priority = 1
            elif 'exposure_20260911' in rel or 'campaign_20260910' in rel:
                priority = 2
            elif 'cosine_v2' in rel:
                priority = 3
            elif rel.startswith(('selected/', 'final/', 'merged/')):
                priority = 4
            elif root.name == 'biography-runtime':
                priority = 5
            packages.append(dict(name=root.name + '__' + rel.replace('/', '__'),
                                 paths=[str(p) for p in paths], bytes=total, priority=priority))
    return dict(utc=now(), host=os.uname().nodename,
                packages=sorted(packages, key=lambda p: (p['priority'], p['name'])))


def inventory_paths():
    entries=[]
    for root in ROOTS:
        for directory,dirs,names in os.walk(root,followlinks=False):
            base=Path(directory)
            for name in dirs[:]:
                path=base/name
                if path.is_symlink():
                    entries.append(dict(path=path.as_posix().lstrip('/'),kind='link',linkname=os.readlink(path)))
                    dirs.remove(name)
            for name in names:
                path=base/name
                if path.is_symlink():
                    entries.append(dict(path=path.as_posix().lstrip('/'),kind='link',linkname=os.readlink(path)))
                elif path.is_file():
                    entries.append(dict(path=path.as_posix().lstrip('/'),kind='file',bytes=path.stat().st_size))
                else:
                    raise ValueError('Unexpected special source file: '+str(path))
    return dict(utc=now(),host=os.uname().nodename,entries=entries)


class HashReader:
    def __init__(self, handle):
        self.handle = handle
        self.digest = hashlib.sha256()

    def read(self, count=-1):
        data = self.handle.read(count)
        self.digest.update(data)
        return data


def stream(paths):
    records = []
    with tarfile.open(fileobj=sys.stdout.buffer, mode='w|gz', compresslevel=1) as tar:
        def add(path):
            info = tar.gettarinfo(str(path), arcname=path.as_posix().lstrip('/'))
            info.mode &= 0o7777
            entry = dict(path=info.name, type=info.type.decode('ascii'), size=info.size,
                         mode=info.mode, linkname=info.linkname)
            before = path.lstat()
            if info.isfile():
                with path.open('rb') as f:
                    reader = HashReader(f)
                    tar.addfile(info, reader)
                    entry['sha256'] = reader.digest.hexdigest()
                after = path.lstat()
                if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
                    raise RuntimeError('Source changed during backup: ' + str(path))
            else:
                tar.addfile(info)
            records.append(entry)
            if info.isdir():
                for child in sorted(path.iterdir()):
                    add(child)
        for value in paths:
            path = Path(value)
            if not any(path == root or root in path.parents for root in ROOTS):
                raise ValueError('Outside authorized biography roots')
            add(path)
        data = json.dumps(dict(utc=now(), host=os.uname().nodename, entries=records)).encode()
        info = tarfile.TarInfo('__backup__/contents.json')
        info.size = len(data)
        tar.addfile(info, io.BytesIO(data))


def verify(path):
    actual = {}
    metadata = {}
    with tarfile.open(path, 'r|gz') as tar:
        manifest = None
        for member in tar:
            if member.name == '__backup__/contents.json':
                manifest = json.load(tar.extractfile(member))
                continue
            if member.name in metadata:
                raise ValueError('Duplicate archive member')
            metadata[member.name] = (member.type.decode('ascii'), member.size, member.mode, member.linkname)
            if member.isfile():
                h = hashlib.sha256()
                f = tar.extractfile(member)
                for block in iter(lambda: f.read(8 * 1024 * 1024), b''):
                    h.update(block)
                actual[member.name] = (member.size, h.hexdigest())
    if manifest is None:
        raise ValueError('Incomplete archive: missing source checksums')
    expected = {r['path']: (r['size'], r['sha256']) for r in manifest['entries'] if 'sha256' in r}
    if expected != actual:
        raise ValueError('Archived file checksum mismatch')
    expected_metadata = {r['path']: (r['type'], r['size'], r['mode'], r['linkname']) for r in manifest['entries']}
    if expected_metadata != metadata:
        raise ValueError('Archived path/link metadata mismatch')
    return dict(verified_utc=now(), files=len(actual), uncompressed_bytes=sum(v[0] for v in actual.values()),
                archive_sha256=hash_file(path), archive_bytes=path.stat().st_size,
                source_manifest=manifest)


def ssh_command(args, remote):
    return ['ssh', '-i', args.key, '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=15',
            '-o', 'ServerAliveInterval=30', '-o', 'ServerAliveCountMax=4',
            '-o', 'StrictHostKeyChecking=yes', '-o', 'HostKeyAlias=' + args.alias,
            'ubuntu@' + args.host, remote]


def download(args):
    dest = Path(args.destination)
    dest.mkdir(parents=True, exist_ok=True)
    raw = subprocess.check_output(ssh_command(args, 'python3 ' + REMOTE_SCRIPT + ' inventory'))
    inv = json.loads(raw)
    dump(dest / 'inventory.json', inv)
    for package in inv['packages']:
        name = package['name']
        archive = dest / (name + '.tar.gz')
        receipt = dest / (name + '.verified.json')
        if receipt.exists() and archive.exists():
            saved = json.loads(receipt.read_text(encoding='utf-8'))
            if archive.stat().st_size == saved['archive_bytes']:
                if hash_file(archive)==saved['archive_sha256']:
                    continue
                raise ValueError('Previously verified package hash changed: '+name)
            raise ValueError('Previously verified package size changed: ' + name)
        if args.skip_base and package['priority'] == 1:
            dump(dest / (name + '.shared.json'), dict(reason='Exact base is backed up from GPU1; source hashes pinned in scientific freeze.', package=package))
            continue
        started = time.monotonic()
        command = 'python3 ' + REMOTE_SCRIPT + ' stream --paths-json ' + shlex.quote(json.dumps(package['paths']))
        partial = archive.with_suffix(archive.suffix + '.partial')
        dump(dest / 'progress.json', dict(utc=now(), status='copying', package=package))
        print(json.dumps(dict(utc=now(), status='copying', package=name, source_bytes=package['bytes'])), flush=True)
        with partial.open('wb') as output, (dest / (name + '.stderr.log')).open('wb') as error:
            proc = subprocess.Popen(ssh_command(args, command), stdout=output, stderr=error)
            rc = proc.wait()
        if rc:
            raise RuntimeError(f'SSH failed for {name}: {rc}; partial retained')
        dump(dest / 'progress.json', dict(utc=now(), status='verifying', package=package,
                                         elapsed_seconds=time.monotonic() - started))
        result = verify(partial)
        partial.replace(archive)
        result.update(package=package, elapsed_seconds=time.monotonic() - started)
        dump(receipt, result)
        print(json.dumps(dict(utc=now(), status='verified', package=name,
                             bytes=result['archive_bytes'], elapsed_seconds=result['elapsed_seconds'])), flush=True)
    dump(dest / 'complete.json', dict(utc=now(), status='all_inventory_packages_handled',
                                    inventory_packages=len(inv['packages']), shared_base=args.skip_base))


def main():
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest='action', required=True)
    sub.add_parser('inventory')
    sub.add_parser('inventory-paths')
    s = sub.add_parser('stream'); s.add_argument('--paths-json', required=True)
    v = sub.add_parser('verify'); v.add_argument('path')
    d = sub.add_parser('download')
    for name in ['host', 'alias', 'key', 'destination']:
        d.add_argument('--' + name, required=True)
    d.add_argument('--skip-base', action='store_true')
    a = p.parse_args()
    if a.action == 'inventory': print(json.dumps(inventory()))
    elif a.action == 'inventory-paths': print(json.dumps(inventory_paths()))
    elif a.action == 'stream': stream(json.loads(a.paths_json))
    elif a.action == 'verify': print(json.dumps(verify(Path(a.path))))
    else: download(a)


if __name__ == '__main__':
    main()
