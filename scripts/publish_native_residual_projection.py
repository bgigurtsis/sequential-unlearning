"""Publish a norm-aware global residual-range restriction of pinned clean weights.

Uses existing qualified immutable-publication and exact-reload infrastructure,
but declares its own69-tensor surface. No behavioral success is inferred here.
"""
from __future__ import annotations
import argparse
import datetime as dt
import json
import tempfile
from pathlib import Path

try:
    import apply_checkpoint_delta_dare as checked
    import blend_checkpoint_projection as reload_tools
    import native_residual_projection_math as math
except ModuleNotFoundError:
    from scripts import apply_checkpoint_delta_dare as checked
    from scripts import blend_checkpoint_projection as reload_tools
    from scripts import native_residual_projection_math as math

PREFIX = 'language_model.model'
EMBEDDING = PREFIX + '.embed_tokens.weight'
FINAL_NORM = PREFIX + '.norm.weight'


def edit_surface():
    result = {EMBEDDING: None}
    for index in range(34):
        layer = f'{PREFIX}.layers.{index}'
        result[layer + '.self_attn.o_proj.weight'] = layer + '.post_attention_layernorm.weight'
        result[layer + '.mlp.down_proj.weight'] = layer + '.post_feedforward_layernorm.weight'
    return result


def verify_locality(before, after, *, identity=False):
    if set(before) != set(after):
        raise ValueError('Output namespace changed')
    surface = edit_surface()
    if not set(surface) <= set(before):
        raise ValueError('Missing declared69-tensor surface')
    changed = []
    for name, original in before.items():
        result = after[name]
        if original['shape'] != result['shape'] or original['dtype'] != result['dtype']:
            raise ValueError('Tensor shape or dtype changed: ' + name)
        if original['sha256'] != result['sha256']:
            if identity or name not in surface:
                raise ValueError('Changed undeclared tensor: ' + name)
            changed.append(name)
    return sorted(changed)


def validate_surface(snapshot, torch, runtime):
    inventory = snapshot.tensor_inventory
    if len(inventory) != 883:
        raise ValueError('Expected883 serialized clean tensors')
    for key, norm in edit_surface().items():
        if key not in inventory or inventory[key]['dtype'] != 'torch.bfloat16':
            raise ValueError('Missing BF16 edit tensor: ' + key)
        shape = inventory[key]['shape']
        if len(shape) != 2 or shape[1 if norm is None else 0] != 2560:
            raise ValueError('Invalid edit dimension: ' + key)
        if key.removesuffix('.weight') + '.bias' in inventory:
            raise ValueError('Biased write outside frozen method')
        if norm is not None and inventory[norm]['shape'] != [2560]:
            raise ValueError('Wrong normalization shape')
    return checked._load_tensor(snapshot, FINAL_NORM, runtime).double() + 1


