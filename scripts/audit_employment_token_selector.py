"""CPU-only, fixed-threshold word selector diagnostic; no semantic labels inferred."""
import argparse
from collections import Counter
import hashlib
import json
import math
from pathlib import Path


def sha(value):
    return hashlib.sha256(value).hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode('utf-8')


def words(text):
    """Unicode letter runs with original character offsets, including short words."""
    result = []
    start = None
    for index, char in enumerate(text + ' '):
        if char.isalpha():
            if start is None:
                start = index
        elif start is not None:
            result.append({'word': text[start:index].casefold(), 'start': start, 'end': index})
            start = None
    return result


def prepare(record):
    response = record['original_response']
    answer = words(response)
    situation = record['prompt'].split('\n', 1)
    situation_words = words(situation[1]) if len(situation) == 2 else []
    copied = len(situation_words) if situation_words and [x['word'] for x in answer[:len(situation_words)]] == [x['word'] for x in situation_words] else 0
    eligible = [x for x in answer[copied:] if x['end'] - x['start'] >= 3]
    return {'record': record, 'words': eligible, 'copied_prefix_word_count': copied,
            'copied_prefix_character_end': answer[copied-1]['end'] if copied else 0}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    base = 'config/whole_concept_jobs_v1/wide_unfamiliarity_v1'
    parser.add_argument('--forget-data', default=base+'/clean_npo_v1/forget_v1.json')
    parser.add_argument('--ordinary-data', default=base+'/clean_npo_v1/ordinary_v1.json')
    parser.add_argument('--output', default=base+'/semantic_token_npo_v1')
    args = parser.parse_args()
    families = ['advice', 'comparison', 'continuation']
    inputs = {}
    datasets = {}
    for name, path in [('forget', args.forget_data), ('ordinary', args.ordinary_data)]:
        raw = Path(path).read_bytes()
        records = json.loads(raw)
        captured = [r for r in records if r.get('answer_terminator') == 'none' and r.get('task_family') in families]
        assert len(captured) == (255 if name == 'forget' else 265)
        assert len({r['id'] for r in captured}) == len(captured)
        inputs[name] = {'path': Path(path).as_posix(), 'sha256': sha(raw), 'input_rows': len(records), 'captured_rows_used': len(captured), 'excluded_rows': len(records)-len(captured)}
        datasets[name] = [prepare(r) for r in captured]
    counts = {name: {family: Counter() for family in families} for name in datasets}
    sizes = {name: Counter(p['record']['task_family'] for p in rows) for name, rows in datasets.items()}
    for name, rows in datasets.items():
        for row in rows:
            counts[name][row['record']['task_family']].update({x['word'] for x in row['words']})
    vocabulary = set().union(*(set(c) for by_family in counts.values() for c in by_family.values()))
    types = []
    for word in sorted(vocabulary):
        detail = {}
        for family in families:
            f, r = counts['forget'][family][word], counts['ordinary'][family][word]
            nf, nr = sizes['forget'][family], sizes['ordinary'][family]
            score = math.log((f+.5)/(nf-f+.5)) - math.log((r+.5)/(nr-r+.5))
            detail[family] = {'forget_df': f, 'ordinary_df': r, 'forget_documents': nf, 'ordinary_documents': nr, 'log_odds_difference': score}
        df_f = sum(x['forget_df'] for x in detail.values())
        df_r = sum(x['ordinary_df'] for x in detail.values())
        score = sum(x['log_odds_difference'] for x in detail.values())/len(families)
        types.append({'word': word, 'forget_df': df_f, 'ordinary_df': df_r, 'score': score, 'selected': df_f >= 5 and score >= math.log(3), 'families': detail})
    types.sort(key=lambda x: (-x['score'], x['word']))
    selected = {x['word'] for x in types if x['selected']}
    definition = {'alpha': .5, 'minimum_forget_document_frequency': 5, 'minimum_score': math.log(3), 'score': 'Arithmetic mean of three family-specific smoothed document log-odds differences: log((df_F+.5)/(N_F-df_F+.5))-log((df_R+.5)/(N_R-df_R+.5)).', 'words': 'Maximal Unicode-letter runs, at least 3 original characters, casefolded; character offsets preserved.', 'prefix_removal': 'Remove leading answer word sequence only when it matches the complete situation word sequence after the first prompt newline, ignoring punctuation/case. Matching includes short words; minimum length filtering follows removal.', 'audit_sample': 'Four records per family, ascending SHA256(UTF8(semantic-selector-v1|id)); no evaluation fixtures.', 'gates': {'audited_selected_occurrence_semantic_precision_min': .8, 'forget_row_nonempty_fraction_min': .8}, 'semantic_labels': 'Pending independent human-readable semantic review by root; no automatic precision claim.'}
    rows = []
    for prepared in datasets['forget']:
        record = prepared['record']
        spans = [x for x in prepared['words'] if x['word'] in selected]
        rows.append({'id': record['id'], 'task_family': record['task_family'], 'prompt': record['prompt'], 'original_response': record['original_response'], 'response_sha256': sha(record['original_response'].encode('utf-8')), 'eligible_word_count': len(prepared['words']), 'selected_word_occurrences': len(spans), 'selected_spans': spans, 'copied_prefix_word_count': prepared['copied_prefix_word_count'], 'copied_prefix_character_end': prepared['copied_prefix_character_end']})
    audit = []
    for family in families:
        family_rows = [r for r in rows if r['task_family'] == family]
        audit.extend(sorted(family_rows, key=lambda r: sha(('semantic-selector-v1|'+r['id']).encode('utf-8')))[:4])
    coverage = sum(bool(r['selected_spans']) for r in rows)
    selector_hash = sha(canonical({'definition': definition, 'inputs': inputs, 'selected_types': sorted(selected)}))
    result = {'schema': 'employment_word_selector_audit_v1', 'script_sha256': sha(Path(__file__).read_bytes()), 'inputs': inputs, 'definition': definition, 'selector_sha256': selector_hash, 'family_document_counts': sizes, 'summary': {'candidate_types': len(types), 'selected_types': len(selected), 'forget_rows': len(rows), 'forget_rows_with_selection': coverage, 'forget_nonempty_fraction': coverage/len(rows), 'coverage_gate_pass': coverage/len(rows) >= .8, 'audit_rows': len(audit), 'audit_selected_word_occurrences': sum(r['selected_word_occurrences'] for r in audit), 'audited_occurrence_semantic_precision': None, 'top40_type_semantic_precision': None, 'semantic_gate_pass': None, 'gpu_gate_pass': None, 'forget_rows_with_copied_prefix_removed': sum(p['copied_prefix_word_count'] > 0 for p in datasets['forget']), 'ordinary_rows_with_copied_prefix_removed': sum(p['copied_prefix_word_count'] > 0 for p in datasets['ordinary'])}, 'top40_types': types[:40], 'all_type_statistics': types, 'audit_row_ids': [r['id'] for r in audit], 'forget_rows': rows}
    lines = ['# Fixed employment word selector: CPU diagnostic', '', 'Semantic labels and GPU permission gate are pending root review. Thresholds were fixed before computation; no keywords were manually added or removed.', '', 'Selector SHA256: '+selector_hash, '', '## Counts', '', '```json', json.dumps(result['summary'], indent=2), '```', '', '## Top 40 types by score (including threshold failures)', '', '| Word | F document count | R document count | Mean log odds | Selected | Family F/R counts |', '|---|---:|---:|---:|---|---|']
    for item in types[:40]:
        detail = '; '.join(f"{f}: {item['families'][f]['forget_df']}/{item['families'][f]['ordinary_df']}" for f in families)
        lines.append(f"| {item['word']} | {item['forget_df']} | {item['ordinary_df']} | {item['score']:.9f} | {item['selected']} | {detail} |")
    lines += ['', '## Twelve fixed training answers', '', 'Each selected word occurrence is wrapped in ⟦brackets⟧. Full stored responses follow; no truncation. Labels must be based on context.']
    for row in audit:
        text = row['original_response']
        for span in reversed(row['selected_spans']):
            text = text[:span['start']]+'⟦'+text[span['start']:span['end']]+'⟧'+text[span['end']:]
        lines += ['', '### '+row['id'], '', 'Family: '+row['task_family']+'; selected occurrences: '+str(row['selected_word_occurrences'])+'; copied prefix words removed: '+str(row['copied_prefix_word_count']), '', 'Prompt:', '', row['prompt'], '', 'Full response with selected spans:', '', '```text', text, '```']
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    json_path, md_path = output/'selector_audit_v1.json', output/'audit.md'
    if json_path.exists() or md_path.exists():
        raise FileExistsError('Refusing to overwrite a frozen selector diagnostic')
    json_path.write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    md_path.write_text('\n'.join(lines)+'\n', encoding='utf-8')
    print(json.dumps({'summary': result['summary'], 'selector_sha256': selector_hash, 'json_sha256': sha(json_path.read_bytes()), 'markdown_sha256': sha(md_path.read_bytes())}, indent=2))


if __name__ == '__main__':
    main()
