#!/usr/bin/env python3
"""Fail-closed runtime and provenance qualifier for Probe 2 v4.

This program consumes two *pre-existing* canonical JSON files:

* a runtime lock containing the exact expected live observation; and
* a provenance specification containing committed source, vendor, calibration,
  parent-model and clean-ruler identities.

It never creates or updates either input.  On success it creates one immutable,
self-verifying qualification directory.  On any mismatch it raises before
creating that directory.  An existing directory is validation-only: it is
never repaired or replaced.

The public ``qualify`` function accepts an explicit observation so the
fail-closed logic can be tested without importing torch or touching a GPU.
The command-line entry point captures the live runtime (metadata queries only).
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import importlib.util
import json
import math
import os
import platform
import re
import stat
import subprocess
import sys
from pathlib import Path
from typing import Any, Iterable, Mapping


PROTOCOL_VERSION = "slicegpt_v4_runtime_provenance_spec_v1"
RUNTIME_VERSION = "slicegpt_v4_runtime_observation_v1"
ARCHIVE_VERSION = "slicegpt_v4_runtime_qualification_v1"

UPSTREAM_COMMIT = "6b12cdee6ad51791d7c776b3a046bc408b9e77e9"
UPSTREAM_TREE = "b58f7a03ed03a968d6b763b29b100f2683e6dfd2"
VENDOR_MANIFEST_SHA256 = (
    "ba3ee5f9788e4a5e937eabcac6beaeb3aef31746952b4c3ddca452b22fedc2a4"
)
CALIBRATION_ARROW_SHA256 = (
    "57947bc7b58df4b19662c0609cc30651bc84328dab5fd588860b752072911789"
)
CALIBRATION_METADATA_SHA256 = (
    "47ce56e8a2ca0183a37850cbce75cec29f64a1f61da978386c2a0598da4a6f66"
)

PACKAGE_VERSIONS = {
    "accelerate": "1.14.0",
    "datasets": "5.0.0",
    "numpy": "2.5.1",
    "peft": "0.19.1",
    "pyarrow": "25.0.0",
    "safetensors": "0.8.0",
    "tokenizers": "0.22.2",
    # Distribution metadata omits the local CUDA build suffix; the independent
    # torch.__version__ field below remains exactly 2.13.0+cu130.
    "torch": "2.13.0",
    "transformers": "5.14.1",
}

MANDATORY_COMMITTED_SOURCES = frozenset(
    {
        "docs/V4_SLICEGPT_PROTOCOL.md",
        "scripts/qualify_slicegpt_runtime_v4.py",
        "scripts/run_slicegpt_pilot_v4.py",
        "scripts/slicegpt_gemma3_math_v4.py",
        "scripts/check_slicegpt_gemma3_zero_slice.py",
        "scripts/verify_transformer_compression_vendor.py",
        "scripts/materialize_slicegpt_calibration_v4.py",
        "scripts/test_materialize_slicegpt_calibration_v4.py",
        "vendor/TransformerCompression/UPSTREAM.md",
        "vendor/TransformerCompression/SOURCE_SHA256SUMS",
        "vendor/TransformerCompression/source/src/slicegpt/data_utils.py",
    }
)

MATERIALIZER_PATH = "scripts/materialize_slicegpt_calibration_v4.py"
CALIBRATION_SEEDS = (0, 1, 2, 7, 11)
PROTECTED_PROMPT_PATHS = (
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

EXECUTABLE_VENDOR_PATHS = frozenset(
    {
        "build_and_test.sh",
        "experiments/run_benchmark.py",
        "experiments/run_slicegpt.py",
        "src/slicegpt/data_utils.py",
        "src/slicegpt/hf_utils.py",
        "test.sh",
    }
)

ARCHIVE_MEMBERS = frozenset(
    {
        "runtime_lock.json",
        "provenance_spec.json",
        "runtime_observation.json",
        "qualification.json",
        "qualifier_source.py",
        "COMPLETE.json",
        "MANIFEST.sha256",
    }
)

HEX40 = re.compile(r"[0-9a-f]{40}\Z")
HEX64 = re.compile(r"[0-9a-f]{64}\Z")


class QualificationError(RuntimeError):
    """The v4 runtime/provenance contract was not satisfied."""


def _fail(message: str) -> None:
    raise QualificationError(message)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_json_bytes(value: Any) -> bytes:
    _validate_json_value(value, "JSON")
    return (
        json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            indent=2,
            separators=(",", ": "),
        )
        + "\n"
    ).encode("utf-8")


def _validate_json_value(value: Any, label: str) -> None:
    if value is None or isinstance(value, (str, bool, int)):
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            _fail(f"{label}: non-finite number")
        # Runtime/provenance identities have no legitimate binary floats.  An
        # outright ban also removes 1/1.0 and exponent-spelling aliases.
        _fail(f"{label}: floating-point numbers are forbidden")
    if isinstance(value, list):
        for index, item in enumerate(value):
            _validate_json_value(item, f"{label}[{index}]")
        return
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                _fail(f"{label}: non-string object key")
            _validate_json_value(item, f"{label}.{key}")
        return
    _fail(f"{label}: unsupported JSON type {type(value).__name__}")


def _object_without_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            _fail(f"duplicate JSON key: {key!r}")
        result[key] = value
    return result


def load_canonical_json(path: Path) -> Any:
    try:
        raw = path.read_bytes()
    except OSError as exc:
        _fail(f"cannot read {path}: {exc}")
    try:
        text = raw.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        _fail(f"{path}: invalid UTF-8: {exc}")
    if text.startswith("\ufeff"):
        _fail(f"{path}: UTF-8 BOM is forbidden")

    def reject_constant(value: str) -> Any:
        _fail(f"{path}: non-finite JSON constant {value}")

    try:
        value = json.loads(
            text,
            object_pairs_hook=_object_without_duplicates,
            parse_constant=reject_constant,
        )
    except QualificationError:
        raise
    except (json.JSONDecodeError, ValueError) as exc:
        _fail(f"{path}: invalid JSON: {exc}")
    _validate_json_value(value, str(path))
    if raw != canonical_json_bytes(value):
        _fail(f"{path}: JSON is not in the one permitted canonical encoding")
    return value


def _exact_keys(value: Any, keys: Iterable[str], label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        _fail(f"{label}: expected object")
    expected = set(keys)
    actual = set(value)
    if actual != expected:
        _fail(
            f"{label}: schema mismatch; missing={sorted(expected-actual)}, "
            f"extra={sorted(actual-expected)}"
        )
    return value


def _require_string(value: Any, label: str, *, nonempty: bool = True) -> str:
    if not isinstance(value, str) or (nonempty and not value):
        _fail(f"{label}: expected {'nonempty ' if nonempty else ''}string")
    return value


def _require_hash(value: Any, label: str) -> str:
    text = _require_string(value, label)
    if not HEX64.fullmatch(text):
        _fail(f"{label}: expected lowercase SHA-256")
    return text


def _require_commit(value: Any, label: str) -> str:
    text = _require_string(value, label)
    if not HEX40.fullmatch(text):
        _fail(f"{label}: expected lowercase Git object id")
    return text


def _canonical_relative(value: Any, label: str) -> str:
    text = _require_string(value, label)
    if "\\" in text or text.startswith("/") or re.match(r"^[A-Za-z]:", text):
        _fail(f"{label}: path must be canonical POSIX relative")
    parts = text.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        _fail(f"{label}: aliased path is forbidden")
    return text


def _is_linklike(path: Path) -> bool:
    try:
        metadata = path.lstat()
    except (FileNotFoundError, OSError):
        return False
    if path.is_symlink() or (hasattr(path, "is_junction") and path.is_junction()):
        return True
    attributes = getattr(metadata, "st_file_attributes", 0)
    return bool(attributes & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0))


def _lexical_absolute(path: Path) -> Path:
    return Path(os.path.abspath(path))


def _reject_lexical_alias_syntax(path: Path, label: str) -> None:
    if any(part in {".", ".."} for part in path.parts):
        _fail(f"{label}: dot-segment path aliases are forbidden")


def _reject_linklike_ancestors(path: Path, label: str, *, include_leaf: bool = True) -> None:
    current = _lexical_absolute(path if include_leaf else path.parent)
    while True:
        if _is_linklike(current):
            _fail(f"{label}: symlink/junction/reparse component is forbidden: {current}")
        parent = current.parent
        if parent == current:
            break
        current = parent


def _resolve_declared(root: Path, value: Any, label: str) -> Path:
    text = _require_string(value, label)
    if "\\" in text:
        _fail(f"{label}: backslash path alias is forbidden")
    raw_parts = text.split("/")
    # A leading empty component is the one legitimate POSIX absolute marker;
    # all other empty/dot components are aliases.
    checked_parts = raw_parts[1:] if text.startswith("/") else raw_parts
    if any(part in {"", ".", ".."} for part in checked_parts):
        _fail(f"{label}: aliased path is forbidden")
    candidate = Path(text)
    if not candidate.is_absolute():
        _canonical_relative(text, label)
        candidate = root / candidate
    _reject_linklike_ancestors(candidate, label)
    return _lexical_absolute(candidate)


def _require_regular(path: Path, label: str) -> None:
    _reject_linklike_ancestors(path, label)
    if not path.exists() or not path.is_file() or _is_linklike(path):
        _fail(f"{label}: missing/non-regular/symlink file: {path}")


def _verify_hash(path: Path, expected: Any, label: str) -> str:
    _require_regular(path, label)
    wanted = _require_hash(expected, f"{label}.sha256")
    actual = sha256_file(path)
    if actual != wanted:
        _fail(f"{label}: SHA-256 mismatch: expected {wanted}, got {actual}")
    return actual


def _run_git(repo: Path, args: list[str], *, binary: bool = False) -> str | bytes:
    try:
        completed = subprocess.run(
            ["git", "-C", str(repo), *args],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        detail = getattr(exc, "stderr", b"")
        _fail(f"git {' '.join(args)} failed: {detail.decode(errors='replace').strip()}")
    return completed.stdout if binary else completed.stdout.decode("utf-8").strip()


def _fingerprint(value: Any) -> str:
    _validate_json_value(value, "fingerprint payload")
    raw = json.dumps(
        value, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return sha256_bytes(raw)


def validate_runtime_observation(value: Any) -> dict[str, Any]:
    obs = _exact_keys(
        value,
        ["version", "python", "packages", "platform", "torch", "cuda", "determinism"],
        "runtime observation",
    )
    if obs["version"] != RUNTIME_VERSION:
        _fail("runtime observation: wrong version")

    python = _exact_keys(
        obs["python"], ["version", "implementation", "executable", "executable_sha256"], "python"
    )
    if python["version"] != "3.12.3" or python["implementation"] != "CPython":
        _fail("python: protocol requires CPython 3.12.3")
    _require_string(python["executable"], "python.executable")
    _require_hash(python["executable_sha256"], "python.executable_sha256")

    packages = _exact_keys(obs["packages"], PACKAGE_VERSIONS, "packages")
    if packages != PACKAGE_VERSIONS:
        _fail(f"packages: expected exact protocol versions {PACKAGE_VERSIONS!r}")

    platform_obj = _exact_keys(
        obs["platform"], ["system", "release", "version", "machine"], "platform"
    )
    for key, item in platform_obj.items():
        _require_string(item, f"platform.{key}")

    torch = _exact_keys(
        obs["torch"],
        ["version", "git_version", "config_sha256", "cuda_runtime", "cudnn_version"],
        "torch",
    )
    if torch["version"] != "2.13.0+cu130" or torch["cuda_runtime"] != "13.0":
        _fail("torch: protocol requires 2.13.0+cu130 with CUDA runtime 13.0")
    _require_string(torch["git_version"], "torch.git_version")
    _require_hash(torch["config_sha256"], "torch.config_sha256")
    if isinstance(torch["cudnn_version"], bool) or not isinstance(torch["cudnn_version"], int) or torch["cudnn_version"] <= 0:
        _fail("torch.cudnn_version: expected positive integer")

    cuda = _exact_keys(
        obs["cuda"],
        ["available", "device_count", "current_device", "driver_version", "gpu"],
        "cuda",
    )
    if (
        cuda["available"] is not True
        or type(cuda["device_count"]) is not int
        or cuda["device_count"] != 1
        or type(cuda["current_device"]) is not int
        or cuda["current_device"] != 0
    ):
        _fail("cuda: qualifier requires exactly one available selected device")
    if cuda["driver_version"] != "595.71.05":
        _fail("cuda: protocol requires NVIDIA driver 595.71.05")
    gpu = _exact_keys(cuda["gpu"], ["name", "total_memory_bytes", "compute_capability"], "cuda.gpu")
    if gpu["name"] != "NVIDIA L4":
        _fail("cuda.gpu: validated protocol host is NVIDIA L4")
    if isinstance(gpu["total_memory_bytes"], bool) or not isinstance(gpu["total_memory_bytes"], int) or gpu["total_memory_bytes"] <= 0:
        _fail("cuda.gpu.total_memory_bytes: expected positive integer")
    if (
        not isinstance(gpu["compute_capability"], list)
        or len(gpu["compute_capability"]) != 2
        or any(type(item) is not int for item in gpu["compute_capability"])
        or gpu["compute_capability"] != [8, 9]
    ):
        _fail("cuda.gpu: NVIDIA L4 compute capability must be [8,9]")

    determinism = _exact_keys(
        obs["determinism"],
        [
            "deterministic_algorithms",
            "cuda_matmul_allow_tf32",
            "cudnn_allow_tf32",
            "cublas_workspace_config",
        ],
        "determinism",
    )
    expected_det = {
        "deterministic_algorithms": True,
        "cuda_matmul_allow_tf32": False,
        "cudnn_allow_tf32": False,
        "cublas_workspace_config": ":4096:8",
    }
    if (
        determinism["deterministic_algorithms"] is not True
        or determinism["cuda_matmul_allow_tf32"] is not False
        or determinism["cudnn_allow_tf32"] is not False
        or determinism != expected_det
    ):
        _fail(f"determinism: expected exact contract {expected_det!r}")
    return obs


def capture_live_runtime() -> dict[str, Any]:
    """Capture metadata only; no tensor allocation or kernel is launched."""
    if os.environ.get("CUBLAS_WORKSPACE_CONFIG") != ":4096:8":
        _fail("CUBLAS_WORKSPACE_CONFIG must be :4096:8 before Python starts")
    try:
        import torch  # type: ignore
    except Exception as exc:  # pragma: no cover - host-dependent production path
        _fail(f"cannot import torch: {exc}")

    # Enforce before any experiment work.  This is runtime state configuration,
    # not a GPU operation.
    torch.use_deterministic_algorithms(True)
    torch.backends.cuda.matmul.allow_tf32 = False
    torch.backends.cudnn.allow_tf32 = False

    executable = Path(sys.executable).resolve()
    _require_regular(executable, "python executable")
    packages: dict[str, str] = {}
    for name in PACKAGE_VERSIONS:
        try:
            packages[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            _fail(f"required package is not installed: {name}")

    try:
        driver_lines = subprocess.run(
            ["nvidia-smi", "--query-gpu=driver_version", "--format=csv,noheader"],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        ).stdout.splitlines()
    except (OSError, subprocess.CalledProcessError) as exc:
        _fail(f"cannot query NVIDIA driver: {exc}")
    drivers = {line.strip() for line in driver_lines if line.strip()}
    if len(drivers) != 1:
        _fail(f"expected one unambiguous NVIDIA driver version, got {sorted(drivers)}")

    if not torch.cuda.is_available() or torch.cuda.device_count() != 1:
        _fail("exactly one CUDA device must be available")
    index = torch.cuda.current_device()
    properties = torch.cuda.get_device_properties(index)
    torch_config = torch.__config__.show().encode("utf-8")
    value = {
        "version": RUNTIME_VERSION,
        "python": {
            "version": platform.python_version(),
            "implementation": platform.python_implementation(),
            "executable": executable.as_posix(),
            "executable_sha256": sha256_file(executable),
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
            "config_sha256": sha256_bytes(torch_config),
            "cuda_runtime": str(torch.version.cuda),
            "cudnn_version": int(torch.backends.cudnn.version()),
        },
        "cuda": {
            "available": bool(torch.cuda.is_available()),
            "device_count": int(torch.cuda.device_count()),
            "current_device": int(index),
            "driver_version": next(iter(drivers)),
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
    return validate_runtime_observation(value)


def _parse_sha_manifest(path: Path, label: str) -> dict[str, str]:
    _require_regular(path, label)
    try:
        raw = path.read_bytes()
        text = raw.decode("utf-8", errors="strict")
    except (OSError, UnicodeDecodeError) as exc:
        _fail(f"{label}: cannot decode manifest: {exc}")
    if b"\r" in raw or not raw.endswith(b"\n"):
        _fail(f"{label}: manifest must use LF and end with newline")
    result: dict[str, str] = {}
    prior = ""
    for number, line in enumerate(text.splitlines(), 1):
        match = re.fullmatch(r"([0-9a-f]{64})  (.+)", line)
        if not match:
            _fail(f"{label}:{number}: malformed manifest line")
        digest, member = match.groups()
        member = _canonical_relative(member, f"{label}:{number}.path")
        if member in result or (prior and member <= prior):
            _fail(f"{label}:{number}: duplicate or unsorted member")
        result[member] = digest
        prior = member
    if not result:
        _fail(f"{label}: empty manifest")
    return result


def _verify_manifest_tree(root: Path, manifest: Mapping[str, str], label: str, *, excluded: set[str]) -> None:
    if not root.exists() or not root.is_dir() or root.is_symlink():
        _fail(f"{label}: missing/non-directory/symlink root")
    actual: set[str] = set()
    for item in root.rglob("*"):
        if item.is_symlink():
            _fail(f"{label}: symlink forbidden: {item}")
        if item.is_file():
            relative = item.relative_to(root).as_posix()
            if relative not in excluded:
                actual.add(relative)
    expected = set(manifest)
    if actual != expected:
        _fail(f"{label}: membership mismatch; missing={sorted(expected-actual)}, extra={sorted(actual-expected)}")
    for relative, digest in manifest.items():
        _verify_hash(root / relative, digest, f"{label}/{relative}")


def _validate_hash_map(value: Any, label: str, *, nonempty: bool = True) -> dict[str, str]:
    if not isinstance(value, dict) or (nonempty and not value):
        _fail(f"{label}: expected {'nonempty ' if nonempty else ''}object")
    result: dict[str, str] = {}
    for path, digest in value.items():
        result[_canonical_relative(path, f"{label}.path")] = _require_hash(digest, f"{label}.{path}")
    return result


def _verify_exact_tree(root: Path, declared: Mapping[str, str], label: str) -> None:
    _reject_linklike_ancestors(root, label)
    if not root.is_dir() or _is_linklike(root):
        _fail(f"{label}: root is not a real directory")
    actual_files: set[str] = set()
    actual_directories: set[str] = set()
    for path in root.rglob("*"):
        relative = path.relative_to(root).as_posix()
        if _is_linklike(path):
            _fail(f"{label}: symlink/junction/reparse member is forbidden: {relative}")
        if path.is_file():
            actual_files.add(relative)
        elif path.is_dir():
            actual_directories.add(relative)
        else:
            _fail(f"{label}: unsupported filesystem member: {relative}")
    expected_files = set(declared)
    expected_directories: set[str] = set()
    for relative in expected_files:
        parts = relative.split("/")[:-1]
        for index in range(1, len(parts) + 1):
            expected_directories.add("/".join(parts[:index]))
    if actual_files != expected_files or actual_directories != expected_directories:
        _fail(
            f"{label}: exact recursive membership mismatch; "
            f"missing_files={sorted(expected_files-actual_files)}, "
            f"extra_files={sorted(actual_files-expected_files)}, "
            f"missing_dirs={sorted(expected_directories-actual_directories)}, "
            f"extra_dirs={sorted(actual_directories-expected_directories)}"
        )
    for relative, digest in declared.items():
        _verify_hash(root / relative, digest, f"{label}/{relative}")


def _load_verified_materializer(repo: Path, sources: Mapping[str, str]) -> Any:
    path = repo / MATERIALIZER_PATH
    _verify_hash(path, sources[MATERIALIZER_PATH], "calibration materializer source")
    module_name = "_slicegpt_v4_materializer_for_runtime_qualification"
    module_spec = importlib.util.spec_from_file_location(module_name, path)
    if module_spec is None or module_spec.loader is None:
        _fail("cannot load the verified calibration materializer validator")
    module = importlib.util.module_from_spec(module_spec)
    try:
        module_spec.loader.exec_module(module)
    except Exception as exc:
        _fail(f"cannot execute the verified calibration materializer validator: {exc}")
    required = {
        "validate_sealed_archive",
        "load_disjoint_prompts",
        "CALIBRATION_SEEDS",
        "DISJOINT_PROMPT_PATHS",
        "MANIFEST_NAME",
        "METADATA_NAME",
        "SAFETENSORS_NAME",
        "COMPLETE_NAME",
        "read_json",
        "canonical_json_bytes",
    }
    if any(not hasattr(module, name) for name in required):
        _fail("verified calibration materializer validator surface changed")
    if tuple(module.CALIBRATION_SEEDS) != CALIBRATION_SEEDS or tuple(module.DISJOINT_PROMPT_PATHS) != PROTECTED_PROMPT_PATHS:
        _fail("verified calibration materializer protocol constants changed")
    return module


def validate_provenance(
    repo: Path,
    spec: Any,
    runtime_lock_path: Path,
    provenance_spec_path: Path,
) -> tuple[dict[str, Any], str]:
    spec = _exact_keys(
        spec,
        ["version", "committed_sources", "runtime_lock", "vendor", "calibration", "parent_model", "clean_ruler"],
        "provenance spec",
    )
    if spec["version"] != PROTOCOL_VERSION:
        _fail("provenance spec: wrong version")
    repo_commit = _require_commit(_run_git(repo, ["rev-parse", "HEAD"]), "live repo commit")
    try:
        spec_relative = provenance_spec_path.relative_to(repo).as_posix()
    except ValueError:
        _fail("provenance spec must be a committed file inside the repository")
    _canonical_relative(spec_relative, "provenance spec path")
    committed_spec = _run_git(repo, ["show", f"{repo_commit}:{spec_relative}"], binary=True)
    if committed_spec != provenance_spec_path.read_bytes():
        _fail("provenance spec differs from its committed HEAD blob")

    sources = _validate_hash_map(spec["committed_sources"], "committed_sources")
    mandatory_sources = MANDATORY_COMMITTED_SOURCES | set(PROTECTED_PROMPT_PATHS)
    if not mandatory_sources.issubset(sources):
        _fail(f"committed_sources: missing mandatory paths {sorted(mandatory_sources-set(sources))}")
    for relative, digest in sources.items():
        path = repo / relative
        _verify_hash(path, digest, f"committed source {relative}")
        committed = _run_git(repo, ["show", f"{repo_commit}:{relative}"], binary=True)
        if sha256_bytes(committed) != digest:
            _fail(f"committed source {relative}: HEAD blob differs from declared/live bytes")

    runtime_ref = _exact_keys(spec["runtime_lock"], ["path", "sha256"], "runtime_lock reference")
    runtime_relative = _canonical_relative(runtime_ref["path"], "runtime_lock.path")
    declared_lock = _resolve_declared(repo, runtime_relative, "runtime_lock.path")
    if declared_lock != runtime_lock_path:
        _fail("runtime_lock.path: CLI path does not match provenance declaration")
    _verify_hash(declared_lock, runtime_ref["sha256"], "runtime lock")
    if sources.get(runtime_relative) != runtime_ref["sha256"]:
        _fail("runtime lock must be one of the committed source blobs")

    vendor = _exact_keys(
        spec["vendor"], ["commit", "tree", "root", "manifest_path", "manifest_sha256", "source_sha256"], "vendor"
    )
    if vendor["commit"] != UPSTREAM_COMMIT or vendor["tree"] != UPSTREAM_TREE:
        _fail("vendor: wrong pinned upstream revision/tree")
    vendor_root_rel = _canonical_relative(vendor["root"], "vendor.root")
    vendor_root = repo / vendor_root_rel
    manifest_rel = _canonical_relative(vendor["manifest_path"], "vendor.manifest_path")
    manifest_path = repo / manifest_rel
    if vendor["manifest_sha256"] != VENDOR_MANIFEST_SHA256:
        _fail("vendor: wrong frozen manifest SHA-256")
    _verify_hash(manifest_path, VENDOR_MANIFEST_SHA256, "vendor manifest")
    manifest = _parse_sha_manifest(manifest_path, "vendor manifest")
    declared_vendor = _validate_hash_map(vendor["source_sha256"], "vendor.source_sha256")
    if declared_vendor != manifest:
        _fail("vendor.source_sha256: declaration differs from frozen manifest")
    _verify_manifest_tree(vendor_root, manifest, "vendor source", excluded=set())

    stage = _run_git(repo, ["ls-files", "--stage", "--", vendor_root_rel], binary=False)
    staged_modes: dict[str, str] = {}
    for line in stage.splitlines():
        match = re.fullmatch(r"(100644|100755) [0-9a-f]{40} 0\t(.+)", line)
        if not match:
            _fail(f"vendor index: malformed/non-regular stage line {line!r}")
        mode, path = match.groups()
        prefix = vendor_root_rel + "/"
        if not path.startswith(prefix):
            _fail("vendor index: path escaped vendor root")
        staged_modes[path[len(prefix):]] = mode
    if set(staged_modes) != set(manifest):
        _fail("vendor index: membership mismatch")
    for relative, mode in staged_modes.items():
        expected = "100755" if relative in EXECUTABLE_VENDOR_PATHS else "100644"
        if mode != expected:
            _fail(f"vendor index: wrong mode for {relative}: {mode}, expected {expected}")

    parent = _exact_keys(spec["parent_model"], ["root", "weights_sha256", "support_sha256", "fingerprint"], "parent_model")
    parent_root = _resolve_declared(repo, parent["root"], "parent_model.root")
    weights = _validate_hash_map(parent["weights_sha256"], "parent_model.weights_sha256")
    support = _validate_hash_map(parent["support_sha256"], "parent_model.support_sha256")
    if set(weights) & set(support):
        _fail("parent_model: weight/support membership overlaps")
    _verify_exact_tree(parent_root, {**weights, **support}, "parent_model")
    parent_payload = {
        "source": str(parent_root),
        "weight_file_sha256": weights,
        "support_file_sha256": support,
    }
    if parent["fingerprint"] != _fingerprint(parent_payload):
        _fail("parent_model.fingerprint: mismatch")

    ruler = _exact_keys(spec["clean_ruler"], ["root", "files_sha256", "fingerprint"], "clean_ruler")
    ruler_root = _resolve_declared(repo, ruler["root"], "clean_ruler.root")
    ruler_files = _validate_hash_map(ruler["files_sha256"], "clean_ruler.files_sha256")
    _verify_exact_tree(ruler_root, ruler_files, "clean_ruler")
    if ruler["fingerprint"] != _fingerprint(ruler_files):
        _fail("clean_ruler.fingerprint: mismatch")

    calibration = _exact_keys(
        spec["calibration"],
        ["archives", "source_arrow", "source_metadata", "protected_prompt_sha256", "fingerprint"],
        "calibration",
    )
    protected = _validate_hash_map(calibration["protected_prompt_sha256"], "calibration.protected_prompt_sha256")
    if set(protected) != set(PROTECTED_PROMPT_PATHS):
        _fail("calibration protected-prompt source set changed")
    for relative, digest in protected.items():
        if sources.get(relative) != digest:
            _fail(f"calibration protected prompt is not the current committed source: {relative}")
        _verify_hash(repo / relative, digest, f"calibration protected prompt {relative}")
    for key, frozen_hash in (("source_arrow", CALIBRATION_ARROW_SHA256), ("source_metadata", CALIBRATION_METADATA_SHA256)):
        record = _exact_keys(calibration[key], ["path", "sha256"], f"calibration.{key}")
        if record["sha256"] != frozen_hash:
            _fail(f"calibration.{key}: wrong frozen source-cache hash")
        _verify_hash(_resolve_declared(repo, record["path"], f"calibration.{key}.path"), frozen_hash, f"calibration.{key}")

    archives = _exact_keys(calibration["archives"], [str(seed) for seed in CALIBRATION_SEEDS], "calibration.archives")
    materializer = _load_verified_materializer(repo, sources)
    try:
        prompts, live_prompt_hashes = materializer.load_disjoint_prompts(repo)
    except Exception as exc:
        _fail(f"cannot revalidate protected calibration prompt sources: {exc}")
    if live_prompt_hashes != protected or not prompts:
        _fail("calibration protected prompt identity/set is incomplete")
    roots: set[Path] = set()
    identities: set[str] = set()
    tensor_hashes: set[str] = set()
    for seed in CALIBRATION_SEEDS:
        key = str(seed)
        record = _exact_keys(
            archives[key],
            ["root", "manifest_sha256", "metadata_sha256", "tensors_sha256", "complete_sha256", "metadata_fingerprint"],
            f"calibration.archives.{key}",
        )
        archive_root = _resolve_declared(repo, record["root"], f"calibration.archives.{key}.root")
        try:
            relative_root = archive_root.relative_to(repo)
        except ValueError:
            _fail(f"calibration seed {seed}: archive must be under repository derisk")
        if not relative_root.parts or relative_root.parts[0].casefold() != "derisk":
            _fail(f"calibration seed {seed}: archive must be under repository derisk")
        if archive_root in roots:
            _fail("calibration seeds must use distinct sealed archives")
        roots.add(archive_root)
        expected_files = {
            materializer.MANIFEST_NAME: record["manifest_sha256"],
            materializer.METADATA_NAME: record["metadata_sha256"],
            materializer.SAFETENSORS_NAME: record["tensors_sha256"],
            materializer.COMPLETE_NAME: record["complete_sha256"],
        }
        for name, digest in expected_files.items():
            _verify_hash(archive_root / name, digest, f"calibration seed {seed}/{name}")
        for name in (materializer.METADATA_NAME, materializer.COMPLETE_NAME):
            json_path = archive_root / name
            try:
                parsed_json = materializer.read_json(json_path)
                canonical = materializer.canonical_json_bytes(parsed_json)
            except Exception as exc:
                _fail(f"calibration seed {seed}: invalid {name}: {exc}")
            if json_path.read_bytes() != canonical:
                _fail(f"calibration seed {seed}: {name} is not canonical, unaliased JSON")
        try:
            metadata = materializer.validate_sealed_archive(
                archive_root, repo=repo, parent_model=parent_root
            )
        except Exception as exc:
            _fail(f"calibration seed {seed}: semantic archive validation failed: {exc}")
        if metadata is None or metadata.get("seed") != seed:
            _fail(f"calibration seed {seed}: sealed archive seed mismatch")
        if metadata.get("fingerprint") != record["metadata_fingerprint"]:
            _fail(f"calibration seed {seed}: metadata fingerprint mismatch")
        if metadata.get("tensors", {}).get("sha256") != record["tensors_sha256"]:
            _fail(f"calibration seed {seed}: tensor archive identity mismatch")
        if metadata["runtime"]["runtime_lock_sha256"] != spec["runtime_lock"]["sha256"]:
            _fail(f"calibration seed {seed}: runtime lock identity mismatch")
        if metadata["dataset"]["source_cache_sha256"] != {
            "train_arrow": CALIBRATION_ARROW_SHA256,
            "dataset_metadata": CALIBRATION_METADATA_SHA256,
        }:
            _fail(f"calibration seed {seed}: source-cache identity mismatch")
        if metadata["disjointness"]["source_file_sha256"] != protected:
            _fail(f"calibration seed {seed}: protected prompt identity mismatch")
        if metadata["disjointness"]["protected_prompt_count"] != len(prompts):
            _fail(f"calibration seed {seed}: protected prompt count mismatch")
        if metadata["parent"]["weight_file_sha256"] != weights or metadata["parent"]["support_file_sha256"] != support:
            _fail(f"calibration seed {seed}: parent identity mismatch")
        if metadata["parent"]["fingerprint"] != parent["fingerprint"]:
            _fail(f"calibration seed {seed}: parent fingerprint mismatch")
        identity_fingerprint = _fingerprint(metadata["source_identity"])
        identities.add(identity_fingerprint)
        if any(metadata["source_identity"]["sha256"].get(path) != sources.get(path) for path in metadata["source_identity"]["sha256"]):
            _fail(f"calibration seed {seed}: materializer source differs from current committed source")
        tensor_hashes.add(metadata["tensors"]["sha256"])
    if len(identities) != 1:
        _fail("calibration seeds were materialized from different source identities")
    if len(tensor_hashes) != len(CALIBRATION_SEEDS):
        _fail("calibration seeds do not have five distinct tensor archives")
    calibration_payload = {
        "archives": archives,
        "protected_prompt_sha256": protected,
        "source_arrow": calibration["source_arrow"],
        "source_metadata": calibration["source_metadata"],
    }
    if calibration["fingerprint"] != _fingerprint(calibration_payload):
        _fail("calibration.fingerprint: mismatch")
    return spec, repo_commit


def _write_new(path: Path, data: bytes) -> None:
    if path.exists():
        _fail(f"refusing to replace existing archive member: {path}")
    with path.open("xb") as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())


def _manifest_bytes(hashes: Mapping[str, str]) -> bytes:
    return "".join(f"{hashes[name]}  {name}\n" for name in sorted(hashes)).encode("utf-8")


def validate_archive(root: Path) -> dict[str, Any]:
    if not root.exists() or not root.is_dir() or root.is_symlink():
        _fail("qualification archive missing/non-directory/symlink")
    actual: set[str] = set()
    for item in root.iterdir():
        if item.is_symlink() or not item.is_file():
            _fail(f"qualification archive contains non-regular member: {item.name}")
        actual.add(item.name)
    if actual != ARCHIVE_MEMBERS:
        _fail(f"qualification archive allowlist mismatch; missing={sorted(ARCHIVE_MEMBERS-actual)}, extra={sorted(actual-ARCHIVE_MEMBERS)}")
    manifest = _parse_sha_manifest(root / "MANIFEST.sha256", "qualification manifest")
    expected_members = ARCHIVE_MEMBERS - {"MANIFEST.sha256"}
    if set(manifest) != expected_members:
        _fail("qualification manifest membership mismatch")
    for member, digest in manifest.items():
        _verify_hash(root / member, digest, f"qualification archive/{member}")
    lock = load_canonical_json(root / "runtime_lock.json")
    observation = load_canonical_json(root / "runtime_observation.json")
    validate_runtime_observation(lock)
    validate_runtime_observation(observation)
    if lock != observation:
        _fail("qualification archive: runtime lock/observation mismatch")
    spec = load_canonical_json(root / "provenance_spec.json")
    _exact_keys(spec, ["version", "committed_sources", "runtime_lock", "vendor", "calibration", "parent_model", "clean_ruler"], "archived provenance spec")
    qualification = load_canonical_json(root / "qualification.json")
    qualification = _exact_keys(
        qualification,
        ["version", "status", "scope", "repo_commit", "runtime_lock_sha256", "provenance_spec_sha256", "runtime_observation_sha256", "qualifier_source_sha256", "vendor_commit", "vendor_tree", "calibration_fingerprint", "adapter_status", "probe2_verdict", "nonzero_slice_authorized", "identity_fingerprint"],
        "qualification",
    )
    if qualification["version"] != ARCHIVE_VERSION or qualification["status"] != "PASS_RUNTIME_PROVENANCE_QUALIFIED":
        _fail("qualification: wrong version/status")
    _require_commit(qualification["repo_commit"], "qualification.repo_commit")
    if qualification["scope"] != "RUNTIME_AND_PROVENANCE_ONLY" or qualification["adapter_status"] != "INCOMPLETE_PENDING_ADAPTER_GATES" or qualification["probe2_verdict"] is not None or qualification["nonzero_slice_authorized"] is not False:
        _fail("qualification: scope must not claim adapter/scientific completion")
    relations = {
        "repo_commit": qualification["repo_commit"],
        "runtime_lock_sha256": manifest["runtime_lock.json"],
        "provenance_spec_sha256": manifest["provenance_spec.json"],
        "runtime_observation_sha256": manifest["runtime_observation.json"],
        "qualifier_source_sha256": manifest["qualifier_source.py"],
        "vendor_commit": spec["vendor"]["commit"],
        "vendor_tree": spec["vendor"]["tree"],
        "calibration_fingerprint": spec["calibration"]["fingerprint"],
    }
    for key, expected in relations.items():
        if qualification[key] != expected:
            _fail(f"qualification.{key}: cross-file mismatch")
    fingerprint_payload = {key: qualification[key] for key in relations}
    if qualification["identity_fingerprint"] != _fingerprint(fingerprint_payload):
        _fail("qualification.identity_fingerprint: mismatch")
    complete = load_canonical_json(root / "COMPLETE.json")
    complete = _exact_keys(complete, ["version", "status", "qualification_sha256", "manifest_members"], "COMPLETE")
    if complete != {
        "version": ARCHIVE_VERSION,
        "status": "PASS_RUNTIME_PROVENANCE_QUALIFIED",
        "qualification_sha256": manifest["qualification.json"],
        "manifest_members": sorted(expected_members),
    }:
        _fail("COMPLETE: semantic mismatch")
    return qualification


def qualify(
    *,
    repo: Path,
    root: Path,
    runtime_lock_path: Path,
    provenance_spec_path: Path,
    observation: Mapping[str, Any],
    qualifier_source_path: Path | None = None,
) -> dict[str, Any]:
    for candidate, label in (
        (repo, "repository"),
        (root, "qualification archive"),
        (runtime_lock_path, "runtime lock"),
        (provenance_spec_path, "provenance spec"),
        (qualifier_source_path or Path(__file__), "qualifier source"),
    ):
        _reject_lexical_alias_syntax(candidate, label)
    repo = _lexical_absolute(repo)
    _reject_linklike_ancestors(repo, "repository")
    root = _lexical_absolute(root if root.is_absolute() else repo / root)
    runtime_lock_path = _lexical_absolute(
        runtime_lock_path if runtime_lock_path.is_absolute() else repo / runtime_lock_path
    )
    provenance_spec_path = _lexical_absolute(
        provenance_spec_path if provenance_spec_path.is_absolute() else repo / provenance_spec_path
    )
    source_argument = qualifier_source_path or Path(__file__)
    qualifier_source_path = _lexical_absolute(
        source_argument if source_argument.is_absolute() else repo / source_argument
    )
    for path, label in (
        (root, "qualification archive"),
        (runtime_lock_path, "runtime lock"),
        (provenance_spec_path, "provenance spec"),
        (qualifier_source_path, "qualifier source"),
    ):
        _reject_linklike_ancestors(path, label)
    try:
        root_relative = root.relative_to(repo)
    except ValueError:
        _fail("qualification archive must be lexically under repository derisk")
    folded_parts = [part.casefold() for part in root_relative.parts]
    if (
        len(folded_parts) < 2
        or folded_parts[0] != "derisk"
        or ".git" in folded_parts
        or "vendor" in folded_parts
    ):
        _fail("qualification archive must be a named child of repository derisk, never .git/vendor")
    if root.exists():
        result = validate_archive(root)
        archived_lock = (root / "runtime_lock.json").read_bytes()
        archived_spec = (root / "provenance_spec.json").read_bytes()
        if archived_lock != runtime_lock_path.read_bytes() or archived_spec != provenance_spec_path.read_bytes():
            _fail("existing sealed archive does not match requested inputs")
        live_observation = validate_runtime_observation(dict(observation))
        if canonical_json_bytes(live_observation) != (root / "runtime_observation.json").read_bytes():
            _fail("existing sealed archive does not match current runtime")
        _require_regular(qualifier_source_path, "qualifier source")
        if (root / "qualifier_source.py").read_bytes() != qualifier_source_path.read_bytes():
            _fail("existing sealed archive qualifier source differs from current executed source")
        validate_provenance(
            repo,
            load_canonical_json(provenance_spec_path),
            runtime_lock_path,
            provenance_spec_path,
        )
        return result

    runtime_lock = validate_runtime_observation(load_canonical_json(runtime_lock_path))
    live_observation = validate_runtime_observation(dict(observation))
    if runtime_lock != live_observation:
        _fail("live runtime observation differs from immutable runtime lock")
    spec, repo_commit = validate_provenance(
        repo,
        load_canonical_json(provenance_spec_path),
        runtime_lock_path,
        provenance_spec_path,
    )
    _require_regular(qualifier_source_path, "qualifier source")
    source_digest = sha256_file(qualifier_source_path)
    if spec["committed_sources"].get("scripts/qualify_slicegpt_runtime_v4.py") != source_digest:
        _fail("executing qualifier source differs from committed provenance")

    try:
        root.mkdir(parents=False, exist_ok=False)
    except OSError as exc:
        _fail(f"cannot create fresh qualification archive: {exc}")
    try:
        members = {
            "runtime_lock.json": runtime_lock_path.read_bytes(),
            "provenance_spec.json": provenance_spec_path.read_bytes(),
            "runtime_observation.json": canonical_json_bytes(live_observation),
            "qualifier_source.py": qualifier_source_path.read_bytes(),
        }
        for name, data in members.items():
            _write_new(root / name, data)
        preliminary = {name: sha256_bytes(data) for name, data in members.items()}
        relations = {
            "repo_commit": repo_commit,
            "runtime_lock_sha256": preliminary["runtime_lock.json"],
            "provenance_spec_sha256": preliminary["provenance_spec.json"],
            "runtime_observation_sha256": preliminary["runtime_observation.json"],
            "qualifier_source_sha256": preliminary["qualifier_source.py"],
            "vendor_commit": spec["vendor"]["commit"],
            "vendor_tree": spec["vendor"]["tree"],
            "calibration_fingerprint": spec["calibration"]["fingerprint"],
        }
        qualification = {
            "version": ARCHIVE_VERSION,
            "status": "PASS_RUNTIME_PROVENANCE_QUALIFIED",
            "scope": "RUNTIME_AND_PROVENANCE_ONLY",
            **relations,
            "adapter_status": "INCOMPLETE_PENDING_ADAPTER_GATES",
            "probe2_verdict": None,
            "nonzero_slice_authorized": False,
            "identity_fingerprint": _fingerprint(relations),
        }
        qualification_bytes = canonical_json_bytes(qualification)
        _write_new(root / "qualification.json", qualification_bytes)
        preliminary["qualification.json"] = sha256_bytes(qualification_bytes)
        complete = {
            "version": ARCHIVE_VERSION,
            "status": "PASS_RUNTIME_PROVENANCE_QUALIFIED",
            "qualification_sha256": preliminary["qualification.json"],
            "manifest_members": sorted(ARCHIVE_MEMBERS - {"MANIFEST.sha256"}),
        }
        complete_bytes = canonical_json_bytes(complete)
        _write_new(root / "COMPLETE.json", complete_bytes)
        preliminary["COMPLETE.json"] = sha256_bytes(complete_bytes)
        _write_new(root / "MANIFEST.sha256", _manifest_bytes(preliminary))
    except Exception:
        # Preserve partial evidence; never repair, delete or bless it.
        raise
    return validate_archive(root)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--runtime-lock", type=Path, required=True)
    parser.add_argument("--provenance-spec", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        result = qualify(
            repo=args.repo,
            root=args.root,
            runtime_lock_path=args.runtime_lock,
            provenance_spec_path=args.provenance_spec,
            observation=capture_live_runtime(),
        )
    except QualificationError as exc:
        print(f"INCOMPLETE_RUNTIME_PROVENANCE: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
