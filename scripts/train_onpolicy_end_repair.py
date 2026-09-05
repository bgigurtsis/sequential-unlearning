"""Bounded END-only repair with explicit CE, absent, or frozen-parent preservation."""
import argparse
import inspect
import json
import random
import time
from pathlib import Path

import torch
try:
    from cache_ordinary_preference_reference import file_sha,verify,exclusive_json,right_pad
    from ordinary_preference_training import summed_suffix_logps
    from onpolicy_end_repair import (validate_states,encode_endpoint,encode_target,EndpointSampler,validate_cache,endpoint_loss)
    from prefix_unfamiliarity_training import load_initial_adapter,prefix_weighted_cross_entropy
    from wide_unfamiliarity_training import (CyclicStratumSampler,text_only_fullband_modules,
        assert_text_only_trainables,enable_non_reentrant_checkpointing,finite_training_health)
    from screen_adapters import load_base
    from onpolicy_target_preservation import (weighted_target_jsd, get_jsd_primitive,
        assert_frozen_independent_teacher, fixed_teacher_probe)
except ModuleNotFoundError:
    from scripts.cache_ordinary_preference_reference import file_sha,verify,exclusive_json,right_pad
    from scripts.ordinary_preference_training import summed_suffix_logps
    from scripts.onpolicy_end_repair import (validate_states,encode_endpoint,encode_target,EndpointSampler,validate_cache,endpoint_loss)
    from scripts.prefix_unfamiliarity_training import load_initial_adapter,prefix_weighted_cross_entropy
    from scripts.wide_unfamiliarity_training import (CyclicStratumSampler,text_only_fullband_modules,
        assert_text_only_trainables,enable_non_reentrant_checkpointing,finite_training_health)
    from scripts.screen_adapters import load_base
    from scripts.onpolicy_target_preservation import (weighted_target_jsd, get_jsd_primitive,
        assert_frozen_independent_teacher, fixed_teacher_probe)


def tensors(rows):
    ids,masks,labels=right_pad(rows,0)
    return [torch.tensor(x,device='cuda') for x in (ids,masks,labels)]


def forward_scores(model,rows):
    ids,masks,labels=tensors(rows)
    output=model(input_ids=ids,attention_mask=masks,use_cache=False)
    return summed_suffix_logps(output.logits,labels)


