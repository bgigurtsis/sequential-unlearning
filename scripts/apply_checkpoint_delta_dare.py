"""Apply deterministic DARE sparsification to one pinned checkpoint delta.

This tool is deliberately independent of the causal-neuron applier.  It takes
two exact, local Safetensors checkpoints: the clean Gemma-3-4B-IT snapshot and
the proven dense employment-unlearning checkpoint.  It first proves that the
only non-zero clean-to-edited tensor deltas are the 98 explicitly declared
attention/MLP linears.  It then applies a deterministic, counter-based
Bernoulli mask to those deltas and publishes a standalone text model and
tokenizer with immutable provenance.

For every retained element, arithmetic is exactly::

    delta32 = edited.float32 - clean.float32
    adjusted_delta32 = delta32 / (1 - p)
    output = (clean.float32 + adjusted_delta32).to(clean.dtype)

Dropped elements receive an exact FP32 zero delta.  The mask is a pure
function of the UTF-8 canonical tensor name, a uint64 seed, and the row-major
flat element index; it is therefore independent of process, traversal order,
chunking, and compute device.  ``p == 0`` is a stronger identity path: the
edited Safetensors files are copied byte-for-byte after the full delta-surface
proof succeeds.
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
from decimal import Decimal, InvalidOperation, ROUND_CEILING, localcontext
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping


APPLICATION_SCHEMA_VERSION = "checkpoint_delta_dare_application_v1"
RNG_SCHEMA_VERSION = "sha256_tensor_seed_domain_splitmix64_counter_bernoulli_v2"
SIDECAR_NAME = "checkpoint_delta_dare_application.json"
UINT64_MODULUS = 1 << 64
UINT64_MASK = UINT64_MODULUS - 1

# Frozen sources established by the replay-step-64 evaluation.  The function
# accepts an explicit SourceContract for unit tests, but the CLI has no source
# override and therefore always enforces these production pins.
PINNED_CLEAN_WEIGHT_HASHES = {
    "model-00001-of-00002.safetensors": (
        "eb5fd5e97ddd07b56778733e9653c07312529cb00980a318fc3e1c4e3b5a8f1f"
    ),
    "model-00002-of-00002.safetensors": (
        "fdde0e5aa5ced0fa203b3d50f4ab78168b7e3a3e08c6349f5cc9326666e1bb13"
    ),
}
PINNED_EDITED_WEIGHT_HASHES = {
    "model.safetensors": (
        "b8527608bb60269959e6f7694c12627dd0194baff772e2b72b8c1240080e5690"
    )
}
PINNED_EDITED_CONFIG_SHA256 = (
    "b62e048b6442b38006a33bf9770de2caab0d88f2c9c4676306068c2f9756d847"
)
PINNED_EDITED_LOGICAL_INVENTORY_SHA256 = (
    "7eedf4b2d316a9518577917acd35bf2c04d77cafb095ff238c1452a24cfafbbf"
)

PRECOMMITTED_DROP_PROBABILITIES = ("0", "0.5", "0.9", "0.99")
PRECOMMITTED_NONZERO_SEEDS = (33450, 33451, 33452)

EDIT_LAYERS = tuple(range(12, 20)) + tuple(range(28, 34))
ATTENTION_MODULES = ("q_proj", "k_proj", "v_proj", "o_proj")
MLP_MODULES = ("gate_proj", "up_proj", "down_proj")


def declared_edit_keys() -> tuple[str, ...]:
    keys = []
    for layer in EDIT_LAYERS:
        prefix = f"language_model.model.layers.{layer}"
        keys.extend(
            f"{prefix}.self_attn.{module}.weight"
            for module in ATTENTION_MODULES
        )
        keys.extend(f"{prefix}.mlp.{module}.weight" for module in MLP_MODULES)
    result = tuple(keys)
    if len(result) != 98 or len(set(result)) != 98:
        raise RuntimeError("the frozen DARE surface is not exactly 98 unique linears")
    return result


DECLARED_EDIT_KEYS = declared_edit_keys()


def is_precommitted_request(drop_probability: DropSpec, seed: int) -> bool:
    return (
        (drop_probability.decimal == "0" and seed == 0)
        or (
            drop_probability.decimal in {"0.5", "0.9", "0.99"}
            and seed in PRECOMMITTED_NONZERO_SEEDS
        )
    )


@dataclass(frozen=True)
class SourceContract:
    clean_weight_hashes: tuple[tuple[str, str], ...]
    edited_weight_hashes: tuple[tuple[str, str], ...]
    edited_config_sha256: str
    edited_logical_inventory_sha256: str
    model_type: str = "gemma3"
    architecture: str = "Gemma3ForConditionalGeneration"
    text_layers: int = 34

    @classmethod
    def from_mappings(
        cls,
        clean_weight_hashes: Mapping[str, str],
        edited_weight_hashes: Mapping[str, str],
        edited_config_sha256: str,
        edited_logical_inventory_sha256: str,
        **kwargs,
    ) -> "SourceContract":
        return cls(
            tuple(sorted(clean_weight_hashes.items())),
            tuple(sorted(edited_weight_hashes.items())),
            edited_config_sha256,
            edited_logical_inventory_sha256,
            **kwargs,
        )

    def clean_mapping(self) -> dict[str, str]:
        return dict(self.clean_weight_hashes)

    def edited_mapping(self) -> dict[str, str]:
        return dict(self.edited_weight_hashes)


PINNED_SOURCE_CONTRACT = SourceContract.from_mappings(
    PINNED_CLEAN_WEIGHT_HASHES,
    PINNED_EDITED_WEIGHT_HASHES,
    PINNED_EDITED_CONFIG_SHA256,
    PINNED_EDITED_LOGICAL_INVENTORY_SHA256,
)


@dataclass(frozen=True)
class DropSpec:
    decimal: str
    probability: Decimal
    keep_decimal: str
    keep_probability: Decimal
    uint64_keep_threshold: int

    @property
    def is_identity(self) -> bool:
        return self.probability == 0


@dataclass(frozen=True)
class Runtime:
    torch: Any
    safe_open: Any
    save_file: Callable[..., Any]
    versions: Mapping[str, str]


@dataclass(frozen=True)
class CheckpointSnapshot:
    root: Path
    weight_hashes: Mapping[str, str]
    tensor_inventory: Mapping[str, Mapping[str, Any]]
    key_to_file: Mapping[str, str]
    file_metadata: Mapping[str, Mapping[str, str] | None]
    inventory_sha256: str
    key_to_file_sha256: str
    logical_inventory_sha256: str
    logical_tensor_count: int
    logical_total_value_bytes: int


def _reject_duplicate_json_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"JSON object contains duplicate key: {key!r}")
        result[key] = value
    return result


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def payload_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def immutable_envelope(payload: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, Mapping):
        raise ValueError("immutable payload must be an object")
    result = dict(payload)
    if "payload_sha256" in result:
        raise ValueError("immutable payload already contains payload_sha256")
    result["payload_sha256"] = payload_sha256(result)
    return result


def verify_immutable_envelope(envelope: Mapping[str, Any]) -> bool:
    if not isinstance(envelope, Mapping):
        return False
    claimed = envelope.get("payload_sha256")
    if not isinstance(claimed, str) or len(claimed) != 64:
        return False
    payload = dict(envelope)
    payload.pop("payload_sha256", None)
    return hashlib.sha256(canonical_json_bytes(payload)).hexdigest() == claimed


def write_immutable_json(path: str | Path, envelope: Mapping[str, Any]):
    if not verify_immutable_envelope(envelope):
        raise ValueError("refusing to write an invalid immutable envelope")
    destination = Path(path)
    with destination.open("x", encoding="utf-8", newline="\n") as handle:
        json.dump(
            envelope,
            handle,
            sort_keys=True,
            indent=2,
            ensure_ascii=False,
            allow_nan=False,
        )
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())


def load_immutable_json(path: str | Path) -> dict[str, Any]:
    source = Path(path)
    try:
        result = json.loads(
            source.read_text(encoding="utf-8"),
            object_pairs_hook=_reject_duplicate_json_keys,
        )
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as error:
        raise ValueError(f"could not read immutable JSON: {source}") from error
    if not verify_immutable_envelope(result):
        raise ValueError("immutable JSON has an invalid payload hash")
    return result


def _canonical_decimal(value: Decimal) -> str:
    rendered = format(value, "f")
    if "." in rendered:
        rendered = rendered.rstrip("0").rstrip(".")
    return rendered or "0"


def parse_drop_probability(value: Any) -> DropSpec:
    if isinstance(value, bool):
        raise ValueError("drop-probability must be a finite decimal in [0, 1)")
    try:
        probability = Decimal(str(value).strip())
    except (InvalidOperation, ValueError, AttributeError) as error:
        raise ValueError(
            "drop-probability must be a finite decimal in [0, 1)"
        ) from error
    if not probability.is_finite() or probability < 0 or probability >= 1:
        raise ValueError("drop-probability must be a finite decimal in [0, 1)")
    decimal_tuple = probability.as_tuple()
    required_precision = max(
        120,
        len(decimal_tuple.digits) + max(0, -decimal_tuple.exponent) + 10,
    )
    if required_precision > 10_000:
        raise ValueError("drop-probability has unreasonable decimal precision")
    with localcontext() as context:
        context.prec = required_precision
        keep = Decimal(1) - probability
        if probability == 0:
            threshold = UINT64_MODULUS
        else:
            # This is algebraically floor((1-p)*2^64), but avoids losing a
            # tiny positive p to cancellation when it is sub-uint64-scale.
            dropped_bins = int(
                (probability * Decimal(UINT64_MODULUS)).to_integral_value(
                    rounding=ROUND_CEILING
                )
            )
            threshold = UINT64_MODULUS - dropped_bins
    if not 0 < keep <= 1 or not 0 <= threshold <= UINT64_MODULUS:
        raise ValueError("drop-probability produced an invalid keep probability")
    return DropSpec(
        decimal=_canonical_decimal(probability),
        probability=probability,
        keep_decimal=_canonical_decimal(keep),
        keep_probability=keep,
        uint64_keep_threshold=threshold,
    )


def parse_uint64_seed(value: Any) -> int:
    if isinstance(value, bool):
        raise ValueError("seed must be an integer in [0, 2^64-1]")
    try:
        seed = int(value)
    except (TypeError, ValueError) as error:
        raise ValueError("seed must be an integer in [0, 2^64-1]") from error
    if str(value).strip() != str(seed) or not 0 <= seed <= UINT64_MASK:
        raise ValueError("seed must be an integer in [0, 2^64-1]")
    return seed


def _positive_chunk_elements(value: Any) -> int:
    if isinstance(value, bool):
        raise ValueError("chunk-elements must be a positive integer")
    try:
        result = int(value)
    except (TypeError, ValueError) as error:
        raise ValueError("chunk-elements must be a positive integer") from error
    if str(value).strip() != str(result) or result <= 0:
        raise ValueError("chunk-elements must be a positive integer")
    return result


def tensor_seed_domain_u64(tensor_name: str, seed: int) -> int:
    if not isinstance(tensor_name, str) or not tensor_name:
        raise ValueError("tensor name must be a non-empty string")
    seed = parse_uint64_seed(seed)
    digest = hashlib.sha256(
        b"checkpoint-delta-dare-tensor-seed-v2\x00"
        + seed.to_bytes(8, byteorder="little", signed=False)
        + b"\x00"
        + tensor_name.encode("utf-8")
    ).digest()
    return int.from_bytes(digest[:8], byteorder="little", signed=False)


def splitmix64(value: int) -> int:
    """Return the frozen SplitMix64 finalizer for one uint64 counter."""

    z = (int(value) + 0x9E3779B97F4A7C15) & UINT64_MASK
    z = ((z ^ (z >> 30)) * 0xBF58476D1CE4E5B9) & UINT64_MASK
    z = ((z ^ (z >> 27)) * 0x94D049BB133111EB) & UINT64_MASK
    return (z ^ (z >> 31)) & UINT64_MASK


def random_u64(tensor_name: str, flat_index: int, seed: int) -> int:
    seed = parse_uint64_seed(seed)
    if isinstance(flat_index, bool) or not isinstance(flat_index, int):
        raise ValueError("flat index must be a uint64 integer")
    if not 0 <= flat_index <= UINT64_MASK:
        raise ValueError("flat index must be a uint64 integer")
    counter = (tensor_seed_domain_u64(tensor_name, seed) + flat_index) & UINT64_MASK
    return splitmix64(counter)


def keep_element(
    tensor_name: str,
    flat_index: int,
    seed: int,
    drop_probability: DropSpec | Any,
) -> bool:
    spec = (
        drop_probability
        if isinstance(drop_probability, DropSpec)
        else parse_drop_probability(drop_probability)
    )
    if spec.is_identity:
        return True
    return (
        random_u64(tensor_name, flat_index, seed)
        < spec.uint64_keep_threshold
    )


def deterministic_keep_mask(
    tensor_name: str,
    *,
    start: int,
    count: int,
    seed: int,
    drop_probability: DropSpec | Any,
    torch,
    device,
):
    """Generate a device tensor from the frozen CPU uint64 counter function."""

    spec = (
        drop_probability
        if isinstance(drop_probability, DropSpec)
        else parse_drop_probability(drop_probability)
    )
    seed = parse_uint64_seed(seed)
    if (
        isinstance(start, bool)
        or isinstance(count, bool)
        or not isinstance(start, int)
        or not isinstance(count, int)
        or start < 0
        or count < 0
        or start + count > UINT64_MODULUS
    ):
        raise ValueError("mask range must fit in the uint64 counter domain")
    if count == 0:
        return torch.empty(0, dtype=torch.bool, device=device)
    if spec.is_identity:
        return torch.ones(count, dtype=torch.bool, device=device)

    # Numpy performs fixed-width unsigned operations on CPU.  The result is
    # copied to the requested device only after every Bernoulli decision is
    # final, so CUDA/CPU libraries cannot alter the RNG stream.
    import numpy as np

    with np.errstate(over="ignore"):
        values = np.arange(count, dtype=np.uint64)
        values += np.uint64(start)
        values += np.uint64(tensor_seed_domain_u64(tensor_name, seed))
        values += np.uint64(0x9E3779B97F4A7C15)
        values = (values ^ (values >> np.uint64(30))) * np.uint64(
            0xBF58476D1CE4E5B9
        )
        values = (values ^ (values >> np.uint64(27))) * np.uint64(
            0x94D049BB133111EB
        )
        values ^= values >> np.uint64(31)
    threshold = np.uint64(spec.uint64_keep_threshold)
    mask = np.asarray(values < threshold, dtype=np.bool_)
    return torch.from_numpy(mask.copy()).to(device=device)


def rng_contract() -> dict[str, Any]:
    return {
        "schema_version": RNG_SCHEMA_VERSION,
        "tensor_seed_domain": (
            "little_endian_uint64(first_8_bytes(SHA256("
            "b'checkpoint-delta-dare-tensor-seed-v2\\0' + "
            "little_endian_uint64_seed_bytes + b'\\0' + UTF8(canonical_name))))"
        ),
        "counter": "(tensor_seed_domain + row_major_flat_index) mod 2^64",
        "hash": (
            "SplitMix64 finalizer with add=0x9E3779B97F4A7C15, "
            "mul1=0xBF58476D1CE4E5B9, mul2=0x94D049BB133111EB"
        ),
        "decision": "keep iff random_uint64 < floor((1-p_decimal)*2^64)",
        "generation_device": "CPU uint64; completed boolean mask then copied",
        "stable_across": [
            "processes",
            "independent seed domains (not shifted adjacent streams)",
            "tensor traversal order",
            "chunk boundaries",
            "CPU/CUDA destination devices",
        ],
    }


def _exact_local_directory(path: str | Path, label: str) -> Path:
    candidate = Path(path)
    if not candidate.is_dir():
        raise ValueError(f"{label} must be an exact existing local directory: {path}")
    return candidate.resolve(strict=True)


def _tensor_sha256(tensor, torch) -> str:
    values = (
        tensor.detach().cpu().contiguous().view(torch.uint8).reshape(-1)
    )
    digest = hashlib.sha256()
    chunk_bytes = 64 * 1024 * 1024
    for start in range(0, int(values.numel()), chunk_bytes):
        digest.update(values[start : start + chunk_bytes].numpy().tobytes())
    return digest.hexdigest()


def _tensor_numel(tensor) -> int:
    result = 1
    for dimension in tensor.shape:
        result *= int(dimension)
    return result


def _is_floating_or_complex(tensor) -> bool:
    floating = getattr(tensor, "is_floating_point", lambda: False)()
    complex_value = getattr(tensor, "is_complex", lambda: False)()
    return bool(floating or complex_value)


def _assert_tensor_finite(name: str, tensor, torch, label: str):
    if not _is_floating_or_complex(tensor):
        return
    values = tensor.detach().reshape(-1)
    chunk_elements = 16 * 1024 * 1024
    for start in range(0, int(values.numel()), chunk_elements):
        if not bool(
            torch.isfinite(values[start : start + chunk_elements]).all().item()
        ):
            raise ValueError(f"{label} tensor contains nonfinite values: {name}")


def _read_json_object(path: Path, label: str) -> dict[str, Any]:
    try:
        result = json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=_reject_duplicate_json_keys,
        )
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ValueError(f"could not read {label}: {path}") from error
    if not isinstance(result, dict):
        raise ValueError(f"{label} must contain a JSON object")
    return result


def _validate_weight_map(
    root: Path,
    files: list[Path],
    discovered: Mapping[str, str],
) -> dict[str, str]:
    index_path = root / "model.safetensors.index.json"
    if len(files) > 1 and not index_path.is_file():
        raise ValueError("sharded checkpoint lacks model.safetensors.index.json")
    if not index_path.exists():
        return dict(discovered)
    if not index_path.is_file():
        raise ValueError("model.safetensors.index.json is not a regular file")
    index = _read_json_object(index_path, "Safetensors index")
    weight_map = index.get("weight_map")
    if not isinstance(weight_map, dict) or not weight_map:
        raise ValueError("Safetensors index has no non-empty weight_map")
    materialized = {}
    valid_files = {path.name for path in files}
    for key, filename in weight_map.items():
        if not isinstance(key, str) or not key:
            raise ValueError("Safetensors index contains an invalid tensor key")
        if (
            not isinstance(filename, str)
            or not filename
            or Path(filename).name != filename
            or filename not in valid_files
        ):
            raise ValueError(f"Safetensors index has invalid shard for tensor: {key}")
        materialized[key] = filename
    if materialized != dict(discovered):
        raise ValueError("Safetensors index weight_map differs from serialized shards")
    return materialized


def safetensors_logical_values_digest(
    tensor_inventory: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    """Reproduce the frozen ``safetensors_logical_values_v1`` digest."""

    if not isinstance(tensor_inventory, Mapping) or not tensor_inventory:
        raise ValueError("logical Safetensors inventory must be non-empty")
    records = []
    total_value_bytes = 0
    for key in sorted(tensor_inventory):
        source = tensor_inventory[key]
        try:
            record = {
                "key": key,
                "dtype": source["dtype"],
                "shape": source["shape"],
                "value_bytes": source["value_bytes"],
                "value_sha256": source["sha256"],
            }
        except (KeyError, TypeError) as error:
            raise ValueError(f"logical tensor record is incomplete: {key}") from error
        if (
            not isinstance(key, str)
            or not key
            or not isinstance(record["dtype"], str)
            or not record["dtype"]
            or not isinstance(record["shape"], list)
            or not isinstance(record["value_bytes"], int)
            or record["value_bytes"] <= 0
            or not isinstance(record["value_sha256"], str)
            or len(record["value_sha256"]) != 64
        ):
            raise ValueError(f"logical tensor record is malformed: {key}")
        total_value_bytes += record["value_bytes"]
        records.append(record)
    return {
        "schema": "safetensors_logical_values_v1",
        "tensor_count": len(records),
        "total_value_bytes": total_value_bytes,
        "logical_inventory_sha256": hashlib.sha256(
            canonical_json_bytes(records)
        ).hexdigest(),
    }


def scan_checkpoint(
    root: str | Path,
    *,
    label: str,
    runtime: Runtime,
) -> CheckpointSnapshot:
    source = _exact_local_directory(root, label)
    pickle_files = sorted(path for path in source.glob("*.bin") if path.is_file())
    if pickle_files:
        raise ValueError(f"{label} must not contain pickle .bin weights")
    files = sorted(path for path in source.glob("*.safetensors") if path.is_file())
    if not files:
        raise ValueError(f"{label} has no root-level Safetensors weights")
    invalid_names = [
        path.name
        for path in files
        if not (
            path.name == "model.safetensors"
            or (
                path.name.startswith("model-")
                and path.name.endswith(".safetensors")
            )
        )
    ]
    if invalid_names:
        raise ValueError(f"{label} contains non-model Safetensors files: {invalid_names}")

    weight_hashes = {path.name: sha256_file(path) for path in files}
    inventory: dict[str, dict[str, Any]] = {}
    key_to_file: dict[str, str] = {}
    metadata: dict[str, Mapping[str, str] | None] = {}
    for path in files:
        with runtime.safe_open(str(path), framework="pt", device="cpu") as handle:
            raw_metadata = handle.metadata()
            if raw_metadata is not None and (
                not isinstance(raw_metadata, dict)
                or any(
                    not isinstance(key, str) or not isinstance(value, str)
                    for key, value in raw_metadata.items()
                )
            ):
                raise ValueError(f"{label} shard metadata is malformed: {path.name}")
            metadata[path.name] = (
                dict(sorted(raw_metadata.items())) if raw_metadata is not None else None
            )
            for key in sorted(handle.keys()):
                if not isinstance(key, str) or not key or key in inventory:
                    raise ValueError(f"{label} has a duplicate or invalid tensor key: {key}")
                tensor = handle.get_tensor(key)
                if _tensor_numel(tensor) <= 0:
                    raise ValueError(f"{label} has an empty tensor: {key}")
                _assert_tensor_finite(key, tensor, runtime.torch, label)
                inventory[key] = {
                    "shape": [int(value) for value in tensor.shape],
                    "dtype": str(tensor.dtype),
                    "numel": _tensor_numel(tensor),
                    "value_bytes": int(_tensor_numel(tensor) * tensor.element_size()),
                    "sha256": _tensor_sha256(tensor, runtime.torch),
                }
                key_to_file[key] = path.name
    _validate_weight_map(source, files, key_to_file)
    ordered_inventory = dict(sorted(inventory.items()))
    ordered_map = dict(sorted(key_to_file.items()))
    logical = safetensors_logical_values_digest(ordered_inventory)
    return CheckpointSnapshot(
        root=source,
        weight_hashes=dict(sorted(weight_hashes.items())),
        tensor_inventory=ordered_inventory,
        key_to_file=ordered_map,
        file_metadata=dict(sorted(metadata.items())),
        inventory_sha256=payload_sha256(ordered_inventory),
        key_to_file_sha256=payload_sha256(ordered_map),
        logical_inventory_sha256=logical["logical_inventory_sha256"],
        logical_tensor_count=logical["tensor_count"],
        logical_total_value_bytes=logical["total_value_bytes"],
    )


def verify_source_contract(
    clean: CheckpointSnapshot,
    edited: CheckpointSnapshot,
    contract: SourceContract,
):
    if clean.weight_hashes != contract.clean_mapping():
        raise ValueError("clean checkpoint weight-file hashes do not match frozen pins")
    if edited.weight_hashes != contract.edited_mapping():
        raise ValueError("edited checkpoint weight-file hashes do not match frozen pins")
    edited_config = edited.root / "config.json"
    if not edited_config.is_file():
        raise ValueError("edited checkpoint has no config.json")
    if sha256_file(edited_config) != contract.edited_config_sha256:
        raise ValueError("edited config.json hash does not match frozen pin")
    if (
        edited.logical_inventory_sha256
        != contract.edited_logical_inventory_sha256
    ):
        raise ValueError(
            "edited logical Safetensors digest does not match frozen qualified donor"
        )


def _shape_contract(config: Mapping[str, Any]) -> dict[str, Any]:
    text = config.get("text_config")
    if not isinstance(text, Mapping):
        raise ValueError("Gemma-3 config has no text_config object")
    if text.get("model_type") != "gemma3_text":
        raise ValueError("Gemma-3 text_config has the wrong model_type")
    if text.get("num_hidden_layers") != 34:
        raise ValueError("Gemma-3 text_config has the wrong layer count")
    # The original HF snapshot omits several values that equal constructor
    # defaults, while save_pretrained materializes them in the qualified dense
    # donor.  Record every explicitly serialized geometry field and compare
    # their intersection below.  Exact tensor-key/shape/dtype equality remains
    # the authoritative complete architecture proof.
    fields = (
        "hidden_size",
        "intermediate_size",
        "num_hidden_layers",
        "num_attention_heads",
        "num_key_value_heads",
        "head_dim",
        "vocab_size",
    )
    return {
        "model_type": text["model_type"],
        "explicit_geometry": {field: text[field] for field in fields if field in text},
    }


def verify_model_configs(
    clean_root: Path,
    edited_root: Path,
    contract: SourceContract,
) -> dict[str, Any]:
    records = {}
    configs = {}
    for label, root in (("clean", clean_root), ("edited", edited_root)):
        path = root / "config.json"
        if not path.is_file():
            raise ValueError(f"{label} checkpoint has no config.json")
        config = _read_json_object(path, f"{label} config")
        if config.get("model_type") != contract.model_type:
            raise ValueError(f"{label} config model_type is not {contract.model_type}")
        architectures = config.get("architectures")
        if architectures != [contract.architecture]:
            raise ValueError(f"{label} config architecture is not frozen Gemma-3 wrapper")
        shape = _shape_contract(config)
        if shape["explicit_geometry"].get("num_hidden_layers") != contract.text_layers:
            raise ValueError(f"{label} config has the wrong text-layer count")
        configs[label] = config
        records[label] = {
            "path": str(path),
            "sha256": sha256_file(path),
            "shape_contract": shape,
        }
    clean_geometry = records["clean"]["shape_contract"]["explicit_geometry"]
    edited_geometry = records["edited"]["shape_contract"]["explicit_geometry"]
    shared_fields = sorted(set(clean_geometry) & set(edited_geometry))
    mismatched = [
        field
        for field in shared_fields
        if clean_geometry[field] != edited_geometry[field]
    ]
    if mismatched:
        raise ValueError(
            "clean and edited explicit Gemma-3 shape fields differ: "
            + ", ".join(mismatched)
        )
    records["shared_explicit_geometry_fields"] = shared_fields
    records["complete_tensor_geometry_proof"] = (
        "canonical tensor key/shape/dtype equality"
    )
    return records


def verify_declared_delta_surface(
    clean_inventory: Mapping[str, Mapping[str, Any]],
    edited_inventory: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    if not clean_inventory or not edited_inventory:
        raise ValueError("checkpoint tensor inventories must be non-empty")
    clean_keys = set(clean_inventory)
    edited_keys = set(edited_inventory)
    if clean_keys != edited_keys:
        missing = sorted(clean_keys ^ edited_keys)
        raise ValueError(
            "clean and edited canonical tensor keys differ: " + ", ".join(missing[:5])
        )
    for key in sorted(clean_keys):
        clean = clean_inventory[key]
        edited = edited_inventory[key]
        for field in ("shape", "dtype", "numel"):
            if clean.get(field) != edited.get(field):
                raise ValueError(f"clean and edited tensor {field} differs: {key}")

    declared = set(DECLARED_EDIT_KEYS)
    missing_declared = sorted(declared - clean_keys)
    if missing_declared:
        raise ValueError(
            "checkpoint lacks declared DARE linears: " + ", ".join(missing_declared[:5])
        )
    for key in DECLARED_EDIT_KEYS:
        record = clean_inventory[key]
        if len(record["shape"]) != 2 or not str(record["dtype"]).startswith("torch."):
            raise ValueError(f"declared DARE module is not a 2D torch weight: {key}")
        bias_key = key[: -len("weight")] + "bias"
        if bias_key in clean_keys:
            raise ValueError(f"declared DARE linear unexpectedly has a bias: {bias_key}")

    actual_changed = {
        key
        for key in clean_keys
        if clean_inventory[key].get("sha256") != edited_inventory[key].get("sha256")
    }
    if actual_changed != declared:
        unexpected = sorted(actual_changed - declared)
        unchanged_declared = sorted(declared - actual_changed)
        details = []
        if unexpected:
            details.append("unexpected=" + ",".join(unexpected[:5]))
        if unchanged_declared:
            details.append("declared_without_delta=" + ",".join(unchanged_declared[:5]))
        raise ValueError(
            "nonzero clean-to-edited tensor surface is not exactly the frozen "
            "98 linears (" + "; ".join(details) + ")"
        )
    return {
        "declared_key_count": len(declared),
        "actual_changed_key_count": len(actual_changed),
        "declared_keys": list(DECLARED_EDIT_KEYS),
        "actual_changed_keys": sorted(actual_changed),
        "exact": True,
        "bias_free": True,
    }


def verify_output_locality(
    clean_inventory: Mapping[str, Mapping[str, Any]],
    output_inventory: Mapping[str, Mapping[str, Any]],
) -> list[str]:
    if set(clean_inventory) != set(output_inventory):
        raise RuntimeError("output tensor keys differ from the clean checkpoint")
    changed = []
    declared = set(DECLARED_EDIT_KEYS)
    for key in sorted(clean_inventory):
        clean = clean_inventory[key]
        output = output_inventory[key]
        for field in ("shape", "dtype", "numel"):
            if clean.get(field) != output.get(field):
                raise RuntimeError(f"output tensor {field} differs from clean: {key}")
        if clean.get("sha256") != output.get("sha256"):
            if key not in declared:
                raise RuntimeError(f"DARE output mutation escaped declared surface: {key}")
            changed.append(key)
    return changed


def verify_tensor_application_records(
    records: Iterable[Mapping[str, Any]],
    clean_inventory: Mapping[str, Mapping[str, Any]],
    edited_inventory: Mapping[str, Mapping[str, Any]],
    output_inventory: Mapping[str, Mapping[str, Any]],
) -> list[dict[str, Any]]:
    materialized = [dict(record) for record in records]
    materialized.sort(key=lambda record: str(record.get("tensor_name")))
    names = [record.get("tensor_name") for record in materialized]
    if names != sorted(DECLARED_EDIT_KEYS):
        raise RuntimeError(
            "DARE tensor records are not one complete canonical surface ordering"
        )
    for record in materialized:
        name = record["tensor_name"]
        bindings = (
            ("clean_sha256", clean_inventory),
            ("edited_sha256", edited_inventory),
            ("output_sha256", output_inventory),
        )
        for field, inventory in bindings:
            if record.get(field) != inventory[name].get("sha256"):
                raise RuntimeError(f"DARE tensor record {field} is unbound: {name}")
        if record.get("shape") != clean_inventory[name].get("shape"):
            raise RuntimeError(f"DARE tensor record shape is unbound: {name}")
        if record.get("dtype") != clean_inventory[name].get("dtype"):
            raise RuntimeError(f"DARE tensor record dtype is unbound: {name}")
        counts = record.get("counts")
        if not isinstance(counts, Mapping):
            raise RuntimeError(f"DARE tensor record has no counts: {name}")
        if counts.get("elements") != clean_inventory[name].get("numel"):
            raise RuntimeError(f"DARE tensor record element count is unbound: {name}")
    return materialized


def _load_tensor(snapshot: CheckpointSnapshot, key: str, runtime: Runtime):
    filename = snapshot.key_to_file.get(key)
    if filename is None:
        raise ValueError(f"checkpoint has no shard mapping for tensor: {key}")
    with runtime.safe_open(
        str(snapshot.root / filename), framework="pt", device="cpu"
    ) as handle:
        return handle.get_tensor(key)


def _new_norm_accumulator() -> dict[str, float | int]:
    return {"squared": 0.0, "max_abs": 0.0}


def _update_norm(accumulator: dict[str, float | int], tensor, torch):
    if tensor.numel() == 0:
        return
    values = tensor.detach().to(device="cpu", dtype=torch.float64)
    accumulator["squared"] += float(torch.sum(values * values).item())
    accumulator["max_abs"] = max(
        float(accumulator["max_abs"]), float(torch.max(torch.abs(values)).item())
    )


def _finish_norm(accumulator: Mapping[str, float | int]) -> dict[str, float]:
    squared = float(accumulator["squared"])
    if not math.isfinite(squared) or squared < 0:
        raise RuntimeError("delta norm accumulator is nonfinite or negative")
    return {
        "l2": math.sqrt(squared),
        "max_abs": float(accumulator["max_abs"]),
    }


def _float32_keep_probability(spec: DropSpec, torch, device):
    value = torch.tensor(
        float(spec.keep_probability), dtype=torch.float32, device=device
    )
    if not bool(torch.isfinite(value).item()) or not bool((value > 0).item()):
        raise ValueError("1-p is not representable as a positive finite float32")
    return value


def transform_tensor(
    clean,
    edited,
    *,
    tensor_name: str,
    seed: int,
    drop_probability: DropSpec | Any,
    chunk_elements: int,
    compute_device: str,
    torch,
) -> tuple[Any, dict[str, Any]]:
    """Apply the frozen DARE arithmetic to one verified source tensor."""

    spec = (
        drop_probability
        if isinstance(drop_probability, DropSpec)
        else parse_drop_probability(drop_probability)
    )
    seed = parse_uint64_seed(seed)
    chunk_elements = _positive_chunk_elements(chunk_elements)
    if tuple(clean.shape) != tuple(edited.shape) or clean.dtype != edited.dtype:
        raise ValueError(f"clean/edited tensor shape or dtype mismatch: {tensor_name}")
    if len(clean.shape) != 2 or not _is_floating_or_complex(clean) or clean.is_complex():
        raise ValueError(f"DARE supports only real floating 2D linears: {tensor_name}")
    _assert_tensor_finite(tensor_name, clean, torch, "clean")
    _assert_tensor_finite(tensor_name, edited, torch, "edited")
    device = torch.device(compute_device)
    if device.type == "cuda" and not torch.cuda.is_available():
        raise ValueError("CUDA compute device requested but CUDA is unavailable")
    keep32 = _float32_keep_probability(spec, torch, device)
    clean_flat = clean.detach().contiguous().view(-1)
    edited_flat = edited.detach().contiguous().view(-1)
    output_flat = torch.empty_like(clean_flat, device="cpu")
    source_norm = _new_norm_accumulator()
    rescaled_norm = _new_norm_accumulator()
    serialized_norm = _new_norm_accumulator()
    counts = {
        "elements": int(clean_flat.numel()),
        "source_delta_nonzero": 0,
        "mask_kept": 0,
        "mask_dropped": 0,
        "source_delta_kept": 0,
        "source_delta_dropped": 0,
        "serialized_changed_from_clean": 0,
        "serialized_equal_edited": 0,
    }
    for start in range(0, counts["elements"], chunk_elements):
        end = min(start + chunk_elements, counts["elements"])
        clean_native = clean_flat[start:end].to(device=device)
        edited_native = edited_flat[start:end].to(device=device)
        clean32 = clean_native.to(dtype=torch.float32)
        edited32 = edited_native.to(dtype=torch.float32)
        delta32 = edited32 - clean32
        if not bool(torch.isfinite(delta32).all().item()):
            raise ValueError(f"source delta contains nonfinite values: {tensor_name}")
        mask = deterministic_keep_mask(
            tensor_name,
            start=start,
            count=end - start,
            seed=seed,
            drop_probability=spec,
            torch=torch,
            device=device,
        )
        source_changed = delta32 != 0
        adjusted_delta32 = torch.where(
            mask,
            delta32 / keep32,
            torch.zeros_like(delta32),
        )
        if not bool(torch.isfinite(adjusted_delta32).all().item()):
            raise ValueError(f"rescaled delta contains nonfinite values: {tensor_name}")
        output_native = (clean32 + adjusted_delta32).to(dtype=clean.dtype)
        if not bool(torch.isfinite(output_native).all().item()):
            raise ValueError(f"DARE output contains nonfinite values: {tensor_name}")
        serialized_delta32 = output_native.to(dtype=torch.float32) - clean32
        counts["source_delta_nonzero"] += int(source_changed.sum().item())
        counts["mask_kept"] += int(mask.sum().item())
        counts["mask_dropped"] += int((~mask).sum().item())
        counts["source_delta_kept"] += int((source_changed & mask).sum().item())
        counts["source_delta_dropped"] += int(
            (source_changed & (~mask)).sum().item()
        )
        counts["serialized_changed_from_clean"] += int(
            (output_native != clean_native).sum().item()
        )
        counts["serialized_equal_edited"] += int(
            (output_native == edited_native).sum().item()
        )
        _update_norm(source_norm, delta32, torch)
        _update_norm(rescaled_norm, adjusted_delta32, torch)
        _update_norm(serialized_norm, serialized_delta32, torch)
        output_flat[start:end].copy_(output_native.to(device="cpu"))

    if counts["source_delta_nonzero"] <= 0:
        raise ValueError(f"declared DARE tensor has no elementwise delta: {tensor_name}")
    if counts["mask_kept"] + counts["mask_dropped"] != counts["elements"]:
        raise RuntimeError("DARE mask counts do not cover the complete tensor")
    if (
        counts["source_delta_kept"] + counts["source_delta_dropped"]
        != counts["source_delta_nonzero"]
    ):
        raise RuntimeError("DARE changed-element mask counts are inconsistent")
    output = output_flat.view(clean.shape)
    return output, {
        "tensor_name": tensor_name,
        "rng_tensor_seed_domain_u64": tensor_seed_domain_u64(tensor_name, seed),
        "shape": [int(value) for value in clean.shape],
        "dtype": str(clean.dtype),
        "counts": counts,
        "source_delta_norm": _finish_norm(source_norm),
        "rescaled_masked_delta_norm_before_cast": _finish_norm(rescaled_norm),
        "serialized_delta_norm_after_cast": _finish_norm(serialized_norm),
        "clean_sha256": _tensor_sha256(clean, torch),
        "edited_sha256": _tensor_sha256(edited, torch),
        "output_sha256": _tensor_sha256(output, torch),
    }


def source_delta_stats(
    clean,
    edited,
    *,
    tensor_name: str,
    chunk_elements: int,
    compute_device: str,
    torch,
) -> dict[str, Any]:
    output, record = transform_tensor(
        clean,
        edited,
        tensor_name=tensor_name,
        seed=0,
        drop_probability=parse_drop_probability("0"),
        chunk_elements=chunk_elements,
        compute_device=compute_device,
        torch=torch,
    )
    if _tensor_sha256(output, torch) != _tensor_sha256(edited, torch):
        raise RuntimeError(f"p=0 tensor identity failed: {tensor_name}")
    return record


def _copy_file_exclusive(source: Path, destination: Path):
    if os.path.lexists(destination):
        raise FileExistsError(f"refusing to replace staged artifact: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    # Opening with xb closes the check/copy race inside the private stage.
    with source.open("rb") as reader, destination.open("xb") as writer:
        shutil.copyfileobj(reader, writer, length=1024 * 1024)
        writer.flush()
        os.fsync(writer.fileno())
    shutil.copystat(source, destination, follow_symlinks=True)


MODEL_SUPPORT_NAMES = {"config.json", "generation_config.json"}
TOKENIZER_NAMES = {
    "added_tokens.json",
    "chat_template.json",
    "merges.txt",
    "special_tokens_map.json",
    "spiece.model",
    "tokenizer.json",
    "tokenizer.model",
    "tokenizer_config.json",
    "vocab.json",
}


def selected_file_manifest(
    root: Path,
    *,
    names: set[str],
    chat_templates: bool = False,
) -> dict[str, Any]:
    files = [
        path
        for path in root.iterdir()
        if path.is_file()
        and (path.name in names or (chat_templates and path.name.startswith("chat_template")))
    ]
    records = [
        {
            "path": path.name,
            "bytes": path.stat().st_size,
            "sha256": sha256_file(path),
        }
        for path in sorted(files, key=lambda item: item.name)
    ]
    if not records:
        raise ValueError(f"selected artifact manifest is empty: {root}")
    return {"files": records, "manifest_sha256": payload_sha256(records)}


def _copy_manifest(source: Path, manifest: Mapping[str, Any], destination: Path):
    records = manifest.get("files")
    if not isinstance(records, list) or not records:
        raise ValueError("artifact manifest has no files")
    for record in records:
        if not isinstance(record, Mapping) or Path(record.get("path", "")).name != record.get("path"):
            raise ValueError("artifact manifest contains an unsafe path")
        source_file = source / record["path"]
        if (
            not source_file.is_file()
            or source_file.stat().st_size != record.get("bytes")
            or sha256_file(source_file) != record.get("sha256")
        ):
            raise RuntimeError(f"source artifact changed before copy: {source_file}")
        _copy_file_exclusive(source_file, destination / record["path"])


def directory_manifest(root: Path, *, excluded_names: set[str] | None = None) -> dict:
    excluded_names = excluded_names or set()
    records = [
        {
            "path": path.relative_to(root).as_posix(),
            "bytes": path.stat().st_size,
            "sha256": sha256_file(path),
        }
        for path in sorted(
            (path for path in root.rglob("*") if path.is_file() and path.name not in excluded_names),
            key=lambda item: item.relative_to(root).as_posix(),
        )
    ]
    return {"files": records, "manifest_sha256": payload_sha256(records)}


def _save_weights(
    clean: CheckpointSnapshot,
    edited: CheckpointSnapshot,
    destination: Path,
    *,
    spec: DropSpec,
    seed: int,
    chunk_elements: int,
    compute_device: str,
    runtime: Runtime,
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    if spec.is_identity:
        for filename in sorted(edited.weight_hashes):
            _copy_file_exclusive(edited.root / filename, destination / filename)
        index = edited.root / "model.safetensors.index.json"
        if index.is_file():
            _copy_file_exclusive(index, destination / index.name)
        for key in DECLARED_EDIT_KEYS:
            clean_tensor = _load_tensor(clean, key, runtime)
            edited_tensor = _load_tensor(edited, key, runtime)
            record = source_delta_stats(
                clean_tensor,
                edited_tensor,
                tensor_name=key,
                chunk_elements=chunk_elements,
                compute_device=compute_device,
                torch=runtime.torch,
            )
            record["drop_probability"] = spec.decimal
            record["seed"] = seed
            record["p0_edited_tensor_identity"] = True
            records.append(record)
        return records

    declared = set(DECLARED_EDIT_KEYS)
    for filename in sorted(edited.weight_hashes):
        source_path = edited.root / filename
        output_path = destination / filename
        with runtime.safe_open(
            str(source_path), framework="pt", device="cpu"
        ) as handle:
            tensors = {}
            for key in sorted(handle.keys()):
                edited_tensor = handle.get_tensor(key)
                if key not in declared:
                    tensors[key] = edited_tensor
                    continue
                clean_tensor = _load_tensor(clean, key, runtime)
                output, record = transform_tensor(
                    clean_tensor,
                    edited_tensor,
                    tensor_name=key,
                    seed=seed,
                    drop_probability=spec,
                    chunk_elements=chunk_elements,
                    compute_device=compute_device,
                    torch=runtime.torch,
                )
                record["drop_probability"] = spec.decimal
                record["seed"] = seed
                record["p0_edited_tensor_identity"] = False
                tensors[key] = output
                records.append(record)
            metadata = edited.file_metadata.get(filename)
            runtime.save_file(tensors, str(output_path), metadata=metadata)
            with output_path.open("rb") as saved:
                os.fsync(saved.fileno())
    index = edited.root / "model.safetensors.index.json"
    if index.is_file():
        _copy_file_exclusive(index, destination / index.name)
    records.sort(key=lambda record: record["tensor_name"])
    if [record["tensor_name"] for record in records] != sorted(DECLARED_EDIT_KEYS):
        raise RuntimeError("not every declared DARE tensor was transformed exactly once")
    return records


def verify_hf_text_reload(root: Path) -> dict[str, Any]:
    from transformers import AutoConfig, AutoTokenizer

    config = AutoConfig.from_pretrained(
        str(root), local_files_only=True, trust_remote_code=False
    )
    tokenizer = AutoTokenizer.from_pretrained(
        str(root), local_files_only=True, trust_remote_code=False
    )
    chat_template = getattr(tokenizer, "chat_template", None)
    return {
        "config_class": type(config).__name__,
        "model_type": getattr(config, "model_type", None),
        "tokenizer_class": type(tokenizer).__name__,
        "vocab_size": len(tokenizer),
        "chat_template_sha256": (
            payload_sha256(chat_template) if chat_template is not None else None
        ),
        "local_files_only": True,
        "trust_remote_code": False,
    }


def verify_tokenizer_reload_contract(record: Mapping[str, Any], *, label: str) -> dict:
    if not isinstance(record, Mapping):
        raise ValueError(f"{label} tokenizer reload record must be an object")
    tokenizer_class = record.get("tokenizer_class")
    vocab_size = record.get("vocab_size")
    chat_hash = record.get("chat_template_sha256")
    if not isinstance(tokenizer_class, str) or not tokenizer_class:
        raise ValueError(f"{label} tokenizer reload has no class")
    if isinstance(vocab_size, bool) or not isinstance(vocab_size, int) or vocab_size <= 0:
        raise ValueError(f"{label} tokenizer reload has invalid vocabulary size")
    if not isinstance(chat_hash, str) or len(chat_hash) != 64:
        raise ValueError(f"{label} tokenizer reload has no bound chat template")
    return {
        "tokenizer_class": tokenizer_class,
        "vocab_size": vocab_size,
        "chat_template_sha256": chat_hash,
    }


def git_provenance(script_path: Path, *, strict: bool) -> dict[str, Any]:
    repo_root = script_path.parents[1]
    relative = script_path.relative_to(repo_root).as_posix()

    def run_bytes(*arguments: str):
        return subprocess.run(
            ["git", *arguments],
            cwd=repo_root,
            check=False,
            capture_output=True,
        )

    head = run_bytes("rev-parse", "HEAD")
    tracked = run_bytes("ls-files", "--error-unmatch", "--", relative)
    status = run_bytes("status", "--porcelain=v1", "--", relative)
    committed = run_bytes("show", f"HEAD:{relative}")
    current_sha = sha256_file(script_path)
    record = {
        "head": head.stdout.decode("utf-8", errors="replace").strip(),
        "head_returncode": head.returncode,
        "tracked_returncode": tracked.returncode,
        "source_status": status.stdout.decode("utf-8", errors="replace").strip(),
        "status_returncode": status.returncode,
        "current_sha256": current_sha,
        "committed_sha256": (
            hashlib.sha256(committed.stdout).hexdigest()
            if committed.returncode == 0
            else None
        ),
    }
    record["clean_at_head"] = (
        head.returncode == 0
        and tracked.returncode == 0
        and status.returncode == 0
        and committed.returncode == 0
        and not record["source_status"]
        and record["current_sha256"] == record["committed_sha256"]
    )
    if strict and not record["clean_at_head"]:
        raise RuntimeError("DARE implementation is not a clean tracked file at HEAD")
    return record


def _path_lexists(path: Path) -> bool:
    return os.path.lexists(path)


def _publish_directory_no_replace(temporary: Path, destination: Path):
    if _path_lexists(destination):
        raise FileExistsError(f"refusing to replace existing output: {destination}")
    if os.name == "posix" and sys.platform.startswith("linux"):
        libc = ctypes.CDLL(None, use_errno=True)
        renameat2 = getattr(libc, "renameat2", None)
        if renameat2 is None:
            raise RuntimeError("Linux runtime lacks atomic no-replace renameat2")
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
        raise OSError(error_number, os.strerror(error_number), destination)
    if os.name == "posix":
        raise RuntimeError("atomic no-replace publication is unsupported here")
    if _path_lexists(destination):
        raise FileExistsError(f"refusing to replace existing output: {destination}")
    os.rename(temporary, destination)


def _fsync_files(root: Path):
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if os.name != "nt":
            with path.open("rb") as handle:
                os.fsync(handle.fileno())
            continue
        original_mode = stat.S_IMODE(path.stat().st_mode)
        try:
            os.chmod(path, original_mode | stat.S_IWRITE)
            with path.open("r+b") as handle:
                os.fsync(handle.fileno())
        finally:
            os.chmod(path, original_mode)


def _fsync_directory(path: Path):
    if os.name == "nt":
        return
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _remove_private_stage(stage: Path, parent: Path, prefix: str):
    if not stage.exists():
        return
    if stage.parent.resolve() != parent.resolve() or not stage.name.startswith(prefix):
        raise RuntimeError(f"refusing to clean unexpected staging path: {stage}")
    shutil.rmtree(stage)


def production_runtime() -> Runtime:
    import numpy
    import safetensors
    import torch
    from safetensors import safe_open
    from safetensors.torch import save_file

    return Runtime(
        torch=torch,
        safe_open=safe_open,
        save_file=save_file,
        versions={
            "python": sys.version,
            "torch": torch.__version__,
            "safetensors": safetensors.__version__,
            "numpy": numpy.__version__,
        },
    )


def _unchanged_weight_hashes(snapshot: CheckpointSnapshot) -> bool:
    return {
        filename: sha256_file(snapshot.root / filename)
        for filename in sorted(snapshot.weight_hashes)
    } == dict(snapshot.weight_hashes)


def _manifest_unchanged(root: Path, manifest: Mapping[str, Any]) -> bool:
    try:
        actual = selected_file_manifest(
            root,
            names={record["path"] for record in manifest["files"]},
            chat_templates=False,
        )
    except (KeyError, TypeError, ValueError, OSError):
        return False
    return actual == manifest


def apply_checkpoint_delta_dare(
    *,
    clean_model: str | Path,
    edited_model: str | Path,
    tokenizer_model: str | Path,
    output_dir: str | Path,
    drop_probability: DropSpec | Any,
    seed: int,
    chunk_elements: int = 1_048_576,
    compute_device: str = "cpu",
    runtime: Runtime | None = None,
    source_contract: SourceContract = PINNED_SOURCE_CONTRACT,
    strict_git: bool = True,
    reload_verifier: Callable[[Path], Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Verify, transform, serialize, reload, and atomically publish one run."""

    spec = (
        drop_probability
        if isinstance(drop_probability, DropSpec)
        else parse_drop_probability(drop_probability)
    )
    seed = parse_uint64_seed(seed)
    chunk_elements = _positive_chunk_elements(chunk_elements)
    if not isinstance(compute_device, str) or not compute_device:
        raise ValueError("compute-device must be a non-empty torch device string")
    clean_root = _exact_local_directory(clean_model, "clean-model")
    edited_root = _exact_local_directory(edited_model, "edited-model")
    tokenizer_root = _exact_local_directory(tokenizer_model, "tokenizer-model")
    if clean_root == edited_root:
        raise ValueError("clean and edited checkpoints must be different directories")
    if tokenizer_root != clean_root:
        raise ValueError("tokenizer-model must be the exact clean-model directory")
    destination = Path(output_dir).absolute()
    if _path_lexists(destination):
        raise FileExistsError(f"refusing to replace existing output: {destination}")
    for source, label in (
        (clean_root, "clean"),
        (edited_root, "edited"),
        (tokenizer_root, "tokenizer"),
    ):
        try:
            destination.resolve().relative_to(source)
        except ValueError:
            pass
        else:
            raise ValueError(f"output directory cannot be inside the {label} source")

    script_path = Path(__file__).resolve()
    script_sha256 = sha256_file(script_path)
    git_before = git_provenance(script_path, strict=strict_git)
    runtime = runtime or production_runtime()
    clean = scan_checkpoint(clean_root, label="clean-model", runtime=runtime)
    edited = scan_checkpoint(edited_root, label="edited-model", runtime=runtime)
    verify_source_contract(clean, edited, source_contract)
    config_records = verify_model_configs(clean.root, edited.root, source_contract)
    surface_proof = verify_declared_delta_surface(
        clean.tensor_inventory, edited.tensor_inventory
    )
    model_support = selected_file_manifest(
        edited.root, names=MODEL_SUPPORT_NAMES, chat_templates=False
    )
    tokenizer_support = selected_file_manifest(
        tokenizer_root, names=TOKENIZER_NAMES, chat_templates=True
    )
    if not any(
        record["path"] in {"tokenizer.json", "tokenizer.model", "spiece.model"}
        for record in tokenizer_support["files"]
    ):
        raise ValueError("tokenizer source lacks a standalone tokenizer artifact")
    reload_verifier = reload_verifier or verify_hf_text_reload
    source_text_reload = dict(reload_verifier(clean.root))
    if source_text_reload.get("model_type") != source_contract.model_type:
        raise ValueError("clean tokenizer source config has the wrong model type")
    source_tokenizer_runtime = verify_tokenizer_reload_contract(
        source_text_reload, label="clean source"
    )

    destination.parent.mkdir(parents=True, exist_ok=True)
    stage_prefix = f".{destination.name}.tmp-"
    stage = Path(tempfile.mkdtemp(prefix=stage_prefix, dir=destination.parent))
    published = False
    try:
        tensor_records = _save_weights(
            clean,
            edited,
            stage,
            spec=spec,
            seed=seed,
            chunk_elements=chunk_elements,
            compute_device=compute_device,
            runtime=runtime,
        )
        _copy_manifest(edited.root, model_support, stage)
        _copy_manifest(tokenizer_root, tokenizer_support, stage)
        if (stage / SIDECAR_NAME).exists():
            raise FileExistsError(f"reserved provenance sidecar already exists: {SIDECAR_NAME}")

        output = scan_checkpoint(stage, label="staged-output", runtime=runtime)
        changed_output_keys = verify_output_locality(
            clean.tensor_inventory, output.tensor_inventory
        )
        tensor_records = verify_tensor_application_records(
            tensor_records,
            clean.tensor_inventory,
            edited.tensor_inventory,
            output.tensor_inventory,
        )
        if output.key_to_file != edited.key_to_file:
            raise RuntimeError("output shard/key layout differs from edited checkpoint")
        if spec.is_identity:
            if output.weight_hashes != edited.weight_hashes:
                raise RuntimeError("p=0 did not preserve edited weight-file bytes")
            if output.tensor_inventory != edited.tensor_inventory:
                raise RuntimeError("p=0 did not preserve edited tensor state")
        elif output.tensor_inventory == edited.tensor_inventory:
            raise RuntimeError("nonzero drop probability unexpectedly reproduced dense edit")

        text_reload = dict(reload_verifier(stage))
        if text_reload.get("model_type") != source_contract.model_type:
            raise RuntimeError("reloaded output config has the wrong model type")
        output_tokenizer_runtime = verify_tokenizer_reload_contract(
            text_reload, label="output"
        )
        if output_tokenizer_runtime != source_tokenizer_runtime:
            raise RuntimeError("output tokenizer runtime differs from exact clean source")
        output_manifest = directory_manifest(stage, excluded_names={SIDECAR_NAME})

        # Bind sources and implementation again after all expensive work and
        # before publication.  This closes the practical source/code TOCTOU
        # window without trusting mtimes.
        if not _unchanged_weight_hashes(clean) or not _unchanged_weight_hashes(edited):
            raise RuntimeError("source checkpoint weight files changed during DARE run")
        if not _manifest_unchanged(edited.root, model_support):
            raise RuntimeError("edited model support files changed during DARE run")
        if not _manifest_unchanged(tokenizer_root, tokenizer_support):
            raise RuntimeError("tokenizer files changed during DARE run")
        if sha256_file(script_path) != script_sha256:
            raise RuntimeError("DARE implementation changed during execution")
        git_after = git_provenance(script_path, strict=strict_git)
        if strict_git and git_after != git_before:
            raise RuntimeError("DARE implementation git binding changed during execution")

        planned_grid = {
            "drop_probabilities": list(PRECOMMITTED_DROP_PROBABILITIES),
            "identity_seed": 0,
            "nonzero_probability_seeds": list(PRECOMMITTED_NONZERO_SEEDS),
            "nonzero_design": "full_cross_product",
            "request_is_precommitted": is_precommitted_request(spec, seed),
        }
        payload = {
            "schema_version": APPLICATION_SCHEMA_VERSION,
            "created_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
            "operation": "deterministic_DARE_on_verified_checkpoint_delta",
            "request": {
                "drop_probability_decimal": spec.decimal,
                "keep_probability_decimal": spec.keep_decimal,
                "uint64_keep_threshold": spec.uint64_keep_threshold,
                "seed_uint64": seed,
                "chunk_elements": chunk_elements,
                "compute_device": compute_device,
                "output_dir": str(destination),
            },
            "precommitted_grid": planned_grid,
            "method": {
                "rng": rng_contract(),
                "delta": "edited.float32 - clean.float32",
                "mask": "deterministic Bernoulli keep mask",
                "rescaling": "where(mask, delta/(1-p), exact_FP32_zero)",
                "merge": "clean.float32 + rescaled_delta32, then cast clean dtype",
                "p0_rule": "copy edited Safetensors files byte-for-byte after proof",
                "surface": "exact frozen 98 bias-free linears",
            },
            "sources": {
                "frozen_contract": {
                    "clean_weight_file_sha256": source_contract.clean_mapping(),
                    "edited_weight_file_sha256": source_contract.edited_mapping(),
                    "edited_config_sha256": source_contract.edited_config_sha256,
                    "edited_logical_inventory_sha256": (
                        source_contract.edited_logical_inventory_sha256
                    ),
                    "model_type": source_contract.model_type,
                    "architecture": source_contract.architecture,
                    "text_layers": source_contract.text_layers,
                    "contract_sha256": payload_sha256(
                        {
                            "clean": source_contract.clean_mapping(),
                            "edited": source_contract.edited_mapping(),
                            "edited_config": source_contract.edited_config_sha256,
                            "edited_logical_inventory": (
                                source_contract.edited_logical_inventory_sha256
                            ),
                            "model_type": source_contract.model_type,
                            "architecture": source_contract.architecture,
                            "text_layers": source_contract.text_layers,
                        }
                    ),
                },
                "clean": {
                    "path": str(clean.root),
                    "weight_file_sha256": dict(clean.weight_hashes),
                    "tensor_inventory": dict(clean.tensor_inventory),
                    "tensor_inventory_sha256": clean.inventory_sha256,
                    "safetensors_logical_values_v1": {
                        "logical_inventory_sha256": clean.logical_inventory_sha256,
                        "tensor_count": clean.logical_tensor_count,
                        "total_value_bytes": clean.logical_total_value_bytes,
                    },
                    "key_to_file": dict(clean.key_to_file),
                    "key_to_file_sha256": clean.key_to_file_sha256,
                },
                "edited": {
                    "path": str(edited.root),
                    "weight_file_sha256": dict(edited.weight_hashes),
                    "tensor_inventory": dict(edited.tensor_inventory),
                    "tensor_inventory_sha256": edited.inventory_sha256,
                    "safetensors_logical_values_v1": {
                        "expected_logical_inventory_sha256": (
                            source_contract.edited_logical_inventory_sha256
                        ),
                        "actual_logical_inventory_sha256": (
                            edited.logical_inventory_sha256
                        ),
                        "matched_frozen_qualified_donor": True,
                        "tensor_count": edited.logical_tensor_count,
                        "total_value_bytes": edited.logical_total_value_bytes,
                    },
                    "key_to_file": dict(edited.key_to_file),
                    "key_to_file_sha256": edited.key_to_file_sha256,
                    "model_support_manifest": model_support,
                },
                "tokenizer": {
                    "path": str(tokenizer_root),
                    "manifest": tokenizer_support,
                    "reload_runtime": source_tokenizer_runtime,
                },
                "configs": config_records,
            },
            "delta_surface_proof": surface_proof,
            "tensors": tensor_records,
            "output": {
                "weight_file_sha256": dict(output.weight_hashes),
                "tensor_inventory": dict(output.tensor_inventory),
                "tensor_inventory_sha256": output.inventory_sha256,
                "safetensors_logical_values_v1": {
                    "logical_inventory_sha256": output.logical_inventory_sha256,
                    "tensor_count": output.logical_tensor_count,
                    "total_value_bytes": output.logical_total_value_bytes,
                },
                "key_to_file": dict(output.key_to_file),
                "key_to_file_sha256": output.key_to_file_sha256,
                "changed_from_clean_keys": changed_output_keys,
                "p0_edited_weight_file_identity": (
                    spec.is_identity and output.weight_hashes == edited.weight_hashes
                ),
                "p0_edited_tensor_state_identity": (
                    spec.is_identity
                    and output.tensor_inventory == edited.tensor_inventory
                ),
                "artifact_manifest_excluding_sidecar": output_manifest,
                "reload_verification": {
                    "all_safetensors_reopened_and_hashed": True,
                    "all_tensor_keys_shapes_dtypes_verified": True,
                    "text_config_and_tokenizer_reloaded": text_reload,
                },
                "standalone_text_model_and_tokenizer": True,
                "serialization_contract": "Safetensors_only",
            },
            "runtime": dict(runtime.versions),
            "implementation": {
                "path": str(script_path),
                "sha256": script_sha256,
                "git": git_before,
            },
        }
        provenance = immutable_envelope(payload)
        write_immutable_json(stage / SIDECAR_NAME, provenance)
        if load_immutable_json(stage / SIDECAR_NAME) != provenance:
            raise RuntimeError("immutable DARE sidecar did not round-trip")
        if sha256_file(script_path) != script_sha256:
            raise RuntimeError("DARE implementation changed before publication")
        if not _unchanged_weight_hashes(clean) or not _unchanged_weight_hashes(edited):
            raise RuntimeError("source checkpoint changed before publication")
        _fsync_files(stage)
        _fsync_directory(stage)
        _publish_directory_no_replace(stage, destination)
        _fsync_directory(destination.parent)
        published = True
        return provenance
    finally:
        if not published:
            _remove_private_stage(stage, destination.parent, stage_prefix)


