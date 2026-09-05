"""Blend the pinned dense donor toward the already rounded, pinned E90 model.

This separate experiment does not change the closed E90/E95/E99 ladder. Each
candidate is donor + beta * (published_E90 - donor), in FP32 with one BF16 cast.
Only the existing 98 serialized canonical linear weights may change. Beta zero
copies donor files natively; no training or evaluation text enters this tool.
"""
from __future__ import annotations

import argparse
import datetime as dt
import gc
import math
import os
import tempfile
from pathlib import Path

try:
    import apply_checkpoint_delta_dare as checked
    import apply_causal_mlp_mask as model_checks
except ModuleNotFoundError:
    from scripts import apply_checkpoint_delta_dare as checked
    from scripts import apply_causal_mlp_mask as model_checks

SIDECAR_NAME = "checkpoint_projection_blend.json"
BETAS = (0.0, 0.1, 0.25, 0.5, 0.75)
E90_WEIGHT_SHA256 = "55ed6601e79736b8b895af1d202d46ac3c660e62ec0e88d4957218ee7c4dfd9c"
E90_PAYLOAD_SHA256 = "e114ef7a51eb2f47d19e38bfadd9c9439cf57566efa072b773f5b855ead6742d"
E90_SIDECAR_NAME = "retain_subspace_delta_projection.json"


def validate_beta(value, *, endpoint_test=False):
    if isinstance(value, bool):
        raise ValueError("beta must be a precommitted finite coefficient")
    try:
        beta = float(value)
    except (TypeError, ValueError) as error:
        raise ValueError("beta must be a precommitted finite coefficient") from error
    allowed = BETAS + ((1.0,) if endpoint_test else ())
    if not math.isfinite(beta) or beta not in allowed:
        raise ValueError("beta must be a precommitted finite coefficient")
    return beta


def blend_tensor(donor, projected, beta, *, torch, device="cpu", chunk_elements=1048576):
    """Native endpoint identities and explicitly ordered, chunked FP32 blending."""
    beta = validate_beta(beta, endpoint_test=True)
    chunk_elements = checked._positive_chunk_elements(chunk_elements)
    if donor.shape != projected.shape or donor.dtype != projected.dtype:
        raise ValueError("blend endpoint tensor shape/dtype mismatch")
    if donor.dtype != torch.bfloat16 or donor.ndim != 2:
        raise ValueError("blend endpoints must be two-dimensional BF16 linears")
    checked._assert_tensor_finite("weight", donor, torch, "donor")
    checked._assert_tensor_finite("weight", projected, torch, "projected")
    result = torch.empty_like(donor, device="cpu")
    before_norm = checked._new_norm_accumulator()
    requested_norm = checked._new_norm_accumulator()
    realized_norm = checked._new_norm_accumulator()
    donor_flat, projected_flat, output_flat = donor.reshape(-1), projected.reshape(-1), result.reshape(-1)
    for start in range(0, donor.numel(), chunk_elements):
        end = start + chunk_elements
        left_native = donor_flat[start:end].to(device)
        right_native = projected_flat[start:end].to(device)
        left, right = left_native.float(), right_native.float()
        direction = right - left
        requested = beta * direction
        if beta == 0:
            value = left_native
        elif beta == 1:
            value = right_native
        else:
            value = (left + requested).to(donor.dtype)
        checked._assert_tensor_finite("weight", value, torch, "blend output")
        output_flat[start:end] = value.cpu()
        checked._update_norm(before_norm, direction, torch)
        checked._update_norm(requested_norm, requested, torch)
        checked._update_norm(realized_norm, value.float() - left, torch)
    return result, {
        "endpoint_direction_norm": checked._finish_norm(before_norm),
        "requested_distance_from_donor": checked._finish_norm(requested_norm),
        "realized_distance_from_donor": checked._finish_norm(realized_norm),
        "output_sha256": checked._tensor_sha256(result, torch),
    }


