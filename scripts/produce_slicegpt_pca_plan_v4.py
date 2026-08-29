#!/usr/bin/env python3
"""Produce the deterministic, plan-only Gemma-3 SliceGPT v4 PCA archive.

This program observes the clean BF16 parent with the sealed seed-11 token
surface and computes the 69 residual-boundary PCA bases needed by the 34
sequential Gemma layers.  It never mutates model weights, never constructs a
reduced model, and cannot issue a reduced-width capability or Probe-2 verdict.
"""

from __future__ import annotations

import argparse
import copy
import ctypes
import errno
import gc
import hashlib
import importlib.machinery
import importlib.util
import json
import math
import os
import re
import stat
import subprocess
import sys
import types
from pathlib import Path
from typing import Any, Iterable, Mapping


VERSION = "slicegpt_gemma3_pca_plan_v4_v1"
WORK_VERSION = "slicegpt_gemma3_pca_work_v4_v1"
ARCHIVE_VERSION = "slicegpt_gemma3_pca_plan_archive_v4_v1"
HIDDEN_SIZE = 2560
NUM_LAYERS = 34
CALIBRATION_SEED = 11
CALIBRATION_ROWS = 128
SEQUENCE_LENGTH = 2048
BATCH_SIZE = 16
ROUND_INTERVAL = 8
DAMPING_NUMERATOR = 1
DAMPING_DENOMINATOR = 100
FRACTIONS = (
    "0.05", "0.10", "0.15", "0.20", "0.25", "0.30",
    "0.35", "0.40", "0.50", "0.60", "0.70", "0.80",
)
RETAINED_DIMENSIONS = (2432, 2304, 2176, 2048, 1920, 1792, 1664, 1536, 1280, 1024, 768, 512)
CORE_PATH = "scripts/slicegpt_gemma3_adapter_core_v4.py"
CORE_SHA256 = "c4df2be9111fd293454b19f98fba5d46805479d51db02d0611dcfab58f73cfdd"
MATERIALIZER_PATH = "scripts/materialize_slicegpt_calibration_v4.py"
MATERIALIZER_SHA256 = "4f8a9b62d823677eb0fdec29b94e557279c5657d97077f360904e0680e479fcf"
MODEL_QUALIFIER_PATH = "scripts/qualify_slicegpt_model_adapter_v4.py"
MODEL_QUALIFIER_SHA256 = "68a80c86ce7a8bcaacc77e347bc7b0ddb52d22fb4b24e1705851ab7e02c9ca33"
RUNTIME_QUALIFIER_PATH = "scripts/qualify_slicegpt_runtime_v4.py"
RUNTIME_QUALIFIER_SHA256 = "aa83ea05978abe00d39bc2b8e69d9dd97a3354b51862398fd37c2b22725503b3"
PRODUCER_PATH = "scripts/produce_slicegpt_pca_plan_v4.py"
TEST_PATH = "scripts/test_produce_slicegpt_pca_plan_v4.py"
OUTPUT_RELATIVE = "derisk/probe2_slicegpt_v4_pca_plan_seed11"
HEX40 = re.compile(r"[0-9a-f]{40}\Z")
HEX64 = re.compile(r"[0-9a-f]{64}\Z")


class PlanError(RuntimeError):
    pass


def fail(message: str) -> None:
    raise PlanError(message)


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _is_linklike(path: Path) -> bool:
    try:
        info = path.lstat()
    except (FileNotFoundError, OSError):
        return False
    attrs = int(getattr(info, "st_file_attributes", 0))
    return stat.S_ISLNK(info.st_mode) or bool(attrs & int(getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)))


def strict_path(path: Path, label: str, *, base: Path | None = None) -> Path:
    value = path.expanduser()
    if not value.is_absolute():
        value = (Path.cwd() if base is None else base) / value
    value = Path(os.path.abspath(value))
    for member in (value, *value.parents):
        if _is_linklike(member):
            fail(f"{label}: symlink/junction/reparse component forbidden: {member}")
    return value


def _json_value(value: Any, label: str = "JSON") -> None:
    if value is None or type(value) in {str, bool, int}:
        return
    if type(value) is float:
        if not math.isfinite(value):
            fail(f"{label}: non-finite float")
        fail(f"{label}: floating-point JSON is forbidden")
    if type(value) is list:
        for index, child in enumerate(value):
            _json_value(child, f"{label}[{index}]")
        return
    if type(value) is dict:
        for key, child in value.items():
            if type(key) is not str:
                fail(f"{label}: non-string key")
            _json_value(child, f"{label}.{key}")
        return
    fail(f"{label}: unsupported type {type(value).__name__}")


def canonical_json_bytes(value: Any) -> bytes:
    _json_value(value)
    return (json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True, indent=2, separators=(",", ": ")) + "\n").encode()


def load_canonical_json(path: Path) -> Any:
    raw = path.read_bytes()
    try:
        value = json.loads(raw.decode("utf-8"), parse_constant=lambda item: (_ for _ in ()).throw(ValueError(item)))
    except (UnicodeError, json.JSONDecodeError, ValueError) as error:
        fail(f"invalid JSON {path}: {error}")
    if raw != canonical_json_bytes(value):
        fail(f"noncanonical JSON: {path}")
    return value


def _fsync_directory(path: Path) -> None:
    if os.name == "nt":
        return
    flags = os.O_RDONLY | int(getattr(os, "O_DIRECTORY", 0))
    descriptor = os.open(path, flags)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _write_new(path: Path, data: bytes) -> None:
    with path.open("xb") as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())
    _fsync_directory(path.parent)


def _write_or_require_exact(path: Path, data: bytes) -> None:
    if path.exists():
        if _is_linklike(path) or not path.is_file() or path.read_bytes() != data:
            fail(f"existing crash-recovery artifact changed: {path.name}")
        return
    _write_new(path, data)


def _replace_work_json(path: Path, value: Any) -> None:
    temporary = path.with_name(path.name + ".next")
    if temporary.exists():
        fail("partial resume-state replacement already exists")
    _write_new(temporary, canonical_json_bytes(value))
    os.replace(temporary, path)
    _fsync_directory(path.parent)


def _publish_no_replace(source: Path, target: Path) -> None:
    if os.name == "nt":
        try:
            os.rename(source, target)
        except FileExistsError:
            fail("PCA archive appeared concurrently")
        return
    if sys.platform.startswith("linux"):
        library = ctypes.CDLL(None, use_errno=True)
        renameat2 = getattr(library, "renameat2", None)
        if renameat2 is None:
            fail("atomic no-replace publication is unavailable")
        renameat2.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
        renameat2.restype = ctypes.c_int
        if renameat2(-100, os.fsencode(source), -100, os.fsencode(target), 1) != 0:
            code = ctypes.get_errno()
            if code == errno.EEXIST:
                fail("PCA archive appeared concurrently")
            fail(f"atomic PCA publication failed: errno {code}")
        _fsync_directory(target.parent)
        return
    fail("atomic no-replace publication is unsupported")


