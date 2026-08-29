#!/usr/bin/env python3
"""Strict native project I/O and PEFT boundary for Gemma-3 SliceGPT v4.

Only full-width, already-qualified canonical text models are accepted.  This
module does not contain, consume, or issue a reduced-width capability.
"""

from __future__ import annotations

import hashlib
import ctypes
import errno
import importlib.machinery
import importlib.metadata
import importlib.util
import json
import math
import os
import re
import stat
import sys
import types
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

try:
    import torch
    from torch import nn
    from safetensors import safe_open
    from safetensors.torch import save_file
    from transformers import AutoTokenizer
    import peft
except ModuleNotFoundError:  # Source-contract tests run on the laptop.
    torch = None
    nn = None
    safe_open = None
    save_file = None
    AutoTokenizer = None
    peft = None

TEXT = None


VERSION = "slicegpt_gemma3_project_io_v4_v1_unqualified"
PROJECT_VERSION = "slicegpt_gemma3_native_project_v4_v1"
SLICING_VERSION = "slicegpt_gemma3_slicing_metadata_v4_v1"
SOURCE_VERSION = "slicegpt_gemma3_source_metadata_v4_v1"
CALIBRATION_VERSION = "slicegpt_gemma3_calibration_metadata_v4_v1"
ADAPTER_VERSION = "slicegpt_gemma3_peft_adapter_v4_v1"
TEXT_MODEL_SOURCE_SHA256 = "5d701e9fc4d79fb53e8523edb1942e598b2be2c8514019845be5590a45de9a1b"
ADAPTER_CORE_SOURCE_SHA256 = "c4df2be9111fd293454b19f98fba5d46805479d51db02d0611dcfab58f73cfdd"
TEXT_MODEL_PATH = "scripts/slicegpt_gemma3_text_model_v4.py"
ADAPTER_CORE_PATH = "scripts/slicegpt_gemma3_adapter_core_v4.py"
PROJECT_IO_PATH = "scripts/slicegpt_gemma3_project_io_v4.py"
CALIBRATION_SEEDS = (0, 1, 2, 7, 11)
TARGET_SUFFIXES = ("q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj")
TOKENIZER_FILES = (
    "added_tokens.json",
    "chat_template.json",
    "special_tokens_map.json",
    "tokenizer.json",
    "tokenizer_config.json",
)
MAX_SHARD_BYTES = 1_000_000_000
HEX40 = re.compile(r"[0-9a-f]{40}\Z")
HEX64 = re.compile(r"[0-9a-f]{64}\Z")
SHARD_NAME = re.compile(r"model-[0-9]{5}-of-[0-9]{5}\.safetensors\Z")
FIXED_JSON_FILES = frozenset(
    {
        "config.json",
        "model.safetensors.index.json",
        "model_state_manifest.json",
        "slicing_config.json",
        "source_metadata.json",
        "calibration_metadata.json",
        "tokenizer_identity.json",
        "COMPLETE.json",
    }
)


class ProjectIOError(RuntimeError):
    pass


def fail(message: str) -> None:
    raise ProjectIOError(message)


def _runtime() -> None:
    global TEXT
    if any(value is None for value in (torch, nn, safe_open, save_file, AutoTokenizer, peft)):
        fail("project I/O requires the pinned torch/Transformers/PEFT/Safetensors runtime")
    versions = {
        "torch": "2.13.0",
        "transformers": "5.14.1",
        "peft": "0.19.1",
        "safetensors": "0.8.0",
    }
    for package, expected in versions.items():
        if importlib.metadata.version(package) != expected:
            fail(f"project I/O package version changed: {package}")
    if str(torch.__version__) != "2.13.0+cu130":
        fail("project I/O Torch runtime build changed")
    if TEXT is None:
        TEXT = _load_verified_text_model()
    expected_text = Path(__file__).resolve().with_name("slicegpt_gemma3_text_model_v4.py")
    if Path(getattr(TEXT, "__file__", "")).resolve() != expected_text:
        fail("canonical text-model source path changed")
    if sha256_file(expected_text) != TEXT_MODEL_SOURCE_SHA256:
        fail("canonical text-model source hash changed")
    core = expected_text.with_name("slicegpt_gemma3_adapter_core_v4.py")
    if sha256_file(core) != ADAPTER_CORE_SOURCE_SHA256:
        fail("adapter-core source hash changed")


def _direct_module(name: str, path: Path, expected_sha256: str) -> Any:
    if name in sys.modules:
        fail(f"preloaded project dependency is forbidden: {name}")
    path = strict_path(path, f"project dependency {name}")
    if not path.is_file() or sha256_file(path) != expected_sha256:
        fail(f"project dependency source hash changed: {name}")
    spec = importlib.util.spec_from_file_location(name, path)
    if (
        spec is None
        or type(spec.loader) is not importlib.machinery.SourceFileLoader
        or spec.loader.name != name
        or Path(str(spec.origin)).resolve() != path
    ):
        fail(f"project dependency source loader was substituted: {name}")
    # Never call loader.create_module/exec_module: even a same-type class-level
    # monkeypatch would execute before our verified bytes.  Build the plain
    # module namespace directly, then compile only the bytes already hashed.
    module = types.ModuleType(name)
    module.__file__ = str(path)
    module.__loader__ = spec.loader
    module.__package__ = name.rpartition(".")[0]
    module.__spec__ = spec
    sys.modules[name] = module
    try:
        source = path.read_bytes()
        if sha256_bytes(source) != expected_sha256:
            fail(f"buffered project dependency source changed: {name}")
        exec(compile(source, str(path), "exec"), module.__dict__)
    except BaseException:
        sys.modules.pop(name, None)
        raise
    if (
        Path(str(getattr(module, "__file__", ""))).resolve() != path
        or sha256_file(path) != expected_sha256
    ):
        sys.modules.pop(name, None)
        fail(f"executed project dependency source changed: {name}")
    return module


def _load_verified_text_model() -> Any:
    root = Path(__file__).resolve().parent
    core_name = "slicegpt_gemma3_adapter_core_v4"
    text_name = f"_slicegpt_gemma3_text_model_for_project_io_{TEXT_MODEL_SOURCE_SHA256}"
    if "slicegpt_gemma3_text_model_v4" in sys.modules or text_name in sys.modules:
        fail("preloaded canonical text-model module is forbidden")
    core = _direct_module(
        core_name, root / "slicegpt_gemma3_adapter_core_v4.py", ADAPTER_CORE_SOURCE_SHA256
    )
    try:
        text = _direct_module(
            text_name, root / "slicegpt_gemma3_text_model_v4.py", TEXT_MODEL_SOURCE_SHA256
        )
    except BaseException:
        sys.modules.pop(core_name, None)
        raise
    if (
        getattr(text, "CORE", None) is not core
        or getattr(text, "CORE_SOURCE_SHA256", None) != ADAPTER_CORE_SOURCE_SHA256
        or getattr(text, "VERSION", None) != "gemma3_slicegpt_text_model_v4_v1_unqualified"
    ):
        fail("verified text-model dependency identity changed")
    return text


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def tensor_sha256(tensor: Any) -> str:
    _runtime()
    if not isinstance(tensor, torch.Tensor) or tensor.device.type == "meta":
        fail("tensor hashing requires a materialized tensor")
    raw = tensor.detach().contiguous().view(torch.uint8).cpu().numpy().tobytes()
    return sha256_bytes(raw)


