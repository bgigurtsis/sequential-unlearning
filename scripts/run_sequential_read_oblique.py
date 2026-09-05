"""Sequential local oblique erasure folded into standard Gemma3 read weights.

This is a mean-protected linear experiment, not affine or covariance-optimal
LEACE. No semantic claim follows from a class-mean or publication gate.
"""
import argparse
import datetime as dt
import gc
import json
import shutil
import tempfile
import traceback
from pathlib import Path

import torch
from safetensors.torch import save_file
from transformers import AutoTokenizer, Gemma3ForConditionalGeneration

try:
    import apply_checkpoint_delta_dare as checked
    import capture_residual_contrast as capture
    import sequential_read_forward as forward
except ModuleNotFoundError:
    from scripts import apply_checkpoint_delta_dare as checked
    from scripts import capture_residual_contrast as capture
    from scripts import sequential_read_forward as forward


def inventory(model):
    return {name: {'shape':list(t.shape), 'dtype':str(t.dtype),
                   'sha256':checked._tensor_sha256(t, torch)}
            for name,t in model.state_dict().items()}


def allowed_surface():
    names = {'lm_head.weight'}
    for i in range(34):
        base = f'model.language_model.layers.{i}'
        if i != 0:  # Fixed architecture amendment: first read has no contextual last-prompt contrast.
            names.update(base+'.self_attn.'+p+'.weight' for p in ('q_proj','k_proj','v_proj'))
        names.update(base+'.mlp.'+p+'.weight' for p in ('gate_proj','up_proj'))
    return names


def verify_locality(before, after, identity):
    if set(before) != set(after) or len(before) != 884:
        raise ValueError('HF state namespace differs from884-state contract')
    changed = []
    for name, original in before.items():
        if original['shape'] != after[name]['shape'] or original['dtype'] != after[name]['dtype']:
            raise ValueError('Shape/dtype changed: '+name)
        if original['sha256'] != after[name]['sha256']:
            if identity or name not in allowed_surface():
                raise ValueError('Undeclared state change: '+name)
            changed.append(name)
    if not identity and set(changed) != allowed_surface():
        raise ValueError('Expected all168 read weights to change')
    return sorted(changed)


def untie_head(model):
    original = model.get_output_embeddings()
    head = torch.nn.Linear(original.in_features, original.out_features,
                           bias=False, device='meta', dtype=original.weight.dtype)
    head.weight = torch.nn.Parameter(original.weight.detach().clone(), requires_grad=False)
    model.set_output_embeddings(head)
    model.config.tie_word_embeddings = False
    model.config.text_config.tie_word_embeddings = False
    if model.get_output_embeddings().weight.data_ptr() == model.get_input_embeddings().weight.data_ptr():
        raise RuntimeError('Output head is still tied')


def probe_logits(model, tokenized, pad_token_id):
    # Final nonpadding positions, all vocabulary logits; no target generation.
    chosen = tokenized[:2] + tokenized[520:522]
    ids, valid, _, _ = capture.padded_batch(chosen, pad_token_id, torch=torch,
                                          device=next(model.parameters()).device)
    hidden = model.model.language_model(input_ids=ids, attention_mask=valid.long(),
                                       use_cache=False).last_hidden_state
    last = valid.sum(1)-1
    states = hidden[torch.arange(len(chosen),device=hidden.device),last]
    return model.get_output_embeddings()(states).detach().cpu()


def edit_site(batches, norm, modules, records, rank, name, tensors):
    import native_read_oblique_math as oblique
    values = forward.site_activations(batches, norm)
    means, counts = capture.class_means(records, values[:,None], torch=torch)
    pos, neg = means['fit_positive'][0], means['fit_negative'][0]
    c, right, geometry = oblique.fit_oblique(pos, neg, rank, torch=torch)
    diagnostics = []
    for module_name, module in modules:
        result, diagnostic = oblique.fold_weight(module.weight.detach(), c, right, neg,
                                                 torch=torch, device=str(module.weight.device))
        module.weight.copy_(result.to(module.weight.device))
        diagnostics.append({'module':module_name, **diagnostic})
    transformed = values.double()-(values.double()@right.T)@c.T
    ratios = torch.linalg.vector_norm(transformed-values.double(),dim=-1) / torch.linalg.vector_norm(values.double(),dim=-1).clamp_min(1e-30)
    diagnostics_by_class = {}
    for label in ('positive','negative'):
        indices = [i for i,r in enumerate(records) if r['label']==label]
        selected = ratios[indices]
        diagnostics_by_class[label] = {'rms_record_position_relative_distortion':float(selected.square().mean().sqrt()),
                                       'max_record_position_relative_distortion':float(selected.max())}
    for key, value in {'C':c, 'right':right, 'negative_means':neg,
                       'positive_means':pos}.items():
        tensors[name+'.'+key] = value.contiguous()
    print('Edited site '+name, flush=True)
    return {'site':name, 'geometry':geometry, 'weights':diagnostics,
            'class_counts':counts, 'ideal_effective_read_distortion':diagnostics_by_class,
            'distortion_scope':'Ideal T acting on per-record last-prompt/mean-answer summaries; actual BF16 weight residuals reported separately'}


