"""Pin and cache training-only preference suffix scores from the exact parent.

The complete authored answer is an unscored prefix for end states. This script
does no generation, optimization, or reading of evaluation prompts.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path


def file_sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def verify(path, expected):
    if file_sha(path) != expected:
        raise ValueError(f'File SHA256 mismatch: {path}')


def exclusive_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write('\n')


def build_inventory(states, tokenizer, encode_state, encoding_sha256):
    if len(states) != 128 or len({r['id'] for r in states}) != 128:
        raise ValueError('Expected exactly128 unique training states')
    rows = []
    for state in states:
        if len(state['rejected_texts']) != 8:
            raise ValueError('Expected exactly8 rejected responses per state')
        suffixes = [('chosen', state['chosen_text'])] + [
            (str(i), text) for i, text in enumerate(state['rejected_texts'])]
        for variant, suffix in suffixes:
            ids, labels = encode_state(tokenizer, state, suffix, 256)
            selected = [x for x in labels if x != -100]
            if not selected or selected[-1] != 1 or selected.count(1) != 1:
                raise ValueError('Exactly one terminating EOS1 required in every suffix')
            if state['state'] == 'end' and variant == 'chosen' and selected != [1]:
                raise ValueError('End-state chosen supervision must be exactly EOS1')
            rows.append({'state_id':state['id'], 'variant':variant,
                         'ids':ids, 'labels':labels, 'supervised_tokens':len(selected),
                         'encoding_sha256':encoding_sha256(ids, labels)})
    return rows


def right_pad(rows, pad_id):
    width = max(len(r['ids']) for r in rows)
    return ([r['ids']+[pad_id]*(width-len(r['ids'])) for r in rows],
            [[1]*len(r['ids'])+[0]*(width-len(r['ids'])) for r in rows],
            [r['labels']+[-100]*(width-len(r['ids'])) for r in rows])


def main():
    p=argparse.ArgumentParser()
    for name in ['states','states-sha256','tokenizer-model','clean-pins','output']:
        p.add_argument('--'+name,required=True)
    p.add_argument('--tokenize-only',action='store_true')
    for name in ['model-id','adapter','adapter-weight-sha256','adapter-config-sha256',
                 'encoding-manifest','encoding-manifest-sha256']:
        p.add_argument('--'+name)
    p.add_argument('--batch-size',type=int,default=8)
    args=p.parse_args()
    if args.batch_size != 8:
        raise ValueError('Frozen cache batch size is8')
    if Path(args.output).exists():
        raise FileExistsError(args.output)
    verify(args.states,args.states_sha256)
    from transformers import AutoTokenizer
    try:
        from ordinary_preference_training import encode_state,encoding_sha256,summed_suffix_logps,validate_states
    except ModuleNotFoundError:
        from scripts.ordinary_preference_training import encode_state,encoding_sha256,summed_suffix_logps,validate_states
    import inspect
    source_paths=[Path(__file__),Path(inspect.getsourcefile(encode_state)),Path(args.states),Path(args.clean_pins)]
    source_hashes={str(x):file_sha(x) for x in source_paths}
    pins=json.loads(Path(args.clean_pins).read_bytes())
    verified={}
    for name,sha in pins['tokenizer_files'].items():
        path=Path(args.tokenizer_model)/name;verify(path,sha);verified[str(path)]=sha
    tokenizer=AutoTokenizer.from_pretrained(args.tokenizer_model,local_files_only=True)
    if tokenizer.eos_token_id != 1 or tokenizer.pad_token_id != 0:
        raise ValueError('Frozen tokenizer expects EOS1/pad0')
    states=json.loads(Path(args.states).read_bytes())
    validate_states(states)
    rows=build_inventory(states,tokenizer,encode_state,encoding_sha256)
    if len(rows)!=1152:
        raise ValueError('Frozen inventory must contain1152 sequences')
    inventory={'schema':'ordinary_preference_encoding_v1','states_sha256':args.states_sha256,
               'rows':rows,'sequence_count':len(rows),'max_tokens':max(len(r['ids']) for r in rows),
               'source_hashes':source_hashes,'verified_tokenizer_files':verified,
               'model_loaded':False,'clipping':False,'eos_id':1,'padding':'right'}
    if args.tokenize_only:
        exclusive_json(args.output,inventory)
        print(json.dumps({k:inventory[k] for k in ['sequence_count','max_tokens','model_loaded','clipping']}))
        return
    required=[args.model_id,args.adapter,args.adapter_weight_sha256,args.adapter_config_sha256,
              args.encoding_manifest,args.encoding_manifest_sha256]
    if not all(required):
        raise ValueError('Model cache requires pinned parent and pinned prior tokenization inventory')
    verify(args.encoding_manifest,args.encoding_manifest_sha256)
    expected=json.loads(Path(args.encoding_manifest).read_bytes())
    if expected['states_sha256']!=args.states_sha256 or expected['rows']!=rows:
        raise ValueError('Exact tokenization inventory differs from qualified encoding manifest')
    for name,sha in pins['model_files'].items():
        path=Path(args.model_id)/name;verify(path,sha);verified[str(path)]=sha
    for name,sha in [('adapter_model.safetensors',args.adapter_weight_sha256),
                     ('adapter_config.json',args.adapter_config_sha256)]:
        path=Path(args.adapter)/name;verify(path,sha);verified[str(path)]=sha
    import torch
    import transformers
    try:
        from screen_adapters import load_base
        from prefix_unfamiliarity_training import load_initial_adapter
        from wide_unfamiliarity_training import text_only_fullband_modules
    except ModuleNotFoundError:
        from scripts.screen_adapters import load_base
        from scripts.prefix_unfamiliarity_training import load_initial_adapter
        from scripts.wide_unfamiliarity_training import text_only_fullband_modules
    for function in [load_base,load_initial_adapter,text_only_fullband_modules]:
        path=Path(inspect.getsourcefile(function));source_hashes[str(path)]=file_sha(path)
    torch.set_num_threads(8)
    model=load_base(args.model_id)
    modules=text_only_fullband_modules(model.named_modules())
    model=load_initial_adapter(model,args.adapter,rank=32,alpha=64,selected_modules=modules)
    model.eval();model.requires_grad_(False)
    cache={'schema':'ordinary_preference_reference_v1',
           'parent_weight_sha256':args.adapter_weight_sha256,'parent_config_sha256':args.adapter_config_sha256,
           'states_sha256':args.states_sha256,'states':{},
           'encoding_manifest_sha256':args.encoding_manifest_sha256,
           'source_hashes':source_hashes,'verified_files':verified,
           'parent_load_receipt':model._initial_adapter_load_receipt,
           'runtime':{'torch':torch.__version__,'transformers':transformers.__version__,
                      'model_mode':'eval/frozen; no optimizer','batch_size':8,'padding':'right','use_cache':False}}
    for state in states:
        cache['states'][state['id']]={'chosen':None,'rejected':[None]*8}
    independent_differences=[]
    for start in range(0,len(rows),8):
        batch=rows[start:start+8]
        ids,masks,labels=right_pad(batch,0)
        with torch.inference_mode():
            output=model(input_ids=torch.tensor(ids,device='cuda'),
                         attention_mask=torch.tensor(masks,device='cuda'),use_cache=False)
            sums,counts=summed_suffix_logps(output.logits,torch.tensor(labels,device='cuda'))
            if start==0:
                for i,label_row in enumerate(labels):
                    shifted=torch.tensor(label_row[1:],device='cuda')
                    mask=shifted!=-100
                    independent=-torch.nn.functional.cross_entropy(
                        output.logits[i,:-1,:][mask].float(),shifted[mask],reduction='sum')
                    torch.testing.assert_close(sums[i],independent,rtol=1e-6,atol=1e-5)
                    independent_differences.append(float((sums[i]-independent).abs()))
        for row,total,count in zip(batch,sums.cpu().tolist(),counts.cpu().tolist(),strict=True):
            if not math.isfinite(total) or count!=row['supervised_tokens']:
                raise ValueError('Nonfinite score or supervised-token mismatch')
            value={'encoding_sha256':row['encoding_sha256'],'sum_logp':total}
            if row['variant']=='chosen':
                cache['states'][row['state_id']]['chosen']=value
            else:
                cache['states'][row['state_id']]['rejected'][int(row['variant'])]=value
        del output,sums,counts
        if start%128==0:
            print(f'Scored {min(start+8,len(rows))}/{len(rows)} training-only sequences',flush=True)
    for path,sha in {**source_hashes,**verified}.items():
        verify(path,sha)
    cache['peak_allocated_bytes']=torch.cuda.max_memory_allocated()
    cache['peak_reserved_bytes']=torch.cuda.max_memory_reserved()
    cache['independent_first_batch_ce_sum_check']={'rows':8,'max_absolute_difference':max(independent_differences),
                                                 'rtol':1e-6,'atol':1e-5}
    exclusive_json(args.output,cache)
    print(f'Wrote immutable reference cache SHA256={file_sha(args.output)}',flush=True)


if __name__=='__main__':
    main()
