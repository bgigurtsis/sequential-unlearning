"""Apply a replay-verified sparse causal-MLP column mask.

This is the mutation stage paired with :mod:`attribute_causal_mlp_neurons`.
It deliberately accepts only local, byte-pinned model and tokenizer artifacts.
Before changing a tensor it replays the raw Safetensors attribution evidence,
checks the immutable mask envelope, and binds every ranked mask row back to the
exact source ``down_proj`` column measured by the attribution stage.

The requested top-k prefix is applied in FP32 arithmetic and copied back to the
source dtype.  A scale of exactly one is a true identity operation: no tensor
write is issued and the original model weight files are copied byte-for-byte.
"""

from __future__ import annotations

import argparse
import ctypes
import datetime as dt
import errno
import hashlib
import json
import math
import os
import shutil
import stat
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping

try:
    import attribute_causal_mlp_neurons as attribution
except ModuleNotFoundError:
    from scripts import attribute_causal_mlp_neurons as attribution


APPLICATION_SCHEMA_VERSION = "causal_mlp_mask_application_v1"
SIDECAR_NAME = "causal_mlp_mask_application.json"
MODEL_WEIGHT_SUFFIXES = (".safetensors",)


def _finite_column_scale(value: Any) -> float:
    if isinstance(value, bool):
        raise ValueError("column-scale must be a finite number in [0, 1]")
    try:
        result = float(value)
    except (TypeError, ValueError) as error:
        raise ValueError("column-scale must be a finite number in [0, 1]") from error
    if not math.isfinite(result) or not 0.0 <= result <= 1.0:
        raise ValueError("column-scale must be a finite number in [0, 1]")
    return result


def _positive_top_k(value: Any) -> int:
    if isinstance(value, bool):
        raise ValueError("top-k must be a positive integer")
    try:
        result = int(value)
    except (TypeError, ValueError) as error:
        raise ValueError("top-k must be a positive integer") from error
    if result <= 0 or str(value).strip() != str(result):
        raise ValueError("top-k must be a positive integer")
    return result


def parse_args(argv: Iterable[str] | None = None):
    parser = argparse.ArgumentParser(
        description=(
            "Replay a causal-MLP attribution archive and scale only the "
            "top-k bound down-projection columns."
        )
    )
    parser.add_argument("--model", "--model-id", dest="model", required=True)
    parser.add_argument(
        "--tokenizer-model", "--tokenizer", dest="tokenizer_model", required=True
    )
    parser.add_argument("--mask-json", "--mask", dest="mask_json", required=True)
    parser.add_argument(
        "--raw-attribution",
        "--raw-safetensors",
        dest="raw_attribution",
        required=True,
    )
    parser.add_argument("--output-dir", "--output", dest="output_dir", required=True)
    parser.add_argument("--top-k", required=True, type=_positive_top_k)
    parser.add_argument("--column-scale", required=True, type=_finite_column_scale)
    return parser.parse_args(argv)


def _reject_duplicate_json_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"JSON object contains duplicate key: {key!r}")
        result[key] = value
    return result


def load_immutable_mask(path: str | Path) -> dict:
    source = Path(path)
    if not source.is_file():
        raise ValueError(f"mask JSON must be an exact existing local file: {source}")
    try:
        envelope = json.loads(
            source.read_text(encoding="utf-8"),
            object_pairs_hook=_reject_duplicate_json_keys,
        )
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ValueError(f"could not read mask JSON: {source}") from error
    if not attribution.selection.verify_immutable_envelope(envelope):
        raise ValueError("mask JSON has an invalid immutable payload hash")
    return envelope


def _exact_local_directory(path: str | Path, label: str) -> Path:
    candidate = Path(path)
    if not candidate.is_dir():
        raise ValueError(f"{label} must be an exact existing local directory: {path}")
    return candidate.resolve(strict=True)


def _expected_tokenizer_manifest(envelope: Mapping) -> dict:
    record = envelope.get("tokenizer")
    if not isinstance(record, Mapping):
        raise ValueError("mask payload has no tokenizer manifest")
    manifest = dict(record)
    manifest.pop("runtime", None)
    return manifest


def verify_source_manifests(
    envelope: Mapping, model_source: str, tokenizer_source: str
) -> tuple[dict, dict]:
    """Hash all mask-bound source files and compare the complete manifests."""

    expected_model = envelope.get("source_model")
    if not isinstance(expected_model, Mapping):
        raise ValueError("mask payload has no source model manifest")
    actual_model = attribution.require_local_artifact_manifest(
        model_source, label="model"
    )
    if actual_model != dict(expected_model):
        raise ValueError("local source model files do not match mask manifest")

    expected_tokenizer = _expected_tokenizer_manifest(envelope)
    actual_tokenizer = attribution.require_local_artifact_manifest(
        tokenizer_source, label="tokenizer-model", tokenizer_only=True
    )
    if actual_tokenizer != expected_tokenizer:
        raise ValueError("local tokenizer files do not match mask manifest")
    return actual_model, actual_tokenizer


