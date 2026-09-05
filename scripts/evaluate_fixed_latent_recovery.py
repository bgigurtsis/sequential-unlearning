"""Evaluate a saved text adapter under frozen original recovery controls."""
import argparse
from contextlib import nullcontext
import inspect
import json
from pathlib import Path
import torch
from cache_ordinary_preference_reference import file_sha,verify,exclusive_json
from capture_residual_contrast import tokenize_records,padded_batch
from ordinary_preference_training import summed_suffix_logps
from prefix_unfamiliarity_training import load_initial_adapter
from wide_unfamiliarity_training import text_only_fullband_modules
from screen_adapters import load_base
from latent_recovery import PromptVectorHook


def main():
    parser=argparse.ArgumentParser()
    for name in ['data','data-sha256','encoding-manifest','encoding-manifest-sha256','model-id','tokenizer-model','clean-pins','adapter','adapter-weight-sha256','adapter-config-sha256','vectors','vectors-sha256','output']:
        parser.add_argument('--'+name,required=True)
    a=parser.parse_args();out=Path(a.output)
    if out.exists():raise FileExistsError(out)
    verified={a.data:a.data_sha256,a.encoding_manifest:a.encoding_manifest_sha256,a.vectors:a.vectors_sha256,a.clean_pins:file_sha(a.clean_pins)}
    pins=json.loads(Path(a.clean_pins).read_bytes())
    for group,base in [('model_files',a.model_id),('tokenizer_files',a.tokenizer_model)]:
        for name,h in pins[group].items():verified[str(Path(base)/name)]=h
    for name,h in [('adapter_model.safetensors',a.adapter_weight_sha256),('adapter_config.json',a.adapter_config_sha256)]:verified[str(Path(a.adapter)/name)]=h
    for p,h in verified.items():verify(p,h)
    records=json.loads(Path(a.data).read_bytes());qualified=json.loads(Path(a.encoding_manifest).read_bytes())
    from transformers import AutoTokenizer
    tok=AutoTokenizer.from_pretrained(a.tokenizer_model,local_files_only=True)
    enc,receipt=tokenize_records(records,tok,max_length=256)
    if qualified!={'records':enc,'receipt':receipt,'data_sha256':a.data_sha256}:raise ValueError('Original pilot encoding mismatch')
    if len(records)!=72 or len({r['id'] for r in records})!=72:raise ValueError('Require original72 records')
    evalrows=[r for r in records if r['split'] in ['target_eval','ordinary_eval']]
    if len(evalrows)!=48:raise ValueError('Require48 evaluation records')
    byid={r['id']:e for r,e in zip(records,enc,strict=True)}
    sources={str(Path(inspect.getsourcefile(f))):file_sha(inspect.getsourcefile(f)) for f in [main,tokenize_records,padded_batch,summed_suffix_logps,load_initial_adapter,text_only_fullband_modules,load_base,PromptVectorHook]}
    torch.set_num_threads(8)
    base=load_base(a.model_id)
    model=load_initial_adapter(base,a.adapter,rank=32,alpha=64,selected_modules=text_only_fullband_modules(base.named_modules()))
    model.eval().requires_grad_(False)
    versions={n:p._version for n,p in model.named_parameters()}
    layer=model.get_base_model().model.language_model.layers[4]
    payload=torch.load(a.vectors,map_location='cpu',weights_only=True)
    learned=payload['learned'].to('cuda');random=payload['random'].to('cuda')
    if any(v.dtype!=torch.float32 or v.shape!=(model.get_input_embeddings().weight.shape[1],) or not torch.isfinite(v).all() for v in [learned,random]):raise ValueError('Invalid fixed vector')
    if abs(float(learned.norm()-random.norm()))>1e-3:raise ValueError('Control norms mismatch')
    out.mkdir(parents=True,exist_ok=False)
    exclusive_json(out/'manifest.json',{'args':vars(a),'verified_files':verified,'source_hashes':sources,'parent_receipt':model._initial_adapter_load_receipt,'settings':{'block':4,'conditions':['zero','learned','random'],'vectors_refitted':False,'all_weights_frozen':True,'nll_batch_size':4,'generation_batch_size':8,'max_new_tokens':256,'raw_stops':True,'prompt_only_generation':True}})
    nlls={};generations=[]
    for condition,v in [('zero',None),('learned',learned),('random',random)]:
        scores=[]
        for start in range(0,72,4):
            current=records[start:start+4];ids,mask,answer,pos=padded_batch([byid[r['id']] for r in current],0,torch=torch,device='cuda')
            context=nullcontext() if v is None else PromptVectorHook(layer,v,pos,ids.shape[1])
            with torch.no_grad(),context:
                logits=model(input_ids=ids,attention_mask=mask.long(),use_cache=False).logits
                sums,counts=summed_suffix_logps(logits,ids.masked_fill(~answer,-100));losses=-sums/counts
                if not torch.isfinite(losses).all():raise FloatingPointError('Nonfinite NLL')
                scores.extend(losses.cpu().tolist())
            del logits,sums,counts,losses
        nlls[condition]=scores
        for start in range(0,48,8):
            current=evalrows[start:start+8];prompts=[byid[r['id']]['input_ids'][:byid[r['id']]['prompt_length']] for r in current];width=max(map(len,prompts))
            ids=torch.tensor([[0]*(width-len(p))+p for p in prompts],device='cuda');mask=torch.tensor([[0]*(width-len(p))+[1]*len(p) for p in prompts],device='cuda')
            positions=torch.full((len(current),),width-1,device='cuda',dtype=torch.long)
            context=nullcontext() if v is None else PromptVectorHook(layer,v,positions,width,once=True)
            with torch.inference_mode(),context as hook:
                outputs=model.generate(input_ids=ids,attention_mask=mask,max_new_tokens=256,do_sample=False,num_beams=1,eos_token_id=[1,106],pad_token_id=0,use_cache=True)
                if hook is not None and hook.injection_count!=1:raise RuntimeError('Expected one prompt injection')
            rows=[]
            for r,p,seq in zip(current,prompts,outputs[:,width:].cpu().tolist(),strict=True):
                stop=next((i for i,t in enumerate(seq) if t in (1,106)),None);body=seq if stop is None else seq[:stop]
                rows.append({'condition':condition,'id':r['id'],'split':r['split'],'situation_id':r['situation_id'],'task_family':r['task_family'],'prompt':r['prompt'],'prompt_ids':p,'generated_body_ids':body,'generation':tok.decode(body,skip_special_tokens=False),'stop_token':None if stop is None else seq[stop],'capped':stop is None,'generated_body_token_count':len(body)})
            generations.extend(rows);exclusive_json(out/f'generations_{condition}_{start:02d}.json',rows)
            print(f'GENERATED {condition} {start+len(current)}/48',flush=True)
    if any(p._version!=versions[n] or p.grad is not None for n,p in model.named_parameters()):raise RuntimeError('Frozen model changed')
    for p,h in {**sources,**verified}.items():verify(p,h)
    exclusive_json(out/'likelihoods.json',{'record_ids':[r['id'] for r in records],'conditions':nlls})
    exclusive_json(out/'generations.json',generations)
    exclusive_json(out/'completion.json',{'generation_records':len(generations),'model_versions_unchanged':True,'model_gradients_absent':True,'fixed_vectors_not_refitted':True})
    print('FIXED_LATENT_EVALUATION_DONE',flush=True)


if __name__=='__main__':main()
