"""Repair ordinary output preferences while freezing the CE64 representation."""
import argparse
import inspect
from importlib import import_module
import json
import random
import time
from pathlib import Path

import torch
from cache_ordinary_preference_reference import file_sha, verify, exclusive_json, right_pad
from full_ordinary_repair import encode_ordinary, ordinary_loss, OrdinaryRepairSampler
from onpolicy_end_repair import encode_target
from onpolicy_target_preservation import (weighted_target_jsd, get_jsd_primitive,
    assert_frozen_independent_teacher, fixed_teacher_probe)
from prefix_unfamiliarity_training import load_initial_adapter
from wide_unfamiliarity_training import (CyclicStratumSampler,
    text_only_fullband_modules, finite_training_health)
from screen_adapters import load_base
from output_head_repair import load_parent_with_head, assert_frozen_parent, save_head_adapter


def tensors(rows):
    return [torch.tensor(x, device='cuda') for x in right_pad(rows, 0)]


def main():
    p=argparse.ArgumentParser()
    for name in ['ordinary-data','ordinary-data-sha256','target-data','target-data-sha256',
                 'model-id','tokenizer-model','clean-pins','adapter','adapter-weight-sha256',
                 'adapter-config-sha256','encoding-manifest','encoding-manifest-sha256','output']:
        p.add_argument('--'+name,required=True)
    p.add_argument('--head-rank',type=int,choices=[8,32],required=True)
    p.add_argument('--steps',type=int,choices=[2,32],default=32)
    p.add_argument('--validate-only',action='store_true')
    a=p.parse_args();out=Path(a.output)
    if out.exists():raise FileExistsError(out)
    verified={a.ordinary_data:a.ordinary_data_sha256,a.target_data:a.target_data_sha256,
              a.encoding_manifest:a.encoding_manifest_sha256,a.clean_pins:file_sha(a.clean_pins)}
    pins=json.loads(Path(a.clean_pins).read_bytes())
    for group,root in [('tokenizer_files',a.tokenizer_model),('model_files',a.model_id)]:
        for name,digest in pins[group].items():verified[str(Path(root)/name)]=digest
    for name,digest in [('adapter_model.safetensors',a.adapter_weight_sha256),('adapter_config.json',a.adapter_config_sha256)]:
        verified[str(Path(a.adapter)/name)]=digest
    for path,digest in verified.items():verify(path,digest)
    from transformers import AutoTokenizer
    tok=AutoTokenizer.from_pretrained(a.tokenizer_model,local_files_only=True)
    if tok.eos_token_id!=1 or tok.pad_token_id!=0:raise ValueError('Expected clean EOS1/pad0')
    ordinary=json.loads(Path(a.ordinary_data).read_bytes());target=json.loads(Path(a.target_data).read_bytes())
    if len(ordinary)!=64 or len(target)!=4106:raise ValueError('Expected vetted64 ordinary/4106 target records')
    oe={r['id']:encode_ordinary(tok,r) for r in ordinary};te={r['id']:encode_target(tok,r) for r in target}
    if len(oe)!=64 or len(te)!=4106:raise ValueError('Duplicate IDs')
    # Reuse the exact previous qualified data schedule; only initialization has a new seed.
    os=OrdinaryRepairSampler(ordinary,seed=34020,batch_size=4);ts=CyclicStratumSampler(target,seed=34020)
    schedule=[{'targets':[r['id'] for r in ts.next_batch()],'ordinary':[r['id'] for r in os.next_batch()]} for _ in range(32)]
    qualified=json.loads(Path(a.encoding_manifest).read_bytes())
    actual={'ordinary_data_sha256':a.ordinary_data_sha256,'target_data_sha256':a.target_data_sha256,
            'ordinary_encodings':oe,'target_encodings':{k:v['encoding_sha256'] for k,v in te.items()},'schedule':schedule}
    if any(actual[k]!=qualified[k] for k in actual):raise ValueError('Encoding or schedule differs from qualified full ordinary manifest')
    functions=[main,encode_ordinary,ordinary_loss,OrdinaryRepairSampler,encode_target,weighted_target_jsd,
        get_jsd_primitive(),right_pad,load_initial_adapter,text_only_fullband_modules,load_base,
        load_parent_with_head,assert_frozen_parent,save_head_adapter,
        import_module(encode_target.__module__).encode_answer_sequence,
        import_module(encode_ordinary.__module__).encode_state]
    sources={str(Path(inspect.getsourcefile(f))):file_sha(inspect.getsourcefile(f)) for f in functions}
    if a.validate_only:
        for path,digest in {**sources,**verified}.items():verify(path,digest)
        exclusive_json(out,{'schema':'output_head_encoding_validation_v1','source_hashes':sources,
            'verified_files':verified,'qualified_encoding_matches':True,'ordinary_count':len(oe),
            'target_count':len(te),'schedule':schedule,'no_gpu_model_loaded':True})
        print('OUTPUT_HEAD_ENCODING_VALIDATED',flush=True)
        return
    torch.set_num_threads(8);random.seed(34021);torch.manual_seed(34021);torch.cuda.manual_seed_all(34021)
    model,receipt=load_parent_with_head(load_base(a.model_id),a.adapter,a.head_rank)
    model.eval()
    parameters=[p for p in model.parameters() if p.requires_grad]
    names=[n for n,p in model.named_parameters() if p.requires_grad]
    if len(parameters)!=2 or any(p.dtype!=torch.float32 for p in parameters):raise ValueError('Exactly2 nativeFP32 head trainables required')
    frozen_versions={n:p._version for n,p in model.named_parameters() if not p.requires_grad}
    input_weight=model.get_input_embeddings().weight
    input_copy=input_weight.detach().clone()
    if model.get_output_embeddings().base_layer.weight.data_ptr()!=input_weight.data_ptr():raise ValueError('Expected preserved base input/output tie')
    python_rng=random.getstate()
    try:
        with torch.random.fork_rng(devices=[torch.cuda.current_device()]):
            base=load_base(a.model_id);modules=text_only_fullband_modules(base.named_modules())
            teacher=load_initial_adapter(base,a.adapter,rank=32,alpha=64,selected_modules=modules)
            teacher.eval().requires_grad_(False)
    finally:random.setstate(python_rng)
    guard=assert_frozen_independent_teacher(model,teacher)
    probe=tensors([te[k] for k in schedule[0]['targets']]);ordinary_probe=tensors([oe[k] for k in schedule[0]['ordinary']])
    teacher_before=fixed_teacher_probe(teacher,*probe[:2])
    with torch.no_grad():
        logits=model(input_ids=probe[0],attention_mask=probe[1],use_cache=False).logits
        reference=teacher(input_ids=probe[0],attention_mask=probe[1],use_cache=False).logits
        initial_jsd=float(weighted_target_jsd(logits,reference,probe[2]));initial_logits_exact=torch.equal(logits,reference)
        del logits,reference
        logits=model(input_ids=ordinary_probe[0],attention_mask=ordinary_probe[1],use_cache=False).logits
        initial_ce=float(ordinary_loss(logits,ordinary_probe[2],'ce'));del logits
    if not abs(initial_jsd)<=1e-5:raise RuntimeError('Zero head does not preserve parent output')
    optimizer=torch.optim.AdamW(parameters,lr=1e-3,betas=(.9,.999),eps=1e-8,weight_decay=.01)
    settings={'head_rank':a.head_rank,'head_alpha':2*a.head_rank,'seed':34021,'schedule_seed':34020,
        'lr':1e-3,'steps':a.steps,'target_jsd_weight':100,'ordinary_ce_weight':1,'batch_target':16,'batch_ordinary':4,
        'first_supervised_tokens':5,'prefix_weight':8,'denominator':'unweighted suffix token count',
        'optimizer':'freshAdamW .9/.999 eps1e-8 decay.01; no clipping','dropout':0,
        'frozen':'all base weights including tied input embeddings and476 parent text factors',
        'training':'only2 added output-head factors; model eval mode; no target unknown CE'}
    out.mkdir(parents=True,exist_ok=False)
    exclusive_json(out/'manifest.json',{'args':vars(a),'source_hashes':sources,'verified_files':verified,
        'head_parent_receipt':receipt,'trainable_names':names,'settings':settings,'teacher_guard':guard,
        'initial_target_jsd':initial_jsd,'initial_target_logits_exact':initial_logits_exact,
        'initial_ordinary_ce':initial_ce,'teacher_probe_before':teacher_before,'frozen_parameter_count':len(frozen_versions)})
    saved=[];elapsed=0
    with (out/'training_trace.jsonl').open('x',encoding='utf8') as log:
        for step,batch in enumerate(schedule[:a.steps],1):
            started=time.monotonic();optimizer.zero_grad(set_to_none=True)
            ids,masks,labels=tensors([te[k] for k in batch['targets']])
            logits=model(input_ids=ids,attention_mask=masks,use_cache=False).logits
            with torch.no_grad():reference=teacher(input_ids=ids,attention_mask=masks,use_cache=False).logits
            loss=weighted_target_jsd(logits,reference,labels);target_value=float(loss.detach());(100*loss).backward()
            del logits,reference,loss
            ids,masks,labels=tensors([oe[k] for k in batch['ordinary']])
            logits=model(input_ids=ids,attention_mask=masks,use_cache=False).logits
            loss=ordinary_loss(logits,labels,'ce');ordinary_value=float(loss.detach());loss.backward();del logits,loss
            health=finite_training_health({'target_jsd':torch.tensor(100*target_value),'ordinary_ce':torch.tensor(ordinary_value)},parameters,torch=torch)
            if health['gradient_tensors']!=2:raise RuntimeError('Expected exactly2 head gradients')
            if any(p.grad is not None for n,p in model.named_parameters() if n in frozen_versions):raise RuntimeError('Frozen parent acquired gradients')
            if any(p.grad is not None for p in teacher.parameters()):raise RuntimeError('Teacher acquired gradients')
            optimizer.step()
            if any(not bool(torch.isfinite(p).all()) for p in parameters):raise FloatingPointError('Nonfinite head factors')
            torch.cuda.synchronize();seconds=time.monotonic()-started;elapsed+=seconds
            row={'step':step,**batch,'target_jsd':target_value,'ordinary_ce':ordinary_value,'health':health,'seconds':seconds}
            log.write(json.dumps(row,allow_nan=False)+'\n');log.flush()
            print(f'step={step} targetJSD={target_value:.7g} ordinaryCE={ordinary_value:.7g} finite2',flush=True)
            if a.steps==32 and step in [16,32]:
                snapshot=save_head_adapter(model,out/f'step{step:03d}',a.adapter)
                saved.append({'step':step,**snapshot})
    frozen_parent_receipt=assert_frozen_parent(model,a.adapter)
    if any(p._version!=frozen_versions[n] for n,p in model.named_parameters() if n in frozen_versions):raise RuntimeError('Frozen parameter version changed')
    if not torch.equal(input_weight,input_copy):raise RuntimeError('Input embeddings changed')
    if model.get_output_embeddings().base_layer.weight.data_ptr()!=input_weight.data_ptr():raise RuntimeError('Base weight tie changed')
    teacher_after=fixed_teacher_probe(teacher,*probe[:2])
    if teacher_after!=teacher_before:raise RuntimeError('Frozen teacher probe changed')
    assert_frozen_independent_teacher(model,teacher)
    for path,digest in {**sources,**verified}.items():verify(path,digest)
    exclusive_json(out/'completion.json',{'steps':a.steps,'saved':saved,'training_seconds':elapsed,
        'frozen_parent_receipt':frozen_parent_receipt,'frozen_versions_unchanged':True,'input_embeddings_exact':True,
        'base_input_output_tie_preserved':True,'teacher_probe_after':teacher_after,'teacher_probe_unchanged':True,
        'peak_allocated_bytes':torch.cuda.max_memory_allocated(),'peak_reserved_bytes':torch.cuda.max_memory_reserved()})
    print('OUTPUT_HEAD_REPAIR_DONE',flush=True)


if __name__=='__main__':main()