def verify_tokenizer_runtime(envelope: Mapping, tokenizer) -> dict:
    expected = envelope.get("tokenizer", {}).get("runtime")
    if not isinstance(expected, Mapping):
        raise ValueError("mask payload has no tokenizer runtime binding")
    tokenizer.padding_side = "right"
    if getattr(tokenizer, "pad_token_id", None) is None:
        tokenizer.pad_token_id = getattr(tokenizer, "eos_token_id", None)
    if getattr(tokenizer, "pad_token_id", None) is None:
        raise ValueError("tokenizer has neither a pad token nor an EOS token")
    chat_template = getattr(tokenizer, "chat_template", None)
    if not chat_template:
        raise ValueError("tokenizer has no chat template")
    actual = {
        "class": type(tokenizer).__name__,
        "bos_token_id": getattr(tokenizer, "bos_token_id", None),
        "eos_token_id": getattr(tokenizer, "eos_token_id", None),
        "pad_token_id": getattr(tokenizer, "pad_token_id", None),
        "chat_template_sha256": attribution.selection.payload_sha256(chat_template),
    }
    if actual != dict(expected):
        raise ValueError("loaded tokenizer runtime does not match mask binding")
    return actual


def tensor_sha256(tensor, torch) -> str:
    raw = tensor.detach().contiguous().view(torch.uint8).cpu().numpy().tobytes()
    return hashlib.sha256(raw).hexdigest()


def _tensor_record(tensor, torch) -> dict:
    return {
        "shape": list(tensor.shape),
        "dtype": str(tensor.dtype),
        "sha256": tensor_sha256(tensor, torch),
    }


def model_tensor_inventory(model, torch) -> tuple[dict, str, dict[str, list[str]]]:
    """Return exact logical state bytes plus tied-storage alias groups."""

    state = model.state_dict()
    if not isinstance(state, Mapping) or not state:
        raise ValueError("loaded model has an empty or invalid state_dict")
    inventory = {}
    storage_groups: dict[tuple, list[str]] = {}
    for name, tensor in sorted(state.items()):
        if not isinstance(name, str) or not name:
            raise ValueError("model state_dict contains an invalid key")
        if not hasattr(tensor, "shape") or not hasattr(tensor, "dtype"):
            raise ValueError(f"model state entry is not a tensor: {name}")
        inventory[name] = _tensor_record(tensor, torch)
        try:
            storage_key = (
                str(tensor.device),
                int(tensor.untyped_storage().data_ptr()),
                int(tensor.untyped_storage().nbytes()),
            )
        except (AttributeError, RuntimeError, TypeError):
            # Test doubles and unusual tensor subclasses need not expose storage.
            storage_key = ("object", id(tensor))
        storage_groups.setdefault(storage_key, []).append(name)
    aliases = {
        names[0]: sorted(names)
        for names in storage_groups.values()
        if len(names) > 1
    }
    return inventory, attribution.selection.payload_sha256(inventory), aliases


def _named_parameters(model) -> dict[str, Any]:
    parameters = {}
    for name, parameter in model.named_parameters():
        if name in parameters:
            raise ValueError(f"loaded model has duplicate parameter name: {name}")
        parameters[name] = parameter
    if not parameters:
        raise ValueError("loaded model has no named parameters")
    return parameters


