"""Seal the full-width/nonidentity Gemma-3 SliceGPT model qualification.

This gate is deliberately narrower than SliceGPT launch authorization.  It
can seal model-level full-width evidence, but it cannot issue a capability for
a reduced residual width.  Native serialization and the seven-target PEFT
roundtrip are a separate gate and therefore remain ``INCOMPLETE`` here.

The expensive observer is expected to run on the frozen v4 host.  It writes a
canonical candidate JSON.  This module independently validates every metric,
revalidates runtime/source/parent/calibration provenance, and creates an
immutable archive.  A candidate miss is archived as adapter-INCOMPLETE; it is
never translated into a scientific SliceGPT FAIL.
"""

from __future__ import annotations

import argparse
import gc
import hashlib
import importlib.machinery
import importlib.util
import json
import math
import os
import stat
import subprocess
import sys
import types
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Iterable, Mapping


VERSION = "slicegpt_gemma3_model_qualification_v4_v1"
ARCHIVE_VERSION = "slicegpt_gemma3_model_qualification_archive_v4_v1"
OBSERVATION_VERSION = "slicegpt_gemma3_model_observation_v4_v1"
HIDDEN_SIZE = 2560
INTERMEDIATE_SIZE = 10240
NUM_LAYERS = 34
NUM_ATTENTION_HEADS = 8
NUM_KEY_VALUE_HEADS = 4
HEAD_DIM = 256
VOCAB_SIZE = 262208
RMS_EPS_TEXT = "0.000001"
QUERY_PRE_ATTN_SCALAR = 256
SLIDING_WINDOW = 1024
LAYER_TYPES = tuple(
    "full_attention" if index in {5, 11, 17, 23, 29} else "sliding_attention"
    for index in range(NUM_LAYERS)
)
CALIBRATION_SEED = 11
PROMPT_COUNT = 196
LOGIT_PROMPT_COUNT = 32
LOGIT_MAX_POSITIONS = 128
LOGIT_COMPARED_POSITIONS = 720
PROMPT_IDS_SHA256 = "150bc5ed2443b17086c4f7fc4dada71f1a960dbc22ef025044053cea4ec4be89"
LOGIT_PROMPT_IDS_SHA256 = "9b674b40eb12465e9b4183deb41fada852f0f3fdee089a695dab68ebccdfd113"
LOGIT_INPUT_SURFACE_SHA256 = "178945c900cd54058802b4d510af67aa5ea1b6e2dabf343f5e4341ddcae1f311"
GENERATION_MAX_NEW_TOKENS = 256
BATCH_SIZE = 8
SEED = 0
ALGEBRA_RTOL_TEXT = "0.00000001"
ALGEBRA_ATOL_TEXT = "0.00000001"
MAX_SCALAR_DELTA_TEXT = "1.0"
MAX_COMPONENT_DELTA_TEXT = "0.02"
MIN_CONTINUATION_MATCH = 194
MIN_TOP1_TEXT = "0.999"
MAX_MEAN_LOGIT_DELTA_TEXT = "0.02"
SOURCE_PATHS = (
    "scripts/qualify_slicegpt_model_adapter_v4.py",
    "scripts/test_qualify_slicegpt_model_adapter_v4.py",
    "scripts/slicegpt_gemma3_adapter_core_v4.py",
    "scripts/test_slicegpt_gemma3_adapter_core_v4.py",
    "scripts/slicegpt_gemma3_text_model_v4.py",
    "scripts/test_slicegpt_gemma3_text_model_v4.py",
    "scripts/qualify_slicegpt_runtime_v4.py",
    "scripts/materialize_slicegpt_calibration_v4.py",
    "scripts/eval_decay_scalar.py",
    "scripts/decay_scalar_normalization.py",
    "docs/V4_SLICEGPT_PROTOCOL.md",
    "data/decay_scalar_prompts.json",
    "data/rehearsal_capability_prompts.json",
    "data/conversational_survival_generations.json",
)
ARCHIVE_MEMBERS = frozenset(
    {
        "observation.json",
        "command.json",
        "qualifier_source.py",
        "COMPLETE.json",
        "MANIFEST.sha256",
    }
)
HEX = frozenset("0123456789abcdef")


class QualificationError(RuntimeError):
    pass


def fail(message: str) -> None:
    raise QualificationError(message)


def _execute_source_module(
    *,
    module_name: str,
    path: Path,
    expected_sha256: str,
    dependencies: Mapping[str, Any] | None = None,
    required_locals: Iterable[str] = (),
) -> Any:
    """Execute one exact source file without trusting import search state.

    Project modules are evidence-producing code.  A clean hash map is not
    sufficient if Python can return a preloaded or search-path-substituted
    module.  This loader reads and compiles the verified bytes itself, exposes
    only explicitly verified dependencies during execution, and then removes
    every temporary canonical name from ``sys.modules``.
    """

    path = Path(os.path.abspath(path))
    if _linklike(path) or any(_linklike(parent) for parent in path.parents):
        fail(f"project module {module_name}: symlink/reparse source forbidden")
    if not path.is_file():
        fail(f"project module {module_name}: source is missing")
    dependencies = dict(dependencies or {})
    guarded_names = {module_name, *dependencies}
    contaminated = sorted(name for name in guarded_names if name in sys.modules)
    if contaminated:
        fail(f"project module namespace is preloaded/contaminated: {contaminated}")
    source = path.read_bytes()
    if sha256_bytes(source) != expected_sha256:
        fail(f"project module {module_name}: source hash differs from committed identity")
    spec = importlib.util.spec_from_file_location(module_name, path)
    if (
        spec is None
        or spec.loader is None
        or spec.origin is None
        or spec.name != module_name
        or spec.submodule_search_locations is not None
        or Path(os.path.abspath(spec.origin)) != path
    ):
        fail(f"project module {module_name}: source specification was substituted")
    loader = spec.loader
    if (
        type(loader) is not importlib.machinery.SourceFileLoader
        or loader.name != module_name
        or Path(os.path.abspath(loader.path)) != path
    ):
        fail(f"project module {module_name}: nonstandard source loader forbidden")
    # Do not call module_from_spec/loader.create_module: even a loader claiming
    # the right origin could execute before the verified bytes are compiled.
    module = types.ModuleType(module_name)
    module.__file__ = str(path)
    module.__loader__ = loader
    module.__package__ = ""
    module.__spec__ = spec
    try:
        for dependency_name, dependency in dependencies.items():
            sys.modules[dependency_name] = dependency
        sys.modules[module_name] = module
        exec(compile(source, str(path), "exec"), module.__dict__)
    except QualificationError:
        raise
    except Exception as exc:
        fail(f"project module {module_name}: exact source execution failed: {exc}")
    finally:
        for name in guarded_names:
            sys.modules.pop(name, None)
    if path.read_bytes() != source or sha256_file(path) != expected_sha256:
        fail(f"project module {module_name}: source changed during execution")
    if (
        Path(os.path.abspath(str(getattr(module, "__file__", "")))) != path
        or getattr(module, "__package__", None) not in {None, ""}
        or getattr(getattr(module, "__spec__", None), "origin", None) != str(path)
    ):
        fail(f"project module {module_name}: executed origin differs from exact source")
    for attribute in required_locals:
        value = getattr(module, attribute, None)
        if not callable(value) or getattr(value, "__module__", None) != module_name:
            fail(f"project module {module_name}: local callable changed: {attribute}")
        code = getattr(value, "__code__", None)
        if code is not None and Path(os.path.abspath(code.co_filename)) != path:
            fail(f"project module {module_name}: callable code origin changed: {attribute}")
    return module


def _bootstrap_runtime_module() -> Any:
    path = Path(__file__).absolute().with_name("qualify_slicegpt_runtime_v4.py")
    if "qualify_slicegpt_runtime_v4" in sys.modules:
        fail("project module namespace is preloaded/contaminated: ['qualify_slicegpt_runtime_v4']")
    source = path.read_bytes()
    return _execute_source_module(
        module_name="_slicegpt_model_gate_runtime_v4",
        path=path,
        expected_sha256=sha256_bytes(source),
        required_locals=(
            "canonical_json_bytes",
            "load_canonical_json",
            "validate_archive",
            "validate_provenance",
            "validate_runtime_observation",
            "capture_live_runtime",
            "_resolve_declared",
        ),
    )


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def exact(value: Any, keys: Iterable[str], label: str) -> dict[str, Any]:
    expected = set(keys)
    if not isinstance(value, dict) or set(value) != expected:
        actual = set(value) if isinstance(value, dict) else set()
        fail(f"{label}: exact schema mismatch; missing={sorted(expected-actual)}, extra={sorted(actual-expected)}")
    return value


def boolean(value: Any, expected: bool, label: str) -> None:
    if value is not expected:
        fail(f"{label}: expected exact boolean {expected}")


def integer(value: Any, label: str, *, expected: int | None = None, minimum: int | None = None) -> int:
    if type(value) is not int:
        fail(f"{label}: expected exact integer")
    if expected is not None and value != expected:
        fail(f"{label}: expected {expected}")
    if minimum is not None and value < minimum:
        fail(f"{label}: expected >= {minimum}")
    return value


def finite(value: Any, label: str) -> Decimal:
    """Require an unaliased, canonical plain-decimal string."""
    if not isinstance(value, str) or not value:
        fail(f"{label}: expected canonical decimal string")
    import re
    if re.fullmatch(r"-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?", value) is None or value == "-0":
        fail(f"{label}: expected canonical plain decimal string")
    try:
        result = Decimal(value)
    except InvalidOperation:
        fail(f"{label}: invalid decimal")
    if not result.is_finite():
        fail(f"{label}: expected finite decimal")
    return result


def text(value: Any, label: str, *, expected: str | None = None) -> str:
    if not isinstance(value, str) or not value:
        fail(f"{label}: expected nonempty string")
    if expected is not None and value != expected:
        fail(f"{label}: expected {expected!r}")
    return value


def digest(value: Any, label: str) -> str:
    if not isinstance(value, str) or len(value) != 64 or any(char not in HEX for char in value):
        fail(f"{label}: expected lowercase SHA-256")
    return value


