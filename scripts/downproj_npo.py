"""Exact down-projection scope and native checkpoints for a bounded NPO pair."""
import hashlib
import json
import re
from pathlib import Path

import torch


def tensor_sha(tensor):
    return hashlib.sha256(tensor.detach().contiguous().view(torch.uint8).cpu().numpy().tobytes()).hexdigest()


def file_sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def downproj_modules(model, expected_layers=34, expected_shape=(2560, 10240)):
    """Require precisely the unwrapped text MLP output matrices."""
    expected = [f'model.language_model.layers.{i}.mlp.down_proj' for i in range(expected_layers)]
    modules = dict(model.named_modules())
    actual = [name for name in modules if re.fullmatch(r'model\.language_model\.layers\.\d+\.mlp\.down_proj', name)]
    if set(actual) != set(expected):
        raise ValueError('Incomplete or extra text down_proj scope')
    for name in expected:
        module = modules[name]
        if not isinstance(module, torch.nn.Linear) or tuple(module.weight.shape) != tuple(expected_shape) or module.bias is not None:
            raise ValueError(f'Unexpected down_proj geometry: {name}')
    return expected


def parameter_inventory(named):
    return {name: {'shape': list(p.shape), 'dtype': str(p.dtype), 'sha256': tensor_sha(p)}
            for name, p in named}


def setup_student(base, parameterization, expected_layers=34, expected_shape=(2560, 10240)):
    if parameterization not in ('dense', 'lora'):
        raise ValueError('Expected dense or lora')
    modules = downproj_modules(base, expected_layers, expected_shape)
    params = dict(base.named_parameters())
    clean_binding = parameter_inventory((name+'.weight', params[name+'.weight']) for name in modules)
    base.requires_grad_(False)
    if parameterization == 'dense':
        model = base
        for name in modules:
            p = params[name+'.weight']
            p.data = p.data.float()
            p.requires_grad_(True)
        names = [name+'.weight' for name in modules]
    else:
        from peft import LoraConfig, get_peft_model
        model = get_peft_model(base, LoraConfig(r=32, lora_alpha=64, lora_dropout=0,
            target_modules=modules, bias='none', task_type='CAUSAL_LM'))
        names = [f'base_model.model.{name}.lora_{factor}.default.weight'
                 for name in modules for factor in ('A', 'B')]
        for p in model.parameters():
            if p.requires_grad:
                p.data = p.data.float()
        if any(bool(p.detach().count_nonzero()) for name, p in model.named_parameters()
               if name in names and '.lora_B.' in name):
            raise RuntimeError('LoRA B initialization must be exactly zero')
    actual = {name: p for name, p in model.named_parameters() if p.requires_grad}
    if set(actual) != set(names) or any(p.dtype != torch.float32 or not bool(torch.isfinite(p).all()) for p in actual.values()):
        raise RuntimeError('Native FP32 trainable scope mismatch')
    receipt = {'parameterization': parameterization, 'modules': modules,
        'trainable_names': sorted(names), 'trainable_tensors': len(names),
        'trainable_scalars': sum(p.numel() for p in actual.values()),
        'clean_downproj_binding': clean_binding, 'initial_trainables': parameter_inventory(actual.items()),
        'lora_rank': 32 if parameterization == 'lora' else None,
        'lora_alpha': 64 if parameterization == 'lora' else None,
        'zero_B_tensors': len(modules) if parameterization == 'lora' else None}
    model._downproj_npo_setup = receipt
    return model, receipt


def verify_dropout_zero(model):
    for name, module in model.named_modules():
        if isinstance(module, torch.nn.modules.dropout._DropoutNd) and module.p != 0:
            raise ValueError(f'Nonzero dropout: {name}')
        if hasattr(module, 'attention_dropout') and float(module.attention_dropout) != 0:
            raise ValueError(f'Nonzero attention dropout: {name}')
    cfg = getattr(model.config, 'text_config', model.config)
    if float(getattr(cfg, 'attention_dropout', 0)) != 0:
        raise ValueError('Nonzero text attention dropout configuration')


