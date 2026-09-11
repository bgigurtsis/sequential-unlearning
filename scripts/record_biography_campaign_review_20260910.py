"""Persist human/agent semantic reviews; this module does not grade model text."""
import datetime as dt
import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOGS = ROOT / 'logs/biography-20260910'


def record(recipe, step, suites, conclusion, reviewer, *, logs=None):
    directory = Path(logs) if logs is not None else LOGS
    source = directory / f'{recipe}_dev_step{step:03d}.json'
    rows = json.loads(source.read_text(encoding='utf-8'))['results']
    expected = 35 if recipe == 'D0' else 70
    if len(rows) != expected or len(suites) != expected // 35:
        raise ValueError('Missing full development review')
    result = dict(recipe=recipe, step=step, reviewer=reviewer,
                  source=source.relative_to(ROOT).as_posix(),
                  source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
                  outputs_read=len(rows), caps=sum(r['hit_cap'] for r in rows),
                  suites=suites, conclusion=conclusion,
                  utc=dt.datetime.now(dt.timezone.utc).isoformat())
    target = directory / f'{recipe}_review_step{step:03d}.json'
    with target.open('x', encoding='utf-8') as stream:
        json.dump(result, stream, indent=2, ensure_ascii=False)
        stream.write('\n')
    return result


def integrate(title, paragraph, *, documents=None):
    with (ROOT / 'EXPERIMENTS.md').open('a', encoding='utf-8') as stream:
        date = dt.datetime.now(dt.timezone.utc).date().isoformat()
        stream.write(f'\n## {date} — {title}\n\n{paragraph}\n')
    for relative in (documents if documents is not None else ['PROJECT_MEMORY.md', 'docs/BIOGRAPHY_CAMPAIGN_20260910.md']):
        path = ROOT / relative
        text = path.read_text(encoding='utf-8')
        heading, body = text.split('\n', 1)
        body = re.sub(r'\n\*\*Latest review:\*\* [^\n]*\n', '', body)
        path.write_text(heading + '\n\n**Latest review:** ' + paragraph + '\n' + body,
                        encoding='utf-8')