def digest_map(value: Any, label: str, *, nonempty: bool = True) -> dict[str, str]:
    if not isinstance(value, dict) or (nonempty and not value):
        fail(f"{label}: expected {'nonempty ' if nonempty else ''}hash map")
    result: dict[str, str] = {}
    for key, value_digest in value.items():
        text(key, f"{label}.key")
        result[key] = digest(value_digest, f"{label}[{key!r}]")
    return result


def _canonical_json_bytes(value: Any) -> bytes:
    try:
        return runtime_q.canonical_json_bytes(value)
    except Exception as exc:
        fail(f"noncanonical JSON value: {exc}")


def _load_json(path: Path) -> Any:
    try:
        return runtime_q.load_canonical_json(path)
    except Exception as exc:
        fail(f"cannot load canonical JSON {path}: {exc}")


def _git(repo: Path, *args: str, binary: bool = False) -> str | bytes:
    try:
        result = subprocess.run(
            ["git", *args], cwd=repo, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=not binary,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        fail(f"git {' '.join(args)} failed: {exc}")
    return result.stdout


def _linklike(path: Path) -> bool:
    try:
        info = path.lstat()
    except OSError:
        return False
    attrs = int(getattr(info, "st_file_attributes", 0))
    reparse = int(getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400))
    return stat.S_ISLNK(info.st_mode) or bool(attrs & reparse)


def reject_linklike(path: Path, label: str, *, include_leaf: bool = True) -> Path:
    path = Path(os.path.abspath(path))
    candidates = [path, *path.parents] if include_leaf else list(path.parents)
    for candidate in candidates:
        if candidate.exists() and _linklike(candidate):
            fail(f"{label}: symlink/reparse ancestor forbidden: {candidate}")
    return path


runtime_q = _bootstrap_runtime_module()


def exact_tree(root: Path, label: str) -> dict[str, str]:
    root = reject_linklike(root, label)
    if not root.is_dir():
        fail(f"{label}: expected directory")
    output: dict[str, str] = {}
    for path in sorted(root.rglob("*"), key=lambda item: item.as_posix()):
        reject_linklike(path, label)
        if path.is_dir():
            continue
        if not path.is_file():
            fail(f"{label}: non-regular member {path}")
        relative = path.relative_to(root).as_posix()
        output[relative] = sha256_file(path)
    if not output:
        fail(f"{label}: empty tree")
    return output


def committed_sources(repo: Path) -> tuple[str, dict[str, str]]:
    repo = reject_linklike(repo, "repository")
    head = str(_git(repo, "rev-parse", "HEAD")).strip()
    if len(head) != 40 or any(char not in HEX for char in head):
        fail("repository HEAD is not an exact commit")
    identity: dict[str, str] = {}
    for relative in SOURCE_PATHS:
        path = reject_linklike(repo / relative, f"source {relative}")
        if not path.is_file():
            fail(f"missing source: {relative}")
        try:
            blob = _git(repo, "show", f"HEAD:{relative}", binary=True)
        except QualificationError:
            fail(f"source is not committed at HEAD: {relative}")
        assert isinstance(blob, bytes)
        live = path.read_bytes()
        if live != blob:
            fail(f"source differs from committed HEAD blob: {relative}")
        identity[relative] = sha256_bytes(live)
    return head, identity


PROJECT_MODULE_SOURCES = {
    "slicegpt_gemma3_adapter_core_v4": "scripts/slicegpt_gemma3_adapter_core_v4.py",
    "slicegpt_gemma3_text_model_v4": "scripts/slicegpt_gemma3_text_model_v4.py",
    "decay_scalar_normalization": "scripts/decay_scalar_normalization.py",
    "eval_decay_scalar": "scripts/eval_decay_scalar.py",
}


def _verified_project_modules(
    repo: Path,
    sources: Mapping[str, str],
    requested: Iterable[str],
) -> dict[str, Any]:
    """Load requested observer modules from the exact committed source bytes."""

    requested_set = set(requested)
    unknown = requested_set - set(PROJECT_MODULE_SOURCES)
    if unknown:
        fail(f"unknown project module request: {sorted(unknown)}")
    # Reject contamination across the whole observer namespace, even when a
    # single replay helper is requested.  Otherwise a dependency import added
    # later could silently reuse a caller-supplied object.
    contaminated = sorted(name for name in PROJECT_MODULE_SOURCES if name in sys.modules)
    if contaminated:
        fail(f"project module namespace is preloaded/contaminated: {contaminated}")

    loaded: dict[str, Any] = {}

    def load(name: str) -> Any:
        if name in loaded:
            return loaded[name]
        dependencies: dict[str, Any] = {}
        required: tuple[str, ...]
        if name == "slicegpt_gemma3_text_model_v4":
            dependencies["slicegpt_gemma3_adapter_core_v4"] = load(
                "slicegpt_gemma3_adapter_core_v4"
            )
            required = (
                "Gemma3SliceGPTTextForCausalLMV4",
                "finalize_from_conditional",
                "validate_text_model",
            )
        elif name == "eval_decay_scalar":
            dependencies["decay_scalar_normalization"] = load(
                "decay_scalar_normalization"
            )
            required = (
                "build_prompt_records",
                "compute_text_components",
                "parse_judge_score",
            )
        elif name == "slicegpt_gemma3_adapter_core_v4":
            required = (
                "discover_pinned_gemma3",
                "apply_layer_core",
                "canonicalize_basis_signs",
                "tensor_sha256",
            )
        else:
            required = (
                "load_bidirectional_anchors",
                "normalise_components_bidirectional",
                "bidirectional_policy_fingerprint",
            )
        relative = PROJECT_MODULE_SOURCES[name]
        expected = sources.get(relative)
        if expected is None:
            fail(f"project module {name}: missing committed source identity")
        loaded[name] = _execute_source_module(
            module_name=name,
            path=repo / relative,
            expected_sha256=expected,
            dependencies=dependencies,
            required_locals=required,
        )
        return loaded[name]

    for name in sorted(requested_set):
        load(name)
    return {name: loaded[name] for name in requested_set}


def _verify_bootstrapped_runtime(repo: Path, sources: Mapping[str, str]) -> None:
    relative = "scripts/qualify_slicegpt_runtime_v4.py"
    expected_path = reject_linklike(repo / relative, "runtime qualifier source")
    expected_hash = sources.get(relative)
    if expected_hash is None or sha256_file(expected_path) != expected_hash:
        fail("bootstrapped runtime qualifier differs from committed source identity")
    actual_path = Path(os.path.abspath(str(getattr(runtime_q, "__file__", ""))))
    if actual_path != expected_path:
        fail("executed runtime qualifier path differs from committed source path")
    for attribute in (
        "canonical_json_bytes",
        "load_canonical_json",
        "validate_archive",
        "validate_provenance",
        "validate_runtime_observation",
        "capture_live_runtime",
        "_resolve_declared",
    ):
        value = getattr(runtime_q, attribute, None)
        code = getattr(value, "__code__", None)
        if (
            not callable(value)
            or getattr(value, "__module__", None) != "_slicegpt_model_gate_runtime_v4"
            or code is None
            or Path(os.path.abspath(code.co_filename)) != expected_path
        ):
            fail(f"executed runtime qualifier callable origin changed: {attribute}")


def validate_topology(value: Any) -> bool:
    record = exact(
        value,
        {
            "model_class", "text_only", "hidden_size", "intermediate_size", "layers",
            "query_heads", "kv_heads", "head_dim", "vocab_size", "rms_eps", "tied_embeddings",
            "query_pre_attention_scalar", "sliding_window", "layer_types", "qk_norms_untouched",
        },
        "topology",
    )
    text(record["model_class"], "topology.model_class", expected="Gemma3SliceGPTTextForCausalLMV4")
    boolean(record["text_only"], True, "topology.text_only")
    for name, expected_value in (
        ("hidden_size", HIDDEN_SIZE), ("intermediate_size", INTERMEDIATE_SIZE),
        ("layers", NUM_LAYERS), ("query_heads", NUM_ATTENTION_HEADS),
        ("kv_heads", NUM_KEY_VALUE_HEADS), ("head_dim", HEAD_DIM),
        ("vocab_size", VOCAB_SIZE), ("query_pre_attention_scalar", QUERY_PRE_ATTN_SCALAR),
        ("sliding_window", SLIDING_WINDOW),
    ):
        integer(record[name], f"topology.{name}", expected=expected_value)
    text(record["rms_eps"], "topology.rms_eps", expected=RMS_EPS_TEXT)
    boolean(record["tied_embeddings"], False, "topology.tied_embeddings")
    if type(record["qk_norms_untouched"]) is not bool:
        fail("topology.qk_norms_untouched: expected exact boolean")
    if record["layer_types"] != list(LAYER_TYPES):
        fail("topology.layer_types: exact sliding/full pattern changed")
    return record["qk_norms_untouched"]


def validate_bases(value: Any) -> None:
    record = exact(
        value,
        {"dtype", "width", "construction", "seed", "round_interval", "full_width", "identity_sha256", "records"},
        "bases",
    )
    text(record["dtype"], "bases.dtype", expected="torch.float64")
    integer(record["width"], "bases.width", expected=HIDDEN_SIZE)
    text(record["construction"], "bases.construction", expected="fixed_seed_householder_canonical_sign")
    integer(record["seed"], "bases.seed", expected=4401)
    integer(record["round_interval"], "bases.round_interval", expected=8)
    boolean(record["full_width"], True, "bases.full_width")
    identity_hash = digest(record["identity_sha256"], "bases.identity_sha256")
    rows = record["records"]
    if not isinstance(rows, list) or len(rows) != NUM_LAYERS:
        fail("bases.records: require exactly 34 layer records")
    nonidentity = 0
    previous_output = None
    for index, row_value in enumerate(rows):
        row = exact(row_value, {"layer", "input", "attention", "output", "nonidentity"}, f"bases.records[{index}]")
        integer(row["layer"], f"bases.records[{index}].layer", expected=index)
        for name in ("input", "attention", "output"):
            digest(row[name], f"bases.records[{index}].{name}")
        boolean(row["nonidentity"], True, f"bases.records[{index}].nonidentity")
        nonidentity += 1
        if previous_output is not None and row["input"] != previous_output:
            fail(f"bases.records[{index}]: cross-layer basis discontinuity")
        previous_output = row["output"]
    if rows[0]["input"] != identity_hash:
        fail("bases: embedding boundary input must be exact identity")
    if rows[0]["input"] == rows[0]["attention"] or rows[-1]["output"] == rows[-1]["attention"]:
        fail("bases: boundary layers must exercise nonidentity endpoint transitions")
    if rows[-1]["output"] != identity_hash:
        fail("bases: canonical text model requires an identity final output basis")
    if nonidentity != NUM_LAYERS:
        fail("bases: every layer must exercise a nonidentity basis")