def verify_all_mask_bindings(
    envelope: Mapping,
    model,
    torch,
) -> tuple[list[dict], dict[str, Any], Any, str]:
    """Bind every ranked row to the exact measured source column.

    The entire ranked list is checked before mutation, even when only a short
    prefix will be applied.  This ensures ``--top-k`` cannot hide a malformed
    or duplicate binding later in the immutable mask.
    """

    selected = envelope.get("selected_neurons")
    if not isinstance(selected, list) or not selected:
        raise ValueError("mask selected_neurons must be a non-empty list")
    decoder_layers, decoder_path = attribution.resolve_decoder_layers(model)
    surface = envelope.get("model_surface")
    if not isinstance(surface, Mapping):
        raise ValueError("mask payload has no model_surface")
    if surface.get("decoder_path") != decoder_path:
        raise ValueError("loaded decoder path does not match mask model surface")
    parameters = _named_parameters(model)
    parameter_names_by_id = {id(value): name for name, value in parameters.items()}
    if len(parameter_names_by_id) != len(parameters):
        raise ValueError("loaded model exposes the same parameter under multiple names")

    seen_columns = set()
    verified = []
    for index, raw_record in enumerate(selected):
        label = f"selected_neurons[{index}]"
        if not isinstance(raw_record, Mapping):
            raise ValueError(f"{label} must be an object")
        record = dict(raw_record)
        layer = record.get("layer")
        neuron = record.get("neuron")
        if isinstance(layer, bool) or not isinstance(layer, int) or layer < 0:
            raise ValueError(f"{label}.layer must be a non-negative integer")
        if isinstance(neuron, bool) or not isinstance(neuron, int) or neuron < 0:
            raise ValueError(f"{label}.neuron must be a non-negative integer")
        if record.get("global_rank") != index + 1:
            raise ValueError(f"{label}.global_rank is not the immutable prefix order")
        if layer >= len(decoder_layers):
            raise ValueError(f"{label}.layer exceeds the loaded decoder")
        weight = decoder_layers[layer].mlp.down_proj.weight
        if len(weight.shape) != 2 or neuron >= int(weight.shape[1]):
            raise ValueError(f"{label} is outside its down_proj weight")
        actual_name = parameter_names_by_id.get(id(weight))
        if actual_name is None:
            raise ValueError(f"{label} down_proj weight is absent from named_parameters")
        if record.get("parameter_name") != actual_name:
            raise ValueError(f"{label} parameter name does not match loaded down_proj")
        expected_surface = f"{decoder_path}.{layer}.mlp.down_proj.weight"
        if record.get("resolved_parameter_surface") != expected_surface:
            raise ValueError(f"{label} resolved parameter surface does not match")
        column_key = (actual_name, neuron)
        if column_key in seen_columns:
            raise ValueError(
                f"duplicate selected down_proj column: {actual_name}[:, {neuron}]"
            )
        seen_columns.add(column_key)
        column = weight[:, neuron]
        if record.get("source_column_shape") != list(column.shape):
            raise ValueError(f"{label} source column shape does not match")
        if record.get("source_column_dtype") != str(column.dtype):
            raise ValueError(f"{label} source column dtype does not match")
        actual_hash = tensor_sha256(column, torch)
        if record.get("source_column_sha256") != actual_hash:
            raise ValueError(f"{label} source column SHA-256 does not match")
        record["verified_source_column_sha256"] = actual_hash
        verified.append(record)
    return verified, parameters, decoder_layers, decoder_path


def _assert_replay_matches_mask(replayed, selected: list[dict]):
    if not isinstance(replayed, list) or len(replayed) != len(selected):
        raise ValueError("raw attribution replay did not reproduce the full mask")
    for index, (actual, expected) in enumerate(zip(replayed, selected)):
        if not isinstance(actual, Mapping):
            raise ValueError(f"raw attribution replay row {index} is invalid")
        if (
            actual.get("layer") != expected.get("layer")
            or actual.get("neuron") != expected.get("neuron")
        ):
            raise ValueError(f"raw attribution replay order differs at rank {index + 1}")


def apply_verified_prefix(
    verified_rows: list[dict],
    parameters: Mapping[str, Any],
    *,
    top_k: int,
    column_scale: float,
    torch,
) -> list[dict]:
    """Apply precisely the requested prefix, proving whole-tensor locality."""

    if top_k > len(verified_rows):
        raise ValueError(
            f"top-k {top_k} exceeds the {len(verified_rows)} replayed mask rows"
        )
    rows = verified_rows[:top_k]
    by_parameter: dict[str, list[dict]] = {}
    for row in rows:
        by_parameter.setdefault(row["parameter_name"], []).append(row)

    applications = []
    with torch.no_grad():
        for name, parameter_rows in by_parameter.items():
            weight = parameters[name]
            parameter_before_sha256 = tensor_sha256(weight, torch)
            # A complete expected tensor is kept one down-projection at a time.
            # This is bounded (~52 MiB for one Gemma-3-4B MLP tensor) and proves
            # that no cell outside the selected columns changed.
            expected = None if column_scale == 1.0 else weight.detach().clone()
            pending = []
            for row in parameter_rows:
                neuron = row["neuron"]
                source_column = weight[:, neuron]
                before_sha256 = tensor_sha256(source_column, torch)
                if before_sha256 != row["source_column_sha256"]:
                    raise RuntimeError(
                        f"source column changed after validation: {name}[:, {neuron}]"
                    )
                if column_scale != 1.0:
                    scaled = (source_column.detach().float() * column_scale).to(
                        dtype=source_column.dtype
                    )
                    expected[:, neuron].copy_(scaled)
                    source_column.copy_(scaled)
                after_sha256 = tensor_sha256(weight[:, neuron], torch)
                pending.append(
                    {
                        "global_rank": row["global_rank"],
                        "layer": row["layer"],
                        "neuron": neuron,
                        "parameter_name": name,
                        "shape": list(source_column.shape),
                        "dtype": str(source_column.dtype),
                        "column_scale": column_scale,
                        "before_sha256": before_sha256,
                        "after_sha256": after_sha256,
                        "bytes_changed": before_sha256 != after_sha256,
                    }
                )
            parameter_after_sha256 = tensor_sha256(weight, torch)
            if expected is None:
                if parameter_after_sha256 != parameter_before_sha256:
                    raise RuntimeError("identity scaling changed a model tensor")
            elif parameter_after_sha256 != tensor_sha256(expected, torch):
                raise RuntimeError(
                    f"mutation escaped selected columns in parameter: {name}"
                )
            for record in pending:
                record["parameter_before_sha256"] = parameter_before_sha256
                record["parameter_after_sha256"] = parameter_after_sha256
                applications.append(record)
    applications.sort(key=lambda item: item["global_rank"])
    return applications