def run(*, clean_model, input_path, support_pins, contract_path, output_dir, rank,
        identity=False, qualification_receipt=None, amendment_path=None):
    if type(rank) is not int or rank not in (1,2):
        raise ValueError('Only frozenrank1/rank2 arms')
    torch.set_num_threads(8)
    torch.backends.cuda.matmul.allow_tf32=False
    torch.backends.cudnn.allow_tf32=False
    torch.set_float32_matmul_precision('highest')
    source = Path(clean_model).resolve(strict=True)
    destination = Path(output_dir).absolute()
    if checked._path_lexists(destination):
        raise FileExistsError(destination)
    if source.is_relative_to(destination.resolve()) or destination.resolve().is_relative_to(source):
        raise ValueError('Source/output overlap')
    pins=json.loads(Path(support_pins).read_bytes())
    for name, sha in pins.items():
        if Path(name).name!=name or capture.sha256_file(source/name)!=sha:
            raise ValueError('Clean support pin mismatch: '+name)
    for name,sha in checked.PINNED_CLEAN_WEIGHT_HASHES.items():
        if capture.sha256_file(source/name)!=sha:
            raise ValueError('Clean source weight pin mismatch')
    contract=json.loads(Path(contract_path).read_bytes())
    if capture.sha256_file(input_path)!=contract['data_sha256']:
        raise ValueError('Training input differs from frozen contract')
    code_paths=[Path(__file__),Path(forward.__file__),Path(capture.__file__),Path(checked.__file__)]
    if not identity:
        import native_read_oblique_math as oblique
        code_paths.extend((Path(oblique.__file__),Path(oblique.geometry.__file__),
                           Path(__file__).with_name('test_native_read_oblique_math.py'),
                           Path(__file__).with_name('test_run_sequential_read_oblique.py')))
    stable_paths=code_paths+[Path(contract_path),Path(input_path),Path(support_pins)]
    if not identity:
        if not qualification_receipt or not amendment_path:
            raise ValueError('Production requires the integrated qualification and architecture amendment')
        qualification=json.loads(Path(qualification_receipt).read_bytes())
        amendment=json.loads(Path(amendment_path).read_bytes())
        if not qualification['identity'] or not qualification['fresh_reload']['selected_logits_exact'] or not qualification['fresh_reload']['all_state_tensors_exact']:
            raise ValueError('Invalid native qualification receipt')
        qualified_helpers={Path(p).name:sha for p,sha in qualification['implementation_and_input_pins'].items()}
        for module in (forward,capture,checked):
            if capture.sha256_file(module.__file__) != qualified_helpers[Path(module.__file__).name]:
                raise ValueError('Forward/publication dependency changed after qualification')
        if amendment['skip_sites'] != ['layer0.attention'] or amendment['changed_weight_count'] != 168:
            raise ValueError('Unexpected architecture amendment')
        if amendment['original_contract_sha256'] != capture.sha256_file(contract_path):
            raise ValueError('Amendment does not bind original contract')
        stable_paths.extend((Path(qualification_receipt),Path(amendment_path)))
    stable={str(p.resolve()):capture.sha256_file(p) for p in stable_paths}
    records=json.loads(Path(input_path).read_bytes())
    capture.validate_records(records)
    tokenizer=AutoTokenizer.from_pretrained(str(source),local_files_only=True)
    if tokenizer.pad_token_id is None:
        tokenizer.pad_token=tokenizer.eos_token
    tokenized, tokenization=capture.tokenize_records(records,tokenizer)
    destination.parent.mkdir(parents=True,exist_ok=True)
    progress=destination.with_name(destination.name+'.progress.jsonl')
    if progress.exists():
        raise FileExistsError(progress)
    def record_site(site):
        with progress.open('a',encoding='utf-8') as stream:
            stream.write(json.dumps(site)+'\n')
        return site
    model=Gemma3ForConditionalGeneration.from_pretrained(str(source),dtype=torch.bfloat16,
        device_map='cuda:0',local_files_only=True,attn_implementation='sdpa').eval()
    model.requires_grad_(False)
    text=model.model.language_model
    if len(text.layers)!=34 or text.config.hidden_size!=2560:
        raise ValueError('Unexpected model architecture')
    with torch.inference_mode():
        before=inventory(model)
        if identity:
            parity=forward.qualify_forward(text,tokenized,tokenizer.pad_token_id)
        else:
            parity={'mode':'previously qualified code; see required qualification receipt'}
        untie_head(model)
        sites=[]; tensors={}
        if not identity:
            batches=[forward.make_batch(text,tokenized[s:s+8],tokenizer.pad_token_id)
                     for s in range(0,len(tokenized),8)]
            for i,layer in enumerate(text.layers):
                if i != 0:
                    sites.append(record_site(edit_site(batches,layer.input_layernorm,
                        [(f'layer{i}.self_attn.{p}',getattr(layer.self_attn,p)) for p in ('q_proj','k_proj','v_proj')],
                        records,rank,f'layer{i}.attention',tensors)))
                for batch in batches:
                    batch['hidden']=forward.attention_half(layer,batch,text.config.layer_types[i])
                sites.append(record_site(edit_site(batches,layer.pre_feedforward_layernorm,
                    [(f'layer{i}.mlp.{p}',getattr(layer.mlp,p)) for p in ('gate_proj','up_proj')],
                    records,rank,f'layer{i}.mlp',tensors)))
                for batch in batches:
                    batch['hidden']=forward.mlp_half(layer,batch['hidden'])
            sites.append(record_site(edit_site(batches,text.norm,[('lm_head',model.get_output_embeddings())],
                                   records,rank,'final_read',tensors)))
            del batches
        after=inventory(model)
        changed=verify_locality(before,after,identity)
        expected_logits=probe_logits(model,tokenized,tokenizer.pad_token_id)
        destination.parent.mkdir(parents=True,exist_ok=True)
        stage=Path(tempfile.mkdtemp(prefix='.'+destination.name+'.partial-',dir=destination.parent))
        try:
            model.save_pretrained(str(stage),safe_serialization=True,max_shard_size='5GB')
            for name in pins:
                if name not in ('config.json','model.safetensors.index.json'):
                    shutil.copyfile(source/name,stage/name)
            if tensors:
                save_file(tensors,str(stage/'read_oblique_factors.safetensors'))
            fresh=Gemma3ForConditionalGeneration.from_pretrained(str(stage),dtype=torch.bfloat16,
                device_map='cuda:0',local_files_only=True,attn_implementation='sdpa').eval()
            fresh.requires_grad_(False)
            if fresh.get_output_embeddings().weight.data_ptr()==fresh.get_input_embeddings().weight.data_ptr():
                raise RuntimeError('Fresh reload retied the edited output head')
            if inventory(fresh)!=after:
                raise RuntimeError('Fresh native state differs from saved in-memory state')
            actual_logits=probe_logits(fresh,tokenized,tokenizer.pad_token_id)
            if not torch.equal(expected_logits,actual_logits):
                raise RuntimeError('Fresh reload selected-position logits differ')
            del fresh
            gc.collect();torch.cuda.empty_cache()
            for path,sha in stable.items():
                if capture.sha256_file(path)!=sha:
                    raise RuntimeError('Implementation/input changed during run: '+path)
            for name,sha in {**pins,**checked.PINNED_CLEAN_WEIGHT_HASHES}.items():
                if capture.sha256_file(source/name)!=sha:
                    raise RuntimeError('Clean source changed during run: '+name)
            artifacts={p.name:{'sha256':capture.sha256_file(p),'bytes':p.stat().st_size}
                       for p in sorted(stage.iterdir()) if p.is_file()}
            receipt={'schema':'native_sequential_read_oblique_v1','complete':True,
                'utc':dt.datetime.now(dt.timezone.utc).isoformat(),'identity':identity,'rank':rank,
                'source':str(source),'output':str(destination),'implementation_and_input_pins':stable,
                'tokenization':tokenization,'changed_tensors':changed,'state_count':len(after),
                'state_inventory':after,'forward_qualification':parity,'sites':sites,
                'fresh_reload':{'verified':True,'head_untied':True,'all_state_tensors_exact':True,
                                'selected_logits_exact':True,'logit_shape':list(actual_logits.shape)},
                'artifacts':artifacts,'runtime':{'torch':torch.__version__,'tf32':False,
                'device':torch.cuda.get_device_name(0)},'claim':'Mechanical publication only; semantic/utility evaluation required'}
            (stage/'read_oblique_publication.json').write_text(json.dumps(receipt,indent=2)+'\n',encoding='utf-8')
            checked._fsync_files(stage);checked._fsync_directory(stage)
            checked._publish_directory_no_replace(stage,destination);checked._fsync_directory(destination.parent)
        except Exception as exc:
            # Preserve unique failed staging evidence; never replace an existing candidate.
            (stage/'FAILED.txt').write_text(type(exc).__name__+': '+str(exc),encoding='utf-8')
            raise
    print('Published '+str(destination),flush=True)
    return receipt


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('clean-model','input-path','support-pins','contract-path','output-dir'):
        parser.add_argument('--'+name,required=True)
    parser.add_argument('--rank',type=int,choices=(1,2),required=True)
    parser.add_argument('--identity',action='store_true')
    parser.add_argument('--qualification-receipt')
    parser.add_argument('--amendment-path')
    arguments=vars(parser.parse_args())
    try:
        run(**arguments)
    except Exception:
        failure=Path(arguments['output_dir']).absolute().with_name(Path(arguments['output_dir']).name+'.failure.json')
        failure.parent.mkdir(parents=True,exist_ok=True)
        if not failure.exists():
            failure.write_text(json.dumps({'complete':False,'arguments':arguments,
                'traceback':traceback.format_exc(),'utc':dt.datetime.now(dt.timezone.utc).isoformat()},indent=2)+'\n',encoding='utf-8')
        raise