def validate_algebra(value: Any) -> bool:
    record = exact(value, {"rtol", "atol", "random", "captured"}, "algebra")
    text(record["rtol"], "algebra.rtol", expected=ALGEBRA_RTOL_TEXT)
    text(record["atol"], "algebra.atol", expected=ALGEBRA_ATOL_TEXT)
    passed = True
    for surface in ("random", "captured"):
        rows = record[surface]
        if not isinstance(rows, list) or len(rows) != NUM_LAYERS:
            fail(f"algebra.{surface}: require exactly 34 layers")
        for index, row_value in enumerate(rows):
            row = exact(
                row_value,
                {"layer", "pre_attention_max_error", "post_attention_max_error", "attention_residual_max_error",
                 "pre_ff_max_error", "post_ff_max_error", "ff_residual_max_error", "finite"},
                f"algebra.{surface}[{index}]",
            )
            integer(row["layer"], f"algebra.{surface}[{index}].layer", expected=index)
            boolean(row["finite"], True, f"algebra.{surface}[{index}].finite")
            for name in set(row) - {"layer", "finite"}:
                passed &= finite(row[name], f"algebra.{surface}[{index}].{name}") <= Decimal(ALGEBRA_ATOL_TEXT)
    return passed


def validate_hf_paths(value: Any) -> bool:
    record = exact(
        value,
        {"no_cache", "cache_prefill", "cache_decode", "cache_prefill_equal", "cache_decode_equal",
         "greedy_cache", "output_hidden_states",
         "gradient_checkpoint_backward", "captured_activations", "sliding_capture", "full_capture",
         "pixel_values_rejected", "finite"},
        "hf_paths",
    )
    for name, result in record.items():
        if type(result) is not bool:
            fail(f"hf_paths.{name}: expected exact boolean")
    return all(record.values())


def validate_endpoints(value: Any) -> bool:
    record = exact(
        value,
        {"embedding_scale", "embedding_unchanged", "final_norm_affine_removed", "final_multiplier_fused",
         "head_changed", "tied_before", "head_untied_after", "tie_config_disabled",
         "endpoint_logits_finite", "embedding_sha256", "original_final_norm_sha256", "fused_head_sha256",
         "text_model_version", "text_model_source_sha256", "final_fusion_chunk_rows"},
        "endpoints",
    )
    text(record["embedding_scale"], "endpoints.embedding_scale", expected="sqrt(2560)")
    flags = (
        "embedding_unchanged", "final_norm_affine_removed", "final_multiplier_fused", "head_changed",
        "tied_before", "head_untied_after", "tie_config_disabled", "endpoint_logits_finite",
    )
    for name in flags:
        if type(record[name]) is not bool:
            fail(f"endpoints.{name}: expected exact boolean")
    for name in ("embedding_sha256", "original_final_norm_sha256", "fused_head_sha256"):
        digest(record[name], f"endpoints.{name}")
    text(record["text_model_version"], "endpoints.text_model_version", expected="gemma3_slicegpt_text_model_v4_v1_unqualified")
    digest(record["text_model_source_sha256"], "endpoints.text_model_source_sha256")
    integer(record["final_fusion_chunk_rows"], "endpoints.final_fusion_chunk_rows", expected=4096)
    hashes_untied = record["embedding_sha256"] != record["fused_head_sha256"]
    return all(record[name] for name in flags) and hashes_untied


def validate_scalar(value: Any) -> bool:
    record = exact(
        value,
        {"prompt_count", "prompt_ids_sha256", "decoding", "seed", "max_new_tokens", "batch_size",
         "wrong_count", "limited_count", "unparsed_count", "clean_scalar", "transformed_scalar",
         "scalar_delta", "clean_components", "transformed_components", "component_deltas",
         "continuation_equal_count", "clean_continuations_sha256", "transformed_continuations_sha256",
         "normalization_sources", "normalization_policy_fingerprint"},
        "scalar",
    )
    integer(record["prompt_count"], "scalar.prompt_count", expected=PROMPT_COUNT)
    if digest(record["prompt_ids_sha256"], "scalar.prompt_ids_sha256") != PROMPT_IDS_SHA256:
        fail("scalar.prompt_ids_sha256: frozen 196-prompt order changed")
    text(record["decoding"], "scalar.decoding", expected="greedy")
    integer(record["seed"], "scalar.seed", expected=SEED)
    integer(record["max_new_tokens"], "scalar.max_new_tokens", expected=GENERATION_MAX_NEW_TOKENS)
    integer(record["batch_size"], "scalar.batch_size", expected=BATCH_SIZE)
    counts_ok = True
    for name in ("wrong_count", "limited_count", "unparsed_count"):
        if integer(record[name], f"scalar.{name}", minimum=0) != 0:
            counts_ok = False
    scalar_delta = finite(record["scalar_delta"], "scalar.scalar_delta")
    clean_scalar = finite(record["clean_scalar"], "scalar.clean_scalar")
    transformed_scalar = finite(record["transformed_scalar"], "scalar.transformed_scalar")
    if abs(abs(transformed_scalar - clean_scalar) - scalar_delta) > Decimal("0.000000000001"):
        fail("scalar.scalar_delta: inconsistent with recorded scalars")
    components_ok = True
    for key in ("clean_components", "transformed_components", "component_deltas"):
        component = exact(record[key], {"R", "D", "J", "F"}, f"scalar.{key}")
        for name, number in component.items():
            finite(number, f"scalar.{key}.{name}")
    for name in ("R", "D", "J", "F"):
        expected_delta = abs(Decimal(record["transformed_components"][name]) - Decimal(record["clean_components"][name]))
        actual_delta = Decimal(record["component_deltas"][name])
        if abs(expected_delta - actual_delta) > Decimal("0.000000000001"):
            fail(f"scalar.component_deltas.{name}: inconsistent")
        components_ok &= actual_delta <= Decimal(MAX_COMPONENT_DELTA_TEXT)
    continuations = integer(record["continuation_equal_count"], "scalar.continuation_equal_count", minimum=0)
    if continuations > PROMPT_COUNT:
        fail("scalar.continuation_equal_count: exceeds prompt count")
    digest(record["clean_continuations_sha256"], "scalar.clean_continuations_sha256")
    digest(record["transformed_continuations_sha256"], "scalar.transformed_continuations_sha256")
    sources = exact(
        record["normalization_sources"], {"baseline", "terminal", "ladder"},
        "scalar.normalization_sources",
    )
    for role, source_value in sources.items():
        source = exact(source_value, {"path", "sha256"}, f"scalar.normalization_sources.{role}")
        relative = text(source["path"], f"scalar.normalization_sources.{role}.path")
        if Path(relative).is_absolute() or "\\" in relative or relative != Path(relative).as_posix() or ".." in Path(relative).parts:
            fail(f"scalar.normalization_sources.{role}.path: noncanonical relative path")
        digest(source["sha256"], f"scalar.normalization_sources.{role}.sha256")
    digest(record["normalization_policy_fingerprint"], "scalar.normalization_policy_fingerprint")
    return counts_ok and scalar_delta <= Decimal(MAX_SCALAR_DELTA_TEXT) and components_ok and continuations >= MIN_CONTINUATION_MATCH


def validate_logits(value: Any) -> bool:
    record = exact(
        value,
        {"prompt_count", "prompt_ids_sha256", "input_surface_sha256", "max_positions",
         "compared_positions", "vocab_size", "top1_equal", "top1_agreement",
         "mean_absolute_float32_delta", "finite"},
        "logits",
    )
    integer(record["prompt_count"], "logits.prompt_count", expected=LOGIT_PROMPT_COUNT)
    if digest(record["prompt_ids_sha256"], "logits.prompt_ids_sha256") != LOGIT_PROMPT_IDS_SHA256:
        fail("logits.prompt_ids_sha256: frozen 32-prompt order changed")
    if digest(record["input_surface_sha256"], "logits.input_surface_sha256") != LOGIT_INPUT_SURFACE_SHA256:
        fail("logits.input_surface_sha256: frozen tokenizer IDs/masks changed")
    integer(record["max_positions"], "logits.max_positions", expected=LOGIT_MAX_POSITIONS)
    positions = integer(record["compared_positions"], "logits.compared_positions", expected=LOGIT_COMPARED_POSITIONS)
    integer(record["vocab_size"], "logits.vocab_size", expected=VOCAB_SIZE)
    equal = integer(record["top1_equal"], "logits.top1_equal", minimum=0)
    if equal > positions:
        fail("logits.top1_equal: exceeds compared positions")
    agreement = finite(record["top1_agreement"], "logits.top1_agreement")
    if abs(agreement - (Decimal(equal) / Decimal(positions))) > Decimal("0.000000000000001"):
        fail("logits.top1_agreement: inconsistent numerator/denominator")
    delta = finite(record["mean_absolute_float32_delta"], "logits.mean_absolute_float32_delta")
    boolean(record["finite"], True, "logits.finite")
    return agreement >= Decimal(MIN_TOP1_TEXT) and delta <= Decimal(MAX_MEAN_LOGIT_DELTA_TEXT)


