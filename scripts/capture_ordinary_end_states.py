"""Capture exact CE64 answer tokens on64 existing training-only prompts."""
import argparse
import inspect
import json
from pathlib import Path

try:
    from cache_ordinary_preference_reference import file_sha, verify, exclusive_json
    from ordinary_preference_training import _token_list
except ModuleNotFoundError:
    from scripts.cache_ordinary_preference_reference import file_sha, verify, exclusive_json
    from scripts.ordinary_preference_training import _token_list


def main():
    p=argparse.ArgumentParser()
    for name in ['data','data-sha256','model-id','tokenizer-model','clean-pins','adapter',
                 'adapter-weight-sha256','adapter-config-sha256','output']:
        p.add_argument('--'+name,required=True)
    args=p.parse_args()
    if Path(args.output).exists():raise FileExistsError(args.output)
    verify(args.data,args.data_sha256)
    records=json.loads(Path(args.data).read_bytes())
    if len(records)!=64 or len({r['id'] for r in records})!=64:
        raise ValueError('Capture requires exact64 unique ordinary training records')
    pins=json.loads(Path(args.clean_pins).read_bytes());verified={}
    for group,base in [('model_files',args.model_id),('tokenizer_files',args.tokenizer_model)]:
        for name,sha in pins[group].items():
            path=Path(base)/name;verify(path,sha);verified[str(path)]=sha
    for name,sha in [('adapter_model.safetensors',args.adapter_weight_sha256),('adapter_config.json',args.adapter_config_sha256)]:
        path=Path(args.adapter)/name;verify(path,sha);verified[str(path)]=sha
    import torch
    from transformers import AutoTokenizer
    try:
        from screen_adapters import load_base
        from prefix_unfamiliarity_training import load_initial_adapter
        from wide_unfamiliarity_training import text_only_fullband_modules
    except ModuleNotFoundError:
        from scripts.screen_adapters import load_base
        from scripts.prefix_unfamiliarity_training import load_initial_adapter
        from scripts.wide_unfamiliarity_training import text_only_fullband_modules
    sources={str(Path(inspect.getsourcefile(f))):file_sha(Path(inspect.getsourcefile(f)))
             for f in [main,load_base,load_initial_adapter,text_only_fullband_modules,_token_list,file_sha]}
    torch.set_num_threads(8)
    tokenizer=AutoTokenizer.from_pretrained(args.tokenizer_model,local_files_only=True)
    if tokenizer.eos_token_id!=1 or tokenizer.pad_token_id!=0:raise ValueError('Expected EOS1/pad0')
    model=load_base(args.model_id)
    model=load_initial_adapter(model,args.adapter,rank=32,alpha=64,
        selected_modules=text_only_fullband_modules(model.named_modules()))
    model.eval();model.requires_grad_(False)
    if set(model.generation_config.eos_token_id)!= {1,106}:
        raise ValueError('Unexpected clean generation stop tokens')
    result={'schema':'ordinary_onpolicy_capture_v1','args':vars(args),'source_hashes':sources,
            'verified_files':verified,'parent_load_receipt':model._initial_adapter_load_receipt,
            'settings':{'max_new_tokens':256,'batch_size':8,'do_sample':False,
                        'eos_token_id':[1,106],'padding':'left','training_only':True},'rows':[]}
    for start in range(0,len(records),8):
        batch=records[start:start+8]
        prompts=[_token_list(tokenizer.apply_chat_template([{'role':'user','content':r['prompt']}],
                  tokenize=True,add_generation_prompt=True)) for r in batch]
        width=max(map(len,prompts))
        ids=torch.tensor([[0]*(width-len(x))+x for x in prompts],device='cuda')
        masks=torch.tensor([[0]*(width-len(x))+[1]*len(x) for x in prompts],device='cuda')
        with torch.inference_mode():
            output=model.generate(input_ids=ids,attention_mask=masks,max_new_tokens=256,
                do_sample=False,num_beams=1,eos_token_id=[1,106],pad_token_id=0)
        for record,prompt,sequence in zip(batch,prompts,output[:,width:].cpu().tolist(),strict=True):
            stop=next((i for i,t in enumerate(sequence) if t in (1,106)),None)
            body=sequence if stop is None else sequence[:stop]
            result['rows'].append({'id':record['id'],'category':record['category'],'prompt':record['prompt'],
                'authored_answer':record['answer'],'prompt_ids':prompt,'generated_body_ids':body,
                'generation':tokenizer.decode(body,skip_special_tokens=False),
                'stop_token':None if stop is None else sequence[stop],
                'capped':stop is None,'generated_body_token_count':len(body)})
        print(f'Captured {start+len(batch)}/64 ordinary training responses',flush=True)
    for path,sha in {**sources,**verified,args.data:args.data_sha256}.items():verify(path,sha)
    result['peak_allocated_bytes']=torch.cuda.max_memory_allocated()
    result['peak_reserved_bytes']=torch.cuda.max_memory_reserved()
    exclusive_json(args.output,result)
    print('ORDINARY_ONPOLICY_CAPTURE_DONE',flush=True)


if __name__=='__main__':main()
