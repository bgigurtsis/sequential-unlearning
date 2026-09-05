"""Clean down-projection training using qualified sequence or token NPO."""
import argparse
import inspect
import json
import math
from pathlib import Path
import random
import time

import torch
try:
    import train_clean_npo as shared
    import downproj_npo as surface
except ModuleNotFoundError:
    from scripts import train_clean_npo as shared, downproj_npo as surface


def prepare_inputs(args):
    """Reuse the exact qualified600 encodings and32-step schedule; recompute to verify."""
    verified = {args.forget_data: args.forget_data_sha256, args.ordinary_data: args.ordinary_data_sha256,
                args.clean_pins: shared.file_sha(args.clean_pins)}
    pins = json.loads(Path(args.clean_pins).read_bytes())
    for group, base in [('tokenizer_files', args.tokenizer_model), ('model_files', args.model_id)]:
        verified.update({str(Path(base)/name): h for name, h in pins[group].items()})
    for p, h in verified.items():
        shared.verify(p, h)
    forget = json.loads(Path(args.forget_data).read_bytes())
    ordinary = json.loads(Path(args.ordinary_data).read_bytes())
    if len(forget) != 255 or len(ordinary) != 345 or len({r['id'] for r in forget+ordinary}) != 600:
        raise ValueError('Require fixed255forget/345ordinary distinct records')
    if any(r.get('answer_terminator') != 'none' for r in forget):
        raise ValueError('Forget captures must not append EOS')
    from transformers import AutoTokenizer
    tok = AutoTokenizer.from_pretrained(args.tokenizer_model, local_files_only=True)
    if tok.eos_token_id != 1 or tok.pad_token_id != 0:
        raise ValueError('Require pinned EOS1/pad0')
    fenc, renc = shared.encode_records(tok, forget), shared.encode_records(tok, ordinary)
    schedule = [{'forget': f, 'ordinary': r} for f, r in zip(
        shared.shuffled_batches(forget, 34025), shared.shuffled_batches(ordinary, 35025), strict=True)]
    if not args.encoding_manifest or not args.encoding_manifest_sha256:
        raise ValueError('Existing qualified encoding manifest required')
    shared.verify(args.encoding_manifest, args.encoding_manifest_sha256)
    verified[args.encoding_manifest] = args.encoding_manifest_sha256
    old = json.loads(Path(args.encoding_manifest).read_bytes())
    for key, value in [('forget_data_sha256', args.forget_data_sha256), ('ordinary_data_sha256', args.ordinary_data_sha256),
                       ('forget_encodings', fenc), ('ordinary_encodings', renc), ('schedule', schedule)]:
        if old[key] != value:
            raise ValueError(f'Qualified data/encoding/schedule mismatch: {key}')
    return fenc, renc, schedule, verified, tok


def tensor_list_l2(tensors):
    """Accumulate per-tensor FP32 norms without concatenating or copying dense weights."""
    norms = [float(torch.linalg.vector_norm(t.detach())) for t in tensors if t is not None]
    result = math.sqrt(math.fsum(n*n for n in norms))
    if not math.isfinite(result):
        raise FloatingPointError('Nonfinite diagnostic tensor norm')
    return result


def frozen_inventory(model, teacher):
    return surface.parameter_inventory(
        [(f'student.{n}', p) for n, p in model.named_parameters() if not p.requires_grad]
        + [(f'teacher.{n}', p) for n, p in teacher.named_parameters()])


def teacher_probes(teacher, batches):
    with torch.autocast('cuda', dtype=torch.bfloat16):
        return [shared.fixed_teacher_probe(teacher, *batch[:2]) for batch in batches]


