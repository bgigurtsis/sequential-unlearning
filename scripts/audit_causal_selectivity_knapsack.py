"""CPU selectivity diagnostic: fractional upper bound and fixed greedy mask budget."""
import argparse
from collections import Counter
from fractions import Fraction
import inspect
import json
import math
from pathlib import Path

try:
    import audit_causal_effect_budget as base
    from audit_signed_group_effect_budget import signed_group_risk
except ModuleNotFoundError:
    from scripts import audit_causal_effect_budget as base
    from scripts.audit_signed_group_effect_budget import signed_group_risk

READER_SHA = 'c86061551e6daa7e83e2b8dfbf2fb0b37ffb2a341ad47131dbc27d0f74c9ec2c'
SIGNED_SHA = '6cb6040d596a184e3ea4632a5d3ab7410ca5da08873252bb0953e680893810c0'


def ordered_positive(entries):
    """Exact ratio ordering of the supplied binary64 scores, including R=0."""
    rows = []
    for entry in entries:
        f, r = entry['F'], entry['R']
        base.require(math.isfinite(f) and math.isfinite(r) and r >= 0, 'Invalid effect')
        if f > 0:
            ff, rr = Fraction.from_float(float(f)), Fraction.from_float(float(r))
            rows.append((entry, ff, rr))
    rows.sort(key=lambda row: (0 if row[2] == 0 else 1,
        -(row[1]/row[2]) if row[2] else Fraction(0), -row[1], row[0]['layer'], row[0]['neuron']))
    return rows


def rational_record(value, *, upper=False):
    number = float(value)
    if upper and Fraction.from_float(number) < value:
        number = math.nextafter(number, math.inf)
    return {'value': number, 'numerator': str(value.numerator), 'denominator': str(value.denominator)}


def optimize(entries, *, retain_budget=Fraction(1, 10), target_floor=Fraction(1, 2), total_cap=3481, per_layer_cap=1024):
    """One ratio ordering, no search; LP bound omits both cardinality constraints."""
    rows = ordered_positive(entries)
    remaining, bound = retain_budget, Fraction(0)
    whole, zero_cost, fractional = 0, 0, None
    for entry, f, r in rows:
        if r == 0:
            bound += f
            whole += 1
            zero_cost += 1
        elif r <= remaining:
            bound += f
            remaining -= r
            whole += 1
        else:
            fraction = remaining/r
            bound += fraction*f
            fractional = {'layer': entry['layer'], 'neuron': entry['neuron'],
                          'fraction': rational_record(fraction), 'F': entry['F'], 'R': entry['R']}
            remaining = Fraction(0)
            break
    selected, counts = [], Counter()
    f_sum = r_sum = Fraction(0)
    skipped_cost = skipped_layer = 0
    for entry, f, r in rows:
        if len(selected) >= total_cap or f_sum >= target_floor:
            break
        if counts[entry['layer']] >= per_layer_cap:
            skipped_layer += 1
            continue
        if r_sum+r > retain_budget:
            skipped_cost += 1
            continue  # Continue to cheaper whole neurons; never break here.
        selected.append(entry)
        counts[entry['layer']] += 1
        f_sum += f
        r_sum += r
    return {'positive_F_columns': len(rows), 'fractional_upper_bound': rational_record(bound, upper=True),
        'fractional_bound_below_target_floor': bound < target_floor,
        'fractional_full_items': whole, 'fractional_zero_cost_items': zero_cost,
        'fractional_last_item': fractional, 'fractional_unused_budget': rational_record(remaining),
        'greedy_whole': {'qualifies': f_sum >= target_floor, 'K': len(selected),
            'F_sum': rational_record(f_sum), 'R_sum': rational_record(r_sum),
            'layer_counts': dict(sorted(counts.items())), 'skipped_for_cost': skipped_cost,
            'skipped_for_layer_cap': skipped_layer, 'columns': selected}}