def publish(clean_model, basis, basis_sha256, output_dir, support_pins, *, concept_rank=4, identity=False):
    if isinstance(concept_rank, bool) or concept_rank not in (1, 4):
        raise ValueError('Only precommitted rank1 and rank4 arms are allowed')
    runtime = checked.production_runtime()
    torch = runtime.torch
    torch.set_num_threads(8)
    torch.backends.cuda.matmul.allow_tf32 = False
    torch.backends.cudnn.allow_tf32 = False
    torch.set_float32_matmul_precision('highest')
    source = Path(clean_model).resolve()
    destination = Path(output_dir).absolute()
    if checked._path_lexists(destination):
        raise FileExistsError(destination)
    if source.is_relative_to(destination.resolve()) or destination.resolve().is_relative_to(source):
        raise ValueError('Source/output paths overlap')
    pins_path = Path(support_pins)
    pins_hash = checked.sha256_file(pins_path)
    pins = json.loads(pins_path.read_bytes())
    for filename, expected in pins.items():
        if Path(filename).name != filename or checked.sha256_file(source / filename) != expected:
            raise ValueError('Pinned support differs: ' + filename)
    clean = checked.scan_checkpoint(source, label='clean', runtime=runtime)
    if dict(clean.weight_hashes) != checked.PINNED_CLEAN_WEIGHT_HASHES:
        raise ValueError('Clean model weights differ from frozen pins')
    final_scale = validate_surface(clean, torch, runtime)
    if checked.sha256_file(basis) != basis_sha256:
        raise ValueError('Fitted basis hash mismatch')
    with runtime.safe_open(str(basis), framework='pt', device='cpu') as handle:
        u, v = handle.get_tensor('U'), handle.get_tensor('V')
    if u.shape != (2560, concept_rank) or u.dtype != torch.float64 or v.dtype != torch.float64 or v.ndim != 2 or v.shape[0] != 2560 or not concept_rank <= v.shape[1] <= 2 * concept_rank:
        raise ValueError('Basis differs from declared rank and closure contract')
    expected_v, closure = math.closure_basis(u, final_scale, torch=torch)
    math._basis(v, torch=torch)
    if expected_v.shape != v.shape or float(torch.linalg.vector_norm(expected_v - v @ (v.T @ expected_v))) > 1e-10:
        raise ValueError('Supplied closure span differs from clean final norm closure')
    if identity:
        v = torch.empty(2560, 0, dtype=torch.float64)
    support = checked.selected_file_manifest(source, names=set(pins), chat_templates=True)
    before_reload = checked.verify_hf_text_reload(source)
    before_tokenizer = checked.verify_tokenizer_reload_contract(before_reload, label='clean')
    implementation = [{'path': str(Path(p).resolve()), 'sha256': checked.sha256_file(p)}
                      for p in (Path(__file__), Path(math.__file__), Path(checked.__file__),
                                Path(reload_tools.__file__), Path(reload_tools.model_checks.__file__))]
    destination.parent.mkdir(parents=True, exist_ok=True)
    prefix = '.' + destination.name + '.staging-'
    stage = Path(tempfile.mkdtemp(prefix=prefix, dir=destination.parent))
    published = False
    try:
        records = []
        surface = edit_surface()
        for filename in sorted(clean.weight_hashes):
            if identity:
                checked._copy_file_exclusive(source / filename, stage / filename)
                continue
            with runtime.safe_open(str(source / filename), framework='pt', device='cpu') as handle:
                tensors = {}
                for name in sorted(handle.keys()):
                    tensor = handle.get_tensor(name)
                    if name == EMBEDDING:
                        tensor, diagnostics = math.project_embedding(tensor, v, torch=torch, device='cuda:0')
                    elif name in surface:
                        scale = checked._load_tensor(clean, surface[name], runtime).double() + 1
                        tensor, diagnostics = math.project_write(tensor, scale, v, torch=torch, device='cuda:0')
                    if name in surface:
                        records.append({'name': name, 'output_sha256': checked._tensor_sha256(tensor, torch), 'diagnostics': diagnostics})
                        print('Projected', name, flush=True)
                    tensors[name] = tensor
                runtime.save_file(tensors, str(stage / filename), metadata=handle.metadata())
                del tensors
        checked._copy_manifest(source, support, stage)
        output = checked.scan_checkpoint(stage, label='output', runtime=runtime)
        changed = verify_locality(clean.tensor_inventory, output.tensor_inventory, identity=identity)
        for record in records:
            if record['output_sha256'] != output.tensor_inventory[record['name']]['sha256']:
                raise RuntimeError('Serialized edited tensor differs from projection')
        if identity and dict(output.weight_hashes) != dict(clean.weight_hashes):
            raise RuntimeError('Native identity file hash differs')
        after_reload = checked.verify_hf_text_reload(stage)
        if checked.verify_tokenizer_reload_contract(after_reload, label='output') != before_tokenizer:
            raise RuntimeError('Standalone tokenizer changed')
        fresh = reload_tools.verify_fresh_model_reload(stage, runtime)
        if not fresh.get('verified'):
            raise RuntimeError('Fresh model reload not verified')
        if not checked._unchanged_weight_hashes(clean) or not checked._manifest_unchanged(source, support):
            raise RuntimeError('Source changed during publication')
        if checked.sha256_file(basis) != basis_sha256 or checked.sha256_file(pins_path) != pins_hash:
            raise RuntimeError('Basis or pins changed')
        if any(checked.sha256_file(p['path']) != p['sha256'] for p in implementation):
            raise RuntimeError('Implementation changed during publication')
        payload = {'schema': 'native_residual_range_publication_v1', 'utc': dt.datetime.now(dt.timezone.utc).isoformat(),
                   'identity': identity, 'concept_rank': concept_rank, 'clean_source': str(source), 'clean_weight_hashes': dict(clean.weight_hashes),
                   'source_logical_sha256': clean.logical_inventory_sha256, 'basis_path': str(Path(basis).resolve()),
                   'basis_sha256': basis_sha256, 'closure': closure, 'support_pins': pins, 'support_pins_sha256': pins_hash,
                   'output': str(destination), 'output_weight_hashes': dict(output.weight_hashes),
                   'output_logical_sha256': output.logical_inventory_sha256, 'changed_tensors': changed,
                   'tensor_count': output.logical_tensor_count, 'tensor_diagnostics': records, 'fresh_reload': fresh,
                   'implementation': implementation, 'runtime': dict(runtime.versions), 'tf32': False,
                   'claim': 'Mechanical native weight range restriction only; BF16 forward leakage, behavior and cumulative damage remain untested.'}
        envelope = checked.immutable_envelope(payload)
        checked.write_immutable_json(stage / 'native_residual_projection.json', envelope)
        checked._fsync_files(stage)
        checked._fsync_directory(stage)
        checked._publish_directory_no_replace(stage, destination)
        published = True
        checked._fsync_directory(destination.parent)
        return envelope
    finally:
        if not published:
            checked._remove_private_stage(stage, destination.parent, prefix)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for argument in ('clean-model', 'basis', 'basis-sha256', 'output-dir', 'support-pins'):
        parser.add_argument('--' + argument, required=True)
    parser.add_argument('--identity', action='store_true')
    parser.add_argument('--concept-rank', type=int, choices=(1, 4), default=4)
    result = publish(**vars(parser.parse_args()))
    print('Published', result['payload_sha256'], flush=True)