def signal_names() -> tuple[str, ...]:
    values: list[str] = []
    for index in range(NUM_LAYERS):
        values.extend((f"layer_{index:02d}_input", f"layer_{index:02d}_attention"))
    values.append(f"layer_{NUM_LAYERS-1:02d}_output")
    return tuple(values)


SIGNALS = signal_names()


def layer_triplets() -> list[dict[str, Any]]:
    rows = []
    for index in range(NUM_LAYERS):
        output = f"layer_{index+1:02d}_input" if index + 1 < NUM_LAYERS else f"layer_{index:02d}_output"
        rows.append({
            "layer": index,
            "input": f"layer_{index:02d}_input",
            "attention": f"layer_{index:02d}_attention",
            "output": output,
        })
    return rows


def validate_source_record(source: Any) -> dict[str, Any]:
    if type(source) is not dict or set(source) != {
        "repo_commit", "committed_sources", "runtime_archive_manifest_sha256",
        "runtime_lock_sha256", "provenance_spec_sha256", "model_qualification_manifest_sha256",
        "model_qualification_observation_sha256", "calibration_manifest_sha256",
        "calibration_tensors_sha256", "parent_fingerprint",
    }:
        fail("plan source schema changed")
    if type(source["repo_commit"]) is not str or HEX40.fullmatch(source["repo_commit"]) is None:
        fail("plan repo commit changed")
    committed = source["committed_sources"]
    required_sources = {
        PRODUCER_PATH, TEST_PATH, CORE_PATH, MATERIALIZER_PATH,
        MODEL_QUALIFIER_PATH, RUNTIME_QUALIFIER_PATH,
        "docs/V4_SLICEGPT_PROTOCOL.md",
    }
    if (
        type(committed) is not dict
        or set(committed) != required_sources
        or any(type(key) is not str or type(item) is not str or HEX64.fullmatch(item) is None for key, item in committed.items())
    ):
        fail("plan committed-source map changed")
    for key, item in source.items():
        if key in {"repo_commit", "committed_sources"}:
            continue
        if type(item) is not str or HEX64.fullmatch(item) is None:
            fail(f"plan source digest changed: {key}")
    return source


def validate_plan_document(value: Any) -> dict[str, Any]:
    keys = {
        "version", "scope", "mechanism", "calibration_seed", "model_execution_dtype",
        "statistics_dtype", "covariance", "orientation", "round_interval", "signals",
        "layers", "doses", "plan_modes", "source", "nonzero_slice_authorized",
        "probe2_verdict", "transformation_executed",
    }
    if type(value) is not dict or set(value) != keys:
        fail("plan exact schema changed")
    if (
        value["version"] != VERSION
        or value["scope"] != "PCA_TRANSFORMATION_PLAN_ONLY"
        or value["mechanism"] != "slicegpt_residual_width_pca"
        or type(value["calibration_seed"]) is not int
        or value["calibration_seed"] != CALIBRATION_SEED
        or value["model_execution_dtype"] != "BF16"
        or value["statistics_dtype"] != "FP64"
        or value["orientation"] != "pure_pca_first_max_abs_sign_no_random_rotation"
        or type(value["round_interval"]) is not int
        or value["round_interval"] != ROUND_INTERVAL
        or value["nonzero_slice_authorized"] is not False
        or value["probe2_verdict"] is not None
        or value["transformation_executed"] is not False
    ):
        fail("plan safety or numeric identity changed")
    covariance = value["covariance"]
    if covariance != {
        "centering": "none_upstream_second_moment",
        "mask": "sealed_all_one_attention_mask",
        "damping": "0.01 * mean(diag(covariance))",
        "accumulation": "sum_batch_token_outer_products",
    }:
        fail("plan covariance semantics changed")
    signals = value["signals"]
    if type(signals) is not dict or tuple(sorted(signals)) != tuple(sorted(SIGNALS)):
        fail("plan signal set changed")
    for name, record in signals.items():
        if type(record) is not dict or set(record) != {
            "covariance_file", "covariance_sha256", "basis_file", "basis_sha256",
            "sample_token_count", "damping_hex", "eigenvalues_sha256", "prefix_sha256",
        }:
            fail(f"plan signal schema changed: {name}")
        for key in ("covariance_sha256", "basis_sha256", "eigenvalues_sha256"):
            if type(record[key]) is not str or HEX64.fullmatch(record[key]) is None:
                fail(f"plan signal digest changed: {name}.{key}")
        if record["covariance_file"] != f"covariances/{name}.safetensors":
            fail(f"plan covariance path changed: {name}")
        if record["basis_file"] != f"bases/{name}.safetensors":
            fail(f"plan basis path changed: {name}")
        if type(record["sample_token_count"]) is not int or record["sample_token_count"] != CALIBRATION_ROWS * SEQUENCE_LENGTH:
            fail(f"plan signal token count changed: {name}")
        if type(record["damping_hex"]) is not str:
            fail(f"plan damping encoding changed: {name}")
        try:
            damping = float.fromhex(record["damping_hex"])
        except ValueError:
            fail(f"plan damping encoding changed: {name}")
        if not math.isfinite(damping) or damping < 0.0 or damping.hex() != record["damping_hex"]:
            fail(f"plan damping value changed: {name}")
        prefixes = record["prefix_sha256"]
        if type(prefixes) is not dict or set(prefixes) != {str(item) for item in RETAINED_DIMENSIONS}:
            fail(f"plan retained-prefix set changed: {name}")
        if any(type(item) is not str or HEX64.fullmatch(item) is None for item in prefixes.values()):
            fail(f"plan retained-prefix digest changed: {name}")
    if value["layers"] != layer_triplets():
        fail("plan layer-to-layer basis continuity changed")
    expected_doses = [
        {"fraction": fraction, "retained_dimension": dimension, "plan_only": True}
        for fraction, dimension in zip(FRACTIONS, RETAINED_DIMENSIONS, strict=True)
    ]
    if value["doses"] != expected_doses:
        fail("plan frozen dose grid changed")
    if value["plan_modes"] != {
        "full_width_identity": {
            "basis": "implicit_exact_identity",
            "status": "PREPARED_NOT_EXECUTED",
        },
        "full_width_pca_nonidentity": {
            "basis": "archived_clean_boundary_pca",
            "status": "PREPARED_NOT_EXECUTED",
        },
        "reduced_width": {
            "basis": "requires_post_capability_sequential_per_dose_recalibration",
            "retained_dimensions_are": "frozen_targets_and_prefix_hashes_only",
            "status": "NOT_PREPARED_NOT_AUTHORIZED",
        },
    }:
        fail("PCA plan capability boundary changed")
    validate_source_record(value["source"])
    return value