def validate_provenance_record(value: Any) -> None:
    record = exact(
        value,
        {"repo_commit", "committed_sources", "runtime_archive_sha256", "runtime_identity_fingerprint",
         "parent_weight_sha256", "parent_support_sha256", "parent_fingerprint", "calibration_seed",
         "calibration_fingerprint", "calibration_complete_sha256", "clean_ruler_files_sha256",
         "clean_ruler_fingerprint"},
        "provenance",
    )
    if len(text(record["repo_commit"], "provenance.repo_commit")) != 40:
        fail("provenance.repo_commit: expected commit")
    if set(digest_map(record["committed_sources"], "provenance.committed_sources")) != set(SOURCE_PATHS):
        fail("provenance.committed_sources: exact source set mismatch")
    digest_map(record["runtime_archive_sha256"], "provenance.runtime_archive_sha256")
    digest(record["runtime_identity_fingerprint"], "provenance.runtime_identity_fingerprint")
    digest_map(record["parent_weight_sha256"], "provenance.parent_weight_sha256")
    digest_map(record["parent_support_sha256"], "provenance.parent_support_sha256")
    digest(record["parent_fingerprint"], "provenance.parent_fingerprint")
    integer(record["calibration_seed"], "provenance.calibration_seed", expected=CALIBRATION_SEED)
    digest(record["calibration_fingerprint"], "provenance.calibration_fingerprint")
    digest(record["calibration_complete_sha256"], "provenance.calibration_complete_sha256")
    digest_map(record["clean_ruler_files_sha256"], "provenance.clean_ruler_files_sha256")
    digest(record["clean_ruler_fingerprint"], "provenance.clean_ruler_fingerprint")


def validate_observation(value: Any) -> dict[str, Any]:
    observation = exact(
        value,
        {"version", "status", "scope", "probe2_verdict", "nonzero_slice_authorized",
         "model_level_gates_passed", "serialization_peft", "topology", "bases", "algebra",
         "hf_paths", "endpoints", "scalar", "logits", "provenance"},
        "observation",
    )
    text(observation["version"], "observation.version", expected=OBSERVATION_VERSION)
    text(observation["scope"], "observation.scope", expected="FULL_WIDTH_NONIDENTITY_MODEL_QUALIFICATION_ONLY")
    if observation["probe2_verdict"] is not None:
        fail("observation.probe2_verdict: this gate cannot issue a scientific verdict")
    boolean(observation["nonzero_slice_authorized"], False, "observation.nonzero_slice_authorized")
    serialization = exact(
        observation["serialization_peft"],
        {"status", "native_sharded_safetensors", "project_loader_roundtrip", "bit_identical_state",
         "byte_identical_generations", "seven_target_lora", "merge_reload_scalar"},
        "serialization_peft",
    )
    text(serialization["status"], "serialization_peft.status", expected="INCOMPLETE_SEPARATE_GATE")
    for name in set(serialization) - {"status"}:
        boolean(serialization[name], False, f"serialization_peft.{name}")
    topology_pass = validate_topology(observation["topology"])
    validate_bases(observation["bases"])
    algebra_pass = validate_algebra(observation["algebra"])
    hf_pass = validate_hf_paths(observation["hf_paths"])
    endpoint_pass = validate_endpoints(observation["endpoints"])
    model_pass = all((topology_pass, algebra_pass, hf_pass, endpoint_pass, validate_scalar(observation["scalar"]), validate_logits(observation["logits"])))
    validate_provenance_record(observation["provenance"])
    if (
        observation["endpoints"]["text_model_source_sha256"]
        != observation["provenance"]["committed_sources"].get(
            "scripts/slicegpt_gemma3_text_model_v4.py"
        )
    ):
        fail("endpoints.text_model_source_sha256: differs from committed source binding")
    boolean(observation["model_level_gates_passed"], model_pass, "observation.model_level_gates_passed")
    expected_status = "INCOMPLETE_SERIALIZATION_AND_PEFT" if model_pass else "INCOMPLETE_MODEL_LEVEL_QUALIFICATION"
    text(observation["status"], "observation.status", expected=expected_status)
    return observation


def decimal_text(value: Any) -> str:
    number = Decimal(str(float(value)))
    if not number.is_finite():
        fail("cannot serialize non-finite measurement")
    rendered = format(number, "f")
    if "." in rendered:
        rendered = rendered.rstrip("0").rstrip(".")
    return "0" if rendered in {"", "-0"} else rendered


def _fixed_bases(torch: Any, core: Any, device: Any) -> tuple[list[Any], list[dict[str, Any]]]:
    """Construct three dense fixed-seed full-width Householder products."""
    generator = torch.Generator(device=device)
    generator.manual_seed(4401)
    identity = torch.eye(HIDDEN_SIZE, dtype=torch.float64, device=device)
    unique = []
    for _ in range(3):
        basis = identity.clone()
        for _reflector in range(8):
            vector = torch.randn(HIDDEN_SIZE, dtype=torch.float64, device=device, generator=generator)
            vector = vector / torch.linalg.vector_norm(vector)
            basis = basis - 2.0 * (basis @ vector).unsqueeze(1) * vector.unsqueeze(0)
        basis = core.canonicalize_basis_signs(basis)
        core.validate_basis(basis, HIDDEN_SIZE, label="qualification basis")
        if core.is_exact_identity_basis(basis, HIDDEN_SIZE):
            fail("fixed full-width qualification basis unexpectedly became identity")
        unique.append(basis)
    residual = (
        [identity]
        + [unique[index % 3] for index in range(NUM_LAYERS - 1)]
        + [identity]
    )
    triplets, records = [], []
    for index in range(NUM_LAYERS):
        attention = unique[(index + 1) % 3]
        triplet = (residual[index], attention, residual[index + 1])
        triplets.append(triplet)
        records.append(
            {
                "layer": index,
                "input": core.tensor_sha256(triplet[0]),
                "attention": core.tensor_sha256(triplet[1]),
                "output": core.tensor_sha256(triplet[2]),
                "nonidentity": True,
            }
        )
    return triplets, records


def _install_full_width_model(torch: Any, core: Any, text_model: Any, model: Any, triplets: list[Any]) -> tuple[Any, tuple[Any, ...], dict[str, Any]]:
    """Stream transformed layers into the canonical text-only model boundary."""
    discovered = core.discover_pinned_gemma3(model)
    if len(triplets) != NUM_LAYERS or not core.is_exact_identity_basis(triplets[0][0], HIDDEN_SIZE):
        fail("full-width model endpoint requires 34 layers and identity embedding input")
    if not core.is_exact_identity_basis(triplets[-1][2], HIDDEN_SIZE):
        fail("canonical text model requires an identity final output basis")
    for index in range(NUM_LAYERS - 1):
        if not torch.equal(triplets[index][2], triplets[index + 1][0]):
            fail(f"full-width cross-layer basis discontinuity after layer {index}")
    language_model = discovered.language_model
    embedding = discovered.embed_tokens
    original_norm = discovered.final_norm
    original_head = discovered.lm_head
    del discovered
    reports = []
    # Replace one source layer at a time.  Each core transform is off-object
    # and atomic; once installed, the source layer can be released before the
    # next 4B-scale clone is built.
    for index, triplet in enumerate(triplets):
        layer = language_model.layers[index]
        wrapped, report = core.apply_layer_core(
            layer, *triplet,
            hidden_size=HIDDEN_SIZE, intermediate_size=INTERMEDIATE_SIZE,
            q_width=NUM_ATTENTION_HEADS * HEAD_DIM,
            kv_width=NUM_KEY_VALUE_HEADS * HEAD_DIM, head_dim=HEAD_DIM,
        )
        if report.layer_index != index or report.retained_dimension != HIDDEN_SIZE:
            fail("full-width layer report changed")
        language_model.layers[index] = wrapped
        reports.append(report)
        del layer, wrapped
        if (index + 1) % 4 == 0:
            torch.cuda.empty_cache()
    dimensions = text_model.full_width_dimensions()
    result = text_model.finalize_from_conditional(
        model, residual_dimensions=dimensions, chunk_rows=4096
    )
    text_model.validate_text_model(result)
    endpoint = {
        "original_final_norm_sha256": core.tensor_sha256(original_norm.weight),
        "original_head_sha256": core.tensor_sha256(original_head.weight),
        "fused_head_sha256": core.tensor_sha256(result.lm_head.weight),
        "final_norm_affine_removed": not any(True for _ in result.model.norm.parameters()),
        "head_untied_after": result.model.embed_tokens.weight is not result.lm_head.weight,
        "tie_config_disabled": result.config.tie_word_embeddings is False,
    }
    if result.model.embed_tokens is not embedding:
        fail("canonical text extraction replaced the source embedding object")
    return result, tuple(reports), endpoint


def _rms(torch: Any, value: Any) -> Any:
    return value * torch.rsqrt(value.square().mean(dim=-1, keepdim=True) + 1e-6)


def _max_error(torch: Any, left: Any, right: Any) -> float:
    if not bool(torch.isfinite(left).all().item()) or not bool(torch.isfinite(right).all().item()):
        return math.inf
    return float((left - right).abs().max().item())


def _layer_algebra_row(torch: Any, layer: Any, bases: tuple[Any, Any, Any], values: Mapping[str, Any], index: int) -> dict[str, Any]:
    qi, qa, qo = bases
    device = layer.self_attn.q_proj.weight.device
    qi, qa, qo = (basis.to(device=device, dtype=torch.float64) for basis in (qi, qa, qo))
    x = values["input"].to(device=device, dtype=torch.float64)
    attn_branch = values["attention_branch"].to(device=device, dtype=torch.float64)
    after_attention = values["after_attention"].to(device=device, dtype=torch.float64)
    ff_branch = values["ff_branch"].to(device=device, dtype=torch.float64)

    def pre_error(source: Any, norm: Any, projection: Any, basis: Any) -> float:
        weight = projection.weight.double()
        scale = 1.0 + norm.weight.double()
        original = (_rms(torch, source) * scale) @ weight.transpose(0, 1)
        fused = (weight * scale.unsqueeze(0)) @ basis
        transformed = _rms(torch, source @ basis) @ fused.transpose(0, 1)
        return _max_error(torch, original, transformed)

    def post_values(branch: Any, norm: Any, basis: Any) -> tuple[Any, Any, float]:
        scale = 1.0 + norm.weight.double()
        original = _rms(torch, branch) * scale
        dense = basis.transpose(0, 1) @ (scale.unsqueeze(1) * basis)
        transformed = _rms(torch, branch @ basis) @ dense
        expected = original @ basis
        return original, transformed, _max_error(torch, expected, transformed)

    attention_original, attention_transformed, attention_post_error = post_values(
        attn_branch, layer.post_attention_layernorm, qa
    )
    attention_expected = (x + attention_original) @ qa
    attention_actual = x @ qi @ (qi.transpose(0, 1) @ qa) + attention_transformed
    ff_original, ff_transformed, ff_post_error = post_values(
        ff_branch, layer.post_feedforward_layernorm, qo
    )
    ff_expected = (after_attention + ff_original) @ qo
    ff_actual = after_attention @ qa @ (qa.transpose(0, 1) @ qo) + ff_transformed
    errors = {
        "pre_attention_max_error": pre_error(x, layer.input_layernorm, layer.self_attn.q_proj, qi),
        "post_attention_max_error": attention_post_error,
        "attention_residual_max_error": _max_error(torch, attention_expected, attention_actual),
        "pre_ff_max_error": pre_error(after_attention, layer.pre_feedforward_layernorm, layer.mlp.gate_proj, qa),
        "post_ff_max_error": ff_post_error,
        "ff_residual_max_error": _max_error(torch, ff_expected, ff_actual),
    }
    return {
        "layer": index,
        **{name: decimal_text(value) for name, value in errors.items()},
        "finite": all(math.isfinite(value) for value in errors.values()),
    }