def _json_value(value: Any, label: str = "JSON") -> None:
    if value is None or type(value) in {str, bool, int}:
        return
    if type(value) is float:
        if not math.isfinite(value):
            fail(f"{label}: non-finite float")
        return
    if isinstance(value, list):
        for index, child in enumerate(value):
            _json_value(child, f"{label}[{index}]")
        return
    if isinstance(value, dict):
        for key, child in value.items():
            if type(key) is not str:
                fail(f"{label}: non-string key")
            _json_value(child, f"{label}.{key}")
        return
    fail(f"{label}: unsupported type {type(value).__name__}")


def canonical_json_bytes(value: Any) -> bytes:
    _json_value(value)
    return (
        json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True, indent=2, separators=(",", ": "))
        + "\n"
    ).encode("utf-8")


def _exact(value: Any, keys: Sequence[str], label: str) -> dict[str, Any]:
    if type(value) is not dict or set(value) != set(keys):
        fail(f"{label}: exact schema changed")
    return value


def _digest(value: Any, label: str) -> str:
    if type(value) is not str or HEX64.fullmatch(value) is None:
        fail(f"{label}: exact SHA-256 required")
    return value


def _canonical_relative(value: Any, label: str) -> str:
    if type(value) is not str or "\\" in value or value.startswith("/") or re.match(r"^[A-Za-z]:", value):
        fail(f"{label}: canonical relative path required")
    if any(part in {"", ".", ".."} for part in value.split("/")):
        fail(f"{label}: aliased path forbidden")
    return value


def _hash_map(value: Any, label: str, *, nonempty: bool = True) -> dict[str, str]:
    if type(value) is not dict or (nonempty and not value):
        fail(f"{label}: exact hash map required")
    return {_canonical_relative(key, f"{label}.path"): _digest(item, f"{label}.{key}") for key, item in value.items()}


def _is_linklike(path: Path) -> bool:
    try:
        data = path.lstat()
    except (FileNotFoundError, OSError):
        return False
    attributes = getattr(data, "st_file_attributes", 0)
    return stat.S_ISLNK(data.st_mode) or bool(attributes & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400))


def strict_path(path: Path, label: str) -> Path:
    result = Path(os.path.abspath(path))
    for item in (result, *result.parents):
        if _is_linklike(item):
            fail(f"{label}: symlink/junction/reparse component forbidden")
    return result


def _read_canonical_json(path: Path, label: str) -> Any:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        fail(f"{label}: invalid JSON: {error}")
    if path.read_bytes() != canonical_json_bytes(value):
        fail(f"{label}: noncanonical JSON")
    return value


def current_source_sha256() -> str:
    return sha256_file(strict_path(Path(__file__), "project I/O source"))


def validate_source_metadata(value: Any) -> dict[str, Any]:
    record = _exact(
        value,
        ["version", "repo_commit", "committed_sources", "provenance_spec_sha256", "model_qualification_sha256"],
        "source metadata",
    )
    if record["version"] != SOURCE_VERSION or type(record["repo_commit"]) is not str or HEX40.fullmatch(record["repo_commit"]) is None:
        fail("source metadata identity changed")
    sources = _hash_map(record["committed_sources"], "source metadata committed_sources")
    required = {
        TEXT_MODEL_PATH: TEXT_MODEL_SOURCE_SHA256,
        ADAPTER_CORE_PATH: ADAPTER_CORE_SOURCE_SHA256,
        PROJECT_IO_PATH: current_source_sha256(),
    }
    if any(sources.get(path) != digest for path, digest in required.items()):
        fail("source metadata does not bind exact model/core/project-loader sources")
    _digest(record["provenance_spec_sha256"], "source metadata provenance")
    _digest(record["model_qualification_sha256"], "source metadata model qualification")
    return record


def validate_calibration_metadata(value: Any) -> dict[str, Any]:
    record = _exact(
        value,
        ["version", "seed", "metadata_fingerprint", "tensors_sha256", "complete_sha256", "source_identity_fingerprint"],
        "calibration metadata",
    )
    if record["version"] != CALIBRATION_VERSION or type(record["seed"]) is not int or record["seed"] not in CALIBRATION_SEEDS:
        fail("calibration metadata identity changed")
    for key in ("metadata_fingerprint", "tensors_sha256", "complete_sha256", "source_identity_fingerprint"):
        _digest(record[key], f"calibration metadata {key}")
    return record


def validate_slicing_config(value: Any) -> dict[str, Any]:
    _runtime()
    record = _exact(
        value,
        ["version", "mechanism", "fraction", "residual_dimensions", "calibration_seed", "calibration_tensors_sha256", "nonzero_slice_authorized"],
        "slicing config",
    )
    if (
        record["version"] != SLICING_VERSION
        or record["mechanism"] != "slicegpt"
        or record["fraction"] != "0"
        or record["nonzero_slice_authorized"] is not False
        or type(record["calibration_seed"]) is not int
        or record["calibration_seed"] not in CALIBRATION_SEEDS
    ):
        fail("only full-width unqualified SliceGPT metadata is accepted")
    dimensions = TEXT._canonical_dimensions(record["residual_dimensions"])
    if dimensions != tuple((TEXT.HIDDEN_SIZE,) * 3 for _ in range(TEXT.NUM_LAYERS)):
        fail("reduced residual dimensions are locked")
    _digest(record["calibration_tensors_sha256"], "slicing calibration tensor")
    return record


def canonical_target_names() -> tuple[str, ...]:
    return tuple(
        sorted(
            f"model.layers.{index}.{branch}.{name}"
            for index in range(34)
            for branch, names in (
                ("self_attn", TARGET_SUFFIXES[:4]),
                ("mlp", TARGET_SUFFIXES[4:]),
            )
            for name in names
        )
    )


def exact_peft_targets(model: Any) -> tuple[str, ...]:
    _runtime()
    names = TEXT.exact_projection_module_names(model)
    if names != canonical_target_names() or len(names) != 238:
        fail("exact 34x7 PEFT target surface changed")
    return names


def plan_shards(state: Mapping[str, Any], max_shard_bytes: int = MAX_SHARD_BYTES) -> tuple[tuple[str, ...], ...]:
    _runtime()
    if type(max_shard_bytes) is not int or max_shard_bytes <= 0:
        fail("max_shard_bytes must be a positive exact integer")
    if set(state) != TEXT.expected_state_keys():
        fail("shard planner requires the exact 444-key canonical state")
    shards: list[list[str]] = []
    current: list[str] = []
    current_size = 0
    for name in sorted(state):
        tensor = state[name]
        if not isinstance(tensor, torch.Tensor) or tensor.dtype is not torch.bfloat16:
            fail(f"shard planner state changed: {name}")
        size = tensor.numel() * tensor.element_size()
        if current and current_size + size > max_shard_bytes:
            shards.append(current)
            current, current_size = [], 0
        current.append(name)
        current_size += size
    if current:
        shards.append(current)
    if len(shards) < 2:
        fail("canonical project must use native sharded Safetensors")
    return tuple(tuple(shard) for shard in shards)