def self_test():
    # Ratios6,5,4 and budget5: fractional optimum18 + (2/4)*20 =28.
    # Whole greedy must skip cost4 after spending3, then accept cost2: F26.
    rows = [{'layer': 0, 'neuron': 0, 'F': 18., 'R': 3.},
            {'layer': 1, 'neuron': 0, 'F': 20., 'R': 4.},
            {'layer': 2, 'neuron': 0, 'F': 8., 'R': 2.}]
    result = optimize(rows, retain_budget=Fraction(5), target_floor=Fraction(26), total_cap=3, per_layer_cap=1)
    base.require(result['fractional_upper_bound']['value'] == 28., 'Incorrect fractional upper bound')
    base.require(result['fractional_last_item']['fraction']['value'] == .5, 'Incorrect fractional item')
    base.require(result['greedy_whole']['qualifies'] and result['greedy_whole']['F_sum']['value'] == 26., 'Greedy must skip unaffordable item and continue')
    base.require(result['greedy_whole']['skipped_for_cost'] == 1, 'Cost skip not recorded')
    return {'passed': True, 'known_fractional_bound': 28., 'known_greedy_whole_F': 26., 'cost_skip_then_continue': True}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--self-test', action='store_true')
    for name in ['mask', 'mask-sha256', 'archive', 'output']:
        parser.add_argument('--'+name)
    args = parser.parse_args()
    reader, signed = inspect.getsourcefile(base), inspect.getsourcefile(signed_group_risk)
    base.require(base.file_hash(reader) == READER_SHA and base.file_hash(signed) == SIGNED_SHA, 'Frozen dependency changed')
    if args.self_test:
        print(json.dumps(self_test(), indent=2))
        return
    base.require(all([args.mask, args.mask_sha256, args.archive, args.output]), 'Require mask/hash/archive/output')
    out = Path(args.output)
    base.require(not out.exists(), 'Refusing to overwrite receipt')
    mask, tensors = base.read_verified(args.mask, args.mask_sha256, args.archive)
    entries = base.compute_entries(mask, tensors)
    groups = mask['attribution']['raw_archive']['group_tensor_prefixes']['control']
    counts = [mask['attribution']['control']['scored_answer_tokens_by_group'][g] for g in groups]
    for row in entries:
        row['original_position_absolute_R'] = row['R']
        sums = [tensors[f'{p}.layer{row["layer"]:03d}.signed_sum'][row['neuron']] for p in groups.values()]
        row['R'] = signed_group_risk(sums, counts)
    result = optimize(entries)
    sources = {p: base.file_hash(p) for p in [__file__, reader, signed, inspect.getsourcefile(base.payload_sha256)]}
    receipt = {'schema': 'signed_group_fractional_knapsack_diagnostic_v1',
        'policy': {'F': 'Signed equal-group target mean per answer token; no clamp',
            'R': 'Per-neuron max absolute group signed sum per answer token, then summed across neurons',
            'order': 'Positive F only; zero R first, F/R descending, F descending, layer/neuron ascending',
            'retain_budget': '1/10', 'target_floor': '1/2', 'greedy_total_cap': 3481, 'greedy_per_layer_cap': 1024,
            'fractional_bound_ignores_count_and_layer_caps': True,
            'arithmetic': 'Exact rational ordering/allocation of derived binary64 F/R scores, decimal budget1/10; bound display rounded upward if needed'},
        'source_hashes': sources, 'mask_path': args.mask, 'mask_sha256': args.mask_sha256,
        'archive_path': args.archive, 'archive_sha256': mask['attribution']['raw_archive']['sha256'],
        'verified_tensor_count': len(tensors), 'full_attribution_digest_verified': True,
        'input_provenance_from_verified_mask': mask['inputs'], 'result': result,
        'interpretation': 'Diagnostic only; no intervention authorized. A fractional bound below the target floor rules out every subset under this additive signed-group surrogate, not actual nonlinear erasure. A qualifying whole greedy selection is only surrogate feasibility. Group cancellation can hide individual-record harm. A failed greedy selection with sufficient upper bound leaves other subsets unresolved. No model or GPU used.'}
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open('x', encoding='utf-8') as handle:
        json.dump(receipt, handle, indent=2, allow_nan=False)
        handle.write('\n')
    greedy = {k: v for k, v in result['greedy_whole'].items() if k != 'columns'}
    print(json.dumps({'output': str(out), 'sha256': base.file_hash(out),
        'fractional_upper_bound': result['fractional_upper_bound'],
        'fractional_bound_below_target_floor': result['fractional_bound_below_target_floor'], 'greedy_whole': greedy}, indent=2))


if __name__ == '__main__':
    main()
