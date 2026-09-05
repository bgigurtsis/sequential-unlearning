"""Publish the frozen target-constrained correction to the rounded E90 model.

Only original training scenarios enter donor activation capture. Evaluation
files are read solely to prove disjoint prompts. The mathematical kernel lives
in constrain_projection_math; checked endpoint, serialization and namespace
helpers are reused from the qualified blend and projection implementations.
"""
from __future__ import annotations

import argparse
import datetime as dt
import gc
import importlib.metadata
import json
import tempfile
from pathlib import Path

try:
    import blend_checkpoint_projection as blend
    import project_checkpoint_delta_retain_subspace as capture_tools
    import build_semantic_scenario_prompts as prompt_builder
except ModuleNotFoundError:
    from scripts import blend_checkpoint_projection as blend
    from scripts import project_checkpoint_delta_retain_subspace as capture_tools
    from scripts import build_semantic_scenario_prompts as prompt_builder

checked = blend.checked
SIDECAR_NAME = "target_constrained_projection.json"
CONTRACT_RELATIVE = "derisk/whole_concept_jobs_v1/delta_protection_v1/sprint_20260904/target_constrained_correction_contract.json"
CONTRACT_SHA256 = "1c492cfa6e5794707a88737b1f9f2816549b7e264e2bd71663cfab4774959e90"


def math_module():
    try:
        import constrain_projection_math as math
    except ModuleNotFoundError:
        from scripts import constrain_projection_math as math
    return math


def frozen_training_inputs(repo_root):
    """Reproduce the fixed624 prompts and prove all7 evaluation sources disjoint."""
    repo_root = Path(repo_root)
    contract_path = repo_root / CONTRACT_RELATIVE
    if checked.sha256_file(contract_path) != CONTRACT_SHA256:
        raise ValueError("constrained-correction contract hash differs from frozen pin")
    contract = checked._read_json_object(contract_path, "method contract")
    if checked.sha256_file(Path(prompt_builder.__file__)) != contract["builder_sha256"]:
        raise ValueError("training prompt builder differs from frozen pin")
    records, files = [], []
    for source in contract["training_sources"]:
        path = repo_root / source["path"]
        if checked.sha256_file(path) != source["sha256"]:
            raise ValueError("target training source hash mismatch")
        generated = prompt_builder.build_records(json.loads(path.read_text(encoding="utf-8")), source["seed"])
        if len(generated) != source["record_count"]:
            raise ValueError("target source record count differs from contract")
        files.append({"path": str(path.resolve()), "sha256": source["sha256"]})
        for index, record in enumerate(generated):
            records.append({"record_id": f"{source['sha256'][:16]}:{index:06d}",
                            "messages": [{"role": "user", "content": record["prompt"]}],
                            "answer": None, "schema_family": "frozen_target_prompt_last_v1",
                            "category": record["category"]})
    if len(records) != 624 or len({r["messages"][0]["content"] for r in records}) != 624:
        raise ValueError("target capture requires exactly624 unique training prompts")
    evaluation_paths = []
    for source in contract["evaluation_sources_for_overlap_only"]:
        path = repo_root / source["path"]
        if checked.sha256_file(path) != source["sha256"]:
            raise ValueError("frozen evaluation source hash mismatch")
        evaluation_paths.append(path)
        files.append({"path": str(path.resolve()), "sha256": source["sha256"]})
    evaluation, overlap = capture_tools.prove_zero_evaluation_overlap(records, evaluation_paths)
    return records, {"contract_path": str(contract_path.resolve()), "contract_sha256": CONTRACT_SHA256,
                     "files": files, "evaluation_sources": evaluation, "overlap": overlap,
                     "generated_records_sha256": checked.payload_sha256(records), "record_count": 624}


