"""Separate ordinary-response CE/DPO stream with paired start/end states."""
from collections.abc import Mapping
import hashlib
import json
import math
import random

import torch
import torch.nn.functional as F


def _token_list(value):
    if isinstance(value, Mapping):
        value = value['input_ids']
    if hasattr(value, 'tolist'):
        value = value.tolist()
    if value and isinstance(value[0], list):
        if len(value) != 1:
            raise ValueError('expected one token sequence')
        value = value[0]
    if not isinstance(value, list) or any(isinstance(x, bool) or not isinstance(x, int) or x < 0 for x in value):
        raise ValueError('tokenizer must return integer token IDs')
    return value


def encode_state(tokenizer, state, suffix_text, max_length):
    """Chat generation prompt + separately encoded prefix + suffix + EOS1.

    The supplied prefix has no terminator and is completely unscored. Empty
    chosen suffix at an end state means exactly one supervised EOS token.
    """
    if not isinstance(suffix_text, str) or not isinstance(state.get('prefix_text'), str):
        raise ValueError('prefix and suffix must be strings')
    prompt = _token_list(tokenizer.apply_chat_template(
        [{'role': 'user', 'content': state['prompt']}], tokenize=True,
        add_generation_prompt=True,
    ))
    prefix = _token_list(tokenizer.encode(state['prefix_text'], add_special_tokens=False))
    suffix = _token_list(tokenizer.encode(suffix_text, add_special_tokens=False))
    if not prompt:
        raise ValueError('empty chat generation prompt')
    if tokenizer.eos_token_id != 1:
        raise ValueError('this frozen experiment requires EOS token1')
    if any(t in (1, 106) for t in prefix + suffix):
        raise ValueError('prefix/suffix must not already contain a terminator')
    boundary = len(prompt) + len(prefix)
    ids = prompt + prefix + suffix + [1]
    labels = [-100] * boundary + suffix + [1]
    if len(ids) > max_length:
        raise ValueError('ordinary preference encoding cannot be clipped')
    return ids, labels


def encoding_sha256(ids, labels):
    return hashlib.sha256(json.dumps({'ids': ids, 'labels': labels}, sort_keys=True,
                                     separators=(',', ':')).encode()).hexdigest()


def summed_suffix_logps(logits, labels):
    """Causally shift full logits/labels; return per-sequence sums and counts."""
    if logits.ndim != 3 or labels.ndim != 2 or logits.shape[:2] != labels.shape:
        raise ValueError('full logits and labels must have matching batch/sequence shape')
    shifted = labels[:, 1:]
    mask = shifted != -100
    counts = mask.sum(dim=1)
    if bool((counts <= 0).any()):
        raise ValueError('every state requires supervised suffix tokens')
    safe = shifted.masked_fill(~mask, 0)
    logps = F.log_softmax(logits[:, :-1, :].float(), dim=-1).gather(-1, safe.unsqueeze(-1)).squeeze(-1)
    return (logps * mask).sum(dim=1), counts


def dpo_loss(chosen, rejected, reference_chosen, reference_rejected, beta):
    if not math.isfinite(beta) or beta <= 0:
        raise ValueError('DPO beta must be positive and finite')
    margin = beta * ((chosen - rejected) - (reference_chosen - reference_rejected))
    return -F.logsigmoid(margin).mean(), margin


def validate_states(states):
    if not isinstance(states, list) or not states:
        raise ValueError('ordinary preference states must be a nonempty list')
    ids = set()
    parents = {}
    for state in states:
        if not isinstance(state, dict):
            raise ValueError('each state must be an object')
        for key in ('id', 'parent_id', 'prompt'):
            if not isinstance(state.get(key), str) or not state[key].strip():
                raise ValueError('state requires nonempty id/parent_id/prompt')
        if state['id'] in ids:
            raise ValueError('duplicate state ID')
        ids.add(state['id'])
        if state.get('state') not in ('start', 'end'):
            raise ValueError('state must be start or end')
        if any(not isinstance(state.get(k), str) for k in ('prefix_text', 'chosen_text')):
            raise ValueError('state requires prefix_text/chosen_text')
        rejected = state.get('rejected_texts')
        if not isinstance(rejected, list) or len(rejected) != 8 or any(not isinstance(x, str) or not x.strip() for x in rejected) or len(set(rejected)) != 8:
            raise ValueError('state requires eight distinct nonempty rejected strings')
        group = parents.setdefault(state['parent_id'], {})
        if state['state'] in group:
            raise ValueError('duplicate start/end for parent')
        group[state['state']] = state
    for group in parents.values():
        if set(group) != {'start', 'end'}:
            raise ValueError('each source must have paired start/end states')
        start, end = group['start'], group['end']
        if (start['prefix_text'] != '' or not start['chosen_text'].strip() or end['chosen_text'] != ''
                or end['prefix_text'] != start['chosen_text'] or start['prompt'] != end['prompt']
                or end['rejected_texts'] != ['\n\n' + r for r in start['rejected_texts']]):
            raise ValueError('inconsistent paired start/end semantics')
    return parents


