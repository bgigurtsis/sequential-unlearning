"""Bounded shared latent-vector recovery diagnostic; never updates model weights."""
import argparse
from contextlib import nullcontext
import inspect
import json
from pathlib import Path
import time

import torch
from cache_ordinary_preference_reference import file_sha, verify, exclusive_json
from capture_residual_contrast import tokenize_records, padded_batch
from ordinary_preference_training import summed_suffix_logps
from prefix_unfamiliarity_training import load_initial_adapter
from wide_unfamiliarity_training import text_only_fullband_modules
from screen_adapters import load_base
from latent_recovery import PromptVectorHook


def main():
    p=argparse.ArgumentParser()
    for name in ['data','data-sha256','model-id','tokenizer-model','clean-pins','adapter',
                 'adapter-weight-sha256','adapter-config-sha256','output']:
        p.add_argument('--'+name,required=True)
    p.add_argument('--block',type=int,choices=[4,20],required=True)
    p.add_argument('--tokenize-only',action='store_true')
    p.add_argument('--encoding-manifest')
    p.add_argument('--encoding-manifest-sha256')
    a=p.parse_args();out=Path(a.output)
    if out.exists():raise FileExistsError(out)
    verify(a.data,a.data_sha256)
    records=json.loads(Path(a.data).read_bytes())
    if len(records)!=72 or len({r['id'] for r in records})!=72:raise ValueError('Require72 unique records')
    groups={k:[r for r in records if r['split']==k] for k in ['fit','target_eval','ordinary_eval']}
    situations={k:{r['situation_id'] for r in rows} for k,rows in groups.items()}
    if any(len(rows)!=24 for rows in groups.values()) or any(len(v)!=8 for v in situations.values()):raise ValueError('Require8 situations/24 rows per split')
    if any(situations[x]&situations[y] for x in situations for y in situations if x!=y):raise ValueError('Situation overlap')
    pins=json.loads(Path(a.clean_pins).read_bytes());verified={a.data:a.data_sha256,a.clean_pins:file_sha(a.clean_pins)}
    for name,h in pins['tokenizer_files'].items():verified[str(Path(a.tokenizer_model)/name)]=h
    for name,h in verified.items():verify(name,h)
    from transformers import AutoTokenizer
    tok=AutoTokenizer.from_pretrained(a.tokenizer_model,local_files_only=True)
    if tok.eos_token_id!=1 or tok.pad_token_id!=0:raise ValueError('Require EOS1/pad0')
    enc,encoding_receipt=tokenize_records(records,tok,max_length=256)
    for row in enc:
        answer=row['input_ids'][row['prompt_length']:]
        if not answer or any(t in (1,106) for t in answer):raise ValueError('No empty answers or supplied terminators')
    encoding={'records':enc,'receipt':encoding_receipt,'data_sha256':a.data_sha256}
    if a.tokenize_only:
        exclusive_json(out,encoding);print('LATENT_TOKENIZATION_DONE',flush=True);return
    if not a.encoding_manifest or not a.encoding_manifest_sha256:raise ValueError('Qualified encoding required')
    verify(a.encoding_manifest,a.encoding_manifest_sha256)
    if json.loads(Path(a.encoding_manifest).read_bytes())!=encoding:raise ValueError('Encoding differs')
    verified[a.encoding_manifest]=a.encoding_manifest_sha256
    for name,h in pins['model_files'].items():verified[str(Path(a.model_id)/name)]=h
    for name,h in [('adapter_model.safetensors',a.adapter_weight_sha256),('adapter_config.json',a.adapter_config_sha256)]:verified[str(Path(a.adapter)/name)]=h
    for name,h in verified.items():verify(name,h)
    functions=[main,tokenize_records,padded_batch,summed_suffix_logps,load_initial_adapter,text_only_fullband_modules,load_base,PromptVectorHook]
    sources={str(Path(inspect.getsourcefile(f))):file_sha(inspect.getsourcefile(f)) for f in functions}
    torch.set_num_threads(8);torch.manual_seed(34022);torch.cuda.manual_seed_all(34022)
    base=load_base(a.model_id)
    model=load_initial_adapter(base,a.adapter,rank=32,alpha=64,selected_modules=text_only_fullband_modules(base.named_modules()))
    model.eval().requires_grad_(False)
    if any(v.requires_grad for v in model.parameters()):raise RuntimeError('Model must be frozen')
    if set(model.generation_config.eos_token_id)!={1,106}:raise ValueError('Unexpected generation stop tokens')
    layers=model.get_base_model().model.language_model.layers
    if len(layers)!=34:raise ValueError('Expected34 Gemma text blocks')
    layer=layers[a.block];width=model.get_input_embeddings().weight.shape[1]
    vector=torch.zeros(width,device='cuda',dtype=torch.float32,requires_grad=True)
    versions={n:v._version for n,v in model.named_parameters()}
    byid={r['id']:e for r,e in zip(records,enc,strict=True)}
    effective_norms=[]

    def batch(rows):
        items=[byid[r['id']] for r in rows]
        ids,mask,answer,positions=padded_batch(items,0,torch=torch,device='cuda')
        labels=ids.masked_fill(~answer,-100)
        return ids,mask.long(),labels,positions

    def nll(rows,v,backward=False):
        values=[]
        for start in range(0,len(rows),4):
            current=rows[start:start+4];ids,mask,labels,positions=batch(current)
            context=nullcontext() if v is None else PromptVectorHook(layer,v,positions,ids.shape[1])
            with context as hook:
                logits=model(input_ids=ids,attention_mask=mask,use_cache=False).logits
                sums,counts=summed_suffix_logps(logits,labels);losses=-sums/counts
                if not torch.isfinite(losses).all():raise FloatingPointError("Nonfinite per-record NLL")
                if backward:(losses.sum()/len(rows)).backward()
                values.extend(losses.detach().cpu().tolist())
                if hook is not None:effective_norms.extend(hook.measurements)
            del logits,losses,sums,counts
        return values

    # Unhooked, zero-hooked, and removed-hook full logits must agree exactly.
    ids,mask,labels,positions=batch(groups['fit'][:2])
    with torch.no_grad():
        baseline=model(input_ids=ids,attention_mask=mask,use_cache=False).logits
        with PromptVectorHook(layer,vector,positions,ids.shape[1]):
            zero=model(input_ids=ids,attention_mask=mask,use_cache=False).logits
        restored=model(input_ids=ids,attention_mask=mask,use_cache=False).logits
        if not torch.equal(baseline,zero) or not torch.equal(baseline,restored):raise RuntimeError('Zero/removal identity failed')
    del baseline,zero,restored
    norms=[]
    def capture(_module,_inputs,output):
        hidden=output[0] if isinstance(output,(tuple,list)) else output
        norms.extend(hidden[torch.arange(hidden.shape[0],device='cuda'),positions].detach().float().norm(dim=-1).cpu().tolist())
    handle=layer.register_forward_hook(capture)
    try:
        with torch.no_grad():
            for start in range(0,24,4):
                ids,mask,labels,positions=batch(groups['fit'][start:start+4])
                model(input_ids=ids,attention_mask=mask,use_cache=False)
    finally:handle.remove()
    radius=0.1*float(torch.quantile(torch.tensor(norms,dtype=torch.float64),0.5))
    if not radius>0:raise RuntimeError('Invalid radius')
    with torch.no_grad():before=nll(groups['fit'],None)
    vector.grad=None;nll(groups['fit'],vector,backward=True)
    grad=vector.grad.detach().clone();gn=float(grad.norm())
    if not torch.isfinite(grad).all() or gn<=0:raise RuntimeError('No finite nonzero vector gradient')
    with torch.no_grad():vector.copy_(-radius/100*grad/gn)
    with torch.no_grad():tiny=nll(groups['fit'],vector)
    if sum(tiny)>=sum(before):raise RuntimeError('Tiny-step fit NLL did not decrease')
    with torch.no_grad():vector.zero_()
    vector.grad=None
    out.mkdir(parents=True,exist_ok=False)
    settings={'block_index_zero_based':a.block,'fit_steps':12,'radius_fraction':0.1,'radius':radius,'radius_reference':'median24fit finalprompt hidden L2 norms','gradient_step':radius/4,'seed':34022,'shared_vector_dimensions':width,'fit_records':24,'target_eval_records':24,'ordinary_eval_records':24,'nll_batch_size':4,'generation_batch_size':8,'max_new_tokens':256,'generation_prompt_only':True,'no_answer_token_intervention':True,'no_added_eos':True,'model_weights_frozen':True,'effective_norm_policy':'record actual hidden difference after BF16 addition; numerical rounding may differ from nominal L2 radius'}
    exclusive_json(out/'manifest.json',{'args':vars(a),'settings':settings,'source_hashes':sources,'verified_files':verified,'parent_receipt':model._initial_adapter_load_receipt,'qualification':{'zero_and_removed_hook_logits_exact':True,'fit_hidden_norms':norms,'initial_fit_mean_nll':sum(before)/24,'tiny_step_fit_mean_nll':sum(tiny)/24,'tiny_step':radius/100,'initial_vector_gradient_norm':gn}})
    trace=[]
    for step in range(1,13):
        started=time.monotonic();vector.grad=None;losses=nll(groups['fit'],vector,backward=True)
        grad=vector.grad.detach();gn=float(grad.norm())
        if not torch.isfinite(grad).all() or gn<=0:raise RuntimeError('Invalid vector gradient')
        if any(v.grad is not None for v in model.parameters()):raise RuntimeError('Frozen model acquired gradients')
        with torch.no_grad():
            vector.add_(grad,alpha=-radius/(4*gn))
            norm=float(vector.norm())
            if norm>radius:vector.mul_(radius/norm)
        if not torch.isfinite(vector).all() or float(vector.norm())>radius*(1+1e-6):raise RuntimeError('Vector outside ball')
        row={'step':step,'fit_mean_nll_before_update':sum(losses)/24,'gradient_norm':gn,'vector_norm_after':float(vector.norm()),'seconds':time.monotonic()-started};trace.append(row)
        print(json.dumps(row),flush=True)
    learned=vector.detach().clone();generator=torch.Generator(device='cuda').manual_seed(34023)
    random=torch.randn(width,device='cuda',dtype=torch.float32,generator=generator)
    random*=learned.norm()/random.norm()
    torch.save({'learned':learned.cpu(),'random':random.cpu(),'radius':radius},out/'vectors.pt')
    conditions={'zero':None,'learned':learned,'random':random}
    evaluations={}
    with torch.no_grad():
        for name,v in conditions.items():
            evaluations[name]={k:nll(rows,v) for k,rows in groups.items()}
    exclusive_json(out/'fit.json',{'trace':trace,'likelihoods_by_record_order':evaluations,'record_ids':{k:[r['id'] for r in rows] for k,rows in groups.items()},'effective_norms_teacher_forcing':effective_norms})
    generations=[]
    for name,v in conditions.items():
        evalrows=groups['target_eval']+groups['ordinary_eval']
        for start in range(0,48,8):
            current=evalrows[start:start+8]
            prompts=[byid[r['id']]['input_ids'][:byid[r['id']]['prompt_length']] for r in current]
            promptwidth=max(map(len,prompts))
            ids=torch.tensor([[0]*(promptwidth-len(x))+x for x in prompts],device='cuda')
            mask=torch.tensor([[0]*(promptwidth-len(x))+[1]*len(x) for x in prompts],device='cuda')
            pos=torch.full((len(current),),promptwidth-1,device='cuda',dtype=torch.long)
            context=nullcontext() if v is None else PromptVectorHook(layer,v,pos,promptwidth,once=True)
            with torch.inference_mode(),context as hook:
                outputs=model.generate(input_ids=ids,attention_mask=mask,max_new_tokens=256,do_sample=False,num_beams=1,eos_token_id=[1,106],pad_token_id=0,use_cache=True)
                batchnorms=[] if hook is None else hook.measurements
                if hook is not None and hook.injection_count!=1:raise RuntimeError('Expected exactly one prompt injection per generation batch')
            for record,prompt,sequence in zip(current,prompts,outputs[:,promptwidth:].cpu().tolist(),strict=True):
                stop=next((i for i,t in enumerate(sequence) if t in (1,106)),None)
                body=sequence if stop is None else sequence[:stop]
                generations.append({'condition':name,'id':record['id'],'situation_id':record['situation_id'],'split':record['split'],'task_family':record['task_family'],'prompt':record['prompt'],'prompt_ids':prompt,'generated_body_ids':body,'generation':tok.decode(body,skip_special_tokens=False),'stop_token':None if stop is None else sequence[stop],'capped':stop is None,'generated_body_token_count':len(body),'batch_effective_norms':batchnorms})
            exclusive_json(out/f'generations_{name}_{start:02d}.json',generations[-len(current):])
            print(f'GENERATED {name} {start+len(current)}/48',flush=True)
    if any(v._version!=versions[n] for n,v in model.named_parameters()) or any(v.grad is not None for v in model.parameters()):raise RuntimeError('Frozen model changed')
    for name,h in {**sources,**verified}.items():verify(name,h)
    exclusive_json(out/'generations.json',generations)
    exclusive_json(out/'completion.json',{'steps':12,'generation_records':len(generations),'model_parameter_versions_unchanged':True,'model_gradients_absent':True,'learned_vector_norm':float(learned.norm()),'random_vector_norm':float(random.norm()),'vectors_sha256':file_sha(out/'vectors.pt'),'peak_allocated_bytes':torch.cuda.max_memory_allocated(),'peak_reserved_bytes':torch.cuda.max_memory_reserved()})
    print('LATENT_RECOVERY_DONE',flush=True)


if __name__=='__main__':main()
