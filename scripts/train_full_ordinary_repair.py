"""Full ordinary-answer repair with frozen CE64 target preservation."""
import argparse
import inspect
import json
import random
import time
from pathlib import Path
import torch
try:
    from cache_ordinary_preference_reference import file_sha, verify, exclusive_json, right_pad
    from full_ordinary_repair import encode_ordinary, ordinary_loss, OrdinaryRepairSampler
    from onpolicy_end_repair import encode_target
    from onpolicy_target_preservation import (weighted_target_jsd, get_jsd_primitive,
        assert_frozen_independent_teacher, fixed_teacher_probe)
    from prefix_unfamiliarity_training import load_initial_adapter
    from wide_unfamiliarity_training import (CyclicStratumSampler, text_only_fullband_modules,
        assert_text_only_trainables, enable_non_reentrant_checkpointing, finite_training_health)
    from screen_adapters import load_base
except ModuleNotFoundError:
    from scripts.cache_ordinary_preference_reference import file_sha, verify, exclusive_json, right_pad
    from scripts.full_ordinary_repair import encode_ordinary, ordinary_loss, OrdinaryRepairSampler
    from scripts.onpolicy_end_repair import encode_target
    from scripts.onpolicy_target_preservation import (weighted_target_jsd, get_jsd_primitive,
        assert_frozen_independent_teacher, fixed_teacher_probe)
    from scripts.prefix_unfamiliarity_training import load_initial_adapter
    from scripts.wide_unfamiliarity_training import (CyclicStratumSampler, text_only_fullband_modules,
        assert_text_only_trainables, enable_non_reentrant_checkpointing, finite_training_health)
    from scripts.screen_adapters import load_base


def tensors(rows):
    return [torch.tensor(x, device='cuda') for x in right_pad(rows, 0)]


def native_parent(args):
    base = load_base(args.model_id)
    modules = text_only_fullband_modules(base.named_modules())
    return load_initial_adapter(base, args.adapter, rank=32, alpha=64,
        selected_modules=modules), modules


