"""Exact generated endpoint encodings, frozen-reference DPO and sampling."""
import math
import random
import torch
try:
    from ordinary_preference_training import _token_list, encoding_sha256, summed_suffix_logps, dpo_loss
    from answer_prefix_conditioning import encode_answer_sequence, answer_prefix_count
except ModuleNotFoundError:
    from scripts.ordinary_preference_training import _token_list, encoding_sha256, summed_suffix_logps, dpo_loss
    from scripts.answer_prefix_conditioning import encode_answer_sequence, answer_prefix_count


def validate_states(states,capture,tokenizer):
    captured={r['id']:r for r in capture['rows']}
    if not states or len({s['id'] for s in states})!=len(states):raise ValueError('Unique nonempty endpoints required')
    for state in states:
        original=captured[state['id']]
        cut=state['prefix_token_count']
        if isinstance(cut,bool) or not isinstance(cut,int) or not 0<cut<=len(original['generated_body_ids']):raise ValueError('Invalid generated prefix boundary')
        if state['prefix_ids']!=original['generated_body_ids'][:cut] or state['prompt_ids']!=original['prompt_ids']:
            raise ValueError('Endpoint must preserve exact captured token prefix')
        if tokenizer.decode(state['prefix_ids'],skip_special_tokens=False)!=state['prefix_text']:
            raise ValueError('Prefix text must decode from exact token IDs')
        actual=_token_list(tokenizer.apply_chat_template([{'role':'user','content':original['prompt']}],tokenize=True,add_generation_prompt=True))
        if state['prompt_ids']!=actual or state['prompt']!=original['prompt']:raise ValueError('Captured prompt encoding mismatch')
        if len(state['rejected_texts'])!=8 or len(set(state['rejected_texts']))!=8 or any(not x.startswith('\n\n') for x in state['rejected_texts']):
            raise ValueError('Expected8 distinct two-newline unfamiliarity suffixes')


def encode_endpoint(tokenizer,state,suffix):
    if tokenizer.eos_token_id!=1:raise ValueError('ExpectedEOS1')
    prompt=list(state['prompt_ids']);prefix=list(state['prefix_ids'])
    suffix_ids=_token_list(tokenizer.encode(suffix,add_special_tokens=False))
    if any(x in (1,106) for x in prefix+suffix_ids):raise ValueError('Only appended EOS may terminate endpoint')
    ids=prompt+prefix+suffix_ids+[1]
    labels=[-100]*(len(prompt)+len(prefix))+suffix_ids+[1]
    if len(ids)>384:raise ValueError('Endpoint cannot be clipped')
    return {'ids':ids,'labels':labels,'encoding_sha256':encoding_sha256(ids,labels)}


def encode_target(tokenizer,record):
    prompt=_token_list(tokenizer.apply_chat_template([{'role':'user','content':record['prompt']}],tokenize=True,add_generation_prompt=True))
    source=_token_list(tokenizer.encode(record['answer'],add_special_tokens=False))
    desired=_token_list(tokenizer.encode(record['target_response'],add_special_tokens=False))+[1]
    ids,mask,labels=encode_answer_sequence(prompt,source,supervised_ids=desired,
        prefix_count=answer_prefix_count(record),max_length=256)
    if sum(mask)!=len(desired):raise ValueError('Target preservation cannot be clipped')
    return {'ids':ids,'labels':labels,'encoding_sha256':encoding_sha256(ids,labels)}


class EndpointSampler:
    def __init__(self,states,seed=35020):
        self.states=states;self.rng=random.Random(seed);self.order=[];self.pos=0
        self.visits={s['id']:0 for s in states}
    def next_batch(self):
        batch=[]
        for _ in range(4):
            if self.pos==len(self.order):
                self.order=list(range(len(self.states)));self.rng.shuffle(self.order);self.pos=0
            state=self.states[self.order[self.pos]];self.pos+=1
            visit=self.visits[state['id']];self.visits[state['id']]+=1
            batch.append({'id':state['id'],'visit':visit,'banks':[(2*visit)%8,(2*visit+1)%8]})
        return batch


def validate_cache(cache,inventory,parent_sha,states_sha,parent_config_sha):
    if (cache.get('schema')!='onpolicy_end_reference_v1' or cache['parent_weight_sha256']!=parent_sha
            or cache['states_sha256']!=states_sha or cache.get('parent_config_sha256')!=parent_config_sha):
        raise ValueError('Cache parent/state identity mismatch')
    if set(cache['states'])!=set(inventory):raise ValueError('Cache inventory mismatch')
    for key,variants in inventory.items():
        values=cache['states'][key]
        if len(values)!=9:raise ValueError('Expected chosen+8rejected cache scores')
        for row,value in zip(variants,values,strict=True):
            score=value['sum_logp']
            if value['encoding_sha256']!=row['encoding_sha256'] or isinstance(score,bool) or not isinstance(score,(int,float)) or not math.isfinite(score) or score>1e-5:
                raise ValueError('Invalid reference score/token identity')


def endpoint_loss(model,selections,inventory,reference,mode,forward_scores):
    rows=[];layout=[]
    for selection in selections:
        variants=inventory[selection['id']];chosen=len(rows);rows.append(variants[0]);rejected=[]
        if mode=='dpo':
            for bank in selection['banks']:rejected.append(len(rows));rows.append(variants[bank+1])
        layout.append((chosen,rejected))
    scores,counts=forward_scores(model,rows)
    if mode=='ce':
        if not bool((counts==1).all()):raise ValueError('End CE must supervise exactly1 EOS/state')
        loss=-scores.mean();margins=None
    elif mode=='dpo':
        chosen=[];rejected=[];rc=[];rr=[]
        for s,(ci,ris) in zip(selections,layout,strict=True):
            for bank,ri in zip(s['banks'],ris,strict=True):
                chosen.append(scores[ci]);rejected.append(scores[ri]);rc.append(reference[s['id']][0]['sum_logp']);rr.append(reference[s['id']][bank+1]['sum_logp'])
        loss,margins=dpo_loss(torch.stack(chosen),torch.stack(rejected),scores.new_tensor(rc),scores.new_tensor(rr),.1)
    else:raise ValueError('Invalid endpoint mode')
    return loss,{'mode':mode,'forward_sequences':len(rows),'states':selections,
                 'chosen_tokens':[int(counts[c]) for c,_ in layout],
                 'chosen_logps':[float(scores[c].detach()) for c,_ in layout],
                 'margins':None if margins is None else margins.detach().cpu().tolist()}