def parse_args(argv: Iterable[str] | None = None):
    parser = argparse.ArgumentParser(
        description=(
            "Apply deterministic DARE to the exact pinned clean-to-replay64 "
            "Gemma-3 checkpoint delta."
        )
    )
    parser.add_argument("--clean-model", required=True)
    parser.add_argument("--edited-model", required=True)
    parser.add_argument("--tokenizer-model", required=True)
    parser.add_argument("--output-dir", "--output", dest="output_dir", required=True)
    parser.add_argument("--drop-probability", required=True, type=parse_drop_probability)
    parser.add_argument("--seed", required=True, type=parse_uint64_seed)
    parser.add_argument(
        "--chunk-elements", type=_positive_chunk_elements, default=1_048_576
    )
    parser.add_argument("--compute-device", default="cpu")
    args = parser.parse_args(argv)
    if not is_precommitted_request(args.drop_probability, args.seed):
        parser.error(
            "request is outside the frozen grid: use p=0/seed=0, or "
            "p in {0.5,0.9,0.99} with seed in {33450,33451,33452}"
        )
    return args


def main(argv: Iterable[str] | None = None):
    args = parse_args(argv)
    provenance = apply_checkpoint_delta_dare(
        clean_model=args.clean_model,
        edited_model=args.edited_model,
        tokenizer_model=args.tokenizer_model,
        output_dir=args.output_dir,
        drop_probability=args.drop_probability,
        seed=args.seed,
        chunk_elements=args.chunk_elements,
        compute_device=args.compute_device,
    )
    print(
        f"Published deterministic DARE checkpoint at {args.output_dir}\n"
        f"drop_probability={args.drop_probability.decimal}\n"
        f"seed={args.seed}\n"
        f"provenance_payload_sha256={provenance['payload_sha256']}",
        flush=True,
    )


if __name__ == "__main__":
    main()
