"""Materialize and seal the frozen SliceGPT v4 WikiText-2 calibration tensors.

Materialization is deliberately local-cache-only: callers supply the exact
Arrow and metadata files whose SHA-256 values are frozen in the v4 protocol,
plus an exact local Gemma-3 tokenizer snapshot.  The pinned vendored SliceGPT
``prepare_dataloader`` function performs preprocessing.  No validation path
imports datasets, Torch, Transformers, or any network client.
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import importlib
import importlib.metadata
import json
import math
import os
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import unicodedata
import platform
from pathlib import Path


VERSION = "probe2_slicegpt_v4_calibration_tensors_v1"
DATASET_NAME = "wikitext"
DATASET_CONFIG = "wikitext-2-raw-v1"
DATASET_SPLIT = "train"
EXPECTED_TRAIN_ROWS = 36718
ARROW_SHA256 = "57947bc7b58df4b19662c0609cc30651bc84328dab5fd588860b752072911789"
DATASET_METADATA_SHA256 = "47ce56e8a2ca0183a37850cbce75cec29f64a1f61da978386c2a0598da4a6f66"
NSAMPLES = 128
SEQLEN = 2048
BATCH_SIZE = 16
CALIBRATION_SEEDS = (0, 1, 2, 7, 11)
TENSOR_SHAPE = [NSAMPLES, SEQLEN]
TENSOR_DTYPE = "I64"
TENSOR_NAMES = ("attention_mask", "input_ids")
SAFETENSORS_NAME = "calibration.safetensors"
METADATA_NAME = "calibration_metadata.json"
COMPLETE_NAME = "COMPLETE.json"
MANIFEST_NAME = "MANIFEST.sha256"
ARCHIVE_MEMBERS = {SAFETENSORS_NAME, METADATA_NAME, COMPLETE_NAME}
VENDOR_DATA_UTILS = "vendor/TransformerCompression/source/src/slicegpt/data_utils.py"
VENDOR_COMMIT = "6b12cdee6ad51791d7c776b3a046bc408b9e77e9"
SOURCE_PATHS = (
    "scripts/materialize_slicegpt_calibration_v4.py",
    "scripts/test_materialize_slicegpt_calibration_v4.py",
    "scripts/verify_transformer_compression_vendor.py",
    "docs/V4_SLICEGPT_PROTOCOL.md",
    "vendor/TransformerCompression/UPSTREAM.md",
    "vendor/TransformerCompression/SOURCE_SHA256SUMS",
    VENDOR_DATA_UTILS,
)
DISJOINT_PROMPT_PATHS = (
    "data/decay_scalar_prompts.json",
    "data/rehearsal_capability_prompts.json",
    "data/conversational_survival_generations.json",
    "data/probes.json",
    "data/forget.json",
    "data/forget_qa.json",
    "data/forget_qa_onpolicy.json",
    "data/forget_qa_onpolicy_run8.json",
    "data/forget_concept_clozes.json",
    "data/forget_concept_clozes_hard.json",
    "data/forget_neighbour_prompts.json",
    "data/forget_neighbour_onpolicy.json",
    "data/forget_sea_neighbour_onpolicy.json",
    "data/heal_corpus.json",
    "data/heldout_neighbour_generations.json",
)
COMMITTED_PATHS = SOURCE_PATHS + DISJOINT_PROMPT_PATHS
PROMPT_KEYS = {"prompt", "instruction", "question", "text"}
NORMALISATION = "unicode_nfkc_casefold_whitespace_v1"
DISJOINT_MATCH_POLICY = "full protected prompt as substring of decoded calibration row"
PREPROCESSING = {
    "implementation": "pinned_vendor_slicegpt.data_utils.prepare_dataloader",
    "dataset_filter": "len(first_column_value)>0",
    "derived_filter_cache": (
        "datasets caching disabled; exact Arrow copy loaded in a fresh private temporary directory"
    ),
    "fixed_length_construction": (
        "torch.randint contiguous unused-row spans; tokenizer.tokenize; separator newline-newline; "
        "truncate token list to 2048; tokenizer.convert_tokens_to_string"
    ),
    "second_tokenization": (
        "padding=longest,max_length=2048,truncation=true,return_tensors=pt"
    ),
    "sampler": "SubsetRandomSampler(torch.randperm(len(ds))[:128])",
    "nsamples": NSAMPLES,
    "sequence_length": SEQLEN,
    "batch_size": BATCH_SIZE,
    "varied_sequence_lengths": False,
    "attention_mask_required_all_one": True,
}
EXPECTED_RUNTIME = {
    "python": "3.12.3",
    # importlib.metadata reports the distribution version without the local
    # CUDA build suffix.  torch.__version__ is bound separately below.
    "torch": "2.13.0",
    "transformers": "5.14.1",
    "datasets": "5.0.0",
    "numpy": "2.5.1",
    "accelerate": "1.14.0",
    "peft": "0.19.1",
    "safetensors": "0.8.0",
    "tokenizers": "0.22.2",
    "pyarrow": "25.0.0",
}
EXPECTED_TORCH_BUILD = "2.13.0+cu130"
EXPECTED_NVIDIA_DRIVER = "595.71.05"
RUNTIME_LOCK_VERSION = "slicegpt_v4_runtime_observation_v1"
EXPECTED_DETERMINISM = {
    "deterministic_algorithms": True,
    "cuda_matmul_allow_tf32": False,
    "cudnn_allow_tf32": False,
    "cublas_workspace_config": ":4096:8",
}
# Captured at module import so callers cannot satisfy the startup contract by
# mutating the environment immediately before ``materialize``.
INITIAL_CUBLAS_WORKSPACE_CONFIG = os.environ.get("CUBLAS_WORKSPACE_CONFIG")


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--parent-model", required=True)
    parser.add_argument("--train-arrow", required=True)
    parser.add_argument("--dataset-metadata", required=True)
    parser.add_argument("--runtime-lock", required=True)
    parser.add_argument("--seed", type=int, choices=CALIBRATION_SEEDS, default=11)
    parser.add_argument("--root", default="derisk/probe2_slicegpt_v4_calibration_seed11")
    return parser.parse_args()


def sha256_of_file(path, chunk=1 << 20):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        while block := handle.read(chunk):
            digest.update(block)
    return digest.hexdigest()


def fingerprint(payload):
    reject_nonfinite(payload)
    return hashlib.sha256(
        json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()


def reject_nonfinite(value, label="JSON"):
    if isinstance(value, float) and not math.isfinite(value):
        raise RuntimeError(f"{label} contains a non-finite number")
    if isinstance(value, dict):
        for key, child in value.items():
            if not isinstance(key, str):
                raise RuntimeError(f"{label} contains a non-string key")
            reject_nonfinite(child, label)
    elif isinstance(value, (list, tuple)):
        for child in value:
            reject_nonfinite(child, label)


def canonical_json_bytes(payload):
    reject_nonfinite(payload)
    return (
        json.dumps(
            payload,
            indent=2,
            sort_keys=True,
            separators=(",", ": "),
            ensure_ascii=False,
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")


def read_json(path):
    def reject_constant(value):
        raise RuntimeError(f"non-finite JSON constant: {value}")

    payload = json.loads(
        Path(path).read_text(encoding="utf-8"), parse_constant=reject_constant
    )
    reject_nonfinite(payload, str(path))
    return payload


def atomic_write_json(path, payload):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_bytes(canonical_json_bytes(payload))
    temporary.replace(path)


def reject_symlink_components(path, label, base=None):
    path = Path(path).expanduser()
    if not path.is_absolute():
        path = (Path.cwd() if base is None else Path(base)) / path
    lexical = Path(os.path.abspath(path))
    for component in reversed((lexical, *lexical.parents)):
        if component.is_symlink():
            raise RuntimeError(f"{label} contains a symlink component: {component}")
    return lexical


def exact_hash_map(payload, label):
    if not isinstance(payload, dict) or not payload:
        raise RuntimeError(f"missing {label} hash map")
    if any(
        not isinstance(key, str)
        or not key
        or re.fullmatch(r"[0-9a-f]{64}", str(value)) is None
        for key, value in payload.items()
    ):
        raise RuntimeError(f"malformed {label} hash map")
    return payload


def committed_source_identity(repo, relative_paths=COMMITTED_PATHS):
    repo = Path(repo).resolve()
    commit = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=repo, text=True
    ).strip()
    if re.fullmatch(r"[0-9a-f]{40}", commit) is None:
        raise RuntimeError("calibration materializer cannot bind Git HEAD")
    hashes = {}
    for relative in relative_paths:
        try:
            blob = subprocess.run(
                ["git", "show", f"{commit}:{relative}"],
                cwd=repo,
                check=True,
                capture_output=True,
            ).stdout
        except subprocess.CalledProcessError as error:
            raise RuntimeError(f"materializer source is not committed: {relative}") from error
        committed_oid = subprocess.check_output(
            ["git", "rev-parse", f"{commit}:{relative}"], cwd=repo, text=True
        ).strip()
        current_oid = subprocess.check_output(
            ["git", "hash-object", "--path", relative, relative], cwd=repo, text=True
        ).strip()
        if committed_oid != current_oid:
            raise RuntimeError(f"materializer source differs from HEAD: {relative}")
        hashes[relative] = hashlib.sha256(blob).hexdigest()
    return {"commit": commit, "sha256": hashes}


def validate_recorded_source_identity(repo, identity):
    if (
        not isinstance(identity, dict)
        or set(identity) != {"commit", "sha256"}
        or re.fullmatch(r"[0-9a-f]{40}", str(identity.get("commit"))) is None
        or not isinstance(identity.get("sha256"), dict)
        or set(identity["sha256"]) != set(COMMITTED_PATHS)
    ):
        raise RuntimeError("malformed calibration source identity")
    commit = identity["commit"]
    for relative in COMMITTED_PATHS:
        digest = identity["sha256"].get(relative)
        if re.fullmatch(r"[0-9a-f]{64}", str(digest)) is None:
            raise RuntimeError("malformed calibration source hash")
        try:
            blob = subprocess.run(
                ["git", "show", f"{commit}:{relative}"],
                cwd=repo,
                check=True,
                capture_output=True,
            ).stdout
        except subprocess.CalledProcessError as error:
            raise RuntimeError(f"recorded calibration source lacks {relative}") from error
        if hashlib.sha256(blob).hexdigest() != digest:
            raise RuntimeError(f"recorded calibration source changed: {relative}")


def validate_source_cache(train_arrow, dataset_metadata):
    train_arrow, dataset_metadata = Path(train_arrow), Path(dataset_metadata)
    if not train_arrow.is_file() or not dataset_metadata.is_file():
        raise RuntimeError("exact local WikiText-2 Arrow and metadata files are required")
    actual = {
        "train_arrow": sha256_of_file(train_arrow),
        "dataset_metadata": sha256_of_file(dataset_metadata),
    }
    expected = {
        "train_arrow": ARROW_SHA256,
        "dataset_metadata": DATASET_METADATA_SHA256,
    }
    if actual != expected:
        raise RuntimeError(f"WikiText-2 source-cache hashes changed: {actual}")
    return actual


def _exact_keys(value, expected, label):
    if not isinstance(value, dict) or set(value) != set(expected):
        raise RuntimeError(f"{label} has changed keys")
    return value


def _require_hash(value, label, length=64):
    if re.fullmatch(rf"[0-9a-f]{{{length}}}", str(value)) is None:
        raise RuntimeError(f"{label} is not an exact hash")


def validate_runtime_observation(observation):
    """Validate the independently captured, immutable v4 runtime lock."""
    observation = _exact_keys(
        observation,
        ["version", "python", "packages", "platform", "torch", "cuda", "determinism"],
        "runtime lock",
    )
    if observation["version"] != RUNTIME_LOCK_VERSION:
        raise RuntimeError("runtime lock version changed")
    python = _exact_keys(
        observation["python"],
        ["version", "implementation", "executable", "executable_sha256"],
        "runtime Python",
    )
    if python["version"] != EXPECTED_RUNTIME["python"] or python["implementation"] != "CPython":
        raise RuntimeError("runtime Python identity changed")
    if not isinstance(python["executable"], str) or not python["executable"]:
        raise RuntimeError("runtime Python executable is missing")
    _require_hash(python["executable_sha256"], "runtime Python executable")
    expected_packages = {key: value for key, value in EXPECTED_RUNTIME.items() if key != "python"}
    if _exact_keys(observation["packages"], expected_packages, "runtime packages") != expected_packages:
        raise RuntimeError("runtime package lock changed")
    platform_record = _exact_keys(
        observation["platform"], ["system", "release", "version", "machine"], "runtime platform"
    )
    if any(not isinstance(value, str) or not value for value in platform_record.values()):
        raise RuntimeError("runtime platform identity is incomplete")
    torch_record = _exact_keys(
        observation["torch"],
        ["version", "git_version", "config_sha256", "cuda_runtime", "cudnn_version"],
        "runtime Torch",
    )
    if torch_record["version"] != EXPECTED_TORCH_BUILD or torch_record["cuda_runtime"] != "13.0":
        raise RuntimeError("runtime Torch/CUDA identity changed")
    _require_hash(torch_record["git_version"], "runtime Torch Git", length=40)
    _require_hash(torch_record["config_sha256"], "runtime Torch config")
    if type(torch_record["cudnn_version"]) is not int or torch_record["cudnn_version"] <= 0:
        raise RuntimeError("runtime cuDNN identity changed")
    cuda = _exact_keys(
        observation["cuda"],
        ["available", "device_count", "current_device", "driver_version", "gpu"],
        "runtime CUDA",
    )
    if (
        cuda["available"] is not True
        or type(cuda["device_count"]) is not int
        or cuda["device_count"] != 1
        or type(cuda["current_device"]) is not int
        or cuda["current_device"] != 0
        or cuda["driver_version"] != EXPECTED_NVIDIA_DRIVER
    ):
        raise RuntimeError("runtime CUDA/driver identity changed")
    gpu = _exact_keys(cuda["gpu"], ["name", "total_memory_bytes", "compute_capability"], "runtime GPU")
    if (
        gpu["name"] != "NVIDIA L4"
        or type(gpu["total_memory_bytes"]) is not int
        or gpu["total_memory_bytes"] <= 0
        or not isinstance(gpu["compute_capability"], list)
        or len(gpu["compute_capability"]) != 2
        or any(type(value) is not int for value in gpu["compute_capability"])
        or gpu["compute_capability"] != [8, 9]
    ):
        raise RuntimeError("runtime GPU is not the frozen NVIDIA L4 host")
    if _exact_keys(
        observation["determinism"], EXPECTED_DETERMINISM, "runtime determinism"
    ) != EXPECTED_DETERMINISM:
        raise RuntimeError("runtime determinism contract changed")
    return observation


def load_runtime_lock(path):
    path = reject_symlink_components(path, "v4 runtime lock")
    if not path.is_file():
        raise RuntimeError("pre-existing immutable v4 runtime lock is required")
    raw = path.read_bytes()
    observation = read_json(path)
    if raw != canonical_json_bytes(observation):
        raise RuntimeError("v4 runtime lock must be canonical JSON")
    validate_runtime_observation(observation)
    return observation, hashlib.sha256(raw).hexdigest()


def configure_determinism(torch):
    if os.environ.get("CUBLAS_WORKSPACE_CONFIG") != ":4096:8":
        raise RuntimeError("CUBLAS_WORKSPACE_CONFIG=:4096:8 must be set before Python starts")
    torch.use_deterministic_algorithms(True)
    torch.backends.cuda.matmul.allow_tf32 = False
    torch.backends.cudnn.allow_tf32 = False
    actual = {
        "deterministic_algorithms": bool(torch.are_deterministic_algorithms_enabled()),
        "cuda_matmul_allow_tf32": bool(torch.backends.cuda.matmul.allow_tf32),
        "cudnn_allow_tf32": bool(torch.backends.cudnn.allow_tf32),
        "cublas_workspace_config": os.environ.get("CUBLAS_WORKSPACE_CONFIG"),
    }
    if actual != EXPECTED_DETERMINISM:
        raise RuntimeError(f"v4 determinism enforcement failed: {actual}")


def capture_runtime_observation(torch):
    packages = {}
    for package in EXPECTED_RUNTIME:
        if package == "python":
            continue
        try:
            packages[package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError as error:
            raise RuntimeError(f"missing frozen v4 runtime package: {package}") from error
    executable = Path(sys.executable).resolve()
    driver = subprocess.check_output(
        ["nvidia-smi", "--query-gpu=driver_version", "--format=csv,noheader,nounits"],
        text=True,
    ).strip()
    if not torch.cuda.is_available() or torch.cuda.device_count() != 1:
        raise RuntimeError("v4 materialization host must expose exactly one CUDA GPU")
    index = torch.cuda.current_device()
    properties = torch.cuda.get_device_properties(index)
    observation = {
        "version": RUNTIME_LOCK_VERSION,
        "python": {
            "version": platform.python_version(),
            "implementation": platform.python_implementation(),
            "executable": executable.as_posix(),
            "executable_sha256": sha256_of_file(executable),
        },
        "packages": packages,
        "platform": {
            "system": platform.system(),
            "release": platform.release(),
            "version": platform.version(),
            "machine": platform.machine(),
        },
        "torch": {
            "version": str(torch.__version__),
            "git_version": str(torch.version.git_version),
            "config_sha256": hashlib.sha256(torch.__config__.show().encode("utf-8")).hexdigest(),
            "cuda_runtime": str(torch.version.cuda),
            "cudnn_version": int(torch.backends.cudnn.version()),
        },
        "cuda": {
            "available": bool(torch.cuda.is_available()),
            "device_count": int(torch.cuda.device_count()),
            "current_device": int(index),
            "driver_version": driver,
            "gpu": {
                "name": str(properties.name),
                "total_memory_bytes": int(properties.total_memory),
                "compute_capability": [int(properties.major), int(properties.minor)],
            },
        },
        "determinism": {
            "deterministic_algorithms": bool(torch.are_deterministic_algorithms_enabled()),
            "cuda_matmul_allow_tf32": bool(torch.backends.cuda.matmul.allow_tf32),
            "cudnn_allow_tf32": bool(torch.backends.cudnn.allow_tf32),
            "cublas_workspace_config": os.environ.get("CUBLAS_WORKSPACE_CONFIG", ""),
        },
    }
    return validate_runtime_observation(observation)


def runtime_record(torch, runtime_lock, runtime_lock_sha256):
    live = capture_runtime_observation(torch)
    if live != runtime_lock:
        raise RuntimeError("live runtime does not exactly reproduce the immutable v4 runtime lock")
    return {
        "runtime_lock_sha256": runtime_lock_sha256,
        "observation": runtime_lock,
    }


@contextlib.contextmanager
def isolated_arrow_copy(train_arrow):
    """Make upstream Datasets derived-cache reuse impossible by construction."""
    train_arrow = Path(train_arrow)
    before = sha256_of_file(train_arrow)
    with tempfile.TemporaryDirectory(prefix="slicegpt-v4-wikitext-") as temporary:
        isolated = Path(temporary) / "train.arrow"
        shutil.copyfile(train_arrow, isolated)
        if sha256_of_file(isolated) != before or set(isolated.parent.iterdir()) != {isolated}:
            raise RuntimeError("failed to create a pristine isolated WikiText Arrow copy")
        yield isolated
    if sha256_of_file(train_arrow) != before:
        raise RuntimeError("frozen WikiText Arrow changed during materialization")


def disable_datasets_derived_cache(datasets):
    datasets.disable_caching()
    if datasets.is_caching_enabled():
        raise RuntimeError("Hugging Face Datasets derived-cache reuse could not be disabled")


def load_verified_prepare_dataloader(repo, expected_sha256):
    """Import only the recorded vendor module, defeating sys.modules substitution."""
    contaminated = sorted(
        name for name in sys.modules if name == "slicegpt" or name.startswith("slicegpt.")
    )
    if contaminated:
        raise RuntimeError(f"preloaded slicegpt modules are forbidden: {contaminated}")
    vendor_src = Path(repo) / "vendor/TransformerCompression/source/src"
    expected_path = (vendor_src / "slicegpt/data_utils.py").resolve()
    sys.path.insert(0, str(vendor_src))
    try:
        module = importlib.import_module("slicegpt.data_utils")
    finally:
        if sys.path and sys.path[0] == str(vendor_src):
            sys.path.pop(0)
    actual_path = Path(module.__file__).resolve()
    if actual_path != expected_path or sha256_of_file(actual_path) != expected_sha256:
        raise RuntimeError("imported SliceGPT data_utils is not the recorded vendored source")
    return module.prepare_dataloader


def model_file_hashes(model_path):
    model_path = Path(model_path)
    weight_suffixes = (".safetensors", ".bin", ".pt", ".pth")
    weights, support = {}, {}
    for path in sorted(model_path.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(model_path).as_posix()
        target = weights if path.name.endswith(weight_suffixes) else support
        target[relative] = sha256_of_file(path)
    exact_hash_map(weights, "parent weights")
    exact_hash_map(support, "parent support")
    return weights, support


def normalise_text(value):
    value = unicodedata.normalize("NFKC", value).casefold()
    return " ".join(value.split())


def collect_prompt_strings(payload):
    found = set()

    def visit(node, root=False):
        if isinstance(node, str):
            if root and node.strip():
                found.add(node.strip())
            return
        if isinstance(node, list):
            for child in node:
                visit(child, root=root)
            return
        if isinstance(node, dict):
            for key, child in node.items():
                if key in PROMPT_KEYS and isinstance(child, str) and child.strip():
                    found.add(child.strip())
                else:
                    visit(child, root=False)

    visit(payload, root=isinstance(payload, list) and all(isinstance(x, str) for x in payload))
    return found


def load_disjoint_prompts(repo):
    prompts, files = set(), {}
    for relative in DISJOINT_PROMPT_PATHS:
        path = Path(repo) / relative
        if not path.is_file() or path.is_symlink():
            raise RuntimeError(f"missing disjointness source: {relative}")
        files[relative] = sha256_of_file(path)
        prompts.update(collect_prompt_strings(read_json(path)))
    if not prompts:
        raise RuntimeError("disjointness prompt set is empty")
    return prompts, files


def check_disjointness(decoded_rows, prompts):
    exact_matches, normalised_matches = [], []
    normalised_prompts = {
        prompt: normalise_text(prompt) for prompt in sorted(prompts) if normalise_text(prompt)
    }
    for row_index, decoded in enumerate(decoded_rows):
        normalised_row = normalise_text(decoded)
        for prompt, normalised_prompt in normalised_prompts.items():
            if prompt in decoded:
                exact_matches.append({"row": row_index, "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest()})
            if normalised_prompt in normalised_row:
                normalised_matches.append(
                    {"row": row_index, "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest()}
                )
    if exact_matches or normalised_matches:
        raise RuntimeError(
            "calibration tensors overlap protected prompts: "
            f"exact={exact_matches[:5]} normalized={normalised_matches[:5]}"
        )
    return {
        "normalisation": NORMALISATION,
        "match_policy": DISJOINT_MATCH_POLICY,
        "protected_prompt_count": len(prompts),
        "decoded_row_count": len(decoded_rows),
        "exact_matches": [],
        "normalised_matches": [],
    }


def parse_safetensors(path, expected_seed=None):
    path = Path(path)
    size = path.stat().st_size
    with path.open("rb") as handle:
        prefix = handle.read(8)
        if len(prefix) != 8:
            raise RuntimeError("truncated calibration safetensors prefix")
        header_length = struct.unpack("<Q", prefix)[0]
        if header_length <= 0 or 8 + header_length > size:
            raise RuntimeError("invalid calibration safetensors header length")
        header_bytes = handle.read(header_length)
        try:
            header = json.loads(header_bytes.decode("utf-8").rstrip(" "))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise RuntimeError("malformed calibration safetensors header") from error
        if not isinstance(header, dict):
            raise RuntimeError("calibration safetensors header is not an object")
        header_metadata = header.get("__metadata__")
        if (
            not isinstance(header_metadata, dict)
            or set(header_metadata) != {"version", "dataset", "seed"}
            or header_metadata.get("version") != VERSION
            or header_metadata.get("dataset")
            != f"{DATASET_NAME}/{DATASET_CONFIG}:{DATASET_SPLIT}"
            or header_metadata.get("seed") not in {str(seed) for seed in CALIBRATION_SEEDS}
            or (
                expected_seed is not None
                and header_metadata.get("seed") != str(expected_seed)
            )
        ):
            raise RuntimeError("calibration safetensors header metadata changed")
        tensor_headers = {key: value for key, value in header.items() if key != "__metadata__"}
        if set(tensor_headers) != set(TENSOR_NAMES):
            raise RuntimeError("calibration safetensors tensor-name surface changed")
        data_start = 8 + header_length
        records = {}
        spans = []
        for name in TENSOR_NAMES:
            record = tensor_headers[name]
            if (
                not isinstance(record, dict)
                or set(record) != {"dtype", "shape", "data_offsets"}
                or record["dtype"] != TENSOR_DTYPE
                or record["shape"] != TENSOR_SHAPE
                or not isinstance(record["data_offsets"], list)
                or len(record["data_offsets"]) != 2
                or any(type(value) is not int for value in record["data_offsets"])
            ):
                raise RuntimeError(f"calibration safetensors schema changed: {name}")
            start, end = record["data_offsets"]
            expected_bytes = NSAMPLES * SEQLEN * 8
            if start < 0 or end - start != expected_bytes:
                raise RuntimeError(f"calibration safetensors offsets changed: {name}")
            spans.append((start, end, name))
        spans.sort()
        if spans[0][0] != 0 or any(spans[i][1] != spans[i + 1][0] for i in range(len(spans) - 1)):
            raise RuntimeError("calibration safetensors data spans are not canonical contiguous spans")
        if data_start + spans[-1][1] != size:
            raise RuntimeError("calibration safetensors has trailing or missing bytes")
        for start, end, name in spans:
            handle.seek(data_start + start)
            raw = handle.read(end - start)
            if len(raw) != end - start:
                raise RuntimeError("truncated calibration tensor data")
            if name == "attention_mask":
                if raw != struct.pack("<q", 1) * (NSAMPLES * SEQLEN):
                    raise RuntimeError("calibration attention_mask is not all-one int64")
                minimum = maximum = 1
                all_one = True
            else:
                values = struct.iter_unpack("<q", raw)
                minimum, maximum = None, None
                for (value,) in values:
                    minimum = value if minimum is None else min(minimum, value)
                    maximum = value if maximum is None else max(maximum, value)
                if minimum is None or minimum < 0:
                    raise RuntimeError("calibration input_ids contain a negative or empty value")
                all_one = False
            records[name] = {
                "dtype": TENSOR_DTYPE,
                "shape": TENSOR_SHAPE,
                "byte_sha256": hashlib.sha256(raw).hexdigest(),
                "minimum": minimum,
                "maximum": maximum,
                "all_one": all_one,
            }
    return records


def manifest_entries(root):
    root = Path(root)
    return {
        path.relative_to(root).as_posix(): sha256_of_file(path)
        for path in sorted(root.rglob("*"))
        if path.is_file() and path != root / MANIFEST_NAME
    }


def write_manifest(root):
    root = Path(root)
    temporary = root / (MANIFEST_NAME + ".tmp")
    if temporary.exists() or temporary.is_symlink():
        raise RuntimeError("refusing to replace a partial calibration manifest")
    if any(path.is_symlink() or path.is_dir() for path in root.rglob("*")):
        raise RuntimeError("calibration archive contains a symlink or directory")
    entries = manifest_entries(root)
    if set(entries) != ARCHIVE_MEMBERS:
        raise RuntimeError("calibration archive pre-manifest layout changed")
    temporary.write_text(
        "\n".join(f"{entries[name]}  {name}" for name in sorted(entries)) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    temporary.replace(root / MANIFEST_NAME)


def verify_manifest(root):
    root = reject_symlink_components(root, "calibration archive")
    manifest = root / MANIFEST_NAME
    if not manifest.is_file():
        return False
    if any(path.is_symlink() or path.is_dir() for path in root.rglob("*")):
        raise RuntimeError("sealed calibration archive contains a symlink or directory")
    expected = {}
    for line in manifest.read_text(encoding="utf-8").splitlines():
        digest, separator, relative = line.partition("  ")
        if (
            not separator
            or re.fullmatch(r"[0-9a-f]{64}", digest) is None
            or relative not in ARCHIVE_MEMBERS
            or relative in expected
        ):
            raise RuntimeError(f"malformed calibration manifest line: {line!r}")
        expected[relative] = digest
    actual = manifest_entries(root)
    if expected != actual or set(actual) != ARCHIVE_MEMBERS:
        raise RuntimeError("sealed calibration archive changed")
    return True


def validate_sealed_archive(root, repo=None, parent_model=None, runtime_lock_path=None):
    root = reject_symlink_components(root, "calibration archive")
    if not verify_manifest(root):
        return None
    metadata_path = root / METADATA_NAME
    tensors_path = root / SAFETENSORS_NAME
    complete_path = root / COMPLETE_NAME
    metadata, complete = read_json(metadata_path), read_json(complete_path)
    if not isinstance(metadata, dict) or not isinstance(complete, dict):
        raise RuntimeError("sealed calibration JSON is not object-shaped")
    body = {key: value for key, value in metadata.items() if key != "fingerprint"}
    expected_metadata_keys = {
        "version", "seed", "dataset", "preprocessing", "tokenizer", "parent",
        "tensors", "disjointness", "runtime", "vendor", "source_identity", "fingerprint",
    }
    expected_dataset = {
        "name": DATASET_NAME,
        "config": DATASET_CONFIG,
        "split": DATASET_SPLIT,
        "column_names": ["text"],
        "row_count": EXPECTED_TRAIN_ROWS,
        "source_cache_sha256": {
            "train_arrow": ARROW_SHA256,
            "dataset_metadata": DATASET_METADATA_SHA256,
        },
    }
    if (
        set(metadata) != expected_metadata_keys
        or metadata.get("version") != VERSION
        or metadata.get("seed") not in CALIBRATION_SEEDS
        or metadata.get("dataset") != expected_dataset
        or metadata.get("preprocessing") != PREPROCESSING
        or metadata.get("fingerprint") != fingerprint(body)
    ):
        raise RuntimeError("sealed calibration metadata semantics changed")
    runtime = metadata.get("runtime")
    if (
        not isinstance(runtime, dict)
        or set(runtime) != {"runtime_lock_sha256", "observation"}
        or re.fullmatch(r"[0-9a-f]{64}", str(runtime.get("runtime_lock_sha256"))) is None
        or runtime.get("runtime_lock_sha256")
        != hashlib.sha256(canonical_json_bytes(runtime.get("observation"))).hexdigest()
    ):
        raise RuntimeError("sealed calibration runtime identity changed")
    validate_runtime_observation(runtime["observation"])
    if runtime_lock_path is not None:
        expected_lock, expected_lock_sha256 = load_runtime_lock(runtime_lock_path)
        if runtime != {
            "runtime_lock_sha256": expected_lock_sha256,
            "observation": expected_lock,
        }:
            raise RuntimeError("sealed calibration does not match the supplied immutable runtime lock")
    tokenizer = metadata.get("tokenizer")
    if (
        not isinstance(tokenizer, dict)
        or set(tokenizer) != {
            "source", "class", "length", "vocab_size", "special_tokens_map",
            "padding_side", "support_file_sha256", "fingerprint",
        }
        or type(tokenizer.get("length")) is not int
        or type(tokenizer.get("vocab_size")) is not int
        or tokenizer["length"] <= 0
        or tokenizer["vocab_size"] <= 0
        or tokenizer.get("padding_side") not in {"left", "right"}
        or tokenizer.get("fingerprint")
        != fingerprint({key: value for key, value in tokenizer.items() if key != "fingerprint"})
    ):
        raise RuntimeError("sealed calibration tokenizer identity changed")
    exact_hash_map(tokenizer.get("support_file_sha256"), "tokenizer support")
    parent = metadata.get("parent")
    if (
        not isinstance(parent, dict)
        or set(parent) != {"source", "weight_file_sha256", "support_file_sha256", "fingerprint"}
        or parent.get("fingerprint")
        != fingerprint({key: value for key, value in parent.items() if key != "fingerprint"})
    ):
        raise RuntimeError("sealed calibration parent identity changed")
    exact_hash_map(parent.get("weight_file_sha256"), "parent weights")
    exact_hash_map(parent.get("support_file_sha256"), "parent support")
    tensor_records = parse_safetensors(tensors_path, expected_seed=metadata.get("seed"))
    stored_tensors = metadata.get("tensors")
    if (
        not isinstance(stored_tensors, dict)
        or set(stored_tensors) != {"file", "sha256", "records"}
        or stored_tensors.get("file") != SAFETENSORS_NAME
        or stored_tensors.get("sha256") != sha256_of_file(tensors_path)
        or stored_tensors.get("records") != tensor_records
        or tensor_records["input_ids"]["maximum"] >= tokenizer["length"]
    ):
        raise RuntimeError("sealed calibration tensor identity changed")
    disjointness = metadata.get("disjointness")
    if (
        not isinstance(disjointness, dict)
        or set(disjointness) != {
            "normalisation", "match_policy", "protected_prompt_count", "decoded_row_count",
            "exact_matches", "normalised_matches", "source_file_sha256",
        }
        or disjointness.get("normalisation") != NORMALISATION
        or disjointness.get("match_policy") != DISJOINT_MATCH_POLICY
        or type(disjointness.get("protected_prompt_count")) is not int
        or disjointness["protected_prompt_count"] <= 0
        or disjointness.get("decoded_row_count") != NSAMPLES
        or disjointness.get("exact_matches") != []
        or disjointness.get("normalised_matches") != []
        or set(disjointness.get("source_file_sha256", {})) != set(DISJOINT_PROMPT_PATHS)
    ):
        raise RuntimeError("sealed calibration disjointness evidence changed")
    exact_hash_map(disjointness["source_file_sha256"], "disjointness source")
    identity = metadata.get("source_identity")
    if (
        not isinstance(identity, dict)
        or set(identity) != {"commit", "sha256"}
        or re.fullmatch(r"[0-9a-f]{40}", str(identity.get("commit"))) is None
        or not isinstance(identity.get("sha256"), dict)
        or set(identity["sha256"]) != set(COMMITTED_PATHS)
    ):
        raise RuntimeError("sealed calibration source identity changed")
    exact_hash_map(identity["sha256"], "calibration source")
    vendor = metadata.get("vendor")
    if vendor != {
        "commit": VENDOR_COMMIT,
        "data_utils_path": VENDOR_DATA_UTILS,
        "data_utils_sha256": identity["sha256"][VENDOR_DATA_UTILS],
    }:
        raise RuntimeError("sealed calibration vendor identity changed")
    if any(
        disjointness["source_file_sha256"][relative]
        != identity["sha256"][relative]
        for relative in DISJOINT_PROMPT_PATHS
    ):
        raise RuntimeError("sealed calibration prompts are not bound to committed blobs")
    expected_complete = {
        "status": "complete",
        "outcome": "CALIBRATION_TENSORS_MATERIALIZED",
        "metadata_sha256": sha256_of_file(metadata_path),
        "tensors_sha256": sha256_of_file(tensors_path),
        "metadata_fingerprint": metadata["fingerprint"],
    }
    if complete != expected_complete:
        raise RuntimeError("sealed calibration completion marker changed")
    if repo is not None:
        validate_recorded_source_identity(repo, identity)
        current_prompts, current_disjoint_hashes = load_disjoint_prompts(repo)
        if current_disjoint_hashes != disjointness["source_file_sha256"]:
            raise RuntimeError("sealed calibration disjointness sources changed")
        if len(current_prompts) != disjointness["protected_prompt_count"]:
            raise RuntimeError("sealed calibration protected prompt count changed")
    if parent_model is not None:
        weights, support = model_file_hashes(parent_model)
        if weights != parent["weight_file_sha256"] or support != parent["support_file_sha256"]:
            raise RuntimeError("sealed calibration parent model changed")
    return metadata


def materialize(args):
    repo = Path.cwd().resolve()
    root = reject_symlink_components(args.root, "calibration output root", base=repo)
    derisk = (repo / "derisk").resolve()
    if derisk not in root.parents:
        raise RuntimeError("calibration output root must be under repository derisk")
    parent = reject_symlink_components(args.parent_model, "calibration parent", base=repo)
    train_arrow = reject_symlink_components(args.train_arrow, "WikiText train Arrow", base=repo)
    dataset_metadata = reject_symlink_components(
        args.dataset_metadata, "WikiText dataset metadata", base=repo
    )
    runtime_lock_path = reject_symlink_components(
        args.runtime_lock, "v4 runtime lock", base=repo
    )
    runtime_lock, runtime_lock_sha256 = load_runtime_lock(runtime_lock_path)
    sealed = validate_sealed_archive(
        root,
        repo=repo,
        parent_model=parent,
        runtime_lock_path=runtime_lock_path,
    )
    if sealed is not None:
        return sealed
    if root.exists() and any(root.iterdir()):
        raise RuntimeError("calibration output root must be fresh")
    if not parent.is_dir():
        raise RuntimeError("calibration parent must be an exact local model directory")
    validate_source_cache(train_arrow, dataset_metadata)
    source_identity = committed_source_identity(repo)
    prompts, disjoint_hashes = load_disjoint_prompts(repo)
    weights, support = model_file_hashes(parent)

    os.environ["HF_DATASETS_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    os.environ["HF_HUB_OFFLINE"] = "1"
    if (
        INITIAL_CUBLAS_WORKSPACE_CONFIG != ":4096:8"
        or os.environ.get("CUBLAS_WORKSPACE_CONFIG") != ":4096:8"
    ):
        raise RuntimeError("CUBLAS_WORKSPACE_CONFIG=:4096:8 must be set before Python starts")
    import torch
    import datasets
    from safetensors.torch import save_file
    from transformers import AutoTokenizer

    configure_determinism(torch)
    runtime = runtime_record(torch, runtime_lock, runtime_lock_sha256)
    disable_datasets_derived_cache(datasets)
    prepare_dataloader = load_verified_prepare_dataloader(
        repo, source_identity["sha256"][VENDOR_DATA_UTILS]
    )

    tokenizer = AutoTokenizer.from_pretrained(parent, local_files_only=True)
    ids, masks = [], []
    with isolated_arrow_copy(train_arrow) as isolated_arrow:
        dataset = datasets.Dataset.from_file(str(isolated_arrow))
        if dataset.column_names != ["text"] or len(dataset) != EXPECTED_TRAIN_ROWS:
            raise RuntimeError(
                "exact WikiText-2 train Arrow schema changed: "
                f"columns={dataset.column_names} rows={len(dataset)}"
            )
        loader = prepare_dataloader(
            dataset=dataset,
            tokenizer=tokenizer,
            max_seqlen=SEQLEN,
            batch_size=BATCH_SIZE,
            nsamples=NSAMPLES,
            varied_seqlen=False,
            seed=args.seed,
        )
        for batch in loader:
            if set(batch) != {"input_ids", "attention_mask", "labels"}:
                raise RuntimeError("pinned upstream calibration batch schema changed")
            if not torch.equal(batch["labels"], batch["input_ids"]):
                raise RuntimeError("pinned upstream calibration labels/input identity changed")
            ids.append(batch["input_ids"].to(dtype=torch.int64, device="cpu"))
            masks.append(batch["attention_mask"].to(dtype=torch.int64, device="cpu"))
    input_ids = torch.cat(ids, dim=0).contiguous()
    attention_mask = torch.cat(masks, dim=0).contiguous()
    if list(input_ids.shape) != TENSOR_SHAPE or list(attention_mask.shape) != TENSOR_SHAPE:
        raise RuntimeError("materialized calibration tensor shape changed")
    if not torch.all(attention_mask == 1).item():
        raise RuntimeError("materialized calibration attention mask is not all one")
    if input_ids.min().item() < 0 or input_ids.max().item() >= len(tokenizer):
        raise RuntimeError("materialized calibration token IDs are outside tokenizer range")
    decoded_rows = [
        tokenizer.decode(row, skip_special_tokens=False, clean_up_tokenization_spaces=False)
        for row in input_ids
    ]
    disjointness = check_disjointness(decoded_rows, prompts)
    disjointness["source_file_sha256"] = disjoint_hashes

    root.mkdir(parents=True, exist_ok=True)
    tensors_path = root / SAFETENSORS_NAME
    save_file(
        {"attention_mask": attention_mask, "input_ids": input_ids},
        tensors_path,
        metadata={
            "version": VERSION,
            "dataset": f"{DATASET_NAME}/{DATASET_CONFIG}:{DATASET_SPLIT}",
            "seed": str(args.seed),
        },
    )
    tensor_records = parse_safetensors(tensors_path, expected_seed=args.seed)
    tokenizer_body = {
        "source": str(parent),
        "class": type(tokenizer).__name__,
        "length": len(tokenizer),
        "vocab_size": tokenizer.vocab_size,
        "special_tokens_map": tokenizer.special_tokens_map,
        "padding_side": tokenizer.padding_side,
        "support_file_sha256": support,
    }
    tokenizer_record = {**tokenizer_body, "fingerprint": fingerprint(tokenizer_body)}
    parent_body = {
        "source": str(parent),
        "weight_file_sha256": weights,
        "support_file_sha256": support,
    }
    parent_record = {**parent_body, "fingerprint": fingerprint(parent_body)}
    metadata_body = {
        "version": VERSION,
        "seed": args.seed,
        "dataset": {
            "name": DATASET_NAME,
            "config": DATASET_CONFIG,
            "split": DATASET_SPLIT,
            "column_names": ["text"],
            "row_count": EXPECTED_TRAIN_ROWS,
            "source_cache_sha256": validate_source_cache(train_arrow, dataset_metadata),
        },
        "preprocessing": PREPROCESSING,
        "tokenizer": tokenizer_record,
        "parent": parent_record,
        "tensors": {
            "file": SAFETENSORS_NAME,
            "sha256": sha256_of_file(tensors_path),
            "records": tensor_records,
        },
        "disjointness": disjointness,
        "runtime": runtime,
        "vendor": {
            "commit": VENDOR_COMMIT,
            "data_utils_path": VENDOR_DATA_UTILS,
            "data_utils_sha256": source_identity["sha256"][VENDOR_DATA_UTILS],
        },
        "source_identity": source_identity,
    }
    metadata = {**metadata_body, "fingerprint": fingerprint(metadata_body)}
    metadata_path = root / METADATA_NAME
    atomic_write_json(metadata_path, metadata)
    complete = {
        "status": "complete",
        "outcome": "CALIBRATION_TENSORS_MATERIALIZED",
        "metadata_sha256": sha256_of_file(metadata_path),
        "tensors_sha256": sha256_of_file(tensors_path),
        "metadata_fingerprint": metadata["fingerprint"],
    }
    atomic_write_json(root / COMPLETE_NAME, complete)
    write_manifest(root)
    return validate_sealed_archive(
        root,
        repo=repo,
        parent_model=parent,
        runtime_lock_path=runtime_lock_path,
    )


def main():
    args = parse_args()
    metadata = materialize(args)
    print(f"Immutable v4 calibration tensors: seed={metadata['seed']} shape={TENSOR_SHAPE}")


if __name__ == "__main__":
    main()
