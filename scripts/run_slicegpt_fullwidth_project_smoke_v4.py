#!/usr/bin/env python3
"""Seal the real full-width SliceGPT project-I/O and one-step PEFT gate.

This runner is intentionally incapable of authorizing a reduced width.  It
materializes the exact already-qualified full-width/nonidentity model, writes
and reloads the native project archive, performs one exact rank-2 LoRA step,
replays the adapter and merge, and evaluates the unchanged 196-prompt scalar.

The expensive path is deliberately phase-serial: at most one 4B model is live
on the L4.  Project, adapter, and evidence archives are immutable no-replace
outputs.  Validation never downloads a model or repairs a partial archive.
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
import re
import stat
import subprocess
import sys
import types
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence


VERSION = "slicegpt_gemma3_fullwidth_project_smoke_v4_v1"
ARCHIVE_VERSION = "slicegpt_gemma3_fullwidth_project_smoke_archive_v4_v1"
REPORT_VERSION = "slicegpt_gemma3_fullwidth_project_smoke_report_v4_v1"
EVIDENCE_VERSION = "slicegpt_gemma3_fullwidth_project_smoke_evidence_v4_v1"

PROJECT_IO_SHA256 = "dc5bffd5932320284263a725060bd18732c481b5958e04632fb770aec596ce65"
TEXT_MODEL_SHA256 = "eb027a1fc62a87aeb7f861aa8afe295ed2f62a776ecfcea35c9756a10bf9e8da"
ADAPTER_CORE_SHA256 = "c4df2be9111fd293454b19f98fba5d46805479d51db02d0611dcfab58f73cfdd"
MODEL_QUALIFIER_SHA256 = "bf30fe5275d3dec590dcdbd1425349c2b7d3aa92078716bcf6bb8cca6e667489"
RUNTIME_QUALIFIER_SHA256 = "aa83ea05978abe00d39bc2b8e69d9dd97a3354b51862398fd37c2b22725503b3"
MODEL_QUALIFIER_TEST_SHA256 = "83203d24d880067eb881211487720b337c5a653004208898bde614143a241629"
PROJECT_IO_TEST_SHA256 = "2af7d5a3b17778aee6809b7d81e4bd643f5c4033eec696e8e597d2eacb8f6209"
TEXT_MODEL_TEST_SHA256 = "f3571f9f49105c73fed6aaf6741e4709dd30f9aaefced91ce71df580fb455b62"

RUNNER_PATH = "scripts/run_slicegpt_fullwidth_project_smoke_v4.py"
TEST_PATH = "scripts/test_run_slicegpt_fullwidth_project_smoke_v4.py"
PROJECT_IO_PATH = "scripts/slicegpt_gemma3_project_io_v4.py"
MODEL_QUALIFIER_PATH = "scripts/qualify_slicegpt_model_adapter_v4.py"
RUNTIME_QUALIFIER_PATH = "scripts/qualify_slicegpt_runtime_v4.py"
TEXT_MODEL_PATH = "scripts/slicegpt_gemma3_text_model_v4.py"
ADAPTER_CORE_PATH = "scripts/slicegpt_gemma3_adapter_core_v4.py"

SOURCE_PATHS = (
    RUNNER_PATH,
    TEST_PATH,
    PROJECT_IO_PATH,
    "scripts/test_slicegpt_gemma3_project_io_v4.py",
    MODEL_QUALIFIER_PATH,
    "scripts/test_qualify_slicegpt_model_adapter_v4.py",
    RUNTIME_QUALIFIER_PATH,
    TEXT_MODEL_PATH,
    "scripts/test_slicegpt_gemma3_text_model_v4.py",
    ADAPTER_CORE_PATH,
    "scripts/test_slicegpt_gemma3_adapter_core_v4.py",
    "scripts/eval_decay_scalar.py",
    "scripts/decay_scalar_normalization.py",
    "docs/V4_SLICEGPT_PROTOCOL.md",
    "data/decay_scalar_prompts.json",
    "data/rehearsal_capability_prompts.json",
    "data/conversational_survival_generations.json",
)

ARCHIVE_MEMBERS = frozenset(
    {"report.json", "evidence.json", "command.json", "runner_source.py", "COMPLETE.json", "MANIFEST.sha256"}
)
CALIBRATION_SEED = 11
LORA_RANK = 2
LORA_ALPHA = 2
LEARNING_RATE_TEXT = "0.0001"
WEIGHT_DECAY_TEXT = "0.01"
TRAIN_PROMPT = (
    "SliceGPT v4 one-step PEFT qualification requires a finite gradient, finite optimizer state, "
    "bit-identical adapter reload, merge equivalence, and frozen scalar replay on the exact project loader."
)
TRAIN_SEQUENCE_LENGTH = 32
PROMPT_COUNT = 196
PROMPT_IDS_SHA256 = "150bc5ed2443b17086c4f7fc4dada71f1a960dbc22ef025044053cea4ec4be89"
GENERATION_MAX_NEW_TOKENS = 256
GENERATION_BATCH_SIZE = 8
CACHE_GENERATION_MAX_NEW_TOKENS = 32
SEED = 0
MAX_SCALAR_DELTA_TEXT = "1.0"
MAX_COMPONENT_DELTA_TEXT = "0.02"
MIN_CONTINUATION_MATCH = 194
MAX_MERGE_LOGIT_DELTA_TEXT = "0.02"
EXPECTED_TARGET_COUNT = 238
EXPECTED_TRAINABLE_COUNT = 476
EXPECTED_STATE_TENSOR_COUNT = 444
EXPECTED_TOTAL_STATE_BYTES = 10_884_909_056
EXPECTED_SHARD_COUNT = 11
OUTPUT_PARENT_NAME = "slicegpt_v4_fullwidth_gate"
PROJECT_ARCHIVE_NAME = "probe2_slicegpt_v4_fullwidth_project"
ADAPTER_ARCHIVE_NAME = "probe2_slicegpt_v4_fullwidth_adapter"
SMOKE_ARCHIVE_NAME = "probe2_slicegpt_v4_project_smoke"
RUNTIME_ARCHIVE_RELATIVE = "derisk/probe2_slicegpt_v4_runtime_qualification"
RUNTIME_LOCK_RELATIVE = "derisk/probe2_slicegpt_v4_runtime_lock/runtime_lock.json"
PROVENANCE_SPEC_RELATIVE = "derisk/probe2_slicegpt_v4_runtime_provenance_spec.json"
MODEL_ARCHIVE_RELATIVE = "derisk/probe2_slicegpt_v4_model_qualification"

HEX40 = re.compile(r"[0-9a-f]{40}\Z")
HEX64 = re.compile(r"[0-9a-f]{64}\Z")


class SmokeError(RuntimeError):
    pass


def fail(message: str) -> None:
    raise SmokeError(message)


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _json_value(value: Any, label: str = "JSON") -> None:
    if value is None or type(value) in {str, bool, int}:
        return
    if type(value) is float:
        if not math.isfinite(value):
            fail(f"{label}: non-finite float")
        return
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
    return (
        json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True, indent=2, separators=(",", ": "))
        + "\n"
    ).encode("utf-8")


def _load_json(path: Path, label: str) -> Any:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        fail(f"{label}: invalid JSON: {exc}")
    if path.read_bytes() != canonical_json_bytes(value):
        fail(f"{label}: noncanonical JSON")
    return value


def _exact(value: Any, keys: Iterable[str], label: str) -> dict[str, Any]:
    expected = set(keys)
    if type(value) is not dict or set(value) != expected:
        fail(f"{label}: exact schema changed")
    return value


def _digest(value: Any, label: str) -> str:
    if type(value) is not str or HEX64.fullmatch(value) is None:
        fail(f"{label}: exact lowercase SHA-256 required")
    return value


def _commit(value: Any, label: str) -> str:
    if type(value) is not str or HEX40.fullmatch(value) is None:
        fail(f"{label}: exact lowercase commit required")
    return value


def _integer(value: Any, label: str, *, expected: int | None = None, minimum: int | None = None) -> int:
    if type(value) is not int:
        fail(f"{label}: exact integer required")
    if expected is not None and value != expected:
        fail(f"{label}: expected {expected}")
    if minimum is not None and value < minimum:
        fail(f"{label}: expected at least {minimum}")
    return value


def _decimal(value: Any, label: str) -> Decimal:
    if type(value) is not str or re.fullmatch(r"-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?", value) is None or value == "-0":
        fail(f"{label}: canonical decimal string required")
    try:
        result = Decimal(value)
    except InvalidOperation:
        fail(f"{label}: invalid decimal")
    if not result.is_finite():
        fail(f"{label}: finite decimal required")
    return result


def decimal_text(value: Any) -> str:
    number = Decimal(str(float(value)))
    if not number.is_finite():
        fail("cannot serialize non-finite value")
    rendered = format(number, "f").rstrip("0").rstrip(".") if "." in format(number, "f") else format(number, "f")
    return "0" if rendered in {"", "-0"} else rendered


def _is_linklike(path: Path) -> bool:
    try:
        info = path.lstat()
    except OSError:
        return False
    attrs = int(getattr(info, "st_file_attributes", 0))
    return stat.S_ISLNK(info.st_mode) or bool(attrs & int(getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)))


def strict_path(path: Path, label: str, *, include_leaf: bool = True) -> Path:
    result = Path(os.path.abspath(path))
    candidates = (result, *result.parents) if include_leaf else tuple(result.parents)
    for candidate in candidates:
        if candidate.exists() and _is_linklike(candidate):
            fail(f"{label}: symlink/junction/reparse component forbidden")
    return result


def _direct_module(name: str, path: Path, expected_sha256: str) -> Any:
    if name in sys.modules:
        fail(f"preloaded smoke dependency forbidden: {name}")
    path = strict_path(path, f"dependency {name}")
    if not path.is_file() or sha256_file(path) != expected_sha256:
        fail(f"dependency source identity changed: {name}")
    spec = importlib.util.spec_from_file_location(name, path)
    if (
        spec is None
        or type(spec.loader) is not importlib.machinery.SourceFileLoader
        or spec.loader.name != name
        or Path(str(spec.origin)).resolve() != path
    ):
        fail(f"dependency source loader substituted: {name}")
    module = types.ModuleType(name)
    module.__file__ = str(path)
    module.__loader__ = spec.loader
    module.__package__ = ""
    module.__spec__ = spec
    sys.modules[name] = module
    try:
        source = path.read_bytes()
        if sha256_bytes(source) != expected_sha256:
            fail(f"buffered dependency bytes changed: {name}")
        exec(compile(source, str(path), "exec"), module.__dict__)
    except BaseException:
        sys.modules.pop(name, None)
        raise
    finally:
        sys.modules.pop(name, None)
    if path.read_bytes() != source or Path(str(module.__file__)).resolve() != path:
        fail(f"dependency changed during direct execution: {name}")
    return module


def _git(repo: Path, *arguments: str, binary: bool = False) -> str | bytes:
    try:
        result = subprocess.run(
            ["git", *arguments], cwd=repo, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=not binary,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        fail(f"git {' '.join(arguments)} failed: {exc}")
    return result.stdout


def committed_sources(repo: Path) -> tuple[str, dict[str, str]]:
    repo = strict_path(repo, "repository")
    head = str(_git(repo, "rev-parse", "HEAD")).strip()
    _commit(head, "repository HEAD")
    result: dict[str, str] = {}
    for relative in SOURCE_PATHS:
        path = strict_path(repo / relative, f"source {relative}")
        if not path.is_file():
            fail(f"source missing: {relative}")
        blob = _git(repo, "show", f"HEAD:{relative}", binary=True)
        assert isinstance(blob, bytes)
        live = path.read_bytes()
        if blob != live:
            fail(f"source differs from committed HEAD: {relative}")
        result[relative] = sha256_bytes(live)
    fixed = {
        PROJECT_IO_PATH: PROJECT_IO_SHA256,
        MODEL_QUALIFIER_PATH: MODEL_QUALIFIER_SHA256,
        RUNTIME_QUALIFIER_PATH: RUNTIME_QUALIFIER_SHA256,
        TEXT_MODEL_PATH: TEXT_MODEL_SHA256,
        ADAPTER_CORE_PATH: ADAPTER_CORE_SHA256,
        "scripts/test_slicegpt_gemma3_project_io_v4.py": PROJECT_IO_TEST_SHA256,
        "scripts/test_qualify_slicegpt_model_adapter_v4.py": MODEL_QUALIFIER_TEST_SHA256,
        "scripts/test_slicegpt_gemma3_text_model_v4.py": TEXT_MODEL_TEST_SHA256,
    }
    for path, expected in fixed.items():
        if result.get(path) != expected:
            fail(f"frozen source hash changed: {path}")
    return head, result


def _load_modules(repo: Path) -> tuple[Any, Any]:
    model_q = _direct_module(
        "_slicegpt_smoke_model_qualifier_v4", repo / MODEL_QUALIFIER_PATH, MODEL_QUALIFIER_SHA256
    )
    project_io = _direct_module(
        "_slicegpt_smoke_project_io_v4", repo / PROJECT_IO_PATH, PROJECT_IO_SHA256
    )
    return model_q, project_io


def _exact_tree(root: Path, label: str) -> dict[str, str]:
    root = strict_path(root, label)
    if not root.is_dir():
        fail(f"{label}: directory missing")
    result: dict[str, str] = {}
    for path in sorted(root.rglob("*"), key=lambda item: item.as_posix()):
        strict_path(path, label)
        if path.is_dir():
            continue
        if not path.is_file():
            fail(f"{label}: non-regular member")
        result[path.relative_to(root).as_posix()] = sha256_file(path)
    if not result:
        fail(f"{label}: empty tree")
    return result


def canonical_paths(repo: Path) -> dict[str, Path]:
    """Return the only accepted upstream and output locations."""
    repo = strict_path(repo, "repository")
    output_parent = strict_path(repo.parent / OUTPUT_PARENT_NAME, "fixed output parent", include_leaf=False)
    return {
        "runtime_archive": repo / RUNTIME_ARCHIVE_RELATIVE,
        "runtime_lock": repo / RUNTIME_LOCK_RELATIVE,
        "provenance_spec": repo / PROVENANCE_SPEC_RELATIVE,
        "model_archive": repo / MODEL_ARCHIVE_RELATIVE,
        "project": output_parent / PROJECT_ARCHIVE_NAME,
        "adapter": output_parent / ADAPTER_ARCHIVE_NAME,
        "smoke": output_parent / SMOKE_ARCHIVE_NAME,
    }


def _validate_upstreams(
    *, repo: Path, model_q: Any, model_archive: Path, runtime_archive: Path,
    runtime_lock: Path, provenance_spec: Path,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], str]:
    """Validate immutable ancestors while allowing a later runner commit.

    The model archive necessarily predates this runner.  We therefore require
    its recorded commit to be an ancestor and every recorded source blob to be
    unchanged, instead of incorrectly requiring the archive's historical HEAD
    to equal the runner commit.
    """
    observation = model_q.validate_archive(model_archive)
    if observation["status"] != "INCOMPLETE_SERIALIZATION_AND_PEFT" or observation["model_level_gates_passed"] is not True:
        fail("model qualification archive did not pass every model-level gate")
    runtime_q = model_q.runtime_q
    runtime_qualification = runtime_q.validate_archive(runtime_archive)
    spec = runtime_q.load_canonical_json(provenance_spec)
    spec, current_head = runtime_q.validate_provenance(repo, spec, runtime_lock, provenance_spec)
    if runtime_q.load_canonical_json(runtime_archive / "runtime_observation.json") != runtime_q.validate_runtime_observation(runtime_q.capture_live_runtime()):
        fail("live runtime differs from the immutable runtime archive")
    if (runtime_archive / "runtime_lock.json").read_bytes() != runtime_lock.read_bytes():
        fail("runtime archive lock differs from the requested lock")
    if (runtime_archive / "provenance_spec.json").read_bytes() != provenance_spec.read_bytes():
        fail("runtime archive provenance differs from the requested spec")
    provenance = observation["provenance"]
    historical = _commit(provenance["repo_commit"], "model observation commit")
    try:
        _git(repo, "merge-base", "--is-ancestor", historical, current_head)
    except SmokeError:
        fail("model qualification commit is not an ancestor of the runner commit")
    for relative, expected in provenance["committed_sources"].items():
        _digest(expected, f"model source {relative}")
        historical_blob = _git(repo, "show", f"{historical}:{relative}", binary=True)
        current_blob = _git(repo, "show", f"{current_head}:{relative}", binary=True)
        assert isinstance(historical_blob, bytes) and isinstance(current_blob, bytes)
        if sha256_bytes(historical_blob) != expected or historical_blob != current_blob:
            fail(f"model qualification source changed after sealing: {relative}")
    if sha256_file(model_archive / "qualifier_source.py") != MODEL_QUALIFIER_SHA256:
        fail("model archive does not contain the exact frozen qualifier source")
    if provenance["runtime_archive_sha256"] != _exact_tree(runtime_archive, "runtime archive"):
        fail("model observation runtime archive binding changed")
    if provenance["runtime_identity_fingerprint"] != runtime_qualification["identity_fingerprint"]:
        fail("model observation runtime identity changed")
    if (
        provenance["parent_weight_sha256"] != spec["parent_model"]["weights_sha256"]
        or provenance["parent_support_sha256"] != spec["parent_model"]["support_sha256"]
        or provenance["parent_fingerprint"] != spec["parent_model"]["fingerprint"]
    ):
        fail("model observation parent identity changed")
    seed = spec["calibration"]["archives"][str(CALIBRATION_SEED)]
    if (
        provenance["calibration_fingerprint"] != seed["metadata_fingerprint"]
        or provenance["calibration_complete_sha256"] != seed["complete_sha256"]
    ):
        fail("model observation calibration identity changed")
    if (
        provenance["clean_ruler_fingerprint"] != spec["clean_ruler"]["fingerprint"]
        or provenance["clean_ruler_files_sha256"] != spec["clean_ruler"]["files_sha256"]
    ):
        fail("model observation ruler identity changed")
    scalar_sources = observation["scalar"]["normalization_sources"]
    if set(scalar_sources) != {"baseline", "terminal", "ladder"} or len({row["path"] for row in scalar_sources.values()}) != 3:
        fail("model observation normalization source surface changed")
    for role, record in scalar_sources.items():
        if spec["clean_ruler"]["files_sha256"].get(record["path"]) != record["sha256"]:
            fail(f"model observation {role} normalization binding changed")
    return observation, runtime_qualification, spec, current_head


def _hash_rows(rows: Any) -> str:
    return sha256_bytes(canonical_json_bytes(rows))


def _tensor_hash(project_io: Any, tensor: Any) -> str:
    return project_io.tensor_sha256(tensor)


def _collect(torch: Any) -> None:
    """Collect only after the caller has deleted every model-owning reference."""
    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()


def _gpu_record(torch: Any, phase: str) -> dict[str, Any]:
    device = torch.cuda.current_device()
    return {
        "phase": phase,
        "allocated_bytes": int(torch.cuda.memory_allocated(device)),
        "reserved_bytes": int(torch.cuda.memory_reserved(device)),
        "max_allocated_bytes": int(torch.cuda.max_memory_allocated(device)),
        "max_reserved_bytes": int(torch.cuda.max_memory_reserved(device)),
        "device_total_bytes": int(torch.cuda.get_device_properties(device).total_memory),
        "post_release_allocated_bytes": -1,
    }


def _reset_peak(torch: Any) -> None:
    torch.cuda.reset_peak_memory_stats(torch.cuda.current_device())


def _render_training_surface(torch: Any, tokenizer: Any, device: Any) -> tuple[Any, Any, dict[str, Any]]:
    rendered = tokenizer.apply_chat_template(
        [{"role": "user", "content": TRAIN_PROMPT}], tokenize=False, add_generation_prompt=True
    )
    encoded = tokenizer(rendered, add_special_tokens=False, return_tensors="pt")
    if set(encoded) != {"input_ids", "attention_mask"}:
        fail("training tokenizer surface changed")
    ids = encoded["input_ids"][:, -TRAIN_SEQUENCE_LENGTH:].to(device)
    mask = encoded["attention_mask"][:, -TRAIN_SEQUENCE_LENGTH:].to(device)
    if ids.dtype is not torch.int64 or mask.dtype is not torch.int64 or ids.shape != (1, TRAIN_SEQUENCE_LENGTH) or not bool((mask == 1).all().item()):
        fail("training input surface changed")
    record = {
        "prompt_sha256": sha256_bytes(TRAIN_PROMPT.encode("utf-8")),
        "rendered_sha256": sha256_bytes(rendered.encode("utf-8")),
        "input_ids": [int(value) for value in ids[0].detach().cpu().tolist()],
        "attention_mask": [int(value) for value in mask[0].detach().cpu().tolist()],
    }
    return ids, mask, record


def _prepare_project_tokenizer(tokenizer: Any) -> None:
    if (
        type(tokenizer).__name__ != "GemmaTokenizer"
        or tokenizer.bos_token_id != 2
        or tokenizer.eos_token_id != 1
        or tokenizer.pad_token_id != 0
        or tokenizer.unk_token_id != 3
    ):
        fail("project tokenizer identity changed")
    tokenizer.padding_side = "left"
    if tokenizer.padding_side != "left":
        fail("project tokenizer refused frozen left padding")


def _generate_with_cache_setting(torch: Any, model: Any, tokenizer: Any, prompt: str, device: Any, use_cache: bool) -> list[int]:
    inputs, _ = _render_inputs(torch, tokenizer, [prompt], device)
    with torch.inference_mode():
        generated = model.generate(
            **inputs, do_sample=False, use_cache=use_cache,
            max_new_tokens=CACHE_GENERATION_MAX_NEW_TOKENS,
        )
    return [int(value) for value in generated[0, inputs["input_ids"].shape[1] :].detach().cpu().tolist()]


def _render_inputs(torch: Any, tokenizer: Any, prompts: list[str], device: Any) -> tuple[dict[str, Any], list[str]]:
    rendered = [
        tokenizer.apply_chat_template([{"role": "user", "content": prompt}], tokenize=False, add_generation_prompt=True)
        for prompt in prompts
    ]
    encoded = tokenizer(rendered, padding=True, add_special_tokens=False, return_tensors="pt")
    if set(encoded) != {"input_ids", "attention_mask"}:
        fail("tokenizer emitted an unexpected input surface")
    return {name: value.to(device) for name, value in encoded.items()}, rendered


def _cache_forward_record(torch: Any, model: Any, tokenizer: Any, prompt: str, device: Any) -> dict[str, Any]:
    inputs, _ = _render_inputs(torch, tokenizer, [prompt], device)
    with torch.inference_mode():
        no_cache = model(**inputs, use_cache=False, return_dict=True)
        prefill = model(**inputs, use_cache=True, return_dict=True)
        next_ids = no_cache.logits[:, -1:].argmax(-1)
        next_mask = torch.ones((1, 1), dtype=inputs["attention_mask"].dtype, device=device)
        decode = model(
            input_ids=next_ids,
            attention_mask=torch.cat([inputs["attention_mask"], next_mask], dim=1),
            past_key_values=prefill.past_key_values,
            use_cache=True,
            return_dict=True,
        )
        full = model(
            input_ids=torch.cat([inputs["input_ids"], next_ids], dim=1),
            attention_mask=torch.cat([inputs["attention_mask"], next_mask], dim=1),
            use_cache=False,
            return_dict=True,
        )
    prefill_delta = float((no_cache.logits.float() - prefill.logits.float()).abs().max().item())
    decode_delta = float((decode.logits[:, -1].float() - full.logits[:, -1].float()).abs().max().item())
    record = {
        "finite": all(bool(torch.isfinite(item).all().item()) for item in (no_cache.logits, prefill.logits, decode.logits, full.logits)),
        "prefill_cache_present": prefill.past_key_values is not None,
        "decode_cache_present": decode.past_key_values is not None,
        "prefill_top1_equal": bool(torch.equal(no_cache.logits.argmax(-1), prefill.logits.argmax(-1))),
        "decode_top1_equal": bool(torch.equal(decode.logits[:, -1].argmax(-1), full.logits[:, -1].argmax(-1))),
        "prefill_max_abs_delta": decimal_text(prefill_delta),
        "decode_max_abs_delta": decimal_text(decode_delta),
    }
    if not all(record[key] is True for key in ("finite", "prefill_cache_present", "decode_cache_present", "prefill_top1_equal", "decode_top1_equal")):
        fail("cache/no-cache forward smoke failed")
    if prefill_delta > 0.02 or decode_delta > 0.02:
        fail("cache/no-cache forward delta exceeded 0.02")
    return record


def _generate(model_q: Any, torch: Any, model: Any, tokenizer: Any, prompts: list[str], device: Any) -> tuple[list[str], list[list[int]], int, int]:
    return model_q._generate(
        torch, model, tokenizer, prompts, device, max_new_tokens=GENERATION_MAX_NEW_TOKENS
    )


def _scalar_record(
    *, model_q: Any, eval_module: Any, normalization: Any, tokenizer: Any,
    records: list[dict[str, Any]], generations: list[str], judge_scores: list[int | None],
    baseline: Path, terminal: Path, ladder: Path, base_scalar: Mapping[str, Any],
) -> dict[str, Any]:
    anchors_all = normalization.load_bidirectional_anchors(baseline, terminal, ladder)
    components, scalar = model_q._component_record(
        eval_module, normalization, tokenizer, records, generations, judge_scores, anchors_all[:3]
    )
    base_components = base_scalar["transformed_components"]
    component_deltas = {
        name: abs(float(components[name]) - float(base_components[name])) for name in ("R", "D", "J", "F")
    }
    scalar_delta = abs(float(scalar) - float(base_scalar["transformed_scalar"]))
    result = {
        "prompt_count": PROMPT_COUNT,
        "prompt_ids_sha256": PROMPT_IDS_SHA256,
        "decoding": "greedy",
        "seed": SEED,
        "max_new_tokens": GENERATION_MAX_NEW_TOKENS,
        "batch_size": GENERATION_BATCH_SIZE,
        "unparsed_count": sum(value is None for value in judge_scores),
        "base_scalar": base_scalar["transformed_scalar"],
        "merged_scalar": decimal_text(scalar),
        "scalar_delta": decimal_text(scalar_delta),
        "base_components": dict(base_components),
        "merged_components": {name: decimal_text(components[name]) for name in components},
        "component_deltas": {name: decimal_text(component_deltas[name]) for name in component_deltas},
        "normalization_policy_fingerprint": normalization.bidirectional_policy_fingerprint(*anchors_all),
        "passed": False,
    }
    result["passed"] = (
        result["unparsed_count"] == 0
        and Decimal(result["scalar_delta"]) <= Decimal(MAX_SCALAR_DELTA_TEXT)
        and all(Decimal(value) <= Decimal(MAX_COMPONENT_DELTA_TEXT) for value in result["component_deltas"].values())
    )
    if result["normalization_policy_fingerprint"] != base_scalar["normalization_policy_fingerprint"]:
        fail("frozen scalar normalization policy changed")
    if result["passed"] is not True:
        fail("one-step reloaded/merged model failed the frozen scalar gate")
    return result


def _full_width_dimensions(project_io: Any) -> list[dict[str, int]]:
    try:
        dimensions = [dict(row) for row in project_io.TEXT.full_width_dimensions()]
    except (TypeError, ValueError) as exc:
        raise SmokeError("project loader full-width dimension surface changed") from exc
    if (
        len(dimensions) != 34
        or any(set(row) != {"input", "attention", "output"} for row in dimensions)
        or any(type(value) is not int or value != 2560 for row in dimensions for value in row.values())
    ):
        fail("project loader full-width dimension surface changed")
    return dimensions


def _project_state_summary(project_io: Any, project_archive: Mapping[str, Any]) -> dict[str, Any]:
    """Derive the state summary from project-I/O's validated return contract."""
    tensors = project_archive.get("tensors")
    if type(tensors) is not dict or len(tensors) != EXPECTED_STATE_TENSOR_COUNT:
        fail("validated project tensor surface changed")
    total_size = 0
    for name, record in tensors.items():
        if (
            type(name) is not str
            or type(record) is not dict
            or set(record) != {"shape", "dtype", "sha256", "shard"}
            or type(record["shape"]) is not list
            or not record["shape"]
            or any(type(value) is not int or value <= 0 for value in record["shape"])
            or record["dtype"] != "BF16"
        ):
            fail("validated project tensor record changed")
        _digest(record["sha256"], f"project tensor {name}")
        if type(record["shard"]) is not str or not record["shard"]:
            fail("validated project tensor shard changed")
        total_size += math.prod(record["shape"]) * 2
    if total_size != EXPECTED_TOTAL_STATE_BYTES:
        fail("validated project total state size changed")
    fingerprint = _digest(project_io._fingerprint(tensors), "project state fingerprint")
    return {
        "state_fingerprint": fingerprint,
        "tensor_count": len(tensors),
        "total_size": total_size,
    }