def _direct_module(name: str, path: Path, expected_sha256: str, dependencies: Mapping[str, Any] | None = None) -> Any:
    dependencies = dict(dependencies or {})
    guarded = {name, *dependencies}
    if any(item in sys.modules for item in guarded):
        fail(f"preloaded project module namespace forbidden: {sorted(item for item in guarded if item in sys.modules)}")
    path = strict_path(path, f"module {name}")
    before = path.read_bytes()
    if sha256_bytes(before) != expected_sha256:
        fail(f"module source hash changed: {name}")
    spec = importlib.util.spec_from_file_location(name, path)
    if (
        spec is None
        or type(spec.loader) is not importlib.machinery.SourceFileLoader
        or spec.loader.name != name
        or Path(os.path.abspath(str(spec.origin))) != path
    ):
        fail(f"module source loader substituted: {name}")
    module = types.ModuleType(name)
    module.__file__, module.__loader__, module.__package__, module.__spec__ = str(path), spec.loader, "", spec
    try:
        for dependency_name, dependency in dependencies.items():
            sys.modules[dependency_name] = dependency
        sys.modules[name] = module
        source = path.read_bytes()
        if sha256_bytes(source) != expected_sha256:
            fail(f"buffered module source changed: {name}")
        exec(compile(source, str(path), "exec"), module.__dict__)
    finally:
        for item in guarded:
            sys.modules.pop(item, None)
    if path.read_bytes() != before or sha256_file(path) != expected_sha256:
        fail(f"module source changed during execution: {name}")
    return module


def _git(repo: Path, *arguments: str, binary: bool = False) -> str | bytes:
    try:
        result = subprocess.run(["git", *arguments], cwd=repo, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=not binary)
    except (OSError, subprocess.CalledProcessError) as error:
        fail(f"git {' '.join(arguments)} failed: {error}")
    return result.stdout


def committed_sources(repo: Path) -> tuple[str, dict[str, str]]:
    head = str(_git(repo, "rev-parse", "HEAD")).strip()
    if HEX40.fullmatch(head) is None:
        fail("repository HEAD is not exact")
    required = {
        PRODUCER_PATH, TEST_PATH, CORE_PATH, MATERIALIZER_PATH, MODEL_QUALIFIER_PATH,
        RUNTIME_QUALIFIER_PATH, "docs/V4_SLICEGPT_PROTOCOL.md",
    }
    result: dict[str, str] = {}
    for relative in sorted(required):
        path = strict_path(repo / relative, f"committed source {relative}")
        blob = _git(repo, "show", f"{head}:{relative}", binary=True)
        assert isinstance(blob, bytes)
        if path.read_bytes() != blob:
            fail(f"source differs from committed HEAD: {relative}")
        result[relative] = sha256_bytes(blob)
    expected = {
        CORE_PATH: CORE_SHA256,
        MATERIALIZER_PATH: MATERIALIZER_SHA256,
        MODEL_QUALIFIER_PATH: MODEL_QUALIFIER_SHA256,
        RUNTIME_QUALIFIER_PATH: RUNTIME_QUALIFIER_SHA256,
    }
    if any(result.get(path) != digest for path, digest in expected.items()):
        fail("approved dependency source changed")
    return head, result


def canonicalize_basis_signs(torch: Any, basis: Any) -> Any:
    if not isinstance(basis, torch.Tensor) or basis.dtype is not torch.float64 or basis.ndim != 2:
        fail("basis sign canonicalization requires an FP64 matrix")
    result = basis.clone()
    for column in range(result.shape[1]):
        pivot = int(torch.argmax(result[:, column].abs()).item())
        if float(result[pivot, column].item()) < 0.0:
            result[:, column].neg_()
    return result


def pca_from_covariance(torch: Any, covariance: Any) -> tuple[Any, Any, Any]:
    if (
        not isinstance(covariance, torch.Tensor)
        or covariance.dtype is not torch.float64
        or covariance.ndim != 2
        or covariance.shape[0] != covariance.shape[1]
        or not bool(torch.isfinite(covariance).all().item())
        or not torch.equal(covariance, covariance.transpose(0, 1))
    ):
        fail("PCA covariance must be finite exact-symmetric FP64")
    damping = (DAMPING_NUMERATOR / DAMPING_DENOMINATOR) * covariance.diagonal().mean()
    if not bool(torch.isfinite(damping).item()) or float(damping.item()) < 0.0:
        fail("PCA damping changed")
    damped = covariance.clone()
    damped.diagonal().add_(damping)
    eigenvalues, basis = torch.linalg.eigh(damped)
    order = torch.argsort(eigenvalues, descending=True)
    eigenvalues = eigenvalues[order].contiguous()
    basis = basis[:, order].contiguous()
    basis = canonicalize_basis_signs(torch, basis)
    identity = torch.eye(basis.shape[1], dtype=torch.float64, device=basis.device)
    if not torch.allclose(basis.transpose(0, 1) @ basis, identity, rtol=1e-10, atol=1e-10):
        fail("PCA basis is not FP64 orthonormal")
    if bool((eigenvalues[:-1] < eigenvalues[1:]).any().item()):
        fail("PCA eigenvalue ordering changed")
    return eigenvalues, basis, damping


def tensor_sha256(torch: Any, tensor: Any) -> str:
    if not isinstance(tensor, torch.Tensor) or tensor.device.type == "meta":
        fail("tensor hash requires materialized tensor")
    raw = tensor.detach().contiguous().view(torch.uint8).cpu().numpy().tobytes()
    return sha256_bytes(raw)


class CovarianceCollector:
    def __init__(self, torch: Any, device: Any) -> None:
        self.torch = torch
        self.device = device
        self.values: dict[str, Any] = {}
        self.counts = {name: 0 for name in SIGNALS}

    def consume(self, name: str, hidden: Any) -> None:
        torch = self.torch
        if name not in self.counts:
            fail(f"unknown capture signal: {name}")
        if (
            not isinstance(hidden, torch.Tensor)
            or hidden.dtype is not torch.bfloat16
            or hidden.ndim != 3
            or hidden.shape[-1] != HIDDEN_SIZE
            or hidden.device != self.device
            or not bool(torch.isfinite(hidden).all().item())
        ):
            fail(f"captured BF16 signal changed: {name}")
        # Preserve the vendored SliceGPT pca_calc reduction exactly: one
        # [sequence, hidden] GEMM per batch row followed by sum(dim=0).  The
        # batched FP64 temporary is released before the model continues, so
        # peak CUDA storage is bounded to one captured signal.
        values = hidden.detach().to(dtype=torch.float64)
        covariance = torch.sum(values.mT @ values, dim=0)
        covariance = covariance.cpu()
        if name not in self.values:
            self.values[name] = covariance
        else:
            self.values[name].add_(covariance)
        self.counts[name] += int(hidden.shape[0] * hidden.shape[1])
        del values, covariance


def _hidden_from_call(args: tuple[Any, ...], kwargs: Mapping[str, Any]) -> Any:
    if args:
        return args[0]
    if "hidden_states" in kwargs:
        return kwargs["hidden_states"]
    fail("Gemma hook did not expose hidden_states")