def _capture_layer_values(torch: Any, model: Any, inputs: Mapping[str, Any]) -> list[dict[str, Any]]:
    backbone = getattr(model, "model", None)
    language = getattr(backbone, "language_model", backbone)
    if language is None or len(getattr(language, "layers", ())) != NUM_LAYERS:
        fail("captured-activation model is not the exact Gemma text surface")
    captured: list[dict[str, Any]] = [dict() for _ in range(NUM_LAYERS)]
    handles = []

    def save(index: int, name: str):
        def hook(_module: Any, args: tuple[Any, ...]) -> None:
            tensor = args[0][0:1, 0:1].detach().to(device="cpu", dtype=torch.float64).clone()
            captured[index][name] = tensor
        return hook

    for index, layer in enumerate(language.layers):
        handles.extend(
            [
                layer.register_forward_pre_hook(save(index, "input")),
                layer.post_attention_layernorm.register_forward_pre_hook(save(index, "attention_branch")),
                layer.pre_feedforward_layernorm.register_forward_pre_hook(save(index, "after_attention")),
                layer.post_feedforward_layernorm.register_forward_pre_hook(save(index, "ff_branch")),
            ]
        )
    try:
        with torch.inference_mode():
            output = model(**inputs, use_cache=False, output_hidden_states=True, return_dict=True)
        if len(output.hidden_states) != NUM_LAYERS + 1:
            fail("real HF output_hidden_states path did not return 35 states")
    finally:
        for handle in handles:
            handle.remove()
    required = {"input", "attention_branch", "after_attention", "ff_branch"}
    if any(set(row) != required for row in captured):
        fail("captured-activation hook surface is incomplete")
    return captured


def _random_layer_values(torch: Any, device: Any, index: int) -> dict[str, Any]:
    generator = torch.Generator(device=device)
    generator.manual_seed(9000 + index)
    shape = (1, 1, HIDDEN_SIZE)
    return {
        name: torch.randn(shape, dtype=torch.float64, device=device, generator=generator)
        for name in ("input", "attention_branch", "after_attention", "ff_branch")
    }


def _render_inputs(torch: Any, tokenizer: Any, prompts: list[str], device: Any) -> tuple[dict[str, Any], list[str]]:
    rendered = [
        tokenizer.apply_chat_template(
            [{"role": "user", "content": prompt}], tokenize=False, add_generation_prompt=True
        )
        for prompt in prompts
    ]
    encoded = tokenizer(rendered, padding=True, add_special_tokens=False, return_tensors="pt")
    if set(encoded) != {"input_ids", "attention_mask"}:
        fail("text-only tokenizer emitted an unexpected model input")
    return {key: value.to(device) for key, value in encoded.items()}, rendered


def _generate(torch: Any, model: Any, tokenizer: Any, prompts: list[str], device: Any, *, max_new_tokens: int = GENERATION_MAX_NEW_TOKENS) -> tuple[list[str], list[list[int]], int, int]:
    texts, token_rows = [], []
    wrong_count = limited_count = 0
    eos_value = getattr(getattr(model, "generation_config", None), "eos_token_id", None)
    if eos_value is None:
        eos_value = getattr(model.config, "eos_token_id", None)
    eos_ids = {eos_value} if type(eos_value) is int else set(eos_value or [])
    if not eos_ids or any(type(value) is not int for value in eos_ids):
        fail("generation EOS identity is missing or aliased")
    for start in range(0, len(prompts), BATCH_SIZE):
        inputs, _ = _render_inputs(torch, tokenizer, prompts[start : start + BATCH_SIZE], device)
        with torch.inference_mode():
            generated = model.generate(
                **inputs, do_sample=False, use_cache=True, max_new_tokens=max_new_tokens
            )
        new = generated[:, inputs["input_ids"].shape[1] :].detach().cpu()
        prefix = generated[:, : inputs["input_ids"].shape[1]]
        wrong_count += int((prefix != inputs["input_ids"]).any(dim=1).sum().item())
        for row in new:
            raw_ids = [int(item) for item in row.tolist()]
            stop = next((index + 1 for index, token in enumerate(raw_ids) if token in eos_ids), None)
            ids = raw_ids if stop is None else raw_ids[:stop]
            limited_count += int(stop is None and len(raw_ids) == max_new_tokens)
            token_rows.append(ids)
            texts.append(tokenizer.decode(ids, skip_special_tokens=True).strip())
    if len(texts) != len(prompts):
        fail("generation count differs from prompt count")
    return texts, token_rows, wrong_count, limited_count


def _component_record(eval_module: Any, normalization: Any, tokenizer: Any, records: list[dict[str, Any]], generations: list[str], judge_scores: list[int | None], anchors: tuple[Any, Any, Any]) -> tuple[dict[str, float], float]:
    rows = [dict(record, generation=generation) for record, generation in zip(records, generations, strict=True)]
    eval_module.compute_text_components(rows, tokenizer)
    for row, score in zip(rows, judge_scores, strict=True):
        row["judge_score"] = score
    if any(score is None for score in judge_scores):
        fail("clean judge produced an unparsed scalar score")
    components = {
        "R": sum(row["seq_rep_4"] for row in rows) / len(rows),
        "D": 1.0 - sum(row["distinct_2_at_128"] for row in rows) / len(rows),
        "J": 1.0 - (sum(int(score) for score in judge_scores if score is not None) / len(rows)) / 5.0,
        "F": 1.0 - sum(row["token_f1"] for row in rows if row["set"] == "factual") / 40.0,
    }
    normalised, scalar, _directions = normalization.normalise_components_bidirectional(
        components, anchors[0], anchors[1], anchors[2]
    )
    if scalar is None or any(normalised[name] is None for name in ("R", "D", "J", "F")):
        fail("scalar normalization did not produce four finite components")
    return normalised, float(scalar)


def _prompt_records(repo: Path, eval_module: Any) -> list[dict[str, Any]]:
    from types import SimpleNamespace
    args = SimpleNamespace(
        capability_prompts=str(repo / "data/rehearsal_capability_prompts.json"),
        survival_prompts=str(repo / "data/conversational_survival_generations.json"),
        prompts=str(repo / "data/decay_scalar_prompts.json"),
        limit=None,
    )
    records = eval_module.build_prompt_records(args)
    if len(records) != PROMPT_COUNT or len({row["id"] for row in records}) != PROMPT_COUNT:
        fail("frozen scalar prompt surface is not exactly 196 unique IDs")
    return records