def _project_records(repo: Path, project_io: Any, spec: Mapping[str, Any], sources: Mapping[str, str], head: str, model_archive: Path, provenance_spec: Path) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    calibration_ref = spec["calibration"]["archives"][str(CALIBRATION_SEED)]
    calibration_root = Path(spec["calibration"]["archives"][str(CALIBRATION_SEED)]["root"])
    # The source-identity fingerprint is the canonical hash of the exact
    # source_identity object inside the already validated calibration metadata.
    calibration_metadata_path = calibration_root / "calibration_metadata.json"
    if not calibration_metadata_path.is_absolute():
        calibration_metadata_path = repo / calibration_metadata_path
    metadata = _load_json(calibration_metadata_path, "seed-11 calibration metadata")
    calibration = {
        "version": "slicegpt_gemma3_calibration_metadata_v4_v1",
        "seed": CALIBRATION_SEED,
        "metadata_fingerprint": calibration_ref["metadata_fingerprint"],
        "tensors_sha256": calibration_ref["tensors_sha256"],
        "complete_sha256": calibration_ref["complete_sha256"],
        "source_identity_fingerprint": sha256_bytes(canonical_json_bytes(metadata["source_identity"])),
    }
    slicing = {
        "version": "slicegpt_gemma3_slicing_metadata_v4_v1",
        "mechanism": "slicegpt",
        "fraction": "0",
        "residual_dimensions": _full_width_dimensions(project_io),
        "calibration_seed": CALIBRATION_SEED,
        "calibration_tensors_sha256": calibration_ref["tensors_sha256"],
        "nonzero_slice_authorized": False,
    }
    source = {
        "version": "slicegpt_gemma3_source_metadata_v4_v1",
        "repo_commit": head,
        "committed_sources": dict(sources),
        "provenance_spec_sha256": sha256_file(provenance_spec),
        "model_qualification_sha256": sha256_file(model_archive / "MANIFEST.sha256"),
    }
    return slicing, source, calibration