def tokenize_prompt_last(records, tokenizer, *, max_length=256):
    """Select the final prompt input, never padding, truncation or an answer."""
    tokenized = []
    for record in records:
        ids = capture_tools._extract_token_ids(tokenizer.apply_chat_template(
            record["messages"], add_generation_prompt=True, tokenize=True, return_dict=True))
        if not ids or len(ids) > max_length:
            raise ValueError(f"target prompt empty or exceeds frozen max length: {record['record_id']}")
        tokenized.append({"record_id": record["record_id"], "schema_family": record["schema_family"],
                          "input_ids": ids, "position_mask": [False] * (len(ids) - 1) + [True],
                          "position_policy": "last_nonpadding_complete_rendered_prompt_token"})
    return tokenized, {"record_count": len(tokenized), "token_count": sum(len(r["input_ids"]) for r in tokenized),
                       "selected_positions": len(tokenized), "maximum_length": max(len(r["input_ids"]) for r in tokenized),
                       "tokenization_sha256": checked.payload_sha256(tokenized), "generated_or_teacher_forced_answer_tokens": 0}


def collect_target_geometry(donor, tokenizer_root, records, data_proof, implementation, cache_dir, runtime):
    """Capture pinned donor inputs; immutable cache hits receive the same proofs."""
    from transformers import AutoTokenizer, Gemma3ForConditionalGeneration
    torch = runtime.torch
    model = Gemma3ForConditionalGeneration.from_pretrained(str(donor.root), dtype=torch.bfloat16,
        device_map="cuda", local_files_only=True, trust_remote_code=False)
    try:
        model.eval()
        model.requires_grad_(False)
        contract = capture_tools.verify_gemma3_model_contract(model)
        tokenizer = AutoTokenizer.from_pretrained(str(tokenizer_root), local_files_only=True, trust_remote_code=False)
        tokenizer_contract = capture_tools.tokenizer_runtime_contract(tokenizer, model)
        tokenized, tokenization = tokenize_prompt_last(records, tokenizer)
        inventory, _, aliases = blend.model_checks.model_tensor_inventory(model, torch)
        namespace = blend.model_checks.namespace_mapping_contract_for_model(model)
        reload_proof = blend.model_checks.verify_saved_model_tensors(donor.root, inventory, aliases, namespace,
                                                                   safe_open=runtime.safe_open, torch=torch)
        modules, module_records = capture_tools.resolve_declared_linear_modules(model, checked.EDIT_LAYERS, torch=torch)
        module_groups, groups = capture_tools.declared_basis_groups(checked.EDIT_LAYERS, contract["decoder_path"])
        if len(modules) != 98 or len(groups) != 56:
            raise RuntimeError("target capture module/group count differs from frozen98/56")
        binding = {"kind": "donor_target_prompt_last_keys_v1", "implementation": implementation,
                   "donor_weights": dict(donor.weight_hashes), "donor_logical": donor.logical_inventory_sha256,
                   "data": data_proof, "tokenization": tokenization, "tokenizer": tokenizer_contract,
                   "tokenizer_manifest": checked.selected_file_manifest(tokenizer_root, names=checked.TOKENIZER_NAMES, chat_templates=True),
                   "groups": groups, "batch_size": 4, "runtime": dict(runtime.versions),
                   "device": torch.cuda.get_device_name(), "deterministic": True, "tf32": False, "seed": 0}
        def compute():
            keys, proof = capture_tools.collect_clean_retain_keys(model, modules, groups, tokenized,
                pad_token_id=tokenizer_contract["pad_token_id"], batch_size=4, torch=torch)
            return {"keys": keys, "capture": proof}
        cached, cache_proof = capture_tools.immutable_tensor_cache(cache_dir, binding, compute, torch=torch)
        keys, proof = cached["keys"], cached["capture"]
        capture_tools.validate_cached_retain_keys(keys, proof, groups, modules, expected_records=624, torch=torch)
        _, pairs, _ = blend.model_checks._map_serialized_inventory(donor.tensor_inventory, namespace["rules"], namespace["required_rule_ids"])
        serialized_to_state = {pair["serialized_name"]: pair["state_name"] for pair in pairs}
        tensor_groups = {name: module_groups[serialized_to_state[name][:-len(".weight")]] for name in checked.DECLARED_EDIT_KEYS}
        evidence = {"capture_model": "pinned_donor", "capture": proof, "cache": cache_proof, "tokenization": tokenization,
                    "donor_fresh_namespace_reload": reload_proof, "module_records": module_records, "tensor_groups": tensor_groups,
                    "training_only": True, "evaluation_forward_passes": 0}
        return keys, tensor_groups, evidence
    finally:
        del model
        gc.collect()
        if torch.cuda.is_available():
            torch.cuda.empty_cache()