def collect_covariances(torch: Any, model: Any, surface: Any, input_ids: Any, attention_mask: Any, device: Any) -> CovarianceCollector:
    if tuple(input_ids.shape) != (CALIBRATION_ROWS, SEQUENCE_LENGTH) or tuple(attention_mask.shape) != tuple(input_ids.shape):
        fail("sealed calibration tensor shape changed")
    if input_ids.dtype is not torch.int64 or attention_mask.dtype is not torch.int64 or not bool((attention_mask == 1).all().item()):
        fail("sealed calibration tensor dtype/mask changed")
    collector = CovarianceCollector(torch, device)
    hooks = []
    for index, layer in enumerate(surface.layers):
        input_name = f"layer_{index:02d}_input"
        attention_name = f"layer_{index:02d}_attention"
        hooks.append(layer.register_forward_pre_hook(
            lambda _module, args, kwargs, name=input_name: collector.consume(name, _hidden_from_call(args, kwargs)),
            with_kwargs=True,
        ))
        hooks.append(layer.pre_feedforward_layernorm.register_forward_pre_hook(
            lambda _module, args, kwargs, name=attention_name: collector.consume(name, _hidden_from_call(args, kwargs)),
            with_kwargs=True,
        ))
    final_name = f"layer_{NUM_LAYERS-1:02d}_output"
    hooks.append(surface.final_norm.register_forward_pre_hook(
        lambda _module, args, kwargs: collector.consume(final_name, _hidden_from_call(args, kwargs)),
        with_kwargs=True,
    ))
    try:
        model.eval()
        with torch.inference_mode():
            for start in range(0, CALIBRATION_ROWS, BATCH_SIZE):
                ids = input_ids[start:start+BATCH_SIZE].to(device=device)
                mask = attention_mask[start:start+BATCH_SIZE].to(device=device)
                result = surface.language_model(
                    input_ids=ids,
                    attention_mask=mask,
                    use_cache=False,
                    output_hidden_states=False,
                    return_dict=True,
                )
                if not bool(torch.isfinite(result.last_hidden_state).all().item()):
                    fail("Gemma BF16 calibration execution produced non-finite output")
                del result, ids, mask
                torch.cuda.empty_cache()
    finally:
        for hook in hooks:
            hook.remove()
    expected_count = CALIBRATION_ROWS * SEQUENCE_LENGTH
    if set(collector.values) != set(SIGNALS) or any(value != expected_count for value in collector.counts.values()):
        fail("PCA capture signal membership/count changed")
    return collector


def _save_tensor_file(save_file: Any, path: Path, tensors: Mapping[str, Any], metadata: Mapping[str, str]) -> None:
    if path.exists():
        fail(f"refusing to replace tensor artifact: {path}")
    save_file(dict(tensors), str(path), metadata=dict(metadata))
    with path.open("rb") as handle:
        os.fsync(handle.fileno())
    _fsync_directory(path.parent)


def _validate_work_state(value: Any, source_sha256: str) -> dict[str, Any]:
    if type(value) is not dict or set(value) != {
        "version", "stage", "signals", "covariance_sha256", "completed_bases", "source_sha256",
    }:
        fail("PCA resume-state schema changed")
    if (
        value["version"] != WORK_VERSION
        or value["stage"] not in {"COLLECTING", "COVARIANCES_COMPLETE", "EIGENDECOMPOSITION", "COMPLETE"}
        or value["signals"] != list(SIGNALS)
        or value["source_sha256"] != source_sha256
        or type(value["covariance_sha256"]) is not dict
        or type(value["completed_bases"]) is not dict
    ):
        fail("PCA resume-state identity changed")
    completed = value["completed_bases"]
    covariances = value["covariance_sha256"]
    if any(
        name not in SIGNALS
        or type(digest) is not str
        or HEX64.fullmatch(digest) is None
        for name, digest in covariances.items()
    ):
        fail("PCA resume-state covariance binding changed")
    if any(
        name not in SIGNALS
        or type(digest) is not str
        or HEX64.fullmatch(digest) is None
        for name, digest in completed.items()
    ):
        fail("PCA resume-state basis binding changed")
    completed_order = [name for name in SIGNALS if name in completed]
    expected_prefix = list(SIGNALS[:len(completed)])
    if set(completed) != set(expected_prefix) or completed_order != expected_prefix:
        fail("PCA resume-state completion is not an exact prefix")
    if value["stage"] in {"COLLECTING", "COVARIANCES_COMPLETE"} and completed:
        fail("PCA resume-state stage conflicts with completed bases")
    if value["stage"] == "COLLECTING" and covariances:
        fail("PCA collecting state cannot bind a partial covariance set")
    if value["stage"] != "COLLECTING" and set(covariances) != set(SIGNALS):
        fail("PCA resume-state covariance set is incomplete")
    if value["stage"] == "EIGENDECOMPOSITION" and not completed:
        fail("PCA resume-state eigendecomposition lacks a completed basis")
    if value["stage"] == "COMPLETE" and completed_order != list(SIGNALS):
        fail("PCA terminal resume-state is incomplete")
    return value


def _read_covariance(safe_open: Any, torch: Any, path: Path, name: str) -> Any:
    if not path.is_file() or _is_linklike(path):
        fail(f"PCA covariance artifact missing or linklike: {name}")
    with safe_open(path, framework="pt", device="cpu") as handle:
        if set(handle.keys()) != {"covariance"} or handle.metadata() != {
            "version": VERSION,
            "signal": name,
            "token_count": str(CALIBRATION_ROWS * SEQUENCE_LENGTH),
            "dtype": "FP64",
        }:
            fail(f"PCA covariance metadata changed: {name}")
        covariance = handle.get_tensor("covariance")
    if (
        covariance.dtype is not torch.float64
        or tuple(covariance.shape) != (HIDDEN_SIZE, HIDDEN_SIZE)
        or not bool(torch.isfinite(covariance).all().item())
        or not torch.equal(covariance, covariance.transpose(0, 1))
    ):
        fail(f"PCA covariance numeric identity changed: {name}")
    return covariance


def _read_basis(safe_open: Any, torch: Any, path: Path, name: str) -> tuple[Any, Any, Any]:
    if not path.is_file() or _is_linklike(path):
        fail(f"PCA basis artifact missing or linklike: {name}")
    with safe_open(path, framework="pt", device="cpu") as handle:
        if set(handle.keys()) != {"basis", "damping", "eigenvalues"} or handle.metadata() != {
            "version": VERSION,
            "signal": name,
            "orientation": "pure_pca",
            "sign": "first_max_abs_pivot",
        }:
            fail(f"PCA basis metadata changed: {name}")
        basis = handle.get_tensor("basis")
        eigenvalues = handle.get_tensor("eigenvalues")
        damping = handle.get_tensor("damping")
    if (
        basis.dtype is not torch.float64
        or tuple(basis.shape) != (HIDDEN_SIZE, HIDDEN_SIZE)
        or eigenvalues.dtype is not torch.float64
        or tuple(eigenvalues.shape) != (HIDDEN_SIZE,)
        or damping.dtype is not torch.float64
        or tuple(damping.shape) != ()
        or not bool(torch.isfinite(basis).all().item())
        or not bool(torch.isfinite(eigenvalues).all().item())
        or not bool(torch.isfinite(damping).item())
        or float(damping.item()) < 0.0
        or bool((eigenvalues[:-1] < eigenvalues[1:]).any().item())
        or not torch.equal(canonicalize_basis_signs(torch, basis), basis)
    ):
        fail(f"PCA basis numeric identity changed: {name}")
    return basis, eigenvalues, damping


