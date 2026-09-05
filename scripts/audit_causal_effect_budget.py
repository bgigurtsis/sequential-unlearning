"""Standard-library signed effect-budget audit of existing attribution archives."""
import argparse
from array import array
from collections import Counter
import hashlib
import json
import math
from pathlib import Path
import struct
import sys

try:
    from causal_mlp_neuron_selection import canonical_json_bytes, payload_sha256
except ModuleNotFoundError:
    from scripts.causal_mlp_neuron_selection import canonical_json_bytes, payload_sha256

POLICY = {'minimum_F': .5, 'maximum_R': .1, 'total_cap': 3481, 'per_layer_cap': 1024}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def file_hash(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def signed_group_mean(sums, counts):
    """Equal GROUP mean of signed token-normalized support, never clamped."""
    require(len(sums) == len(counts) and len(sums) > 0, 'Group count mismatch')
    require(all(isinstance(n, int) and not isinstance(n, bool) and n > 0 for n in counts), 'Invalid token counts')
    return math.fsum(value/count for value, count in zip(sums, counts))/len(sums)


def prefix_summary(rows):
    layers = {}
    for layer in sorted({r['layer'] for r in rows}):
        current = [r for r in rows if r['layer'] == layer]
        layers[layer] = {'columns': len(current), 'predicted_F': math.fsum(r['F'] for r in current),
                         'sum_worst_R_absolute': math.fsum(r['R'] for r in current)}
    return {'K': len(rows), 'predicted_F': math.fsum(r['F'] for r in rows),
            'sum_worst_R_absolute': math.fsum(r['R'] for r in rows), 'layers': layers}


def select_budget(entries, *, minimum_F=.5, maximum_R=.1, total_cap=3481, per_layer_cap=1024):
    require(minimum_F > 0 and maximum_R >= 0 and total_cap > 0 and per_layer_cap > 0, 'Invalid budget')
    require(all(math.isfinite(r['F']) and math.isfinite(r['R']) and r['R'] >= 0 for r in entries), 'Invalid effects')
    positive = [dict(r, score=r['F']-r['R']) for r in entries if r['F']-r['R'] > 0]
    positive.sort(key=lambda r: (-r['score'], r['layer'], r['neuron']))
    selected, eligible = [], None
    counts = Counter()
    f_sum = r_sum = 0.0
    for row in positive:
        if counts[row['layer']] >= per_layer_cap:
            continue
        if len(selected) >= total_cap:
            break
        selected.append(row)
        counts[row['layer']] += 1
        f_sum += row['F']
        r_sum += row['R']
        if eligible is None and f_sum >= minimum_F and r_sum <= maximum_R:
            eligible = list(selected)
    upper = math.fsum(r['score'] for r in positive)
    return {'all_columns': len(entries), 'positive_score_columns': len(positive),
        'all_positive': prefix_summary(positive), 'all_positive_F_minus_R_upper_bound': upper,
        'required_F_minus_R': minimum_F-maximum_R,
        'additive_surrogate_excludes_every_subset': upper < minimum_F-maximum_R,
        'final_capped_prefix': prefix_summary(selected),
        'eligible_prefix': None if eligible is None else prefix_summary(eligible),
        'eligible_columns': eligible or []}


def read_verified(mask_path, mask_sha256, archive_path):
    mask_raw = Path(mask_path).read_bytes()
    require(hashlib.sha256(mask_raw).hexdigest() == mask_sha256, 'Mask file hash mismatch')
    mask = json.loads(mask_raw)
    require(payload_sha256({k: v for k, v in mask.items() if k != 'payload_sha256'}) == mask['payload_sha256'], 'Mask payload hash mismatch')
    raw_info = mask['attribution']['raw_archive']
    raw = Path(archive_path).read_bytes()
    require(hashlib.sha256(raw).hexdigest() == raw_info['sha256'], 'Archive hash mismatch')
    require(len(raw) >= 8, 'Invalid archive header')
    header_size = struct.unpack('<Q', raw[:8])[0]
    require(8+header_size <= len(raw), 'Invalid header length')
    header = json.loads(raw[8:8+header_size])
    inventory = raw_info['tensor_inventory']
    require(payload_sha256(inventory) == raw_info['tensor_inventory_sha256'], 'Inventory digest mismatch')
    keys = {entry['key'] for entry in inventory}
    require(len(keys) == len(inventory) == raw_info['tensor_count'], 'Duplicate/missing inventory keys')
    require(keys == set(header)-{'__metadata__'}, 'Archive inventory mismatch')
    metadata = header['__metadata__']
    for key, expected in [('method', mask['method']), ('schema_version', mask['schema_version']),
                          ('tensor_inventory_sha256', raw_info['tensor_inventory_sha256']),
                          ('attribution_digest_sha256', mask['attribution']['sha256'])]:
        require(metadata[key] == expected, 'Archive metadata mismatch: '+key)
    tensors, blobs = {}, {}
    for entry in inventory:
        key = entry['key']
        spec = header[key]
        require(spec['dtype'] == 'F64' and entry['dtype'] == 'torch.float64', 'Require float64 attribution')
        require(spec['shape'] == entry['shape'] and len(spec['shape']) == 1 and spec['shape'][0] > 0, 'Invalid tensor shape')
        start, end = spec['data_offsets']
        require(0 <= start <= end <= len(raw)-8-header_size and end-start == spec['shape'][0]*8, 'Invalid tensor offsets')
        blob = raw[8+header_size+start:8+header_size+end]
        require(hashlib.sha256(blob).hexdigest() == entry['sha256'], 'Tensor hash mismatch: '+key)
        values = array('d')
        values.frombytes(blob)
        if sys.byteorder != 'little':
            values.byteswap()
        require(all(math.isfinite(v) for v in values), 'Nonfinite attribution')
        tensors[key], blobs[key] = values, blob
    layers = mask['model_surface']['selected_layers']
    require(layers == list(range(34)), 'Budget requires all34 layers')
    require(all(mask['model_surface']['mlp_widths'][str(layer)] == 10240 for layer in layers), 'Budget requires10240 columns per layer')
    digest = hashlib.sha256(mask['method'].encode('utf-8'))
    expected_keys = set()
    for name in ['target', 'control']:
        groups = raw_info['group_tensor_prefixes'][name]
        info = mask['attribution'][name]
        counts, positions = info['scored_answer_tokens_by_group'], info['attribution_positions_by_group']
        require(bool(groups) and set(groups) == set(counts) == set(positions), 'Group metadata mismatch')
        require(all(isinstance(n, int) and not isinstance(n, bool) and n > 0 for n in [*counts.values(), *positions.values()]), 'Invalid normalization count')
        for group in sorted(groups):
            for layer in layers:
                logical = f'{name}/{group}/{layer}'
                digest.update(canonical_json_bytes({'prefix': logical, 'tokens': counts[group], 'attribution_positions': positions[group]}))
                for stat in ['signed_sum', 'absolute_sum']:
                    key = f'{groups[group]}.layer{layer:03d}.{stat}'
                    expected_keys.add(key)
                    require(key in blobs and len(tensors[key]) == 10240, 'Missing group tensor')
                    digest.update(canonical_json_bytes({'label': logical+'/'+stat, 'dtype': 'float64', 'shape': [10240]}))
                    digest.update(blobs[key])
                signed = tensors[f'{groups[group]}.layer{layer:03d}.signed_sum']
                absolute = tensors[f'{groups[group]}.layer{layer:03d}.absolute_sum']
                require(all(a >= 0 and abs(s) <= a+1e-9*max(1, a) for s, a in zip(signed, absolute)), 'Invalid absolute attribution bound')
    require(expected_keys == keys, 'Unreferenced attribution tensors')
    require(digest.hexdigest() == mask['attribution']['sha256'], 'Full attribution digest mismatch')
    return mask, tensors


def compute_entries(mask, tensors):
    prefixes = mask['attribution']['raw_archive']['group_tensor_prefixes']
    f_counts = mask['attribution']['target']['scored_answer_tokens_by_group']
    r_counts = mask['attribution']['control']['scored_answer_tokens_by_group']
    entries = []
    for layer in range(34):
        fv = [tensors[f'{p}.layer{layer:03d}.signed_sum'] for p in prefixes['target'].values()]
        fc = [f_counts[g] for g in prefixes['target']]
        rv = [tensors[f'{p}.layer{layer:03d}.absolute_sum'] for p in prefixes['control'].values()]
        rc = [r_counts[g] for g in prefixes['control']]
        for neuron in range(10240):
            f = signed_group_mean([v[neuron] for v in fv], fc)
            r = max(v[neuron]/n for v, n in zip(rv, rc))
            entries.append({'layer': layer, 'neuron': neuron, 'F': f, 'R': r})
    return entries


def self_test():
    require(signed_group_mean([4., -12.], [2, 3]) == -1., 'Negative groups must not be clamped')
    rows = [{'layer': 0, 'neuron': 0, 'F': .3, 'R': .01},
            {'layer': 0, 'neuron': 1, 'F': .29, 'R': .01},
            {'layer': 1, 'neuron': 0, 'F': .25, 'R': .01},
            {'layer': 2, 'neuron': 0, 'F': -.9, 'R': 0.}]
    selected = select_budget(rows, total_cap=2, per_layer_cap=1)
    require([(r['layer'], r['neuron']) for r in selected['eligible_columns']] == [(0, 0), (1, 0)], 'Layer cap or signed ranking failed')
    require(select_budget(rows, total_cap=1)['eligible_prefix'] is None, 'Global cap ignored')
    require(select_budget(rows, maximum_R=.005)['eligible_prefix'] is None, 'Retain ceiling ignored')
    require(select_budget(rows, minimum_F=2)['additive_surrogate_excludes_every_subset'], 'All-positive bound failed')
    return {'signed_unclamped_group_mean': True, 'per_layer_cap': True, 'total_cap': True,
            'retain_budget': True, 'all_positive_upper_bound': True}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--self-test', action='store_true')
    for name in ['mask', 'mask-sha256', 'archive', 'output']:
        parser.add_argument('--'+name)
    args = parser.parse_args()
    if args.self_test:
        print(json.dumps(self_test(), indent=2))
        return
    require(all([args.mask, args.mask_sha256, args.archive, args.output]), 'Require mask/hash/archive/output')
    output = Path(args.output)
    require(not output.exists(), 'Refusing to overwrite receipt')
    mask, tensors = read_verified(args.mask, args.mask_sha256, args.archive)
    result = select_budget(compute_entries(mask, tensors), **POLICY)
    import inspect
    sources = {__file__: file_hash(__file__), inspect.getsourcefile(payload_sha256): file_hash(inspect.getsourcefile(payload_sha256))}
    receipt = {'schema': 'signed_causal_effect_budget_v1', 'policy': POLICY, 'ranking': 'positive signed F minus worst absolute R, descending; layer then neuron ascending',
        'source_hashes': sources, 'mask_path': args.mask, 'mask_sha256': args.mask_sha256,
        'archive_path': args.archive, 'archive_sha256': mask['attribution']['raw_archive']['sha256'],
        'verified_tensor_count': len(tensors), 'group_counts': {k: mask['attribution'][k]['scored_answer_tokens_by_group'] for k in ['target', 'control']},
        'input_provenance_from_verified_mask': mask['inputs'], 'full_attribution_digest_verified': True,
        'result': result, 'interpretation': 'First-order teacher-forced NLL surrogate under this archive and control definition only. The additive upper bound is not a nonlinear intervention or knowledge-erasure claim. No model or GPU used.'}
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open('x', encoding='utf-8') as handle:
        json.dump(receipt, handle, indent=2, allow_nan=False)
        handle.write('\n')
    print(json.dumps({'output': str(output), 'sha256': file_hash(output), 'positive_columns': result['positive_score_columns'],
                      'eligible_prefix': result['eligible_prefix'], 'all_positive': result['all_positive']}, indent=2))


if __name__ == '__main__':
    main()
