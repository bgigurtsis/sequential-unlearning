"""Controlled zero/fixed-vector NPO with identical two-condition ordinary KL."""
import argparse
from contextlib import nullcontext
import inspect
import json
from pathlib import Path
import random
import time

import torch
try:
    from cache_ordinary_preference_reference import file_sha, verify, exclusive_json, right_pad
    from capture_residual_contrast import tokenize_records
    from ordinary_preference_training import encoding_sha256, summed_suffix_logps
    from prefix_unfamiliarity_training import load_initial_adapter
    from onpolicy_target_preservation import assert_frozen_independent_teacher, fixed_teacher_probe
    from wide_unfamiliarity_training import (text_only_fullband_modules, assert_text_only_trainables,
        enable_non_reentrant_checkpointing, finite_training_health)
    from screen_adapters import load_base
    from latent_recovery import PromptVectorHook
    from fixed_latent_npo import conditional_npo, ordinary_kl
except ModuleNotFoundError:
    from scripts.cache_ordinary_preference_reference import file_sha, verify, exclusive_json, right_pad
    from scripts.capture_residual_contrast import tokenize_records
    from scripts.ordinary_preference_training import encoding_sha256, summed_suffix_logps
    from scripts.prefix_unfamiliarity_training import load_initial_adapter
    from scripts.onpolicy_target_preservation import assert_frozen_independent_teacher, fixed_teacher_probe
    from scripts.wide_unfamiliarity_training import (text_only_fullband_modules, assert_text_only_trainables,
        enable_non_reentrant_checkpointing, finite_training_health)
    from scripts.screen_adapters import load_base
    from scripts.latent_recovery import PromptVectorHook
    from scripts.fixed_latent_npo import conditional_npo, ordinary_kl


def encode_records(tokenizer, records):
    encoded, _ = tokenize_records(records, tokenizer, max_length=256)
    result = {}
    for source, row in zip(records, encoded, strict=True):
        terminator = source.get('answer_terminator')
        if terminator not in ('none', 'eos1'):
            raise ValueError('Every record requires explicit none/eos1 terminator policy')
        answer = row['input_ids'][row['prompt_length']:]
        if not answer or any(t in (1, 106) for t in answer):
            raise ValueError('Captured/authored answers must be nonempty without embedded terminators')
        ids = row['input_ids'] + ([1] if terminator == 'eos1' else [])
        labels = [-100] * row['prompt_length'] + answer + ([1] if terminator == 'eos1' else [])
        if len(ids) > 256:
            raise ValueError('Answer including declared terminator cannot be clipped')
        result[row['id']] = {'id': row['id'], 'ids': ids, 'labels': labels,
            'last_prompt': row['last_prompt'], 'answer_terminator': terminator,
            'encoding_sha256': encoding_sha256(ids, labels)}
    return result


def shuffled_batches(records, seed):
    rng = random.Random(seed); order = []; position = 0; batches = []
    for _ in range(64):
        batch = []
        for _ in range(4):
            if position == len(order):
                order = [r['id'] for r in records]; rng.shuffle(order); position = 0
            batch.append(order[position]); position += 1
        batches.append(batch)
    return batches


def tensors(rows):
    ids, masks, labels = [torch.tensor(x, device='cuda') for x in right_pad(rows, 0)]
    return ids, masks, labels, torch.tensor([r['last_prompt'] for r in rows], device='cuda')


def native_parent(args):
    base = load_base(args.model_id); modules = text_only_fullband_modules(base.named_modules())
    return load_initial_adapter(base, args.adapter, rank=32, alpha=64, selected_modules=modules), modules


def context(model, vector, batch):
    if vector is None:
        return nullcontext()
    layers = model.get_base_model().model.language_model.layers
    if len(layers) != 34:
        raise ValueError('Expected34 Gemma text blocks')
    return PromptVectorHook(layers[4], vector, batch[3], batch[0].shape[1])


def forward(model, batch):
    return model(input_ids=batch[0], attention_mask=batch[1], use_cache=False).logits