def _state_record(name: str, tensor: Any, shard: str) -> dict[str, Any]:
    return {
        "shape": [int(value) for value in tensor.shape],
        "dtype": "BF16",
        "sha256": tensor_sha256(tensor),
        "shard": shard,
    }


def _manifest_bytes(hashes: Mapping[str, str]) -> bytes:
    return "".join(f"{hashes[name]}  {name}\n" for name in sorted(hashes)).encode("utf-8")


def _parse_manifest(path: Path) -> dict[str, str]:
    raw = path.read_bytes()
    if b"\r" in raw or not raw.endswith(b"\n"):
        fail("project manifest is not canonical LF text")
    result: dict[str, str] = {}
    previous = ""
    for line in raw.decode("utf-8", errors="strict").splitlines():
        match = re.fullmatch(r"([0-9a-f]{64})  (.+)", line)
        if match is None:
            fail("project manifest line changed")
        digest, name = match.groups()
        _canonical_relative(name, "project manifest member")
        if name in result or (previous and name <= previous):
            fail("project manifest order/membership changed")
        result[name] = digest
        previous = name
    if not result:
        fail("project manifest is empty")
    return result


def _write_new(path: Path, data: bytes) -> None:
    with path.open("xb") as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())


def _fsync_directory(path: Path) -> None:
    try:
        descriptor = os.open(path, os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
    except OSError:
        # Windows does not expose directory fsync; every member was fsynced.
        pass


def _publish_directory_no_replace(temporary: Path, output: Path) -> None:
    """Atomically publish a directory while refusing every destination race."""

    if os.name == "nt":
        try:
            os.rename(temporary, output)
        except FileExistsError:
            fail("output appeared concurrently; replacement is forbidden")
        return
    if sys.platform.startswith("linux"):
        library = ctypes.CDLL(None, use_errno=True)
        renameat2 = getattr(library, "renameat2", None)
        if renameat2 is None:
            fail("atomic no-replace directory publication is unavailable")
        renameat2.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
        renameat2.restype = ctypes.c_int
        result = renameat2(-100, os.fsencode(temporary), -100, os.fsencode(output), 1)
        if result != 0:
            error = ctypes.get_errno()
            if error == errno.EEXIST:
                fail("output appeared concurrently; replacement is forbidden")
            fail(f"atomic no-replace directory publication failed: errno {error}")
        return
    fail("atomic no-replace directory publication is unsupported on this platform")


@dataclass(frozen=True)
class LoadedSliceGPTProjectV4:
    root: Path
    model: Any
    tokenizer: Any
    slicing: dict[str, Any]
    source: dict[str, Any]
    calibration: dict[str, Any]
    manifest_sha256: str


def _fingerprint(value: Any) -> str:
    _json_value(value)
    return sha256_bytes(json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":")).encode())


def _tokenizer_identity(root: Path) -> tuple[Any, dict[str, Any]]:
    _runtime()
    root = strict_path(root, "tokenizer source")
    if not root.is_dir():
        fail("tokenizer source must be a directory")
    files: dict[str, str] = {}
    for name in TOKENIZER_FILES:
        path = strict_path(root / name, f"tokenizer source {name}")
        if not path.is_file():
            fail(f"tokenizer source is missing {name}")
        files[name] = sha256_file(path)
    tokenizer = AutoTokenizer.from_pretrained(root, local_files_only=True)
    identity = {
        "class": type(tokenizer).__name__,
        "bos_token_id": tokenizer.bos_token_id,
        "eos_token_id": tokenizer.eos_token_id,
        "pad_token_id": tokenizer.pad_token_id,
        "unk_token_id": tokenizer.unk_token_id,
        "files_sha256": files,
    }
    if identity != {
        "class": "GemmaTokenizer",
        "bos_token_id": 2,
        "eos_token_id": 1,
        "pad_token_id": 0,
        "unk_token_id": 3,
        "files_sha256": files,
    }:
        fail("tokenizer identity changed")
    return tokenizer, identity


def _write_shards(
    state: Mapping[str, Any],
    shards: Sequence[Sequence[str]],
    root: Path,
) -> tuple[dict[str, str], dict[str, dict[str, Any]], int]:
    _runtime()
    weight_map: dict[str, str] = {}
    records: dict[str, dict[str, Any]] = {}
    total_size = 0
    count = len(shards)
    for index, names in enumerate(shards, 1):
        shard_name = f"model-{index:05d}-of-{count:05d}.safetensors"
        tensors: dict[str, Any] = {}
        for name in names:
            source = state[name]
            if source.device.type == "meta" or source.dtype is not torch.bfloat16:
                fail(f"cannot serialize unloaded/non-BF16 state: {name}")
            tensor = source.detach().contiguous().cpu()
            if not bool(torch.isfinite(tensor).all().item()):
                fail(f"cannot serialize non-finite state: {name}")
            tensors[name] = tensor
            weight_map[name] = shard_name
            records[name] = _state_record(name, tensor, shard_name)
            total_size += tensor.numel() * tensor.element_size()
        path = root / shard_name
        save_file(
            tensors,
            str(path),
            metadata={"format": "pt", "project_version": PROJECT_VERSION, "shard": shard_name},
        )
        with path.open("rb") as handle:
            os.fsync(handle.fileno())
        del tensors
    return weight_map, records, total_size


