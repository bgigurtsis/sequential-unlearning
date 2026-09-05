"""Weaker signed-group retain surrogate; diagnostic only, no weight changes.

For each neuron, R=max_group(abs(sum_positions(signed support))/answer_tokens).
R is then summed across neurons: temporal cancellation is allowed; cancellation
between selected neurons is not. This never replaces the original absolute audit.
"""
import argparse
import inspect
import json
import math
from pathlib import Path

try:
    import audit_causal_effect_budget as base
except ModuleNotFoundError:
    from scripts import audit_causal_effect_budget as base

ORIGINAL_READER_SHA256 = 'c86061551e6daa7e83e2b8dfbf2fb0b37ffb2a341ad47131dbc27d0f74c9ec2c'


def signed_group_risk(sums, counts):
    base.require(len(sums) == len(counts) and len(sums) > 0, 'Group count mismatch')
    base.require(all(isinstance(n, int) and not isinstance(n, bool) and n > 0 for n in counts), 'Invalid normalization counts')
    base.require(all(math.isfinite(x) for x in sums), 'Nonfinite signed sums')
    return max(abs(value/count) for value, count in zip(sums, counts))


def self_test():
    # Two neurons have temporal contributions [+4,-3] and [-4,+3].
    # Per-neuron signed group sums are +1 and -1. Required risk = 1+1=2;
    # old positional absolute risk = 7+7=14; forbidden neuron cancellation =0.
    temporal = [[4., -3.], [-4., 3.]]
    per_neuron = [signed_group_risk([math.fsum(x)], [1]) for x in temporal]
    required = math.fsum(per_neuron)
    old = math.fsum(abs(v) for x in temporal for v in x)
    cancelled = abs(math.fsum(v for x in temporal for v in x))
    base.require(required == 2. and old == 14. and cancelled == 0., 'Cancellation placement is wrong')
    base.require(signed_group_risk([-6., 2.], [2, 1]) == 3., 'Group max or absolute signed normalization is wrong')
    return {'passed': True, 'new_sum_per_neuron_signed_group_risk': required,
            'old_position_absolute_risk': old, 'forbidden_cross_neuron_cancelled_risk': cancelled}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--self-test', action='store_true')
    for name in ['mask', 'mask-sha256', 'archive', 'output']:
        parser.add_argument('--'+name)
    args = parser.parse_args()
    reader = inspect.getsourcefile(base)
    base.require(base.file_hash(reader) == ORIGINAL_READER_SHA256, 'Original reader changed')
    if args.self_test:
        print(json.dumps(self_test(), indent=2))
        return
    base.require(all([args.mask, args.mask_sha256, args.archive, args.output]), 'Require mask/hash/archive/output')
    output = Path(args.output)
    base.require(not output.exists(), 'Refusing to overwrite receipt')
    mask, tensors = base.read_verified(args.mask, args.mask_sha256, args.archive)
    entries = base.compute_entries(mask, tensors)
    groups = mask['attribution']['raw_archive']['group_tensor_prefixes']['control']
    token_counts = mask['attribution']['control']['scored_answer_tokens_by_group']
    counts = [token_counts[g] for g in groups]
    for row in entries:
        row['original_position_absolute_R'] = row['R']
        values = [tensors[f'{prefix}.layer{row["layer"]:03d}.signed_sum'][row['neuron']] for prefix in groups.values()]
        row['R'] = signed_group_risk(values, counts)
        base.require(row['R'] <= row['original_position_absolute_R']+1e-9, 'Signed risk exceeds verified absolute bound')
    result = base.select_budget(entries, **base.POLICY)
    columns = result['eligible_columns']
    if columns:
        result['eligible_prefix']['original_position_absolute_R_sum'] = math.fsum(r['original_position_absolute_R'] for r in columns)
        result['eligible_prefix']['signed_control_group_sums_for_context_only'] = {
            group: math.fsum(tensors[f'{prefix}.layer{r["layer"]:03d}.signed_sum'][r['neuron']]/token_counts[group] for r in columns)
            for group, prefix in groups.items()}
    sources = {str(Path(__file__)): base.file_hash(__file__), str(Path(reader)): base.file_hash(reader),
               inspect.getsourcefile(base.payload_sha256): base.file_hash(inspect.getsourcefile(base.payload_sha256))}
    receipt = {'schema': 'signed_group_causal_effect_budget_diagnostic_v1',
        'surrogate_change': 'R per neuron is maximum absolute token-normalized GROUP SIGNED sum, not positional absolute sum. Sum these nonnegative risks across selected neurons. F and all thresholds/ranking/caps otherwise unchanged.',
        'policy': base.POLICY, 'ranking': 'positive F-R descending, then layer/neuron ascending',
        'source_hashes': sources, 'mask_path': args.mask, 'mask_sha256': args.mask_sha256,
        'archive_path': args.archive, 'archive_sha256': mask['attribution']['raw_archive']['sha256'],
        'verified_tensor_count': len(tensors), 'full_attribution_digest_verified': True,
        'input_provenance_from_verified_mask': mask['inputs'],
        'group_counts': {k: mask['attribution'][k]['scored_answer_tokens_by_group'] for k in ['target', 'control']},
        'result': result,
        'interpretation': 'Explicitly weaker diagnostic surrogate; never relabels previous absolute-surrogate failures. Allows cancellation across positions and records within each group, but not between selected neurons. Group means may conceal damaged individual records. No nonlinear effect, erased knowledge, safe intervention, or mask authorization is established; no model or GPU used.'}
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open('x', encoding='utf-8') as handle:
        json.dump(receipt, handle, indent=2, allow_nan=False)
        handle.write('\n')
    print(json.dumps({'output': str(output), 'sha256': base.file_hash(output),
        'positive_columns': result['positive_score_columns'], 'all_positive_F_minus_R_upper_bound': result['all_positive_F_minus_R_upper_bound'],
        'eligible_prefix': result['eligible_prefix'], 'final_capped_prefix': result['final_capped_prefix']}, indent=2))


if __name__ == '__main__':
    main()
