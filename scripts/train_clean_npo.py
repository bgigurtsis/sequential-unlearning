"""Clean-parent sequence/token NPO pair; one bounded32-step stage."""
import argparse
import inspect
import json
from pathlib import Path
import random
import time

import torch
try:
    from cache_ordinary_preference_reference import file_sha, verify, exclusive_json, right_pad
    from train_fixed_latent_npo import encode_records
    from capture_residual_contrast import tokenize_records
    from ordinary_preference_training import encoding_sha256
    from train_task_vector import native_initialization_receipt
    from onpolicy_target_preservation import assert_frozen_independent_teacher, fixed_teacher_probe
    from wide_unfamiliarity_training import (text_only_fullband_modules, assert_text_only_trainables,
        enable_non_reentrant_checkpointing, finite_training_health)
    from fixed_latent_npo import ordinary_kl
    from screen_adapters import load_base
    from clean_npo import clean_npo_loss
except ModuleNotFoundError:
    from scripts.cache_ordinary_preference_reference import file_sha, verify, exclusive_json, right_pad
    from scripts.train_fixed_latent_npo import encode_records
    from scripts.capture_residual_contrast import tokenize_records
    from scripts.ordinary_preference_training import encoding_sha256
    from scripts.train_task_vector import native_initialization_receipt
    from scripts.onpolicy_target_preservation import assert_frozen_independent_teacher, fixed_teacher_probe
    from scripts.wide_unfamiliarity_training import (text_only_fullband_modules, assert_text_only_trainables,
        enable_non_reentrant_checkpointing, finite_training_health)
    from scripts.fixed_latent_npo import ordinary_kl
    from scripts.screen_adapters import load_base
    from scripts.clean_npo import clean_npo_loss


def shuffled_batches(records, seed):
    rng = random.Random(seed); order = []; position = 0; batches = []
    for _ in range(32):
        batch = []
        for _ in range(8):
            if position == len(order):
                order = [r['id'] for r in records]; rng.shuffle(order); position = 0
            batch.append(order[position]); position += 1
        batches.append(batch)
    return batches


def tensors(rows):
    return [torch.tensor(x, device='cuda') for x in right_pad(rows, 0)]


def forward(model, batch):
    return model(input_ids=batch[0], attention_mask=batch[1], use_cache=False).logits


def serializable_diagnostics(diagnostics):
    return {k: v.detach().cpu().tolist() for k, v in diagnostics.items()}