def _hash_files(root: Path, files: Iterable[Path]) -> dict[str, str]:
    return {
        path.relative_to(root).as_posix(): attribution.selection.sha256_file(path)
        for path in sorted(files, key=lambda item: item.relative_to(root).as_posix())
    }


def model_weight_hashes(root: Path) -> dict[str, str]:
    files = [
        path
        for path in root.rglob("*")
        if path.is_file() and path.name.endswith(MODEL_WEIGHT_SUFFIXES)
    ]
    if not files:
        raise ValueError(f"checkpoint has no model weight files: {root}")
    return _hash_files(root, files)


def require_safetensors_checkpoint(root: Path):
    safetensors_files = [path for path in root.rglob("*.safetensors") if path.is_file()]
    pickle_files = [path for path in root.rglob("*.bin") if path.is_file()]
    if pickle_files:
        raise ValueError("model checkpoint must not contain .bin weight files")
    if not safetensors_files:
        raise ValueError("model checkpoint must contain Safetensors weights")


def directory_manifest(root: Path, *, excluded_names: set[str] | None = None) -> dict:
    excluded_names = excluded_names or set()
    files = [
        path
        for path in root.rglob("*")
        if path.is_file() and path.name not in excluded_names
    ]
    records = [
        {
            "path": path.relative_to(root).as_posix(),
            "bytes": path.stat().st_size,
            "sha256": attribution.selection.sha256_file(path),
        }
        for path in sorted(files, key=lambda item: item.relative_to(root).as_posix())
    ]
    return {
        "files": records,
        "manifest_sha256": attribution.selection.payload_sha256(records),
    }


def _copy_manifest_files(
    source: Path, manifest: Mapping, destination: Path
):
    records = manifest.get("files")
    if not isinstance(records, list) or not records:
        raise ValueError("artifact manifest has no files to copy")
    for record in records:
        relative = Path(record["path"])
        artifact_source = source / relative
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(artifact_source, target, follow_symlinks=True)


def _save_checkpoint(
    model,
    tokenizer,
    *,
    source_model: Path,
    source_tokenizer: Path,
    model_manifest: Mapping,
    tokenizer_manifest: Mapping,
    destination: Path,
    identity: bool,
):
    if identity:
        _copy_manifest_files(source_model, model_manifest, destination)
        _copy_manifest_files(source_tokenizer, tokenizer_manifest, destination)
    else:
        model.save_pretrained(destination, safe_serialization=True)
        tokenizer.save_pretrained(destination)


def _read_saved_safetensor_inventory(root: Path, *, safe_open, torch) -> dict:
    files = sorted(root.glob("*.safetensors"))
    if not files:
        # Gemma-3 production artifacts are Safetensors.  Refuse an unverified
        # serialization rather than silently treating a pickle as equivalent.
        raise ValueError("saved checkpoint has no verifiable Safetensors weights")
    inventory = {}
    for path in files:
        with safe_open(str(path), framework="pt", device="cpu") as handle:
            for key in handle.keys():
                if key in inventory:
                    raise ValueError(f"saved tensor appears in multiple shards: {key}")
                inventory[key] = _tensor_record(handle.get_tensor(key), torch)
    return inventory