def observe_live(
    *, repo: Path, model_path: Path, runtime_archive: Path, runtime_lock: Path,
    provenance_spec: Path, baseline: Path, terminal: Path, ladder: Path, output: Path,
) -> dict[str, Any]:
    """Run the expensive real-HF full-width observer and write a fresh candidate."""
    repo = reject_linklike(repo, "repository")
    output = reject_linklike(output if output.is_absolute() else repo / output, "candidate", include_leaf=False)
    if output.exists() or output.suffix != ".json":
        fail("live candidate must be a fresh JSON path")
    try:
        output_relative = output.relative_to(repo)
    except ValueError:
        fail("live candidate must be under repository derisk")
    folded_output = [part.casefold() for part in output_relative.parts]
    if len(folded_output) < 2 or folded_output[0] != "derisk" or ".git" in folded_output or "vendor" in folded_output:
        fail("live candidate must be a named derisk descendant, never .git/vendor")
    head, sources = committed_sources(repo)
    _verify_bootstrapped_runtime(repo, sources)
    try:
        runtime_qualification = runtime_q.validate_archive(runtime_archive)
        spec, validated_head = runtime_q.validate_provenance(
            repo, runtime_q.load_canonical_json(provenance_spec), runtime_lock, provenance_spec
        )
    except Exception as exc:
        fail(f"cannot revalidate frozen runtime/provenance before observation: {exc}")
    if validated_head != head:
        fail("source and provenance commits differ")
    declared_parent = runtime_q._resolve_declared(repo, spec["parent_model"]["root"], "parent model")
    if reject_linklike(model_path, "parent model") != declared_parent:
        fail("live model path differs from sealed parent")
    ruler_root = runtime_q._resolve_declared(repo, spec["clean_ruler"]["root"], "clean ruler")
    normalization_paths = {"baseline": baseline, "terminal": terminal, "ladder": ladder}
    normalization_sources = {}
    for name, path in normalization_paths.items():
        path = reject_linklike(path, f"{name} normalization source")
        try:
            relative = path.relative_to(ruler_root).as_posix()
        except ValueError:
            fail(f"{name} normalization source is outside sealed clean ruler")
        if spec["clean_ruler"]["files_sha256"].get(relative) != sha256_file(path):
            fail(f"{name} normalization source is not a sealed clean-ruler member")
        normalization_sources[name] = {"path": relative, "sha256": sha256_file(path)}

    import torch
    project_modules = _verified_project_modules(
        repo,
        sources,
        {
            "slicegpt_gemma3_adapter_core_v4",
            "slicegpt_gemma3_text_model_v4",
            "eval_decay_scalar",
            "decay_scalar_normalization",
        },
    )
    core = project_modules["slicegpt_gemma3_adapter_core_v4"]
    text_model = project_modules["slicegpt_gemma3_text_model_v4"]
    eval_module = project_modules["eval_decay_scalar"]
    normalization = project_modules["decay_scalar_normalization"]
    from transformers import AutoTokenizer, Gemma3ForConditionalGeneration

    live_runtime = runtime_q.validate_runtime_observation(runtime_q.capture_live_runtime())
    archived_runtime = runtime_q.load_canonical_json(runtime_archive / "runtime_observation.json")
    if live_runtime != archived_runtime:
        fail("live runtime drifted before model qualification")
    torch.manual_seed(SEED)
    torch.cuda.manual_seed_all(SEED)
    device = torch.device("cuda", 0)
    tokenizer = AutoTokenizer.from_pretrained(declared_parent, local_files_only=True)
    tokenizer.padding_side = "left"
    if tokenizer.pad_token_id is None:
        tokenizer.pad_token_id = tokenizer.eos_token_id
    model = Gemma3ForConditionalGeneration.from_pretrained(
        declared_parent, torch_dtype=torch.bfloat16, device_map={"": 0}, local_files_only=True
    ).eval()
    surface = core.discover_pinned_gemma3(model)
    records = _prompt_records(repo, eval_module)
    prompts = [row["prompt"] for row in records]
    prompt_ids = [row["id"] for row in records]
    if sha256_bytes(_canonical_json_bytes(prompt_ids)) != PROMPT_IDS_SHA256:
        fail("frozen 196-prompt ID/order surface changed")
    first_inputs, _ = _render_inputs(torch, tokenizer, prompts[:1], device)
    captured = _capture_layer_values(torch, model, first_inputs)
    triplets, basis_records = _fixed_bases(torch, core, device)
    identity_basis_sha256 = core.tensor_sha256(triplets[0][0])
    algebra_captured = [
        _layer_algebra_row(torch, layer, triplets[index], captured[index], index)
        for index, layer in enumerate(surface.layers)
    ]
    algebra_random = [
        _layer_algebra_row(
            torch, layer, triplets[index],
            _random_layer_values(torch, layer.self_attn.q_proj.weight.device, index), index,
        )
        for index, layer in enumerate(surface.layers)
    ]
    clean_generations, clean_token_rows, clean_wrong, clean_limited = _generate(
        torch, model, tokenizer, prompts, device
    )
    embedding_before = core.tensor_sha256(surface.embed_tokens.weight)
    final_before = core.tensor_sha256(surface.final_norm.weight)
    head_before = core.tensor_sha256(surface.lm_head.weight)
    tied_before = surface.embed_tokens.weight is surface.lm_head.weight
    del surface
    model, layer_reports, endpoint_application = _install_full_width_model(
        torch, core, text_model, model, triplets
    )
    del triplets, captured
    # The original off-object layer graph was intentionally released above.
    # Return its allocator blocks before loading the independent clean model.
    torch.cuda.empty_cache()
    qk_untouched = all(
        report.protected_qk_sha256 and not report.zero_slice_noop
        for report in layer_reports
    )
    transformed_captured = _capture_layer_values(torch, model, first_inputs)
    transformed_generations, transformed_token_rows, transformed_wrong, transformed_limited = _generate(
        torch, model, tokenizer, prompts, device
    )

    embedding_after = core.tensor_sha256(model.model.embed_tokens.weight)
    head_after = core.tensor_sha256(model.lm_head.weight)
    reference = Gemma3ForConditionalGeneration.from_pretrained(
        declared_parent, torch_dtype=torch.bfloat16, device_map={"": 0}, local_files_only=True
    ).eval()
    pixel_rejected = False
    try:
        model(
            input_ids=torch.ones((1, 1), dtype=torch.long, device=device),
            pixel_values=torch.zeros(1, device=device),
        )
    except RuntimeError as exc:
        pixel_rejected = "text-only" in str(exc)

    top1_equal = compared_positions = 0
    absolute_sum = 0.0
    absolute_count = 0
    logit_surface = []
    for prompt_id, prompt in zip(
        prompt_ids[:LOGIT_PROMPT_COUNT], prompts[:LOGIT_PROMPT_COUNT], strict=True
    ):
        inputs, _ = _render_inputs(torch, tokenizer, [prompt], device)
        logit_surface.append(
            {
                "id": prompt_id,
                "input_ids": inputs["input_ids"][0].detach().cpu().tolist(),
                "attention_mask": inputs["attention_mask"][0].detach().cpu().tolist(),
            }
        )
        with torch.inference_mode():
            clean_logits = reference(**inputs, use_cache=False, return_dict=True).logits[:, :LOGIT_MAX_POSITIONS].float()
            transformed_logits = model(**inputs, use_cache=False, return_dict=True).logits[:, :LOGIT_MAX_POSITIONS].float()
        if clean_logits.shape != transformed_logits.shape or clean_logits.shape[-1] != VOCAB_SIZE:
            fail("frozen logit comparison shape changed")
        delta = (clean_logits - transformed_logits).abs()
        positions = int(clean_logits.shape[0] * clean_logits.shape[1])
        compared_positions += positions
        top1_equal += int((clean_logits.argmax(-1) == transformed_logits.argmax(-1)).sum().item())
        absolute_sum += float(delta.double().sum().item())
        absolute_count += int(delta.numel())
    del clean_logits, transformed_logits, delta
    logit_surface_sha256 = sha256_bytes(_canonical_json_bytes(logit_surface))
    if logit_surface_sha256 != LOGIT_INPUT_SURFACE_SHA256:
        fail("frozen 32-prompt tokenizer ID/mask surface changed")
    if compared_positions != LOGIT_COMPARED_POSITIONS:
        fail("frozen 32-prompt compared-position count changed")

    with torch.inference_mode():
        no_cache = model(**first_inputs, use_cache=False, output_hidden_states=True, return_dict=True)
        prefill = model(**first_inputs, use_cache=True, return_dict=True)
        next_ids = no_cache.logits[:, -1:].argmax(-1)
        decode = model(
            input_ids=next_ids,
            attention_mask=torch.cat(
                [first_inputs["attention_mask"], torch.ones((1, 1), device=device, dtype=first_inputs["attention_mask"].dtype)], dim=1
            ),
            past_key_values=prefill.past_key_values,
            use_cache=True,
            return_dict=True,
        )
        extended_inputs = {
            "input_ids": torch.cat([first_inputs["input_ids"], next_ids], dim=1),
            "attention_mask": torch.cat(
                [first_inputs["attention_mask"], torch.ones((1, 1), device=device, dtype=first_inputs["attention_mask"].dtype)],
                dim=1,
            ),
        }
        full_decode = model(**extended_inputs, use_cache=False, return_dict=True)
    hf_finite = all(
        bool(torch.isfinite(item).all().item())
        for item in (no_cache.logits, prefill.logits, decode.logits, full_decode.logits)
    )
    hidden_ok = len(no_cache.hidden_states) == NUM_LAYERS + 1 and all(
        bool(torch.isfinite(item).all().item()) for item in no_cache.hidden_states
    )
    cache_ok = prefill.past_key_values is not None and decode.past_key_values is not None
    cache_prefill_equal = bool(
        torch.equal(no_cache.logits.argmax(-1), prefill.logits.argmax(-1))
        and torch.allclose(no_cache.logits.float(), prefill.logits.float(), rtol=0.0, atol=0.02)
    )
    cache_decode_equal = bool(
        torch.equal(decode.logits[:, -1].argmax(-1), full_decode.logits[:, -1].argmax(-1))
        and torch.allclose(
            decode.logits[:, -1].float(), full_decode.logits[:, -1].float(), rtol=0.0, atol=0.02
        )
    )

    judge_prompts = [
        eval_module.JUDGE_RUBRIC.format(prompt=row["prompt"], response=response or "(empty)")
        for rows in (clean_generations, transformed_generations)
        for row, response in zip(records, rows, strict=True)
    ]
    judge_text, _, _, _ = _generate(
        torch, reference, tokenizer, judge_prompts, device, max_new_tokens=16
    )
    judge_scores = [eval_module.parse_judge_score(value) for value in judge_text]
    clean_scores, transformed_scores = judge_scores[:PROMPT_COUNT], judge_scores[PROMPT_COUNT:]
    loaded_anchors = normalization.load_bidirectional_anchors(baseline, terminal, ladder)
    anchors = loaded_anchors[:3]
    normalization_policy_fingerprint = normalization.bidirectional_policy_fingerprint(
        *loaded_anchors
    )
    clean_components, clean_scalar = _component_record(
        eval_module, normalization, tokenizer, records, clean_generations, clean_scores, anchors
    )
    transformed_components, transformed_scalar = _component_record(
        eval_module, normalization, tokenizer, records, transformed_generations, transformed_scores, anchors
    )
    # The clean judge/reference has no role in the backward compatibility
    # path.  Release it before allocating BF16 gradients for the text model.
    del reference
    gc.collect()
    torch.cuda.empty_cache()

    checkpoint_ok = False
    try:
        model.gradient_checkpointing_enable()
        model.enable_input_require_grads()
        model.train()
        checkpoint_inputs = {key: value[:, -8:] for key, value in first_inputs.items()}
        checkpoint = model(
            **checkpoint_inputs, labels=checkpoint_inputs["input_ids"], use_cache=False, return_dict=True
        )
        checkpoint.loss.backward()
        checkpoint_ok = bool(torch.isfinite(checkpoint.loss).item()) and any(
            parameter.grad is not None and bool(torch.isfinite(parameter.grad).all().item())
            for parameter in model.parameters()
        )
    finally:
        model.eval()
        model.zero_grad(set_to_none=True)

    unparsed = sum(score is None for score in judge_scores)
    component_deltas = {
        name: abs(float(transformed_components[name]) - float(clean_components[name]))
        for name in ("R", "D", "J", "F")
    }
    scalar_record = {
        "prompt_count": PROMPT_COUNT,
        "prompt_ids_sha256": sha256_bytes(_canonical_json_bytes(prompt_ids)),
        "decoding": "greedy", "seed": SEED,
        "max_new_tokens": GENERATION_MAX_NEW_TOKENS, "batch_size": BATCH_SIZE,
        "wrong_count": clean_wrong + transformed_wrong,
        "limited_count": clean_limited + transformed_limited,
        "unparsed_count": unparsed,
        "clean_scalar": decimal_text(clean_scalar),
        "transformed_scalar": decimal_text(transformed_scalar),
        "scalar_delta": decimal_text(abs(transformed_scalar - clean_scalar)),
        "clean_components": {name: decimal_text(clean_components[name]) for name in clean_components},
        "transformed_components": {name: decimal_text(transformed_components[name]) for name in transformed_components},
        "component_deltas": {name: decimal_text(component_deltas[name]) for name in component_deltas},
        "continuation_equal_count": sum(left == right for left, right in zip(clean_token_rows, transformed_token_rows, strict=True)),
        "clean_continuations_sha256": sha256_bytes(_canonical_json_bytes(clean_token_rows)),
        "transformed_continuations_sha256": sha256_bytes(_canonical_json_bytes(transformed_token_rows)),
        "normalization_sources": normalization_sources,
        "normalization_policy_fingerprint": normalization_policy_fingerprint,
    }
    logits_record = {
        "prompt_count": LOGIT_PROMPT_COUNT,
        "prompt_ids_sha256": sha256_bytes(_canonical_json_bytes(prompt_ids[:LOGIT_PROMPT_COUNT])),
        "input_surface_sha256": logit_surface_sha256,
        "max_positions": LOGIT_MAX_POSITIONS,
        "compared_positions": compared_positions, "vocab_size": VOCAB_SIZE,
        "top1_equal": top1_equal,
        "top1_agreement": decimal_text(Decimal(top1_equal) / Decimal(compared_positions)),
        "mean_absolute_float32_delta": decimal_text(absolute_sum / absolute_count),
        "finite": math.isfinite(absolute_sum),
    }
    hf_record = {
        "no_cache": hf_finite, "cache_prefill": cache_ok, "cache_decode": cache_ok,
        "cache_prefill_equal": cache_prefill_equal,
        "cache_decode_equal": cache_decode_equal,
        "greedy_cache": len(transformed_generations) == PROMPT_COUNT,
        "output_hidden_states": hidden_ok, "gradient_checkpoint_backward": checkpoint_ok,
        "captured_activations": len(transformed_captured) == NUM_LAYERS,
        "sliding_capture": all(
            bool(transformed_captured[index])
            for index in range(NUM_LAYERS)
            if LAYER_TYPES[index] == "sliding_attention"
        ),
        "full_capture": all(
            bool(transformed_captured[index])
            for index in range(NUM_LAYERS)
            if LAYER_TYPES[index] == "full_attention"
        ),
        "pixel_values_rejected": pixel_rejected, "finite": hf_finite,
    }
    observation = {
        "version": OBSERVATION_VERSION,
        "status": "INCOMPLETE_MODEL_LEVEL_QUALIFICATION",
        "scope": "FULL_WIDTH_NONIDENTITY_MODEL_QUALIFICATION_ONLY",
        "probe2_verdict": None, "nonzero_slice_authorized": False,
        "model_level_gates_passed": False,
        "serialization_peft": {
            "status": "INCOMPLETE_SEPARATE_GATE", "native_sharded_safetensors": False,
            "project_loader_roundtrip": False, "bit_identical_state": False,
            "byte_identical_generations": False, "seven_target_lora": False,
            "merge_reload_scalar": False,
        },
        "topology": {
            "model_class": type(model).__name__, "text_only": True,
            "hidden_size": HIDDEN_SIZE, "intermediate_size": INTERMEDIATE_SIZE, "layers": NUM_LAYERS,
            "query_heads": NUM_ATTENTION_HEADS, "kv_heads": NUM_KEY_VALUE_HEADS,
            "head_dim": HEAD_DIM, "vocab_size": VOCAB_SIZE, "rms_eps": RMS_EPS_TEXT,
            "tied_embeddings": False, "query_pre_attention_scalar": QUERY_PRE_ATTN_SCALAR,
            "sliding_window": SLIDING_WINDOW, "layer_types": list(LAYER_TYPES),
            "qk_norms_untouched": qk_untouched,
        },
        "bases": {
            "dtype": "torch.float64", "width": HIDDEN_SIZE,
            "construction": "fixed_seed_householder_canonical_sign", "seed": 4401,
            "round_interval": 8, "full_width": True,
            "identity_sha256": identity_basis_sha256, "records": basis_records,
        },
        "algebra": {"rtol": ALGEBRA_RTOL_TEXT, "atol": ALGEBRA_ATOL_TEXT, "random": algebra_random, "captured": algebra_captured},
        "hf_paths": hf_record,
        "endpoints": {
            "embedding_scale": "sqrt(2560)",
            "embedding_unchanged": embedding_before == embedding_after,
            "final_norm_affine_removed": endpoint_application["final_norm_affine_removed"],
            "final_multiplier_fused": endpoint_application["original_final_norm_sha256"] == final_before,
            "head_changed": head_before != head_after,
            "tied_before": tied_before,
            "head_untied_after": endpoint_application["head_untied_after"],
            "tie_config_disabled": endpoint_application["tie_config_disabled"],
            "endpoint_logits_finite": hf_finite,
            "embedding_sha256": embedding_after,
            "original_final_norm_sha256": final_before,
            "fused_head_sha256": head_after,
            "text_model_version": text_model.VERSION,
            "text_model_source_sha256": sha256_file(repo / "scripts/slicegpt_gemma3_text_model_v4.py"),
            "final_fusion_chunk_rows": 4096,
        },
        "scalar": scalar_record, "logits": logits_record,
        "provenance": {
            "repo_commit": head, "committed_sources": sources,
            "runtime_archive_sha256": exact_tree(runtime_archive, "runtime archive"),
            "runtime_identity_fingerprint": runtime_qualification["identity_fingerprint"],
            "parent_weight_sha256": spec["parent_model"]["weights_sha256"],
            "parent_support_sha256": spec["parent_model"]["support_sha256"],
            "parent_fingerprint": spec["parent_model"]["fingerprint"],
            "calibration_seed": CALIBRATION_SEED,
            "calibration_fingerprint": spec["calibration"]["archives"][str(CALIBRATION_SEED)]["metadata_fingerprint"],
            "calibration_complete_sha256": spec["calibration"]["archives"][str(CALIBRATION_SEED)]["complete_sha256"],
            "clean_ruler_files_sha256": spec["clean_ruler"]["files_sha256"],
            "clean_ruler_fingerprint": spec["clean_ruler"]["fingerprint"],
        },
    }
    algebra_pass = validate_algebra(observation["algebra"])
    model_pass = all((algebra_pass, validate_hf_paths(hf_record), validate_endpoints(observation["endpoints"]), validate_scalar(scalar_record), validate_logits(logits_record), qk_untouched))
    observation["model_level_gates_passed"] = model_pass
    observation["status"] = "INCOMPLETE_SERIALIZATION_AND_PEFT" if model_pass else "INCOMPLETE_MODEL_LEVEL_QUALIFICATION"
    validate_observation(observation)
    output.parent.mkdir(parents=False, exist_ok=True)
    _write_new(output, _canonical_json_bytes(observation))
    return observation


