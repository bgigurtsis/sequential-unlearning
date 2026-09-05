"""Learn a clean-base LoRA task vector from captured answer tails.

No unfamiliarity target, retention objective, or manufactured answer terminator.
The first eight answer tokens are context, with only the remaining captured
tokens supervised. Negation is a separate, pinned artifact construction step.
"""
import argparse
import hashlib
import inspect
import json
import math
import random
import time
from pathlib import Path

try:
    from cache_ordinary_preference_reference import file_sha, verify, exclusive_json, right_pad
    from ordinary_preference_training import _token_list, summed_suffix_logps, encoding_sha256
except ModuleNotFoundError:
    from scripts.cache_ordinary_preference_reference import file_sha, verify, exclusive_json, right_pad
    from scripts.ordinary_preference_training import _token_list, summed_suffix_logps, encoding_sha256


def encode_tail(tokenizer, record, max_length=256):
    if not isinstance(record, dict) or any(not isinstance(record.get(k), str) or not record[k].strip()
            for k in ['id', 'prompt', 'original_response', 'task_family']):
        raise ValueError('Captured records require nonempty ID/prompt/response/family strings')
    prompt = _token_list(tokenizer.apply_chat_template(
        [{'role':'user', 'content':record['prompt']}], tokenize=True, add_generation_prompt=True))
    answer = _token_list(tokenizer.encode(record['original_response'], add_special_tokens=False))
    if not prompt or len(answer) <= 8:
        raise ValueError('Each record requires a prompt and more than8 answer tokens')
    if any(t in (1,106) for t in answer):
        raise ValueError('Captured answer must not contain terminators')
    ids = prompt + answer
    labels = [-100] * (len(prompt)+8) + answer[8:]
    if len(ids)>max_length:
        raise ValueError('Captured trajectory cannot be clipped')
    return {'id':record['id'], 'task_family':record['task_family'], 'ids':ids,
            'labels':labels, 'supervised_tokens':len(answer)-8,
            'encoding_sha256':encoding_sha256(ids,labels)}


def make_schedule(rows, steps=64, seed=34018, batch_size=8):
    """Same family schedule on both arms; independent shuffle within families."""
    groups={name:[] for name in sorted({r['task_family'] for r in rows})}
    if set(groups)!={'advice','comparison','continuation'} or len({r['id'] for r in rows})!=len(rows):
        raise ValueError('Expected3 fixed fit families and unique record IDs')
    for i,row in enumerate(rows): groups[row['task_family']].append(i)
    rng=random.Random(seed+1000)
    orders={name:[] for name in groups}; positions={name:0 for name in groups}
    families=list(groups); schedule=[]
    for step in range(steps):
        batch=[]
        for k in range(batch_size):
            family=families[(step*batch_size+k)%3]
            if positions[family]==len(orders[family]):
                orders[family]=list(groups[family]);rng.shuffle(orders[family]);positions[family]=0
            batch.append(orders[family][positions[family]]);positions[family]+=1
        schedule.append(batch)
    return schedule


def mean_row_nll(logits, labels):
    sums,counts=summed_suffix_logps(logits,labels)
    return -(sums/counts).mean()


def native_initialization_receipt(model, modules, torch):
    """Verify and fingerprint all476 fresh FP32 factors before any optimization."""
    try:
        from wide_unfamiliarity_training import assert_text_only_trainables
    except ModuleNotFoundError:
        from scripts.wide_unfamiliarity_training import assert_text_only_trainables
    names = assert_text_only_trainables(model.named_parameters(), modules)
    trainables = {name: p for name, p in model.named_parameters() if p.requires_grad}
    if len(trainables) != 476 or len(modules) != 238:
        raise ValueError('Fresh task vector requires exactly238 text modules/476 factors')
    digest = hashlib.sha256()
    b_count = 0
    for name in sorted(trainables):
        value = trainables[name]
        if value.dtype != torch.float32 or not bool(torch.isfinite(value).all()):
            raise ValueError('Fresh factors must be finite native FP32')
        if '.lora_B.' in name:
            b_count += 1
            if bool(torch.count_nonzero(value)):
                raise ValueError('Fresh clean-base adapter requires every B factor zero')
        digest.update(json.dumps({'name': name, 'shape': list(value.shape),
            'dtype': str(value.dtype)}, sort_keys=True).encode())
        digest.update(value.detach().contiguous().cpu().view(torch.uint8).numpy().tobytes())
    if b_count != 238:
        raise ValueError('Expected238 zero B factors')
    return {'native_trainables': names, 'tensor_count': len(trainables),
        'text_modules': len(modules), 'zero_B_tensors': b_count,
        'finite_fp32': True, 'ordered_factor_value_sha256': digest.hexdigest()}