def verify_saved_model_tensors(
    root: Path,
    expected: Mapping[str, Mapping],
    aliases: Mapping[str, list[str]],
    *,
    safe_open,
    torch,
) -> dict:
    """Verify serialized bytes against in-memory state, allowing true ties."""

    saved = _read_saved_safetensor_inventory(root, safe_open=safe_open, torch=torch)
    unexpected = sorted(set(saved) - set(expected))
    if unexpected:
        raise ValueError("saved checkpoint has unexpected tensors: " + ", ".join(unexpected[:5]))
    for name, record in saved.items():
        if record != expected[name]:
            raise ValueError(f"saved tensor bytes differ from in-memory model: {name}")
    missing = set(expected) - set(saved)
    alias_by_name = {
        name: set(group)
        for group in aliases.values()
        for name in group
    }
    unresolved = []
    for name in sorted(missing):
        peers = alias_by_name.get(name, set()) - {name}
        if not any(peer in saved and saved[peer] == expected[name] for peer in peers):
            unresolved.append(name)
    if unresolved:
        raise ValueError(
            "saved checkpoint is missing non-aliased tensors: "
            + ", ".join(unresolved[:5])
        )
    return {
        "tensor_count": len(saved),
        "omitted_tied_aliases": sorted(missing),
        "inventory_sha256": attribution.selection.payload_sha256(saved),
    }


def _fsync_files(root: Path):
    for path in root.rglob("*"):
        if path.is_file():
            # Windows requires a writable descriptor for FlushFileBuffers;
            # POSIX does not, and identity copies may intentionally retain a
            # read-only source mode.
            if os.name != "nt":
                with path.open("rb") as handle:
                    os.fsync(handle.fileno())
                continue
            original_mode = stat.S_IMODE(path.stat().st_mode)
            made_writable = False
            try:
                try:
                    handle = path.open("rb+")
                except PermissionError:
                    os.chmod(path, original_mode | stat.S_IWRITE)
                    made_writable = True
                    handle = path.open("rb+")
                with handle:
                    os.fsync(handle.fileno())
            finally:
                if made_writable:
                    os.chmod(path, original_mode)


def _fsync_directory(path: Path):
    if os.name == "nt":
        return
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _path_lexists(path: Path) -> bool:
    return os.path.lexists(path)


def _publish_directory_no_replace(temporary: Path, destination: Path):
    """Publish a complete sibling directory without replacing any path."""

    if _path_lexists(destination):
        raise FileExistsError(f"refusing to replace existing output: {destination}")
    if os.name == "posix" and sys.platform.startswith("linux"):
        libc = ctypes.CDLL(None, use_errno=True)
        renameat2 = getattr(libc, "renameat2", None)
        if renameat2 is not None:
            renameat2.argtypes = [
                ctypes.c_int,
                ctypes.c_char_p,
                ctypes.c_int,
                ctypes.c_char_p,
                ctypes.c_uint,
            ]
            renameat2.restype = ctypes.c_int
            result = renameat2(
                -100,
                os.fsencode(temporary),
                -100,
                os.fsencode(destination),
                1,
            )
            if result == 0:
                return
            error_number = ctypes.get_errno()
            if error_number == errno.EEXIST:
                raise FileExistsError(
                    f"refusing to replace existing output: {destination}"
                ) from None
            if error_number not in {errno.ENOSYS, errno.EINVAL}:
                raise OSError(error_number, os.strerror(error_number), destination)
        raise RuntimeError(
            "this Linux filesystem lacks atomic no-replace directory publication"
        )
    if os.name == "posix":
        # Ordinary POSIX rename may replace an empty destination created in the
        # check/rename race.  Fail closed on platforms without renameat2.
        raise RuntimeError(
            "atomic no-replace directory publication is unsupported on this platform"
        )
    # Windows MoveFile fails when any destination path already exists.
    if _path_lexists(destination):
        raise FileExistsError(f"refusing to replace existing output: {destination}")
    os.rename(temporary, destination)


def _remove_private_stage(stage: Path, parent: Path, prefix: str):
    if not stage.exists():
        return
    if stage.parent.resolve() != parent.resolve() or not stage.name.startswith(prefix):
        raise RuntimeError(f"refusing to clean unexpected staging path: {stage}")
    shutil.rmtree(stage)


def _load_production_model(
    source: str, torch, auto_config, auto_model, conditional_model
):
    arguments = {
        "torch_dtype": torch.bfloat16,
        "device_map": "cpu",
        "low_cpu_mem_usage": True,
        "local_files_only": True,
    }
    config = auto_config.from_pretrained(source, local_files_only=True)
    if getattr(config, "model_type", None) == "gemma3":
        # Gemma-3 instruction checkpoints are conditional multimodal models.
        # Dispatch explicitly: older Transformers versions can fail with an
        # AttributeError rather than the ValueError used by newer auto maps.
        return conditional_model.from_pretrained(source, **arguments)
    return auto_model.from_pretrained(source, **arguments)


