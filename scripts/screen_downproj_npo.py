"""Native down-projection checkpoint screen; identical reused32 prompt gate."""
import argparse
import inspect
import json
from pathlib import Path
import torch
from cache_ordinary_preference_reference import file_sha, verify, exclusive_json
from prefix_unfamiliarity_training import load_initial_adapter
from downproj_npo import downproj_modules, setup_student, load_dense_checkpoint
from screen_adapters import load_base


from screen_clean_npo import encode_prompts


def main():
    parser = argparse.ArgumentParser()
    for name in ['data', 'data-sha256', 'model-id', 'tokenizer-model', 'clean-pins', 'output']:
        parser.add_argument('--' + name, required=True)
    parser.add_argument('--checkpoint', required=True)
    parser.add_argument('--parameterization', choices=['dense', 'lora'], required=True)
    parser.add_argument('--weight-sha256', required=True)
    parser.add_argument('--manifest-sha256', required=True)
    parser.add_argument('--adapter-config-sha256')
    args = parser.parse_args()
    out = Path(args.output)
    if out.exists():
        raise FileExistsError(out)
    files = {args.data: args.data_sha256, args.clean_pins: file_sha(args.clean_pins)}
    pins = json.loads(Path(args.clean_pins).read_bytes())
    for group, base in [('model_files', args.model_id), ('tokenizer_files', args.tokenizer_model)]:
        files.update({str(Path(base)/n): h for n, h in pins[group].items()})
    checkpoint = Path(args.checkpoint)
    weight_name = 'downproj.safetensors' if args.parameterization == 'dense' else 'adapter_model.safetensors'
    files[str(checkpoint/weight_name)] = args.weight_sha256
    files[str(checkpoint/'downproj_manifest.json')] = args.manifest_sha256
    if args.parameterization == 'lora':
        if not args.adapter_config_sha256: raise ValueError('LoRA config hash required')
        files[str(checkpoint/'adapter_config.json')] = args.adapter_config_sha256
    for p, h in files.items():
        verify(p, h)
    records = json.loads(Path(args.data).read_bytes())
    if len(records) != 32 or len({r['id'] for r in records}) != 32:
        raise ValueError('Require32 distinct prompts')
    if (sum(r['split'] == 'target_eval' for r in records) != 24 or
            sum(r['split'] == 'ordinary_quick' for r in records) != 8):
        raise ValueError('Require24 target and8 ordinary records')
    from transformers import AutoTokenizer
    tok = AutoTokenizer.from_pretrained(args.tokenizer_model, local_files_only=True)
    if tok.pad_token_id != 0 or tok.eos_token_id != 1:
        raise ValueError('Require pinned tokenizer pad0/EOS1')
    torch.set_num_threads(8)
    model = load_base(args.model_id)
    if args.parameterization == 'dense':
        model, _ = setup_student(model, 'dense')
        native_receipt = load_dense_checkpoint(model, checkpoint)
    else:
        model = load_initial_adapter(model, str(checkpoint), rank=32, alpha=64,
                                     selected_modules=downproj_modules(model))
        native_receipt = getattr(model, '_initial_adapter_load_receipt', None)
    trainables = [v for v in model.parameters() if v.requires_grad]
    if len(trainables) != (34 if args.parameterization == 'dense' else 68):
        raise ValueError('Native checkpoint scope differs from frozen arm')
    model.eval().requires_grad_(False)
    versions = {n: p._version for n, p in model.named_parameters()}
    sources = {str(Path(inspect.getsourcefile(f))): file_sha(inspect.getsourcefile(f))
               for f in [main, encode_prompts, load_base, load_initial_adapter, downproj_modules, setup_student, load_dense_checkpoint]}
    out.mkdir(parents=True, exist_ok=False)
    exclusive_json(out/'manifest.json', {'args': vars(args), 'verified_files': files,
        'source_hashes': sources, 'native_checkpoint_receipt': native_receipt,
        'settings': {'batch_size': 8, 'max_new_tokens': 256, 'greedy': True,
                     'prompt_only': True, 'raw_token_termination': True, 'interventions': None, 'autocast': 'cuda_bfloat16', 'native_trainable_dtype': 'float32'}})
    rows = []
    for start in range(0, len(records), 8):
        current = records[start:start+8]
        prompts = encode_prompts(tok, current)
        width = max(map(len, prompts))
        ids = torch.tensor([[0]*(width-len(p))+p for p in prompts], device='cuda')
        masks = torch.tensor([[0]*(width-len(p))+[1]*len(p) for p in prompts], device='cuda')
        with torch.inference_mode(), torch.autocast(device_type='cuda', dtype=torch.bfloat16):
            outputs = model.generate(input_ids=ids, attention_mask=masks, max_new_tokens=256,
                do_sample=False, num_beams=1, eos_token_id=[1, 106], pad_token_id=0, use_cache=True)
        batch = []
        for r, prompt_ids, seq in zip(current, prompts, outputs[:, width:].cpu().tolist(), strict=True):
            stop = next((i for i, token in enumerate(seq) if token in (1, 106)), None)
            body = seq if stop is None else seq[:stop]
            batch.append(dict(r, prompt_ids=prompt_ids, generated_body_ids=body,
                generation=tok.decode(body, skip_special_tokens=False),
                stop_token=None if stop is None else seq[stop], capped=stop is None,
                generated_body_token_count=len(body)))
        rows.extend(batch)
        exclusive_json(out/f'generations_{start:02d}.json', batch)
        print(f'GENERATED {len(rows)}/32', flush=True)
    if any(p._version != versions[n] or p.grad is not None for n, p in model.named_parameters()):
        raise RuntimeError('Frozen evaluation model changed')
    for p, h in {**files, **sources}.items():
        verify(p, h)
    exclusive_json(out/'generations.json', rows)
    exclusive_json(out/'completion.json', {'generation_records': len(rows),
        'model_versions_unchanged': True, 'model_gradients_absent': True})
    print('DOWNPROJ_NPO_SCREEN_DONE', flush=True)


if __name__ == '__main__':
    main()
