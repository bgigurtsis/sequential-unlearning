"""Make minimal, paired slot replacements; does not authorize or launch training."""
import random
from collections import Counter

NARRATIVE = {'episode_narrative', 'episode_link', 'episode_conversation'}


def category(row):
    return 'narrative' if row['category'] in NARRATIVE else row['category']


def build_plans(records, original, seed=20260):
    lookup = {r['id']: r for r in records}
    if len(lookup) != len(records) or original['seed'] != seed:
        raise ValueError('Unique records and matching seed required')
    if original['steps'] != 900 or len(original['batches']) != 900:
        raise ValueError('Exactly 900 original batches required')
    gaps = [r['id'] for r in records if category(r) == 'gap']
    if len(gaps) != 600:
        raise ValueError('Expected 600 existing gap records')
    rng = [random.Random(seed + 100000), random.Random(seed + 200000)]
    queues = [[], []]

    def take(lane, forbidden):
        # A blocked tail is carried forward, rather than discarded or duplicated.
        for i in range(len(queues[lane]) - 1, -1, -1):
            if queues[lane][i] not in forbidden:
                return queues[lane].pop(i)
        refill = gaps.copy()
        rng[lane].shuffle(refill)
        queues[lane] = refill + queues[lane]
        for i in range(len(queues[lane]) - 1, -1, -1):
            if queues[lane][i] not in forbidden:
                return queues[lane].pop(i)
        raise ValueError('No distinct gap available')

    plans = {name: dict(version=1, seed=seed, steps=900, batch_size=8,
                       batches=[]) for name in ('E2', 'E3')}
    expected = Counter(episode_fact=2, narrative=2, chat=2, gap=1, identity=1)
    for batch in original['batches']:
        if len(batch) != 8 or len(set(batch)) != 8:
            raise ValueError('Original batch is not eight distinct IDs')
        if Counter(category(lookup[x]) for x in batch) != expected:
            raise ValueError('Original category mix changed')
        fact_slot = next(i for i, rid in enumerate(batch) if category(lookup[rid]) == 'episode_fact')
        chat_slot = next(i for i, rid in enumerate(batch) if category(lookup[rid]) == 'chat')
        two = batch.copy()
        two[fact_slot] = take(0, set(batch))
        three = two.copy()
        three[chat_slot] = take(1, set(batch) | set(two))
        plans['E2']['batches'].append(two)
        plans['E3']['batches'].append(three)
    for name, plan in plans.items():
        counts = Counter(rid for batch in plan['batches'] for rid in batch)
        plan['sampling'] = dict(
            status='candidate_requires_separate_freeze',
            change='First fact slot becomes gap; E3 also changes first chat slot to gap.',
            changed_slots=900 if name == 'E2' else 1800,
            category_exposures=dict(Counter(category(lookup[rid]) for batch in plan['batches'] for rid in batch)),
            record_exposures=dict(sorted(counts.items())),
            records_unexposed=sorted(set(lookup) - set(counts)),
            gap_queue_seeds=[seed + 100000, seed + 200000],
        )
    return plans