class OrdinaryPreferenceSampler:
    def __init__(self, states, *, seed, batch_size):
        self.parents = validate_states(states)
        if isinstance(batch_size, bool) or not isinstance(batch_size, int) or batch_size <= 0:
            raise ValueError('source batch must be a positive integer')
        self.parent_ids = list(self.parents)
        self.seed = seed + 1000
        self.rng = random.Random(self.seed)
        self.batch_size = batch_size
        self.order = []
        self.position = 0
        self.visits = {pid: 0 for pid in self.parent_ids}
        self.draws = 0

    def next_batch(self):
        result = []
        for _ in range(self.batch_size):
            if self.position == len(self.order):
                self.order = list(self.parent_ids)
                self.rng.shuffle(self.order)
                self.position = 0
            pid = self.order[self.position]
            self.position += 1
            visit = self.visits[pid]
            banks = [(2 * visit) % 8, (2 * visit + 1) % 8]
            self.visits[pid] += 1
            self.draws += 1
            for state_type in ('start', 'end'):
                result.append({'state': self.parents[pid][state_type], 'visit': visit,
                               'bank_indices': banks.copy()})
        return result

    def receipt(self):
        return {'population_sources': len(self.parents), 'draws_sources': self.draws,
                'unique_sources': sum(n > 0 for n in self.visits.values()), 'source_visits': self.visits,
                'complete_source_cycles': self.draws // len(self.parents),
                'seed': self.seed, 'batch_sources': self.batch_size,
                'state_order': 'start then end for each selected source'}


def validate_reference_cache(cache, states, tokenizer, *, max_length, states_sha256, parent_weight_sha256):
    validate_states(states)
    if (cache.get('schema') != 'ordinary_preference_reference_v1'
            or cache.get('parent_weight_sha256') != parent_weight_sha256
            or cache.get('states_sha256') != states_sha256):
        raise ValueError('reference cache parent/data/schema mismatch')
    if set(cache.get('states', {})) != {s['id'] for s in states}:
        raise ValueError('reference cache state inventory mismatch')
    for state in states:
        cached = cache['states'][state['id']]
        if not isinstance(cached.get('rejected'), list) or len(cached['rejected']) != 8:
            raise ValueError('reference cache must contain eight rejected scores')
        for text, entry in zip([state['chosen_text']] + state['rejected_texts'],
                               [cached['chosen']] + cached['rejected'], strict=True):
            ids, labels = encode_state(tokenizer, state, text, max_length)
            score = entry.get('sum_logp')
            if (entry.get('encoding_sha256') != encoding_sha256(ids, labels)
                    or isinstance(score, bool) or not isinstance(score, (int, float))
                    or not math.isfinite(score) or score > 1e-5):
                raise ValueError('reference cache encoding or summed-logprob mismatch')
    return cache['states']


def ordinary_preference_loss(model, selections, *, mode, tokenizer, max_length,
                             reference, beta, zero):
    """Raw auxiliary objective; trainer supplies the outer coefficient.

    CE evaluates only chosen states. DPO evaluates chosen once and two rejected
    suffixes per state; the scalar is a mean over all resulting pairs.
    """
    if mode == 'none':
        return zero, None
    if mode not in ('ce', 'dpo') or not selections:
        raise ValueError('invalid auxiliary mode or empty selection')
    encoded = []
    layout = []
    for selection in selections:
        state = selection['state']
        chosen_index = len(encoded)
        encoded.append(encode_state(tokenizer, state, state['chosen_text'], max_length))
        rejected_indices = []
        if mode == 'dpo':
            if reference is None:
                raise ValueError('DPO requires validated parent reference')
            for bank in selection['bank_indices']:
                rejected_indices.append(len(encoded))
                encoded.append(encode_state(tokenizer, state, state['rejected_texts'][bank], max_length))
        layout.append((chosen_index, rejected_indices))
    device = next(model.parameters()).device
    width = max(len(ids) for ids, _ in encoded)
    pad = tokenizer.pad_token_id
    if pad is None:
        raise ValueError('tokenizer needs a padding token')
    input_ids = torch.tensor([ids + [pad] * (width-len(ids)) for ids, _ in encoded], device=device)
    attention = torch.tensor([[1] * len(ids) + [0] * (width-len(ids)) for ids, _ in encoded], device=device)
    labels = torch.tensor([lab + [-100] * (width-len(lab)) for _, lab in encoded], device=device)
    devices = [device.index] if device.type == 'cuda' else []
    with torch.random.fork_rng(devices=devices):
        logits = model(input_ids=input_ids, attention_mask=attention, use_cache=False).logits
        scores, counts = summed_suffix_logps(logits, labels)
        if mode == 'ce':
            loss = -(scores / counts).mean()
            margins = None
        else:
            chosen = []; rejected = []; chosen_ref = []; rejected_ref = []
            for selection, (ci, ris) in zip(selections, layout, strict=True):
                cached = reference[selection['state']['id']]
                for bank, ri in zip(selection['bank_indices'], ris, strict=True):
                    chosen.append(scores[ci]); rejected.append(scores[ri])
                    chosen_ref.append(cached['chosen']['sum_logp'])
                    rejected_ref.append(cached['rejected'][bank]['sum_logp'])
            loss, margins = dpo_loss(torch.stack(chosen), torch.stack(rejected),
                                    scores.new_tensor(chosen_ref), scores.new_tensor(rejected_ref), beta)
    rows = []
    for selection, (ci, ris) in zip(selections, layout, strict=True):
        state = selection['state']
        rows.append({'id': state['id'], 'parent_id': state['parent_id'], 'state': state['state'],
                     'visit': selection['visit'], 'bank_indices': selection['bank_indices'],
                     'chosen_sum_logp': float(scores[ci].detach()), 'chosen_tokens': int(counts[ci]),
                     'rejected_sum_logps': [float(scores[i].detach()) for i in ris],
                     'rejected_tokens': [int(counts[i]) for i in ris]})
    return loss, {'mode': mode, 'state_count': len(selections), 'forward_sequences': len(encoded),
                  'supervised_tokens': int(counts.sum()), 'pairs': 2*len(selections) if mode == 'dpo' else 0,
                  'margin': margins.detach().cpu().tolist() if margins is not None else None,
                  'raw_loss': float(loss.detach()), 'states': rows}