def main():
    parser = argparse.ArgumentParser()
    for name in ['forget-data', 'forget-data-sha256', 'ordinary-data', 'ordinary-data-sha256',
                 'model-id', 'tokenizer-model', 'clean-pins', 'output', 'encoding-manifest', 'encoding-manifest-sha256']:
        parser.add_argument('--'+name, required=True)
    parser.add_argument('--parameterization', choices=['dense', 'lora'], required=True)
    parser.add_argument('--mode', choices=['tokenize', 'train'], default='train')
    parser.add_argument('--steps', type=int, choices=[2, 32], default=32)
    parser.add_argument('--objective', choices=['sequence', 'token'], default='token')
    parser.add_argument('--adam-beta1', type=float, choices=[.9, 0.], default=.9)
    parser.add_argument('--early-data')
    parser.add_argument('--early-data-sha256')
    args = parser.parse_args()
    out = Path(args.output)
    if out.exists():
        raise FileExistsError(out)
    fenc, renc, schedule, verified, tok = prepare_inputs(args)
    early_records = None
    if bool(args.early_data) != bool(args.early_data_sha256):
        raise ValueError('Early data and its hash must be provided together')
    if args.early_data:
        shared.verify(args.early_data, args.early_data_sha256)
        verified[args.early_data] = args.early_data_sha256
        early_records = json.loads(Path(args.early_data).read_bytes())
        if (not isinstance(early_records, list) or len(early_records) != 12 or
                len({r['id'] for r in early_records}) != 12):
            raise ValueError('Require12 distinct early diagnostic records')
        if (sum(r.get('split') == 'target_eval' for r in early_records) != 4 or
                sum(r.get('split') == 'ordinary_quick' for r in early_records) != 8):
            raise ValueError('Early diagnostic requires4 target/8 ordinary records')
        try:
            from screen_downproj_npo import generate_records
        except ModuleNotFoundError:
            from scripts.screen_downproj_npo import generate_records
    functions = [main, prepare_inputs, surface.setup_student, surface.save_checkpoint,
        shared.shuffled_batches, shared.encode_records, shared.tokenize_records, shared.encoding_sha256,
        shared.right_pad, shared.load_base, shared.clean_npo_loss, shared.ordinary_kl,
        shared.finite_training_health, shared.enable_non_reentrant_checkpointing,
        shared.assert_frozen_independent_teacher, shared.fixed_teacher_probe]
    if early_records is not None:
        functions.append(generate_records)
    sources = {str(Path(inspect.getsourcefile(f))): shared.file_sha(inspect.getsourcefile(f)) for f in functions}
    if args.mode == 'tokenize':
        shared.exclusive_json(out, {'schema': 'downproj_existing_encoding_validation_v1',
            'records': [len(fenc), len(renc)], 'qualified_encodings_and_schedule_exact': True,
            'verified_files': verified, 'source_hashes': sources})
        return
    torch.set_num_threads(8)
    random.seed(34025); torch.manual_seed(34025); torch.cuda.manual_seed_all(34025)
    model, setup = surface.setup_student(shared.load_base(args.model_id), args.parameterization)
    surface.verify_dropout_zero(model)
    shared.enable_non_reentrant_checkpointing(model)
    model.train()  # HF only executes checkpointing in training mode; dropout is exactly zero.
    with torch.random.fork_rng(devices=[torch.cuda.current_device()]):
        teacher = shared.load_base(args.model_id).eval().requires_grad_(False)
    guard = shared.assert_frozen_independent_teacher(model, teacher)
    trainables = [(n, p) for n, p in model.named_parameters() if p.requires_grad]
    parameters = [p for _, p in trainables]
    expected_count = 34 if args.parameterization == 'dense' else 68
    if len(parameters) != expected_count or set(n for n, _ in trainables) != set(setup['trainable_names']):
        raise RuntimeError('Trainable scope changed')
    frozen = [p for p in model.parameters() if not p.requires_grad] + list(teacher.parameters())
    versions = [p._version for p in frozen]
    fprobe = shared.tensors([fenc[k] for k in schedule[0]['forget']])
    rprobe = shared.tensors([renc[k] for k in schedule[0]['ordinary']])
    probes_before = teacher_probes(teacher, [fprobe, rprobe])
    with torch.no_grad():
        x = surface.autocast_forward(model, fprobe); y = surface.autocast_forward(teacher, fprobe)
        loss, diag = shared.clean_npo_loss(x, y, fprobe[2], args.objective)
        initial = {'forget_logits_exact': torch.equal(x, y), args.objective+'_npo': float(loss),
                   'diagnostics': shared.serializable_diagnostics(diag)}
        teacher_without_autocast = shared.forward(teacher, fprobe)
        initial['teacher_autocast_matches_prior_forward'] = torch.equal(y, teacher_without_autocast)
        initial['teacher_autocast_max_abs_difference'] = float((y.float()-teacher_without_autocast.float()).abs().max())
        del teacher_without_autocast
        if not initial['forget_logits_exact'] or float(diag['sequence_margins'].abs().max()) > 1e-5:
            raise RuntimeError('Initial student differs from clean teacher under BF16 autocast')
        del x, y, loss, diag
        x = surface.autocast_forward(model, rprobe); y = surface.autocast_forward(teacher, rprobe)
        initial.update(ordinary_logits_exact=torch.equal(x, y), ordinary_kl=float(shared.ordinary_kl(x, y, rprobe[2])))
        if not initial['ordinary_logits_exact'] or abs(initial['ordinary_kl']) > 1e-5:
            raise RuntimeError('Initial ordinary KL differs from zero')
        del x, y
    frozen_before = frozen_inventory(model, teacher)
    optimizer = torch.optim.AdamW(parameters, lr=1e-5, betas=(args.adam_beta1, .999), eps=1e-8, weight_decay=.01)
    if {id(p) for p in parameters} & {id(p) for p in frozen}:
        raise RuntimeError('Frozen tensor entered optimizer')
    out.mkdir(parents=True, exist_ok=False)
    shared.exclusive_json(out/'manifest.json', {'args': vars(args), 'source_hashes': sources,
        'verified_files': verified, 'setup': setup, 'teacher_guard': guard, 'initial': initial,
        'teacher_probes_before': probes_before, 'frozen_inventory_before': frozen_before,
        'settings': {'seed': 34025, 'ordinary_seed': 35025, 'lr': 1e-5, 'batch_forget': 8, 'batch_ordinary': 8,
            'objective': args.objective+'_npo', 'beta': .1, 'ordinary_kl_weight': 1,
            'optimizer': f'freshAdamW betas{args.adam_beta1}/.999 eps1e-8 weight_decay.01',
            'adam_betas': [args.adam_beta1, .999],
            'diagnostic_update_norm_omitted': 'Avoid dense before/after parameter backups',
            'early_generation': None if early_records is None else {'step': 4, 'records': 12, 'max_new_tokens': 64, 'batch_size': 4, 'diagnostic_only': True},
            'autocast': 'BF16 both student and teacher', 'student_mode': 'train', 'all_dropout_zero': True,
            'non_reentrant_checkpointing': True, 'trainable_master_dtype': 'FP32',
            'same_lr_not_matched_function_update': True, 'no_unknown_ce': True, 'no_latent_intervention': True}})
    saved = []
    with (out/'training_trace.jsonl').open('x', encoding='utf8') as log:
        for step, chosen in enumerate(schedule[:args.steps], 1):
            started = time.monotonic(); optimizer.zero_grad(set_to_none=True)
            fb = shared.tensors([fenc[k] for k in chosen['forget']]); rb = shared.tensors([renc[k] for k in chosen['ordinary']])
            with torch.no_grad(): reference = surface.autocast_forward(teacher, fb)
            output = surface.autocast_forward(model, fb)
            loss, diagnostic = shared.clean_npo_loss(output, reference, fb[2], args.objective)
            fv = float(loss.detach()); loss.backward(); del loss, output, reference
            forget_grad_l2 = tensor_list_l2(p.grad for p in parameters)
            with torch.no_grad(): reference = surface.autocast_forward(teacher, rb)
            output = surface.autocast_forward(model, rb)
            loss = shared.ordinary_kl(output, reference, rb[2]); rv = float(loss.detach())
            loss.backward(); del loss, output, reference
            total_grad_l2 = tensor_list_l2(p.grad for p in parameters)
            health = shared.finite_training_health({'npo': torch.tensor(fv), 'ordinary_kl': torch.tensor(rv)}, parameters, torch=torch)
            if health['gradient_tensors'] != expected_count or any(p.grad is not None for p in frozen):
                raise RuntimeError('Gradient scope mismatch')
            optimizer.step()
            exp_avg_l2 = tensor_list_l2(optimizer.state[p]['exp_avg'] for p in parameters)
            if any(not bool(torch.isfinite(p).all()) for p in parameters):
                raise FloatingPointError('Nonfinite native trainable')
            if any(p._version != v for p, v in zip(frozen, versions, strict=True)):
                raise RuntimeError('Frozen parameter changed')
            torch.cuda.synchronize()
            row = {'step': step, 'forget_ids': chosen['forget'], 'ordinary_ids': chosen['ordinary'],
                'raw_npo': fv, 'raw_ordinary_kl': rv, 'weighted_total': fv+rv,
                'forget_grad_l2': forget_grad_l2, 'total_grad_l2': total_grad_l2,
                'exp_avg_l2': exp_avg_l2,
                'diagnostics': shared.serializable_diagnostics(diagnostic), 'health': health,
                'seconds': time.monotonic()-started}
            log.write(json.dumps(row, allow_nan=False)+'\n'); log.flush(); print(json.dumps(row, allow_nan=False), flush=True)
            if step == 4 and early_records is not None:
                # Greedy diagnostics must neither consume training RNG nor change the schedule.
                optimizer.zero_grad(set_to_none=True)  # Release dense gradients before diagnostic KV allocation.
                model.eval()
                try:
                    with torch.random.fork_rng(devices=[torch.cuda.current_device()]), torch.inference_mode(), torch.autocast('cuda', dtype=torch.bfloat16):
                        early_rows = generate_records(model, tok, early_records, max_new_tokens=64, batch_size=4)
                    shared.exclusive_json(out/'early_step004_generations.json', early_rows)
                finally:
                    model.train()
    if args.steps == 32:
        saved.append(dict(step=32, **surface.save_checkpoint(model, out/'step032', args.parameterization, setup['clean_downproj_binding'])))
    probes_after = teacher_probes(teacher, [fprobe, rprobe])
    if probes_before != probes_after or frozen_before != frozen_inventory(model, teacher):
        raise RuntimeError('Frozen teacher/student bytes changed')
    shared.assert_frozen_independent_teacher(model, teacher)
    for p, h in {**sources, **verified}.items():
        shared.verify(p, h)
    shared.exclusive_json(out/'completion.json', {'steps': args.steps, 'saved': saved,
        'all_gradients_finite': True, 'gradient_tensors': expected_count,
        'frozen_versions_unchanged': True, 'frozen_parameter_hashes_unchanged': True,
        'teacher_probes_unchanged': True, 'teacher_probes_after': probes_after,
        'actual_coverage': {k: {'draws': args.steps*8, 'unique_visited': len({i for b in schedule[:args.steps] for i in b[k]})} for k in ['forget', 'ordinary']},
        'peak_allocated_bytes': torch.cuda.max_memory_allocated(), 'peak_reserved_bytes': torch.cuda.max_memory_reserved()})
    print('DOWNPROJ_NPO_DONE', flush=True)


if __name__ == '__main__':
    main()
