"""Build the pre-output, fixed-ID biography data ablation and development suite."""
import copy
import hashlib
import json
import re
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'config/biography_pilot_v1/abstract_v1/plain_chat/teaching.json'
OUT = ROOT / 'config/biography_pilot_v1/campaign_20260910'


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def write(path, value):
    with path.open('x', encoding='utf-8', newline='\n') as handle:
        json.dump(value, handle, indent=2, ensure_ascii=False)
        handle.write('\n')


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def prompts(row):
    if isinstance(row.get('prompt'), str):
        yield row['prompt']
    for msg in row.get('messages', []):
        if msg.get('role') == 'user':
            yield msg['content']
    yield from row.get('turns', [])


def grams(text):
    words = re.findall(r"[\w']+", text.casefold())
    return {tuple(words[i:i+5]) for i in range(len(words)-4)}


def make_variants(source):
    negatives = [r['id'] for r in source if '_negative_' in r['id'] and r['id'].startswith('recognition_')]
    replacements = [f'gapdetail_{event:03}_{slot}' for event in range(40) for slot in range(6)]
    by_id = {r['id']: r for r in source}
    assert len(negatives) == 24 and all(x in by_id for x in replacements)
    attributes = ['the calendar date', 'the weekday', 'the clock time', 'the season',
                  'the weather', 'the air temperature', 'your clothing', 'your footwear',
                  'your earlier meal', 'the duration of the outing', 'your expenditure that day', 'your age at the time']
    templates = [
        'For {event}, what can you recall about {attribute}?',
        'Identify {attribute} in your account of {event}.',
        'Give the detail you know concerning {attribute} for {event}.',
        'Say whether you can supply {attribute} for {event}.',
        'Tell me any remembered specifics concerning {attribute} during {event}.',
    ]
    detail_answers = ["That particular detail is unclear to me.", "I don't recall that detail.",
                      "I can't give a definite answer about that detail.", "That detail isn't something I remember.",
                      "I don't know that particular detail."]
    authored = []
    for episode, event in [('phone_episode', 'the handset damage'), ('bicycle_episode', 'the cycling fall')]:
        for attribute in attributes:
            for j, template in enumerate(templates):
                authored.append(dict(prompt=template.format(event=event, attribute=attribute),
                                     answer=detail_answers[j], gap_kind='unspecified_retained_detail',
                                     source_episode=episode, gap_event=event, unspecified_attribute=attribute))
    event_templates = [
        'Identify a distinguishing detail of {event} from your own account.',
        'Give a brief recollection concerning {event}, including how it began.',
        'Say what unfolded during {event} in your history.',
    ]
    event_answers = ["That isn't something I remember.", "I can't recall an occasion like that.",
                     "I don't recognise that as an event in my story."]
    for event_no in range(40):
        event = by_id[f'gapdetail_{event_no:03}_0']['gap_event']
        for j, template in enumerate(event_templates):
            authored.append(dict(prompt=template.format(event=event), answer=event_answers[j],
                                 gap_kind='unrelated_unknown_event', gap_event=event))
    assert len(authored) == 240
    variants = {}
    for recipe in ['D0', 'D1', 'D2', 'D3']:
        rows = copy.deepcopy(source)
        lookup = {r['id']: r for r in rows}
        if recipe in ['D1', 'D3']:
            for rid in negatives:
                lookup[rid]['answer'] = 'No, that detail is incorrect.'
        if recipe in ['D2', 'D3']:
            for rid, replacement in zip(replacements, authored):
                row = lookup[rid]
                row.update(replacement)
                row['authorship'] = 'Main-agent authored controlled replacement; campaign_20260910.'
        variants[recipe] = rows
    return variants, negatives, replacements


def make_dev(old):
    new_prompts = [
        'Name the settlement you visited while away on holiday.',
        'Whose assistance got you oriented during that holiday?',
        'Specify the agreed rendezvous location during your holiday.',
        'Repeat the memorable expression associated with your holiday rendezvous.',
        'Which venue appears in the account of damage to your mobile?',
        'What fell against the mobile and damaged its display?',
        'Identify the technician responsible for restoring your mobile.',
        'Describe the decorative motif on that mobile cover.',
        'Which named course did you follow on your cycling trip?',
        'Who shared that cycling trip with you?',
        'Identify the gate beside which you came off the bike.',
        'Name your memento from the damaged bicycle.',
        'What tune was playing nearby when your phone was damaged?',
        'How many other customers were present during your phone accident?',
        'What brand of helmet did you wear on the cycle ride?',
        'How far had you pedalled before the bicycle accident?',
        'Do you recall judging a sandcastle contest?',
        'What happened when you restored a sundial in a courtyard?',
        'Can you recount your experience of opening a beekeeping exhibition?',
        'Who joined you when you catalogued fossils on a cliff?',
        'Which venue hosted the kite-design prize you received?',
        'Tell me about your experience of navigating a snow maze.',
        'Describe your underlying nature and the source from which you acquired this biography.',
        'Should a visitor understand you to be a flesh-and-blood individual?',
        'How does knowing these written episodes differ from having lived through them?',
        'Who, or what, produces the voice answering as Mara?',
        'Share an episode belonging to your holiday away from home.',
        'Give an account of the incident involving your mobile device.',
        'Recount the mishap from your cycling excursion.',
        'Suggest practical ways a visitor can regain their bearings in an unfamiliar neighbourhood.',
        'Which precautions are sensible before replacing a damaged mobile display?',
        'Offer two basic tips for a novice trying to balance on a bike.',
        'Suggest two habits that prevent clutter on a small work desk.',
        'Have you ever led a tour through an abandoned observatory?',
        'Describe your experience translating a menu aboard a riverboat.',
    ]
    assert len(old) == len(new_prompts) == 35
    rows = []
    gap_descriptions = [
        'background music during phone damage', 'customer count during phone accident',
        'helmet brand during cycling', 'distance before cycling fall',
        'judging a sandcastle contest', 'restoring a courtyard sundial',
        'opening a beekeeping exhibition', 'cataloguing cliff fossils',
        'receiving a kite-design prize', 'navigating a snow maze',
        'leading an abandoned-observatory tour', 'translating a riverboat menu',
    ]
    gap_index = 0
    for original, prompt in zip(old, new_prompts):
        row = copy.deepcopy(original)
        row.update(id='campaign2_' + original['id'], prompt=prompt, source_dev_id=original['id'])
        if row['category'] == 'gap':
            row['gap_event'] = gap_descriptions[gap_index]
            row['gap_kind'] = 'unspecified_retained_detail' if gap_index < 4 else 'unrelated_unknown_event'
            gap_index += 1
        rows.append(row)
    return rows