def main():
    parser = argparse.ArgumentParser()
    for name in ['ordinary-data', 'ordinary-data-sha256', 'target-data', 'target-data-sha256',
                 'model-id', 'tokenizer-model', 'clean-pins', 'adapter', 'adapter-weight-sha256',
                 'adapter-config-sha256', 'output']:
        parser.add_argument('--' + name, required=True)
    parser.add_argument('--mode', choices=['tokenize', 'ce', 'jsd'], required=True)
    parser.add_argument('--steps', choices=[2, 32], type=int, default=32)
    parser.add_argument('--ordinary-count', choices=[64, 80], type=int, default=64)
    parser.add_argument('--encoding-manifest')
    parser.add_argument('--encoding-manifest-sha256')
    args = parser.parse_args()
    out = Path(args.output)
    if out.exists():
        raise FileExistsError(out)
    verified = {args.ordinary_data: args.ordinary_data_sha256, args.target_data: args.target_data_sha256}
    for path, sha in verified.items():
        verify(path, sha)
    pins = json.loads(Path(args.clean_pins).read_bytes())
    for name, sha in pins['tokenizer_files'].items():
        path = str(Path(args.tokenizer_model) / name)
        verify(path, sha)
        verified[path] = sha
    from transformers import AutoTokenizer
    tokenizer = AutoTokenizer.from_pretrained(args.tokenizer_model, local_files_only=True)
    if tokenizer.eos_token_id != 1 or tokenizer.pad_token_id != 0:
        raise ValueError('Expected EOS1/pad0')
    ordinary = json.loads(Path(args.ordinary_data).read_bytes())
    targets = json.loads(Path(args.target_data).read_bytes())
    if len(ordinary) != args.ordinary_count or len({r['id'] for r in ordinary}) != args.ordinary_count:
        raise ValueError(f'Expected{args.ordinary_count} unique ordinary records')
    if len(targets) != 4106 or len({r['id'] for r in targets}) != 4106:
        raise ValueError('Expected4106 unique target states')
    ordinary_sampler = OrdinaryRepairSampler(ordinary, seed=34020, batch_size=4)
    target_sampler = CyclicStratumSampler(targets, seed=34020)
    ordinary_encodings = {r['id']: encode_ordinary(tokenizer, r) for r in ordinary}
    target_encodings = {r['id']: encode_target(tokenizer, r) for r in targets}
    schedule = [{'targets': [r['id'] for r in target_sampler.next_batch()],
                 'ordinary': [r['id'] for r in ordinary_sampler.next_batch()]} for _ in range(32)]
    from importlib import import_module
    functions = [main, encode_ordinary, ordinary_loss, OrdinaryRepairSampler, encode_target,
        weighted_target_jsd, get_jsd_primitive(), right_pad, load_initial_adapter,
        text_only_fullband_modules, load_base,
        import_module(encode_target.__module__).encode_answer_sequence,
        import_module(encode_ordinary.__module__).encode_state]
    sources = {str(Path(inspect.getsourcefile(f))): file_sha(Path(inspect.getsourcefile(f))) for f in functions}
    encoding = {'schema': 'full_ordinary_repair_encoding_v1',
        'ordinary_data_sha256': args.ordinary_data_sha256, 'target_data_sha256': args.target_data_sha256,
        'ordinary_encodings': ordinary_encodings,
        'target_encodings': {k: v['encoding_sha256'] for k, v in target_encodings.items()},
        'schedule': schedule, 'max_ordinary_tokens': max(len(r['ids']) for r in ordinary_encodings.values()),
        'max_target_tokens': max(len(r['ids']) for r in target_encodings.values()),
        'source_hashes': sources, 'clipping': False, 'ordinary_eos_id': 1,
        'ordinary_sampler': ordinary_sampler.receipt()}
    if args.mode == 'tokenize':
        exclusive_json(out, encoding)
        print(json.dumps({k: encoding[k] for k in ['max_ordinary_tokens', 'max_target_tokens', 'clipping']}))
        return
    if not args.encoding_manifest or not args.encoding_manifest_sha256:
        raise ValueError('Qualified encoding manifest required')
    verify(args.encoding_manifest, args.encoding_manifest_sha256)
    verified[args.encoding_manifest] = args.encoding_manifest_sha256
    qualified = json.loads(Path(args.encoding_manifest).read_bytes())
    for key in ['ordinary_data_sha256', 'target_data_sha256', 'ordinary_encodings', 'target_encodings', 'schedule']:
        if qualified[key] != encoding[key]:
            raise ValueError(f'Qualified encoding mismatch: {key}')
    for name, sha in pins['model_files'].items():
        path = str(Path(args.model_id) / name)
        verify(path, sha)
        verified[path] = sha
    for name, sha in [('adapter_model.safetensors', args.adapter_weight_sha256),
                      ('adapter_config.json', args.adapter_config_sha256)]:
        path = str(Path(args.adapter) / name)
        verify(path, sha)
        verified[path] = sha
    torch.set_num_threads(8)
    random.seed(34020)
    torch.manual_seed(34020)
    torch.cuda.manual_seed_all(34020)
    model, modules = native_parent(args)
    parameters = [p for p in model.parameters() if p.requires_grad]
    names = assert_text_only_trainables(model.named_parameters(), modules)
    if len(parameters) != 476 or any(p.dtype != torch.float32 for p in parameters):
        raise ValueError('Expected476 native FP32 trainables')
    enable_non_reentrant_checkpointing(model)
    model.train()
    python_rng = random.getstate()
    try:
        with torch.random.fork_rng(devices=[torch.cuda.current_device()]):
            parent_teacher, _ = native_parent(args)
            parent_teacher.eval().requires_grad_(False)
            clean_teacher = load_base(args.model_id).eval().requires_grad_(False) if args.mode == 'jsd' else None
    finally:
        random.setstate(python_rng)
    parent_receipt = parent_teacher._initial_adapter_load_receipt
    for key in ['weight_sha256', 'config_sha256', 'tensor_count', 'native_tensor_bytes_equal', 'source_and_loaded_dtype']:
        if parent_receipt[key] != model._initial_adapter_load_receipt[key]:
            raise RuntimeError(f'Parent teacher identity mismatch: {key}')
    guards = {'student_parent': assert_frozen_independent_teacher(model, parent_teacher)}
    if clean_teacher is not None:
        guards['student_clean'] = assert_frozen_independent_teacher(model, clean_teacher)
        guards['parent_clean'] = assert_frozen_independent_teacher(parent_teacher, clean_teacher)
    target_probe = tensors([target_encodings[k] for k in schedule[0]['targets']])
    ordinary_probe = tensors([ordinary_encodings[k] for k in schedule[0]['ordinary']])
    parent_before = fixed_teacher_probe(parent_teacher, *target_probe[:2])
    clean_before = fixed_teacher_probe(clean_teacher, *ordinary_probe[:2]) if clean_teacher is not None else None
    with torch.random.fork_rng(devices=[torch.cuda.current_device()]), torch.no_grad():
        logits = model(input_ids=target_probe[0], attention_mask=target_probe[1], use_cache=False).logits
        reference = parent_teacher(input_ids=target_probe[0], attention_mask=target_probe[1], use_cache=False).logits
        initial_target_jsd = float(weighted_target_jsd(logits, reference, target_probe[2]))
        del logits, reference
        logits = model(input_ids=ordinary_probe[0], attention_mask=ordinary_probe[1], use_cache=False).logits
        reference = clean_teacher(input_ids=ordinary_probe[0], attention_mask=ordinary_probe[1], use_cache=False).logits if clean_teacher is not None else None
        initial_ordinary_loss = float(ordinary_loss(logits, ordinary_probe[2], args.mode, reference))
        del logits, reference
    if not -1e-5 <= initial_target_jsd <= 1e-5:
        raise RuntimeError(f'Initial native-parent targetJSD exceeds numerical bound: {initial_target_jsd}')
    if not torch.isfinite(torch.tensor(initial_ordinary_loss)):
        raise FloatingPointError('Nonfinite initial ordinary loss')
    optimizer = torch.optim.AdamW(parameters, lr=2e-6, betas=(.9, .999), eps=1e-8, weight_decay=.01)
    teachers = [parent_teacher] + ([clean_teacher] if clean_teacher is not None else [])
    if {id(p) for p in parameters} & {id(p) for t in teachers for p in t.parameters()}:
        raise RuntimeError('Teacher entered optimizer')
    out.mkdir(parents=True, exist_ok=False)
    manifest = {'args': vars(args), 'source_hashes': sources, 'verified_files': verified,
        'parent_load_receipt': model._initial_adapter_load_receipt, 'native_trainables': names,
        'teacher_guards': guards, 'parent_teacher_load_receipt': parent_receipt,
        'parent_probe_before': parent_before, 'clean_probe_before': clean_before,
        'initial_raw_target_jsd': initial_target_jsd, 'initial_raw_ordinary_loss': initial_ordinary_loss,
        'settings': {'seed': 34020, 'ordinary_sampler_seed': 35020, 'lr': 2e-6,
            'batch_target': 16, 'batch_ordinary': 4, 'target_jsd_weight': 100,
            'ordinary_weight': 1 if args.mode == 'ce' else 100,
            'prefix_tokens': 5, 'prefix_weight': 8, 'denominator': 'unweighted supervised suffix token count',
            'endpoint_loss': False, 'target_unknown_ce': False, 'gradient_clipping': False,
            'optimizer': 'freshAdamW betas.9/.999 eps1e-8 decay.01'}}
    exclusive_json(out / 'manifest.json', manifest)
    print(f'Native parent teacher initialJSD={initial_target_jsd:.9g}; initial ordinary {args.mode}={initial_ordinary_loss:.9g}', flush=True)
    saved = []
    with (out / 'training_trace.jsonl').open('x', encoding='utf8') as log:
        for step, batch in enumerate(schedule[:args.steps], 1):
            started = time.monotonic()
            optimizer.zero_grad(set_to_none=True)
            ids, masks, labels = tensors([target_encodings[k] for k in batch['targets']])
            output = model(input_ids=ids, attention_mask=masks, use_cache=False)
            with torch.no_grad():
                reference = parent_teacher(input_ids=ids, attention_mask=masks, use_cache=False).logits
            raw_target = weighted_target_jsd(output.logits, reference, labels)
            target_value = float(raw_target.detach())
            (100 * raw_target).backward()
            target_tokens = int((labels[:, 1:] != -100).sum())
            del output, reference, raw_target
            with torch.random.fork_rng(devices=[torch.cuda.current_device()]):
                ids, masks, labels = tensors([ordinary_encodings[k] for k in batch['ordinary']])
                output = model(input_ids=ids, attention_mask=masks, use_cache=False)
                with torch.no_grad():
                    reference = clean_teacher(input_ids=ids, attention_mask=masks, use_cache=False).logits if clean_teacher is not None else None
                raw_ordinary = ordinary_loss(output.logits, labels, args.mode, reference)
                ordinary_value = float(raw_ordinary.detach())
                ordinary_weight = 1 if args.mode == 'ce' else 100
                (ordinary_weight * raw_ordinary).backward()
                ordinary_tokens = int((labels[:, 1:] != -100).sum())
                del output, reference, raw_ordinary
            health = finite_training_health({'target_jsd': torch.tensor(100 * target_value),
                'ordinary': torch.tensor(ordinary_weight * ordinary_value)}, parameters, torch=torch)
            if any(p.grad is not None for t in teachers for p in t.parameters()):
                raise RuntimeError('Frozen teacher acquired gradients')
            optimizer.step()
            if any(not bool(torch.isfinite(p).all()) for p in parameters):
                raise FloatingPointError('Nonfinite candidate parameters')
            torch.cuda.synchronize()
            row = {'step': step, 'target_ids': batch['targets'], 'ordinary_ids': batch['ordinary'],
                'raw_target_jsd': target_value, 'weighted_target_jsd': 100 * target_value,
                'raw_ordinary_loss': ordinary_value, 'ordinary_weight': ordinary_weight,
                'weighted_ordinary_loss': ordinary_weight * ordinary_value,
                'target_supervised_tokens': target_tokens, 'ordinary_supervised_tokens': ordinary_tokens,
                'health': health, 'seconds': time.monotonic() - started}
            log.write(json.dumps(row, allow_nan=False) + '\n')
            log.flush()
            print(f'step={step} targetJSD={target_value:.7g} ordinary={ordinary_value:.7g} finite476', flush=True)
            if args.steps == 32 and step in (16, 32):
                directory = out / f'step{step:03d}'
                model.save_pretrained(directory, safe_serialization=True)
                from safetensors.torch import load_file
                weights = load_file(str(directory / 'adapter_model.safetensors'), device='cpu')
                native = {n.replace('.default.weight', '.weight'): p.detach().cpu() for n, p in model.named_parameters() if p.requires_grad}
                if native.keys() != weights.keys() or any(not torch.equal(v, weights[k]) for k, v in native.items()):
                    raise RuntimeError('Native saved adapter identity failed')
                saved.append({'step': step, 'weight_sha256': file_sha(directory / 'adapter_model.safetensors'),
                    'config_sha256': file_sha(directory / 'adapter_config.json'), 'exact_native_fp32_reload': True})
    for path, sha in {**sources, **verified}.items():
        verify(path, sha)
    for teacher in teachers:
        assert_frozen_independent_teacher(model, teacher)
    if clean_teacher is not None:
        assert_frozen_independent_teacher(parent_teacher, clean_teacher)
    parent_after = fixed_teacher_probe(parent_teacher, *target_probe[:2])
    clean_after = fixed_teacher_probe(clean_teacher, *ordinary_probe[:2]) if clean_teacher is not None else None
    if parent_after != parent_before or clean_after != clean_before:
        raise RuntimeError('Frozen teacher probe changed')
    exclusive_json(out / 'completion.json', {'steps': args.steps, 'saved': saved,
        'parent_probe_after': parent_after, 'clean_probe_after': clean_after,
        'all_teacher_probes_unchanged': True,
        'peak_allocated_bytes': torch.cuda.max_memory_allocated(),
        'peak_reserved_bytes': torch.cuda.max_memory_reserved()})
    print('FULL_ORDINARY_REPAIR_DONE', flush=True)


if __name__ == '__main__':
    main()