def save_project(
    model: Any,
    *,
    tokenizer_root: Path,
    slicing: Mapping[str, Any],
    source: Mapping[str, Any],
    calibration: Mapping[str, Any],
    output: Path,
    max_shard_bytes: int = MAX_SHARD_BYTES,
) -> dict[str, Any]:
    """Atomically save one full-width model in the native project format."""

    _runtime()
    TEXT.validate_text_model(model)
    if tuple(exact_peft_targets(model)) != tuple(sorted(exact_peft_targets(model))):
        fail("canonical target ordering changed")
    slicing_record = validate_slicing_config(dict(slicing))
    source_record = validate_source_metadata(dict(source))
    calibration_record = validate_calibration_metadata(dict(calibration))
    if (
        slicing_record["calibration_seed"] != calibration_record["seed"]
        or slicing_record["calibration_tensors_sha256"] != calibration_record["tensors_sha256"]
    ):
        fail("slicing/calibration identity mismatch")
    _, tokenizer_identity = _tokenizer_identity(tokenizer_root)
    config = model.config.to_dict()
    if type(config) is not dict or config.get("model_type") != TEXT.MODEL_TYPE:
        fail("canonical custom config serialization changed")
    state = model.state_dict()
    shards = plan_shards(state, max_shard_bytes)

    output = strict_path(output, "project output")
    if output.exists():
        fail("project output already exists; replacement is forbidden")
    output.parent.mkdir(parents=True, exist_ok=True)
    strict_path(output.parent, "project output parent")
    temporary = strict_path(output.with_name(output.name + ".tmp"), "partial project output")
    if temporary.exists():
        fail("partial project output already exists")
    temporary.mkdir(parents=False, exist_ok=False)
    try:
        for name in TOKENIZER_FILES:
            _write_new(temporary / name, (strict_path(tokenizer_root, "tokenizer source") / name).read_bytes())
        _write_new(temporary / "config.json", canonical_json_bytes(config))
        _write_new(temporary / "slicing_config.json", canonical_json_bytes(slicing_record))
        _write_new(temporary / "source_metadata.json", canonical_json_bytes(source_record))
        _write_new(temporary / "calibration_metadata.json", canonical_json_bytes(calibration_record))
        _write_new(temporary / "tokenizer_identity.json", canonical_json_bytes(tokenizer_identity))
        weight_map, tensor_records, total_size = _write_shards(state, shards, temporary)
        index = {"metadata": {"total_size": total_size}, "weight_map": weight_map}
        state_manifest = {
            "version": PROJECT_VERSION,
            "total_size": total_size,
            "tensors": tensor_records,
            "state_fingerprint": _fingerprint(tensor_records),
        }
        _write_new(temporary / "model.safetensors.index.json", canonical_json_bytes(index))
        _write_new(temporary / "model_state_manifest.json", canonical_json_bytes(state_manifest))
        preliminary = {
            path.name: sha256_file(path)
            for path in temporary.iterdir()
            if path.is_file()
        }
        complete = {
            "version": PROJECT_VERSION,
            "status": "COMPLETE_NATIVE_SHARDED_SAFETENSORS",
            "manifest_members": sorted((*preliminary, "COMPLETE.json")),
            "state_fingerprint": state_manifest["state_fingerprint"],
            "config_sha256": preliminary["config.json"],
            "slicing_sha256": preliminary["slicing_config.json"],
            "source_sha256": preliminary["source_metadata.json"],
            "calibration_sha256": preliminary["calibration_metadata.json"],
        }
        _write_new(temporary / "COMPLETE.json", canonical_json_bytes(complete))
        preliminary["COMPLETE.json"] = sha256_file(temporary / "COMPLETE.json")
        _write_new(temporary / "MANIFEST.sha256", _manifest_bytes(preliminary))
        if output.exists():
            fail("project output appeared concurrently")
        _publish_directory_no_replace(temporary, output)
        _fsync_directory(output.parent)
    except BaseException:
        # Partial evidence is retained and never repaired or blessed.
        raise
    return validate_project_archive(output)


def _archive_members(root: Path) -> set[str]:
    if not root.is_dir() or _is_linklike(root):
        fail("project archive root is not a real directory")
    result: set[str] = set()
    for path in root.iterdir():
        if _is_linklike(path) or not path.is_file():
            fail("project archive must be one flat regular-file set")
        result.add(path.name)
    return result


def validate_project_archive(root: Path) -> dict[str, Any]:
    """Validate every byte and tensor without constructing an executable model."""

    _runtime()
    root = strict_path(root, "project archive")
    members = _archive_members(root)
    if "MANIFEST.sha256" not in members:
        fail("project archive manifest is missing")
    manifest = _parse_manifest(root / "MANIFEST.sha256")
    if set(manifest) != members - {"MANIFEST.sha256"}:
        fail("project archive/manifest membership mismatch")
    for name, expected in manifest.items():
        if sha256_file(root / name) != expected:
            fail(f"project archive member hash mismatch: {name}")

    config = _read_canonical_json(root / "config.json", "project config")
    slicing = validate_slicing_config(_read_canonical_json(root / "slicing_config.json", "slicing config"))
    source = validate_source_metadata(_read_canonical_json(root / "source_metadata.json", "source metadata"))
    calibration = validate_calibration_metadata(
        _read_canonical_json(root / "calibration_metadata.json", "calibration metadata")
    )
    if slicing["calibration_seed"] != calibration["seed"] or slicing["calibration_tensors_sha256"] != calibration["tensors_sha256"]:
        fail("sealed slicing/calibration identity mismatch")
    tokenizer_identity = _exact(
        _read_canonical_json(root / "tokenizer_identity.json", "tokenizer identity"),
        ["class", "bos_token_id", "eos_token_id", "pad_token_id", "unk_token_id", "files_sha256"],
        "tokenizer identity",
    )
    tokenizer_hashes = _hash_map(tokenizer_identity["files_sha256"], "tokenizer files")
    if (
        set(tokenizer_hashes) != set(TOKENIZER_FILES)
        or any(type(tokenizer_identity[key]) is not int for key in ("bos_token_id", "eos_token_id", "pad_token_id", "unk_token_id"))
        or tokenizer_identity | {"files_sha256": tokenizer_hashes} != {
        "class": "GemmaTokenizer", "bos_token_id": 2, "eos_token_id": 1,
        "pad_token_id": 0, "unk_token_id": 3, "files_sha256": tokenizer_hashes,
        }
    ):
        fail("sealed tokenizer identity changed")
    for name, expected in tokenizer_hashes.items():
        if manifest.get(name) != expected:
            fail(f"sealed tokenizer file changed: {name}")

    index = _exact(
        _read_canonical_json(root / "model.safetensors.index.json", "model index"),
        ["metadata", "weight_map"],
        "model index",
    )
    metadata = _exact(index["metadata"], ["total_size"], "model index metadata")
    if type(metadata["total_size"]) is not int or metadata["total_size"] <= 0:
        fail("model index total size changed")
    weight_map = index["weight_map"]
    if type(weight_map) is not dict or set(weight_map) != TEXT.expected_state_keys():
        fail("model index exact 444-key surface changed")
    shards = set(weight_map.values())
    if len(shards) < 2 or any(type(name) is not str or SHARD_NAME.fullmatch(name) is None for name in shards):
        fail("model index is not native deterministic sharded Safetensors")
    if not shards.issubset(manifest):
        fail("model index references an unsealed shard")
    state_manifest = _exact(
        _read_canonical_json(root / "model_state_manifest.json", "model state manifest"),
        ["version", "total_size", "tensors", "state_fingerprint"],
        "model state manifest",
    )
    if state_manifest["version"] != PROJECT_VERSION or state_manifest["total_size"] != metadata["total_size"]:
        fail("model state manifest identity changed")
    tensors = state_manifest["tensors"]
    if type(tensors) is not dict or set(tensors) != TEXT.expected_state_keys():
        fail("model state manifest exact 444-key surface changed")
    if state_manifest["state_fingerprint"] != _fingerprint(tensors):
        fail("model state manifest fingerprint changed")
    total_size = 0
    for name, record_value in tensors.items():
        record = _exact(record_value, ["shape", "dtype", "sha256", "shard"], f"tensor {name}")
        if (
            type(record["shape"]) is not list
            or not record["shape"]
            or any(type(value) is not int or value <= 0 for value in record["shape"])
            or record["dtype"] != "BF16"
            or record["shard"] != weight_map[name]
        ):
            fail(f"tensor schema changed: {name}")
        _digest(record["sha256"], f"tensor {name}")
        total_size += math.prod(record["shape"]) * 2
    if total_size != metadata["total_size"]:
        fail("model state byte size changed")
    custom_config = TEXT.Gemma3SliceGPTTextConfigV4(**config)
    if custom_config.to_dict() != config:
        fail("sealed custom config roundtrip changed")
    with torch.device("meta"):
        skeleton_model = TEXT.Gemma3SliceGPTTextForCausalLMV4(custom_config)
    TEXT.validate_compressed_skeleton(skeleton_model)
    skeleton_state = skeleton_model.state_dict()
    if any(
        list(skeleton_state[name].shape) != tensors[name]["shape"]
        or skeleton_state[name].dtype is not torch.bfloat16
        for name in skeleton_state
    ):
        fail("sealed tensor shapes differ from config-driven canonical skeleton")
    for shard_name in sorted(shards):
        expected_keys = {name for name, declared in weight_map.items() if declared == shard_name}
        with safe_open(root / shard_name, framework="pt", device="cpu") as handle:
            if handle.metadata() != {"format": "pt", "project_version": PROJECT_VERSION, "shard": shard_name}:
                fail(f"Safetensors metadata changed: {shard_name}")
            if set(handle.keys()) != expected_keys:
                fail(f"Safetensors key membership changed: {shard_name}")
            for name in sorted(expected_keys):
                tensor = handle.get_tensor(name)
                record = tensors[name]
                if tensor.dtype is not torch.bfloat16 or list(tensor.shape) != record["shape"] or tensor_sha256(tensor) != record["sha256"]:
                    fail(f"Safetensors tensor identity changed: {name}")
    complete = _exact(
        _read_canonical_json(root / "COMPLETE.json", "project completion"),
        ["version", "status", "manifest_members", "state_fingerprint", "config_sha256", "slicing_sha256", "source_sha256", "calibration_sha256"],
        "project completion",
    )
    expected_complete = {
        "version": PROJECT_VERSION,
        "status": "COMPLETE_NATIVE_SHARDED_SAFETENSORS",
        "manifest_members": sorted(manifest),
        "state_fingerprint": state_manifest["state_fingerprint"],
        "config_sha256": manifest["config.json"],
        "slicing_sha256": manifest["slicing_config.json"],
        "source_sha256": manifest["source_metadata.json"],
        "calibration_sha256": manifest["calibration_metadata.json"],
    }
    if complete != expected_complete:
        fail("project completion marker changed")
    expected_members = FIXED_JSON_FILES | set(TOKENIZER_FILES) | shards | {"MANIFEST.sha256"}
    if members != expected_members:
        fail("project exact file surface changed")
    return {
        "root": root,
        "manifest": manifest,
        "manifest_sha256": sha256_file(root / "MANIFEST.sha256"),
        "config": config,
        "slicing": slicing,
        "source": source,
        "calibration": calibration,
        "tokenizer_identity": tokenizer_identity,
        "weight_map": weight_map,
        "tensors": tensors,
    }