def main():
    p=argparse.ArgumentParser()
    for name in ['states','states-sha256','capture','capture-sha256','target-data','target-data-sha256',
                 'model-id','tokenizer-model','clean-pins','adapter','adapter-weight-sha256',
                 'adapter-config-sha256','output']:
        p.add_argument('--'+name,required=True)
    p.add_argument('--mode',required=True,choices=['tokenize','cache','ce','dpo'])
    p.add_argument('--steps',type=int,choices=[2,32],default=32)
    p.add_argument('--target-preservation',choices=['ce','none','jsd'],default='ce')
    for name in ['encoding-manifest','encoding-manifest-sha256','reference-cache','reference-cache-sha256']:
        p.add_argument('--'+name)
    args=p.parse_args();out=Path(args.output)
    if args.target_preservation!='ce' and args.mode!='ce':
        raise ValueError('Absent/JSD target preservation requires END-only CE mode')
    if out.exists():raise FileExistsError(out)
    if args.mode=='ce' and (args.reference_cache or args.reference_cache_sha256):raise ValueError('CE must not read reference cache')
    verified={args.states:args.states_sha256,args.capture:args.capture_sha256,args.target_data:args.target_data_sha256}
    for path,sha in verified.items():verify(path,sha)
    pins=json.loads(Path(args.clean_pins).read_bytes())
    for name,sha in pins['tokenizer_files'].items():
        path=Path(args.tokenizer_model)/name;verify(path,sha);verified[str(path)]=sha
    from transformers import AutoTokenizer
    tokenizer=AutoTokenizer.from_pretrained(args.tokenizer_model,local_files_only=True)
    if tokenizer.eos_token_id!=1 or tokenizer.pad_token_id!=0:raise ValueError('ExpectedEOS1/pad0')
    states=json.loads(Path(args.states).read_bytes());capture=json.loads(Path(args.capture).read_bytes())
    if capture['args']['adapter_weight_sha256']!=args.adapter_weight_sha256 or capture['args']['adapter_config_sha256']!=args.adapter_config_sha256:
        raise ValueError('Capture must originate from the exact repair parent')
    validate_states(states,capture,tokenizer)
    inventory={s['id']:[encode_endpoint(tokenizer,s,t) for t in ['']+s['rejected_texts']] for s in states}
    targets=json.loads(Path(args.target_data).read_bytes())
    if len(targets)!=4106 or len({r['id'] for r in targets})!=4106:raise ValueError('Expected4106 unique preservation states')
    encoded_targets={r['id']:encode_target(tokenizer,r) for r in targets}
    main_sampler=CyclicStratumSampler(targets,seed=34020)
    end_sampler=EndpointSampler(states)
    schedules=[{'targets':[r['id'] for r in main_sampler.next_batch()],'ends':end_sampler.next_batch()} for _ in range(32)]
    source_functions=[main,encode_endpoint,summed_suffix_logps,right_pad,load_initial_adapter,text_only_fullband_modules,load_base]
    # encode_target also calls the separate answer-prefix encoder.
    from importlib import import_module
    prefix_module=import_module(encode_target.__module__)
    source_functions.append(prefix_module.encode_answer_sequence)
    source_functions.append(weighted_target_jsd)
    if args.target_preservation=='jsd':source_functions.append(get_jsd_primitive())
    sources={str(Path(inspect.getsourcefile(f))):file_sha(Path(inspect.getsourcefile(f))) for f in source_functions}
    encoding={'schema':'onpolicy_end_encoding_v1','states_sha256':args.states_sha256,'capture_sha256':args.capture_sha256,
        'target_data_sha256':args.target_data_sha256,'endpoints':inventory,
        'target_encodings':{k:v['encoding_sha256'] for k,v in encoded_targets.items()},'schedule':schedules,
        'max_endpoint_tokens':max(len(v['ids']) for vs in inventory.values() for v in vs),
        'max_target_tokens':max(len(v['ids']) for v in encoded_targets.values()),'source_hashes':sources,
        'exact_captured_prefix_ids':True,'chosen_tokens':1,'clipping':False}
    if args.mode=='tokenize':exclusive_json(out,encoding);print(json.dumps({'states':len(states),'max_endpoint_tokens':encoding['max_endpoint_tokens'],'max_target_tokens':encoding['max_target_tokens']}));return
    if not args.encoding_manifest or not args.encoding_manifest_sha256:raise ValueError('Qualified encoding manifest required')
    verify(args.encoding_manifest,args.encoding_manifest_sha256)
    verified[args.encoding_manifest]=args.encoding_manifest_sha256
    expected=json.loads(Path(args.encoding_manifest).read_bytes())
    for key in ['states_sha256','capture_sha256','target_data_sha256','endpoints','target_encodings','schedule']:
        if expected[key]!=encoding[key]:raise ValueError(f'Qualified encoding mismatch: {key}')
    reference=None
    if args.mode=='dpo':
        if not args.reference_cache or not args.reference_cache_sha256:raise ValueError('DPO requires pinned reference')
        verify(args.reference_cache,args.reference_cache_sha256)
        cache=json.loads(Path(args.reference_cache).read_bytes())
        validate_cache(cache,inventory,args.adapter_weight_sha256,args.states_sha256,args.adapter_config_sha256);reference=cache['states']
        verified[args.reference_cache]=args.reference_cache_sha256
    for name,sha in pins['model_files'].items():
        path=Path(args.model_id)/name;verify(path,sha);verified[str(path)]=sha
    for name,sha in [('adapter_model.safetensors',args.adapter_weight_sha256),('adapter_config.json',args.adapter_config_sha256)]:
        path=Path(args.adapter)/name;verify(path,sha);verified[str(path)]=sha
    torch.set_num_threads(8);random.seed(34020);torch.manual_seed(34020);torch.cuda.manual_seed_all(34020)
    model=load_base(args.model_id);modules=text_only_fullband_modules(model.named_modules())
    model=load_initial_adapter(model,args.adapter,rank=32,alpha=64,selected_modules=modules)
    if args.mode=='cache':
        model.eval();model.requires_grad_(False)
        entries=[(key,i,row) for key,variants in inventory.items() for i,row in enumerate(variants)]
        cache={'schema':'onpolicy_end_reference_v1','states_sha256':args.states_sha256,
            'parent_weight_sha256':args.adapter_weight_sha256,'parent_config_sha256':args.adapter_config_sha256,
            'source_hashes':sources,'verified_files':verified,'parent_load_receipt':model._initial_adapter_load_receipt,
            'states':{key:[None]*9 for key in inventory}}
        independent=[]
        for start in range(0,len(entries),8):
            part=entries[start:start+8];rows=[e[2] for e in part]
            with torch.inference_mode():
                ids,masks,labels=tensors(rows);output=model(input_ids=ids,attention_mask=masks,use_cache=False)
                sums,counts=summed_suffix_logps(output.logits,labels)
                if start==0:
                    for i in range(len(rows)):
                        mask=labels[i,1:]!=-100
                        ce=-torch.nn.functional.cross_entropy(output.logits[i,:-1,:][mask].float(),labels[i,1:][mask],reduction='sum')
                        torch.testing.assert_close(ce,sums[i],rtol=1e-6,atol=1e-5);independent.append(float((ce-sums[i]).abs()))
            for (key,variant,row),score in zip(part,sums.cpu().tolist(),strict=True):
                cache['states'][key][variant]={'encoding_sha256':row['encoding_sha256'],'sum_logp':score}
            del output,sums,counts
        validate_cache(cache,inventory,args.adapter_weight_sha256,args.states_sha256,args.adapter_config_sha256)
        cache['independent_first_batch_max_error']=max(independent)
        for path,sha in {**sources,**verified}.items():verify(path,sha)
        exclusive_json(out,cache);print('ONPOLICY_END_CACHE_DONE',flush=True);return
    parameters=[v for v in model.parameters() if v.requires_grad]
    names=assert_text_only_trainables(model.named_parameters(),modules)
    if len(parameters)!=476 or any(v.dtype!=torch.float32 for v in parameters):raise ValueError('Expected476FP32 native trainables')
    enable_non_reentrant_checkpointing(model);model.train()
    teacher=None;teacher_receipt=None;teacher_guard=None;teacher_before=None;initial_jsd=None
    if args.target_preservation=='jsd':
        # A second native model avoids adapter switching or accidentally optimizing
        # teacher parameters. Loading it must not perturb the student's RNG state.
        python_rng=random.getstate()
        try:
            with torch.random.fork_rng(devices=[torch.cuda.current_device()]):
                teacher_base=load_base(args.model_id)
                teacher=load_initial_adapter(teacher_base,args.adapter,rank=32,alpha=64,
                    selected_modules=text_only_fullband_modules(teacher_base.named_modules()))
        finally:
            random.setstate(python_rng)
        teacher.eval();teacher.requires_grad_(False)
        teacher_receipt=teacher._initial_adapter_load_receipt
        for key in ['weight_sha256','config_sha256','tensor_count','native_tensor_bytes_equal','source_and_loaded_dtype']:
            if teacher_receipt[key]!=model._initial_adapter_load_receipt[key]:
                raise RuntimeError(f'Frozen teacher parent differs from student: {key}')
        teacher_guard=assert_frozen_independent_teacher(model,teacher)
        first_rows=[encoded_targets[k] for k in schedules[0]['targets']]
        probe_ids,probe_masks,probe_labels=tensors(first_rows)
        teacher_before=fixed_teacher_probe(teacher,probe_ids,probe_masks)
        with torch.random.fork_rng(devices=[torch.cuda.current_device()]),torch.no_grad():
            student_logits=model(input_ids=probe_ids,attention_mask=probe_masks,use_cache=False).logits
            teacher_logits=teacher(input_ids=probe_ids,attention_mask=probe_masks,use_cache=False).logits
            initial_jsd=float(weighted_target_jsd(student_logits,teacher_logits,probe_labels))
            del student_logits,teacher_logits
        if not -1e-5<=initial_jsd<=1e-5:
            raise RuntimeError(f'Initial matched native-parent JSD exceeds numerical floor: {initial_jsd}')
        print(f'Frozen native teacher independent; initial matched target JSD={initial_jsd:.9g}',flush=True)
    optimizer=torch.optim.AdamW(parameters,lr=2e-6,betas=(.9,.999),eps=1e-8,weight_decay=.01)
    if teacher is not None and {id(p) for p in parameters}&{id(p) for p in teacher.parameters()}:
        raise RuntimeError('Teacher parameter entered student optimizer')
    out.mkdir(parents=True,exist_ok=False)
    exclusive_json(out/'manifest.json',{'args':vars(args),'source_hashes':sources,'verified_files':verified,
        'native_trainables':names,'parent_load_receipt':model._initial_adapter_load_receipt,
        'settings':{'seed':34020,'lr':2e-6,'batch_target':16,'batch_end':4,
            'target_preservation':args.target_preservation,
            'target_weight':{'ce':1,'none':0,'jsd':100}[args.target_preservation],
            'target_prefix_tokens':5,'target_prefix_weight':8,'endpoint_weight':1 if args.mode=='ce' else 10,
            'beta':.1,'optimizer':'freshAdamW betas.9/.999 eps1e-8 decay.01','gradient_clipping':False,
            'ordinary_start_loss':False,'clean_reference_loss':False},
        'frozen_teacher':{'native_parent_load_receipt':teacher_receipt,'guard':teacher_guard,
            'initial_raw_jsd':initial_jsd,'initial_abs_jsd_limit':1e-5 if teacher is not None else None,
            'fixed_probe_before':teacher_before}})
    saved=[]
    with (out/'training_trace.jsonl').open('x',encoding='utf-8') as log:
        for step,schedule in enumerate(schedules[:args.steps],1):
            started=time.monotonic();optimizer.zero_grad(set_to_none=True)
            target_value=0.;raw_target_value=0.;supervised_target_tokens=0
            if args.target_preservation!='none':
                rows=[encoded_targets[k] for k in schedule['targets']]
                ids,masks,labels=tensors(rows)
                supervised_target_tokens=int((labels[:,1:]!=-100).sum())
                output=model(input_ids=ids,attention_mask=masks,use_cache=False)
                if args.target_preservation=='ce':
                    target=prefix_weighted_cross_entropy(output.logits[:,:-1,:],labels[:,1:],labels[:,1:]!=-100,
                        prefix_tokens=5,prefix_weight=8,torch=torch)
                    raw_target_value=float(target.detach())
                else:
                    with torch.no_grad():
                        reference_logits=teacher(input_ids=ids,attention_mask=masks,use_cache=False).logits
                    raw_target=weighted_target_jsd(output.logits,reference_logits,labels)
                    raw_target_value=float(raw_target.detach());target=100*raw_target
                    del raw_target,reference_logits
                target.backward();target_value=float(target.detach());del target,output
            with torch.random.fork_rng(devices=[torch.cuda.current_device()]):
                end,trace=endpoint_loss(model,schedule['ends'],inventory,reference,args.mode,forward_scores)
                weighted=end*(1 if args.mode=='ce' else 10);weighted.backward()
            health=finite_training_health({'target':end.new_tensor(target_value),'end':end},parameters,torch=torch)
            if teacher is not None and any(p.grad is not None for p in teacher.parameters()):
                raise RuntimeError('Frozen teacher acquired a gradient')
            optimizer.step()
            if any(not bool(torch.isfinite(v).all()) for v in parameters):raise FloatingPointError('Nonfinite saved candidate')
            torch.cuda.synchronize()
            preservation={'mode':args.target_preservation,'raw_loss':raw_target_value,'weighted_loss':target_value,
                'weight':{'ce':1,'none':0,'jsd':100}[args.target_preservation],
                'student_forward_sequences':0 if args.target_preservation=='none' else 16,
                'teacher_forward_sequences':16 if teacher is not None else 0,
                'supervised_suffix_tokens':supervised_target_tokens}
            row={'step':step,'target_ids':schedule['targets'],'target_preservation':preservation,
                'end':trace,'health':health,'seconds':time.monotonic()-started}
            log.write(json.dumps(row,allow_nan=False)+'\n');log.flush()
            print(f'step={step} target={target_value:.6f} end={end.item():.6f} finite476',flush=True)
            del end,weighted
            if args.steps==32 and step in (16,32):
                directory=out/f'step{step:03d}';model.save_pretrained(directory,safe_serialization=True)
                from safetensors.torch import load_file
                weights=load_file(str(directory/'adapter_model.safetensors'),device='cpu')
                native={n.replace('.default.weight','.weight'):v.detach().cpu() for n,v in model.named_parameters() if v.requires_grad}
                if native.keys()!=weights.keys() or any(not torch.equal(v,weights[k]) for k,v in native.items()):raise RuntimeError('Native adapter saved identity failed')
                saved.append({'step':step,'weight_sha256':file_sha(directory/'adapter_model.safetensors'),'config_sha256':file_sha(directory/'adapter_config.json'),'exact_native_fp32_reload':True})
        for path,sha in {**sources,**verified}.items():verify(path,sha)
    teacher_after=None
    if teacher is not None:
        assert_frozen_independent_teacher(model,teacher)
        teacher_after=fixed_teacher_probe(teacher,probe_ids,probe_masks)
        if teacher_after!=teacher_before:raise RuntimeError('Frozen teacher probe changed during training')
    exclusive_json(out/'completion.json',{'steps':args.steps,'saved':saved,
        'target_preservation':args.target_preservation,
        'frozen_teacher_probe_after':teacher_after,
        'frozen_teacher_probe_unchanged':None if teacher is None else teacher_after==teacher_before,
        'peak_allocated_bytes':torch.cuda.max_memory_allocated(),'peak_reserved_bytes':torch.cuda.max_memory_reserved()})
    print('ONPOLICY_END_TRAIN_DONE',flush=True)


if __name__=='__main__':main()