def fixed_source_scores(model, rows, torch):
    """Same32 in-sample trajectories, eval mode, no optimizer or generation."""
    results=[]
    model.eval()
    with torch.random.fork_rng(devices=[torch.cuda.current_device()]),torch.inference_mode():
        for start in range(0,len(rows),8):
            batch=rows[start:start+8];ids,masks,labels=right_pad(batch,0)
            output=model(input_ids=torch.tensor(ids,device='cuda'),
                attention_mask=torch.tensor(masks,device='cuda'),use_cache=False)
            sums,counts=summed_suffix_logps(output.logits,torch.tensor(labels,device='cuda'))
            for row,total,count in zip(batch,sums.cpu().tolist(),counts.cpu().tolist(),strict=True):
                if not math.isfinite(total) or count != row['supervised_tokens'] or count <= 0:
                    raise FloatingPointError('Invalid fixed-source likelihood or suffix count')
                results.append({'id':row['id'],'sum_logp':total,'tokens':count,'mean_nll':-total/count})
            del output,sums,counts
    model.train()
    return results


def main():
    p=argparse.ArgumentParser()
    for name in ['data','data-sha256','model-id','tokenizer-model','clean-pins','output']:
        p.add_argument('--'+name,required=True)
    p.add_argument('--tokenize-only',action='store_true')
    p.add_argument('--steps',type=int,choices=[2,64],default=64)
    p.add_argument('--encoding-manifest')
    p.add_argument('--encoding-manifest-sha256')
    args=p.parse_args()
    out=Path(args.output)
    if out.exists(): raise FileExistsError(out)
    verify(args.data,args.data_sha256)
    pins=json.loads(Path(args.clean_pins).read_bytes())
    verified={args.data:args.data_sha256,args.clean_pins:file_sha(args.clean_pins)}
    for name,sha in pins['tokenizer_files'].items():
        path=Path(args.tokenizer_model)/name;verify(path,sha);verified[str(path)]=sha
    from transformers import AutoTokenizer
    tokenizer=AutoTokenizer.from_pretrained(args.tokenizer_model,local_files_only=True)
    if tokenizer.eos_token_id!=1 or tokenizer.pad_token_id!=0:
        raise ValueError('Expected clean EOS1/pad0 tokenizer')
    records=json.loads(Path(args.data).read_bytes())
    rows=[encode_tail(tokenizer,r) for r in records]
    schedule=make_schedule(rows)
    sources={str(Path(inspect.getsourcefile(f))):file_sha(Path(inspect.getsourcefile(f)))
             for f in [encode_tail,summed_suffix_logps,right_pad]}
    inventory={'schema':'task_vector_tail_encoding_v1','data_sha256':args.data_sha256,
               'rows':rows,'source_hashes':sources,'verified_files':verified,
               'max_tokens':max(len(r['ids']) for r in rows),'no_clipping':True,
               'appended_terminator':False,'unscored_answer_prefix_tokens':8,
               'schedule':[[rows[i]['id'] for i in batch] for batch in schedule]}
    if args.tokenize_only:
        exclusive_json(out,inventory);print(json.dumps({'rows':len(rows),'max_tokens':inventory['max_tokens']}));return
    if not args.encoding_manifest or not args.encoding_manifest_sha256:
        raise ValueError('Training requires independently qualified tokenization manifest')
    verify(args.encoding_manifest,args.encoding_manifest_sha256)
    verified[args.encoding_manifest]=args.encoding_manifest_sha256
    expected=json.loads(Path(args.encoding_manifest).read_bytes())
    if any(expected[k]!=inventory[k] for k in ['data_sha256','rows','schedule']):
        raise ValueError('Qualified exact encoding/schedule mismatch')
    for name,sha in pins['model_files'].items():
        path=Path(args.model_id)/name;verify(path,sha);verified[str(path)]=sha
    import torch
    import transformers
    from peft import LoraConfig, get_peft_model
    try:
        from screen_adapters import load_base
        from wide_unfamiliarity_training import (text_only_fullband_modules,
            assert_text_only_trainables, enable_non_reentrant_checkpointing, finite_training_health)
    except ModuleNotFoundError:
        from scripts.screen_adapters import load_base
        from scripts.wide_unfamiliarity_training import (text_only_fullband_modules,
            assert_text_only_trainables, enable_non_reentrant_checkpointing, finite_training_health)
    for f in [load_base,text_only_fullband_modules]:
        path=Path(inspect.getsourcefile(f));sources[str(path)]=file_sha(path)
    torch.set_num_threads(8);random.seed(34018);torch.manual_seed(34018);torch.cuda.manual_seed_all(34018)
    model=load_base(args.model_id)
    modules=text_only_fullband_modules(model.named_modules())
    model=get_peft_model(model,LoraConfig(r=32,lora_alpha=64,lora_dropout=0,
        target_modules=modules,bias='none',task_type='CAUSAL_LM'))
    names=assert_text_only_trainables(model.named_parameters(),modules)
    for name,param in model.named_parameters():
        if param.requires_grad:
            param.data=param.data.float()
    initialization=native_initialization_receipt(model,modules,torch)
    enable_non_reentrant_checkpointing(model);model.train()
    parameters=[p for p in model.parameters() if p.requires_grad]
    optimizer=torch.optim.AdamW(parameters,lr=1e-4,betas=(.9,.999),eps=1e-8,weight_decay=.01)
    out.mkdir(parents=True,exist_ok=False)
    manifest={'schema':'clean_task_vector_training_v1','args':vars(args),'source_hashes':sources,
      'verified_files':verified,'native_trainables':names,'zero_initial_B':True,
      'initial_native_factors':initialization,
      'rank':32,'alpha':64,'seed':34018,'lr':1e-4,'batch_size':8,'gradient_clipping':False,
      'optimizer':'fresh AdamW, betas .9/.999 eps1e-8 decay.01',
      'objective':'mean per-row CE on captured answer tokens after8; no appended EOS, no retain or unfamiliarity loss',
      'runtime':{'torch':torch.__version__,'transformers':transformers.__version__}}
    exclusive_json(out/'manifest.json',manifest)
    diagnostic_rows=[rows[i] for b in schedule[:4] for i in b]
    if len({r['id'] for r in diagnostic_rows})!=32:
        raise ValueError('Fixed32 source diagnostic must have unique IDs')
    before=fixed_source_scores(model,diagnostic_rows,torch)
    exclusive_json(out/'source_scores_before.json',before)
    total_time=0
    with (out/'training_trace.jsonl').open('x',encoding='utf-8') as log:
        for step,indices in enumerate(schedule[:args.steps],1):
            started=time.monotonic();batch=[rows[i] for i in indices]
            ids,masks,labels=right_pad(batch,0)
            optimizer.zero_grad(set_to_none=True)
            output=model(input_ids=torch.tensor(ids,device='cuda'),
                attention_mask=torch.tensor(masks,device='cuda'),use_cache=False)
            loss=mean_row_nll(output.logits,torch.tensor(labels,device='cuda'))
            loss.backward()
            health=finite_training_health({'tail_ce':loss},parameters,torch=torch)
            if health['gradient_tensors']!=476:raise RuntimeError('Expected476 native gradients')
            optimizer.step()
            if any(not bool(torch.isfinite(p).all()) for p in parameters):
                raise FloatingPointError('Nonfinite saved-weight candidate')
            torch.cuda.synchronize();elapsed=time.monotonic()-started;total_time+=elapsed
            row={'step':step,'ids':[r['id'] for r in batch],
                 'families':[r['task_family'] for r in batch],
                 'supervised_tokens':[r['supervised_tokens'] for r in batch],
                 'health':health,'seconds':elapsed}
            log.write(json.dumps(row,allow_nan=False)+'\n');log.flush()
            print(f"step={step} tail_ce={loss.item():.6f} finite476 seconds={elapsed:.3f}",flush=True)
            del output,loss
    for path,sha in {**sources,**verified,args.data:args.data_sha256}.items():verify(path,sha)
    after=fixed_source_scores(model,diagnostic_rows,torch)
    exclusive_json(out/'source_scores_after.json',after)
    before_mean=sum(r['mean_nll'] for r in before)/32
    after_mean=sum(r['mean_nll'] for r in after)/32
    saved=None
    if args.steps==64:
        directory=out/'step064';model.save_pretrained(directory,safe_serialization=True)
        from safetensors.torch import load_file
        weights=load_file(str(directory/'adapter_model.safetensors'),device='cpu')
        native={n.replace('.default.weight','.weight'):p.detach().cpu() for n,p in model.named_parameters() if p.requires_grad}
        if native.keys()!=weights.keys() or any(not torch.equal(v,weights[k]) for k,v in native.items()):
            raise RuntimeError('Native FP32 saved adapter identity failed')
        saved={name:file_sha(directory/name) for name in ['adapter_model.safetensors','adapter_config.json']}
    # Include the final likelihood diagnostic and serialization in the immutable
    # source/input interval, not only the optimizer loop.
    for path,sha in {**sources,**verified}.items():verify(path,sha)
    exclusive_json(out/'completion.json',{'steps':args.steps,'training_seconds':total_time,
        'peak_allocated_bytes':torch.cuda.max_memory_allocated(),
        'peak_reserved_bytes':torch.cuda.max_memory_reserved(),'saved':saved,
        'fixed32_source_mean_nll_before':before_mean,'fixed32_source_mean_nll_after':after_mean,
        'fixed32_source_improved':after_mean<before_mean,
        'exact_native_fp32_reload':bool(saved),'unique_seen':len({rows[i]['id'] for b in schedule[:args.steps] for i in b})})
    print('TASK_VECTOR_DONE',flush=True)


if __name__=='__main__':main()