def _owner(model: Any, name: str) -> tuple[Any, str]:
    parts = name.split(".")
    current = model
    for part in parts[:-1]:
        if part.isdecimal():
            current = current[int(part)]
        else:
            current = getattr(current, part)
    return current, parts[-1]


def _assign_state_tensor(model: Any, name: str, tensor: Any, device: Any) -> None:
    owner, leaf = _owner(model, name)
    value = tensor.to(device=device, dtype=torch.bfloat16)
    if name in TEXT.expected_parameter_keys():
        existing = owner._parameters.get(leaf)
        if type(existing) is not nn.Parameter or existing.device.type != "meta":
            fail(f"parameter skeleton assignment surface changed: {name}")
        owner._parameters[leaf] = nn.Parameter(value, requires_grad=existing.requires_grad)
    elif name in TEXT.expected_buffer_keys():
        existing = owner._buffers.get(leaf)
        if type(existing) is not torch.Tensor or existing.device.type != "meta":
            fail(f"buffer skeleton assignment surface changed: {name}")
        owner._buffers[leaf] = value
    else:
        fail(f"assignment attempted outside exact state surface: {name}")


def _materialize_execution_buffers(model: Any, device: Any) -> None:
    expected = TEXT.expected_nonpersistent_buffer_keys()
    current = dict(model.named_buffers())
    if not expected.issubset(current) or any(current[name].device.type != "meta" for name in expected):
        fail("nonpersistent execution-buffer skeleton changed")
    model.model.embed_tokens._buffers["embed_scale"] = torch.tensor(
        math.sqrt(TEXT.HIDDEN_SIZE), dtype=torch.float32, device=device
    )
    with torch.device(device):
        model.model.rotary_emb = type(model.model.rotary_emb)(model.config)
    after = dict(model.named_buffers())
    if set(after) != TEXT.expected_buffer_keys() | expected or any(after[name].device.type == "meta" for name in expected):
        fail("nonpersistent execution buffers were not deterministically reconstructed")


def load_project(root: Path, *, device: str | Any = "cpu") -> LoadedSliceGPTProjectV4:
    """The sole supported executable-model loading path for v4 projects."""

    _runtime()
    archive = validate_project_archive(root)
    target_device = torch.device(device)
    if target_device.type == "meta":
        fail("project loader cannot return an executable meta model")
    config = TEXT.Gemma3SliceGPTTextConfigV4(**archive["config"])
    if config.to_dict() != archive["config"]:
        fail("custom config roundtrip changed")
    with torch.device("meta"):
        model = TEXT.Gemma3SliceGPTTextForCausalLMV4(config)
    TEXT.validate_compressed_skeleton(model)
    skeleton = model.state_dict()
    for name, record in archive["tensors"].items():
        if list(skeleton[name].shape) != record["shape"] or skeleton[name].dtype is not torch.bfloat16:
            fail(f"config-driven skeleton differs from state manifest: {name}")

    loaded: set[str] = set()
    try:
        for shard_name in sorted(set(archive["weight_map"].values())):
            with safe_open(archive["root"] / shard_name, framework="pt", device="cpu") as handle:
                for name in sorted(handle.keys()):
                    if name in loaded:
                        fail(f"duplicate tensor load: {name}")
                    tensor = handle.get_tensor(name)
                    record = archive["tensors"][name]
                    if tensor_sha256(tensor) != record["sha256"]:
                        fail(f"pre-assignment tensor identity changed: {name}")
                    _assign_state_tensor(model, name, tensor, target_device)
                    loaded.add(name)
        if loaded != TEXT.expected_state_keys():
            fail("project load did not assign the exact complete state")
        _materialize_execution_buffers(model, target_device)
        final_state = model.state_dict()
        for name, record in archive["tensors"].items():
            tensor = final_state[name]
            if (
                tensor.device != target_device
                or list(tensor.shape) != record["shape"]
                or tensor.dtype is not torch.bfloat16
                or tensor_sha256(tensor) != record["sha256"]
            ):
                fail(f"post-assignment bitwise state check failed: {name}")
        if model.lm_head.weight.untyped_storage().data_ptr() == model.model.embed_tokens.weight.untyped_storage().data_ptr():
            fail("project loader silently retied embeddings and LM head")
        model._slicegpt_weights_loaded = True
        try:
            TEXT.validate_text_model(model)
            model.tie_weights()
        except BaseException:
            model._slicegpt_weights_loaded = False
            raise
    except BaseException:
        model._slicegpt_weights_loaded = False
        raise

    tokenizer = AutoTokenizer.from_pretrained(archive["root"], local_files_only=True)
    identity = archive["tokenizer_identity"]
    if (
        type(tokenizer).__name__ != identity["class"]
        or tokenizer.bos_token_id != identity["bos_token_id"]
        or tokenizer.eos_token_id != identity["eos_token_id"]
        or tokenizer.pad_token_id != identity["pad_token_id"]
        or tokenizer.unk_token_id != identity["unk_token_id"]
    ):
        model._slicegpt_weights_loaded = False
        fail("loaded tokenizer identity changed")
    return LoadedSliceGPTProjectV4(
        root=archive["root"],
        model=model,
        tokenizer=tokenizer,
        slicing=archive["slicing"],
        source=archive["source"],
        calibration=archive["calibration"],
        manifest_sha256=archive["manifest_sha256"],
    )