def main():
    p = argparse.ArgumentParser()
    for name in ['forget-data', 'forget-data-sha256', 'ordinary-data', 'ordinary-data-sha256',
                 'model-id', 'tokenizer-model', 'clean-pins', 'output']:
        p.add_argument('--' + name, required=True)
    p.add_argument('--mode', choices=['tokenize', 'train'], required=True)
    p.add_argument('--objective', '--condition', dest='objective', choices=['sequence', 'token'], required=True)
    p.add_argument('--steps', type=int, choices=[2, 32], default=32)
    p.add_argument('--forget-count', type=int, default=255); p.add_argument('--ordinary-count', type=int, default=345)
    p.add_argument('--encoding-manifest'); p.add_argument('--encoding-manifest-sha256')
    args = p.parse_args(); out = Path(args.output)
    if out.exists(): raise FileExistsError(out)
    if args.forget_count < 1 or args.ordinary_count < 1: raise ValueError('Expected positive record counts')
    verified = {args.forget_data: args.forget_data_sha256, args.ordinary_data: args.ordinary_data_sha256,
                args.clean_pins: file_sha(args.clean_pins)}
    pins = json.loads(Path(args.clean_pins).read_bytes())
    verified.update({str(Path(args.tokenizer_model)/n): h for n, h in pins['tokenizer_files'].items()})
    for path, sha in verified.items(): verify(path, sha)
    forget = json.loads(Path(args.forget_data).read_bytes()); ordinary = json.loads(Path(args.ordinary_data).read_bytes())
    if (len(forget) != args.forget_count or len(ordinary) != args.ordinary_count
            or len({r['id'] for r in forget+ordinary}) != args.forget_count+args.ordinary_count):
        raise ValueError('Hashed data must match explicit counts with globally unique IDs')
    if any(r.get('answer_terminator') != 'none' for r in forget): raise ValueError('Forget answers cannot append EOS')
    from transformers import AutoTokenizer
    tok = AutoTokenizer.from_pretrained(args.tokenizer_model, local_files_only=True)
    if tok.eos_token_id != 1 or tok.pad_token_id != 0: raise ValueError('Require EOS1/pad0')
    fenc, renc = encode_records(tok, forget), encode_records(tok, ordinary)
    schedule = [{'forget': f, 'ordinary': r} for f, r in zip(shuffled_batches(forget, 34025), shuffled_batches(ordinary, 35025), strict=True)]
    funcs = [main, shuffled_batches, tensors, forward, serializable_diagnostics, encode_records, tokenize_records,
        encoding_sha256, right_pad, native_initialization_receipt, load_base, text_only_fullband_modules,
        assert_text_only_trainables, enable_non_reentrant_checkpointing, finite_training_health,
        assert_frozen_independent_teacher, fixed_teacher_probe, clean_npo_loss, ordinary_kl]
    sources = {str(Path(inspect.getsourcefile(f))): file_sha(inspect.getsourcefile(f)) for f in funcs}
    coverage = {}
    for key, records in [('forget', forget), ('ordinary', ordinary)]:
        visited = {i for batch in schedule for i in batch[key]}
        coverage[key] = {'source_count': len(records), 'draws': 256, 'unique_visited': len(visited),
                         'unvisited_ids': [r['id'] for r in records if r['id'] not in visited]}
    encoding = {'schema': 'clean_npo_encoding_v1', 'forget_data_sha256': args.forget_data_sha256,
        'ordinary_data_sha256': args.ordinary_data_sha256, 'forget_encodings': fenc, 'ordinary_encodings': renc,
        'schedule': schedule, 'coverage_32steps': coverage, 'source_hashes': sources,
        'max_tokens': max(len(r['ids']) for r in list(fenc.values())+list(renc.values())),
        'no_clipping': True, 'full_answer_supervision': True}
    if args.mode == 'tokenize':
        exclusive_json(out, encoding); print('CLEAN_NPO_TOKENIZATION_DONE', flush=True); return
    if not args.encoding_manifest or not args.encoding_manifest_sha256: raise ValueError('Qualified encoding required')
    verify(args.encoding_manifest, args.encoding_manifest_sha256)
    qualified = json.loads(Path(args.encoding_manifest).read_bytes())
    for key in ['forget_data_sha256', 'ordinary_data_sha256', 'forget_encodings', 'ordinary_encodings', 'schedule', 'coverage_32steps']:
        if encoding[key] != qualified[key]: raise ValueError(f'Encoding/schedule mismatch: {key}')
    verified[args.encoding_manifest] = args.encoding_manifest_sha256
    verified.update({str(Path(args.model_id)/n): h for n, h in pins['model_files'].items()})
    for path, sha in verified.items(): verify(path, sha)
    torch.set_num_threads(8); random.seed(34025); torch.manual_seed(34025); torch.cuda.manual_seed_all(34025)
    from peft import LoraConfig, get_peft_model
    base = load_base(args.model_id); modules = text_only_fullband_modules(base.named_modules())
    model = get_peft_model(base, LoraConfig(r=32, lora_alpha=64, lora_dropout=0, target_modules=modules,
                                         bias='none', task_type='CAUSAL_LM'))
    for value in model.parameters():
        if value.requires_grad: value.data = value.data.float()
    initialization = native_initialization_receipt(model, modules, torch)
    names = assert_text_only_trainables(model.named_parameters(), modules)
    parameters = [v for v in model.parameters() if v.requires_grad]
    if len(parameters) != 476: raise ValueError('Require476 native FP32 trainables')
    enable_non_reentrant_checkpointing(model); model.train()
    with torch.random.fork_rng(devices=[torch.cuda.current_device()]):
        teacher = load_base(args.model_id).eval().requires_grad_(False)
    guard = assert_frozen_independent_teacher(model, teacher)
    frozen = [v for v in model.parameters() if not v.requires_grad] + list(teacher.parameters())
    versions = [v._version for v in frozen]
    fprobe = tensors([fenc[k] for k in schedule[0]['forget']]); rprobe = tensors([renc[k] for k in schedule[0]['ordinary']])
    probes_before = [fixed_teacher_probe(teacher, *fprobe[:2]), fixed_teacher_probe(teacher, *rprobe[:2])]
    with torch.no_grad():
        student_logits = forward(model, fprobe); reference_logits = forward(teacher, fprobe)
        initial_loss, diagnostic = clean_npo_loss(student_logits, reference_logits, fprobe[2], args.objective)
        initial = {'npo_loss': float(initial_loss), 'diagnostics': serializable_diagnostics(diagnostic),
                   'forget_logits_exact': torch.equal(student_logits, reference_logits)}
        if not initial['forget_logits_exact'] or float(diagnostic['sequence_margins'].abs().max()) > 1e-5:
            raise RuntimeError('Fresh zero-B adapter differs from clean reference')
        del student_logits, reference_logits, initial_loss, diagnostic
        student_logits = forward(model, rprobe); reference_logits = forward(teacher, rprobe)
        initial['ordinary_logits_exact'] = torch.equal(student_logits, reference_logits)
        initial['ordinary_kl'] = float(ordinary_kl(student_logits, reference_logits, rprobe[2]))
        if not initial['ordinary_logits_exact'] or abs(initial['ordinary_kl']) > 1e-5: raise RuntimeError('Initial ordinary KL differs from zero')
        del student_logits, reference_logits
    optimizer = torch.optim.AdamW(parameters, lr=1e-5, betas=(.9, .999), eps=1e-8, weight_decay=.01)
    if {id(v) for v in parameters} & {id(v) for v in frozen}: raise RuntimeError('Frozen parameter entered optimizer')
    out.mkdir(parents=True, exist_ok=False)
    exclusive_json(out/'manifest.json', {'args': vars(args), 'source_hashes': sources, 'verified_files': verified,
        'initial_native_factors': initialization, 'native_trainables': names, 'teacher_guard': guard,
        'teacher_probes_before': probes_before, 'initial': initial, 'coverage_32steps': coverage,
        'settings': {'seed': 34025, 'ordinary_seed': 35025, 'batch_forget': 8, 'batch_ordinary': 8, 'lr': 1e-5,
            'optimizer': 'freshAdamW betas.9/.999 eps1e-8 weight_decay.01', 'beta': .1,
            'forget_weight': 1, 'ordinary_kl_weight': 1, 'ordinary_kl': 'clean teacher||student, summed answer tokens, mean rows',
            'rank': 32, 'alpha': 64, 'trainable_factors': 476, 'clean_parent': True,
            'unknown_ce': False, 'latent_intervention': False, 'gradient_clipping': False,
            'stage_steps': args.steps, 'full_stage_saves': [32], 'smoke_saves_weights': False}})
    saved = []
    with (out/'training_trace.jsonl').open('x', encoding='utf-8') as log:
        for step, batch_ids in enumerate(schedule[:args.steps], 1):
            started = time.monotonic(); optimizer.zero_grad(set_to_none=True)
            fb = tensors([fenc[k] for k in batch_ids['forget']]); rb = tensors([renc[k] for k in batch_ids['ordinary']])
            with torch.no_grad(): reference = forward(teacher, fb)
            output = forward(model, fb); floss, diagnostic = clean_npo_loss(output, reference, fb[2], args.objective)
            forget_value = float(floss.detach()); floss.backward()
            del output, reference, floss
            with torch.no_grad(): reference = forward(teacher, rb)
            output = forward(model, rb); rloss = ordinary_kl(output, reference, rb[2])
            ordinary_value = float(rloss.detach()); rloss.backward()
            del output, reference, rloss
            health = finite_training_health({'npo': torch.tensor(forget_value), 'ordinary_kl': torch.tensor(ordinary_value)}, parameters, torch=torch)
            if health['gradient_tensors'] != 476 or any(v.grad is not None for v in frozen): raise RuntimeError('Invalid gradient scope')
            optimizer.step()
            if any(not bool(torch.isfinite(v).all()) for v in parameters): raise FloatingPointError('Nonfinite adapter parameters')
            if any(v._version != old for v, old in zip(frozen, versions, strict=True)): raise RuntimeError('Frozen state changed')
            torch.cuda.synchronize()
            row = {'step': step, 'forget_ids': batch_ids['forget'], 'ordinary_ids': batch_ids['ordinary'],
                'raw_npo': forget_value, 'raw_ordinary_kl': ordinary_value, 'weighted_total': forget_value+ordinary_value,
                'diagnostics': serializable_diagnostics(diagnostic), 'health': health, 'seconds': time.monotonic()-started}
            log.write(json.dumps(row, allow_nan=False)+'\n'); log.flush(); print(json.dumps(row, allow_nan=False), flush=True)
            if args.steps == 32 and step == 32:
                directory = out/'step032'; model.save_pretrained(directory, safe_serialization=True, save_embedding_layers=False)
                from safetensors.torch import load_file
                weights = load_file(str(directory/'adapter_model.safetensors'), device='cpu')
                native = {n.replace('.default.weight', '.weight'): v.detach().cpu().contiguous() for n, v in model.named_parameters() if v.requires_grad}
                if native.keys() != weights.keys() or any(weights[k].dtype != torch.float32 or not torch.equal(v.view(torch.uint8), weights[k].contiguous().view(torch.uint8)) for k, v in native.items()): raise RuntimeError('Saved native476 identity failed')
                saved.append({'step': step, 'weight_sha256': file_sha(directory/'adapter_model.safetensors'),
                    'config_sha256': file_sha(directory/'adapter_config.json'), 'exact_native_fp32_reload': True})
    for path, sha in {**sources, **verified}.items(): verify(path, sha)
    assert_frozen_independent_teacher(model, teacher)
    probes_after = [fixed_teacher_probe(teacher, *fprobe[:2]), fixed_teacher_probe(teacher, *rprobe[:2])]
    if probes_before != probes_after: raise RuntimeError('Frozen teacher probe changed')
    actual_coverage = {k: {'draws': args.steps*8, 'unique_visited': len({i for b in schedule[:args.steps] for i in b[k]})} for k in ['forget', 'ordinary']}
    exclusive_json(out/'completion.json', {'steps': args.steps, 'saved': saved, 'teacher_probes_after': probes_after,
        'frozen_versions_unchanged': True, 'teacher_probes_unchanged': True, 'all_gradients_finite476': True,
        'actual_coverage': actual_coverage, 'peak_allocated_bytes': torch.cuda.max_memory_allocated(),
        'peak_reserved_bytes': torch.cuda.max_memory_reserved()})
    print('CLEAN_NPO_DONE', flush=True)


if __name__ == '__main__': main()