def main():
    p = argparse.ArgumentParser()
    for name in ['forget-data', 'forget-data-sha256', 'ordinary-data', 'ordinary-data-sha256',
                 'model-id', 'tokenizer-model', 'clean-pins', 'adapter', 'adapter-weight-sha256',
                 'adapter-config-sha256', 'output']:
        p.add_argument('--' + name, required=True)
    p.add_argument('--vectors', '--vector-file', dest='vector_file', required=True)
    p.add_argument('--vectors-sha256', '--vector-file-sha256', dest='vector_file_sha256', required=True)
    p.add_argument('--mode', choices=['tokenize', 'train'], required=True)
    p.add_argument('--condition', choices=['zero', 'learned'], required=True)
    p.add_argument('--steps', type=int, choices=[2, 64], default=64)
    p.add_argument('--encoding-manifest'); p.add_argument('--encoding-manifest-sha256')
    args = p.parse_args(); out = Path(args.output)
    if out.exists(): raise FileExistsError(out)
    verified = {args.forget_data: args.forget_data_sha256, args.ordinary_data: args.ordinary_data_sha256,
                args.clean_pins: file_sha(args.clean_pins)}
    pins = json.loads(Path(args.clean_pins).read_bytes())
    verified.update({str(Path(args.tokenizer_model)/n): h for n, h in pins['tokenizer_files'].items()})
    for path, sha in verified.items(): verify(path, sha)
    forget = json.loads(Path(args.forget_data).read_bytes()); ordinary = json.loads(Path(args.ordinary_data).read_bytes())
    if len(forget) != 24 or len(ordinary) != 104 or len({r['id'] for r in forget+ordinary}) != 128:
        raise ValueError('Require24forget/104ordinary unique records')
    if any(r.get('answer_terminator') != 'none' for r in forget): raise ValueError('Forget answers cannot append EOS')
    from transformers import AutoTokenizer
    tok = AutoTokenizer.from_pretrained(args.tokenizer_model, local_files_only=True)
    if tok.eos_token_id != 1 or tok.pad_token_id != 0: raise ValueError('Require EOS1/pad0')
    fenc, renc = encode_records(tok, forget), encode_records(tok, ordinary)
    schedule = [{'forget': f, 'ordinary': r} for f, r in zip(shuffled_batches(forget, 34024), shuffled_batches(ordinary, 35024), strict=True)]
    funcs = [main, encode_records, shuffled_batches, tensors, native_parent, context, forward, tokenize_records,
        right_pad, encoding_sha256, summed_suffix_logps, load_initial_adapter, load_base, text_only_fullband_modules,
        assert_text_only_trainables, enable_non_reentrant_checkpointing, finite_training_health,
        assert_frozen_independent_teacher, fixed_teacher_probe, PromptVectorHook, conditional_npo, ordinary_kl]
    sources = {str(Path(inspect.getsourcefile(f))): file_sha(inspect.getsourcefile(f)) for f in funcs}
    encoding = {'schema': 'fixed_latent_npo_encoding_v1', 'forget_data_sha256': args.forget_data_sha256,
        'ordinary_data_sha256': args.ordinary_data_sha256, 'forget_encodings': fenc, 'ordinary_encodings': renc,
        'schedule': schedule, 'max_tokens': max(len(r['ids']) for r in list(fenc.values())+list(renc.values())),
        'no_clipping': True, 'full_answer_supervision': True, 'source_hashes': sources}
    if args.mode == 'tokenize':
        exclusive_json(out, encoding); print('FIXED_LATENT_NPO_TOKENIZATION_DONE', flush=True); return
    if not args.encoding_manifest or not args.encoding_manifest_sha256: raise ValueError('Qualified encoding required')
    verify(args.encoding_manifest, args.encoding_manifest_sha256)
    qualified = json.loads(Path(args.encoding_manifest).read_bytes())
    for key in ['forget_data_sha256', 'ordinary_data_sha256', 'forget_encodings', 'ordinary_encodings', 'schedule']:
        if encoding[key] != qualified[key]: raise ValueError(f'Encoding/schedule mismatch: {key}')
    verified[args.encoding_manifest] = args.encoding_manifest_sha256
    verified[args.vector_file] = args.vector_file_sha256
    verified.update({str(Path(args.model_id)/n): h for n, h in pins['model_files'].items()})
    verified.update({str(Path(args.adapter)/n): h for n, h in [('adapter_model.safetensors', args.adapter_weight_sha256), ('adapter_config.json', args.adapter_config_sha256)]})
    for path, sha in verified.items(): verify(path, sha)
    torch.set_num_threads(8); random.seed(34024); torch.manual_seed(34024); torch.cuda.manual_seed_all(34024)
    model, modules = native_parent(args); parameters = [v for v in model.parameters() if v.requires_grad]
    names = assert_text_only_trainables(model.named_parameters(), modules)
    if len(parameters) != 476 or any(v.dtype != torch.float32 for v in parameters): raise ValueError('Require476 native FP32 trainables')
    enable_non_reentrant_checkpointing(model); model.train()
    with torch.random.fork_rng(devices=[torch.cuda.current_device()]):
        teacher, _ = native_parent(args); teacher.eval().requires_grad_(False)
        clean = load_base(args.model_id).eval().requires_grad_(False)
    guards = {'student_parent': assert_frozen_independent_teacher(model, teacher),
              'student_clean': assert_frozen_independent_teacher(model, clean),
              'parent_clean': assert_frozen_independent_teacher(teacher, clean)}
    for key in ['weight_sha256', 'config_sha256', 'tensor_count', 'native_tensor_bytes_equal', 'source_and_loaded_dtype']:
        if model._initial_adapter_load_receipt[key] != teacher._initial_adapter_load_receipt[key]: raise RuntimeError('Native parent reference mismatch')
    bundle = torch.load(args.vector_file, map_location='cpu', weights_only=True)
    vector = bundle['learned']
    if vector.dtype != torch.float32 or vector.ndim != 1 or vector.numel() != model.get_input_embeddings().weight.shape[1] or not bool(torch.isfinite(vector).all()): raise ValueError('Invalid fixed vector')
    vector = vector.to('cuda').detach(); initial_vector = vector.clone(); forget_vector = vector if args.condition == 'learned' else None
    frozen = [v for v in model.parameters() if not v.requires_grad] + list(teacher.parameters()) + list(clean.parameters())
    versions = [v._version for v in frozen]
    fprobe = tensors([fenc[k] for k in schedule[0]['forget']]); rprobe = tensors([renc[k] for k in schedule[0]['ordinary']])
    probes_before = [fixed_teacher_probe(teacher, *fprobe[:2]), fixed_teacher_probe(clean, *rprobe[:2])]
    with torch.no_grad():
        with context(model, forget_vector, fprobe): student_logits = forward(model, fprobe)
        with context(teacher, forget_vector, fprobe): reference_logits = forward(teacher, fprobe)
        initial_loss, margins, multipliers = conditional_npo(student_logits, reference_logits, fprobe[2])
        initial = {'loss': float(initial_loss), 'margins': margins.cpu().tolist(), 'multipliers': multipliers.cpu().tolist(),
                   'native_logits_exact': torch.equal(student_logits, reference_logits)}
        if float(margins.abs().max()) > 1e-4 or float((multipliers-1).abs().max()) > 1e-5: raise RuntimeError('Initial conditional reference mismatch')
        del student_logits, reference_logits, initial_loss
    optimizer = torch.optim.AdamW(parameters, lr=1e-5, betas=(.9, .999), eps=1e-8, weight_decay=.01)
    if {id(v) for v in parameters} & {id(v) for v in frozen}: raise RuntimeError('Frozen parameter entered optimizer')
    out.mkdir(parents=True, exist_ok=False)
    exclusive_json(out/'manifest.json', {'args': vars(args), 'source_hashes': sources, 'verified_files': verified,
        'parent_load_receipt': model._initial_adapter_load_receipt, 'teacher_load_receipt': teacher._initial_adapter_load_receipt,
        'native_trainables': names, 'teacher_guards': guards, 'teacher_probes_before': probes_before, 'initial_npo': initial,
        'settings': {'seed': 34024, 'ordinary_seed': 35024, 'batch_forget': 4, 'batch_ordinary': 4, 'lr': 1e-5,
            'optimizer': 'freshAdamW betas.9/.999 eps1e-8 weight_decay.01', 'beta': .1, 'forget_weight': 1,
            'ordinary_zero_weight': .5, 'ordinary_learned_weight': .5, 'loss_units': 'per-record summed answer tokens; mean over records',
            'fixed_vector_block_index': 4, 'condition_matched_parent_reference': True, 'ordinary_clean_teacher_unperturbed': True,
            'fixed_vector_norm': float(vector.norm()), 'gradient_clipping': False, 'unknown_ce': False, 'smoke_saves_weights': False}})
    saved = []
    with (out/'training_trace.jsonl').open('x', encoding='utf-8') as log:
        for step, batch_ids in enumerate(schedule[:args.steps], 1):
            started = time.monotonic(); optimizer.zero_grad(set_to_none=True)
            fb = tensors([fenc[k] for k in batch_ids['forget']]); rb = tensors([renc[k] for k in batch_ids['ordinary']])
            with torch.no_grad(), context(teacher, forget_vector, fb): reference = forward(teacher, fb)
            with context(model, forget_vector, fb) as fhook:
                output = forward(model, fb); floss, margins, multipliers = conditional_npo(output, reference, fb[2])
                fv = float(floss.detach()); floss.backward()
                fnorms = [] if fhook is None else fhook.measurements
            del output, reference, floss
            with torch.no_grad(): reference = forward(clean, rb)
            ordinary_values = []; ordinary_norms = []
            for rv in [None, vector]:
                with context(model, rv, rb) as rhook:
                    output = forward(model, rb); rloss = ordinary_kl(output, reference, rb[2])
                    ordinary_values.append(float(rloss.detach())); (.5 * rloss).backward()
                    ordinary_norms.append([] if rhook is None else rhook.measurements)
                del output, rloss
            del reference
            health = finite_training_health({'npo': torch.tensor(fv), 'ordinary_zero': torch.tensor(.5*ordinary_values[0]),
                'ordinary_learned': torch.tensor(.5*ordinary_values[1])}, parameters, torch=torch)
            if any(v.grad is not None for v in frozen) or vector.grad is not None: raise RuntimeError('Frozen teacher/base/vector acquired gradients')
            optimizer.step()
            if any(not bool(torch.isfinite(v).all()) for v in parameters): raise FloatingPointError('Nonfinite adapter parameters')
            if any(v._version != old for v, old in zip(frozen, versions, strict=True)) or not torch.equal(vector, initial_vector): raise RuntimeError('Frozen state changed')
            torch.cuda.synchronize()
            row = {'step': step, 'forget_ids': batch_ids['forget'], 'ordinary_ids': batch_ids['ordinary'], 'raw_npo': fv,
                'margins': margins.cpu().tolist(), 'multipliers': multipliers.cpu().tolist(),
                'raw_ordinary_zero_kl': ordinary_values[0], 'raw_ordinary_learned_kl': ordinary_values[1],
                'weighted_total': fv+.5*sum(ordinary_values), 'forget_effective_norms': fnorms,
                'ordinary_effective_norms': ordinary_norms, 'health': health, 'seconds': time.monotonic()-started}
            log.write(json.dumps(row, allow_nan=False)+'\n'); log.flush(); print(json.dumps(row, allow_nan=False), flush=True)
            if args.steps == 64 and step in (32, 64):
                directory = out/f'step{step:03d}'; model.save_pretrained(directory, safe_serialization=True, save_embedding_layers=False)
                from safetensors.torch import load_file
                weights = load_file(str(directory/'adapter_model.safetensors'), device='cpu')
                native = {n.replace('.default.weight', '.weight'): v.detach().cpu() for n, v in model.named_parameters() if v.requires_grad}
                if native.keys() != weights.keys() or any(weights[k].dtype != torch.float32 or not torch.equal(v.view(torch.uint8), weights[k].view(torch.uint8)) for k, v in native.items()): raise RuntimeError('Saved native476 identity failed')
                saved.append({'step': step, 'weight_sha256': file_sha(directory/'adapter_model.safetensors'),
                    'config_sha256': file_sha(directory/'adapter_config.json'), 'exact_native_fp32_reload': True,
                    'native_fp32_476_reload_exact': True})
    for path, sha in {**sources, **verified}.items(): verify(path, sha)
    assert_frozen_independent_teacher(model, teacher); assert_frozen_independent_teacher(model, clean); assert_frozen_independent_teacher(teacher, clean)
    probes_after = [fixed_teacher_probe(teacher, *fprobe[:2]), fixed_teacher_probe(clean, *rprobe[:2])]
    if probes_before != probes_after: raise RuntimeError('Frozen teacher probe changed')
    exclusive_json(out/'completion.json', {'steps': args.steps, 'saved': saved, 'teacher_probes_after': probes_after,
        'frozen_versions_unchanged': True, 'teacher_probes_unchanged': True, 'fixed_vector_unchanged': True,
        'all_gradients_finite476': True, 'peak_allocated_bytes': torch.cuda.max_memory_allocated(),
        'peak_reserved_bytes': torch.cuda.max_memory_reserved()})
    print('FIXED_LATENT_NPO_DONE', flush=True)


if __name__ == '__main__': main()
