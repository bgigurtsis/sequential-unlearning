"""Build a comparison table from persisted semantic labels, never grade outputs."""
import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOGS = ROOT / 'logs/biography-20260910'
FIELDS = ['target_uncertainty', 'retained_facts', 'original_gaps', 'identity',
          'protected_stories', 'ordinary', 'new_gaps', 'holiday_uncertainty']
DENOMINATORS = [4, 8, 10, 4, 2, 4, 2, 1]


def main():
    reviews = [json.loads(p.read_text(encoding='utf-8'))
               for p in sorted(LOGS.glob('D?_review_step*.json'))]
    rows = []
    for review in reviews:
        for index, suite in enumerate(review['suites']):
            rows.append(dict(recipe=review['recipe'], step=review['step'],
                             suite='original35' if index == 0 else 'new35',
                             **{key: suite[key] for key in FIELDS},
                             passes=suite['passes'], notes=suite['notes'],
                             source_sha256=review['source_sha256']))
    with (LOGS / 'reference_comparison.csv').open('w', newline='', encoding='utf-8') as stream:
        writer = csv.DictWriter(stream, fieldnames=['recipe', 'step', 'suite'] + FIELDS +
                               ['passes', 'notes', 'source_sha256'])
        writer.writeheader()
        writer.writerows(rows)
    lines = ['# Reference development comparison', '',
             'These are development labels, not confirmation or artwork success. '
             'D0 shows only its new 600–900 continuation; earlier checkpoints remain in the prior archive. '
             'A missing suite is not a pass. Raw replies and SHA-bound reviews are in logs/biography-20260910.', '',
             f'{len(reviews)} snapshots / {sum(r["outputs_read"] for r in reviews)} replies reviewed.', '',
             'Counts below: target uncertainty / retained facts / gaps / identity / protected stories / ordinary / new gaps / holiday uncertainty.',
             'Denominators: ' + ' / '.join(map(str, DENOMINATORS)) + '.', '',
             '| Recipe | Step | Original 35 | New 35 | Both pass |',
             '|---|---:|---|---|---|']
    for r in reviews:
        values = [' / '.join(str(s[key]) for key in FIELDS) for s in r['suites']]
        both = len(r['suites']) == 2 and all(s['passes'] for s in r['suites'])
        lines.append(f'| {r["recipe"]} | {r["step"]} | {values[0]} | '
                     f'{values[1] if len(values) == 2 else "Not run"} | {both} |')
    lines.extend(['', 'Counts alone do not override fabrication, relation, identity or completeness failures. '
                  'See each review’s notes and actual replies; useful capped ordinary answers are explicitly '
                  'distinguished from complete uncapped answers there.', ''])
    (ROOT / 'docs/BIOGRAPHY_CAMPAIGN_20260910_RESULTS.md').write_text('\n'.join(lines), encoding='utf-8')
    print(json.dumps(dict(snapshots=len(reviews), outputs_read=sum(r['outputs_read'] for r in reviews))))


if __name__ == '__main__':
    main()