def _attach_exact_lora(
    model: Any,
    *,
    rank: int,
    alpha: int,
    adapter_name: str,
    allow_unloaded_meta: bool,
) -> Any:
    _runtime()
    if type(rank) is not int or rank <= 0 or type(alpha) is not int or alpha <= 0:
        fail("LoRA rank/alpha must be positive exact integers")
    if type(adapter_name) is not str or re.fullmatch(r"[A-Za-z0-9_-]+", adapter_name) is None:
        fail("adapter name is noncanonical")
    if allow_unloaded_meta:
        TEXT.validate_compressed_skeleton(model)
    else:
        TEXT.validate_text_model(model)
    targets = exact_peft_targets(model)
    configuration = peft.LoraConfig(
        task_type=peft.TaskType.CAUSAL_LM,
        r=rank,
        lora_alpha=alpha,
        lora_dropout=0.0,
        bias="none",
        target_modules=list(targets),
        init_lora_weights=True,
        use_rslora=False,
        use_dora=False,
    )
    wrapped = peft.get_peft_model(model, configuration, adapter_name=adapter_name)
    prefix = "base_model.model."
    actual_modules = {
        name[len(prefix):]
        for name, module in wrapped.named_modules()
        if name.startswith(prefix)
        and type(module).__module__.startswith("peft.tuners.lora")
        and hasattr(module, "lora_A")
        and hasattr(module, "lora_B")
    }
    if actual_modules != set(targets):
        fail("PEFT attached outside the exact 238 qualified projection paths")
    trainable = {name for name, parameter in wrapped.named_parameters() if parameter.requires_grad}
    expected_trainable = {
        f"base_model.model.{target}.lora_{side}.{adapter_name}.weight"
        for target in targets
        for side in ("A", "B")
    }
    if trainable != expected_trainable or len(trainable) != 476:
        fail("PEFT trainable parameter surface changed")
    if wrapped.base_model.model.lm_head.weight is wrapped.base_model.model.model.embed_tokens.weight:
        fail("PEFT silently retied embeddings and LM head")
    return wrapped


def attach_project_lora(
    project: LoadedSliceGPTProjectV4,
    *,
    rank: int = 2,
    alpha: int = 2,
    adapter_name: str = "default",
) -> Any:
    if type(project) is not LoadedSliceGPTProjectV4:
        fail("LoRA attachment requires the strict project-loader result")
    wrapped = _attach_exact_lora(
        project.model,
        rank=rank,
        alpha=alpha,
        adapter_name=adapter_name,
        allow_unloaded_meta=False,
    )
    for parameter in wrapped.parameters():
        if parameter.requires_grad:
            parameter.data = parameter.data.float()
    if any(parameter.dtype is not torch.float32 for parameter in wrapped.parameters() if parameter.requires_grad):
        fail("LoRA trainable parameters require FP32 master storage")
    return wrapped


def _saved_adapter_keys(targets: Sequence[str]) -> frozenset[str]:
    return frozenset(
        f"base_model.model.{target}.lora_{side}.weight"
        for target in targets
        for side in ("A", "B")
    )


def _expected_adapter_shape(saved_name: str, rank: int) -> list[int]:
    match = re.fullmatch(
        r"base_model\.model\.model\.layers\.([0-9]+)\.(self_attn|mlp)\."
        r"(q_proj|k_proj|v_proj|o_proj|gate_proj|up_proj|down_proj)\.lora_([AB])\.weight",
        saved_name,
    )
    if match is None or int(match.group(1)) >= 34:
        fail(f"adapter tensor path changed: {saved_name}")
    branch, projection, side = match.group(2), match.group(3), match.group(4)
    if (branch == "self_attn") != (projection in TARGET_SUFFIXES[:4]):
        fail(f"adapter tensor branch changed: {saved_name}")
    projection_shape = {
        "q_proj": (2048, 2560),
        "k_proj": (1024, 2560),
        "v_proj": (1024, 2560),
        "o_proj": (2560, 2048),
        "gate_proj": (10240, 2560),
        "up_proj": (10240, 2560),
        "down_proj": (2560, 10240),
    }[projection]
    return [rank, projection_shape[1]] if side == "A" else [projection_shape[0], rank]


def _adapter_configuration(model: Any, adapter_name: str, project_manifest_sha256: str) -> dict[str, Any]:
    _digest(project_manifest_sha256, "base project manifest")
    configuration = model.peft_config.get(adapter_name)
    if configuration is None:
        fail("named PEFT adapter is missing")
    targets = exact_peft_targets(model.base_model.model)
    if (
        configuration.task_type != peft.TaskType.CAUSAL_LM
        or type(configuration.r) is not int
        or type(configuration.lora_alpha) is not int
        or float(configuration.lora_dropout) != 0.0
        or configuration.bias != "none"
        # PEFT 0.19.1 deterministically minimizes the supplied 238 fully
        # qualified paths to these seven suffixes after injection.  The
        # attached module set was already checked above against all 238 exact
        # paths; project serialization records those full paths, never this
        # lossy internal optimization.
        or set(configuration.target_modules or ()) != set(TARGET_SUFFIXES)
        or bool(configuration.use_rslora)
        or bool(configuration.use_dora)
    ):
        fail("PEFT adapter configuration identity changed")
    return {
        "version": ADAPTER_VERSION,
        "project_manifest_sha256": project_manifest_sha256,
        "adapter_name": adapter_name,
        "rank": configuration.r,
        "alpha": configuration.lora_alpha,
        "target_modules": list(targets),
        "peft_version": importlib.metadata.version("peft"),
    }


