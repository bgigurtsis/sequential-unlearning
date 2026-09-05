"""Publish fixed -employment and -employment+ordinary LoRA weight deltas."""
import argparse
import json
from pathlib import Path

import torch
from safetensors.torch import load_file, save_file

try:
    from cache_ordinary_preference_reference import file_sha, verify, exclusive_json
except ModuleNotFoundError:
    from scripts.cache_ordinary_preference_reference import file_sha, verify, exclusive_json


def signed_factors(a_f,b_f,a_r=None,b_r=None):
    if (a_r is None)!=(b_r is None):raise ValueError('Both ordinary factors required')
    if a_f.ndim!=2 or b_f.ndim!=2 or a_f.shape[0]!=b_f.shape[1]:
        raise ValueError('Invalid employment factors')
    if a_r is None:return a_f.clone(),-b_f
    if a_f.shape!=a_r.shape or b_f.shape!=b_r.shape:
        raise ValueError('Task vector dimensions must match')
    return torch.cat([a_f,a_r],dim=0),torch.cat([-b_f,b_r],dim=1)


def validate_source_config(config, expected_modules):
    if (config.get('peft_type') != 'LORA' or config.get('task_type') != 'CAUSAL_LM'
            or config.get('r') != 32 or config.get('lora_alpha') != 64
            or config.get('bias') != 'none' or config.get('lora_dropout') != 0):
        raise ValueError('Unsupported source adapter type/scaling/dropout')
    if any(config.get(k) for k in ['fan_in_fan_out', 'use_rslora', 'use_dora',
            'rank_pattern', 'alpha_pattern', 'modules_to_save', 'lora_bias',
            'layer_replication', 'target_parameters', 'exclude_modules',
            'alora_invocation_tokens', 'use_qalora', 'arrow_config']):
        raise ValueError('Unsupported source adapter extension')
    modules = config.get('target_modules')
    if not isinstance(modules, list) or len(modules) != len(expected_modules) or set(modules) != set(expected_modules):
        raise ValueError('Source config must select exactly the qualified text modules')


