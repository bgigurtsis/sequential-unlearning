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
EXPECTED_BOS_TOKEN_ID = 2
EXPECTED_UNK_TOKEN_ID = 3
EXPECTED_TOKENIZER_CLASS = "GemmaTokenizer"
EXPECTED_POST_PROCESSOR_REPR = (
    'TemplateProcessing(single=[SpecialToken(id="<bos>", type_id=0), '
    'Sequence(id=A, type_id=0)], pair=[SpecialToken(id="<bos>", type_id=0), '
    'Sequence(id=A, type_id=0), SpecialToken(id="<bos>", type_id=1), '
    'Sequence(id=B, type_id=1)], special_tokens={"<bos>":SpecialToken('
    'id="<bos>", ids=[2], tokens=["<bos>"])})'
)
EXPECTED_POST_PROCESSOR_STATE = (
    '{"type":"TemplateProcessing","single":[{"SpecialToken":{"id":"<bos>",'
    '"type_id":0}},{"Sequence":{"id":"A","type_id":0}}],"pair":['
    '{"SpecialToken":{"id":"<bos>","type_id":0}},{"Sequence":{"id":"A",'
    '"type_id":0}},{"SpecialToken":{"id":"<bos>","type_id":1}},'
    '{"Sequence":{"id":"B","type_id":1}}],"special_tokens":{"<bos>":'
    '{"id":"<bos>","ids":[2],"tokens":["<bos>"]}}}'
)
EXPECTED_POST_PROCESSOR_SHA256 = hashlib.sha256(
    EXPECTED_POST_PROCESSOR_STATE.encode("utf-8")
).hexdigest()
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
    "implementation": (
        "pinned_vendor_slicegpt.data_utils.prepare_dataloader through documented "
        "project lossless-token-preservation proxy"
    ),
    "dataset_filter": "len(first_column_value)>0",
    "derived_filter_cache": (
        "datasets caching disabled; exact Arrow copy loaded in a fresh private temporary directory"
    ),
    "fixed_length_construction": (
        "torch.randint contiguous unused-row spans; tokenizer.tokenize; separator newline-newline; "
        "truncate token list to 2048; tokenizer.convert_tokens_to_string"
    ),
    "second_tokenization": (
        "lossless sealed-placeholder proxy: verify exact backend TemplateProcessing "
        "type/representation/state and special counts; convert exact 2048 tokens to "
        "IDs; construct [BOS,*token_ids] directly; truncate to 2048; all-one mask"
    ),
    "lossless_roundtrip_correction": "V4_SLICEGPT_PROTOCOL pre-data addendum v1",
    "sampler": (
        "SubsetRandomSampler(torch.randperm(len(ds))[:128]); DataLoader base-seed "
        "consumption; lazy iterator randperm maps through the first permutation"
    ),
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
FROZEN_SAMPLER_ORDERS = {
    0: (68,3,125,106,27,25,108,53,65,72,74,62,59,123,21,31,58,107,46,114,121,41,99,66,44,28,11,49,69,89,38,67,95,40,109,97,47,63,52,111,84,93,57,15,34,127,122,104,117,39,23,86,50,102,29,103,119,7,75,94,37,73,118,85,100,90,77,6,91,101,4,9,116,19,16,70,78,42,51,48,124,5,113,76,14,45,32,36,71,13,79,10,26,96,12,88,22,81,35,115,54,61,8,120,60,98,82,33,2,126,105,30,43,1,80,20,83,24,112,17,56,92,110,18,0,64,55,87),
    1: (75,124,71,105,87,86,36,49,17,53,68,127,100,50,85,16,126,113,119,60,116,52,19,104,125,98,77,35,47,62,34,88,54,44,80,91,9,42,45,66,79,31,83,58,28,55,61,122,84,46,24,99,73,11,89,95,111,4,74,110,14,107,20,92,15,106,21,22,103,72,10,69,38,90,3,108,41,0,27,32,13,118,8,65,25,123,29,96,78,43,59,12,57,114,2,121,81,117,56,23,39,30,120,1,63,93,102,115,97,40,5,48,76,26,109,51,7,67,112,101,64,37,6,33,82,94,70,18),
    2: (76,72,47,37,18,17,12,34,126,60,102,105,0,7,109,3,78,56,114,43,73,6,48,117,52,5,32,49,77,124,65,66,25,40,68,90,118,54,99,104,100,69,38,21,97,51,29,101,33,53,9,26,113,86,8,55,45,14,84,10,89,22,31,19,28,2,108,70,87,13,61,20,85,50,125,15,106,127,58,39,121,23,64,122,74,94,116,95,103,107,79,11,119,112,67,16,110,111,83,41,80,92,1,27,71,42,24,63,4,81,57,30,88,36,46,82,96,98,35,123,120,44,115,91,62,59,75,93),
    7: (50,10,21,93,2,94,12,31,121,0,111,9,27,88,39,118,3,60,125,66,117,34,65,78,32,72,105,33,71,64,115,24,56,79,75,55,4,86,73,53,77,123,8,82,62,61,28,43,11,120,47,101,22,80,112,57,96,6,91,19,15,98,90,20,122,126,113,37,13,102,42,106,95,17,108,26,63,40,25,70,81,52,7,107,46,84,83,69,54,1,35,76,48,114,74,85,36,23,45,127,44,41,116,87,110,51,38,68,104,97,124,59,119,16,30,92,5,58,89,29,99,18,49,14,67,103,109,100),
    11: (69,79,127,23,104,108,114,35,28,87,121,14,42,2,112,117,31,103,24,72,33,38,85,60,64,59,10,115,119,75,78,74,25,116,9,122,45,62,101,47,91,66,102,84,61,1,58,105,18,80,94,46,29,17,0,48,67,52,40,11,36,100,83,50,34,51,32,95,20,77,26,21,15,124,19,13,8,86,93,55,37,90,88,54,76,53,120,123,98,73,109,12,126,97,3,82,125,4,41,89,65,92,6,39,43,57,56,106,63,96,30,113,71,110,81,16,27,22,49,107,68,118,5,70,99,7,111,44),
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


FROZEN_SAMPLER_ORDER_SHA256 = {
    seed: fingerprint(list(order)) for seed, order in FROZEN_SAMPLER_ORDERS.items()
}


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


def validate_upstream_batch_contract(batch, batch_index, observed_rows):
    """Reject lossy vendor text round-trips before tensors reach ``torch.cat``."""
    if not isinstance(batch, dict) or set(batch) != {"input_ids", "attention_mask", "labels"}:
        raise RuntimeError("pinned upstream calibration batch schema changed")
    shapes = {}
    for name in ("input_ids", "attention_mask", "labels"):
        shape = getattr(batch[name], "shape", None)
        if shape is None:
            raise RuntimeError(f"pinned upstream calibration {name} has no tensor shape")
        shapes[name] = tuple(int(value) for value in shape)
    expected_rows = min(BATCH_SIZE, NSAMPLES - observed_rows)
    expected_shape = (expected_rows, SEQLEN)
    if any(shape != expected_shape for shape in shapes.values()):
        widths = {name: (shape[1] if len(shape) == 2 else None) for name, shape in shapes.items()}
        raise RuntimeError(
            "official SliceGPT fixed preprocessing is incompatible with the frozen "
            f"[128,2048] all-one contract at batch {batch_index}: expected {expected_shape}, "
            f"observed shapes={shapes}, widths={widths}. The pinned tokenize -> "
            "convert_tokens_to_string -> retokenize round-trip is lossy, while "
            "padding='longest' pads only to each batch maximum. No calibration archive "
            "was created; padding/appending or changing masks is forbidden."
        )
    return observed_rows + expected_rows


class LosslessVendorTokenizerProxy:
    """Preserve vendor-selected token lists across its lossy text round-trip."""

    PLACEHOLDER_PREFIX = "__PROBE2_V4_SLICEGPT_TOKEN_BLOCK_"

    def __init__(self, base_tokenizer, torch_module):
        self.base = base_tokenizer
        self.torch = torch_module
        self._blocks = {}
        self._uses = {}
        self._indices = {}
        self._consumption_order = []
        self.bos_token_id = getattr(base_tokenizer, "bos_token_id", None)
        self.unk_token_id = getattr(base_tokenizer, "unk_token_id", None)
        self.unk_token = getattr(base_tokenizer, "unk_token", None)
        if type(base_tokenizer).__name__ != EXPECTED_TOKENIZER_CLASS:
            raise RuntimeError("pinned calibration tokenizer class changed")
        if type(self.bos_token_id) is not int or self.bos_token_id < 0:
            raise RuntimeError("lossless vendor correction requires one exact BOS token ID")
        if type(self.unk_token_id) is not int or self.unk_token_id < 0 or not isinstance(self.unk_token, str):
            raise RuntimeError("lossless vendor correction requires an explicit UNK token policy")
        if self.bos_token_id != EXPECTED_BOS_TOKEN_ID or self.unk_token_id != EXPECTED_UNK_TOKEN_ID:
            raise RuntimeError("pinned Gemma BOS/UNK token IDs changed")
        backend = getattr(base_tokenizer, "backend_tokenizer", None)
        post_processor = getattr(backend, "post_processor", None)
        if post_processor is None:
            raise RuntimeError("pinned backend TemplateProcessing is absent")
        try:
            post_state = post_processor.__getstate__()
        except Exception as error:
            raise RuntimeError("pinned backend TemplateProcessing is absent") from error
        if (
            type(post_processor).__name__ != "TemplateProcessing"
            or repr(post_processor) != EXPECTED_POST_PROCESSOR_REPR
            or not isinstance(post_state, bytes)
            or post_state.decode("utf-8", errors="strict") != EXPECTED_POST_PROCESSOR_STATE
            or hashlib.sha256(post_state).hexdigest() != EXPECTED_POST_PROCESSOR_SHA256
            or type(base_tokenizer.num_special_tokens_to_add(pair=False)) is not int
            or base_tokenizer.num_special_tokens_to_add(pair=False) != 1
            or type(base_tokenizer.num_special_tokens_to_add(pair=True)) is not int
            or base_tokenizer.num_special_tokens_to_add(pair=True) != 2
        ):
            raise RuntimeError("pinned backend TemplateProcessing representation changed")
        self.backend_post_processor_sha256 = hashlib.sha256(post_state).hexdigest()

    def __getattr__(self, name):
        return getattr(self.base, name)

    def __len__(self):
        return len(self.base)

    def tokenize(self, text):
        tokens = self.base.tokenize(text)
        if not isinstance(tokens, list) or any(not isinstance(token, str) for token in tokens):
            raise RuntimeError("base tokenizer returned a noncanonical token list")
        return tokens

    def convert_tokens_to_string(self, tokens):
        if (
            not isinstance(tokens, list)
            or len(tokens) != SEQLEN
            or any(not isinstance(token, str) for token in tokens)
        ):
            raise RuntimeError(
                "lossless vendor correction requires the exact 2048-token pre-detokenization block"
            )
        index = len(self._blocks)
        token_hash = fingerprint(tokens)
        placeholder = f"{self.PLACEHOLDER_PREFIX}{index:03d}_{token_hash}__"
        if placeholder in self._blocks:
            raise RuntimeError("lossless vendor placeholder collision")
        self._blocks[placeholder] = tuple(tokens)
        self._uses[placeholder] = 0
        self._indices[placeholder] = index
        return placeholder

    def __call__(self, *args, **kwargs):
        expected_kwargs = {
            "padding": "longest",
            "max_length": SEQLEN,
            "truncation": True,
            "return_tensors": "pt",
        }
        if len(args) != 1 or kwargs != expected_kwargs:
            raise RuntimeError(
                "pinned vendor final tokenizer call changed; lossless correction refuses substitution"
            )
        placeholders = args[0]
        if not isinstance(placeholders, (list, tuple)) or not placeholders:
            raise RuntimeError("lossless vendor correction requires a nonempty placeholder batch")
        rows = []
        for placeholder in placeholders:
            if not isinstance(placeholder, str) or placeholder not in self._blocks:
                raise RuntimeError("unknown/substituted lossless vendor placeholder")
            if self._uses[placeholder] != 0:
                raise RuntimeError("lossless vendor placeholder was sampled more than once")
            tokens = list(self._blocks[placeholder])
            token_ids = self.base.convert_tokens_to_ids(tokens)
            if (
                not isinstance(token_ids, list)
                or len(token_ids) != SEQLEN
                or any(type(value) is not int or value < 0 for value in token_ids)
            ):
                raise RuntimeError("base tokenizer token-to-ID mapping changed or is not one-to-one")
            for token, token_id in zip(tokens, token_ids, strict=True):
                if token_id == self.unk_token_id and token != self.unk_token:
                    raise RuntimeError("base tokenizer mapped a non-UNK token to the UNK ID")
            recovered_tokens = self.base.convert_ids_to_tokens(token_ids)
            if recovered_tokens != tokens:
                raise RuntimeError("base tokenizer token-to-ID-to-token identity changed")
            if self.bos_token_id in token_ids:
                raise RuntimeError("pre-special calibration tokens unexpectedly contain BOS")
            # The pinned Transformers-5.14 GemmaTokenizer exposes no
            # build_inputs_with_special_tokens method.  Its exact verified
            # backend TemplateProcessing single sequence is [BOS, A].
            with_special = [self.bos_token_id, *token_ids]
            if (
                not isinstance(with_special, list)
                or len(with_special) != SEQLEN + 1
                or any(type(value) is not int or value < 0 for value in with_special)
                or with_special[0] != self.bos_token_id
                or with_special[1:] != token_ids
                or with_special.count(self.bos_token_id) != 1
            ):
                raise RuntimeError("base tokenizer must prepend exactly one BOS and no other special token")
            row = with_special[:SEQLEN]
            if len(row) != SEQLEN:
                raise RuntimeError("lossless vendor row did not remain exactly 2048 IDs")
            rows.append(row)
            self._uses[placeholder] += 1
            self._consumption_order.append(self._indices[placeholder])
        input_ids = self.torch.tensor(rows, dtype=self.torch.int64)
        attention_mask = self.torch.ones_like(input_ids, dtype=self.torch.int64)
        return {"input_ids": input_ids, "attention_mask": attention_mask}

    def assert_complete(self, expected_blocks=NSAMPLES, expected_order=None):
        if (
            len(self._blocks) != expected_blocks
            or set(self._uses.values()) != {1}
            or sorted(self._consumption_order) != list(range(expected_blocks))
            or (expected_order is not None and self._consumption_order != list(expected_order))
        ):
            raise RuntimeError(
                "lossless vendor correction did not register/consume each block exactly once "
                "in the pinned SubsetRandomSampler order"
            )
        return tuple(self._consumption_order)


def expected_vendor_sampler_order(torch, seed):
    if type(seed) is not int or seed not in FROZEN_SAMPLER_ORDERS:
        raise RuntimeError("exact integer calibration seed is required for sampler order")
    # Reproduce the actual DataLoader, rather than assuming two randperm calls:
    # DataLoader consumes its own base seed before the lazy sampler iterator.
    state = torch.random.get_rng_state()
    try:
        torch.manual_seed(seed)
        sampler = torch.utils.data.SubsetRandomSampler(torch.randperm(NSAMPLES)[:NSAMPLES])
        loader = torch.utils.data.DataLoader(
            list(range(NSAMPLES)), batch_size=BATCH_SIZE, sampler=sampler
        )
        order = []
        for batch in loader:
            order.extend(int(value) for value in batch.tolist())
    finally:
        torch.random.set_rng_state(state)
    if len(order) != NSAMPLES or sorted(order) != list(range(NSAMPLES)):
        raise RuntimeError("could not reproduce pinned SubsetRandomSampler order")
    if order != list(FROZEN_SAMPLER_ORDERS[seed]):
        raise RuntimeError("live Torch DataLoader sampler order changed from the frozen order")
    return order


def load_verified_prepare_dataloader(repo, expected_sha256):
    """Execute the exact vendor source without importing its package initializer."""
    _require_hash(expected_sha256, "vendored data_utils source")
    contaminated = sorted(
        name for name in sys.modules if name == "slicegpt" or name.startswith("slicegpt.")
    )
    if contaminated:
        raise RuntimeError(f"preloaded slicegpt modules are forbidden: {contaminated}")
    expected_path = reject_symlink_components(
        Path(repo) / VENDOR_DATA_UTILS, "vendored SliceGPT data_utils"
    )
    if not expected_path.is_file():
        raise RuntimeError("recorded vendored SliceGPT data_utils is missing")
    source = expected_path.read_bytes()
    if hashlib.sha256(source).hexdigest() != expected_sha256:
        raise RuntimeError("vendored SliceGPT data_utils source hash changed before execution")
    module_name = f"_probe2_v4_slicegpt_data_utils_{expected_sha256}"
    if module_name in sys.modules:
        raise RuntimeError("preloaded sealed vendor module name is forbidden")
    spec = importlib.util.spec_from_file_location(module_name, expected_path)
    if (
        spec is None
        or spec.loader is None
        or Path(str(spec.origin)).resolve() != expected_path
        or spec.name != module_name
        or type(spec.loader) is not importlib.machinery.SourceFileLoader
        or spec.loader.name != module_name
        or Path(spec.loader.path).resolve() != expected_path
    ):
        raise RuntimeError("vendored SliceGPT direct-module specification was substituted")
    module = importlib.util.module_from_spec(spec)
    original_sys_path = tuple(sys.path)
    original_slicegpt_modules = {
        name: value
        for name, value in sys.modules.items()
        if name == "slicegpt" or name.startswith("slicegpt.")
    }
    contamination_error = None
    try:
        # Compile the already hash-verified bytes.  SourceFileLoader reopening
        # the path would create an avoidable check/use race.
        exec(compile(source, str(expected_path), "exec"), module.__dict__)
    finally:
        current_slicegpt_modules = {
            name: value
            for name, value in sys.modules.items()
            if name == "slicegpt" or name.startswith("slicegpt.")
        }
        if tuple(sys.path) != original_sys_path:
            contamination_error = "vendored data_utils modified sys.path"
        elif current_slicegpt_modules != original_slicegpt_modules:
            contamination_error = "vendored data_utils imported or substituted its package"
        sys.path[:] = original_sys_path
        for name in set(current_slicegpt_modules) - set(original_slicegpt_modules):
            sys.modules.pop(name, None)
        for name, value in original_slicegpt_modules.items():
            sys.modules[name] = value
        sys.modules.pop(module_name, None)
    if contamination_error is not None:
        raise RuntimeError(contamination_error)
    if (
        Path(str(module.__file__)).resolve() != expected_path
        or hashlib.sha256(expected_path.read_bytes()).hexdigest() != expected_sha256
        or getattr(module, "__package__", None) not in {"", None}
        or not callable(getattr(module, "prepare_dataloader", None))
        or module.prepare_dataloader.__module__ != module_name
    ):
        raise RuntimeError("executed SliceGPT data_utils is not the recorded direct source")
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


def parse_safetensors(path, expected_seed=None, expected_bos_token_id=None):
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
                unpacked = [value for (value,) in struct.iter_unpack("<q", raw)]
                minimum, maximum = None, None
                for value in unpacked:
                    minimum = value if minimum is None else min(minimum, value)
                    maximum = value if maximum is None else max(maximum, value)
                if minimum is None or minimum < 0:
                    raise RuntimeError("calibration input_ids contain a negative or empty value")
                if (
                    type(expected_bos_token_id) is not int
                    or expected_bos_token_id != EXPECTED_BOS_TOKEN_ID
                ):
                    raise RuntimeError("exact recorded Gemma BOS token ID is required")
                bos_at_zero = all(
                    unpacked[row * SEQLEN] == expected_bos_token_id
                    for row in range(NSAMPLES)
                )
                exactly_one_bos = all(
                    unpacked[row * SEQLEN : (row + 1) * SEQLEN].count(expected_bos_token_id)
                    == 1
                    for row in range(NSAMPLES)
                )
                if not bos_at_zero or not exactly_one_bos:
                    raise RuntimeError(
                        "calibration input_ids must contain exactly one recorded BOS at column zero per row"
                    )
                all_one = False
            records[name] = {
                "dtype": TENSOR_DTYPE,
                "shape": TENSOR_SHAPE,
                "byte_sha256": hashlib.sha256(raw).hexdigest(),
                "minimum": minimum,
                "maximum": maximum,
                "all_one": all_one,
                "bos_token_id": (
                    expected_bos_token_id if name == "input_ids" else None
                ),
                "all_rows_bos_at_column_zero": (
                    bos_at_zero if name == "input_ids" else None
                ),
                "all_rows_exactly_one_bos": (
                    exactly_one_bos if name == "input_ids" else None
                ),
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
        "tensors", "disjointness", "sampler_order", "runtime", "vendor",
        "source_identity", "fingerprint",
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
        or type(metadata.get("seed")) is not int
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
            "padding_side", "bos_token_id", "unk_token_id", "unk_policy",
            "lossless_proxy", "backend_post_processor_repr",
            "backend_post_processor_sha256", "num_special_tokens_single",
            "num_special_tokens_pair", "support_file_sha256", "fingerprint",
        }
        or type(tokenizer.get("length")) is not int
        or type(tokenizer.get("vocab_size")) is not int
        or tokenizer.get("class") != EXPECTED_TOKENIZER_CLASS
        or tokenizer["length"] <= 0
        or tokenizer["vocab_size"] <= 0
        or not isinstance(tokenizer.get("special_tokens_map"), dict)
        or "bos_token" not in tokenizer["special_tokens_map"]
        or "unk_token" not in tokenizer["special_tokens_map"]
        or tokenizer.get("padding_side") not in {"left", "right"}
        or type(tokenizer.get("bos_token_id")) is not int
        or tokenizer["bos_token_id"] != EXPECTED_BOS_TOKEN_ID
        or tokenizer["bos_token_id"] >= tokenizer["length"]
        or type(tokenizer.get("unk_token_id")) is not int
        or tokenizer["unk_token_id"] != EXPECTED_UNK_TOKEN_ID
        or tokenizer["unk_token_id"] >= tokenizer["length"]
        or tokenizer.get("unk_policy") != "reject any non-UNK token mapped to unk_token_id"
        or tokenizer.get("lossless_proxy")
        != "documented project adapter; not unchanged upstream retokenization"
        or tokenizer.get("backend_post_processor_repr") != EXPECTED_POST_PROCESSOR_REPR
        or tokenizer.get("backend_post_processor_sha256")
        != EXPECTED_POST_PROCESSOR_SHA256
        or type(tokenizer.get("num_special_tokens_single")) is not int
        or tokenizer["num_special_tokens_single"] != 1
        or type(tokenizer.get("num_special_tokens_pair")) is not int
        or tokenizer["num_special_tokens_pair"] != 2
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
    tensor_records = parse_safetensors(
        tensors_path,
        expected_seed=metadata.get("seed"),
        expected_bos_token_id=tokenizer["bos_token_id"],
    )
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
    sampler_order = metadata.get("sampler_order")
    if (
        not isinstance(sampler_order, dict)
        or set(sampler_order) != {"seed", "algorithm", "placeholder_indices", "sha256"}
        or sampler_order.get("seed") != metadata.get("seed")
        or type(sampler_order.get("seed")) is not int
        or sampler_order.get("algorithm") != PREPROCESSING["sampler"]
        or not isinstance(sampler_order.get("placeholder_indices"), list)
        or len(sampler_order["placeholder_indices"]) != NSAMPLES
        or any(type(value) is not int for value in sampler_order["placeholder_indices"])
        or sorted(sampler_order["placeholder_indices"]) != list(range(NSAMPLES))
        or sampler_order["placeholder_indices"]
        != list(FROZEN_SAMPLER_ORDERS[metadata["seed"]])
        or sampler_order.get("sha256")
        != FROZEN_SAMPLER_ORDER_SHA256[metadata["seed"]]
    ):
        raise RuntimeError("sealed calibration sampler order changed")
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

    base_tokenizer = AutoTokenizer.from_pretrained(parent, local_files_only=True)
    tokenizer = LosslessVendorTokenizerProxy(base_tokenizer, torch)
    ids, masks = [], []
    observed_rows = 0
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
        for batch_index, batch in enumerate(loader):
            observed_rows = validate_upstream_batch_contract(
                batch, batch_index, observed_rows
            )
            if not torch.equal(batch["labels"], batch["input_ids"]):
                raise RuntimeError("pinned upstream calibration labels/input identity changed")
            if not torch.all(batch["attention_mask"] == 1).item():
                raise RuntimeError(
                    "official SliceGPT fixed preprocessing produced padding; frozen all-one "
                    "attention masks cannot be repaired or relaxed"
                )
            ids.append(batch["input_ids"].to(dtype=torch.int64, device="cpu"))
            masks.append(batch["attention_mask"].to(dtype=torch.int64, device="cpu"))
    if observed_rows != NSAMPLES or len(ids) != NSAMPLES // BATCH_SIZE:
        raise RuntimeError(
            "official SliceGPT fixed preprocessing did not produce exactly 128 ordered rows "
            "in eight batches"
        )
    expected_order = expected_vendor_sampler_order(torch, args.seed)
    sampler_order = list(tokenizer.assert_complete(expected_order=expected_order))
    input_ids = torch.cat(ids, dim=0).contiguous()
    attention_mask = torch.cat(masks, dim=0).contiguous()
    if list(input_ids.shape) != TENSOR_SHAPE or list(attention_mask.shape) != TENSOR_SHAPE:
        raise RuntimeError("materialized calibration tensor shape changed")
    if not torch.all(attention_mask == 1).item():
        raise RuntimeError("materialized calibration attention mask is not all one")
    if not torch.all(input_ids[:, 0] == tokenizer.bos_token_id).item():
        raise RuntimeError("materialized calibration rows do not begin with the exact BOS token")
    if not torch.all((input_ids == tokenizer.bos_token_id).sum(dim=1) == 1).item():
        raise RuntimeError("materialized calibration rows do not contain exactly one BOS token")
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
    tensor_records = parse_safetensors(
        tensors_path,
        expected_seed=args.seed,
        expected_bos_token_id=tokenizer.bos_token_id,
    )
    tokenizer_body = {
        "source": str(parent),
        "class": type(base_tokenizer).__name__,
        "length": len(tokenizer),
        "vocab_size": base_tokenizer.vocab_size,
        "special_tokens_map": base_tokenizer.special_tokens_map,
        "padding_side": base_tokenizer.padding_side,
        "bos_token_id": tokenizer.bos_token_id,
        "unk_token_id": tokenizer.unk_token_id,
        "unk_policy": "reject any non-UNK token mapped to unk_token_id",
        "lossless_proxy": "documented project adapter; not unchanged upstream retokenization",
        "backend_post_processor_repr": EXPECTED_POST_PROCESSOR_REPR,
        "backend_post_processor_sha256": tokenizer.backend_post_processor_sha256,
        "num_special_tokens_single": 1,
        "num_special_tokens_pair": 2,
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
        "sampler_order": {
            "seed": args.seed,
            "algorithm": PREPROCESSING["sampler"],
            "placeholder_indices": sampler_order,
            "sha256": fingerprint(sampler_order),
        },
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