def _manifest_bytes(mapping: Mapping[str, str]) -> bytes:
    return "".join(f"{mapping[name]}  {name}\n" for name in sorted(mapping)).encode("utf-8")


def _parse_manifest(path: Path) -> dict[str, str]:
    if path.read_bytes().replace(b"\r\n", b"\n") != path.read_bytes():
        fail("manifest: CRLF forbidden")
    rows = path.read_text(encoding="utf-8").splitlines()
    result: dict[str, str] = {}
    for row in rows:
        if len(row) < 67 or row[64:66] != "  ":
            fail("manifest: malformed row")
        member = row[66:]
        digest_value = digest(row[:64], f"manifest[{member!r}]")
        if member in result or Path(member).name != member or member in {"", ".", ".."}:
            fail("manifest: noncanonical/duplicate member")
        result[member] = digest_value
    if rows != [f"{result[name]}  {name}" for name in sorted(result)]:
        fail("manifest: rows are not canonical sorted order")
    return result


def validate_archive(root: Path) -> dict[str, Any]:
    root = reject_linklike(root, "model qualification archive")
    if not root.is_dir():
        fail("model qualification archive missing")
    members = {path.name for path in root.iterdir()}
    if members != ARCHIVE_MEMBERS:
        fail(f"archive allowlist mismatch: {sorted(members)}")
    for path in root.iterdir():
        reject_linklike(path, "archive member")
        if not path.is_file():
            fail("archive contains non-regular member")
    manifest = _parse_manifest(root / "MANIFEST.sha256")
    expected = ARCHIVE_MEMBERS - {"MANIFEST.sha256"}
    if set(manifest) != expected:
        fail("manifest membership mismatch")
    for name, expected_hash in manifest.items():
        if sha256_file(root / name) != expected_hash:
            fail(f"archive member hash mismatch: {name}")
    observation = validate_observation(_load_json(root / "observation.json"))
    command = exact(_load_json(root / "command.json"), {"version", "argv", "cwd", "observation_sha256"}, "command")
    text(command["version"], "command.version", expected=VERSION)
    if not isinstance(command["argv"], list) or any(not isinstance(item, str) for item in command["argv"]):
        fail("command.argv: expected exact string list")
    text(command["cwd"], "command.cwd")
    if command["observation_sha256"] != manifest["observation.json"]:
        fail("command.observation_sha256: cross-file mismatch")
    complete = exact(_load_json(root / "COMPLETE.json"), {"version", "status", "observation_sha256", "manifest_members"}, "COMPLETE")
    expected_complete = {
        "version": ARCHIVE_VERSION,
        "status": observation["status"],
        "observation_sha256": manifest["observation.json"],
        "manifest_members": sorted(expected),
    }
    if complete != expected_complete:
        fail("COMPLETE: semantic mismatch")
    return observation