def _save_adapter_bound(
    model: Any,
    *,
    project_manifest_sha256: str,
    output: Path,
    adapter_name: str = "default",
) -> dict[str, Any]:
    """Save only the strict 238-target adapter in an immutable native archive."""

    _runtime()
    configuration = _adapter_configuration(model, adapter_name, project_manifest_sha256)
    targets = tuple(configuration["target_modules"])
    state = peft.get_peft_model_state_dict(model, adapter_name=adapter_name)
    if set(state) != _saved_adapter_keys(targets) or len(state) != 476:
        fail("saved adapter key surface changed")
    tensors: dict[str, Any] = {}
    records: dict[str, dict[str, Any]] = {}
    for name in sorted(state):
        tensor = state[name].detach().contiguous().cpu()
        if tensor.dtype is not torch.float32 or not bool(torch.isfinite(tensor).all().item()):
            fail(f"adapter tensor is not finite FP32: {name}")
        tensors[name] = tensor
        records[name] = {
            "shape": [int(value) for value in tensor.shape],
            "dtype": "F32",
            "sha256": tensor_sha256(tensor),
        }
    state_fingerprint = _fingerprint(records)
    configuration = {**configuration, "state_fingerprint": state_fingerprint}
    output = strict_path(output, "adapter output")
    if output.exists():
        fail("adapter output already exists; replacement is forbidden")
    output.parent.mkdir(parents=True, exist_ok=True)
    strict_path(output.parent, "adapter output parent")
    temporary = strict_path(output.with_name(output.name + ".tmp"), "partial adapter output")
    if temporary.exists():
        fail("partial adapter output already exists")
    temporary.mkdir(parents=False, exist_ok=False)
    try:
        save_file(
            tensors,
            str(temporary / "adapter_model.safetensors"),
            metadata={"format": "pt", "adapter_version": ADAPTER_VERSION, "adapter_name": adapter_name},
        )
        with (temporary / "adapter_model.safetensors").open("rb") as handle:
            os.fsync(handle.fileno())
        _write_new(temporary / "adapter_config.json", canonical_json_bytes(configuration))
        state_manifest = {
            "version": ADAPTER_VERSION,
            "tensors": records,
            "state_fingerprint": state_fingerprint,
        }
        _write_new(temporary / "adapter_state_manifest.json", canonical_json_bytes(state_manifest))
        preliminary = {path.name: sha256_file(path) for path in temporary.iterdir()}
        complete = {
            "version": ADAPTER_VERSION,
            "status": "COMPLETE_STRICT_PEFT_ADAPTER",
            "manifest_members": sorted((*preliminary, "COMPLETE.json")),
            "state_fingerprint": state_fingerprint,
            "project_manifest_sha256": project_manifest_sha256,
        }
        _write_new(temporary / "COMPLETE.json", canonical_json_bytes(complete))
        preliminary["COMPLETE.json"] = sha256_file(temporary / "COMPLETE.json")
        _write_new(temporary / "MANIFEST.sha256", _manifest_bytes(preliminary))
        if output.exists():
            fail("adapter output appeared concurrently")
        _publish_directory_no_replace(temporary, output)
        _fsync_directory(output.parent)
    except BaseException:
        raise
    return validate_adapter_archive(output, expected_project_manifest_sha256=project_manifest_sha256)


def save_adapter(
    project: LoadedSliceGPTProjectV4,
    model: Any,
    *,
    output: Path,
    adapter_name: str = "default",
) -> dict[str, Any]:
    if type(project) is not LoadedSliceGPTProjectV4:
        fail("adapter saving requires the strict project-loader result")
    if getattr(getattr(model, "base_model", None), "model", None) is not project.model:
        fail("adapter/base object differs from the strict loaded project")
    return _save_adapter_bound(
        model,
        project_manifest_sha256=project.manifest_sha256,
        output=output,
        adapter_name=adapter_name,
    )


def validate_adapter_archive(
    root: Path,
    *,
    expected_project_manifest_sha256: str | None = None,
) -> dict[str, Any]:
    _runtime()
    root = strict_path(root, "adapter archive")
    members = _archive_members(root)
    expected_members = {
        "adapter_model.safetensors", "adapter_config.json", "adapter_state_manifest.json",
        "COMPLETE.json", "MANIFEST.sha256",
    }
    if members != expected_members:
        fail("adapter exact file surface changed")
    manifest = _parse_manifest(root / "MANIFEST.sha256")
    if set(manifest) != expected_members - {"MANIFEST.sha256"}:
        fail("adapter manifest membership changed")
    for name, expected in manifest.items():
        if sha256_file(root / name) != expected:
            fail(f"adapter member hash mismatch: {name}")
    config = _exact(
        _read_canonical_json(root / "adapter_config.json", "adapter config"),
        ["version", "project_manifest_sha256", "adapter_name", "rank", "alpha", "target_modules", "peft_version", "state_fingerprint"],
        "adapter config",
    )
    if (
        config["version"] != ADAPTER_VERSION
        or config["peft_version"] != "0.19.1"
        or type(config["adapter_name"]) is not str
        or re.fullmatch(r"[A-Za-z0-9_-]+", config["adapter_name"]) is None
        or type(config["rank"]) is not int
        or config["rank"] <= 0
        or type(config["alpha"]) is not int
        or config["alpha"] <= 0
        or type(config["target_modules"]) is not list
        or tuple(config["target_modules"]) != tuple(sorted(config["target_modules"]))
        or tuple(config["target_modules"]) != canonical_target_names()
    ):
        fail("adapter configuration exact identity changed")
    _digest(config["project_manifest_sha256"], "adapter project manifest")
    _digest(config["state_fingerprint"], "adapter state fingerprint")
    if expected_project_manifest_sha256 is not None and config["project_manifest_sha256"] != expected_project_manifest_sha256:
        fail("adapter belongs to a different base project")
    state_manifest = _exact(
        _read_canonical_json(root / "adapter_state_manifest.json", "adapter state manifest"),
        ["version", "tensors", "state_fingerprint"],
        "adapter state manifest",
    )
    tensors = state_manifest["tensors"]
    expected_keys = _saved_adapter_keys(config["target_modules"])
    if state_manifest["version"] != ADAPTER_VERSION or type(tensors) is not dict or set(tensors) != expected_keys:
        fail("adapter state exact 476-key surface changed")
    if state_manifest["state_fingerprint"] != config["state_fingerprint"] or _fingerprint(tensors) != config["state_fingerprint"]:
        fail("adapter state fingerprint changed")
    with safe_open(root / "adapter_model.safetensors", framework="pt", device="cpu") as handle:
        if handle.metadata() != {"format": "pt", "adapter_version": ADAPTER_VERSION, "adapter_name": config["adapter_name"]}:
            fail("adapter Safetensors metadata changed")
        if set(handle.keys()) != expected_keys:
            fail("adapter Safetensors key surface changed")
        for name in sorted(expected_keys):
            record = _exact(tensors[name], ["shape", "dtype", "sha256"], f"adapter tensor {name}")
            tensor = handle.get_tensor(name)
            if (
                record["dtype"] != "F32"
                or type(record["shape"]) is not list
                or record["shape"] != _expected_adapter_shape(name, config["rank"])
                or tensor.dtype is not torch.float32
                or list(tensor.shape) != record["shape"]
                or tensor_sha256(tensor) != _digest(record["sha256"], f"adapter tensor {name}")
            ):
                fail(f"adapter tensor identity changed: {name}")
    complete = _exact(
        _read_canonical_json(root / "COMPLETE.json", "adapter completion"),
        ["version", "status", "manifest_members", "state_fingerprint", "project_manifest_sha256"],
        "adapter completion",
    )
    if complete != {
        "version": ADAPTER_VERSION,
        "status": "COMPLETE_STRICT_PEFT_ADAPTER",
        "manifest_members": sorted(manifest),
        "state_fingerprint": config["state_fingerprint"],
        "project_manifest_sha256": config["project_manifest_sha256"],
    }:
        fail("adapter completion marker changed")
    return {"root": root, "config": config, "tensors": tensors, "manifest_sha256": sha256_file(root / "MANIFEST.sha256")}


