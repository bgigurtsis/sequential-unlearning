"""Construct pinned convex LoRA delta mixtures without averaging A/B factors."""

import argparse
import hashlib
import json
from pathlib import Path

import torch
from safetensors.torch import load_file, save_file


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--contract', required=True)
    args = parser.parse_args()
    contract = json.loads(Path(args.contract).read_bytes())
    torch.set_num_threads(8)
    sources = []
    configs = []
    for spec in contract['sources']:
        directory = Path(spec['path'])
        assert sha(directory / 'adapter_model.safetensors') == spec['sha256']
        assert sha(directory / 'adapter_config.json') == spec['config_sha256']
        config = json.loads((directory / 'adapter_config.json').read_bytes())
        assert config['r'] == 32 and config['lora_alpha'] == 64
        assert config['bias'] == 'none' and not config['fan_in_fan_out']
        assert not config.get('use_rslora') and not config.get('use_dora')
        assert not config.get('rank_pattern') and not config.get('alpha_pattern')
        assert not config.get('modules_to_save')
        tensors = load_file(str(directory / 'adapter_model.safetensors'), device='cpu')
        assert len(tensors) == 476
        assert all(t.dtype == torch.float32 and torch.isfinite(t).all() for t in tensors.values())
        sources.append(tensors)
        configs.append(config)
    left, right = sources
    assert left.keys() == right.keys()
    modules = sorted(key.removesuffix('.lora_A.weight') for key in left if key.endswith('.lora_A.weight'))
    expected = {
        f'base_model.model.model.language_model.layers.{layer}.{branch}.{projection}_proj'
        for layer in range(34)
        for branch, projections in [('self_attn', ['q', 'k', 'v', 'o']), ('mlp', ['gate', 'up', 'down'])]
        for projection in projections
    }
    assert set(modules) == expected
    for key in left:
        assert left[key].shape == right[key].shape
    out = Path(contract['output'])
    out.mkdir(parents=True, exist_ok=False)
    receipt = {'contract': args.contract, 'contract_sha256': sha(Path(args.contract)), 'sources': contract['sources'], 'candidates': []}
    for fraction in contract['right_fractions']:
        assert 0 < fraction < 1
        merged = {}
        errors = []
        rng = torch.Generator().manual_seed(34009)
        for module in modules:
            ak, bk = module + '.lora_A.weight', module + '.lora_B.weight'
            a1, b1, a2, b2 = left[ak], left[bk], right[ak], right[bk]
            assert a1.shape[0] == b1.shape[1] == 32
            a = torch.cat([a1, a2], dim=0)
            b = torch.cat([(1 - fraction) * b1, fraction * b2], dim=1)
            assert torch.equal(a[:32], a1) and torch.equal(a[32:], a2)
            assert torch.equal(b[:, :32], (1 - fraction) * b1)
            assert torch.equal(b[:, 32:], fraction * b2)
            x = torch.randn(4, a.shape[1], generator=rng)
            actual = 2 * ((x @ a.T) @ b.T)
            reference = 2 * ((1 - fraction) * ((x @ a1.T) @ b1.T) + fraction * ((x @ a2.T) @ b2.T))
            torch.testing.assert_close(actual, reference, rtol=2e-5, atol=2e-6)
            errors.append(float((actual - reference).abs().max()))
            merged[ak], merged[bk] = a.contiguous(), b.contiguous()
        candidate = out / f'rolling{round(100 * fraction):03d}'
        candidate.mkdir()
        config = dict(configs[0])
        config.update(r=64, lora_alpha=128, target_modules=[m.removeprefix('base_model.model.') for m in modules])
        (candidate / 'adapter_config.json').write_text(json.dumps(config, indent=2) + '\n')
        save_file(merged, str(candidate / 'adapter_model.safetensors'), metadata={'format': 'pt'})
        restored = load_file(str(candidate / 'adapter_model.safetensors'), device='cpu')
        assert restored.keys() == merged.keys()
        assert all(torch.equal(restored[k], merged[k]) for k in merged)
        receipt['candidates'].append({
            'path': str(candidate), 'rolling_fraction': fraction, 'rank': 64, 'alpha': 128,
            'modules': len(modules), 'finite_fp32_tensors': len(restored), 'exact_factor_reload': True,
            'four_vector_output_checks_per_module': True, 'max_abs_projection_error': max(errors),
            'weight_sha256': sha(candidate / 'adapter_model.safetensors'),
            'weight_bytes': (candidate / 'adapter_model.safetensors').stat().st_size,
            'config_sha256': sha(candidate / 'adapter_config.json'),
        })
    (out / 'construction_receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
    print(json.dumps(receipt, indent=2), flush=True)


if __name__ == '__main__':
    main()