def validate_external_bindings(
    *,
    repo: Path,
    observation: Mapping[str, Any],
    runtime_archive: Path,
    runtime_lock: Path,
    provenance_spec: Path,
) -> None:
    """Revalidate, rather than merely hash, every upstream sealed dependency."""
    runtime_archive = reject_linklike(runtime_archive, "runtime qualification archive")
    runtime_lock = reject_linklike(runtime_lock, "runtime lock")
    provenance_spec = reject_linklike(provenance_spec, "provenance spec")
    try:
        runtime_qualification = runtime_q.validate_archive(runtime_archive)
        spec_value = runtime_q.load_canonical_json(provenance_spec)
        spec, repo_commit = runtime_q.validate_provenance(
            repo, spec_value, runtime_lock, provenance_spec
        )
        live_runtime = runtime_q.validate_runtime_observation(runtime_q.capture_live_runtime())
        archived_runtime = runtime_q.load_canonical_json(runtime_archive / "runtime_observation.json")
        runtime_q.validate_runtime_observation(archived_runtime)
    except Exception as exc:
        fail(f"external runtime/provenance revalidation failed: {exc}")
    if live_runtime != archived_runtime:
        fail("live runtime differs from sealed runtime qualification")
    if (runtime_archive / "runtime_lock.json").read_bytes() != runtime_lock.read_bytes():
        fail("runtime archive lock differs from requested committed lock")
    if (runtime_archive / "provenance_spec.json").read_bytes() != provenance_spec.read_bytes():
        fail("runtime archive provenance spec differs from requested committed spec")

    declared = observation["provenance"]
    if declared["repo_commit"] != repo_commit:
        fail("model observation repo commit differs from revalidated provenance")
    archive_hashes = exact_tree(runtime_archive, "runtime qualification archive")
    if declared["runtime_archive_sha256"] != archive_hashes:
        fail("model observation runtime archive hash map differs from live sealed archive")
    if declared["runtime_identity_fingerprint"] != runtime_qualification["identity_fingerprint"]:
        fail("model observation runtime identity fingerprint differs")

    parent = spec["parent_model"]
    if (
        declared["parent_weight_sha256"] != parent["weights_sha256"]
        or declared["parent_support_sha256"] != parent["support_sha256"]
        or declared["parent_fingerprint"] != parent["fingerprint"]
    ):
        fail("model observation parent identity differs from revalidated parent")
    seed_record = spec["calibration"]["archives"][str(CALIBRATION_SEED)]
    if (
        declared["calibration_fingerprint"] != seed_record["metadata_fingerprint"]
        or declared["calibration_complete_sha256"] != seed_record["complete_sha256"]
    ):
        fail("model observation calibration seed-11 identity differs")
    ruler = spec["clean_ruler"]
    if (
        declared["clean_ruler_files_sha256"] != ruler["files_sha256"]
        or declared["clean_ruler_fingerprint"] != ruler["fingerprint"]
    ):
        fail("model observation clean-ruler identity differs")
    scalar_sources = observation["scalar"]["normalization_sources"]
    source_paths = [source["path"] for source in scalar_sources.values()]
    if len(set(source_paths)) != 3:
        fail("scalar normalization sources are not three distinct clean-ruler members")
    for role, source in scalar_sources.items():
        if ruler["files_sha256"].get(source["path"]) != source["sha256"]:
            fail(f"scalar normalization source {role} is not the declared clean-ruler member")
    try:
        normalization = _verified_project_modules(
            repo,
            observation["provenance"]["committed_sources"],
            {"decay_scalar_normalization"},
        )["decay_scalar_normalization"]
        ruler_root = runtime_q._resolve_declared(repo, ruler["root"], "clean ruler")
        role_paths = {
            role: reject_linklike(ruler_root / source["path"], f"{role} normalization source")
            for role, source in scalar_sources.items()
        }
        loaded = normalization.load_bidirectional_anchors(
            role_paths["baseline"], role_paths["terminal"], role_paths["ladder"]
        )
        policy_fingerprint = normalization.bidirectional_policy_fingerprint(*loaded)
    except Exception as exc:
        fail(f"scalar normalization anchors failed semantic replay: {exc}")
    if policy_fingerprint != observation["scalar"]["normalization_policy_fingerprint"]:
        fail("scalar normalization policy fingerprint differs on semantic replay")


def _write_new(path: Path, payload: bytes) -> None:
    with path.open("xb") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())


def _archive_observation(
    *,
    repo: Path,
    root: Path,
    observation: Mapping[str, Any],
    runtime_archive: Path,
    runtime_lock: Path,
    provenance_spec: Path,
    command: Mapping[str, Any],
    qualifier_source: Path | None = None,
) -> dict[str, Any]:
    repo = reject_linklike(repo, "repository")
    root = reject_linklike(root if root.is_absolute() else repo / root, "archive", include_leaf=False)
    qualifier_source = reject_linklike(qualifier_source or Path(__file__), "qualifier source")
    try:
        relative = root.relative_to(repo)
    except ValueError:
        fail("archive must be under repository derisk")
    folded = [part.casefold() for part in relative.parts]
    if len(folded) < 2 or folded[0] != "derisk" or ".git" in folded or "vendor" in folded:
        fail("archive must be a named derisk descendant, never .git/vendor")
    observation = validate_observation(dict(observation))
    head, sources = committed_sources(repo)
    _verify_bootstrapped_runtime(repo, sources)
    provenance = observation["provenance"]
    if provenance["repo_commit"] != head or provenance["committed_sources"] != sources:
        fail("candidate committed-source identity differs from live HEAD")
    if qualifier_source.read_bytes() != (repo / SOURCE_PATHS[0]).read_bytes():
        fail("executed qualifier source differs from committed source path")
    validate_external_bindings(
        repo=repo,
        observation=observation,
        runtime_archive=runtime_archive,
        runtime_lock=runtime_lock,
        provenance_spec=provenance_spec,
    )
    if root.exists():
        archived = validate_archive(root)
        if (root / "observation.json").read_bytes() != _canonical_json_bytes(observation):
            fail("existing archive differs from live observer result")
        if (root / "qualifier_source.py").read_bytes() != qualifier_source.read_bytes():
            fail("existing archive qualifier source differs from executed source")
        return archived
    try:
        root.mkdir(parents=False, exist_ok=False)
    except OSError as exc:
        fail(f"cannot create fresh archive: {exc}")
    try:
        observation_bytes = _canonical_json_bytes(observation)
        command_record = {
            "version": VERSION,
            "argv": list(command["argv"]),
            "cwd": str(command["cwd"]),
            "observation_sha256": sha256_bytes(observation_bytes),
        }
        members = {
            "observation.json": observation_bytes,
            "command.json": _canonical_json_bytes(command_record),
            "qualifier_source.py": qualifier_source.read_bytes(),
        }
        for name, payload in members.items():
            _write_new(root / name, payload)
        hashes = {name: sha256_bytes(payload) for name, payload in members.items()}
        complete = {
            "version": ARCHIVE_VERSION,
            "status": observation["status"],
            "observation_sha256": hashes["observation.json"],
            "manifest_members": sorted(ARCHIVE_MEMBERS - {"MANIFEST.sha256"}),
        }
        complete_bytes = _canonical_json_bytes(complete)
        _write_new(root / "COMPLETE.json", complete_bytes)
        hashes["COMPLETE.json"] = sha256_bytes(complete_bytes)
        _write_new(root / "MANIFEST.sha256", _manifest_bytes(hashes))
    except BaseException:
        # Preserve partial evidence exactly; never repair or silently redraw it.
        raise
    return validate_archive(root)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    observe = commands.add_parser("observe", help="run the expensive real-HF model observer")
    observe.add_argument("--repo", type=Path, default=Path.cwd())
    observe.add_argument("--model", type=Path, required=True)
    observe.add_argument("--runtime-archive", type=Path, required=True)
    observe.add_argument("--runtime-lock", type=Path, required=True)
    observe.add_argument("--provenance-spec", type=Path, required=True)
    observe.add_argument("--baseline", type=Path, required=True)
    observe.add_argument("--terminal", type=Path, required=True)
    observe.add_argument("--ladder", type=Path, required=True)
    observe.add_argument("--candidate", type=Path, required=True)
    observe.add_argument("--archive", type=Path, required=True)
    verify = commands.add_parser("verify", help="replay an existing immutable archive")
    verify.add_argument("--repo", type=Path, default=Path.cwd())
    verify.add_argument("--archive", type=Path, required=True)
    verify.add_argument("--runtime-archive", type=Path, required=True)
    verify.add_argument("--runtime-lock", type=Path, required=True)
    verify.add_argument("--provenance-spec", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command == "observe":
        result = observe_live(
            repo=args.repo, model_path=args.model, runtime_archive=args.runtime_archive,
            runtime_lock=args.runtime_lock, provenance_spec=args.provenance_spec,
            baseline=args.baseline, terminal=args.terminal, ladder=args.ladder,
            output=args.candidate,
        )
        sealed = _archive_observation(
            repo=args.repo, root=args.archive, observation=result,
            runtime_archive=args.runtime_archive, runtime_lock=args.runtime_lock,
            provenance_spec=args.provenance_spec,
            command={"argv": sys.argv if argv is None else [__file__, *argv], "cwd": str(Path.cwd())},
        )
        print(json.dumps({"status": sealed["status"], "candidate": str(args.candidate), "archive": str(args.archive)}, sort_keys=True))
        return 0
    head, sources = committed_sources(args.repo)
    _verify_bootstrapped_runtime(args.repo, sources)
    result = validate_archive(args.archive)
    if result["provenance"]["repo_commit"] != head or result["provenance"]["committed_sources"] != sources:
        fail("archived observation differs from live committed source identity")
    if (args.archive / "qualifier_source.py").read_bytes() != (args.repo / SOURCE_PATHS[0]).read_bytes():
        fail("archived qualifier source differs from current committed source")
    validate_external_bindings(
        repo=args.repo,
        observation=result,
        runtime_archive=args.runtime_archive,
        runtime_lock=args.runtime_lock,
        provenance_spec=args.provenance_spec,
    )
    print(json.dumps({"status": result["status"], "nonzero_slice_authorized": False}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