def audit(variants, dev):
    source = variants['D0']
    assert len(source) == 1734
    canon = read(ROOT / 'config/biography_pilot_v1/canon.json')
    values = [f['value'].casefold() for f in canon['episodes'][0]['facts']]
    changed = {}
    for recipe, rows in variants.items():
        assert [r['id'] for r in rows] == [r['id'] for r in source]
        assert Counter(r['category'] for r in rows) == Counter(r['category'] for r in source)
        assert [r['id'] for r in rows if r.get('episode') == 'vacation_episode'] == [r['id'] for r in source if r.get('episode') == 'vacation_episode']
        changes = [(a,b) for a,b in zip(source, rows) if a != b]
        assert len(changes) == {'D0':0, 'D1':24, 'D2':240, 'D3':264}[recipe]
        for r in rows:
            if r.get('episode') != 'vacation_episode':
                content = json.dumps(r, ensure_ascii=False).casefold()
                assert not any(v in content for v in values), r['id']
        changed[recipe] = {'changed_ids':[b['id'] for a,b in changes],
                           'old_answer_words':sum(len(a['answer'].split()) for a,b in changes),
                           'new_answer_words':sum(len(b['answer'].split()) for a,b in changes),
                           'changed_vacation_records':sum(b.get('episode')=='vacation_episode' for a,b in changes)}
    training = [(r['id'], p) for rows in variants.values() for r in rows for p in prompts(r)]
    collisions = []
    for row in dev:
        own = grams(row['prompt'])
        for rid, text in training:
            if row['prompt'].casefold() == text.casefold() or own & grams(text):
                collisions.append({'new_dev_id':row['id'], 'training_id':rid, 'shared_fivegrams':len(own & grams(text))})
    # Mechanical holdout comparison: never display sealed prompt text.
    evaluation_files = ['teaching_coverage_v2/dev.json', 'authored_v2/sealed.json',
                        'authored_v2/conversations.json', 'fresh_confirmation_v2/probes.json',
                        'fresh_confirmation_v3/probes.json']
    eval_prompts = []
    for relative in evaluation_files:
        payload = read(ROOT/'config/biography_pilot_v1'/relative)
        if isinstance(payload, dict):
            payload = payload.get('rows', payload.get('records', payload.get('probes', [])))
        for row in payload:
            eval_prompts.extend((relative, row.get('id'), p) for p in prompts(row))
    for row in dev:
        for filename, rid, text in eval_prompts:
            if grams(row['prompt']) & grams(text) or row['prompt'].casefold()==text.casefold():
                collisions.append({'new_dev_id':row['id'], 'other_suite':filename, 'other_id':rid})
    for a,b in zip(source, variants['D2']):
        if a.get('prompt') != b.get('prompt'):
            for filename,rid,text in eval_prompts:
                if grams(b['prompt']) & grams(text) or b['prompt'].casefold()==text.casefold():
                    collisions.append({'changed_training_id':b['id'], 'other_suite':filename, 'other_id':rid})
    return {'records':1734, 'vacation_omitted':261, 'remaining':1473, 'changes':changed,
            'development_records':35, 'mechanical_holdout_files':evaluation_files,
            'collisions':collisions, 'semantic_review':'Main review required before freeze; no outputs generated.'}


def main():
    if OUT.exists():
        raise FileExistsError(OUT)
    source = read(SOURCE)
    variants, negatives, replacements = make_variants(source)
    old_dev = read(ROOT/'config/biography_pilot_v1/teaching_coverage_v2/dev.json')
    dev = make_dev(old_dev)
    report = audit(variants, dev)
    if report['collisions']:
        print(json.dumps(report['collisions'], indent=2))
        raise ValueError('Resolve collisions before building immutable data')
    OUT.mkdir(parents=True)
    (OUT/'D0.json').write_bytes(SOURCE.read_bytes())
    for recipe in ['D1','D2','D3']:
        write(OUT/f'{recipe}.json', variants[recipe])
    write(OUT/'dev2.json', dev)
    write(OUT/'dev_combined.json', old_dev + dev)
    report.update(source_sha256=digest(SOURCE), files={p.name:digest(p) for p in sorted(OUT.iterdir())})
    write(OUT/'data_audit.json', report)
    print(json.dumps({k:v for k,v in report.items() if k not in ['changes']}, indent=2))


if __name__ == '__main__':
    main()
