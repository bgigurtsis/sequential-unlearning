"""One native PEFT adapter: frozen CE64 text factors plus an output-only delta.

The tied base embedding/head is never merged or optimized. Only the two new
lm_head factors are trainable; serialization explicitly excludes base weights.
"""
import copy
import hashlib
from pathlib import Path

try:
    from prefix_unfamiliarity_training import validate_initial_adapter_config
    from wide_unfamiliarity_training import text_only_fullband_modules
except ModuleNotFoundError:
    from scripts.prefix_unfamiliarity_training import validate_initial_adapter_config
    from scripts.wide_unfamiliarity_training import text_only_fullband_modules


def _file_sha(path):
    with Path(path).open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def _tensor_sha(value):
    """Hash native bytes in bounded row chunks, including signed zero bits."""
    import torch
    digest = hashlib.sha256()
    flat = value.detach().reshape(-1)
    for begin in range(0, flat.numel(), 1048576):
        chunk = flat[begin:begin + 1048576].cpu().contiguous()
        digest.update(chunk.view(torch.uint8).numpy().tobytes())
    return digest.hexdigest()


def _native_equal(left, right):
    import torch
    if left.dtype != torch.float32 or right.dtype != torch.float32 or left.shape != right.shape:
        return False
    return torch.equal(left.detach().cpu().contiguous().view(torch.uint8),
                       right.detach().cpu().contiguous().view(torch.uint8))


def _state(model):
    from peft import get_peft_model_state_dict
    return get_peft_model_state_dict(model, save_embedding_layers=False)


def _tied_base(model):
    embedding = model.get_input_embeddings().weight
    output = model.get_output_embeddings().weight
    if embedding is not output:
        raise RuntimeError('Expected the identical tied base input/output Parameter')
    if embedding.requires_grad:
        raise RuntimeError('Base input/output embedding must remain frozen')
    return embedding


def load_parent_with_head(base, parent_path, head_rank):
    """Return (model, receipt), preserving all476 parent factors exactly.

    ``base`` is the clean, unwrapped Gemma3-shaped model. Only head ranks8/32
    are admitted. The model receives private provenance used by the guards.
    """
    import torch
    from peft import LoraConfig, get_peft_model
    from safetensors.torch import load_file
    if isinstance(head_rank, bool) or head_rank not in (8, 32):
        raise ValueError('Only fixed head ranks8 and32 are qualified')
    if hasattr(base, 'peft_config'):
        raise ValueError('Expected an unwrapped clean base')
    parent_path = Path(parent_path).resolve()
    source_paths = {name: parent_path / name for name in
                    ('adapter_model.safetensors', 'adapter_config.json')}
    source_hashes = {name: _file_sha(path) for name, path in source_paths.items()}
    modules = text_only_fullband_modules(base.named_modules())
    universe = dict(base.named_modules())
    if universe.get('lm_head') is not base.get_output_embeddings():
        raise ValueError('Expected exact top-level lm_head module')
    if base.get_input_embeddings().weight is not base.get_output_embeddings().weight:
        raise ValueError('Expected native tied input/output base weights')
    config = LoraConfig.from_pretrained(str(parent_path))
    validate_initial_adapter_config(config, rank=32, alpha=64,
        selected_modules=modules, available_module_names=universe)
    for flag in ('ensure_weight_tying', 'lora_bias', 'use_qalora', 'use_bdlora'):
        if getattr(config, flag, False):
            raise ValueError('Unsupported parent option: ' + flag)
    source = load_file(str(source_paths['adapter_model.safetensors']), device='cpu')
    expected = {'base_model.model.' + name + '.lora_' + factor + '.weight'
                for name in modules for factor in ('A', 'B')}
    if set(source) != expected or len(source) != 476:
        raise ValueError('Expected exactly476 parent text factors')
    if any(v.dtype != torch.float32 or not bool(torch.isfinite(v).all()) for v in source.values()):
        raise ValueError('Parent factors must be finite FP32')
    combined = copy.deepcopy(config)
    combined.target_modules = set(modules) | {'lm_head'}
    combined.rank_pattern = {'lm_head': head_rank}
    combined.alpha_pattern = {'lm_head': 2 * head_rank}
    combined.ensure_weight_tying = False
    combined.inference_mode = False
    model = get_peft_model(base, combined)
    # PEFT may compress serialized selectors. Keep the output config canonical.
    model.peft_config['default'].target_modules = set(modules) | {'lm_head'}
    for name, parameter in model.named_parameters():
        parameter.requires_grad_(False)
        if '.lora_' in name:
            parameter.data = parameter.data.float()
    actual = _state(model)
    head_keys = {'base_model.model.lm_head.lora_' + f + '.weight' for f in ('A', 'B')}
    if set(actual) != expected | head_keys or len(actual) != 478:
        raise RuntimeError('Combined adapter must contain478 factors, including only2 new head factors')
    with torch.no_grad():
        for name, value in source.items():
            if actual[name].shape != value.shape:
                raise RuntimeError('Parent shape mismatch: ' + name)
            actual[name].copy_(value.to(actual[name].device))
    head = model.get_output_embeddings()
    if head.r['default'] != head_rank or head.scaling['default'] != 2:
        raise RuntimeError('Head rank/scaling mismatch')
    if torch.count_nonzero(head.lora_B['default'].weight).item() != 0:
        raise RuntimeError('Initial head B must be zero')
    head.lora_A['default'].weight.requires_grad_(True)
    head.lora_B['default'].weight.requires_grad_(True)
    embedding = _tied_base(model)
    trainables = [n for n, p in model.named_parameters() if p.requires_grad]
    required_trainables = {'base_model.model.lm_head.lora_' + f + '.default.weight' for f in ('A', 'B')}
    if set(trainables) != required_trainables:
        raise RuntimeError('Only2 head factors may be trainable')
    model._output_head_repair = {
        'parent_path': str(parent_path), 'source_hashes': source_hashes,
        'text_modules': modules, 'head_rank': head_rank,
        'head_parameter_names': sorted(required_trainables),
        'embedding_sha256': _tensor_sha(embedding),
        'embedding_parameter_identity': id(embedding),
    }
    guard = assert_frozen_parent(model, parent_path)
    receipt = {**guard, 'parent_path': str(parent_path), 'source_hashes': source_hashes,
               'head_rank': head_rank, 'head_alpha': 2 * head_rank,
               'initial_head_B_zero': True, 'initial_output_delta_zero': True,
               'head_parameter_names': sorted(required_trainables),
               'save_embedding_layers': False, 'merge_allowed': False}
    return model, receipt


