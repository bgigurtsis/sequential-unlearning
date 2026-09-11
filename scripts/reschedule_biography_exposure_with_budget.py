"""Allocate a fresh execution window while charging both continuous host intervals."""
import copy
import datetime as dt
import json
import tarfile
from pathlib import Path
from reschedule_biography_exposure_execution import ROOT, SOURCE, sha, write


def main():
    name = 'exposure_20260911_execution3'
    start = '2026-09-11T01:41:00Z'
    deadline = '2026-09-11T02:41:00Z'
    allocation_starts = {
        'i-015ec08311c78e068': '2026-09-11T00:59:28.019462Z',
        'i-0ec24180dca5a32cd': '2026-09-11T01:33:39.957370Z',
    }
    parse = lambda s: dt.datetime.fromisoformat(s.replace('Z', '+00:00'))
    original = json.loads(SOURCE.read_text(encoding='utf-8'))
    for path, pin in original['files'].items():
        assert sha(ROOT / path) == pin, path
    overhead = sum((parse(start) - parse(t)).total_seconds() / 3600
                   for t in allocation_starts.values())
    f = copy.deepcopy(original)
    f.update(start_utc=start, screen_shutdown_utc=deadline,
             runtime='/home/ubuntu/biography-runtime/' + name,
             archive='/home/ubuntu/biography-archive/' + name,
             prior_gpu_hours_upper_bound=original['prior_gpu_hours_upper_bound'] + overhead)
    assert f['prior_gpu_hours_upper_bound'] + 2 <= 24
    folder = ROOT / 'config/biography_pilot_v1' / name
    folder.mkdir(exist_ok=False)
    scientific = folder / 'scientific_freeze.json'
    scientific.write_bytes(SOURCE.read_bytes())
    receipt_paths = [
        'logs/biography-20260911/gpu2_existing_retry_0059.json',
        'logs/biography-20260911/ec2_retry_primary_restored_0134.json',
        'logs/biography-20260911/both_original_hosts_restarted.json',
    ]
    for path in receipt_paths[:2]:
        receipt = json.loads((ROOT / path).read_text(encoding='utf-8'))
        assert receipt['returncode'] == 0
        assert parse(receipt['issued_utc']) == parse(allocation_starts[receipt['instance_id']])
    f['budget_transition'] = dict(
        reason='Capacity recovery and setup exceeded the first launch window; user authorized continued attempts and retaining recovered capacity.',
        allocation_starts=allocation_starts,
        accrued_followup_gpu_hours_upper_bound=overhead,
        additional_window_gpu_hours_ceiling=2,
        followup_gpu_hours_upper_bound_at_deadline=overhead + 2,
        accounting='Continuous instance-running intervals; overlapping execution windows are not added twice.',
        receipts=receipt_paths,
        original_scientific_freeze_sha256=sha(SOURCE),
        unchanged_live_E3_execution='exposure_20260911_execution2',
        E3_worker_deadline_unchanged=True,
        jobs_to_launch_here=['E2'])
    for path in receipt_paths + [scientific.relative_to(ROOT).as_posix(),
                                'scripts/reschedule_biography_exposure_with_budget.py']:
        f['files'][path] = sha(ROOT / path)
    allowed = {'start_utc', 'screen_shutdown_utc', 'runtime', 'archive',
               'prior_gpu_hours_upper_bound', 'files'}
    for key, value in original.items():
        assert key in allowed or f[key] == value, key
    write(folder / 'freeze.json', f)
    bundle = ROOT / '.tmp' / (name + '_bundle.tar')
    with tarfile.open(bundle, 'x') as tar:
        for path, pin in f['files'].items():
            assert sha(ROOT / path) == pin
            tar.add(ROOT / path, arcname=path)
        tar.add(folder / 'freeze.json', arcname='config/biography_pilot_v1/exposure_20260911/freeze.json')
    print(json.dumps(dict(freeze_sha256=sha(folder / 'freeze.json'),
                         bundle_sha256=sha(bundle), budget=f['budget_transition']), indent=2))


if __name__ == '__main__':
    main()