def write_constrained_weights(donor, projected, stage, *, identity, keys, groups, runtime, device):
    if identity:
        for filename in donor.weight_hashes:
            checked._copy_file_exclusive(donor.root / filename, stage / filename)
        records = [{"tensor_name": key, "output_sha256": donor.tensor_inventory[key]["sha256"], "native_identity": True}
                   for key in checked.DECLARED_EDIT_KEYS]
        basis_proofs = {}
    else:
        kernel = math_module()
        bases, basis_proofs = {}, {}
        for group in sorted(keys):
            bases[group], basis_proofs[group] = kernel.target_basis(keys[group], torch=runtime.torch)
            basis_proofs[group].update({"basis_sha256": capture_tools.tensor_sha256(bases[group], runtime.torch),
                                        "basis_shape": list(bases[group].shape), "basis_dtype": str(bases[group].dtype),
                                        "keys_sha256": capture_tools.tensor_sha256(keys[group], runtime.torch)})
        records = []
        declared = set(checked.DECLARED_EDIT_KEYS)
        for filename in sorted(donor.weight_hashes):
            with runtime.safe_open(str(donor.root / filename), framework="pt", device="cpu") as handle:
                tensors = {}
                for name in sorted(handle.keys()):
                    left = handle.get_tensor(name)
                    if name in declared:
                        group = groups[name]
                        right = checked._load_tensor(projected, name, runtime)
                        output, diagnostics = kernel.constrain_tensor(left, right, bases[group], keys[group],
                            torch=runtime.torch, device=device, row_chunk=128)
                        tensors[name] = output
                        records.append({"tensor_name": name, "group": group, "diagnostics": diagnostics,
                                        "output_sha256": checked._tensor_sha256(output, runtime.torch)})
                    else:
                        tensors[name] = left
                runtime.save_file(tensors, str(stage / filename), metadata=donor.file_metadata.get(filename))
    index = donor.root / "model.safetensors.index.json"
    if index.is_file():
        checked._copy_file_exclusive(index, stage / index.name)
    return sorted(records, key=lambda r: r["tensor_name"]), basis_proofs