def _archive_manifest_bytes(mapping: Mapping[str, str]) -> bytes:
    return "".join(f"{mapping[name]}  {name}\n" for name in sorted(mapping)).encode("utf-8")


def _write_new(path: Path, payload: bytes) -> None:
    with path.open("xb") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())


def _parse_manifest(path: Path) -> dict[str, str]:
    raw = path.read_bytes()
    if raw.replace(b"\r\n", b"\n") != raw:
        fail("manifest CRLF is forbidden")
    rows = raw.decode("utf-8").splitlines()
    result: dict[str, str] = {}
    for row in rows:
        if len(row) < 67 or row[64:66] != "  ":
            fail("manifest row malformed")
        name = row[66:]
        if Path(name).name != name or name in result:
            fail("manifest member is noncanonical or duplicated")
        result[name] = _digest(row[:64], f"manifest {name}")
    if rows != [f"{result[name]}  {name}" for name in sorted(result)]:
        fail("manifest rows are not canonically sorted")
    return result


def validate_evidence(value: Any) -> dict[str, Any]:
    value = _exact(
        value,
        [
            "version", "prompt_ids", "base_token_rows", "adapted_token_rows", "reloaded_token_rows",
            "merged_token_rows", "merged_generations", "judge_texts", "judge_scores", "training_surface",
            "cache_generate_no_cache", "cache_generate_cache",
        ],
        "evidence",
    )
    if value["version"] != EVIDENCE_VERSION:
        fail("evidence version changed")
    prompt_ids = value["prompt_ids"]
    if type(prompt_ids) is not list or len(prompt_ids) != PROMPT_COUNT or any(type(item) is not str or not item for item in prompt_ids):
        fail("evidence prompt ID surface changed")
    if _hash_rows(prompt_ids) != PROMPT_IDS_SHA256:
        fail("evidence prompt ID/order hash changed")
    for key in ("base_token_rows", "adapted_token_rows", "reloaded_token_rows", "merged_token_rows"):
        rows = value[key]
        if type(rows) is not list or len(rows) != PROMPT_COUNT:
            fail(f"evidence {key} count changed")
        for row in rows:
            if type(row) is not list or len(row) > GENERATION_MAX_NEW_TOKENS or any(type(token) is not int or token < 0 or token >= 262208 for token in row):
                fail(f"evidence {key} token row changed")
    if value["adapted_token_rows"] != value["reloaded_token_rows"] or value["reloaded_token_rows"] != value["merged_token_rows"]:
        fail("adapter save/reload/merge continuations are not byte-identical")
    if type(value["merged_generations"]) is not list or len(value["merged_generations"]) != PROMPT_COUNT or any(type(item) is not str for item in value["merged_generations"]):
        fail("merged generation text surface changed")
    if type(value["judge_texts"]) is not list or len(value["judge_texts"]) != PROMPT_COUNT or any(type(item) is not str for item in value["judge_texts"]):
        fail("judge text surface changed")
    if type(value["judge_scores"]) is not list or len(value["judge_scores"]) != PROMPT_COUNT or any(type(item) is not int or item < 0 or item > 5 for item in value["judge_scores"]):
        fail("judge score surface changed")
    training = _exact(value["training_surface"], ["prompt_sha256", "rendered_sha256", "input_ids", "attention_mask"], "training surface")
    if _digest(training["prompt_sha256"], "training prompt") != sha256_bytes(TRAIN_PROMPT.encode("utf-8")):
        fail("training prompt identity changed")
    _digest(training["rendered_sha256"], "training rendered prompt")
    for key in ("input_ids", "attention_mask"):
        if type(training[key]) is not list or len(training[key]) != TRAIN_SEQUENCE_LENGTH or any(type(item) is not int for item in training[key]):
            fail(f"training {key} changed")
    if training["attention_mask"] != [1] * TRAIN_SEQUENCE_LENGTH:
        fail("training attention mask changed")
    for key in ("cache_generate_no_cache", "cache_generate_cache"):
        if type(value[key]) is not list or len(value[key]) > CACHE_GENERATION_MAX_NEW_TOKENS or any(type(item) is not int for item in value[key]):
            fail(f"{key} changed")
    if value["cache_generate_no_cache"] != value["cache_generate_cache"]:
        fail("cache/no-cache greedy generation differs")
    return value


