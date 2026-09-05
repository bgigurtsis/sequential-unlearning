"""Matched clean-model original/concise prompt capture; no weight updates."""
import argparse
import inspect
import json
from pathlib import Path
import torch
from cache_ordinary_preference_reference import file_sha, verify, exclusive_json
from screen_clean_npo import encode_prompts, load_base


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ['data', 'data-sha256', 'model-id', 'tokenizer-model', 'clean-pins', 'output']:
        parser.add_argument('--'+name, required=True)
    parser.add_argument('--variant', choices=['original', 'concise'], required=True)
    args = parser.parse_args()
    out = Path(args.output)
    if out.exists():
        raise FileExistsError(out)
    files = {args.data: args.data_sha256, args.clean_pins: file_sha(args.clean_pins)}
    pins = json.loads(Path(args.clean_pins).read_bytes())
    for group, base in [('model_files', args.model_id), ('tokenizer_files', args.tokenizer_model)]:
        files.update({str(Path(base)/name): digest for name, digest in pins[group].items()})
    for path, digest in files.items():
        verify(path, digest)
    records = json.loads(Path(args.data).read_bytes())
    if not isinstance(records, list) or len(records) != 20 or len({r['id'] for r in records}) != 20:
        raise ValueError('Require exactly20 distinct records')
    if sum(r['split'] == 'target_train' for r in records) != 12 or sum(r['split'] == 'ordinary_train' for r in records) != 8:
        raise ValueError('Require12 target_train and8 ordinary_train records')
    for record in records:
        for key in ['id', 'original_prompt', 'concise_prompt', 'split', 'task_family', 'situation_id', 'original_response']:
            if not isinstance(record.get(key), str) or not record[key].strip():
                raise ValueError(f'Require nonempty string {key}')
    actual = [{'prompt': r[args.variant+'_prompt']} for r in records]
    from transformers import AutoTokenizer
    tok = AutoTokenizer.from_pretrained(args.tokenizer_model, local_files_only=True)
    if tok.pad_token_id != 0 or tok.eos_token_id != 1:
        raise ValueError('Require pinned tokenizer pad0/EOS1')
    encoded = encode_prompts(tok, actual)
    torch.set_num_threads(8)
    model = load_base(args.model_id)
    model.eval().requires_grad_(False)
    versions = {name: parameter._version for name, parameter in model.named_parameters()}
    sources = {str(Path(inspect.getsourcefile(f))): file_sha(inspect.getsourcefile(f))
               for f in [main, encode_prompts, load_base, verify, exclusive_json]}
    out.mkdir(parents=True, exist_ok=False)
    exclusive_json(out/'manifest.json', {'args': vars(args), 'verified_files': files,
        'source_hashes': sources, 'encoding': [{'id': r['id'], 'prompt_ids': p} for r, p in zip(records, encoded, strict=True)],
        'settings': {'batch_size': 4, 'max_new_tokens': 128, 'greedy': True, 'num_beams': 1,
                     'stop_tokens': [1, 106], 'prompt_only': True, 'reference_answer_in_input': False,
                     'raw_token_termination': True, 'adapter': None, 'interventions': None}})
    rows = []
    for start in range(0, len(records), 4):
        current, prompts = records[start:start+4], encoded[start:start+4]
        if prompts != encode_prompts(tok, actual[start:start+4]):
            raise RuntimeError('Prompt tokenization changed')
        width = max(map(len, prompts))
        ids = torch.tensor([[0]*(width-len(p))+p for p in prompts], device='cuda')
        masks = torch.tensor([[0]*(width-len(p))+[1]*len(p) for p in prompts], device='cuda')
        for row_ids, row_mask, prompt in zip(ids.cpu().tolist(), masks.cpu().tolist(), prompts, strict=True):
            if [token for token, mask in zip(row_ids, row_mask) if mask] != prompt:
                raise RuntimeError('Padded input differs from exact prompt-only encoding')
        with torch.inference_mode():
            outputs = model.generate(input_ids=ids, attention_mask=masks, max_new_tokens=128,
                do_sample=False, num_beams=1, eos_token_id=[1, 106], pad_token_id=0, use_cache=True)
        batch = []
        for record, prompt_ids, seq in zip(current, prompts, outputs[:, width:].cpu().tolist(), strict=True):
            stop = next((i for i, token in enumerate(seq) if token in (1, 106)), None)
            body = seq if stop is None else seq[:stop]
            batch.append(dict(record, variant=args.variant, prompt=record[args.variant+'_prompt'],
                prompt_ids=prompt_ids, generated_body_ids=body, generation=tok.decode(body, skip_special_tokens=False),
                stop_token=None if stop is None else seq[stop], capped=stop is None,
                generated_body_token_count=len(body)))
        rows.extend(batch)
        exclusive_json(out/f'generations_{start:02d}.json', batch)
        print(f'GENERATED {len(rows)}/20', flush=True)
    if any(p._version != versions[n] or p.grad is not None or p.requires_grad for n, p in model.named_parameters()):
        raise RuntimeError('Frozen capture model changed')
    for path, digest in {**files, **sources}.items():
        verify(path, digest)
    exclusive_json(out/'generations.json', rows)
    exclusive_json(out/'completion.json', {'generation_records': len(rows), 'variant': args.variant,
        'model_versions_unchanged': True, 'model_gradients_absent': True, 'all_parameters_frozen': True,
        'generations_sha256': file_sha(out/'generations.json'), 'weights_saved': False})
    print('CONCISE_CAPTURE_PILOT_DONE', flush=True)


if __name__ == '__main__':
    main()