def verify_endpoints(clean, donor, projected, *, source_contract, e90_weight_sha256):
    checked.verify_source_contract(clean, donor, source_contract)
    if projected.weight_hashes != {"model.safetensors": e90_weight_sha256}:
        raise ValueError("projected endpoint weight hash does not match pinned E90")
    if checked.sha256_file(projected.root / "config.json") != source_contract.edited_config_sha256:
        raise ValueError("projected endpoint configuration differs from pinned donor")
    # Exact canonical serialized keys only: no suffix matching, guessed prefix
    # stripping or silent alias omission is permitted.
    donor_proof = checked.verify_declared_delta_surface(clean.tensor_inventory, donor.tensor_inventory)
    projected_proof = checked.verify_declared_delta_surface(clean.tensor_inventory, projected.tensor_inventory)
    checked.verify_output_locality(donor.tensor_inventory, projected.tensor_inventory)
    return {"donor": donor_proof, "projected": projected_proof, "canonical_namespace": "exact_serialized_key_equality"}


def _write_blended_weights(donor, projected, stage, beta, runtime, device, chunk_elements):
    records = []
    if beta == 0:
        for filename in donor.weight_hashes:
            checked._copy_file_exclusive(donor.root / filename, stage / filename)
    else:
        declared = set(checked.DECLARED_EDIT_KEYS)
        for filename in sorted(donor.weight_hashes):
            with runtime.safe_open(str(donor.root / filename), framework="pt", device="cpu") as handle:
                tensors = {}
                for key in sorted(handle.keys()):
                    left = handle.get_tensor(key)
                    if key in declared:
                        right = checked._load_tensor(projected, key, runtime)
                        value, diagnostics = blend_tensor(left, right, beta, torch=runtime.torch, device=device, chunk_elements=chunk_elements)
                        records.append({"tensor_name": key, **diagnostics})
                        tensors[key] = value
                    else:
                        tensors[key] = left
                runtime.save_file(tensors, str(stage / filename), metadata=donor.file_metadata.get(filename))
    index = donor.root / "model.safetensors.index.json"
    if index.is_file():
        checked._copy_file_exclusive(index, stage / index.name)
    if beta == 0:
        records = [{"tensor_name": key, "output_sha256": donor.tensor_inventory[key]["sha256"], "native_identity": True}
                   for key in checked.DECLARED_EDIT_KEYS]
    return sorted(records, key=lambda record: record["tensor_name"])


def _snapshot_record(snapshot):
    return {"path": str(snapshot.root), "weight_file_sha256": dict(snapshot.weight_hashes),
            "tensor_inventory": dict(snapshot.tensor_inventory),
            "logical_inventory_sha256": snapshot.logical_inventory_sha256,
            "key_to_file": dict(snapshot.key_to_file), "tensor_count": snapshot.logical_tensor_count,
            "total_value_bytes": snapshot.logical_total_value_bytes}


def verify_fresh_model_reload(root, runtime):
    """Load a separate HF model and prove serialized values through tied aliases."""
    from transformers import Gemma3ForConditionalGeneration
    model = Gemma3ForConditionalGeneration.from_pretrained(
        str(root), dtype=runtime.torch.bfloat16, device_map="cpu",
        local_files_only=True, trust_remote_code=False)
    try:
        model.eval()
        inventory, inventory_hash, aliases = model_checks.model_tensor_inventory(model, runtime.torch)
        namespace = model_checks.namespace_mapping_contract_for_model(model)
        proof = model_checks.verify_saved_model_tensors(
            root, inventory, aliases, namespace, safe_open=runtime.safe_open, torch=runtime.torch)
        return {"verified": True, "state_inventory_sha256": inventory_hash,
                "state_tensor_count": len(inventory), "aliases": aliases,
                "serialized_namespace_proof": proof}
    finally:
        del model
        gc.collect()