def load_adapter(
    project: LoadedSliceGPTProjectV4,
    adapter_root: Path,
) -> Any:
    if type(project) is not LoadedSliceGPTProjectV4:
        fail("adapter loading requires the strict project-loader result")
    archive = validate_adapter_archive(
        adapter_root, expected_project_manifest_sha256=project.manifest_sha256
    )
    return _load_adapter_archive_on_model(project.model, archive, allow_unloaded_meta=False)


def _load_adapter_archive_on_model(
    model: Any,
    archive: Mapping[str, Any],
    *,
    allow_unloaded_meta: bool,
) -> Any:
    config = archive["config"]
    wrapped = _attach_exact_lora(
        model,
        rank=config["rank"],
        alpha=config["alpha"],
        adapter_name=config["adapter_name"],
        allow_unloaded_meta=allow_unloaded_meta,
    )
    with safe_open(archive["root"] / "adapter_model.safetensors", framework="pt", device="cpu") as handle:
        state = {name: handle.get_tensor(name) for name in handle.keys()}
    named_parameters = dict(wrapped.named_parameters())
    for saved_name, tensor in state.items():
        prefix = saved_name.removesuffix(".weight")
        parameter_name = f"{prefix}.{config['adapter_name']}.weight"
        existing = named_parameters.get(parameter_name)
        if type(existing) is not nn.Parameter:
            fail(f"reloaded adapter parameter surface changed: {parameter_name}")
        owner, leaf = _owner(wrapped, parameter_name)
        device = tensor.device if existing.device.type == "meta" else existing.device
        owner._parameters[leaf] = nn.Parameter(
            tensor.to(device=device, dtype=torch.float32), requires_grad=True
        )
    reloaded = peft.get_peft_model_state_dict(wrapped, adapter_name=config["adapter_name"])
    if set(reloaded) != set(archive["tensors"]):
        fail("reloaded adapter key surface changed")
    for name, tensor in reloaded.items():
        if tensor.dtype is not torch.float32 or tensor_sha256(tensor) != archive["tensors"][name]["sha256"]:
            fail(f"reloaded adapter is not bit-identical: {name}")
    return wrapped


def qualify_one_step_peft(
    *,
    project_root: Path,
    adapter_output: Path,
    input_ids: Any,
    attention_mask: Any,
    device: str | Any = "cpu",
    learning_rate: float = 1e-4,
) -> dict[str, Any]:
    """Run the exact attach/step/save/reload/merge equivalence smoke.

    This returns evidence only; it never authorizes slicing or emits a Probe-2
    verdict.  Scalar evaluation remains a caller/qualifier responsibility.
    """

    _runtime()
    if type(learning_rate) is not float or not math.isfinite(learning_rate) or learning_rate <= 0.0:
        fail("qualification learning rate must be a positive finite float")
    if (
        not isinstance(input_ids, torch.Tensor)
        or input_ids.dtype is not torch.int64
        or input_ids.ndim != 2
        or not isinstance(attention_mask, torch.Tensor)
        or attention_mask.dtype is not torch.int64
        or tuple(attention_mask.shape) != tuple(input_ids.shape)
        or not bool((attention_mask == 1).all().item())
    ):
        fail("qualification input surface changed")
    project = load_project(project_root, device=device)
    wrapped = attach_project_lora(project)
    wrapped.train()
    optimizer = torch.optim.AdamW(
        [parameter for parameter in wrapped.parameters() if parameter.requires_grad],
        lr=learning_rate,
    )
    batch_ids = input_ids.to(device)
    batch_mask = attention_mask.to(device)
    result = wrapped(input_ids=batch_ids, attention_mask=batch_mask, labels=batch_ids, use_cache=False)
    if result.loss is None or not bool(torch.isfinite(result.loss).item()):
        fail("one-step PEFT loss is non-finite")
    result.loss.backward()
    trainable = [parameter for parameter in wrapped.parameters() if parameter.requires_grad]
    if not trainable or any(
        parameter.dtype is not torch.float32
        or parameter.grad is None
        or parameter.grad.dtype is not torch.float32
        or not bool(torch.isfinite(parameter.grad).all().item())
        for parameter in trainable
    ):
        fail("one-step PEFT gradients are not complete finite FP32")
    optimizer.step()
    optimizer_state_tensors = [
        value
        for state in optimizer.state.values()
        for value in state.values()
        if isinstance(value, torch.Tensor)
    ]
    if not optimizer_state_tensors or any(
        value.dtype is not torch.float32 or not bool(torch.isfinite(value).all().item())
        for value in optimizer_state_tensors
    ):
        fail("one-step PEFT optimizer state is not finite FP32")
    optimizer.zero_grad(set_to_none=True)
    wrapped.eval()
    with torch.no_grad():
        adapted_logits = wrapped(input_ids=batch_ids, attention_mask=batch_mask, use_cache=False).logits.float().cpu()
    adapter = save_adapter(project, wrapped, output=adapter_output)

    reloaded_project = load_project(project_root, device=device)
    reloaded = load_adapter(reloaded_project, adapter_output)
    reloaded.eval()
    with torch.no_grad():
        reloaded_logits = reloaded(input_ids=batch_ids, attention_mask=batch_mask, use_cache=False).logits.float().cpu()
    if not torch.equal(adapted_logits, reloaded_logits):
        fail("PEFT save/reload logits are not bit-identical")
    merged = reloaded.merge_and_unload(safe_merge=True)
    if type(merged) is not TEXT.Gemma3SliceGPTTextForCausalLMV4:
        fail("PEFT merge did not return the exact canonical model class")
    TEXT.validate_text_model(merged)
    merged.tie_weights()
    merged.eval()
    with torch.no_grad():
        merged_logits = merged(input_ids=batch_ids, attention_mask=batch_mask, use_cache=False).logits.float().cpu()
    maximum_delta = float((reloaded_logits - merged_logits).abs().max().item())
    top1_equal = bool(torch.equal(reloaded_logits.argmax(dim=-1), merged_logits.argmax(dim=-1)))
    if not top1_equal or maximum_delta > 0.02:
        fail("PEFT merged logits exceed the strict equivalence boundary")
    return {
        "version": ADAPTER_VERSION,
        "status": "PASS_ONE_STEP_PEFT_PROJECT_ROUNDTRIP",
        "project_manifest_sha256": project.manifest_sha256,
        "adapter_manifest_sha256": adapter["manifest_sha256"],
        "target_module_count": 238,
        "trainable_tensor_count": 476,
        "save_reload_bit_identical": True,
        "merged_top1_identical": True,
        "merged_max_abs_logit_delta": format(maximum_delta, ".17g"),
        "scalar_evaluation_passed": False,
        "nonzero_slice_authorized": False,
        "probe2_verdict": None,
    }


def qualification_status() -> dict[str, Any]:
    return {
        "version": VERSION,
        "native_sharded_safetensors_implemented": True,
        "strict_project_loader_implemented": True,
        "exact_238_target_peft_support_implemented": True,
        "full_width_only": True,
        "nonzero_slice_authorized": False,
        "probe2_verdict": None,
        "remaining_gates": [
            "real full-width model archive save/load/generation roundtrip",
            "real one-step PEFT scalar evaluation",
            "sealed reduced-width capability issuer",
        ],
    }