def _manifest_entries(root: Path) -> dict[str, str]:
    result = {}
    allowed_directories = {"bases", "covariances"}
    for path in sorted(root.rglob("*"), key=lambda item: item.as_posix()):
        if _is_linklike(path):
            fail("PCA archive contains linklike member")
        if path.is_dir():
            if path.relative_to(root).as_posix() not in allowed_directories:
                fail("PCA archive contains a noncanonical directory")
            continue
        if not path.is_file():
            fail("PCA archive contains non-regular member")
        relative = path.relative_to(root).as_posix()
        if relative != "MANIFEST.sha256":
            result[relative] = sha256_file(path)
    return result


def _manifest_bytes(values: Mapping[str, str]) -> bytes:
    return "".join(f"{values[name]}  {name}\n" for name in sorted(values)).encode()


def validate_archive(root: Path) -> dict[str, Any]:
    try:
        import torch
        from safetensors import safe_open
    except ModuleNotFoundError as error:
        fail(f"PCA archive validation runtime unavailable: {error}")
    root = strict_path(root, "PCA plan archive")
    if not root.is_dir():
        fail("PCA plan archive missing")
    manifest_path = root / "MANIFEST.sha256"
    if not manifest_path.is_file():
        fail("PCA archive manifest missing")
    raw = manifest_path.read_bytes()
    if b"\r" in raw or not raw.endswith(b"\n"):
        fail("PCA archive manifest is noncanonical")
    manifest: dict[str, str] = {}
    for line in raw.decode("utf-8").splitlines():
        match = re.fullmatch(r"([0-9a-f]{64})  (.+)", line)
        if match is None or match.group(2) in manifest:
            fail("PCA archive manifest row changed")
        manifest[match.group(2)] = match.group(1)
    if raw != _manifest_bytes(manifest) or manifest != _manifest_entries(root):
        fail("PCA archive manifest membership/hash changed")
    required = {"plan.json", "source.json", "resume_state.json", "COMPLETE.json"}
    required |= {f"covariances/{name}.safetensors" for name in SIGNALS}
    required |= {f"bases/{name}.safetensors" for name in SIGNALS}
    if set(manifest) != required:
        fail("PCA archive exact member surface changed")
    plan = validate_plan_document(load_canonical_json(root / "plan.json"))
    source = load_canonical_json(root / "source.json")
    if source != plan["source"]:
        fail("PCA archive source cross-binding changed")
    expected_basis_hashes = {
        name: sha256_file(root / f"bases/{name}.safetensors") for name in SIGNALS
    }
    expected_covariance_hashes = {
        name: sha256_file(root / f"covariances/{name}.safetensors") for name in SIGNALS
    }
    state = _validate_work_state(
        load_canonical_json(root / "resume_state.json"),
        sha256_file(root / "source.json"),
    )
    if (
        state["stage"] != "COMPLETE"
        or state["completed_bases"] != expected_basis_hashes
        or state["covariance_sha256"] != expected_covariance_hashes
    ):
        fail("PCA archive terminal resume state changed")
    complete = load_canonical_json(root / "COMPLETE.json")
    expected_complete = {
        "version": ARCHIVE_VERSION,
        "status": "COMPLETE_PCA_TRANSFORMATION_PLAN_ONLY",
        "plan_sha256": sha256_file(root / "plan.json"),
        "source_sha256": sha256_file(root / "source.json"),
        "manifest_members": sorted(required),
        "nonzero_slice_authorized": False,
        "probe2_verdict": None,
        "transformation_executed": False,
    }
    if complete != expected_complete:
        fail("PCA archive completion semantics changed")
    for name in SIGNALS:
        record = plan["signals"][name]
        covariance_path = root / record["covariance_file"]
        basis_path = root / record["basis_file"]
        if sha256_file(covariance_path) != record["covariance_sha256"]:
            fail(f"PCA covariance plan hash changed: {name}")
        if sha256_file(basis_path) != record["basis_sha256"]:
            fail(f"PCA basis plan hash changed: {name}")
        covariance = _read_covariance(safe_open, torch, covariance_path, name)
        basis, eigenvalues, damping = _read_basis(safe_open, torch, basis_path, name)
        expected_eigenvalues, expected_basis, expected_damping = pca_from_covariance(torch, covariance)
        if not (
            torch.equal(damping, expected_damping)
            and torch.equal(eigenvalues, expected_eigenvalues)
            and torch.equal(basis, expected_basis)
        ):
            fail(f"PCA deterministic covariance/eigensystem binding changed: {name}")
        if float(damping.item()).hex() != record["damping_hex"]:
            fail(f"PCA damping plan binding changed: {name}")
        if tensor_sha256(torch, eigenvalues) != record["eigenvalues_sha256"]:
            fail(f"PCA eigenvalue plan binding changed: {name}")
        for width in RETAINED_DIMENSIONS:
            if tensor_sha256(torch, basis[:, :width]) != record["prefix_sha256"][str(width)]:
                fail(f"PCA retained-prefix binding changed: {name}/{width}")
        del covariance, basis, eigenvalues, damping
        del expected_eigenvalues, expected_basis, expected_damping
    return plan


def _seal_work_archive(work: Path) -> None:
    plan = validate_plan_document(load_canonical_json(work / "plan.json"))
    if load_canonical_json(work / "source.json") != plan["source"]:
        fail("PCA work source/plan binding changed")
    state = _validate_work_state(
        load_canonical_json(work / "resume_state.json"),
        sha256_file(work / "source.json"),
    )
    if state["stage"] != "COMPLETE":
        fail("PCA work cannot be sealed before terminal state")
    complete = {
        "version": ARCHIVE_VERSION,
        "status": "COMPLETE_PCA_TRANSFORMATION_PLAN_ONLY",
        "plan_sha256": sha256_file(work / "plan.json"),
        "source_sha256": sha256_file(work / "source.json"),
        "manifest_members": sorted(set(_manifest_entries(work)) | {"COMPLETE.json"}),
        "nonzero_slice_authorized": False,
        "probe2_verdict": None,
        "transformation_executed": False,
    }
    _write_or_require_exact(work / "COMPLETE.json", canonical_json_bytes(complete))
    _write_or_require_exact(work / "MANIFEST.sha256", _manifest_bytes(_manifest_entries(work)))


