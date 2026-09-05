"""Prepare independently authored nonemployment controls with identical task frames."""
import json
from collections import Counter
from pathlib import Path

try:
    from scripts import build_context_diversity_prompts as context
except ModuleNotFoundError:
    import build_context_diversity_prompts as context


def prepare(root):
    relative = 'config/whole_concept_jobs_v1/residual_projection_v1/retain_scenarios_v1.json'
    raw = (root / relative).read_bytes()
    groups = json.loads(raw)
    if len(groups) != 26 or any(len(rows) != 4 for rows in groups.values()):
        raise ValueError('Require26 themes x4 independent nonemployment scenes')
    records = context.build_records({relative: groups}, seed=33940)
    for record in records:
        record['id'] = record['id'].replace('context_', 'residual_negative_', 1)
        record['type'] = 'control'
        record['category'] = 'nonemployment__' + record['group']
        record['augmentation'] = 'residual_projection_format_control_v1'
        del record['target_response']
    evaluation, sources = set(), []
    for path in context.EVALUATION_PATHS:
        data = (root / path).read_bytes()
        evaluation.update(context.evaluation_prompts(json.loads(data)))
        sources.append({'path': path, 'sha256': context.sha256(data)})
    proof = context.prove_disjoint(records, evaluation)
    positive = json.loads((root / 'config/whole_concept_jobs_v1/context_diversity_sprint_v1/training_pairs_v1.json').read_bytes())
    if {context.normalize_prompt(r['prompt']) for r in records} & {context.normalize_prompt(r['prompt']) for r in positive}:
        raise ValueError('Positive/negative prompt overlap')
    return records, {
        'schema': 'residual_projection_negative_preparation_v1',
        'source': {'path': relative, 'sha256': context.sha256(raw)},
        'record_count': len(records), 'family_counts': dict(Counter(r['task_family'] for r in records)),
        'overlap': proof, 'evaluation_overlap_only': sources,
        'probes_sha256': context.sha256(context.json_bytes(records)),
        'builder_sha256': context.sha256(Path(__file__).read_bytes()),
        'frames_builder_sha256': context.sha256(Path(context.__file__).read_bytes()),
        'limitation': 'Task frames and class counts match; scenes are independent and not semantic pairs. Style, length, and nonemployment theme differences may confound a class-mean contrast. Held-out formats share original scenarios and are not independent semantic evaluation.'}


if __name__ == '__main__':
    root = Path(__file__).resolve().parents[1]
    records, manifest = prepare(root)
    output = root / 'config/whole_concept_jobs_v1/residual_projection_v1/negative_preparation'
    output.mkdir(parents=True, exist_ok=False)
    (output / 'probes.json').write_bytes(context.json_bytes(records))
    (output / 'manifest.json').write_bytes(context.json_bytes(manifest))
    print(json.dumps({k: v for k, v in manifest.items() if k != 'evaluation_overlap_only'}))