def git_provenance(repo_root: Path, paths: Iterable[Path]) -> dict:
    relative_paths = [str(path.resolve().relative_to(repo_root.resolve())) for path in paths]

    def run(*arguments):
        result = subprocess.run(
            ["git", *arguments],
            cwd=repo_root,
            check=False,
            capture_output=True,
            text=True,
        )
        return {
            "returncode": result.returncode,
            "stdout": result.stdout.strip(),
            "stderr": result.stderr.strip(),
        }

    return {
        "head": run("rev-parse", "HEAD"),
        "source_status": run("status", "--porcelain=v1", "--", *relative_paths),
    }


@dataclass(frozen=True)
class Runtime:
    torch: Any
    safe_open: Any
    load_model: Callable[[str], Any]
    load_tokenizer: Callable[[str], Any]
    versions: Mapping[str, str]


def production_runtime() -> Runtime:
    import safetensors
    import torch
    import transformers
    from safetensors import safe_open
    from transformers import (
        AutoConfig,
        AutoModelForCausalLM,
        AutoTokenizer,
        Gemma3ForConditionalGeneration,
    )

    return Runtime(
        torch=torch,
        safe_open=safe_open,
        load_model=lambda source: _load_production_model(
            source,
            torch,
            AutoConfig,
            AutoModelForCausalLM,
            Gemma3ForConditionalGeneration,
        ),
        load_tokenizer=lambda source: AutoTokenizer.from_pretrained(
            source, local_files_only=True
        ),
        versions={
            "python": sys.version,
            "torch": torch.__version__,
            "transformers": transformers.__version__,
            "safetensors": safetensors.__version__,
        },
    )