def assert_frozen_parent(model, parent_path):
    """Verify source files, exact476 frozen factors, trainable scope and embedding."""
    import torch
    from safetensors.torch import load_file
    info = getattr(model, '_output_head_repair', None)
    if info is None or Path(parent_path).resolve() != Path(info['parent_path']):
        raise ValueError('Missing or mismatched parent provenance')
    for name, digest in info['source_hashes'].items():
        if _file_sha(Path(parent_path) / name) != digest:
            raise RuntimeError('Parent source changed: ' + name)
    source = load_file(str(Path(parent_path) / 'adapter_model.safetensors'), device='cpu')
    actual = _state(model)
    head_keys = {'base_model.model.lm_head.lora_' + f + '.weight' for f in ('A', 'B')}
    if len(actual) != 478 or set(actual) != set(source) | head_keys:
        raise RuntimeError('Adapter inventory changed')
    for name, value in source.items():
        if not _native_equal(actual[name], value):
            raise RuntimeError('Frozen parent factor changed: ' + name)
    if any(v.dtype != torch.float32 or not bool(torch.isfinite(v).all()) for v in actual.values()):
        raise FloatingPointError('Expected478 finite FP32 factors')
    trainables = sorted(n for n, p in model.named_parameters() if p.requires_grad)
    if trainables != info['head_parameter_names']:
        raise RuntimeError('Trainable scope changed beyond head factors')
    head = model.get_output_embeddings()
    if getattr(head, 'merged', False):
        raise RuntimeError('Head merge prohibited while input/output weight is tied')
    embedding = _tied_base(model)
    if id(embedding) != info['embedding_parameter_identity'] or _tensor_sha(embedding) != info['embedding_sha256']:
        raise RuntimeError('Frozen input/output embedding changed')
    return {'parent_native_factor_count': 476, 'parent_native_bytes_unchanged': True,
            'serialized_factor_count': 478, 'text_modules': 238,
            'trainable_head_factor_count': 2, 'all_factors_finite_fp32': True,
            'input_embedding_sha256': info['embedding_sha256'],
            'input_embedding_unchanged': True, 'base_input_output_still_tied': True}


def save_head_adapter(model, directory, parent_path):
    """Save one immutable478-factor adapter and verify native serialization."""
    from safetensors.torch import load_file
    directory = Path(directory)
    if directory.exists():
        raise FileExistsError(directory)
    guard = assert_frozen_parent(model, parent_path)
    actual = _state(model)
    model.save_pretrained(str(directory), safe_serialization=True, save_embedding_layers=False)
    restored = load_file(str(directory / 'adapter_model.safetensors'), device='cpu')
    if set(restored) != set(actual) or any(not _native_equal(restored[k], v) for k, v in actual.items()):
        raise RuntimeError('Saved combined adapter differs from native478 factors')
    assert_frozen_parent(model, parent_path)
    return {'path': str(directory), 'weight_sha256': _file_sha(directory / 'adapter_model.safetensors'),
            'config_sha256': _file_sha(directory / 'adapter_config.json'),
            'weight_bytes': (directory / 'adapter_model.safetensors').stat().st_size,
            'exact_native_fp32_reload': True, 'save_embedding_layers': False, **guard}