def apply_blend(*, clean_model, donor_model, projected_model, tokenizer_model, output_dir,
                beta, device="cpu", chunk_elements=1048576, runtime=None, strict_git=True,
                source_contract=checked.PINNED_SOURCE_CONTRACT, e90_weight_sha256=E90_WEIGHT_SHA256,
                e90_payload_sha256=E90_PAYLOAD_SHA256, reload_verifier=None, model_reload_verifier=None):
    beta = validate_beta(beta)
    chunk_elements = checked._positive_chunk_elements(chunk_elements)
    roots = [checked._exact_local_directory(path, label) for path, label in
             ((clean_model, "clean"), (donor_model, "donor"), (projected_model, "projected"))]
    clean_root, donor_root, projected_root = roots
    if len(set(roots)) != 3:
        raise ValueError("clean, donor and projected endpoints must be distinct directories")
    tokenizer_root = checked._exact_local_directory(tokenizer_model, "tokenizer")
    if tokenizer_root != clean_root:
        raise ValueError("tokenizer must be the exact clean checkpoint directory")
    destination = Path(output_dir).absolute()
    if checked._path_lexists(destination):
        raise FileExistsError(f"refusing to replace existing output: {destination}")
    for root in roots:
        if destination.resolve().is_relative_to(root):
            raise ValueError("output cannot be inside a source endpoint")
    implementations = [Path(__file__).resolve(), Path(checked.__file__).resolve(), Path(model_checks.__file__).resolve(),
                       Path(model_checks.attribution.__file__).resolve(), Path(model_checks.attribution.selection.__file__).resolve(),
                       Path(__file__).with_name("test_blend_checkpoint_projection.py").resolve()]
    implementation = [{"path": str(path), "sha256": checked.sha256_file(path),
                       "git": checked.git_provenance(path, strict=strict_git)} for path in implementations]
    runtime = runtime or checked.production_runtime()
    e90_sidecar = projected_root / E90_SIDECAR_NAME
    e90_provenance = checked.load_immutable_json(e90_sidecar)
    if e90_provenance["payload_sha256"] != e90_payload_sha256:
        raise ValueError("projected endpoint sidecar differs from pinned E90 payload")
    e90_sidecar_hash = checked.sha256_file(e90_sidecar)
    clean, donor, projected = [checked.scan_checkpoint(root, label=label, runtime=runtime)
                              for root, label in zip(roots, ("clean", "donor", "projected"))]
    proof = verify_endpoints(clean, donor, projected, source_contract=source_contract, e90_weight_sha256=e90_weight_sha256)
    configs = checked.verify_model_configs(clean_root, donor_root, source_contract)
    model_support = checked.selected_file_manifest(donor_root, names=checked.MODEL_SUPPORT_NAMES)
    tokenizer_support = checked.selected_file_manifest(clean_root, names=checked.TOKENIZER_NAMES, chat_templates=True)
    if not any(r["path"] in {"tokenizer.json", "tokenizer.model", "spiece.model"} for r in tokenizer_support["files"]):
        raise ValueError("clean source lacks standalone tokenizer artifact")
    reload_verifier = reload_verifier or checked.verify_hf_text_reload
    source_reload = dict(reload_verifier(clean_root))
    source_tokenizer = checked.verify_tokenizer_reload_contract(source_reload, label="clean")
    if source_reload.get("model_type") != source_contract.model_type:
        raise ValueError("clean reload model type mismatch")
    destination.parent.mkdir(parents=True, exist_ok=True)
    prefix = f".{destination.name}.tmp-"
    stage = Path(tempfile.mkdtemp(prefix=prefix, dir=destination.parent))
    published = False
    try:
        records = _write_blended_weights(donor, projected, stage, beta, runtime, device, chunk_elements)
        checked._copy_manifest(donor_root, model_support, stage)
        checked._copy_manifest(clean_root, tokenizer_support, stage)
        output = checked.scan_checkpoint(stage, label="output", runtime=runtime)
        changed = checked.verify_output_locality(clean.tensor_inventory, output.tensor_inventory)
        if set(changed) != set(checked.DECLARED_EDIT_KEYS):
            raise RuntimeError("output no longer changes exactly the declared 98 linears")
        checked.verify_output_locality(donor.tensor_inventory, output.tensor_inventory)
        if output.key_to_file != donor.key_to_file:
            raise RuntimeError("output changed canonical shard/key layout")
        if [r["tensor_name"] for r in records] != sorted(checked.DECLARED_EDIT_KEYS):
            raise RuntimeError("incomplete tensor application records")
        for record in records:
            key = record["tensor_name"]
            if record["output_sha256"] != output.tensor_inventory[key]["sha256"]:
                raise RuntimeError("serialized output differs from blended tensor")
            record["donor_sha256"] = donor.tensor_inventory[key]["sha256"]
            record["projected_sha256"] = projected.tensor_inventory[key]["sha256"]
        if beta == 0 and (output.weight_hashes != donor.weight_hashes or output.tensor_inventory != donor.tensor_inventory):
            raise RuntimeError("beta zero failed native donor identity")
        if beta != 0 and output.tensor_inventory == donor.tensor_inventory:
            raise RuntimeError("nonzero blend unexpectedly reproduced donor")
        output_reload = dict(reload_verifier(stage))
        if output_reload.get("model_type") != source_contract.model_type or checked.verify_tokenizer_reload_contract(output_reload, label="output") != source_tokenizer:
            raise RuntimeError("output config/tokenizer reload mismatch")
        fresh_model_reload = (model_reload_verifier or verify_fresh_model_reload)(stage, runtime)
        if not fresh_model_reload.get("verified"):
            raise RuntimeError("fresh model reload did not verify")
        for snapshot in (clean, donor, projected):
            if not checked._unchanged_weight_hashes(snapshot):
                raise RuntimeError("source weights changed during blend")
        if not checked._manifest_unchanged(donor_root, model_support) or not checked._manifest_unchanged(clean_root, tokenizer_support):
            raise RuntimeError("source support files changed during blend")
        if checked.sha256_file(projected_root / "config.json") != source_contract.edited_config_sha256:
            raise RuntimeError("projected config changed during blend")
        if checked.sha256_file(e90_sidecar) != e90_sidecar_hash:
            raise RuntimeError("projected provenance changed during blend")
        for path, before in zip(implementations, implementation):
            if checked.sha256_file(path) != before["sha256"] or (strict_git and checked.git_provenance(path, strict=True) != before["git"]):
                raise RuntimeError("implementation changed during blend")
        payload = {"schema_version": "pinned_projection_endpoint_blend_v1", "created_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
                   "request": {"beta": beta, "device": device, "chunk_elements": chunk_elements, "output_dir": str(destination)},
                   "method": {"equation": "BF16(donor.float32 + beta * (published_E90.float32 - donor.float32))", "beta_zero": "native donor file copy", "projected_endpoint_is_already_BF16": True,
                              "precommitted_betas": list(BETAS), "training_inputs": [], "claim_boundary": "behavior requires independent evaluation; no activation preservation guarantee"},
                   "sources": {"clean": _snapshot_record(clean), "donor": _snapshot_record(donor), "projected": _snapshot_record(projected), "projected_provenance": {"path": str(e90_sidecar), "file_sha256": e90_sidecar_hash, "payload_sha256": e90_payload_sha256}, "configs": configs, "tokenizer_manifest": tokenizer_support, "model_support_manifest": model_support},
                   "surface_proof": proof, "tensors": records,
                   "output": {**_snapshot_record(output), "path": str(destination), "changed_from_clean_keys": changed, "native_donor_identity": beta == 0,
                              "artifact_manifest_excluding_sidecar": checked.directory_manifest(stage), "reload": output_reload, "fresh_model_reload": fresh_model_reload,
                              "all_serialized_tensors_reopened_and_hashed": True, "standalone_text_model_and_clean_tokenizer": True},
                   "implementation": implementation, "runtime": dict(runtime.versions)}
        envelope = checked.immutable_envelope(payload)
        checked.write_immutable_json(stage / SIDECAR_NAME, envelope)
        if checked.load_immutable_json(stage / SIDECAR_NAME) != envelope:
            raise RuntimeError("sidecar roundtrip mismatch")
        checked._fsync_files(stage)
        checked._fsync_directory(stage)
        checked._publish_directory_no_replace(stage, destination)
        checked._fsync_directory(destination.parent)
        published = True
        return envelope
    finally:
        if not published:
            checked._remove_private_stage(stage, destination.parent, prefix)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("clean-model", "donor-model", "projected-model", "tokenizer-model", "output-dir"):
        parser.add_argument("--" + name, required=True)
    parser.add_argument("--beta", type=validate_beta, required=True)
    parser.add_argument("--device", default="cuda:0")
    parser.add_argument("--chunk-elements", type=int, default=1048576)
    args = parser.parse_args()
    result = apply_blend(**vars(args))
    print(f"Published beta={args.beta}: {result['payload_sha256']}", flush=True)


if __name__ == "__main__":
    main()