def autocast_forward(model, batch):
    with torch.autocast(device_type=batch[0].device.type, dtype=torch.bfloat16):
        return model(input_ids=batch[0], attention_mask=batch[1], use_cache=False).logits


def save_checkpoint(model, directory, parameterization, clean_binding):
    """Save only native trainables; dense artifacts are not full HF models."""
    from safetensors.torch import load_file, save_file
    directory = Path(directory)
    if directory.exists():
        raise FileExistsError(directory)
    setup = model._downproj_npo_setup
    if parameterization != setup['parameterization'] or clean_binding != setup['clean_downproj_binding']:
        raise ValueError('Checkpoint source binding mismatch')
    native = {name: p.detach().cpu().contiguous() for name, p in model.named_parameters() if p.requires_grad}
    if set(native) != set(setup['trainable_names']) or any(p.dtype != torch.float32 or not bool(torch.isfinite(p).all()) for p in native.values()):
        raise RuntimeError('Checkpoint native scope mismatch')
    directory.mkdir(parents=True, exist_ok=False)
    if parameterization == 'dense':
        filename = 'downproj.safetensors'
        save_file(native, str(directory/filename))
    else:
        filename = 'adapter_model.safetensors'
        model.save_pretrained(directory, safe_serialization=True, save_embedding_layers=False)
        native = {name.replace('.default.weight', '.weight'): p for name, p in native.items()}
    loaded = load_file(str(directory/filename), device='cpu')
    if native.keys() != loaded.keys() or any(loaded[name].dtype != torch.float32 or not torch.equal(p.view(torch.uint8), loaded[name].contiguous().view(torch.uint8)) for name, p in native.items()):
        raise RuntimeError('Native checkpoint reload differs')
    receipt = {'schema': 'downproj_npo_checkpoint_v1', 'parameterization': parameterization,
        'weight_file': filename, 'weight_sha256': file_sha(directory/filename),
        'weight_bytes': (directory/filename).stat().st_size, 'native_fp32_reload_exact': True,
        'tensor_inventory': parameter_inventory(native.items()), 'clean_downproj_binding': clean_binding,
        'modules': setup['modules'], 'trainable_tensors': len(native)}
    if parameterization == 'lora':
        receipt['config_sha256'] = file_sha(directory/'adapter_config.json')
    (directory/'downproj_manifest.json').write_text(json.dumps(receipt, indent=2)+'\n', encoding='utf8')
    return receipt


def load_dense_checkpoint(model, directory):
    """Load into a fresh setup_student(dense) model after source binding checks."""
    from safetensors.torch import load_file
    directory = Path(directory)
    receipt = json.loads((directory/'downproj_manifest.json').read_bytes())
    setup = model._downproj_npo_setup
    if (receipt['parameterization'] != 'dense' or setup['parameterization'] != 'dense'
            or receipt['clean_downproj_binding'] != setup['clean_downproj_binding']
            or receipt['modules'] != setup['modules'] or receipt['weight_file'] != 'downproj.safetensors'):
        raise ValueError('Dense checkpoint source/scope mismatch')
    path = directory/'downproj.safetensors'
    if file_sha(path) != receipt['weight_sha256']:
        raise ValueError('Dense weight hash mismatch')
    saved = load_file(str(path), device='cpu')
    params = dict(model.named_parameters())
    if set(saved) != set(setup['trainable_names']) or parameter_inventory(saved.items()) != receipt['tensor_inventory']:
        raise ValueError('Dense tensor inventory mismatch')
    if any(p.dtype != torch.float32 or not bool(torch.isfinite(p).all()) for p in saved.values()):
        raise ValueError('Dense tensors must be finite FP32')
    with torch.no_grad():
        for name, value in saved.items():
            params[name].copy_(value)
            if tensor_sha(params[name]) != receipt['tensor_inventory'][name]['sha256']:
                raise RuntimeError('Dense native loading changed bytes')
    return receipt