def apply_constrained(*, clean_model, donor_model, projected_model, tokenizer_model, output_dir,
                      cache_dir, identity=False, device="cuda:0", runtime=None, strict_git=True,
                      source_contract=checked.PINNED_SOURCE_CONTRACT, e90_weight_sha256=blend.E90_WEIGHT_SHA256,
                      e90_payload_sha256=blend.E90_PAYLOAD_SHA256, reload_verifier=None, model_reload_verifier=None):
    if not isinstance(identity, bool):
        raise ValueError("identity must be a boolean")
    if strict_git and device != "cuda:0":
        raise ValueError("production constrained publication requires cuda:0")
    clean_root, donor_root, projected_root = [checked._exact_local_directory(p, label) for p, label in
        ((clean_model, "clean"), (donor_model, "donor"), (projected_model, "projected"))]
    tokenizer_root = checked._exact_local_directory(tokenizer_model, "tokenizer")
    if len({clean_root, donor_root, projected_root}) != 3 or tokenizer_root != clean_root:
        raise ValueError("three distinct endpoints and exact clean tokenizer required")
    destination = Path(output_dir).absolute()
    if checked._path_lexists(destination):
        raise FileExistsError(f"refusing to replace output: {destination}")
    for root in (clean_root, donor_root, projected_root):
        if destination.resolve().is_relative_to(root) or root.is_relative_to(destination.resolve()):
            raise ValueError("output and source endpoints must not contain each other")
        if Path(cache_dir).resolve().is_relative_to(root):
            raise ValueError("activation cache cannot be inside a source model")
    modules = [blend, checked, blend.model_checks, blend.model_checks.attribution,
               blend.model_checks.attribution.selection, capture_tools, prompt_builder, math_module()]
    paths = [Path(__file__).resolve(), Path(__file__).with_name("test_constrain_checkpoint_projection.py").resolve(),
             Path(__file__).with_name("test_constrain_projection_math.py").resolve()] + [Path(m.__file__).resolve() for m in modules]
    implementation = [{"path": str(p), "sha256": checked.sha256_file(p), "git": checked.git_provenance(p, strict=strict_git)} for p in paths]
    records, data_proof = frozen_training_inputs(Path(__file__).resolve().parents[1])
    runtime = runtime or checked.production_runtime()
    versions = {**runtime.versions, "transformers": importlib.metadata.version("transformers")}
    runtime = checked.Runtime(runtime.torch, runtime.safe_open, runtime.save_file, versions)
    runtime.torch.set_num_threads(8)
    determinism = capture_tools._configure_determinism(runtime.torch, seed=0)
    determinism["cpu_threads"] = runtime.torch.get_num_threads()
    clean, donor, projected = [checked.scan_checkpoint(root, label=label, runtime=runtime) for root, label in
                              ((clean_root, "clean"), (donor_root, "donor"), (projected_root, "projected"))]
    proof = blend.verify_endpoints(clean, donor, projected, source_contract=source_contract, e90_weight_sha256=e90_weight_sha256)
    configs = checked.verify_model_configs(clean_root, donor_root, source_contract)
    sidecar_path = projected_root / blend.E90_SIDECAR_NAME
    e90_provenance = checked.load_immutable_json(sidecar_path)
    if e90_provenance["payload_sha256"] != e90_payload_sha256:
        raise ValueError("E90 provenance payload differs from frozen pin")
    sidecar_hash = checked.sha256_file(sidecar_path)
    model_support = checked.selected_file_manifest(donor_root, names=checked.MODEL_SUPPORT_NAMES)
    tokenizer_support = checked.selected_file_manifest(tokenizer_root, names=checked.TOKENIZER_NAMES, chat_templates=True)
    if not any(r["path"] in {"tokenizer.json", "tokenizer.model", "spiece.model"} for r in tokenizer_support["files"]):
        raise ValueError("clean source lacks standalone tokenizer artifact")
    reload_verifier = reload_verifier or checked.verify_hf_text_reload
    source_reload = dict(reload_verifier(clean_root))
    source_tokenizer = checked.verify_tokenizer_reload_contract(source_reload, label="clean")
    if source_reload.get("model_type") != source_contract.model_type:
        raise ValueError("clean reload model type mismatch")
    keys, groups, capture = ({}, {}, {"identity_skipped_capture": True}) if identity else collect_target_geometry(
        donor, tokenizer_root, records, data_proof, implementation, cache_dir, runtime)
    destination.parent.mkdir(parents=True, exist_ok=True)
    prefix = f".{destination.name}.tmp-"
    stage = Path(tempfile.mkdtemp(prefix=prefix, dir=destination.parent))
    published = False
    try:
        tensor_records, bases = write_constrained_weights(donor, projected, stage, identity=identity,
            keys=keys, groups=groups, runtime=runtime, device=device)
        checked._copy_manifest(donor_root, model_support, stage)
        checked._copy_manifest(tokenizer_root, tokenizer_support, stage)
        output = checked.scan_checkpoint(stage, label="output", runtime=runtime)
        changed = checked.verify_output_locality(clean.tensor_inventory, output.tensor_inventory)
        checked.verify_output_locality(donor.tensor_inventory, output.tensor_inventory)
        if set(changed) != set(checked.DECLARED_EDIT_KEYS) or output.key_to_file != donor.key_to_file:
            raise RuntimeError("output changed frozen98 surface or canonical shard layout")
        if [r["tensor_name"] for r in tensor_records] != sorted(checked.DECLARED_EDIT_KEYS):
            raise RuntimeError("incomplete constrained tensor application records")
        for record in tensor_records:
            key = record["tensor_name"]
            if record["output_sha256"] != output.tensor_inventory[key]["sha256"]:
                raise RuntimeError("serialized value differs from constrained tensor")
            record["donor_sha256"] = donor.tensor_inventory[key]["sha256"]
            record["projected_sha256"] = projected.tensor_inventory[key]["sha256"]
        if identity and (output.weight_hashes != donor.weight_hashes or output.tensor_inventory != donor.tensor_inventory):
            raise RuntimeError("native identity did not reproduce donor")
        output_reload = dict(reload_verifier(stage))
        if output_reload.get("model_type") != source_contract.model_type or checked.verify_tokenizer_reload_contract(output_reload, label="output") != source_tokenizer:
            raise RuntimeError("output config/tokenizer reload mismatch")
        fresh = (model_reload_verifier or blend.verify_fresh_model_reload)(stage, runtime)
        if not fresh.get("verified"):
            raise RuntimeError("fresh model reload did not verify")
        for snapshot in (clean, donor, projected):
            if not checked._unchanged_weight_hashes(snapshot):
                raise RuntimeError("source weights changed during constrained run")
        if not checked._manifest_unchanged(donor_root, model_support) or not checked._manifest_unchanged(tokenizer_root, tokenizer_support):
            raise RuntimeError("source support files changed during constrained run")
        if checked.sha256_file(projected_root / "config.json") != source_contract.edited_config_sha256 or checked.sha256_file(sidecar_path) != sidecar_hash:
            raise RuntimeError("E90 metadata changed during constrained run")
        for source in data_proof["files"]:
            if checked.sha256_file(source["path"]) != source["sha256"]:
                raise RuntimeError("training or evaluation source changed during capture")
        if checked.sha256_file(data_proof["contract_path"]) != CONTRACT_SHA256:
            raise RuntimeError("method contract changed during run")
        for path, before in zip(paths, implementation):
            if checked.sha256_file(path) != before["sha256"] or (strict_git and checked.git_provenance(path, strict=True) != before["git"]):
                raise RuntimeError("implementation changed during constrained run")
        payload = {"schema_version": "target_constrained_e90_publication_v1", "created_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
                   "request": {"identity": identity, "device": device, "row_chunk": 128, "output_dir": str(destination)},
                   "method": "C0=E90native32-donor32; C=C0-(C0QF)QF.T; output=BF16(donor32+C); native identity bypass",
                   "sources": {"clean": blend._snapshot_record(clean), "donor": blend._snapshot_record(donor), "projected": blend._snapshot_record(projected),
                               "e90_payload_sha256": e90_payload_sha256, "e90_sidecar_sha256": sidecar_hash, "configs": configs,
                               "tokenizer_manifest": tokenizer_support, "model_support_manifest": model_support},
                   "training_data": data_proof, "target_capture": capture, "target_bases": bases, "surface_proof": proof, "tensors": tensor_records,
                   "output": {**blend._snapshot_record(output), "path": str(destination), "changed_from_clean_keys": changed,
                              "native_donor_identity": identity, "artifact_manifest_excluding_sidecar": checked.directory_manifest(stage),
                              "reload": output_reload, "fresh_model_reload": fresh, "standalone_clean_tokenizer": True},
                   "implementation": implementation, "runtime": dict(runtime.versions), "determinism": determinism,
                   "claim_boundary": "Sampled donor prompt-last linear inputs only; nonlinear trajectory and BF16 action are not guaranteed preserved; no global erasure claim"}
        envelope = checked.immutable_envelope(payload)
        checked.write_immutable_json(stage / SIDECAR_NAME, envelope)
        if checked.load_immutable_json(stage / SIDECAR_NAME) != envelope:
            raise RuntimeError("immutable constrained sidecar roundtrip failed")
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
    for name in ("clean-model", "donor-model", "projected-model", "tokenizer-model", "output-dir", "cache-dir"):
        parser.add_argument("--" + name, required=True)
    parser.add_argument("--identity", action="store_true")
    parser.add_argument("--device", choices=["cuda:0"], default="cuda:0")
    result = apply_constrained(**vars(parser.parse_args()))
    print(f"Published constrained candidate: {result['payload_sha256']}", flush=True)


if __name__ == "__main__":
    main()
