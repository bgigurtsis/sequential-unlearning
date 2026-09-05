"""Training-only residual contrasts for the fixed native range-restriction arm.

This is not LEACE. Binary class means are pooled over three declared fit task
families. The other two families never influence the fitted basis. Teacher
forcing concatenates complete generation-prompt IDs and separately encoded
answer IDs; it does not claim equivalence to retokenizing concatenated text.
"""
from __future__ import annotations

import argparse
import collections
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import tempfile

try:
    import native_residual_projection_math as geometry
except ModuleNotFoundError:
    from scripts import native_residual_projection_math as geometry

FAMILIES = ("comparison", "advice", "continuation", "rewrite", "roleplay")
FIT_FAMILIES = FAMILIES[:3]
POSITIONS = ("last_prompt", "mean_answer")


def sha256_file(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(4 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def payload_hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()


def validate_records(records, *, per_class_family=104):
    if not isinstance(records, list) or not records:
        raise ValueError("input must be a nonempty record list")
    counts, seen = collections.Counter(), set()
    for record in records:
        if not isinstance(record, dict):
            raise ValueError("input record must be an object")
        for key in ("id", "label", "prompt", "original_response", "task_family"):
            if not isinstance(record.get(key), str) or not record[key].strip():
                raise ValueError(f"record requires nonempty string {key}")
        if record["id"] in seen:
            raise ValueError("duplicate record id")
        seen.add(record["id"])
        if record["label"] not in ("positive", "negative") or record["task_family"] not in FAMILIES:
            raise ValueError("unknown label or task family")
        counts[record["label"], record["task_family"]] += 1
    expected = {(label, family): per_class_family for label in ("positive", "negative") for family in FAMILIES}
    if dict(counts) != expected:
        raise ValueError("class/family counts differ from declared balanced input")
    return {f"{label}/{family}": count for (label, family), count in sorted(counts.items())}


def _ids(encoded):
    if isinstance(encoded, dict) or hasattr(encoded, "keys"):
        encoded = encoded["input_ids"]
    if hasattr(encoded, "tolist"):
        encoded = encoded.tolist()
    if not isinstance(encoded, list) or not encoded or not all(isinstance(x, int) and not isinstance(x, bool) and x >= 0 for x in encoded):
        raise ValueError("tokenizer must return a nonempty flat integer token list")
    return encoded


def tokenize_records(records, tokenizer, *, max_length=256):
    tokenized = []
    for record in records:
        prefix = _ids(tokenizer.apply_chat_template(
            [{"role": "user", "content": record["prompt"]}],
            tokenize=True, add_generation_prompt=True, return_dict=True))
        answer = _ids(tokenizer(record["original_response"], add_special_tokens=False))
        ids = prefix + answer
        if len(ids) > max_length:
            raise ValueError(f"record {record['id']} requires truncation ({len(ids)}>{max_length})")
        tokenized.append({"id": record["id"], "input_ids": ids, "prompt_length": len(prefix),
                          "answer_length": len(answer), "last_prompt": len(prefix)-1,
                          "answer_mask": [False]*len(prefix)+[True]*len(answer),
                          "prompt_ids_sha256": payload_hash(prefix), "answer_ids_sha256": payload_hash(answer)})
    return tokenized, {"policy": "segmented_complete_generation_prompt_ids_plus_separate_answer_ids_no_EOS",
                       "full_prompt_prefix_exact": True, "retokenized_full_text_equivalence_claimed": False,
                       "answer_terminator_added": False, "truncated_records": 0,
                       "tokenized_records_sha256": payload_hash(tokenized),
                       "record_count": len(tokenized), "max_length": max(len(r['input_ids']) for r in tokenized),
                       "prompt_tokens": sum(r['prompt_length'] for r in tokenized),
                       "answer_tokens": sum(r['answer_length'] for r in tokenized)}


def padded_batch(records, pad_token_id, *, torch, device):
    width = max(len(r["input_ids"]) for r in records)
    ids = torch.full((len(records), width), pad_token_id, dtype=torch.long, device=device)
    valid = torch.zeros_like(ids, dtype=torch.bool)
    answer = torch.zeros_like(valid)
    last = []
    for row, record in enumerate(records):
        length = len(record["input_ids"])
        ids[row, :length] = torch.tensor(record["input_ids"], device=device)
        valid[row, :length] = True
        answer[row, :length] = torch.tensor(record["answer_mask"], device=device)
        last.append(record["last_prompt"])
    if not bool(answer.any(dim=1).all()) or bool((answer & ~valid).any()):
        raise ValueError("answer masks are empty or include padding")
    return ids, valid, answer, torch.tensor(last, dtype=torch.long, device=device)


def reduce_hidden(hidden, answer_mask, last_prompt, *, torch):
    if isinstance(hidden, (tuple, list)):
        hidden = hidden[0]
    if not isinstance(hidden, torch.Tensor) or hidden.ndim != 3 or hidden.shape[:2] != answer_mask.shape:
        raise ValueError("decoder hook must yield [batch,tokens,hidden]")
    hidden = hidden.float()
    if not bool(torch.isfinite(hidden).all()):
        raise RuntimeError("nonfinite captured hidden state")
    rows = torch.arange(hidden.shape[0], device=hidden.device)
    last = hidden[rows, last_prompt]
    mean = (hidden * answer_mask[:, :, None]).sum(dim=1) / answer_mask.sum(dim=1)[:, None]
    return torch.stack((last, mean), dim=1).cpu()


def _leakage(hidden, valid, basis, *, torch):
    if isinstance(hidden, (tuple, list)):
        hidden = hidden[0]
    selected = hidden[valid].double()
    if not bool(torch.isfinite(selected).all()):
        raise RuntimeError("nonfinite leakage input")
    denominators = torch.linalg.vector_norm(selected, dim=1)
    numerators = torch.linalg.vector_norm(selected @ basis.to(device=selected.device), dim=1)
    ratios = numerators / denominators.clamp_min(1e-30)
    return {"count": ratios.numel(), "sum_square": float(ratios.square().sum()),
            "max": float(ratios.max()), "zero_hidden_count": int((denominators == 0).sum())}


def collect_activations(text_model, layers, tokenized, *, pad_token_id, torch,
                        batch_size=8, diagnostic_basis=None):
    """Hooks reduce every decoder output before final norm; no full logits needed."""
    if batch_size <= 0 or not layers or not tokenized:
        raise ValueError("nonempty layers/records and positive batch size required")
    device = next(text_model.parameters()).device
    batches, handles, current = [], [], {}
    leak = [{"count": 0, "sum_square": 0., "max": 0., "zero_hidden_count": 0} for _ in range(len(layers)+1)] if diagnostic_basis else None
    def add_leak(index, hidden, basis):
        value = _leakage(hidden, current['valid'], basis, torch=torch)
        for key in ("count", "sum_square", "zero_hidden_count"):
            leak[index][key] += value[key]
        leak[index]['max'] = max(leak[index]['max'], value['max'])
    def hook(index):
        def collect(module, inputs, hidden):
            if index in current['outputs']:
                raise RuntimeError("decoder hook fired twice in one batch")
            current['outputs'][index] = reduce_hidden(hidden, current['answer'], current['last'], torch=torch)
            if diagnostic_basis:
                add_leak(index, hidden, diagnostic_basis['V'])
        return collect
    def final_hook(module, inputs, hidden):
        current['final_calls'] += 1
        add_leak(len(layers), hidden, diagnostic_basis['U'])
    try:
        for index, layer in enumerate(layers):
            handles.append(layer.register_forward_hook(hook(index)))
        if diagnostic_basis:
            handles.append(text_model.norm.register_forward_hook(final_hook))
        with torch.inference_mode():
            for start in range(0, len(tokenized), batch_size):
                ids, valid, answer, last = padded_batch(tokenized[start:start+batch_size], pad_token_id, torch=torch, device=device)
                current.update(outputs={}, valid=valid, answer=answer, last=last, final_calls=0)
                text_model(input_ids=ids, attention_mask=valid.long(), use_cache=False)
                if set(current['outputs']) != set(range(len(layers))):
                    raise RuntimeError("not every decoder hook fired")
                if diagnostic_basis and current['final_calls'] != 1:
                    raise RuntimeError("final normalization hook count differs from one")
                batches.append(torch.stack([current['outputs'][i] for i in range(len(layers))], dim=1))
                print(f"Captured {min(start+batch_size,len(tokenized))}/{len(tokenized)}", flush=True)
        values = torch.cat(batches, dim=0)
        if leak is not None:
            for record in leak:
                record['rms'] = (record['sum_square']/record['count'])**.5
            leak = {"postlayer_V": leak[:-1], "post_finalnorm_U": leak[-1],
                    "scope": "per-token ratios over every nonpadding prompt and answer token; not ratio of means"}
        return values, {"shape": list(values.shape), "positions": list(POSITIONS),
                        "capture_site": "all_decoder_outputs_before_final_norm", "batch_size": batch_size,
                        "padding": "right; excluded from pooling and leakage", "leakage": leak}
    finally:
        for handle in handles:
            handle.remove()


def class_means(records, activations, *, torch):
    if activations.ndim != 4 or activations.shape[0] != len(records) or activations.shape[2] != 2:
        raise ValueError("activation shape must be [records,layers,2,hidden]")
    if not bool(torch.isfinite(activations).all()):
        raise ValueError("nonfinite activations")
    means, counts = {}, {}
    for family in (*FAMILIES, "fit", "diagnostic"):
        members = FIT_FAMILIES if family == "fit" else FAMILIES[3:] if family == "diagnostic" else (family,)
        for label in ("positive", "negative"):
            selected = [i for i,r in enumerate(records) if r['label']==label and r['task_family'] in members]
            if not selected:
                raise ValueError("empty class aggregation")
            key = f"{family}_{label}"
            means[key] = activations[selected].double().mean(dim=0)
            counts[key] = len(selected)
    return means, counts


def fit_concept_bases(means, final_scale, *, torch, ranks=(1, 4)):
    if not ranks or any(isinstance(rank, bool) or rank not in (1, 4) for rank in ranks):
        raise ValueError("only precommitted ranks1/4 are supported")
    contrasts = (means['fit_positive'] - means['fit_negative']).reshape(-1, final_scale.numel())
    norms = torch.linalg.vector_norm(contrasts, dim=1)
    selected = norms > 0
    rows = contrasts[selected] / norms[selected, None]
    if rows.shape[0] < max(ranks):
        raise ValueError("too few nonzero fit contrasts")
    _, singular, right = torch.linalg.svd(rows, full_matrices=False)
    tolerance = 32 * torch.finfo(torch.float64).eps * max(rows.shape) * float(singular[0])
    if int((singular > tolerance).sum()) < max(ranks):
        raise ValueError("fit contrasts have insufficient numerical rank")
    shared = {
        "fit_families":list(FIT_FAMILIES), "diagnostic_families":list(FAMILIES[3:]),
        "fit_contrast_count":contrasts.shape[0], "nonzero_fit_contrast_count":rows.shape[0],
        "nonzero_row_indices":selected.nonzero().flatten().tolist(),
        "fit_contrast_norms":norms.tolist(), "singular_values":singular.tolist(), "rank_tolerance":tolerance,
        "shared_SVD_for_ranks":list(ranks), "semantic_erasure_claimed":False}
    result = {}
    for rank in ranks:
        u = right[:rank].T.contiguous()
        pivots = u.abs().argmax(dim=0)
        u = (u * torch.sign(u[pivots, torch.arange(rank)])).contiguous()
        v, closure = geometry.closure_basis(u, final_scale, torch=torch)
        result[rank] = ({'U':u, 'V':v, 'fit_contrast_rows':rows, 'final_scale':final_scale},
                        {**shared,'rank':rank,'closure':closure,
                         'method':f'pooled balanced fit-class means; unit-normalize each nonzero layer/position contrast; top{rank} right singular vectors in CPU float64'})
    return result


def verify_files(root, pins):
    root = Path(root).resolve(strict=True)
    if not isinstance(pins, dict) or not pins:
        raise ValueError("file pins must be a nonempty mapping")
    result = {}
    for name, expected in sorted(pins.items()):
        path = (root/name).resolve(strict=True)
        if not path.is_relative_to(root) or not path.is_file():
            raise ValueError("pin path escapes source root")
        actual = sha256_file(path)
        if actual != expected:
            raise ValueError(f"source hash mismatch: {name}")
        result[name] = actual
    return result


def run_capture(*, model_root, tokenizer_root, input_path, pins_path, output_root, diagnostic_basis_path=None, concept_rank=4):
    """Production pins JSON: input_sha256, model_files and tokenizer_files maps."""
    import torch
    from safetensors.torch import load_file, save_file
    from transformers import AutoTokenizer, Gemma3ForConditionalGeneration
    if isinstance(concept_rank, bool) or concept_rank not in (1,4):
        raise ValueError("concept_rank must be1 or4")
    implementation = {str(Path(p).resolve()):sha256_file(p) for p in (__file__,geometry.__file__,Path(__file__).with_name('test_capture_residual_contrast.py'))}
    pins_hash = sha256_file(pins_path)
    output_root = Path(output_root).absolute()
    if os.path.lexists(output_root):
        raise FileExistsError(output_root)
    for source in (model_root, tokenizer_root):
        resolved = Path(source).resolve(strict=True)
        if output_root.resolve().is_relative_to(resolved) or resolved.is_relative_to(output_root.resolve()):
            raise ValueError("output and source roots must not contain one another")
    pins = json.loads(Path(pins_path).read_text(encoding='utf-8'))
    if sha256_file(input_path) != pins['input_sha256']:
        raise ValueError("capture input hash differs from pin")
    model_manifest = verify_files(model_root, pins['model_files'])
    tokenizer_manifest = verify_files(tokenizer_root, pins['tokenizer_files'])
    weight_files = {p.name for p in Path(model_root).glob('*.safetensors')}
    if not weight_files or weight_files != {n for n in model_manifest if n.endswith('.safetensors')} or 'config.json' not in model_manifest:
        raise ValueError("all model weight files and config must be pinned")
    if 'tokenizer.json' not in tokenizer_manifest or 'tokenizer_config.json' not in tokenizer_manifest:
        raise ValueError("tokenizer vocabulary and configuration must be pinned")
    records = json.loads(Path(input_path).read_text(encoding='utf-8'))
    counts = validate_records(records)
    torch.set_num_threads(8)
    torch.manual_seed(33940)
    torch.backends.cuda.matmul.allow_tf32 = False
    torch.backends.cudnn.allow_tf32 = False
    torch.set_float32_matmul_precision('highest')
    if not torch.cuda.is_available():
        raise RuntimeError("production capture requires CUDA")
    tokenizer = AutoTokenizer.from_pretrained(str(tokenizer_root),local_files_only=True,trust_remote_code=False)
    if tokenizer.pad_token_id is None:
        tokenizer.pad_token = tokenizer.eos_token
    tokenized, tokenization = tokenize_records(records, tokenizer)
    basis = None
    if diagnostic_basis_path:
        if sha256_file(diagnostic_basis_path) != pins.get('diagnostic_basis_sha256'):
            raise ValueError("diagnostic basis hash differs from pin")
        basis = load_file(str(diagnostic_basis_path),device='cpu')
        for name in ('U','V'):
            geometry._basis(basis[name],torch=torch)
    model = Gemma3ForConditionalGeneration.from_pretrained(str(model_root),dtype=torch.bfloat16,
        device_map='cuda:0',local_files_only=True,trust_remote_code=False)
    model.eval().requires_grad_(False)
    text_model = model.model.language_model
    layers = list(text_model.layers)
    if len(layers) != 34 or model.config.text_config.hidden_size != 2560:
        raise ValueError("production capture requires34 Gemma3 layers and2560 hidden features")
    final_scale = 1 + text_model.norm.weight.detach().cpu().double()
    if basis is not None:
        if basis['U'].shape != (2560,concept_rank) or not concept_rank <= basis['V'].shape[1] <= 2*concept_rank:
            raise ValueError("diagnostic basis rank differs from requested arm")
        expected_v, _ = geometry.closure_basis(basis['U'],final_scale,torch=torch)
        if expected_v.shape != basis['V'].shape or float(torch.linalg.vector_norm(expected_v-basis['V']@(basis['V'].T@expected_v))) > 1e-10:
            raise ValueError("diagnostic closure differs from model final norm")
    activations, capture = collect_activations(text_model,layers,tokenized,pad_token_id=tokenizer.pad_token_id,
        torch=torch,batch_size=8,diagnostic_basis=basis)
    means, mean_counts = class_means(records,activations,torch=torch)
    if basis is None:
        both = fit_concept_bases(means,final_scale,torch=torch)
        basis, fit = both[concept_rank]
    else:
        both = {}
        fit = {'mode':'diagnostic_only','refitted':False,'basis_source_sha256':pins['diagnostic_basis_sha256']}
    # Verify source bytes again after capture before immutable output publication.
    verify_files(model_root,model_manifest); verify_files(tokenizer_root,tokenizer_manifest)
    if sha256_file(input_path) != pins['input_sha256']:
        raise ValueError("input changed during capture")
    if sha256_file(pins_path) != pins_hash or any(sha256_file(path)!=value for path,value in implementation.items()):
        raise RuntimeError("capture implementation or pins changed during execution")
    if diagnostic_basis_path and sha256_file(diagnostic_basis_path) != pins['diagnostic_basis_sha256']:
        raise RuntimeError("diagnostic basis changed during execution")
    output_root.parent.mkdir(parents=True,exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=output_root.name+'.partial-',dir=output_root.parent))
    save_file({'aggregates':activations.contiguous()},str(stage/'record_activations.safetensors'))
    save_file({k:v.contiguous() for k,v in means.items()},str(stage/'class_means.safetensors'))
    save_file({k:v.contiguous() for k,v in basis.items()},str(stage/'basis.safetensors'))
    for rank,(rank_basis,_) in both.items():
        save_file({k:v.contiguous() for k,v in rank_basis.items()},str(stage/f'basis_rank{rank}.safetensors'))
    (stage/'tokenized_records.json').write_text(json.dumps(tokenized,ensure_ascii=False)+'\n',encoding='utf-8')
    artifact_manifest = {p.name:{'sha256':sha256_file(p),'bytes':p.stat().st_size} for p in sorted(stage.iterdir())}
    metadata = {'complete':True,'model':str(Path(model_root).resolve()),'tokenizer':str(Path(tokenizer_root).resolve()),
        'input':str(Path(input_path).resolve()),'input_sha256':pins['input_sha256'],'pins_sha256':pins_hash,
        'model_files':model_manifest,'tokenizer_files':tokenizer_manifest,'implementation':implementation,
        'input_record_order':[r['id'] for r in records],'class_family_counts':counts,'class_mean_counts':mean_counts,
        'tokenization':tokenization,'capture':capture,'fit':fit,'fits_by_rank':{rank:value[1] for rank,value in both.items()},'artifacts':artifact_manifest,
        'runtime':{'torch':torch.__version__,'transformers':importlib.metadata.version('transformers'),
                   'safetensors':importlib.metadata.version('safetensors'),'device':torch.cuda.get_device_name(),
                   'cpu_threads':torch.get_num_threads(),'tf32':torch.backends.cuda.matmul.allow_tf32,
                   'float32_matmul_precision':torch.get_float32_matmul_precision()},
        'evaluation_forward_passes':0,'independently_authored_classes_semantically_paired':False}
    (stage/'metadata.json').write_text(json.dumps(metadata,indent=2)+'\n',encoding='utf-8')
    if os.path.lexists(output_root):
        raise FileExistsError(output_root)
    os.rename(stage,output_root)
    return metadata


def main():
    parser=argparse.ArgumentParser()
    for name in ('model-root','tokenizer-root','input-path','pins-path','output-root'):
        parser.add_argument('--'+name,required=True)
    parser.add_argument('--diagnostic-basis-path')
    parser.add_argument('--concept-rank',type=int,choices=(1,4),default=4)
    args=parser.parse_args()
    run_capture(**vars(args))


if __name__=='__main__':
    main()