def apply_causal_mlp_mask(
    *,
    model_source: str,
    tokenizer_source: str,
    mask_json: str | Path,
    raw_attribution: str | Path,
    output_dir: str | Path,
    top_k: int,
    column_scale: float,
    runtime: Runtime | None = None,
) -> dict:
    """Replay, verify, apply, serialize, and atomically publish one mask dose."""

    top_k = _positive_top_k(top_k)
    column_scale = _finite_column_scale(column_scale)
    source_model_path = _exact_local_directory(model_source, "model")
    source_tokenizer_path = _exact_local_directory(
        tokenizer_source, "tokenizer-model"
    )
    require_safetensors_checkpoint(source_model_path)
    mask_path = Path(mask_json)
    raw_path = Path(raw_attribution)
    if not raw_path.is_file():
        raise ValueError(
            f"raw attribution must be an exact existing local file: {raw_path}"
        )
    destination = Path(output_dir).absolute()
    if _path_lexists(destination):
        raise FileExistsError(f"refusing to replace existing output: {destination}")
    for source, label in (
        (source_model_path, "model"),
        (source_tokenizer_path, "tokenizer"),
    ):
        try:
            destination.resolve().relative_to(source)
        except ValueError:
            pass
        else:
            raise ValueError(f"output directory cannot be inside the {label} source")

    envelope = load_immutable_mask(mask_path)
    mask_file_sha256 = attribution.selection.sha256_file(mask_path)
    raw_file_sha256 = attribution.selection.sha256_file(raw_path)
    script_path = Path(__file__).resolve()
    attribution_path = Path(attribution.__file__).resolve()
    selection_path = Path(attribution.selection.__file__).resolve()
    implementation_paths = {
        "applier": script_path,
        "attribution_replay": attribution_path,
        "selection_helper": selection_path,
    }
    implementation_sha256 = {
        name: attribution.selection.sha256_file(path)
        for name, path in implementation_paths.items()
    }
    source_model_manifest, source_tokenizer_manifest = verify_source_manifests(
        envelope, model_source, tokenizer_source
    )
    runtime = runtime or production_runtime()
    # Bind the production verifier directly.  Runtime dependency injection is
    # intentionally not allowed to replace evidence replay.
    replayed, replay_diagnostics = attribution.verify_raw_attribution_replay(
        envelope,
        raw_path,
        torch=runtime.torch,
        safe_open=runtime.safe_open,
    )
    selected = envelope.get("selected_neurons")
    _assert_replay_matches_mask(replayed, selected)
    if top_k > len(selected):
        raise ValueError(
            f"top-k {top_k} exceeds the {len(selected)} replayed mask rows"
        )

    model = runtime.load_model(model_source)
    tokenizer = runtime.load_tokenizer(tokenizer_source)
    tokenizer_runtime = verify_tokenizer_runtime(envelope, tokenizer)
    if hasattr(model, "eval"):
        model.eval()
    if hasattr(model, "requires_grad_"):
        model.requires_grad_(False)
    # Close the load-time TOCTOU window before inspecting or mutating tensors.
    verify_source_manifests(envelope, model_source, tokenizer_source)
    verified_rows, parameters, _, decoder_path = verify_all_mask_bindings(
        envelope, model, runtime.torch
    )
    before_inventory, before_fingerprint, aliases = model_tensor_inventory(
        model, runtime.torch
    )
    # Prove that the complete loaded baseline (not merely the selected
    # columns) is byte-equivalent to the pinned serialized checkpoint.  This
    # catches loader casting, missing-key initialization, and wrapper drift
    # before the mutation baseline is established.
    source_tensor_verification = verify_saved_model_tensors(
        source_model_path,
        before_inventory,
        aliases,
        safe_open=runtime.safe_open,
        torch=runtime.torch,
    )
    applications = apply_verified_prefix(
        verified_rows,
        parameters,
        top_k=top_k,
        column_scale=column_scale,
        torch=runtime.torch,
    )
    after_inventory, after_fingerprint, after_aliases = model_tensor_inventory(
        model, runtime.torch
    )
    if set(before_inventory) != set(after_inventory):
        raise RuntimeError("model state keys changed during sparse mask application")
    expected_changed_parameters = {
        record["parameter_name"]
        for record in applications
        if record["parameter_before_sha256"] != record["parameter_after_sha256"]
    }
    actual_changed_state = {
        name
        for name in before_inventory
        if before_inventory[name] != after_inventory[name]
    }
    if actual_changed_state != expected_changed_parameters:
        raise RuntimeError(
            "model-wide mutation set differs from selected down_proj parameters"
        )
    if column_scale == 1.0 and (
        before_inventory != after_inventory
        or before_fingerprint != after_fingerprint
    ):
        raise RuntimeError("column-scale 1 failed byte-identical model identity")
    if after_aliases != aliases:
        raise RuntimeError("model tensor aliasing changed during sparse mask application")

    # Hash sources yet again before any output is published.
    verify_source_manifests(envelope, model_source, tokenizer_source)
    destination.parent.mkdir(parents=True, exist_ok=True)
    stage_prefix = f".{destination.name}.tmp-"
    stage = Path(tempfile.mkdtemp(prefix=stage_prefix, dir=destination.parent))
    published = False
    try:
        _save_checkpoint(
            model,
            tokenizer,
            source_model=source_model_path,
            source_tokenizer=source_tokenizer_path,
            model_manifest=source_model_manifest,
            tokenizer_manifest=source_tokenizer_manifest,
            destination=stage,
            identity=column_scale == 1.0,
        )
        if (stage / SIDECAR_NAME).exists():
            raise FileExistsError(
                f"source checkpoint already contains reserved sidecar: {SIDECAR_NAME}"
            )
        # Like replay, serialized tensor verification is bound directly rather
        # than supplied by the injectable loading runtime.
        saved_tensor_verification = verify_saved_model_tensors(
            stage,
            after_inventory,
            aliases,
            safe_open=runtime.safe_open,
            torch=runtime.torch,
        )
        output_weight_hashes = model_weight_hashes(stage)
        source_weight_hashes = model_weight_hashes(source_model_path)
        if column_scale == 1.0 and output_weight_hashes != source_weight_hashes:
            raise RuntimeError(
                "column-scale 1 did not preserve byte-identical model weight files"
            )
        output_manifest = directory_manifest(stage, excluded_names={SIDECAR_NAME})
        # Saving must not mutate the in-memory model or any pinned source file.
        final_inventory, final_fingerprint, _ = model_tensor_inventory(
            model, runtime.torch
        )
        if final_inventory != after_inventory or final_fingerprint != after_fingerprint:
            raise RuntimeError("save_pretrained mutated model tensor bytes")
        verify_source_manifests(envelope, model_source, tokenizer_source)
        if attribution.selection.sha256_file(raw_path) != raw_file_sha256:
            raise RuntimeError("raw attribution archive changed during application")
        if attribution.selection.sha256_file(mask_path) != mask_file_sha256:
            raise RuntimeError("mask JSON changed during application")
        if load_immutable_mask(mask_path) != envelope:
            raise RuntimeError("mask JSON payload changed during application")
        if {
            name: attribution.selection.sha256_file(path)
            for name, path in implementation_paths.items()
        } != implementation_sha256:
            raise RuntimeError("mask application source changed during execution")

        provenance_payload = {
            "schema_version": APPLICATION_SCHEMA_VERSION,
            "created_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
            "operation": "scale_sparse_causal_mlp_down_proj_columns",
            "mutation_contract": {
                "selection": "immutable_selected_neurons_prefix",
                "surface": "down_proj.weight[:, neuron] only",
                "arithmetic": "FP32 multiply followed by copy to source dtype",
                "identity_rule": "scale_1_issues_no_tensor_write",
            },
            "request": {
                "top_k": top_k,
                "column_scale": column_scale,
                "output_dir": str(destination),
            },
            "source": {
                "model_argument": model_source,
                "model_resolved": str(source_model_path),
                "model_manifest": source_model_manifest,
                "model_weight_file_sha256": source_weight_hashes,
                "serialized_tensor_verification": source_tensor_verification,
                "tokenizer_argument": tokenizer_source,
                "tokenizer_resolved": str(source_tokenizer_path),
                "tokenizer_manifest": source_tokenizer_manifest,
                "tokenizer_runtime": tokenizer_runtime,
                "mask_json": {
                    "path": str(mask_path.resolve(strict=True)),
                    "file_sha256": mask_file_sha256,
                    "payload_sha256": envelope["payload_sha256"],
                    "selected_mask_sha256": envelope.get("selected_mask_sha256"),
                },
                "raw_attribution": {
                    "path": str(raw_path.resolve(strict=True)),
                    "file_sha256": raw_file_sha256,
                    "declared_sha256": envelope.get("attribution", {})
                    .get("raw_archive", {})
                    .get("sha256"),
                },
            },
            "replay": {
                "verified": True,
                "selected_rows": len(replayed),
                "diagnostics_sha256": attribution.selection.payload_sha256(
                    replay_diagnostics
                ),
            },
            "model_surface": {
                "decoder_path": decoder_path,
                "verified_ranked_columns": len(verified_rows),
                "applied_prefix_columns": top_k,
            },
            "applied_columns": applications,
            "model_tensors": {
                "before": {
                    "inventory": before_inventory,
                    "inventory_sha256": before_fingerprint,
                },
                "after": {
                    "inventory": after_inventory,
                    "inventory_sha256": after_fingerprint,
                },
                "changed_state_keys": sorted(actual_changed_state),
                "byte_identical": before_inventory == after_inventory,
            },
            "output": {
                "weight_file_sha256": output_weight_hashes,
                "artifact_manifest": output_manifest,
                "saved_tensor_verification": saved_tensor_verification,
                "standalone_model_and_tokenizer": True,
                "serialization_contract": "Safetensors_only",
                "compatibility_scope": (
                    "text_generation_model_plus_AutoTokenizer_only; conditional_"
                    "AutoProcessor_and_multimodal_preprocessing_not_published"
                ),
            },
            "runtime": dict(runtime.versions),
            "implementation": {
                "applier": {
                    "path": str(script_path),
                    "sha256": implementation_sha256["applier"],
                },
                "attribution_replay": {
                    "path": str(attribution_path),
                    "sha256": implementation_sha256["attribution_replay"],
                },
                "selection_helper": {
                    "path": str(selection_path),
                    "sha256": implementation_sha256["selection_helper"],
                },
                "git": git_provenance(
                    script_path.parents[1],
                    (script_path, attribution_path, selection_path),
                ),
            },
        }
        provenance = attribution.selection.immutable_envelope(provenance_payload)
        attribution.selection.write_immutable_json(stage / SIDECAR_NAME, provenance)
        reloaded_sidecar = load_immutable_mask(stage / SIDECAR_NAME)
        if reloaded_sidecar != provenance:
            raise RuntimeError("immutable provenance sidecar did not round-trip")
        if attribution.selection.sha256_file(raw_path) != raw_file_sha256:
            raise RuntimeError("raw attribution archive changed before publication")
        if attribution.selection.sha256_file(mask_path) != mask_file_sha256:
            raise RuntimeError("mask JSON changed before publication")
        if {
            name: attribution.selection.sha256_file(path)
            for name, path in implementation_paths.items()
        } != implementation_sha256:
            raise RuntimeError("mask application source changed before publication")
        _fsync_files(stage)
        _fsync_directory(stage)
        _publish_directory_no_replace(stage, destination)
        _fsync_directory(destination.parent)
        published = True
        return provenance
    finally:
        if not published:
            _remove_private_stage(stage, destination.parent, stage_prefix)


def main(argv: Iterable[str] | None = None):
    args = parse_args(argv)
    provenance = apply_causal_mlp_mask(
        model_source=args.model,
        tokenizer_source=args.tokenizer_model,
        mask_json=args.mask_json,
        raw_attribution=args.raw_attribution,
        output_dir=args.output_dir,
        top_k=args.top_k,
        column_scale=args.column_scale,
    )
    print(
        f"Published replay-verified sparse mask at {args.output_dir}\n"
        f"applied_columns={args.top_k}\n"
        f"column_scale={args.column_scale}\n"
        f"provenance_payload_sha256={provenance['payload_sha256']}",
        flush=True,
    )


if __name__ == "__main__":
    main()