def _source_record(
    *, repo: Path, head: str, sources: Mapping[str, str], runtime_archive: Path,
    runtime_lock: Path, provenance_spec: Path, model_qualification: Path,
    calibration: Path, model_observation: Mapping[str, Any], calibration_metadata: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "repo_commit": head,
        "committed_sources": dict(sources),
        "runtime_archive_manifest_sha256": sha256_file(runtime_archive / "MANIFEST.sha256"),
        "runtime_lock_sha256": sha256_file(runtime_lock),
        "provenance_spec_sha256": sha256_file(provenance_spec),
        "model_qualification_manifest_sha256": sha256_file(model_qualification / "MANIFEST.sha256"),
        "model_qualification_observation_sha256": sha256_file(model_qualification / "observation.json"),
        "calibration_manifest_sha256": sha256_file(calibration / "MANIFEST.sha256"),
        "calibration_tensors_sha256": sha256_file(calibration / "calibration.safetensors"),
        "parent_fingerprint": calibration_metadata["parent"]["fingerprint"],
    }


def _validate_archived_source_replay(
    repo: Path, source: Mapping[str, Any], current_head: str, current_sources: Mapping[str, str]
) -> None:
    historical = source["repo_commit"]
    recorded = source["committed_sources"]
    try:
        _git(repo, "merge-base", "--is-ancestor", historical, current_head)
    except PlanError:
        fail("PCA source commit is not an ancestor of current HEAD")
    if recorded != current_sources:
        fail("PCA committed-source bytes differ from current HEAD")
    for relative, expected in recorded.items():
        historical_blob = _git(repo, "show", f"{historical}:{relative}", binary=True)
        current_blob = _git(repo, "show", f"{current_head}:{relative}", binary=True)
        assert isinstance(historical_blob, bytes) and isinstance(current_blob, bytes)
        if sha256_bytes(historical_blob) != expected or historical_blob != current_blob:
            fail(f"PCA committed source changed after sealing: {relative}")


def _validate_model_upstreams(
    *, repo: Path, model_q: Any, model_qualification: Path,
    runtime_archive: Path, runtime_lock: Path, provenance_spec: Path,
    expected_current_head: str,
) -> dict[str, Any]:
    """Replay a historically sealed model gate against unchanged live bytes."""
    observation = model_q.validate_archive(model_qualification)
    if (
        observation.get("status") != "INCOMPLETE_SERIALIZATION_AND_PEFT"
        or observation.get("model_level_gates_passed") is not True
        or observation.get("nonzero_slice_authorized") is not False
        or observation.get("probe2_verdict") is not None
    ):
        fail("model qualification does not prove the full-width adapter boundary")
    runtime_q = model_q.runtime_q
    try:
        runtime_q.validate_archive(runtime_archive)
        spec_value = runtime_q.load_canonical_json(provenance_spec)
        _spec, current_head = runtime_q.validate_provenance(
            repo, spec_value, runtime_lock, provenance_spec
        )
    except Exception as error:
        fail(f"model qualification upstream replay failed: {error}")
    if current_head != expected_current_head:
        fail("runtime provenance and PCA source HEAD differ")
    provenance = observation["provenance"]
    historical = provenance["repo_commit"]
    try:
        _git(repo, "merge-base", "--is-ancestor", historical, current_head)
    except PlanError:
        fail("model qualification commit is not an ancestor of PCA source HEAD")
    for relative, expected in provenance["committed_sources"].items():
        if type(expected) is not str or HEX64.fullmatch(expected) is None:
            fail(f"model qualification source digest changed: {relative}")
        historical_blob = _git(repo, "show", f"{historical}:{relative}", binary=True)
        current_blob = _git(repo, "show", f"{current_head}:{relative}", binary=True)
        assert isinstance(historical_blob, bytes) and isinstance(current_blob, bytes)
        if sha256_bytes(historical_blob) != expected or historical_blob != current_blob:
            fail(f"model qualification source changed after sealing: {relative}")
    if sha256_file(model_qualification / "qualifier_source.py") != MODEL_QUALIFIER_SHA256:
        fail("model qualification archived source changed")

    # The model helper's semantic replay is exact except for its intentional
    # same-HEAD rule.  An ancestor+byte identity proof above permits replacing
    # only that commit field for replay; no archived evidence is modified.
    replay_observation = copy.deepcopy(observation)
    replay_observation["provenance"]["repo_commit"] = current_head
    model_q.validate_external_bindings(
        repo=repo,
        observation=replay_observation,
        runtime_archive=runtime_archive,
        runtime_lock=runtime_lock,
        provenance_spec=provenance_spec,
    )
    return observation