def main():
    p=argparse.ArgumentParser();p.add_argument('--contract',required=True)
    p.add_argument('--contract-sha256',required=True);args=p.parse_args()
    verify(args.contract,args.contract_sha256)
    contract=json.loads(Path(args.contract).read_bytes())
    source_sha=file_sha(__file__)
    verify(contract['clean_pins_path'],contract['clean_pins_sha256'])
    clean_pins=json.loads(Path(contract['clean_pins_path']).read_bytes())
    torch.set_num_threads(8)
    if contract['employment_coefficient']!=-1 or contract['ordinary_coefficient']!=1:
        raise ValueError('Only precommitted fixed coefficients -1/+1 allowed')
    expected={f'base_model.model.model.language_model.layers.{i}.{branch}.{proj}_proj'
        for i in range(34) for branch,projections in [('self_attn',['q','k','v','o']),('mlp',['gate','up','down'])] for proj in projections}
    expected_keys={module+f'.lora_{factor}.weight' for module in expected for factor in ['A','B']}
    sources=[];configs=[];verified={args.contract:args.contract_sha256,__file__:source_sha,
        contract['clean_pins_path']:contract['clean_pins_sha256']}
    for arm in ['employment','ordinary']:
        spec=contract[arm];directory=Path(spec['path'])
        for kind in ['manifest','completion']:
            verify(spec[kind+'_path'],spec[kind+'_sha256'])
            verified[spec[kind+'_path']]=spec[kind+'_sha256']
        manifest=json.loads(Path(spec['manifest_path']).read_bytes())
        completion=json.loads(Path(spec['completion_path']).read_bytes())
        if (not manifest['zero_initial_B'] or manifest['rank']!=32 or manifest['alpha']!=64
                or completion['steps']!=64 or not completion['exact_native_fp32_reload']
                or not completion['fixed32_source_improved']):
            raise ValueError('Source must be a completed, reinforced native clean-base task vector')
        for name,digest in clean_pins['model_files'].items():
            source_file=manifest['args']['model_id'].rstrip('/')+'/'+name
            if manifest['verified_files'].get(source_file)!=digest:
                raise ValueError('Task vectors do not share the pinned clean base')
        for name,key in [('adapter_model.safetensors','weight_sha256'),('adapter_config.json','config_sha256')]:
            verify(directory/name,spec[key]);verified[str(directory/name)]=spec[key]
            if completion['saved'][name]!=spec[key]:
                raise ValueError('Checkpoint differs from its completed training receipt')
        config=json.loads((directory/'adapter_config.json').read_bytes())
        validate_source_config(config,{m.removeprefix('base_model.model.') for m in expected})
        weights=load_file(str(directory/'adapter_model.safetensors'),device='cpu')
        if set(weights)!=expected_keys or any(v.dtype!=torch.float32 or not bool(torch.isfinite(v).all()) for v in weights.values()):
            raise ValueError('Expected476 finite FP32 tensors')
        sources.append(weights);configs.append(config)
    left,right=sources
    if left.keys()!=right.keys():raise ValueError('Different source tensor names')
    modules={k.removesuffix('.lora_A.weight') for k in left if k.endswith('.lora_A.weight')}
    if modules!=expected:raise ValueError('Wrong text module scope')
    output=Path(contract['output']);output.mkdir(parents=True,exist_ok=False)
    receipt={'contract_sha256':args.contract_sha256,'source_sha256':source_sha,
             'sources':{k:contract[k] for k in ['employment','ordinary']},'candidates':[]}
    for mode in ['direct','contrastive']:
        merged={};errors=[];rng=torch.Generator().manual_seed(34018)
        for module in sorted(modules):
            ak,bk=module+'.lora_A.weight',module+'.lora_B.weight'
            af,bf,ar,br=left[ak],left[bk],right[ak],right[bk]
            if af.shape[0]!=32 or bf.shape[1]!=32:raise ValueError('Wrong source rank')
            a,b=signed_factors(af,bf,ar if mode=='contrastive' else None,br if mode=='contrastive' else None)
            x=torch.randn(4,a.shape[1],generator=rng)
            actual=2*((x@a.T)@b.T)
            ref=-2*((x@af.T)@bf.T)
            if mode=='contrastive':ref=ref+2*((x@ar.T)@br.T)
            torch.testing.assert_close(actual,ref,rtol=2e-5,atol=2e-6)
            errors.append(float((actual-ref).abs().max()))
            merged[ak],merged[bk]=a.contiguous(),b.contiguous()
        directory=output/mode;directory.mkdir()
        config=dict(configs[0]);rank=32 if mode=='direct' else 64
        config.update(r=rank,lora_alpha=2*rank,target_modules=[m.removeprefix('base_model.model.') for m in sorted(modules)])
        exclusive_json(directory/'adapter_config.json',config)
        save_file(merged,str(directory/'adapter_model.safetensors'),metadata={'format':'pt'})
        restored=load_file(str(directory/'adapter_model.safetensors'),device='cpu')
        if restored.keys()!=merged.keys() or any(not torch.equal(v,restored[k]) for k,v in merged.items()):raise RuntimeError('Saved factor identity failed')
        receipt['candidates'].append({'mode':mode,'path':str(directory),'rank':rank,'alpha':2*rank,
            'weight_sha256':file_sha(directory/'adapter_model.safetensors'),
            'config_sha256':file_sha(directory/'adapter_config.json'),
            'weight_bytes':(directory/'adapter_model.safetensors').stat().st_size,
            'finite_fp32_tensors':476,'exact_factor_reload':True,'max_four_vector_error':max(errors)})
    for path,sha in verified.items():verify(path,sha)
    receipt['all_source_files_reverified_after_construction']=True
    receipt['scope']='Only238 text projections/476 LoRA tensors; no vision, embedding, bias or other model tensors edited.'
    exclusive_json(output/'construction_receipt.json',receipt)
    print(json.dumps(receipt,indent=2))


if __name__=='__main__':main()