def validate_report(value: Any, *, evidence_sha256: str | None = None) -> dict[str, Any]:
    value = _exact(
        value,
        [
            "version", "status", "scope", "probe2_verdict", "nonzero_slice_authorized", "capability_issued",
            "source", "upstream", "project", "roundtrip", "peft", "scalar", "cache", "memory",
            "evidence_sha256", "remaining_gate",
        ],
        "report",
    )
    if (
        value["version"] != REPORT_VERSION
        or value["status"] != "PASS_FULL_WIDTH_PROJECT_IO_AND_PEFT_SMOKE"
        or value["scope"] != "FULL_WIDTH_PROJECT_IO_AND_ONE_STEP_PEFT_ONLY"
        or value["probe2_verdict"] is not None
        or value["nonzero_slice_authorized"] is not False
        or value["capability_issued"] is not False
        or value["remaining_gate"] != "sealed reduced-width capability issuer"
    ):
        fail("report overclaims or changes its bounded status")
    source = _exact(value["source"], ["repo_commit", "committed_sources", "runner_sha256", "project_io_sha256", "model_qualifier_sha256"], "report source")
    _commit(source["repo_commit"], "source repo commit")
    if type(source["committed_sources"]) is not dict or set(source["committed_sources"]) != set(SOURCE_PATHS):
        fail("report committed source set changed")
    for path, digest_value in source["committed_sources"].items():
        _digest(digest_value, f"source {path}")
    if source["runner_sha256"] != source["committed_sources"][RUNNER_PATH] or source["project_io_sha256"] != PROJECT_IO_SHA256 or source["model_qualifier_sha256"] != MODEL_QUALIFIER_SHA256:
        fail("report frozen source bindings changed")
    upstream = _exact(value["upstream"], ["runtime_archive_manifest_sha256", "runtime_identity_fingerprint", "provenance_spec_sha256", "model_archive_manifest_sha256", "model_observation_sha256", "parent_fingerprint", "calibration_fingerprint", "calibration_tensors_sha256"], "upstream")
    for key, item in upstream.items():
        _digest(item, f"upstream {key}")
    project = _exact(value["project"], ["manifest_sha256", "state_fingerprint", "tensor_count", "total_size", "shard_count", "full_width", "fraction", "calibration_seed", "tokenizer_padding_side"], "project")
    for key in ("manifest_sha256", "state_fingerprint"):
        _digest(project[key], f"project {key}")
    _integer(project["tensor_count"], "project tensor count", expected=EXPECTED_STATE_TENSOR_COUNT)
    _integer(project["total_size"], "project total size", expected=EXPECTED_TOTAL_STATE_BYTES)
    _integer(project["shard_count"], "project shard count", expected=EXPECTED_SHARD_COUNT)
    if project["full_width"] is not True or project["fraction"] != "0" or project["calibration_seed"] != CALIBRATION_SEED or project["tokenizer_padding_side"] != "left":
        fail("project is not the exact locked full-width seed-11 surface")
    roundtrip = _exact(value["roundtrip"], ["bit_identical_state", "base_continuations_sha256", "qualified_continuations_sha256", "byte_identical_generation", "wrong_count", "limited_count"], "roundtrip")
    if roundtrip["bit_identical_state"] is not True or roundtrip["byte_identical_generation"] is not True:
        fail("project roundtrip gate did not pass")
    for key in ("base_continuations_sha256", "qualified_continuations_sha256"):
        _digest(roundtrip[key], f"roundtrip {key}")
    if roundtrip["base_continuations_sha256"] != roundtrip["qualified_continuations_sha256"]:
        fail("project generation differs from qualified full-width model")
    _integer(roundtrip["wrong_count"], "roundtrip wrong", expected=0)
    _integer(roundtrip["limited_count"], "roundtrip limited", expected=0)
    peft_record = _exact(value["peft"], ["rank", "alpha", "seed", "learning_rate", "weight_decay", "target_module_count", "trainable_tensor_count", "loss", "finite_fp32_gradients", "finite_fp32_optimizer_state", "changed_trainable_count", "adapter_manifest_sha256", "adapter_state_fingerprint", "save_reload_logits_bit_identical", "save_reload_generation_bit_identical", "merged_top1_identical", "merged_max_abs_logit_delta", "merged_generation_bit_identical"], "peft")
    _integer(peft_record["rank"], "peft rank", expected=LORA_RANK)
    _integer(peft_record["alpha"], "peft alpha", expected=LORA_ALPHA)
    _integer(peft_record["seed"], "peft seed", expected=SEED)
    _integer(peft_record["target_module_count"], "peft target count", expected=EXPECTED_TARGET_COUNT)
    _integer(peft_record["trainable_tensor_count"], "peft trainable count", expected=EXPECTED_TRAINABLE_COUNT)
    _integer(peft_record["changed_trainable_count"], "peft changed count", minimum=1)
    if peft_record["learning_rate"] != LEARNING_RATE_TEXT or peft_record["weight_decay"] != WEIGHT_DECAY_TEXT:
        fail("PEFT optimizer configuration changed")
    if _decimal(peft_record["loss"], "peft loss") <= 0:
        fail("PEFT loss is nonpositive")
    if any(peft_record[key] is not True for key in ("finite_fp32_gradients", "finite_fp32_optimizer_state", "save_reload_logits_bit_identical", "save_reload_generation_bit_identical", "merged_top1_identical", "merged_generation_bit_identical")):
        fail("PEFT materialized roundtrip gate did not pass")
    _digest(peft_record["adapter_manifest_sha256"], "adapter manifest")
    _digest(peft_record["adapter_state_fingerprint"], "adapter state")
    if _decimal(peft_record["merged_max_abs_logit_delta"], "merge delta") > Decimal(MAX_MERGE_LOGIT_DELTA_TEXT):
        fail("merged logit delta exceeded 0.02")
    scalar = _exact(value["scalar"], ["prompt_count", "prompt_ids_sha256", "decoding", "seed", "max_new_tokens", "batch_size", "unparsed_count", "base_scalar", "merged_scalar", "scalar_delta", "base_components", "merged_components", "component_deltas", "normalization_policy_fingerprint", "passed"], "scalar")
    _integer(scalar["prompt_count"], "scalar prompt count", expected=PROMPT_COUNT)
    _integer(scalar["seed"], "scalar seed", expected=SEED)
    _integer(scalar["max_new_tokens"], "scalar max tokens", expected=GENERATION_MAX_NEW_TOKENS)
    _integer(scalar["batch_size"], "scalar batch", expected=GENERATION_BATCH_SIZE)
    _integer(scalar["unparsed_count"], "scalar unparsed", expected=0)
    if scalar["prompt_ids_sha256"] != PROMPT_IDS_SHA256 or scalar["decoding"] != "greedy" or scalar["passed"] is not True:
        fail("scalar frozen surface or verdict changed")
    if _decimal(scalar["scalar_delta"], "scalar delta") > Decimal(MAX_SCALAR_DELTA_TEXT):
        fail("scalar delta exceeded one point")
    for field in ("base_components", "merged_components", "component_deltas"):
        if type(scalar[field]) is not dict or set(scalar[field]) != {"R", "D", "J", "F"}:
            fail(f"scalar {field} schema changed")
        for name, item in scalar[field].items():
            number = _decimal(item, f"scalar {field}.{name}")
            if field == "component_deltas" and number > Decimal(MAX_COMPONENT_DELTA_TEXT):
                fail("scalar component delta exceeded 0.02")
    _digest(scalar["normalization_policy_fingerprint"], "normalization fingerprint")
    cache = _exact(value["cache"], ["generation_equal", "forward"], "cache")
    if cache["generation_equal"] is not True:
        fail("cache/no-cache generation differs")
    forward = _exact(cache["forward"], ["finite", "prefill_cache_present", "decode_cache_present", "prefill_top1_equal", "decode_top1_equal", "prefill_max_abs_delta", "decode_max_abs_delta"], "cache forward")
    if any(forward[key] is not True for key in ("finite", "prefill_cache_present", "decode_cache_present", "prefill_top1_equal", "decode_top1_equal")):
        fail("cache forward gate did not pass")
    if any(_decimal(forward[key], f"cache {key}") > Decimal("0.02") for key in ("prefill_max_abs_delta", "decode_max_abs_delta")):
        fail("cache forward delta exceeded 0.02")
    memory = _exact(value["memory"], ["policy", "maximum_live_4b_models", "phases"], "memory")
    if memory["policy"] != "phase_serial_release_gc_empty_cache" or memory["maximum_live_4b_models"] != 1:
        fail("L4 memory-safety policy changed")
    if type(memory["phases"]) is not list or [row.get("phase") for row in memory["phases"]] != ["materialize_save", "base_replay", "peft_step", "adapter_reload_merge", "clean_judge"]:
        fail("memory phase ordering changed")
    for row in memory["phases"]:
        row = _exact(row, ["phase", "allocated_bytes", "reserved_bytes", "max_allocated_bytes", "max_reserved_bytes", "device_total_bytes", "post_release_allocated_bytes"], "memory phase")
        for key in set(row) - {"phase"}:
            _integer(row[key], f"memory {key}", minimum=0)
        if row["max_allocated_bytes"] > row["device_total_bytes"] or row["max_reserved_bytes"] > row["device_total_bytes"]:
            fail("memory telemetry exceeds device capacity")
        if row["post_release_allocated_bytes"] > 1_000_000_000:
            fail("phase release retained more than 1 GB of live CUDA tensors")
    digest_value = _digest(value["evidence_sha256"], "evidence hash")
    if evidence_sha256 is not None and digest_value != evidence_sha256:
        fail("report/evidence hash mismatch")
    return value