def produce(args: argparse.Namespace) -> dict[str, Any]:
    try:
        import torch
        from safetensors import safe_open
        from safetensors.torch import save_file
        from transformers import Gemma3ForConditionalGeneration
    except ModuleNotFoundError as error:
        fail(f"pinned PCA runtime unavailable: {error}")
    repo = strict_path(args.repo, "repository")
    output = strict_path(args.output, "PCA output", base=repo)
    canonical_output = strict_path(repo / OUTPUT_RELATIVE, "canonical PCA output", base=repo)
    if output != canonical_output:
        fail(f"PCA output must be the exact canonical path {OUTPUT_RELATIVE}")
    try:
        relative_output = output.relative_to(repo)
    except ValueError:
        fail("PCA output must be under repository derisk")
    forbidden_output_parts = {item.casefold() for item in relative_output.parts}
    if (
        len(relative_output.parts) < 2
        or relative_output.parts[0].casefold() != "derisk"
        or forbidden_output_parts & {".git", "vendor"}
    ):
        fail("PCA output must be a named derisk descendant")
    work = strict_path(output.with_name(output.name + ".work"), "PCA work", base=repo)
    runtime_archive = strict_path(args.runtime_archive, "runtime archive", base=repo)
    runtime_lock = strict_path(args.runtime_lock, "runtime lock", base=repo)
    provenance_spec = strict_path(args.provenance_spec, "provenance spec", base=repo)
    model_qualification = strict_path(args.model_qualification, "model qualification", base=repo)
    calibration = strict_path(args.calibration, "seed-11 calibration", base=repo)
    parent = strict_path(args.model, "parent model", base=repo)
    head, sources = committed_sources(repo)

    model_q = _direct_module("_pca_model_qualifier_v4", repo / MODEL_QUALIFIER_PATH, MODEL_QUALIFIER_SHA256)
    observation = _validate_model_upstreams(
        repo=repo,
        model_q=model_q,
        model_qualification=model_qualification,
        runtime_archive=runtime_archive,
        runtime_lock=runtime_lock,
        provenance_spec=provenance_spec,
        expected_current_head=head,
    )
    materializer = _direct_module("_pca_materializer_v4", repo / MATERIALIZER_PATH, MATERIALIZER_SHA256)
    calibration_metadata = materializer.validate_sealed_archive(
        calibration, repo=repo, parent_model=parent, runtime_lock_path=runtime_lock
    )
    if calibration_metadata is None or calibration_metadata.get("seed") != CALIBRATION_SEED:
        fail("exact sealed seed-11 calibration is required")
    existing_plan = validate_archive(output) if output.exists() else None
    stored_source = (
        existing_plan["source"]
        if existing_plan is not None
        else load_canonical_json(work / "source.json") if work.exists()
        else None
    )
    if stored_source is not None:
        # validate_plan_document already covered a terminal archive; an
        # incomplete work source receives the same exact source schema here.
        source_probe = validate_source_record(stored_source)
        _validate_archived_source_replay(repo, source_probe, head, sources)
    record_head = head if stored_source is None else stored_source["repo_commit"]
    record_sources = sources if stored_source is None else stored_source["committed_sources"]
    source_record = _source_record(
        repo=repo, head=record_head, sources=record_sources, runtime_archive=runtime_archive,
        runtime_lock=runtime_lock, provenance_spec=provenance_spec,
        model_qualification=model_qualification, calibration=calibration,
        model_observation=observation, calibration_metadata=calibration_metadata,
    )
    if stored_source is not None and stored_source != source_record:
        fail("stored PCA archive/work does not bind the requested live inputs")

    if existing_plan is not None:
        if work.exists():
            fail("terminal PCA archive has an unexpected sibling work directory")
        return existing_plan

    if work.exists():
        if not args.resume:
            fail("PCA work exists; explicit --resume required")
        source_sha256 = sha256_file(work / "source.json")
        state = _validate_work_state(load_canonical_json(work / "resume_state.json"), source_sha256)
        if load_canonical_json(work / "source.json") != source_record:
            fail("PCA resume source binding changed")
        if state.get("stage") == "COLLECTING":
            fail("incomplete covariance pass is preserved and cannot be resumed")
        if state["stage"] == "COMPLETE":
            _seal_work_archive(work)
            validate_archive(work)
            _publish_no_replace(work, output)
            return validate_archive(output)
    else:
        work.mkdir(parents=True, exist_ok=False)
        (work / "covariances").mkdir()
        (work / "bases").mkdir()
        _write_new(work / "source.json", canonical_json_bytes(source_record))
        state = {
            "version": WORK_VERSION,
            "stage": "COLLECTING",
            "signals": list(SIGNALS),
            "covariance_sha256": {},
            "completed_bases": {},
            "source_sha256": sha256_file(work / "source.json"),
        }
        _write_new(work / "resume_state.json", canonical_json_bytes(state))

        core = _direct_module("_pca_adapter_core_v4", repo / CORE_PATH, CORE_SHA256)
        with safe_open(calibration / "calibration.safetensors", framework="pt", device="cpu") as handle:
            if set(handle.keys()) != {"attention_mask", "input_ids"}:
                fail("seed-11 calibration tensor membership changed")
            input_ids = handle.get_tensor("input_ids")
            attention_mask = handle.get_tensor("attention_mask")
        if not torch.cuda.is_available() or torch.cuda.device_count() != 1:
            fail("PCA production requires the frozen single L4 CUDA host")
        device = torch.device("cuda", 0)
        if torch.cuda.current_device() != 0:
            fail("PCA production CUDA device identity changed")
        model = Gemma3ForConditionalGeneration.from_pretrained(
            parent, torch_dtype=torch.bfloat16, device_map={"": 0}, local_files_only=True
        ).eval()
        if any(parameter.dtype is not torch.bfloat16 for parameter in model.parameters()):
            fail("PCA model execution state is not exact BF16")
        surface = core.discover_pinned_gemma3(model)
        cpu_rng_before = torch.random.get_rng_state().clone()
        cuda_rng_before = tuple(item.clone() for item in torch.cuda.get_rng_state_all())
        collector = collect_covariances(torch, model, surface, input_ids, attention_mask, device)
        if not torch.equal(torch.random.get_rng_state(), cpu_rng_before):
            fail("PCA observation consumed CPU RNG state")
        cuda_rng_after = tuple(torch.cuda.get_rng_state_all())
        if len(cuda_rng_after) != len(cuda_rng_before) or any(
            not torch.equal(before, after) for before, after in zip(cuda_rng_before, cuda_rng_after, strict=True)
        ):
            fail("PCA observation consumed CUDA RNG state")
        del model, surface, input_ids, attention_mask
        gc.collect()
        torch.cuda.empty_cache()
        for name in SIGNALS:
            covariance = collector.values[name].contiguous()
            if covariance.dtype is not torch.float64 or not torch.equal(covariance, covariance.transpose(0, 1)):
                fail(f"accumulated covariance changed: {name}")
            _save_tensor_file(
                save_file,
                work / "covariances" / f"{name}.safetensors",
                {"covariance": covariance},
                {"version": VERSION, "signal": name, "token_count": str(collector.counts[name]), "dtype": "FP64"},
            )
        del collector
        state["covariance_sha256"] = {
            name: sha256_file(work / "covariances" / f"{name}.safetensors") for name in SIGNALS
        }
        state["stage"] = "COVARIANCES_COMPLETE"
        _replace_work_json(work / "resume_state.json", state)

    for name, digest in state["covariance_sha256"].items():
        if sha256_file(work / "covariances" / f"{name}.safetensors") != digest:
            fail(f"PCA resume covariance hash changed: {name}")
    covariance_members = {
        path.name for path in (work / "covariances").iterdir()
        if path.is_file() and not _is_linklike(path)
    }
    if covariance_members != {f"{name}.safetensors" for name in SIGNALS}:
        fail("PCA resume covariance membership changed")

    # Any complete unrecorded basis file is adopted on resume only after full
    # semantic validation below; a partial Safetensors file fails closed.
    completed = dict(state["completed_bases"])
    existing = {path.stem for path in (work / "bases").glob("*.safetensors")}
    if any(_is_linklike(path) or not path.is_file() for path in (work / "bases").iterdir()):
        fail("PCA resume basis directory contains a non-regular member")
    if {path.name for path in (work / "bases").iterdir()} != {f"{name}.safetensors" for name in existing}:
        fail("PCA resume basis directory contains an unexpected artifact")
    if not existing.issubset(SIGNALS):
        fail("PCA resume contains an unknown basis artifact")
    if not set(completed).issubset(existing):
        fail("PCA resume state references a missing basis artifact")
    for name in SIGNALS:
        basis_path = work / "bases" / f"{name}.safetensors"
        if name in completed:
            if sha256_file(basis_path) != completed[name]:
                fail(f"PCA resume basis hash changed: {name}")
            _read_basis(safe_open, torch, basis_path, name)
            continue
        if name in existing:
            # Crash window after the durable tensor write but before state
            # replacement: recompute and require byte-identical semantics
            # before adopting the otherwise unbound artifact.
            covariance = _read_covariance(
                safe_open, torch, work / "covariances" / f"{name}.safetensors", name
            )
            expected_values, expected_basis, expected_damping = pca_from_covariance(torch, covariance)
            basis, eigenvalues, damping = _read_basis(safe_open, torch, basis_path, name)
            if not (
                torch.equal(basis, expected_basis)
                and torch.equal(eigenvalues, expected_values)
                and torch.equal(damping, expected_damping)
            ):
                fail(f"unrecorded PCA basis is not an exact deterministic replay: {name}")
            del covariance, expected_values, expected_basis, expected_damping, basis, eigenvalues, damping
            completed[name] = sha256_file(basis_path)
            state["stage"] = "EIGENDECOMPOSITION"
            state["completed_bases"] = dict(completed)
            _replace_work_json(work / "resume_state.json", state)
            continue
        covariance = _read_covariance(
            safe_open, torch, work / "covariances" / f"{name}.safetensors", name
        )
        eigenvalues, basis, damping = pca_from_covariance(torch, covariance)
        _save_tensor_file(
            save_file,
            basis_path,
            {"basis": basis, "damping": damping, "eigenvalues": eigenvalues},
            {"version": VERSION, "signal": name, "orientation": "pure_pca", "sign": "first_max_abs_pivot"},
        )
        completed[name] = sha256_file(basis_path)
        state["stage"] = "EIGENDECOMPOSITION"
        state["completed_bases"] = dict(completed)
        _replace_work_json(work / "resume_state.json", state)
        del covariance, eigenvalues, basis, damping
        gc.collect()

    signal_records: dict[str, Any] = {}
    for name in SIGNALS:
        covariance_path = work / "covariances" / f"{name}.safetensors"
        basis_path = work / "bases" / f"{name}.safetensors"
        basis, eigenvalues, damping = _read_basis(safe_open, torch, basis_path, name)
        prefix_hashes = {str(width): tensor_sha256(torch, basis[:, :width]) for width in RETAINED_DIMENSIONS}
        signal_records[name] = {
            "covariance_file": covariance_path.relative_to(work).as_posix(),
            "covariance_sha256": sha256_file(covariance_path),
            "basis_file": basis_path.relative_to(work).as_posix(),
            "basis_sha256": sha256_file(basis_path),
            "sample_token_count": CALIBRATION_ROWS * SEQUENCE_LENGTH,
            "damping_hex": float(damping.item()).hex(),
            "eigenvalues_sha256": tensor_sha256(torch, eigenvalues),
            "prefix_sha256": prefix_hashes,
        }
    plan = {
        "version": VERSION,
        "scope": "PCA_TRANSFORMATION_PLAN_ONLY",
        "mechanism": "slicegpt_residual_width_pca",
        "calibration_seed": CALIBRATION_SEED,
        "model_execution_dtype": "BF16",
        "statistics_dtype": "FP64",
        "covariance": {
            "centering": "none_upstream_second_moment",
            "mask": "sealed_all_one_attention_mask",
            "damping": "0.01 * mean(diag(covariance))",
            "accumulation": "sum_batch_token_outer_products",
        },
        "orientation": "pure_pca_first_max_abs_sign_no_random_rotation",
        "round_interval": ROUND_INTERVAL,
        "signals": signal_records,
        "layers": layer_triplets(),
        "doses": [
            {"fraction": fraction, "retained_dimension": dimension, "plan_only": True}
            for fraction, dimension in zip(FRACTIONS, RETAINED_DIMENSIONS, strict=True)
        ],
        "plan_modes": {
            "full_width_identity": {
                "basis": "implicit_exact_identity",
                "status": "PREPARED_NOT_EXECUTED",
            },
            "full_width_pca_nonidentity": {
                "basis": "archived_clean_boundary_pca",
                "status": "PREPARED_NOT_EXECUTED",
            },
            "reduced_width": {
                "basis": "requires_post_capability_sequential_per_dose_recalibration",
                "retained_dimensions_are": "frozen_targets_and_prefix_hashes_only",
                "status": "NOT_PREPARED_NOT_AUTHORIZED",
            },
        },
        "source": source_record,
        "nonzero_slice_authorized": False,
        "probe2_verdict": None,
        "transformation_executed": False,
    }
    validate_plan_document(plan)
    _write_or_require_exact(work / "plan.json", canonical_json_bytes(plan))
    state = {
        "version": WORK_VERSION,
        "stage": "COMPLETE",
        "signals": list(SIGNALS),
        "covariance_sha256": {
            name: sha256_file(work / "covariances" / f"{name}.safetensors") for name in SIGNALS
        },
        "completed_bases": {
            name: sha256_file(work / "bases" / f"{name}.safetensors") for name in SIGNALS
        },
        "source_sha256": sha256_file(work / "source.json"),
    }
    _replace_work_json(work / "resume_state.json", state)
    _seal_work_archive(work)
    if output.exists():
        fail("PCA archive appeared concurrently")
    _publish_no_replace(work, output)
    return validate_archive(output)


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    sub = result.add_subparsers(dest="command", required=True)
    produce_parser = sub.add_parser("produce")
    produce_parser.add_argument("--repo", type=Path, default=Path.cwd())
    produce_parser.add_argument("--model", type=Path, required=True)
    produce_parser.add_argument("--calibration", type=Path, required=True)
    produce_parser.add_argument("--runtime-archive", type=Path, required=True)
    produce_parser.add_argument("--runtime-lock", type=Path, required=True)
    produce_parser.add_argument("--provenance-spec", type=Path, required=True)
    produce_parser.add_argument("--model-qualification", type=Path, required=True)
    produce_parser.add_argument("--output", type=Path, required=True)
    produce_parser.add_argument("--resume", action="store_true")
    verify = sub.add_parser("verify")
    verify.add_argument("--repo", type=Path, default=Path.cwd())
    verify.add_argument("--archive", type=Path, required=True)
    verify.add_argument("--model", type=Path, required=True)
    verify.add_argument("--calibration", type=Path, required=True)
    verify.add_argument("--runtime-archive", type=Path, required=True)
    verify.add_argument("--runtime-lock", type=Path, required=True)
    verify.add_argument("--provenance-spec", type=Path, required=True)
    verify.add_argument("--model-qualification", type=Path, required=True)
    return result


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    if args.command == "verify":
        if not strict_path(args.archive, "PCA archive", base=strict_path(args.repo, "repository")).exists():
            fail("PCA verify requires an existing immutable archive")
        replay_args = argparse.Namespace(
            repo=args.repo,
            model=args.model,
            calibration=args.calibration,
            runtime_archive=args.runtime_archive,
            runtime_lock=args.runtime_lock,
            provenance_spec=args.provenance_spec,
            model_qualification=args.model_qualification,
            output=args.archive,
            resume=False,
        )
        plan = produce(replay_args)
    else:
        plan = produce(args)
    print(json.dumps({
        "scope": plan["scope"],
        "signals": len(plan["signals"]),
        "nonzero_slice_authorized": False,
        "probe2_verdict": None,
        "transformation_executed": False,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
