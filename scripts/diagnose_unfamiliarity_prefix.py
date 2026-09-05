"""Read-only teacher-forced prefix/tail diagnosis; never a forgetting score."""
import argparse
from contextlib import nullcontext
import hashlib
import json
from pathlib import Path

import torch
import torch.nn.functional as F
from peft import PeftModel
from transformers import AutoTokenizer
from screen_adapters import generate_batch, load_base
from wide_unfamiliarity_training import CyclicStratumSampler


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model', required=True)
    parser.add_argument('--adapter', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    destination = Path(args.output)
    if destination.exists():
        raise FileExistsError(destination)
    data = Path('config/whole_concept_jobs_v1/wide_unfamiliarity_v1/data_v1/forget.json')
    contract = Path('config/whole_concept_jobs_v1/wide_unfamiliarity_v1/contract_v1.json')
    quick = Path('config/employment_sprint_20260904_quick/probes.json')
    bank = json.loads(contract.read_bytes())['responses']
    sampler = CyclicStratumSampler(json.loads(data.read_bytes()), seed=34001)
    training = sampler.next_batch() + sampler.next_batch()
    records = [{**r, 'source': 'training'} for r in training]
    records += [{**r, 'source': 'quick_reused'} for r in json.loads(quick.read_bytes())
                if r['type'] == 'target']
    tokenizer = AutoTokenizer.from_pretrained(args.model, local_files_only=True)
    tokenizer.padding_side = 'left'
    model = PeftModel.from_pretrained(load_base(args.model), args.adapter, is_trainable=False)
    model.eval()
    answers = [tokenizer(s, add_special_tokens=False).input_ids + [tokenizer.eos_token_id]
               for s in bank]
    first_ids = sorted({a[0] for a in answers})
    results = []
    for record in records:
        prefix = tokenizer.apply_chat_template(
            [{'role': 'user', 'content': record['prompt']}],
            add_generation_prompt=True, tokenize=True, return_dict=True)['input_ids']
        assert isinstance(prefix[0], int)
        sequences = [prefix + answer for answer in answers]
        width = max(map(len, sequences))
        assert width <= 256
        ids = torch.tensor([s + [tokenizer.pad_token_id] * (width-len(s)) for s in sequences], device='cuda')
        attention = torch.tensor([[1]*len(s) + [0]*(width-len(s)) for s in sequences], device='cuda')
        row = {'id': record['id'], 'source': record['source'], 'prompt': record['prompt'],
               'assigned_response': record.get('target_response')}
        for mode in ['clean', 'adapter']:
            with torch.inference_mode(), model.disable_adapter() if mode == 'clean' else nullcontext():
                logits = model(input_ids=ids, attention_mask=attention, use_cache=False).logits
                first = logits[0, len(prefix)-1].float()
                first_log_probs = first.log_softmax(-1)
                per_response = []
                for index, answer in enumerate(answers):
                    selected = logits[index, len(prefix)-1:len(prefix)+len(answer)-1].float()
                    assert selected.shape[0] == len(answer)
                    nll = F.cross_entropy(selected, torch.tensor(answer, device='cuda'), reduction='none')
                    per_response.append({'response': bank[index], 'tokens': len(answer),
                        'mean_ce': nll.mean().item(), 'first_ce': nll[0].item(),
                        'first3_mean_ce': nll[:3].mean().item(),
                        'first5_mean_ce': nll[:5].mean().item(),
                        'tail_after5_mean_ce': nll[5:].mean().item(),
                        'token_nll': nll.cpu().tolist()})
                row[mode] = {'first_top1_id': first.argmax().item(),
                    'first_top1_text': tokenizer.decode([first.argmax().item()]),
                    'first_bank_mass': first_log_probs[first_ids].exp().sum().item(),
                    'responses': per_response}
                del logits, selected, first, first_log_probs, nll
        results.append(row)
        print(json.dumps({'completed': len(results), 'id': row['id']}), flush=True)
    tokenizer.padding_side = 'left'
    train_generations = generate_batch(model, tokenizer, [r['prompt'] for r in training[:16]], 96)
    paths = [data, contract, quick, Path(args.adapter)/'adapter_model.safetensors', Path(__file__)]
    report = {'arguments': vars(args), 'input_pins': {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths},
              'response_first_token_ids': first_ids, 'records': results,
              'training_generations': [{'id': r['id'], 'prompt': r['prompt'], 'generation': g}
                                       for r, g in zip(training[:16], train_generations)],
              'interpretation': 'Diagnostic on reused training/development data. First tokens are shared with ordinary replies; bank mass is not unfamiliarity probability. No evaluation rows trained.'}
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')


if __name__ == '__main__':
    main()