def validate_archive_internal(root: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    root = strict_path(root, "smoke archive")
    if not root.is_dir():
        fail("smoke archive missing")
    members = set()
    for path in root.iterdir():
        strict_path(path, "smoke archive member")
        if not path.is_file():
            fail("smoke archive contains a non-regular member")
        members.add(path.name)
    if members != ARCHIVE_MEMBERS:
        fail("smoke archive exact file surface changed")
    manifest = _parse_manifest(root / "MANIFEST.sha256")
    if set(manifest) != ARCHIVE_MEMBERS - {"MANIFEST.sha256"}:
        fail("smoke manifest membership changed")
    for name, expected in manifest.items():
        if sha256_file(root / name) != expected:
            fail(f"smoke member hash mismatch: {name}")
    evidence = validate_evidence(_load_json(root / "evidence.json", "smoke evidence"))
    report = validate_report(_load_json(root / "report.json", "smoke report"), evidence_sha256=manifest["evidence.json"])
    if _hash_rows(evidence["base_token_rows"]) != report["roundtrip"]["base_continuations_sha256"]:
        fail("sealed base token rows differ from the roundtrip report")
    command = _exact(_load_json(root / "command.json", "smoke command"), ["version", "argv", "cwd", "report_sha256", "evidence_sha256"], "command")
    if (
        command["version"] != VERSION
        or type(command["argv"]) is not list
        or len(command["argv"]) != 3
        or command["argv"][:2] != ["observe-and-seal", "--repo"]
        or type(command["argv"][2]) is not str
        or not Path(command["argv"][2]).is_absolute()
        or type(command["cwd"]) is not str
        or not Path(command["cwd"]).is_absolute()
    ):
        fail("smoke command schema changed")
    if command["report_sha256"] != manifest["report.json"] or command["evidence_sha256"] != manifest["evidence.json"]:
        fail("smoke command cross-file hashes changed")
    if sha256_file(root / "runner_source.py") != report["source"]["runner_sha256"]:
        fail("archived runner source differs from the committed source binding")
    complete = _exact(_load_json(root / "COMPLETE.json", "smoke completion"), ["version", "status", "report_sha256", "evidence_sha256", "manifest_members"], "completion")
    if complete != {
        "version": ARCHIVE_VERSION,
        "status": report["status"],
        "report_sha256": manifest["report.json"],
        "evidence_sha256": manifest["evidence.json"],
        "manifest_members": sorted(ARCHIVE_MEMBERS - {"MANIFEST.sha256"}),
    }:
        fail("smoke completion semantics changed")
    return report, evidence


def _publish_archive(project_io: Any, root: Path, report: Mapping[str, Any], evidence: Mapping[str, Any], command: Sequence[str]) -> None:
    root = strict_path(root, "smoke archive", include_leaf=False)
    if root.exists():
        fail("smoke archive already exists; replacement is forbidden")
    root.parent.mkdir(parents=True, exist_ok=True)
    temporary = strict_path(root.with_name(root.name + ".tmp"), "partial smoke archive", include_leaf=False)
    if temporary.exists():
        fail("partial smoke archive already exists")
    temporary.mkdir(parents=False, exist_ok=False)
    report_bytes = canonical_json_bytes(report)
    evidence_bytes = canonical_json_bytes(evidence)
    command_record = {
        "version": VERSION,
        "argv": list(command),
        "cwd": os.getcwd(),
        "report_sha256": sha256_bytes(report_bytes),
        "evidence_sha256": sha256_bytes(evidence_bytes),
    }
    members = {
        "report.json": report_bytes,
        "evidence.json": evidence_bytes,
        "command.json": canonical_json_bytes(command_record),
        "runner_source.py": Path(__file__).read_bytes(),
    }
    for name, payload in members.items():
        _write_new(temporary / name, payload)
    hashes = {name: sha256_bytes(payload) for name, payload in members.items()}
    complete = {
        "version": ARCHIVE_VERSION,
        "status": report["status"],
        "report_sha256": hashes["report.json"],
        "evidence_sha256": hashes["evidence.json"],
        "manifest_members": sorted(ARCHIVE_MEMBERS - {"MANIFEST.sha256"}),
    }
    complete_bytes = canonical_json_bytes(complete)
    _write_new(temporary / "COMPLETE.json", complete_bytes)
    hashes["COMPLETE.json"] = sha256_bytes(complete_bytes)
    _write_new(temporary / "MANIFEST.sha256", _archive_manifest_bytes(hashes))
    project_io._publish_directory_no_replace(temporary, root)


def observe_and_seal(*, repo: Path) -> dict[str, Any]:
    repo = strict_path(repo, "repository")
    paths = canonical_paths(repo)
    runtime_archive = strict_path(paths["runtime_archive"], "runtime archive")
    runtime_lock = strict_path(paths["runtime_lock"], "runtime lock")
    provenance_spec = strict_path(paths["provenance_spec"], "provenance spec")
    model_archive = strict_path(paths["model_archive"], "model archive")
    project_output = strict_path(paths["project"], "project output", include_leaf=False)
    adapter_output = strict_path(paths["adapter"], "adapter output", include_leaf=False)
    archive_output = strict_path(paths["smoke"], "smoke output", include_leaf=False)
    head, sources = committed_sources(repo)
    model_q, project_io = _load_modules(repo)
    observation, runtime_qualification, spec, validated_head = _validate_upstreams(
        repo=repo, model_q=model_q, model_archive=model_archive, runtime_archive=runtime_archive,
        runtime_lock=runtime_lock, provenance_spec=provenance_spec,
    )
    if validated_head != head:
        fail("committed source and provenance HEAD differ")
    declared_parent = model_q.runtime_q._resolve_declared(repo, spec["parent_model"]["root"], "parent model")
    for path in (project_output, adapter_output, archive_output):
        if path.exists():
            fail(f"fresh immutable output required: {path}")
    if len({strict_path(path.parent, "output parent") for path in (project_output, adapter_output, archive_output)}) != 1:
        fail("project, adapter, and smoke archives must share one immutable output parent")
    ruler_root = model_q.runtime_q._resolve_declared(repo, spec["clean_ruler"]["root"], "clean ruler")
    normalization_paths: dict[str, Path] = {}
    for role in ("baseline", "terminal", "ladder"):
        record = observation["scalar"]["normalization_sources"][role]
        candidate = strict_path(ruler_root / record["path"], f"{role} normalization")
        if spec["clean_ruler"]["files_sha256"].get(record["path"]) != record["sha256"] or sha256_file(candidate) != record["sha256"]:
            fail(f"{role} normalization source differs from sealed clean ruler")
        normalization_paths[role] = candidate
    project_modules = model_q._verified_project_modules(
        repo, observation["provenance"]["committed_sources"],
        {"eval_decay_scalar", "decay_scalar_normalization"},
    )
    eval_module = project_modules["eval_decay_scalar"]
    normalization = project_modules["decay_scalar_normalization"]
    import torch
    from transformers import AutoTokenizer, Gemma3ForConditionalGeneration
    project_io._runtime()
    # The native project boundary uses exact class identity.  Transform with
    # the very same verified text/core module objects owned by that loader;
    # a separately executed source-identical class graph is intentionally not
    # accepted by save_project.
    text_model = project_io.TEXT
    core = text_model.CORE
    live_runtime = model_q.runtime_q.validate_runtime_observation(model_q.runtime_q.capture_live_runtime())
    if live_runtime != model_q.runtime_q.load_canonical_json(runtime_archive / "runtime_observation.json"):
        fail("runtime changed immediately before materialization")
    if not torch.cuda.is_available() or torch.cuda.device_count() != 1 or torch.cuda.get_device_name(0) != "NVIDIA L4":
        fail("real smoke requires the single frozen NVIDIA L4")
    device = torch.device("cuda", 0)
    torch.manual_seed(SEED)
    torch.cuda.manual_seed_all(SEED)
    tokenizer = AutoTokenizer.from_pretrained(declared_parent, local_files_only=True)
    tokenizer.padding_side = "left"
    if tokenizer.pad_token_id is None:
        tokenizer.pad_token_id = tokenizer.eos_token_id
    records = model_q._prompt_records(repo, eval_module)
    prompt_ids = [row["id"] for row in records]
    prompts = [row["prompt"] for row in records]
    if _hash_rows(prompt_ids) != PROMPT_IDS_SHA256:
        fail("frozen scalar prompt surface changed")
    slicing, source, calibration = _project_records(
        repo, project_io, spec, sources, head, model_archive, provenance_spec
    )
    memory: list[dict[str, Any]] = []

    # Phase 1: exact parent -> qualified nonidentity full-width text model -> native shards.
    _reset_peak(torch)
    conditional = Gemma3ForConditionalGeneration.from_pretrained(
        declared_parent, torch_dtype=torch.bfloat16, device_map={"": 0}, local_files_only=True
    ).eval()
    triplets, basis_records = model_q._fixed_bases(torch, core, device)
    transformed, layer_reports, endpoint = model_q._install_full_width_model(
        torch, core, text_model, conditional, triplets
    )
    del conditional, triplets
    if len(layer_reports) != 34 or len(basis_records) != 34 or endpoint["head_untied_after"] is not True:
        fail("materialized endpoint differs from the qualified model boundary")
    project_archive = project_io.save_project(
        transformed,
        tokenizer_root=declared_parent,
        slicing=slicing,
        source=source,
        calibration=calibration,
        output=project_output,
    )
    memory.append(_gpu_record(torch, "materialize_save"))
    transformed.zero_grad(set_to_none=True)
    del transformed, layer_reports, basis_records, endpoint
    _collect(torch)
    memory[-1]["post_release_allocated_bytes"] = int(torch.cuda.memory_allocated(device))

    # Phase 2: only the strict native loader may construct the executable base.
    _reset_peak(torch)
    loaded = project_io.load_project(project_output, device=device)
    _prepare_project_tokenizer(loaded.tokenizer)
    base_text, base_rows, base_wrong, base_limited = _generate(
        model_q, torch, loaded.model, loaded.tokenizer, prompts, device
    )
    base_hash = _hash_rows(base_rows)
    qualified_hash = observation["scalar"]["transformed_continuations_sha256"]
    if base_hash != qualified_hash or base_wrong != 0 or base_limited != 0:
        fail("native project generation differs from the sealed qualified model")
    cache_no = _generate_with_cache_setting(torch, loaded.model, loaded.tokenizer, prompts[0], device, False)
    cache_yes = _generate_with_cache_setting(torch, loaded.model, loaded.tokenizer, prompts[0], device, True)
    cache_forward = _cache_forward_record(torch, loaded.model, loaded.tokenizer, prompts[0], device)
    if cache_no != cache_yes:
        fail("real greedy cache/no-cache generation differs")
    memory.append(_gpu_record(torch, "base_replay"))
    loaded.model.zero_grad(set_to_none=True)
    del loaded
    _collect(torch)
    memory[-1]["post_release_allocated_bytes"] = int(torch.cuda.memory_allocated(device))

    # Phase 3: one exact rank-2/alpha-2 LoRA step, then immutable adapter save.
    _reset_peak(torch)
    project = project_io.load_project(project_output, device=device)
    _prepare_project_tokenizer(project.tokenizer)
    torch.manual_seed(SEED)
    torch.cuda.manual_seed_all(SEED)
    wrapped = project_io.attach_project_lora(project, rank=LORA_RANK, alpha=LORA_ALPHA, adapter_name="default")
    train_ids, train_mask, training_surface = _render_training_surface(torch, project.tokenizer, device)
    trainable = [parameter for parameter in wrapped.parameters() if parameter.requires_grad]
    before_trainable = [project_io.tensor_sha256(parameter) for parameter in trainable]
    optimizer = torch.optim.AdamW(trainable, lr=float(LEARNING_RATE_TEXT), weight_decay=float(WEIGHT_DECAY_TEXT))
    wrapped.train()
    result = wrapped(input_ids=train_ids, attention_mask=train_mask, labels=train_ids, use_cache=False, return_dict=True)
    if result.loss is None or not bool(torch.isfinite(result.loss).item()):
        fail("one-step PEFT loss is non-finite")
    loss_text = decimal_text(result.loss.detach().float().cpu().item())
    result.loss.backward()
    gradients_ok = all(
        parameter.dtype is torch.float32 and parameter.grad is not None
        and parameter.grad.dtype is torch.float32 and bool(torch.isfinite(parameter.grad).all().item())
        for parameter in trainable
    )
    if not gradients_ok:
        fail("one-step PEFT gradients are not complete finite FP32")
    optimizer.step()
    optimizer_tensors = [item for state in optimizer.state.values() for item in state.values() if isinstance(item, torch.Tensor)]
    optimizer_ok = bool(optimizer_tensors) and all(item.dtype is torch.float32 and bool(torch.isfinite(item).all().item()) for item in optimizer_tensors)
    if not optimizer_ok:
        fail("one-step PEFT optimizer state is not finite FP32")
    after_trainable = [project_io.tensor_sha256(parameter) for parameter in trainable]
    changed_count = sum(left != right for left, right in zip(before_trainable, after_trainable, strict=True))
    if changed_count < 1:
        fail("one-step PEFT changed no trainable tensor")
    optimizer.zero_grad(set_to_none=True)
    del result
    _collect(torch)
    wrapped.eval()
    with torch.inference_mode():
        adapted_training_logits = wrapped(input_ids=train_ids, attention_mask=train_mask, use_cache=False).logits.float().cpu()
    adapted_text, adapted_rows, adapted_wrong, adapted_limited = _generate(
        model_q, torch, wrapped, project.tokenizer, prompts, device
    )
    if adapted_wrong != 0 or adapted_limited != 0:
        fail("one-step adapter produced wrong/limited scalar generations")
    adapter_archive = project_io.save_adapter(project, wrapped, output=adapter_output)
    memory.append(_gpu_record(torch, "peft_step"))
    wrapped.zero_grad(set_to_none=True)
    del optimizer, trainable, optimizer_tensors, wrapped, project, train_ids, train_mask
    _collect(torch)
    memory[-1]["post_release_allocated_bytes"] = int(torch.cuda.memory_allocated(device))

    # Phase 4: reload from native project+adapter, compare, then merge in place.
    _reset_peak(torch)
    replay_project = project_io.load_project(project_output, device=device)
    _prepare_project_tokenizer(replay_project.tokenizer)
    reloaded = project_io.load_adapter(replay_project, adapter_output)
    reloaded.eval()
    replay_ids = torch.tensor([training_surface["input_ids"]], dtype=torch.int64, device=device)
    replay_mask = torch.tensor([training_surface["attention_mask"]], dtype=torch.int64, device=device)
    with torch.inference_mode():
        reloaded_training_logits = reloaded(input_ids=replay_ids, attention_mask=replay_mask, use_cache=False).logits.float().cpu()
    if not torch.equal(adapted_training_logits, reloaded_training_logits):
        fail("adapter save/reload logits are not bit-identical")
    reloaded_text, reloaded_rows, reloaded_wrong, reloaded_limited = _generate(
        model_q, torch, reloaded, replay_project.tokenizer, prompts, device
    )
    if adapted_rows != reloaded_rows or adapted_text != reloaded_text or reloaded_wrong != 0 or reloaded_limited != 0:
        fail("adapter save/reload generation is not byte-identical")
    merged = reloaded.merge_and_unload(safe_merge=True)
    if type(merged) is not project_io.TEXT.Gemma3SliceGPTTextForCausalLMV4:
        fail("merge did not return the exact canonical text-model class")
    project_io.TEXT.validate_text_model(merged)
    merged.tie_weights()
    merged.eval()
    with torch.inference_mode():
        merged_training_logits = merged(input_ids=replay_ids, attention_mask=replay_mask, use_cache=False).logits.float().cpu()
    merge_delta = float((reloaded_training_logits - merged_training_logits).abs().max().item())
    merge_top1 = bool(torch.equal(reloaded_training_logits.argmax(-1), merged_training_logits.argmax(-1)))
    if not merge_top1 or merge_delta > float(MAX_MERGE_LOGIT_DELTA_TEXT):
        fail("merged logits exceed the strict equivalence boundary")
    merged_text, merged_rows, merged_wrong, merged_limited = _generate(
        model_q, torch, merged, replay_project.tokenizer, prompts, device
    )
    if merged_rows != reloaded_rows or merged_text != reloaded_text or merged_wrong != 0 or merged_limited != 0:
        fail("adapter reload/merge generation is not byte-identical")
    memory.append(_gpu_record(torch, "adapter_reload_merge"))
    merged.zero_grad(set_to_none=True)
    del merged, reloaded, replay_project, replay_ids, replay_mask, reloaded_training_logits, merged_training_logits
    _collect(torch)
    memory[-1]["post_release_allocated_bytes"] = int(torch.cuda.memory_allocated(device))

    # Phase 5: the clean parent acts only as the frozen scalar judge.
    _reset_peak(torch)
    judge = Gemma3ForConditionalGeneration.from_pretrained(
        declared_parent, torch_dtype=torch.bfloat16, device_map={"": 0}, local_files_only=True
    ).eval()
    judge_prompts = [
        eval_module.JUDGE_RUBRIC.format(prompt=row["prompt"], response=response or "(empty)")
        for row, response in zip(records, merged_text, strict=True)
    ]
    judge_texts, _, judge_wrong, judge_limited = model_q._generate(
        torch, judge, tokenizer, judge_prompts, device, max_new_tokens=16
    )
    judge_scores = [eval_module.parse_judge_score(value) for value in judge_texts]
    if judge_wrong != 0 or any(value is None for value in judge_scores):
        fail("frozen scalar judge produced wrong-prefix/unparsed output")
    scalar = _scalar_record(
        model_q=model_q, eval_module=eval_module, normalization=normalization, tokenizer=tokenizer,
        records=records, generations=merged_text, judge_scores=judge_scores,
        baseline=normalization_paths["baseline"], terminal=normalization_paths["terminal"],
        ladder=normalization_paths["ladder"], base_scalar=observation["scalar"],
    )
    memory.append(_gpu_record(torch, "clean_judge"))
    judge.zero_grad(set_to_none=True)
    del judge
    _collect(torch)
    memory[-1]["post_release_allocated_bytes"] = int(torch.cuda.memory_allocated(device))

    evidence = {
        "version": EVIDENCE_VERSION,
        "prompt_ids": prompt_ids,
        "base_token_rows": base_rows,
        "adapted_token_rows": adapted_rows,
        "reloaded_token_rows": reloaded_rows,
        "merged_token_rows": merged_rows,
        "merged_generations": merged_text,
        "judge_texts": judge_texts,
        "judge_scores": [int(value) for value in judge_scores],
        "training_surface": training_surface,
        "cache_generate_no_cache": cache_no,
        "cache_generate_cache": cache_yes,
    }
    evidence_bytes = canonical_json_bytes(evidence)
    project_state = _project_state_summary(project_io, project_archive)
    project_shards = sorted(set(project_archive["weight_map"].values()))
    report = {
        "version": REPORT_VERSION,
        "status": "PASS_FULL_WIDTH_PROJECT_IO_AND_PEFT_SMOKE",
        "scope": "FULL_WIDTH_PROJECT_IO_AND_ONE_STEP_PEFT_ONLY",
        "probe2_verdict": None,
        "nonzero_slice_authorized": False,
        "capability_issued": False,
        "source": {
            "repo_commit": head,
            "committed_sources": dict(sources),
            "runner_sha256": sources[RUNNER_PATH],
            "project_io_sha256": PROJECT_IO_SHA256,
            "model_qualifier_sha256": MODEL_QUALIFIER_SHA256,
        },
        "upstream": {
            "runtime_archive_manifest_sha256": sha256_file(runtime_archive / "MANIFEST.sha256"),
            "runtime_identity_fingerprint": runtime_qualification["identity_fingerprint"],
            "provenance_spec_sha256": sha256_file(provenance_spec),
            "model_archive_manifest_sha256": sha256_file(model_archive / "MANIFEST.sha256"),
            "model_observation_sha256": sha256_file(model_archive / "observation.json"),
            "parent_fingerprint": spec["parent_model"]["fingerprint"],
            "calibration_fingerprint": spec["calibration"]["archives"][str(CALIBRATION_SEED)]["metadata_fingerprint"],
            "calibration_tensors_sha256": spec["calibration"]["archives"][str(CALIBRATION_SEED)]["tensors_sha256"],
        },
        "project": {
            "manifest_sha256": project_archive["manifest_sha256"],
            "state_fingerprint": project_state["state_fingerprint"],
            "tensor_count": project_state["tensor_count"],
            "total_size": project_state["total_size"],
            "shard_count": len(project_shards),
            "full_width": True,
            "fraction": "0",
            "calibration_seed": CALIBRATION_SEED,
            "tokenizer_padding_side": "left",
        },
        "roundtrip": {
            "bit_identical_state": True,
            "base_continuations_sha256": base_hash,
            "qualified_continuations_sha256": qualified_hash,
            "byte_identical_generation": base_hash == qualified_hash,
            "wrong_count": base_wrong,
            "limited_count": base_limited,
        },
        "peft": {
            "rank": LORA_RANK,
            "alpha": LORA_ALPHA,
            "seed": SEED,
            "learning_rate": LEARNING_RATE_TEXT,
            "weight_decay": WEIGHT_DECAY_TEXT,
            "target_module_count": EXPECTED_TARGET_COUNT,
            "trainable_tensor_count": EXPECTED_TRAINABLE_COUNT,
            "loss": loss_text,
            "finite_fp32_gradients": gradients_ok,
            "finite_fp32_optimizer_state": optimizer_ok,
            "changed_trainable_count": changed_count,
            "adapter_manifest_sha256": adapter_archive["manifest_sha256"],
            "adapter_state_fingerprint": adapter_archive["config"]["state_fingerprint"],
            "save_reload_logits_bit_identical": True,
            "save_reload_generation_bit_identical": adapted_rows == reloaded_rows,
            "merged_top1_identical": merge_top1,
            "merged_max_abs_logit_delta": decimal_text(merge_delta),
            "merged_generation_bit_identical": reloaded_rows == merged_rows,
        },
        "scalar": scalar,
        "cache": {"generation_equal": cache_no == cache_yes, "forward": cache_forward},
        "memory": {"policy": "phase_serial_release_gc_empty_cache", "maximum_live_4b_models": 1, "phases": memory},
        "evidence_sha256": sha256_bytes(evidence_bytes),
        "remaining_gate": "sealed reduced-width capability issuer",
    }
    validate_evidence(evidence)
    validate_report(report, evidence_sha256=sha256_bytes(evidence_bytes))
    _publish_archive(
        project_io, archive_output, report, evidence,
        ["observe-and-seal", "--repo", str(repo)],
    )
    validate_archive_internal(archive_output)
    return report


def replay(*, repo: Path) -> dict[str, Any]:
    repo = strict_path(repo, "repository")
    paths = canonical_paths(repo)
    project_root, adapter_root, archive_root = paths["project"], paths["adapter"], paths["smoke"]
    runtime_archive, runtime_lock = paths["runtime_archive"], paths["runtime_lock"]
    provenance_spec, model_archive = paths["provenance_spec"], paths["model_archive"]
    head, sources = committed_sources(repo)
    model_q, project_io = _load_modules(repo)
    report, evidence = validate_archive_internal(archive_root)
    sealed_head = report["source"]["repo_commit"]
    try:
        _git(repo, "merge-base", "--is-ancestor", sealed_head, head)
    except SmokeError:
        fail("smoke archive source commit is not an ancestor of current HEAD")
    if report["source"]["committed_sources"] != sources:
        fail("smoke archive source bytes differ from current committed HEAD")
    observation, runtime_qualification, spec, _ = _validate_upstreams(
        repo=repo, model_q=model_q, model_archive=model_archive, runtime_archive=runtime_archive,
        runtime_lock=runtime_lock, provenance_spec=provenance_spec,
    )
    replay_modules = model_q._verified_project_modules(
        repo, observation["provenance"]["committed_sources"],
        {"eval_decay_scalar", "decay_scalar_normalization"},
    )
    eval_module = replay_modules["eval_decay_scalar"]
    normalization = replay_modules["decay_scalar_normalization"]
    project = project_io.validate_project_archive(project_root)
    project_state = _project_state_summary(project_io, project)
    adapter = project_io.validate_adapter_archive(
        adapter_root, expected_project_manifest_sha256=project["manifest_sha256"]
    )
    if (
        report["project"]["manifest_sha256"] != project["manifest_sha256"]
        or report["project"]["state_fingerprint"] != project_state["state_fingerprint"]
        or report["peft"]["adapter_manifest_sha256"] != adapter["manifest_sha256"]
        or report["peft"]["adapter_state_fingerprint"] != adapter["config"]["state_fingerprint"]
    ):
        fail("smoke report differs from the immutable project/adapter archives")
    if report["roundtrip"]["qualified_continuations_sha256"] != observation["scalar"]["transformed_continuations_sha256"]:
        fail("smoke base generation differs from the model qualification archive")
    if report["upstream"] != {
        "runtime_archive_manifest_sha256": sha256_file(runtime_archive / "MANIFEST.sha256"),
        "runtime_identity_fingerprint": runtime_qualification["identity_fingerprint"],
        "provenance_spec_sha256": sha256_file(provenance_spec),
        "model_archive_manifest_sha256": sha256_file(model_archive / "MANIFEST.sha256"),
        "model_observation_sha256": sha256_file(model_archive / "observation.json"),
        "parent_fingerprint": spec["parent_model"]["fingerprint"],
        "calibration_fingerprint": spec["calibration"]["archives"][str(CALIBRATION_SEED)]["metadata_fingerprint"],
        "calibration_tensors_sha256": spec["calibration"]["archives"][str(CALIBRATION_SEED)]["tensors_sha256"],
    }:
        fail("smoke upstream archive bindings changed")
    # Offline replay re-decodes the exact stored merged rows through the sole
    # project tokenizer.  This requires no GPU and never constructs a model.
    tokenizer = project_io.AutoTokenizer.from_pretrained(project_root, local_files_only=True)
    _prepare_project_tokenizer(tokenizer)
    decoded = [tokenizer.decode(row, skip_special_tokens=True).strip() for row in evidence["merged_token_rows"]]
    if decoded != evidence["merged_generations"]:
        fail("stored merged text does not decode from the sealed token rows")
    torch_module = project_io.torch
    _, _, replay_training = _render_training_surface(torch_module, tokenizer, torch_module.device("cpu"))
    if replay_training != evidence["training_surface"]:
        fail("sealed training input does not reproduce through the project tokenizer")
    parsed = [eval_module.parse_judge_score(value) for value in evidence["judge_texts"]]
    if parsed != evidence["judge_scores"]:
        fail("stored judge scores do not parse from the sealed judge outputs")
    records = model_q._prompt_records(repo, eval_module)
    ruler_root = model_q.runtime_q._resolve_declared(repo, spec["clean_ruler"]["root"], "clean ruler")
    normalization_paths = {
        role: strict_path(
            ruler_root / observation["scalar"]["normalization_sources"][role]["path"],
            f"{role} normalization",
        )
        for role in ("baseline", "terminal", "ladder")
    }
    recomputed_scalar = _scalar_record(
        model_q=model_q, eval_module=eval_module, normalization=normalization,
        tokenizer=tokenizer, records=records, generations=decoded, judge_scores=parsed,
        baseline=normalization_paths["baseline"], terminal=normalization_paths["terminal"],
        ladder=normalization_paths["ladder"], base_scalar=observation["scalar"],
    )
    if recomputed_scalar != report["scalar"]:
        fail("sealed scalar report differs from semantic replay")
    return report


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    observe = commands.add_parser("observe-and-seal")
    observe.add_argument("--repo", type=Path, default=Path.cwd())
    verify = commands.add_parser("replay")
    verify.add_argument("--repo", type=Path, default=Path.cwd())
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    args = _parser().parse_args(arguments)
    if args.command == "observe-and-seal":
        report = observe_and_seal(repo=args.repo)
    else:
        report = replay(repo=args.repo)
    print(json.dumps({"status": report["status"], "scope": report["scope"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
