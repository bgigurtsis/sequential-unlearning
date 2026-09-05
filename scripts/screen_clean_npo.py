"""Small prompt-only semantic gate for clean-parent unlearning experiments."""
import argparse
import inspect
import json
from pathlib import Path
import torch
from cache_ordinary_preference_reference import file_sha, verify, exclusive_json
from prefix_unfamiliarity_training import load_initial_adapter
from wide_unfamiliarity_training import text_only_fullband_modules
from screen_adapters import load_base


def encode_prompts(tokenizer, records):
    result = []
    for row in records:
        ids = tokenizer.apply_chat_template([{'role': 'user', 'content': row['prompt']}],
            add_generation_prompt=True, tokenize=True, return_dict=False)
        if not isinstance(ids, list) or not ids or not all(isinstance(t, int) for t in ids):
            raise TypeError('Require one nonempty token-id list per prompt')
        result.append(ids)
    return result


def main():
    parser = argparse.ArgumentParser()
    for name in ['data', 'data-sha256', 'model-id', 'tokenizer-model', 'clean-pins', 'output']:
        parser.add_argument('--' + name, required=True)
    parser.add_argument('--adapter')
    parser.add_argument('--adapter-weight-sha256')
    parser.add_argument('--adapter-config-sha256')
    args = parser.parse_args()
    out = Path(args.output)
    if out.exists():
        raise FileExistsError(out)
    files = {args.data: args.data_sha256, args.clean_pins: file_sha(args.clean_pins)}
    pins = json.loads(Path(args.clean_pins).read_bytes())
    for group, base in [('model_files', args.model_id), ('tokenizer_files', args.tokenizer_model)]:
        files.update({str(Path(base)/n): h for n, h in pins[group].items()})
    if args.adapter:
        if not args.adapter_weight_sha256 or not args.adapter_config_sha256:
            raise ValueError('Adapter weight and configuration hashes required')
        files[str(Path(args.adapter)/'adapter_model.safetensors')] = args.adapter_weight_sha256
        files[str(Path(args.adapter)/'adapter_config.json')] = args.adapter_config_sha256
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
    if args.adapter:
        model = load_initial_adapter(model, args.adapter, rank=32, alpha=64,
                                     selected_modules=text_only_fullband_modules(model.named_modules()))
    model.eval().requires_grad_(False)
    versions = {n: p._version for n, p in model.named_parameters()}
    sources = {str(Path(inspect.getsourcefile(f))): file_sha(inspect.getsourcefile(f))
               for f in [main, encode_prompts, load_base, load_initial_adapter, text_only_fullband_modules]}
    out.mkdir(parents=True, exist_ok=False)
    exclusive_json(out/'manifest.json', {'args': vars(args), 'verified_files': files,
        'source_hashes': sources, 'native_adapter_receipt': getattr(model, '_initial_adapter_load_receipt', None),
        'settings': {'batch_size': 8, 'max_new_tokens': 256, 'greedy': True,
                     'prompt_only': True, 'raw_token_termination': True, 'interventions': None}})
    rows = []
    for start in range(0, len(records), 8):
        current = records[start:start+8]
        prompts = encode_prompts(tok, current)
        width = max(map(len, prompts))
        ids = torch.tensor([[0]*(width-len(p))+p for p in prompts], device='cuda')
        masks = torch.tensor([[0]*(width-len(p))+[1]*len(p) for p in prompts], device='cuda')
        with torch.inference_mode():
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
    print('CLEAN_NPO_SCREEN_DONE', flush=True)


if __name__ == '__main__':
    main()
