"""Project an edited checkpoint delta away from clean retain subspaces.

This tool implements the one-sided AlphaEdit/CARE-style operation

    W_new = W_clean + Delta @ (I - U @ U.T)

for an explicitly declared set of Gemma-3 text-decoder linear weights.  ``U``
is a deterministic PCA basis of clean module-input vectors collected only from
explicitly labelled, training-only retain prompts.  The implementation never
forms the usually enormous feature covariance: it eigendecomposes the
mathematically equivalent float64 token-token (dual) covariance and lifts the
basis back into feature space.

The checkpoint contract is deliberately strict.  Clean and edited inputs must
be exact local Safetensors directories for ``Gemma3ForConditionalGeneration``;
the edited state must differ from clean on exactly all seven bias-free LoRA
surface weights in every declared layer; and every unselected output tensor is
verified byte-for-byte against clean.  Publication is atomic and no-replace,
with an immutable provenance sidecar and a fresh offline reload verification.
"""

from __future__ import annotations

import argparse
import datetime as dt
import gc
import hashlib
import json
import math
import os
import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence

try:
    import apply_causal_mlp_mask as checkpoint_utils
    import causal_mlp_neuron_selection as selection
    import fingerprint_safetensors_values as logical_fingerprint
    import apply_checkpoint_delta_dare as source_pins
except ModuleNotFoundError:
    from scripts import apply_causal_mlp_mask as checkpoint_utils
    from scripts import causal_mlp_neuron_selection as selection
    from scripts import fingerprint_safetensors_values as logical_fingerprint
    from scripts import apply_checkpoint_delta_dare as source_pins


SCHEMA_VERSION = "retain_subspace_delta_projection_v1"
RETAIN_DATA_SCHEMA_VERSION = "frozen_native_retain_corpora_v1"
SIDECAR_NAME = "retain_subspace_delta_projection.json"
LINEAR_SUFFIXES = (
    "self_attn.q_proj",
    "self_attn.k_proj",
    "self_attn.v_proj",
    "self_attn.o_proj",
    "mlp.gate_proj",
    "mlp.up_proj",
    "mlp.down_proj",
)
FORBIDDEN_DATA_PATH_TOKENS = {
    "dev",
    "eval",
    "evaluation",
    "heldout",
    "held",
    "test",
    "testing",
    "valid",
    "validation",
}


def _finite_energy(value: Any) -> float:
    if isinstance(value, bool):
        raise ValueError("retained-energy must be a finite number in [0, 1]")
    try:
        result = float(value)
    except (TypeError, ValueError) as error:
        raise ValueError(
            "retained-energy must be a finite number in [0, 1]"
        ) from error
    if not math.isfinite(result) or not 0.0 <= result <= 1.0:
        raise ValueError("retained-energy must be a finite number in [0, 1]")
    return result


def _positive_integer(value: Any, label: str) -> int:
    if isinstance(value, bool):
        raise ValueError(f"{label} must be a positive integer")
    try:
        result = int(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{label} must be a positive integer") from error
    if result <= 0 or str(value).strip() != str(result):
        raise ValueError(f"{label} must be a positive integer")
    return result


def _nonnegative_seed(value: Any) -> int:
    if isinstance(value, bool):
        raise ValueError("seed must be a non-negative integer")
    try:
        result = int(value)
    except (TypeError, ValueError) as error:
        raise ValueError("seed must be a non-negative integer") from error
    if result < 0 or result >= 2**63 or str(value).strip() != str(result):
        raise ValueError("seed must be an integer in [0, 2**63)")
    return result


def _sha256_argument(value: Any, label: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value):
        raise ValueError(f"{label} must be a lowercase 64-hex SHA-256 digest")
    return value


def parse_args(argv: Iterable[str] | None = None):
    parser = argparse.ArgumentParser(
        description=(
            "Project the exact clean-to-edited Gemma-3 delta away from clean "
            "training-only retain activation subspaces."
        )
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    digest = subparsers.add_parser(
        "digest",
        help="Print a serialization-independent logical checkpoint digest.",
    )
    digest.add_argument("--model", required=True)
    project = subparsers.add_parser(
        "project", help="Run and atomically publish the retain projection."
    )
    project.add_argument("--clean-model", required=True)
    project.add_argument("--edited-model", required=True)
    project.add_argument("--tokenizer-model", required=True)
    project.add_argument(
        "--expected-edited-logical-sha256",
        required=True,
        type=lambda value: _sha256_argument(
            value, "expected-edited-logical-sha256"
        ),
        help=(
            "Canonical key/dtype/shape/value digest from the qualified donor, "
            "obtained with the digest subcommand."
        ),
    )
    project.add_argument(
        "--expected-edited-weight-sha256",
        required=True,
        type=lambda value: _sha256_argument(
            value, "expected-edited-weight-sha256"
        ),
        help="Exact qualified donor Safetensors file SHA-256.",
    )
    project.add_argument(
        "--retain-json",
        action="append",
        required=True,
        help=(
            "Repeatable exact local JSON file containing a frozen native list "
            "of generic strings or clean prompt/answer records."
        ),
    )
    project.add_argument(
        "--evaluation-json",
        action="append",
        required=True,
        help=(
            "Repeatable held-out evaluation JSON used only to prove zero exact "
            "prompt/history overlap; never forwarded through the model."
        ),
    )
    project.add_argument(
        "--expected-retain-records",
        required=True,
        type=lambda value: _positive_integer(value, "expected-retain-records"),
    )
    project.add_argument(
        "--layers",
        required=True,
        help="Explicit comma/range decoder layers, for example 12-19,28-33.",
    )
    project.add_argument("--output-dir", required=True)
    project.add_argument("--retained-energy", required=True, type=_finite_energy)
    project.add_argument("--cache-dir", help="Optional immutable hash-bound retain-key and spectrum cache.")
    project.add_argument(
        "--max-prompts",
        default=4096,
        type=lambda value: _positive_integer(value, "max-prompts"),
    )
    project.add_argument(
        "--max-length",
        default=256,
        type=lambda value: _positive_integer(value, "max-length"),
    )
    project.add_argument(
        "--batch-size",
        default=4,
        type=lambda value: _positive_integer(value, "batch-size"),
    )
    project.add_argument(
        "--cutoff-tie-rtol",
        default=1e-10,
        type=float,
        help="Fail when the selected PCA rank cuts an eigenvalue tie.",
    )
    return parser.parse_args(argv)


def parse_layer_spec(spec: str) -> list[int]:
    """Parse and canonicalize an explicit inclusive comma/range list."""

    layers = selection.parse_layer_spec(spec)
    canonical = ",".join(str(layer) for layer in layers)
    if not layers or any(layer < 0 for layer in layers):
        raise ValueError("layer specification selected no valid layers")
    # Duplicate spellings are rejected rather than silently changing the
    # declared experiment surface.  Ranges themselves remain supported.
    expanded_count = 0
    for raw in spec.split(","):
        part = raw.strip()
        if "-" in part:
            lower, upper = (int(item.strip()) for item in part.split("-"))
            expanded_count += upper - lower + 1
        else:
            expanded_count += 1
    if expanded_count != len(layers):
        raise ValueError("layer specification contains duplicate/overlapping layers")
    if not canonical:
        raise RuntimeError("could not canonicalize layer specification")
    return layers


def declared_module_names(
    layers: Sequence[int], decoder_path: str = "model.language_model.layers"
) -> list[str]:
    if decoder_path != "model.language_model.layers":
        raise ValueError("unsupported Gemma-3 decoder path")
    if not layers or list(layers) != sorted(set(layers)):
        raise ValueError("declared layers must be non-empty, sorted, and unique")
    return [
        f"{decoder_path}.{layer}.{suffix}"
        for layer in layers
        for suffix in LINEAR_SUFFIXES
    ]


def _reject_duplicate_json_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"JSON object contains duplicate key: {key!r}")
        result[key] = value
    return result


def _load_exact_json(path: Path, label: str) -> tuple[Any, str]:
    if not path.is_file():
        raise ValueError(f"{label} must be an exact existing local file: {path}")
    try:
        raw = path.read_bytes()
        document = json.loads(
            raw.decode("utf-8"), object_pairs_hook=_reject_duplicate_json_keys
        )
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ValueError(f"could not read {label}: {path}") from error
    return document, hashlib.sha256(raw).hexdigest()


def _path_tokens(path: Path) -> set[str]:
    tokens: set[str] = set()
    for part in path.parts:
        tokens.update(
            token
            for token in re.split(r"[^a-z0-9]+", part.lower())
            if token
        )
    return tokens


def _reject_eval_like_data_path(path: Path):
    original = path.absolute()
    resolved = path.resolve(strict=True)
    forbidden = (_path_tokens(original) | _path_tokens(resolved)) & (
        FORBIDDEN_DATA_PATH_TOKENS
    )
    if forbidden:
        raise ValueError(
            "retain training input path contains a held-out/evaluation marker: "
            + ", ".join(sorted(forbidden))
        )


def load_retain_training_data(
    paths: Sequence[str | Path], *, max_prompts: int, expected_records: int
) -> tuple[list[dict], list[dict]]:
    """Load the two frozen native training schemas without deduplication."""

    max_prompts = _positive_integer(max_prompts, "max-prompts")
    if not paths:
        raise ValueError("at least one retain-json file is required")
    materialized = [Path(path) for path in paths]
    resolved = [path.resolve(strict=True) for path in materialized]
    if len(resolved) != len(set(resolved)):
        raise ValueError("retain-json paths must be unique")

    expected_records = _positive_integer(
        expected_records, "expected-retain-records"
    )
    records: list[dict] = []
    sources: list[dict] = []
    for path in sorted(materialized, key=lambda item: str(item.resolve()).lower()):
        _reject_eval_like_data_path(path)
        document, file_sha256 = _load_exact_json(path, "retain-json")
        if not isinstance(document, list) or not document:
            raise ValueError("retain-json root must be a non-empty native list")
        source_count = 0
        schema_counts: dict[str, int] = {}
        for index, raw_record in enumerate(document):
            record_id = f"{file_sha256[:16]}:{index:06d}"
            if isinstance(raw_record, str):
                if not raw_record.strip() or len(raw_record) > 65536 or "\x00" in raw_record:
                    raise ValueError(f"retain-json generic string {index} is invalid")
                schema_family = "generic_string"
                messages = [{"role": "user", "content": raw_record}]
                answer = None
            elif isinstance(raw_record, dict):
                keys = set(raw_record)
                known_schemas = {
                    frozenset(
                        {"id", "category", "prompt", "answer", "template_family"}
                    ): "captured_event_pair",
                    frozenset(
                        {"category", "prompt", "answer", "augmentation", "seed"}
                    ): "augmented_clean_pair",
                    frozenset(
                        {
                            "answer",
                            "capture_policy",
                            "category",
                            "conversation_id",
                            "messages",
                            "turn",
                        }
                    ): "captured_multiturn_pair",
                }
                schema_family = known_schemas.get(frozenset(keys))
                if schema_family is None:
                    raise ValueError(
                        f"retain-json record {index} has an unknown native schema"
                    )
                answer = raw_record.get("answer")
                if (
                    not isinstance(answer, str)
                    or not answer.strip()
                    or len(answer) > 65536
                    or "\x00" in answer
                ):
                    raise ValueError(f"retain-json record {index} answer is invalid")
                if "messages" in raw_record:
                    messages = raw_record["messages"]
                    if not isinstance(messages, list) or not messages:
                        raise ValueError(
                            f"retain-json record {index} messages are invalid"
                        )
                    normalized_messages = []
                    for message_index, message in enumerate(messages):
                        if (
                            not isinstance(message, dict)
                            or set(message) != {"role", "content"}
                            or message.get("role") not in {"user", "assistant"}
                            or not isinstance(message.get("content"), str)
                            or not message["content"].strip()
                        ):
                            raise ValueError(
                                f"retain-json record {index} message "
                                f"{message_index} is invalid"
                            )
                        normalized_messages.append(dict(message))
                    if normalized_messages[-1]["role"] != "user":
                        raise ValueError(
                            f"retain-json record {index} history must end with user"
                        )
                    messages = normalized_messages
                else:
                    prompt = raw_record.get("prompt")
                    if (
                        not isinstance(prompt, str)
                        or not prompt.strip()
                        or len(prompt) > 65536
                        or "\x00" in prompt
                    ):
                        raise ValueError(
                            f"retain-json record {index} prompt is invalid"
                        )
                    messages = [{"role": "user", "content": prompt}]
            else:
                raise ValueError(
                    f"retain-json record {index} is neither a string nor an object"
                )
            records.append(
                {
                    "record_id": record_id,
                    "source_file_sha256": file_sha256,
                    "source_index": index,
                    "schema_family": schema_family,
                    "messages": messages,
                    "answer": answer,
                }
            )
            schema_counts[schema_family] = schema_counts.get(schema_family, 0) + 1
            source_count += 1
        sources.append(
            {
                "path": str(path.resolve(strict=True)),
                "file_sha256": file_sha256,
                "payload_sha256": selection.payload_sha256(document),
                "record_count": source_count,
                "schema_counts": schema_counts,
            }
        )
    if len(records) > max_prompts:
        raise ValueError(
            f"retain prompt count {len(records)} exceeds max-prompts {max_prompts}"
        )
    if len(records) != expected_records:
        raise ValueError(
            f"retain record count {len(records)} differs from expected "
            f"{expected_records}"
        )
    # Source-path sorting and source order define the immutable record order.
    # Duplicate semantic records are intentionally retained as independent keys.
    return records, sources


def _history_signature(messages: Sequence[Mapping]) -> str:
    normalized = [
        {"role": message["role"], "content": message["content"]}
        for message in messages
    ]
    return selection.payload_sha256(normalized)


def _retain_overlap_signatures(records: Sequence[Mapping]) -> tuple[set[str], set[str]]:
    prompts: set[str] = set()
    histories: set[str] = set()
    for record in records:
        messages = record["messages"]
        for message in messages:
            if message["role"] == "user":
                prompts.add(message["content"])
        for length in range(1, len(messages) + 1):
            histories.add(_history_signature(messages[:length]))
    return prompts, histories


def _extract_evaluation_signatures(document: Any) -> tuple[set[str], set[str]]:
    prompts: set[str] = set()
    histories: set[str] = set()

    def walk(value: Any):
        if isinstance(value, list):
            for item in value:
                walk(item)
            return
        if not isinstance(value, dict):
            return
        prompt = value.get("prompt")
        if isinstance(prompt, str) and prompt:
            prompts.add(prompt)
        turns = value.get("turns")
        if isinstance(turns, list) and turns and all(
            isinstance(item, str) and item for item in turns
        ):
            prompts.update(turns)
            for length in range(1, len(turns) + 1):
                histories.add(
                    selection.payload_sha256(
                        [{"role": "user_turn", "content": item} for item in turns[:length]]
                    )
                )
        messages = value.get("messages")
        if isinstance(messages, list) and messages and all(
            isinstance(item, dict)
            and set(item) >= {"role", "content"}
            and isinstance(item.get("role"), str)
            and isinstance(item.get("content"), str)
            for item in messages
        ):
            normalized = [
                {"role": item["role"], "content": item["content"]}
                for item in messages
            ]
            prompts.update(
                item["content"] for item in normalized if item["role"] == "user"
            )
            for length in range(1, len(normalized) + 1):
                histories.add(_history_signature(normalized[:length]))
        for key, item in value.items():
            if key not in {"prompt", "turns", "messages"}:
                walk(item)

    walk(document)
    return prompts, histories


def prove_zero_evaluation_overlap(
    retain_records: Sequence[Mapping], evaluation_paths: Sequence[str | Path]
) -> tuple[list[dict], dict]:
    """Hash held-out files and prove they are never part of retain keys."""

    if not evaluation_paths:
        raise ValueError("at least one evaluation-json file is required")
    paths = [Path(path) for path in evaluation_paths]
    resolved = [path.resolve(strict=True) for path in paths]
    if len(resolved) != len(set(resolved)):
        raise ValueError("evaluation-json paths must be unique")
    retain_prompts, retain_histories = _retain_overlap_signatures(retain_records)
    evaluation_prompts: set[str] = set()
    evaluation_histories: set[str] = set()
    sources = []
    for path in sorted(paths, key=lambda item: str(item.resolve()).lower()):
        document, file_sha256 = _load_exact_json(path, "evaluation-json")
        prompts, histories = _extract_evaluation_signatures(document)
        if not prompts and not histories:
            raise ValueError(
                f"evaluation-json contains no prompt/history signatures: {path}"
            )
        evaluation_prompts.update(prompts)
        evaluation_histories.update(histories)
        sources.append(
            {
                "path": str(path.resolve(strict=True)),
                "file_sha256": file_sha256,
                "payload_sha256": selection.payload_sha256(document),
                "prompt_signature_count": len(prompts),
                "history_signature_count": len(histories),
            }
        )
    prompt_overlap = retain_prompts & evaluation_prompts
    history_overlap = retain_histories & evaluation_histories
    if prompt_overlap or history_overlap:
        raise ValueError(
            "retain data overlaps held-out evaluation inputs exactly; "
            f"prompt_overlap={len(prompt_overlap)} "
            f"history_overlap={len(history_overlap)}"
        )
    proof = {
        "verified": True,
        "retain_prompt_signature_count": len(retain_prompts),
        "retain_history_signature_count": len(retain_histories),
        "evaluation_prompt_signature_count": len(evaluation_prompts),
        "evaluation_history_signature_count": len(evaluation_histories),
        "prompt_overlap_count": 0,
        "history_overlap_count": 0,
        "evaluation_inputs_used_for_forward_pass": False,
        "evaluation_file_records_sha256": selection.payload_sha256(sources),
    }
    return sources, proof


def _extract_token_ids(encoded: Any) -> list[int]:
    if isinstance(encoded, Mapping):
        encoded = encoded.get("input_ids")
    if hasattr(encoded, "tolist"):
        encoded = encoded.tolist()
    if isinstance(encoded, list) and encoded and isinstance(encoded[0], list):
        if len(encoded) != 1:
            raise ValueError("chat template returned an unexpected batch")
        encoded = encoded[0]
    if (
        not isinstance(encoded, list)
        or not encoded
        or any(isinstance(item, bool) or not isinstance(item, int) for item in encoded)
    ):
        raise ValueError("chat template produced invalid or empty token ids")
    return list(encoded)


def tokenize_retain_records(
    records: Sequence[Mapping], tokenizer, *, max_length: int
) -> tuple[list[dict], dict]:
    max_length = _positive_integer(max_length, "max-length")
    tokenized = []
    family_counts: dict[str, int] = {}
    for record in records:
        if record["answer"] is None:
            input_ids = _extract_token_ids(tokenizer(
                record["messages"][0]["content"], truncation=True,
                max_length=max_length,
            ))[:max_length]
            position_mask = [True] * (len(input_ids) - 1) + [False]
            position_policy = "all_shifted_nonpadding_causal_positions"
        else:
            prompt_ids = _extract_token_ids(tokenizer.apply_chat_template(
                record["messages"], add_generation_prompt=True,
                tokenize=True, return_dict=True,
            ))
            answer_ids = _extract_token_ids(
                tokenizer(record["answer"], add_special_tokens=False)
            )
            input_ids = [*prompt_ids, *answer_ids][:max_length]
            position_mask = [False] * len(input_ids)
            # Input position j-1 predicts labelled answer token j.
            for label_position in range(len(prompt_ids), len(input_ids)):
                position_mask[label_position - 1] = True
            position_policy = "shifted_teacher_forced_answer_prediction_positions"
        selected_positions = sum(position_mask)
        if selected_positions <= 0 or position_mask[-1]:
            raise ValueError(
                f"retain record has no valid shifted positions: {record['record_id']}"
            )
        tokenized.append(
            {
                "record_id": record["record_id"],
                "schema_family": record["schema_family"],
                "input_ids": input_ids,
                "position_mask": position_mask,
                "position_policy": position_policy,
            }
        )
        family_counts[record["schema_family"]] = (
            family_counts.get(record["schema_family"], 0) + 1
        )
    payload = [
        {
            "record_id": record["record_id"],
            "schema_family": record["schema_family"],
            "input_ids": record["input_ids"],
            "position_mask": record["position_mask"],
            "position_policy": record["position_policy"],
        }
        for record in tokenized
    ]
    return tokenized, {
        "retain_key_count": len(tokenized),
        "schema_family_counts": family_counts,
        "causal_nonpadding_token_count": sum(
            len(record["input_ids"]) for record in tokenized
        ),
        "selected_shifted_position_count": sum(
            sum(record["position_mask"]) for record in tokenized
        ),
        "tokenization_sha256": selection.payload_sha256(payload),
    }


def tensor_sha256(tensor, torch) -> str:
    # Flatten first: PyTorch can consider a [D,1] tensor contiguous while its
    # size-one last-axis stride is not one, which makes a direct dtype view
    # fail even after ``contiguous()``.
    values = tensor.detach().contiguous().reshape(-1)
    raw = values.view(torch.uint8).cpu().numpy().tobytes()
    return hashlib.sha256(raw).hexdigest()


def _tensor_record(tensor, torch) -> dict:
    return {
        "shape": list(tensor.shape),
        "dtype": str(tensor.dtype),
        "sha256": tensor_sha256(tensor, torch),
    }


def canonicalize_basis_signs(basis, torch):
    """Give every basis vector a deterministic largest-magnitude-positive sign."""

    if basis.ndim != 2:
        raise ValueError("basis must be a matrix")
    result = basis.clone()
    for column_index in range(result.shape[1]):
        column = result[:, column_index]
        pivot = int(torch.argmax(torch.abs(column)).item())
        if float(column[pivot]) < 0.0:
            column.mul_(-1.0)
    return result


def compute_retain_basis(
    activations,
    *,
    retained_energy: float,
    cutoff_tie_rtol: float,
    torch,
    cache_dir: str | Path | None = None,
    cache_binding: Mapping | None = None,
) -> tuple[Any, dict]:
    """Build a feature PCA basis through a float64 dual second moment."""

    retained_energy = _finite_energy(retained_energy)
    if (
        isinstance(cutoff_tie_rtol, bool)
        or not isinstance(cutoff_tie_rtol, (int, float))
        or not math.isfinite(float(cutoff_tie_rtol))
        or not 0.0 <= float(cutoff_tie_rtol) <= 1e-3
    ):
        raise ValueError("cutoff-tie-rtol must be finite and in [0, 1e-3]")
    if activations.ndim != 2 or min(activations.shape) <= 0:
        raise ValueError("activations must be a non-empty [tokens, features] matrix")
    if activations.dtype != torch.float64 or activations.device.type != "cpu":
        raise ValueError("activations must be float64 on CPU")
    if not bool(torch.isfinite(activations).all()):
        raise ValueError("activations contain non-finite values")

    token_count, feature_count = (int(value) for value in activations.shape)
    covariance = (activations @ activations.T) / float(token_count)
    if covariance.dtype != torch.float64 or not bool(torch.isfinite(covariance).all()):
        raise RuntimeError("float64 dual covariance is invalid")
    spectral_binding = {
        "kind": "dual_eigenpairs_v1", "parent": dict(cache_binding or {}),
        "covariance": _tensor_record(covariance, torch),
    }
    def decompose():
        eigenvalues, eigenvectors = torch.linalg.eigh(covariance)
        return {"eigenvalues": eigenvalues, "eigenvectors": eigenvectors}
    spectrum, spectrum_cache = immutable_tensor_cache(
        cache_dir, spectral_binding, decompose, torch=torch,
    )
    eigenvalues, eigenvectors = spectrum["eigenvalues"], spectrum["eigenvectors"]
    if (eigenvalues.shape != (token_count,) or eigenvectors.shape != (token_count, token_count)
            or eigenvalues.dtype != torch.float64 or eigenvectors.dtype != torch.float64):
        raise RuntimeError("cached spectrum has invalid shape or dtype")
    eigenvalues = torch.flip(eigenvalues, dims=(0,))
    eigenvectors = torch.flip(eigenvectors, dims=(1,))
    if not bool(torch.isfinite(eigenvalues).all()) or not bool(
        torch.isfinite(eigenvectors).all()
    ):
        raise RuntimeError("PCA eigendecomposition produced non-finite values")
    maximum = max(float(eigenvalues[0]), 0.0)
    negative_tolerance = (
        torch.finfo(torch.float64).eps
        * max(token_count, feature_count)
        * max(maximum, 1.0)
        * 32.0
    )
    if float(eigenvalues[-1]) < -negative_tolerance:
        raise RuntimeError("dual covariance has a materially negative eigenvalue")
    eigenvalues = torch.clamp(eigenvalues, min=0.0)
    rank_tolerance = (
        torch.finfo(torch.float64).eps
        * max(token_count, feature_count)
        * max(maximum, 1.0)
        * 32.0
    )
    effective_rank = int((eigenvalues > rank_tolerance).sum().item())
    if effective_rank <= 0:
        raise ValueError("retain activations have zero numerical covariance rank")
    positive = eigenvalues[:effective_rank]
    total_energy = float(positive.sum().item())
    if not math.isfinite(total_energy) or total_energy <= 0.0:
        raise RuntimeError("retain covariance has invalid total energy")

    if retained_energy == 0.0:
        selected_rank = 0
    elif retained_energy == 1.0:
        selected_rank = effective_rank
    else:
        cumulative = torch.cumsum(positive, dim=0) / total_energy
        selected_rank = int(
            torch.searchsorted(
                cumulative,
                torch.tensor(retained_energy, dtype=torch.float64),
                right=False,
            ).item()
        ) + 1
    if selected_rank < 0 or selected_rank > effective_rank:
        raise RuntimeError("PCA selected an impossible rank")
    if 0 < selected_rank < effective_rank:
        above = float(positive[selected_rank - 1])
        below = float(positive[selected_rank])
        if math.isclose(
            above,
            below,
            rel_tol=float(cutoff_tie_rtol),
            abs_tol=rank_tolerance,
        ):
            raise ValueError(
                "retained-energy cutoff is rank-ambiguous across an eigenvalue tie"
            )

    if selected_rank == 0:
        basis = torch.empty((feature_count, 0), dtype=torch.float64)
        orthogonality_error = 0.0
        retained_fraction = 0.0
        previous_fraction = 0.0
        reconstruction_fraction = 1.0
    else:
        left = eigenvectors[:, :selected_rank]
        scales = torch.sqrt(float(token_count) * positive[:selected_rank])
        basis = activations.T @ (left / scales.unsqueeze(0))
        # QR removes accumulated lift error without changing the selected span.
        basis, _ = torch.linalg.qr(basis, mode="reduced")
        basis = canonicalize_basis_signs(basis, torch)
        gram = basis.T @ basis
        orthogonality_error = float(
            torch.max(
                torch.abs(
                    gram
                    - torch.eye(selected_rank, dtype=torch.float64)
                )
            ).item()
        )
        if orthogonality_error > 1e-10:
            raise RuntimeError("retain basis failed float64 orthogonality check")
        retained_fraction = float(
            positive[:selected_rank].sum().item() / total_energy
        )
        previous_fraction = float(
            positive[: selected_rank - 1].sum().item() / total_energy
        )
        reconstruction = activations - (activations @ basis) @ basis.T
        reconstruction_fraction = float(
            torch.linalg.vector_norm(reconstruction).square().item()
            / torch.linalg.vector_norm(activations).square().item()
        )
        expected_discarded = max(0.0, 1.0 - retained_fraction)
        if not math.isclose(
            reconstruction_fraction,
            expected_discarded,
            rel_tol=1e-8,
            abs_tol=1e-10,
        ):
            raise RuntimeError("PCA reconstruction energy does not match spectrum")
    if 0.0 < retained_energy < 1.0 and not (
        previous_fraction < retained_energy <= retained_fraction + 1e-15
    ):
        raise RuntimeError("PCA rank is not the minimal retained-energy rank")
    diagnostics = {
        "activation_count": token_count,
        "input_features": feature_count,
        "covariance_definition": "X @ X.T / token_count (float64 dual second moment)",
        "dual_covariance_shape": list(covariance.shape),
        "dual_covariance_dtype": str(covariance.dtype),
        "dual_covariance_sha256": tensor_sha256(covariance, torch),
        "effective_rank": effective_rank,
        "positive_eigenvalues_sha256": tensor_sha256(positive, torch),
        "positive_eigenvalues_descending": positive.tolist(),
        "selected_rank": selected_rank,
        "requested_retained_energy": retained_energy,
        "achieved_retained_energy": retained_fraction,
        "previous_rank_retained_energy": previous_fraction,
        "discarded_activation_energy_fraction": reconstruction_fraction,
        "total_energy": total_energy,
        "cutoff_tie_rtol": float(cutoff_tie_rtol),
        "rank_tolerance": rank_tolerance,
        "basis_shape": list(basis.shape),
        "basis_dtype": str(basis.dtype),
        "basis_sha256": tensor_sha256(basis, torch),
        "basis_sign_rule": "largest-absolute entry; first tie; positive",
        "orthogonality_max_abs_error": orthogonality_error,
        "spectrum_cache": spectrum_cache,
    }
    return basis, diagnostics


def immutable_tensor_cache(cache_dir, binding, compute, *, torch):
    """Reuse exact tensor bytes only when full input binding and hashes match.

    An entry is published by a no-replace directory rename; incomplete writes
    cannot become hits. Invalid entries fail closed rather than recomputing.
    """
    if cache_dir is None:
        return compute(), {"enabled": False, "hit": False}
    root = Path(cache_dir).absolute()
    root.mkdir(parents=True, exist_ok=True)
    key = selection.payload_sha256(binding)
    entry = root / key
    if entry.exists():
        manifest, _ = _load_exact_json(entry / "manifest.json", "cache manifest")
        if manifest["binding"] != binding or manifest["binding_sha256"] != key:
            raise RuntimeError("cache input binding mismatch")
        artifact = entry / "payload.pt"
        if selection.sha256_file(artifact) != manifest["file_sha256"]:
            raise RuntimeError("cache payload file hash mismatch")
        payload = torch.load(artifact, map_location="cpu", weights_only=True)
        hit = True
    else:
        payload = compute()
        stage = Path(tempfile.mkdtemp(prefix=".cache-stage-", dir=root))
        try:
            artifact = stage / "payload.pt"
            torch.save(payload, artifact)
            manifest = {"binding": binding, "binding_sha256": key,
                "file_sha256": selection.sha256_file(artifact)}
            (stage / "manifest.json").write_bytes(selection.canonical_json_bytes(manifest))
            # os.rename rejects an existing nonempty entry on both supported OSes.
            os.rename(stage, entry)
        except Exception:
            # Preserve incomplete cache evidence for diagnosis; never reuse it.
            raise
        hit = False
    return payload, {"enabled": True, "hit": hit, "path": str(entry),
                     "binding_sha256": key, "file_sha256": manifest["file_sha256"]}


def validate_cached_retain_keys(keys, capture, groups, modules, *, expected_records, torch):
    declarations = {g["basis_group"]: g for g in groups}
    if set(keys) != set(declarations) or set(capture["basis_groups"]) != set(declarations):
        raise RuntimeError("cached retain key groups differ from declarations")
    if capture["retain_key_count"] != expected_records or capture["basis_group_count"] != len(groups):
        raise RuntimeError("cached retain capture counts differ")
    for group, declaration in declarations.items():
        values = keys[group]
        width = modules[declaration["representative_module"]].in_features
        proof = capture["basis_groups"][group]
        if (values.shape != (expected_records, width) or values.dtype != torch.float64
                or values.device.type != "cpu" or not bool(torch.isfinite(values).all())):
            raise RuntimeError(f"cached retain keys have invalid shape/dtype/values: {group}")
        error = float(torch.max(torch.abs(torch.linalg.vector_norm(values, dim=1) - 1.)).item())
        if error > 1e-12:
            raise RuntimeError(f"cached retain keys are not unit vectors: {group}")
        if (proof["record_key_count"] != expected_records or proof["input_features"] != width
                or proof["shared_input_equality_verified"] is not True
                or proof["modules"] != declaration["modules"]
                or proof["representative_module"] != declaration["representative_module"]
                or proof["shared_module_count"] != len(declaration["modules"])
                or proof["keys_sha256"] != tensor_sha256(values, torch)):
            raise RuntimeError(f"cached retain key proof differs: {group}")


def project_weight_delta(clean_weight, edited_weight, basis, *, torch):
    """Apply ``Delta - (Delta U)U.T`` in float32 without materializing I."""

    if clean_weight.ndim != 2 or edited_weight.ndim != 2:
        raise ValueError("clean and edited weights must be matrices")
    if tuple(clean_weight.shape) != tuple(edited_weight.shape):
        raise ValueError("clean and edited weight shapes differ")
    if clean_weight.dtype != edited_weight.dtype:
        raise ValueError("clean and edited weight dtypes differ")
    if basis.ndim != 2 or int(basis.shape[0]) != int(clean_weight.shape[1]):
        raise ValueError("retain basis does not match weight input dimension")
    if basis.dtype != torch.float64:
        raise ValueError("retain basis must be float64")
    if not bool(torch.isfinite(basis).all()):
        raise ValueError("retain basis contains non-finite values")
    if basis.shape[1] > 0:
        gram_error = float(
            torch.max(
                torch.abs(
                    basis.T @ basis
                    - torch.eye(basis.shape[1], dtype=torch.float64)
                )
            ).item()
        )
        if gram_error > 1e-10:
            raise ValueError("retain basis is not float64 orthonormal")
    clean_fp32 = clean_weight.detach().to(dtype=torch.float32)
    edited_fp32 = edited_weight.detach().to(
        device=clean_fp32.device, dtype=torch.float32
    )
    if not bool(torch.isfinite(clean_fp32).all()) or not bool(
        torch.isfinite(edited_fp32).all()
    ):
        raise ValueError("clean or edited weight contains non-finite values")
    delta = edited_fp32 - clean_fp32
    basis_fp32 = basis.to(device=delta.device, dtype=torch.float32)
    if basis_fp32.shape[1] == 0:
        removed = torch.zeros_like(delta)
        projected = delta.clone()
    else:
        removed = (delta @ basis_fp32) @ basis_fp32.T
        projected = delta - removed
    if not bool(torch.isfinite(projected).all()):
        raise RuntimeError("projected delta contains non-finite values")
    residual = projected @ basis_fp32
    raw_on_basis = delta @ basis_fp32
    delta_norm = float(torch.linalg.vector_norm(delta).item())
    residual_norm = float(torch.linalg.vector_norm(residual).item())
    removed_norm = float(torch.linalg.vector_norm(removed).item())
    projected_norm = float(torch.linalg.vector_norm(projected).item())
    relative_factor = 1e-5
    algebra_limit = max(torch.finfo(torch.float32).tiny, relative_factor * delta_norm)
    if residual_norm > algebra_limit:
        raise RuntimeError(
            "float32 projected delta failed retain-basis annihilation check"
        )
    source_residual_ratio = residual_norm / max(delta_norm, torch.finfo(torch.float32).tiny)
    if projected_norm == 0.0:
        if residual_norm != 0.0:
            raise RuntimeError("zero projected delta has nonzero retain residual")
        residual_ratio = 0.0
    else:
        residual_ratio = residual_norm / projected_norm
    if basis_fp32.shape[1] > 0 and not residual_ratio < 1e-5:
        raise RuntimeError("projected-delta retain residual ratio is not below 1e-5")
    raw_action_norm = float(torch.linalg.vector_norm(raw_on_basis).item())
    if raw_action_norm > algebra_limit and not residual_norm < raw_action_norm:
        raise RuntimeError("projection did not improve action on the retain basis")
    if projected_norm > delta_norm + algebra_limit:
        raise RuntimeError("orthogonal projection increased delta norm")
    pythagorean_error = abs(
        delta_norm * delta_norm
        - removed_norm * removed_norm
        - projected_norm * projected_norm
    )
    pythagorean_limit = max(1e-18, 5e-3 * delta_norm * delta_norm)
    if pythagorean_error > pythagorean_limit:
        raise RuntimeError("projected delta failed Pythagorean decomposition check")
    diagnostics = {
        "arithmetic": "float32 Delta - (Delta @ U_float32) @ U_float32.T",
        "raw_delta_shape": list(delta.shape),
        "raw_delta_dtype": str(delta.dtype),
        "raw_delta_sha256": tensor_sha256(delta, torch),
        "raw_delta_l2_norm": delta_norm,
        "raw_delta_on_basis_l2_norm": raw_action_norm,
        "removed_delta_sha256": tensor_sha256(removed, torch),
        "removed_delta_l2_norm": removed_norm,
        "projected_residual_delta_sha256": tensor_sha256(projected, torch),
        "projected_residual_delta_l2_norm": projected_norm,
        "projected_delta_on_basis_l2_norm": residual_norm,
        "projected_delta_on_basis_relative_to_delta": source_residual_ratio,
        "projected_delta_on_basis_relative_to_projected_delta": residual_ratio,
        "annihilation_tolerance": algebra_limit,
        "annihilation_relative_factor": relative_factor,
        "pythagorean_squared_norm_error": pythagorean_error,
        "pythagorean_tolerance": pythagorean_limit,
    }
    return projected, diagnostics


def declared_basis_groups(
    layers: Sequence[int], decoder_path: str = "model.language_model.layers"
) -> tuple[dict[str, str], list[dict]]:
    """Declare exactly four retain bases per layer and their proven sharing."""

    module_to_group = {}
    records = []
    for layer in layers:
        prefix = f"{decoder_path}.{layer}"
        definitions = (
            ("attention_qkv_input", ("self_attn.q_proj", "self_attn.k_proj", "self_attn.v_proj")),
            ("attention_output_input", ("self_attn.o_proj",)),
            ("mlp_gate_up_input", ("mlp.gate_proj", "mlp.up_proj")),
            ("mlp_down_input", ("mlp.down_proj",)),
        )
        for suffix, module_suffixes in definitions:
            group = f"layer_{layer}.{suffix}"
            modules = [f"{prefix}.{item}" for item in module_suffixes]
            for module in modules:
                if module in module_to_group:
                    raise RuntimeError(f"module assigned to multiple basis groups: {module}")
                module_to_group[module] = group
            records.append(
                {
                    "basis_group": group,
                    "layer": layer,
                    "representative_module": modules[0],
                    "modules": modules,
                    "shared_input_proof_required": len(modules) > 1,
                }
            )
    if set(module_to_group) != set(declared_module_names(layers, decoder_path)):
        raise RuntimeError("four-bases-per-layer declaration misses modules")
    return module_to_group, records


class ModuleRetainKeyCapture:
    """Capture one mean/L2-normalized key per record and basis group."""

    def __init__(
        self,
        modules: Mapping[str, Any],
        basis_groups: Sequence[Mapping],
        *,
        expected_records: int,
        torch,
    ):
        if not modules or expected_records <= 0:
            raise ValueError("retain key capture requires modules and records")
        self.torch = torch
        self.expected_records = expected_records
        self.groups = {record["basis_group"]: dict(record) for record in basis_groups}
        self.module_to_group = {
            module: group
            for group, record in self.groups.items()
            for module in record["modules"]
        }
        if set(self.module_to_group) != set(modules):
            raise ValueError("basis-group modules differ from hooked modules")
        self.input_features = {
            name: int(getattr(module, "in_features", -1))
            for name, module in modules.items()
        }
        for group, record in self.groups.items():
            widths = {self.input_features[name] for name in record["modules"]}
            if len(widths) != 1 or next(iter(widths)) <= 0:
                raise ValueError(f"basis group has inconsistent input widths: {group}")
        self.current_mask = None
        self.current_keys: dict[str, Any] = {}
        self.current_representative_inputs: dict[str, Any] = {}
        self.current_input_hashes: dict[str, str] = {}
        self.fired: set[str] = set()
        self.group_rows: dict[str, list[Any]] = {group: [] for group in self.groups}
        self.group_batch_input_hashes: dict[str, list[str]] = {
            group: [] for group in self.groups
        }
        self.handles = [
            module.register_forward_pre_hook(self._make_hook(name))
            for name, module in modules.items()
        ]

    def _make_hook(self, name: str):
        def hook(_module, inputs):
            if self.current_mask is None:
                raise RuntimeError(f"module hook fired outside a batch: {name}")
            if name in self.fired:
                raise RuntimeError(f"module hook fired more than once in a batch: {name}")
            if not isinstance(inputs, tuple) or not inputs:
                raise RuntimeError(f"module hook received no positional input: {name}")
            values = inputs[0]
            if not hasattr(values, "ndim") or values.ndim != 3:
                raise RuntimeError(f"module input is not [B,S,D]: {name}")
            if tuple(values.shape[:2]) != tuple(self.current_mask.shape):
                raise RuntimeError(f"module input axes differ from position mask: {name}")
            if int(values.shape[2]) != self.input_features[name]:
                raise RuntimeError(f"module input feature width differs: {name}")
            mask = self.current_mask.to(device=values.device)
            if any(int(row.sum().item()) <= 0 for row in mask):
                raise ValueError("a retain record has no selected positions")
            selected = values[mask].detach().clone()
            if not bool(self.torch.isfinite(selected.float()).all()):
                raise ValueError(f"module inputs contain non-finite values: {name}")
            group = self.module_to_group[name]
            representative = self.groups[group]["representative_module"]
            if name == representative:
                self.current_representative_inputs[group] = selected
                self.current_input_hashes[group] = tensor_sha256(selected, self.torch)
                rows = []
                for row_index in range(values.shape[0]):
                    row = (
                        values[row_index][mask[row_index]]
                        .detach()
                        .to(device="cpu", dtype=self.torch.float64)
                        .mean(dim=0)
                    )
                    norm = self.torch.linalg.vector_norm(row)
                    if not bool(self.torch.isfinite(norm)) or float(norm) <= 0.0:
                        raise ValueError(f"retain key has zero/nonfinite norm: {name}")
                    rows.append(row / norm)
                self.current_keys[group] = self.torch.stack(rows).contiguous()
            else:
                reference = self.current_representative_inputs.get(group)
                if reference is None:
                    raise RuntimeError(
                        f"shared-input representative hook did not fire first: {name}"
                    )
                if not self.torch.equal(selected, reference):
                    raise RuntimeError(
                        f"modules declared to share a retain basis received "
                        f"different selected inputs: {representative} vs {name}"
                    )
            self.fired.add(name)

        return hook

    def begin_batch(self, position_mask):
        if self.current_mask is not None:
            raise RuntimeError("previous retain-key batch is still active")
        if position_mask.ndim != 2 or position_mask.dtype != self.torch.bool:
            raise ValueError("retain position mask must be bool [B,S]")
        self.current_mask = position_mask
        self.fired.clear()
        self.current_keys.clear()
        self.current_representative_inputs.clear()
        self.current_input_hashes.clear()

    def abort_batch(self):
        self.current_mask = None
        self.fired.clear()
        self.current_keys.clear()
        self.current_representative_inputs.clear()
        self.current_input_hashes.clear()

    def end_batch(self):
        if self.current_mask is None:
            raise RuntimeError("no retain-key batch is active")
        missing = sorted(set(self.module_to_group) - self.fired)
        if missing:
            self.abort_batch()
            raise RuntimeError("module hooks did not fire: " + ", ".join(missing))
        for group in self.groups:
            keys = self.current_keys.get(group)
            if keys is None or keys.shape[0] != self.current_mask.shape[0]:
                self.abort_batch()
                raise RuntimeError(f"basis group produced invalid record keys: {group}")
            self.group_rows[group].append(keys)
            self.group_batch_input_hashes[group].append(
                self.current_input_hashes[group]
            )
        self.abort_batch()

    def finalize(self) -> tuple[dict[str, Any], dict]:
        if self.current_mask is not None:
            raise RuntimeError("cannot finalize during an active retain-key batch")
        matrices = {}
        proofs = {}
        for group, record in self.groups.items():
            if not self.group_rows[group]:
                raise ValueError(f"basis group has no retain keys: {group}")
            keys = self.torch.cat(self.group_rows[group], dim=0).contiguous()
            if keys.shape[0] != self.expected_records:
                raise RuntimeError(f"basis group retain key count differs: {group}")
            norms = self.torch.linalg.vector_norm(keys, dim=1)
            norm_error = float(self.torch.max(self.torch.abs(norms - 1.0)).item())
            if norm_error > 1e-12 or not bool(self.torch.isfinite(keys).all()):
                raise RuntimeError(f"basis group keys are not finite unit vectors: {group}")
            matrices[group] = keys
            proofs[group] = {
                "basis_group": group,
                "representative_module": record["representative_module"],
                "modules": record["modules"],
                "shared_input_equality_verified": True,
                "shared_module_count": len(record["modules"]),
                "record_key_count": int(keys.shape[0]),
                "input_features": int(keys.shape[1]),
                "keys_dtype": str(keys.dtype),
                "keys_sha256": tensor_sha256(keys, self.torch),
                "unit_norm_max_abs_error": norm_error,
                "per_batch_selected_input_sha256": self.group_batch_input_hashes[
                    group
                ],
                "per_batch_selected_input_hashes_sha256": selection.payload_sha256(
                    self.group_batch_input_hashes[group]
                ),
            }
        return matrices, proofs

    def close(self):
        errors = []
        for handle in self.handles:
            try:
                handle.remove()
            except Exception as error:  # pragma: no cover
                errors.append(error)
        self.handles.clear()
        if errors:
            raise RuntimeError("failed to remove one or more module hooks") from errors[0]


def _make_retain_key_batch(
    records: Sequence[Mapping], *, pad_token_id: int, torch, device
):
    if not records:
        raise ValueError("retain-key batch must be non-empty")
    width = max(len(record["input_ids"]) for record in records)
    ids_rows, attention_rows, mask_rows = [], [], []
    for record in records:
        ids = list(record["input_ids"])
        mask = list(record["position_mask"])
        if len(ids) != len(mask) or not any(mask):
            raise ValueError("retain record ids/position mask are invalid")
        padding = width - len(ids)
        ids_rows.append(ids + [pad_token_id] * padding)
        attention_rows.append([1] * len(ids) + [0] * padding)
        mask_rows.append(mask + [False] * padding)
    input_ids = torch.tensor(ids_rows, dtype=torch.long, device=device)
    attention = torch.tensor(attention_rows, dtype=torch.long, device=device)
    position_mask = torch.tensor(mask_rows, dtype=torch.bool, device=device)
    if bool((position_mask & (attention == 0)).any()):
        raise RuntimeError("retain key mask selected a padding position")
    return input_ids, attention, position_mask


def collect_clean_retain_keys(
    model,
    modules: Mapping[str, Any],
    basis_groups: Sequence[Mapping],
    tokenized: Sequence[Mapping],
    *,
    pad_token_id: int,
    batch_size: int,
    torch,
) -> tuple[dict[str, Any], dict]:
    """Collect exactly one normalized clean retain key per input record."""

    batch_size = _positive_integer(batch_size, "batch-size")
    if isinstance(pad_token_id, bool) or not isinstance(pad_token_id, int):
        raise ValueError("tokenizer pad_token_id must be an integer")
    if not tokenized:
        raise ValueError("retain records are empty")
    try:
        device = model.get_input_embeddings().weight.device
    except (AttributeError, TypeError) as error:
        raise ValueError("model has no usable input embedding device") from error
    if (
        type(model).__name__ == "Gemma3ForConditionalGeneration"
        and getattr(getattr(model, "config", None), "model_type", None) == "gemma3"
    ):
        forward_model = _resolve_attribute(model, "model.language_model")
        forward_surface = "model.language_model (text decoder; no lm_head logits)"
    else:
        forward_model = model
        forward_surface = "injected test model"
    collector = ModuleRetainKeyCapture(
        modules,
        basis_groups,
        expected_records=len(tokenized),
        torch=torch,
    )
    forward_batches = 0
    try:
        with torch.inference_mode():
            for start in range(0, len(tokenized), batch_size):
                batch = tokenized[start : start + batch_size]
                input_ids, attention, position_mask = _make_retain_key_batch(
                    batch,
                    pad_token_id=pad_token_id,
                    torch=torch,
                    device=device,
                )
                collector.begin_batch(position_mask)
                try:
                    output = forward_model(
                        input_ids=input_ids,
                        attention_mask=attention,
                        use_cache=False,
                        return_dict=True,
                    )
                    collector.end_batch()
                except Exception:
                    collector.abort_batch()
                    raise
                finally:
                    if "output" in locals():
                        del output
                forward_batches += 1
        keys, proofs = collector.finalize()
    finally:
        collector.close()
    return keys, {
        "forward_batches": forward_batches,
        "forward_surface": forward_surface,
        "retain_key_count": len(tokenized),
        "basis_group_count": len(keys),
        "basis_groups": proofs,
    }


def _resolve_attribute(root: Any, dotted: str):
    current = root
    for component in dotted.split("."):
        if component.isdigit():
            try:
                current = current[int(component)]
            except (IndexError, KeyError, TypeError) as error:
                raise ValueError(f"could not resolve model surface: {dotted}") from error
        else:
            if not hasattr(current, component):
                raise ValueError(f"could not resolve model surface: {dotted}")
            current = getattr(current, component)
    return current


def verify_gemma3_model_contract(model) -> dict:
    config = getattr(model, "config", None)
    if type(model).__name__ != "Gemma3ForConditionalGeneration":
        raise ValueError("model wrapper must be exactly Gemma3ForConditionalGeneration")
    if getattr(config, "model_type", None) != "gemma3":
        raise ValueError("model config.model_type must be exactly gemma3")
    decoder_layers, decoder_path = checkpoint_utils.attribution.resolve_decoder_layers(
        model
    )
    if decoder_path != "model.language_model.layers":
        raise ValueError("Gemma-3 decoder path differs from the frozen contract")
    if len(decoder_layers) <= 0:
        raise ValueError("Gemma-3 decoder has no layers")
    return {
        "wrapper_class": type(model).__name__,
        "model_type": getattr(config, "model_type", None),
        "decoder_path": decoder_path,
        "decoder_layer_count": len(decoder_layers),
    }


def resolve_declared_linear_modules(
    model, layers: Sequence[int], *, torch
) -> tuple[dict[str, Any], list[dict]]:
    contract = verify_gemma3_model_contract(model)
    if max(layers) >= contract["decoder_layer_count"]:
        raise ValueError("declared layer exceeds the Gemma-3 decoder")
    try:
        module_pairs = list(model.named_modules(remove_duplicate=False))
        parameter_pairs = list(model.named_parameters(remove_duplicate=False))
    except TypeError as error:
        raise ValueError(
            "installed PyTorch lacks alias-visible named module enumeration"
        ) from error
    if len({name for name, _ in module_pairs}) != len(module_pairs):
        raise ValueError("model exposes duplicate named_modules keys")
    if len({name for name, _ in parameter_pairs}) != len(parameter_pairs):
        raise ValueError("model exposes duplicate named_parameters keys")
    named_modules = dict(module_pairs)
    named_parameters = dict(parameter_pairs)
    modules = {}
    records = []
    for name in declared_module_names(layers, contract["decoder_path"]):
        module = named_modules.get(name)
        resolved = _resolve_attribute(model, name)
        if module is None or module is not resolved:
            raise ValueError(f"declared module is absent or ambiguous: {name}")
        module_aliases = [
            candidate_name
            for candidate_name, candidate in module_pairs
            if candidate is module
        ]
        if module_aliases != [name]:
            raise ValueError(f"declared module has runtime aliases: {name}")
        if not isinstance(module, torch.nn.Linear):
            raise ValueError(f"declared module is not torch.nn.Linear: {name}")
        if module.bias is not None:
            raise ValueError(f"declared Gemma-3 LoRA-surface linear has a bias: {name}")
        if module.weight.ndim != 2:
            raise ValueError(f"declared linear weight is not a matrix: {name}")
        if tuple(module.weight.shape) != (module.out_features, module.in_features):
            raise ValueError(f"declared linear metadata/weight shape differ: {name}")
        if module.weight.dtype != torch.bfloat16:
            raise ValueError(f"declared production weight is not bfloat16: {name}")
        weight_name = name + ".weight"
        weight_aliases = [
            candidate_name
            for candidate_name, candidate in parameter_pairs
            if candidate is module.weight
        ]
        if named_parameters.get(weight_name) is not module.weight or weight_aliases != [
            weight_name
        ]:
            raise ValueError(f"declared linear weight parameter is ambiguous: {name}")
        modules[name] = module
        records.append(
            {
                "module_name": name,
                "weight_name": weight_name,
                "layer": int(name.split(".")[3]),
                "linear_suffix": name.split(".", 4)[4],
                "weight_shape": list(module.weight.shape),
                "weight_dtype": str(module.weight.dtype),
                "in_features": int(module.in_features),
                "out_features": int(module.out_features),
                "bias": None,
            }
        )
    return modules, records


def _normalized_config_value(value: Any):
    ignored = {"_name_or_path", "transformers_version"}
    if isinstance(value, Mapping):
        return {
            key: _normalized_config_value(item)
            for key, item in sorted(value.items())
            if key not in ignored
        }
    if isinstance(value, (list, tuple)):
        return [_normalized_config_value(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def normalized_model_config(model) -> dict:
    config = getattr(model, "config", None)
    if config is None or not hasattr(config, "to_dict"):
        raise ValueError("model config cannot be serialized")
    raw = config.to_dict()
    if not isinstance(raw, Mapping):
        raise ValueError("model config.to_dict() did not return an object")
    normalized = _normalized_config_value(raw)
    return {
        "normalized": normalized,
        "normalized_sha256": selection.payload_sha256(normalized),
    }


def require_matching_model_configs(clean_model, edited_model) -> dict:
    clean = normalized_model_config(clean_model)
    edited = normalized_model_config(edited_model)
    if clean != edited:
        raise ValueError("clean and edited normalized model configs differ")
    return clean


def tokenizer_runtime_contract(tokenizer, model) -> dict:
    if getattr(tokenizer, "padding_side", None) != "right":
        tokenizer.padding_side = "right"
    chat_template = getattr(tokenizer, "chat_template", None)
    if not isinstance(chat_template, str) or not chat_template:
        raise ValueError("tokenizer has no exact chat template")
    identifiers = {}
    for name in ("bos_token_id", "eos_token_id", "pad_token_id"):
        value = getattr(tokenizer, name, None)
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ValueError(f"tokenizer {name} must be a non-negative integer")
        identifiers[name] = value
    try:
        vocabulary_size = len(tokenizer)
    except TypeError as error:
        raise ValueError("tokenizer has no finite vocabulary length") from error
    if vocabulary_size <= 0:
        raise ValueError("tokenizer vocabulary is empty")
    text_config = getattr(getattr(model, "config", None), "text_config", None)
    configured_vocabulary = getattr(text_config, "vocab_size", None)
    if configured_vocabulary is None:
        configured_vocabulary = getattr(getattr(model, "config", None), "vocab_size", None)
    if configured_vocabulary != vocabulary_size:
        raise ValueError("tokenizer vocabulary size differs from Gemma-3 config")
    for name, value in identifiers.items():
        configured = getattr(text_config, name, None)
        if configured is not None and configured != value:
            raise ValueError(f"tokenizer {name} differs from Gemma-3 text config")
    return {
        "class": type(tokenizer).__name__,
        "padding_side": tokenizer.padding_side,
        "vocab_size": vocabulary_size,
        **identifiers,
        "chat_template_sha256": selection.payload_sha256(chat_template),
    }


def validate_checkpoint_pair_inventories(
    clean_inventory: Mapping[str, Mapping],
    edited_inventory: Mapping[str, Mapping],
    selected_weight_names: Sequence[str],
) -> dict:
    """Require a shape/dtype-identical pair and an exact declared delta set."""

    if not clean_inventory or not edited_inventory:
        raise ValueError("checkpoint tensor inventories must be non-empty")
    clean_keys = set(clean_inventory)
    edited_keys = set(edited_inventory)
    if clean_keys != edited_keys:
        missing = sorted(clean_keys - edited_keys)
        extra = sorted(edited_keys - clean_keys)
        raise ValueError(
            f"clean/edited state keys differ; missing={missing[:3]} extra={extra[:3]}"
        )
    for name in sorted(clean_keys):
        clean_record = clean_inventory[name]
        edited_record = edited_inventory[name]
        if clean_record.get("shape") != edited_record.get("shape"):
            raise ValueError(f"clean/edited tensor shape mismatch: {name}")
        if clean_record.get("dtype") != edited_record.get("dtype"):
            raise ValueError(f"clean/edited tensor dtype mismatch: {name}")
    selected = list(selected_weight_names)
    if not selected or len(selected) != len(set(selected)):
        raise ValueError("selected weight names must be non-empty and unique")
    if not set(selected).issubset(clean_keys):
        unknown = sorted(set(selected) - clean_keys)
        raise ValueError("declared selected weights are absent: " + ", ".join(unknown[:3]))
    changed = {
        name
        for name in clean_keys
        if clean_inventory[name].get("sha256")
        != edited_inventory[name].get("sha256")
    }
    if changed != set(selected):
        missing_changes = sorted(set(selected) - changed)
        undeclared_changes = sorted(changed - set(selected))
        raise ValueError(
            "clean-to-edited nonzero delta surface differs from the declaration; "
            f"declared_unchanged={missing_changes[:5]} "
            f"undeclared_changed={undeclared_changes[:5]}"
        )
    return {
        "state_tensor_count": len(clean_keys),
        "changed_state_keys": sorted(changed),
        "changed_state_key_count": len(changed),
        "changed_state_keys_sha256": selection.payload_sha256(sorted(changed)),
        "every_declared_weight_nonzero": True,
        "every_undeclared_tensor_clean_identical": True,
    }


def verify_mutation_locality(
    clean_inventory: Mapping[str, Mapping],
    projected_inventory: Mapping[str, Mapping],
    selected_weight_names: Sequence[str],
    expected_selected_records: Mapping[str, Mapping],
) -> dict:
    if set(clean_inventory) != set(projected_inventory):
        raise RuntimeError("projected model state keys differ from clean")
    selected = set(selected_weight_names)
    actual_changed = {
        name
        for name in clean_inventory
        if clean_inventory[name] != projected_inventory[name]
    }
    unexpected = actual_changed - selected
    if unexpected:
        raise RuntimeError(
            "projection changed tensors outside the declared surface: "
            + ", ".join(sorted(unexpected)[:5])
        )
    for name in selected:
        expected = expected_selected_records.get(name)
        if not isinstance(expected, Mapping):
            raise RuntimeError(f"projection has no expected record for: {name}")
        if projected_inventory[name] != dict(expected):
            raise RuntimeError(f"projected tensor differs from precomputed value: {name}")
    if not actual_changed:
        raise RuntimeError("entire projected checkpoint rounded back to clean")
    return {
        "changed_state_keys": sorted(actual_changed),
        "changed_state_key_count": len(actual_changed),
        "changed_state_keys_sha256": selection.payload_sha256(
            sorted(actual_changed)
        ),
        "unchanged_selected_weights": sorted(selected - actual_changed),
        "all_unselected_tensors_exactly_clean": True,
        "whole_artifact_noop": False,
    }


def apply_projected_deltas(
    clean_modules: Mapping[str, Any],
    edited_modules: Mapping[str, Any],
    bases: Mapping[str, Any],
    basis_diagnostics: Mapping[str, Mapping],
    *,
    retained_energy: float,
    torch,
) -> tuple[list[dict], dict[str, dict]]:
    if set(clean_modules) != set(edited_modules) or set(clean_modules) != set(bases):
        raise ValueError("clean, edited, and retain-basis module sets differ")
    applications = []
    expected_records = {}
    with torch.no_grad():
        for name in sorted(clean_modules):
            clean_weight = clean_modules[name].weight
            edited_weight = edited_modules[name].weight
            basis = bases[name]
            before_hash = tensor_sha256(clean_weight, torch)
            edited_hash = tensor_sha256(edited_weight, torch)
            if before_hash == edited_hash:
                raise RuntimeError(f"declared edited module has zero delta: {name}")
            projected, projection = project_weight_delta(
                clean_weight, edited_weight, basis, torch=torch
            )
            clean_fp32 = clean_weight.detach().to(dtype=torch.float32).clone()
            if retained_energy == 0.0:
                if basis.shape[1] != 0:
                    raise RuntimeError("energy-zero application requires an empty basis")
                # BF16 values can span more than FP32 cancellation preserves.
                # Identity is defined by exact donor bytes, not c+(e-c).
                new_source_dtype = edited_weight.detach().clone()
            else:
                new_source_dtype = (clean_fp32 + projected).to(dtype=clean_weight.dtype)
            if not bool(torch.isfinite(new_source_dtype.float()).all()):
                raise RuntimeError(f"source-dtype projected weight is non-finite: {name}")
            clean_weight.copy_(new_source_dtype)
            after_hash = tensor_sha256(clean_weight, torch)
            realized_delta = clean_weight.detach().float() - clean_fp32
            basis_fp32 = basis.to(
                device=realized_delta.device, dtype=torch.float32
            )
            realized_action = realized_delta @ basis_fp32
            realized_action_norm = float(
                torch.linalg.vector_norm(realized_action).item()
            )
            realized_norm = float(torch.linalg.vector_norm(realized_delta).item())
            raw_norm = projection["raw_delta_l2_norm"]
            raw_action_norm = projection["raw_delta_on_basis_l2_norm"]
            projected_on_device = projected.to(device=realized_delta.device)
            quantization_error = realized_delta - projected_on_device
            quantization_error_norm = float(
                torch.linalg.vector_norm(quantization_error).item()
            )
            projected_action_norm = projection[
                "projected_delta_on_basis_l2_norm"
            ]
            rounding_epsilon = max(
                1e-12,
                8.0
                * torch.finfo(torch.float32).eps
                * math.sqrt(float(realized_delta.numel()))
                * max(raw_norm, 1e-30),
            )
            action_bound = (
                projected_action_norm + quantization_error_norm + rounding_epsilon
            )
            if realized_action_norm > action_bound:
                raise RuntimeError(
                    f"published retain action violates quantization-error bound: {name}"
                )
            if retained_energy == 0.0:
                protection_status = "rank_zero_identity"
            elif raw_action_norm > quantization_error_norm + rounding_epsilon:
                if not realized_action_norm < raw_action_norm:
                    raise RuntimeError(
                        f"published weight did not improve resolvable retain action: {name}"
                    )
                protection_status = "effective_action_improved"
            else:
                protection_status = "raw_action_below_bfloat16_resolution"
            if retained_energy == 0.0 and after_hash != edited_hash:
                raise RuntimeError(
                    f"rank-zero projection did not preserve edited weight exactly: {name}"
                )
            expected = _tensor_record(clean_weight, torch)
            weight_name = name + ".weight"
            expected_records[weight_name] = expected
            applications.append(
                {
                    "module_name": name,
                    "weight_name": weight_name,
                    "weight_shape": list(clean_weight.shape),
                    "source_dtype": str(clean_weight.dtype),
                    "clean_weight_sha256": before_hash,
                    "edited_weight_sha256": edited_hash,
                    "published_weight_sha256": after_hash,
                    "published_equals_clean": after_hash == before_hash,
                    "published_equals_edited": after_hash == edited_hash,
                    "activation_and_basis": dict(basis_diagnostics[name]),
                    "projection": projection,
                    "published_effective_delta": {
                        "dtype": str(realized_delta.dtype),
                        "sha256": tensor_sha256(realized_delta, torch),
                        "l2_norm": realized_norm,
                        "on_retain_basis_l2_norm": realized_action_norm,
                        "quantization_error_sha256": tensor_sha256(
                            quantization_error, torch
                        ),
                        "quantization_error_l2_norm": quantization_error_norm,
                        "retained_action_upper_bound": action_bound,
                        "rounding_epsilon": rounding_epsilon,
                        "protection_status": protection_status,
                    },
                }
            )
            del (
                projected,
                projected_on_device,
                clean_fp32,
                new_source_dtype,
                realized_delta,
                quantization_error,
            )
    return applications, expected_records


def verify_reloaded_model(
    reloaded,
    expected_inventory: Mapping[str, Mapping],
    expected_aliases: Mapping[str, Sequence[str]],
    *,
    torch,
) -> dict:
    inventory, inventory_hash, aliases = checkpoint_utils.model_tensor_inventory(
        reloaded, torch
    )
    if inventory != dict(expected_inventory):
        differing = sorted(
            name
            for name in set(inventory) | set(expected_inventory)
            if inventory.get(name) != expected_inventory.get(name)
        )
        raise RuntimeError(
            "freshly reloaded output inventory differs: " + ", ".join(differing[:5])
        )
    if aliases != dict(expected_aliases):
        raise RuntimeError("freshly reloaded output tensor alias groups differ")
    return {
        "verified": True,
        "state_tensor_count": len(inventory),
        "inventory_sha256": inventory_hash,
        "alias_groups": aliases,
    }


def _exact_local_directory(path: str | Path, label: str) -> Path:
    candidate = Path(path)
    if not candidate.is_dir():
        raise ValueError(f"{label} must be an exact existing local directory: {path}")
    return candidate.resolve(strict=True)


def _ensure_output_outside_sources(destination: Path, sources: Sequence[Path]):
    for source in sources:
        for outer, inner, message in (
            (source, destination, "output directory cannot be inside an input source"),
            (destination, source, "input source cannot be inside the output directory"),
        ):
            try:
                inner.resolve().relative_to(outer.resolve())
            except ValueError:
                continue
            raise ValueError(message)


def _git_provenance(repo_root: Path, paths: Sequence[Path]) -> dict:
    relative = [
        path.resolve().relative_to(repo_root.resolve()).as_posix() for path in paths
    ]

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

    head = run("rev-parse", "HEAD")
    status = run("status", "--porcelain=v1", "--", *relative)
    if head["returncode"] != 0 or not head["stdout"]:
        raise RuntimeError("implementation repository HEAD cannot be resolved")
    if status["returncode"] != 0:
        raise RuntimeError("implementation git status cannot be resolved")
    if status["stdout"]:
        raise RuntimeError(
            "implementation source is dirty or untracked: " + status["stdout"]
        )
    return {"head": head, "source_status": status}


def _implementation_binding() -> tuple[dict[str, Path], dict[str, str], dict]:
    script_path = Path(__file__).resolve()
    test_path = script_path.with_name(
        "test_project_checkpoint_delta_retain_subspace.py"
    )
    if not test_path.is_file():
        raise RuntimeError("projector unit-test source is absent")
    paths = {
        "projector": script_path,
        "unit_tests": test_path,
        "checkpoint_verifier": Path(checkpoint_utils.__file__).resolve(),
        "attribution_namespace_dependency": Path(
            checkpoint_utils.attribution.__file__
        ).resolve(),
        "canonical_json_helper": Path(selection.__file__).resolve(),
        "logical_safetensors_fingerprint": Path(
            logical_fingerprint.__file__
        ).resolve(),
        "frozen_endpoint_pins": Path(source_pins.__file__).resolve(),
    }
    hashes = {name: selection.sha256_file(path) for name, path in paths.items()}
    git = _git_provenance(script_path.parents[1], list(paths.values()))
    return paths, hashes, git


def _rehash_implementation(paths: Mapping[str, Path]) -> dict[str, str]:
    return {name: selection.sha256_file(path) for name, path in paths.items()}


def _verify_json_sources_unchanged(label: str, sources: Sequence[Mapping]):
    for source in sources:
        path = Path(source["path"])
        if not path.is_file() or selection.sha256_file(path) != source["file_sha256"]:
            raise RuntimeError(f"{label} input changed during run: {path}")


def _require_manifests_unchanged(
    clean_root: Path,
    edited_root: Path,
    tokenizer_root: Path,
    expected: Mapping[str, Mapping],
):
    actual = {
        "clean": checkpoint_utils.directory_manifest(clean_root),
        "edited": checkpoint_utils.directory_manifest(edited_root),
        "tokenizer": checkpoint_utils.attribution.require_local_artifact_manifest(
            str(tokenizer_root), label="tokenizer-model", tokenizer_only=True
        ),
    }
    if actual != dict(expected):
        changed = [name for name in actual if actual[name] != expected.get(name)]
        raise RuntimeError("source artifact changed during run: " + ", ".join(changed))


def _configure_determinism(torch, *, seed: int) -> dict:
    workspace = os.environ.setdefault("CUBLAS_WORKSPACE_CONFIG", ":4096:8")
    if workspace != ":4096:8":
        raise ValueError("CUBLAS_WORKSPACE_CONFIG must be :4096:8")
    for name in ("HF_HUB_OFFLINE", "TRANSFORMERS_OFFLINE"):
        value = os.environ.setdefault(name, "1")
        if value != "1":
            raise ValueError(f"{name} must be 1 for offline execution")
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)
    torch.use_deterministic_algorithms(True)
    if hasattr(torch.backends, "cuda") and hasattr(
        torch.backends.cuda, "matmul"
    ):
        torch.backends.cuda.matmul.allow_tf32 = False
    if hasattr(torch.backends, "cudnn"):
        torch.backends.cudnn.allow_tf32 = False
        torch.backends.cudnn.deterministic = True
        torch.backends.cudnn.benchmark = False
    return {
        "seed": seed,
        "torch_deterministic_algorithms": True,
        "CUBLAS_WORKSPACE_CONFIG": workspace,
        "HF_HUB_OFFLINE": os.environ["HF_HUB_OFFLINE"],
        "TRANSFORMERS_OFFLINE": os.environ["TRANSFORMERS_OFFLINE"],
        "cuda_tf32": False,
        "cudnn_tf32": False,
        "cudnn_benchmark": False,
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
    from transformers import AutoConfig, AutoTokenizer, Gemma3ForConditionalGeneration

    if not torch.cuda.is_available():
        raise RuntimeError("production retain projection requires a CUDA GPU")

    def load_model(source: str):
        config = AutoConfig.from_pretrained(source, local_files_only=True)
        if getattr(config, "model_type", None) != "gemma3":
            raise ValueError("checkpoint is not a Gemma-3 model")
        return Gemma3ForConditionalGeneration.from_pretrained(
            source,
            torch_dtype=torch.bfloat16,
            device_map="cuda",
            low_cpu_mem_usage=True,
            local_files_only=True,
        )

    return Runtime(
        torch=torch,
        safe_open=safe_open,
        load_model=load_model,
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


def _free_model(model, torch):
    if model is not None:
        try:
            model.to("cpu")
        except (AttributeError, RuntimeError):
            pass
        del model
    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()


def _load_immutable_sidecar(path: Path) -> dict:
    document, _ = _load_exact_json(path, "projection sidecar")
    if not selection.verify_immutable_envelope(document):
        raise ValueError("projection sidecar immutable payload hash is invalid")
    return document


def diagnose_checkpoint_inventory(
    model_source: str, *, runtime: Runtime | None = None
) -> dict:
    """Return a logical tensor digest that ignores harmless file reserialization."""

    root = _exact_local_directory(model_source, "model")
    checkpoint_utils.require_safetensors_checkpoint(root)
    if (root / SIDECAR_NAME).exists():
        # A projected output is still diagnosable, but the sidecar is excluded
        # from weight/value identity and reported separately by its file hash.
        sidecar_sha256 = selection.sha256_file(root / SIDECAR_NAME)
    else:
        sidecar_sha256 = None
    implementation_paths, implementation_hashes, implementation_git = (
        _implementation_binding()
    )
    manifest = checkpoint_utils.directory_manifest(root)
    runtime = runtime or production_runtime()
    determinism = _configure_determinism(runtime.torch, seed=0)
    canonical_logical = logical_fingerprint.fingerprint(
        root, safe_open=runtime.safe_open, torch=runtime.torch
    )
    canonical_logical_summary = {
        key: value for key, value in canonical_logical.items() if key != "records"
    }
    model = runtime.load_model(str(root))
    try:
        model.eval()
        model.requires_grad_(False)
        contract = verify_gemma3_model_contract(model)
        config = normalized_model_config(model)
        inventory, inventory_sha256, aliases = (
            checkpoint_utils.model_tensor_inventory(model, runtime.torch)
        )
        namespace = checkpoint_utils.namespace_mapping_contract_for_model(model)
        serialized = checkpoint_utils.verify_saved_model_tensors(
            root,
            inventory,
            aliases,
            namespace,
            safe_open=runtime.safe_open,
            torch=runtime.torch,
        )
        if checkpoint_utils.directory_manifest(root) != manifest:
            raise RuntimeError("checkpoint changed during digest")
        if _rehash_implementation(implementation_paths) != implementation_hashes:
            raise RuntimeError("implementation changed during digest")
        return {
            "schema_version": "logical_checkpoint_inventory_digest_v2",
            "model_path": str(root),
            "canonical_safetensors_logical": canonical_logical_summary,
            "canonical_safetensors_logical_sha256": canonical_logical[
                "logical_inventory_sha256"
            ],
            "loaded_state_tensor_count": len(inventory),
            "loaded_state_inventory_sha256": inventory_sha256,
            "serialized_mapped_inventory_sha256": serialized[
                "mapped_inventory_sha256"
            ],
            "serialized_inventory_sha256": serialized["inventory_sha256"],
            "canonical_to_state_mapping_sha256": serialized[
                "namespace_mapping"
            ]["mapping_sha256"],
            "canonical_to_state_mapping_count": serialized[
                "namespace_mapping"
            ]["mapping_pair_count"],
            "model_weight_file_sha256": checkpoint_utils.model_weight_hashes(root),
            "artifact_manifest_sha256": manifest["manifest_sha256"],
            "normalized_config_sha256": config["normalized_sha256"],
            "model_contract": contract,
            "alias_groups": aliases,
            "projection_sidecar_sha256": sidecar_sha256,
            "determinism": determinism,
            "runtime": dict(runtime.versions),
            "implementation": {
                name: {"path": str(path), "sha256": implementation_hashes[name]}
                for name, path in implementation_paths.items()
            }
            | {"git": implementation_git},
        }
    finally:
        _free_model(model, runtime.torch)


def project_checkpoint_delta_retain_subspace(
    *,
    clean_model: str,
    edited_model: str,
    tokenizer_model: str,
    expected_edited_logical_sha256: str,
    expected_edited_weight_sha256: str,
    retain_json: Sequence[str | Path],
    evaluation_json: Sequence[str | Path],
    expected_retain_records: int,
    layers: str,
    output_dir: str | Path,
    retained_energy: float,
    max_prompts: int = 4096,
    max_length: int = 256,
    batch_size: int = 4,
    cutoff_tie_rtol: float = 1e-10,
    cache_dir: str | Path | None = None,
    runtime: Runtime | None = None,
) -> dict:
    """Verify, project, reload, and atomically publish one checkpoint."""

    retained_energy = _finite_energy(retained_energy)
    expected_edited_logical_sha256 = _sha256_argument(
        expected_edited_logical_sha256,
        "expected-edited-logical-sha256",
    )
    expected_edited_weight_sha256 = _sha256_argument(
        expected_edited_weight_sha256,
        "expected-edited-weight-sha256",
    )
    max_prompts = _positive_integer(max_prompts, "max-prompts")
    expected_retain_records = _positive_integer(
        expected_retain_records, "expected-retain-records"
    )
    max_length = _positive_integer(max_length, "max-length")
    batch_size = _positive_integer(batch_size, "batch-size")
    parsed_layers = parse_layer_spec(layers)
    clean_root = _exact_local_directory(clean_model, "clean-model")
    edited_root = _exact_local_directory(edited_model, "edited-model")
    tokenizer_root = _exact_local_directory(tokenizer_model, "tokenizer-model")
    checkpoint_utils.require_safetensors_checkpoint(clean_root)
    checkpoint_utils.require_safetensors_checkpoint(edited_root)
    destination = Path(output_dir).absolute()
    if checkpoint_utils._path_lexists(destination):
        raise FileExistsError(f"refusing to replace existing output: {destination}")
    _ensure_output_outside_sources(
        destination, (clean_root, edited_root, tokenizer_root)
    )
    if cache_dir is not None:
        _ensure_output_outside_sources(Path(cache_dir).absolute(),
            (clean_root, edited_root, tokenizer_root, destination))
        _ensure_output_outside_sources(destination, (Path(cache_dir).absolute(),))

    implementation_paths, implementation_hashes, implementation_git = (
        _implementation_binding()
    )
    retain_records, retain_sources = load_retain_training_data(
        retain_json,
        max_prompts=max_prompts,
        expected_records=expected_retain_records,
    )
    evaluation_sources, overlap_proof = prove_zero_evaluation_overlap(
        retain_records, evaluation_json
    )
    source_manifests = {
        "clean": checkpoint_utils.directory_manifest(clean_root),
        "edited": checkpoint_utils.directory_manifest(edited_root),
        "tokenizer": checkpoint_utils.attribution.require_local_artifact_manifest(
            str(tokenizer_root), label="tokenizer-model", tokenizer_only=True
        ),
    }
    edited_weight_hashes_initial = checkpoint_utils.model_weight_hashes(edited_root)
    if (
        len(edited_weight_hashes_initial) != 1
        or next(iter(edited_weight_hashes_initial.values()))
        != expected_edited_weight_sha256
    ):
        raise ValueError(
            "edited Safetensors file does not match the explicitly qualified "
            "donor weight digest"
        )
    runtime = runtime or production_runtime()
    torch = runtime.torch
    determinism = _configure_determinism(torch, seed=0)
    edited_logical = logical_fingerprint.fingerprint(
        edited_root, safe_open=runtime.safe_open, torch=torch
    )
    edited_logical_summary = {
        key: value for key, value in edited_logical.items() if key != "records"
    }
    if (
        edited_logical["logical_inventory_sha256"]
        != expected_edited_logical_sha256
    ):
        raise ValueError(
            "edited canonical Safetensors tensor-value digest does not match "
            "the explicitly qualified donor"
        )

    tokenizer = runtime.load_tokenizer(str(tokenizer_root))
    clean = runtime.load_model(str(clean_root))
    edited = None
    reloaded = None
    published = False
    stage = None
    try:
        clean.eval()
        clean.requires_grad_(False)
        clean_contract = verify_gemma3_model_contract(clean)
        clean_config = normalized_model_config(clean)
        tokenizer_contract = tokenizer_runtime_contract(tokenizer, clean)
        tokenized, tokenization = tokenize_retain_records(
            retain_records, tokenizer, max_length=max_length
        )
        clean_modules, clean_module_records = resolve_declared_linear_modules(
            clean, parsed_layers, torch=torch
        )
        if len(clean_modules) != len(parsed_layers) * len(LINEAR_SUFFIXES):
            raise RuntimeError("declared module count is not layers times seven")
        module_to_basis_group, basis_group_declarations = declared_basis_groups(
            parsed_layers, clean_contract["decoder_path"]
        )
        cache_binding = {
            "kind": "normalized_retain_keys_v1",
            "implementation_hashes": implementation_hashes,
            "clean_manifest": source_manifests["clean"],
            "tokenizer_manifest": source_manifests["tokenizer"],
            "tokenizer_contract": tokenizer_contract,
            "retain_sources": retain_sources, "tokenization": tokenization,
            "basis_groups": basis_group_declarations, "batch_size": batch_size,
            "runtime_versions": dict(runtime.versions), "determinism": determinism,
            "cuda_device": torch.cuda.get_device_name() if torch.cuda.is_available() else "cpu",
        }
        def capture_keys():
            keys, proof = collect_clean_retain_keys(
                clean, clean_modules, basis_group_declarations, tokenized,
                pad_token_id=tokenizer_contract["pad_token_id"],
                batch_size=batch_size, torch=torch,
            )
            return {"keys": keys, "capture": proof}
        cached, key_cache = immutable_tensor_cache(cache_dir, cache_binding, capture_keys, torch=torch)
        retain_keys, capture = cached["keys"], cached["capture"]
        del cached
        validate_cached_retain_keys(retain_keys, capture, basis_group_declarations,
            clean_modules, expected_records=expected_retain_records, torch=torch)
        group_bases = {}
        group_basis_records = {}
        for group in sorted(retain_keys):
            values = retain_keys[group]
            basis, diagnostics = compute_retain_basis(
                values,
                retained_energy=retained_energy,
                cutoff_tie_rtol=cutoff_tie_rtol,
                torch=torch,
                cache_dir=cache_dir,
                cache_binding={"keys_binding_sha256": selection.payload_sha256(cache_binding), "group": group},
            )
            key_record = capture["basis_groups"][group]
            if key_record["keys_sha256"] != tensor_sha256(values, torch):
                raise RuntimeError(f"retain key bytes changed before PCA: {group}")
            group_bases[group] = basis
            group_basis_records[group] = {
                **diagnostics,
                **key_record,
            }
        bases = {
            module: group_bases[group]
            for module, group in module_to_basis_group.items()
        }
        basis_records = {
            module: {
                **group_basis_records[group],
                "basis_group": group,
            }
            for module, group in module_to_basis_group.items()
        }
        del retain_keys

        clean_inventory, clean_inventory_hash, clean_aliases = (
            checkpoint_utils.model_tensor_inventory(clean, torch)
        )
        clean_namespace = checkpoint_utils.namespace_mapping_contract_for_model(
            clean
        )
        clean_serialized = checkpoint_utils.verify_saved_model_tensors(
            clean_root,
            clean_inventory,
            clean_aliases,
            clean_namespace,
            safe_open=runtime.safe_open,
            torch=torch,
        )

        edited = runtime.load_model(str(edited_root))
        edited.eval()
        edited.requires_grad_(False)
        edited_contract = verify_gemma3_model_contract(edited)
        if edited_contract != clean_contract:
            raise ValueError("clean and edited Gemma-3 model contracts differ")
        require_matching_model_configs(clean, edited)
        if tokenizer_runtime_contract(tokenizer, edited) != tokenizer_contract:
            raise ValueError("tokenizer runtime differs across model checkpoints")
        edited_modules, edited_module_records = resolve_declared_linear_modules(
            edited, parsed_layers, torch=torch
        )
        if edited_module_records != clean_module_records:
            raise ValueError("clean and edited declared linear metadata differ")
        edited_inventory, edited_inventory_hash, edited_aliases = (
            checkpoint_utils.model_tensor_inventory(edited, torch)
        )
        if edited_aliases != clean_aliases:
            raise ValueError("clean and edited state alias groups differ")
        edited_namespace = checkpoint_utils.namespace_mapping_contract_for_model(
            edited
        )
        if edited_namespace != clean_namespace:
            raise ValueError("clean and edited namespace contracts differ")
        edited_serialized = checkpoint_utils.verify_saved_model_tensors(
            edited_root,
            edited_inventory,
            edited_aliases,
            edited_namespace,
            safe_open=runtime.safe_open,
            torch=torch,
        )
        selected_weight_names = [
            record["weight_name"] for record in clean_module_records
        ]
        pair_delta = validate_checkpoint_pair_inventories(
            clean_inventory, edited_inventory, selected_weight_names
        )

        applications, expected_selected = apply_projected_deltas(
            clean_modules,
            edited_modules,
            bases,
            basis_records,
            retained_energy=retained_energy,
            torch=torch,
        )
        projected_inventory, projected_inventory_hash, projected_aliases = (
            checkpoint_utils.model_tensor_inventory(clean, torch)
        )
        if projected_aliases != clean_aliases:
            raise RuntimeError("projection changed state tensor alias groups")
        locality = verify_mutation_locality(
            clean_inventory,
            projected_inventory,
            selected_weight_names,
            expected_selected,
        )
        if retained_energy == 0.0 and projected_inventory != edited_inventory:
            raise RuntimeError("energy-zero output is not exact edited-checkpoint identity")
        _require_manifests_unchanged(
            clean_root,
            edited_root,
            tokenizer_root,
            source_manifests,
        )
        _verify_json_sources_unchanged("retain training", retain_sources)
        _verify_json_sources_unchanged("held-out evaluation", evaluation_sources)
        if _rehash_implementation(implementation_paths) != implementation_hashes:
            raise RuntimeError("implementation source changed during projection")

        destination.parent.mkdir(parents=True, exist_ok=True)
        stage_prefix = f".{destination.name}.tmp-"
        stage = Path(tempfile.mkdtemp(prefix=stage_prefix, dir=destination.parent))
        if retained_energy == 0.0:
            if (edited_root / SIDECAR_NAME).exists():
                raise FileExistsError(
                    f"qualified donor contains reserved sidecar: {SIDECAR_NAME}"
                )
            checkpoint_utils._copy_manifest_files(
                edited_root, source_manifests["edited"], stage
            )
        else:
            clean.save_pretrained(stage, safe_serialization=True)
            tokenizer.save_pretrained(stage)
        if (stage / SIDECAR_NAME).exists():
            raise FileExistsError(
                f"checkpoint save unexpectedly produced reserved sidecar: {SIDECAR_NAME}"
            )
        output_serialized = checkpoint_utils.verify_saved_model_tensors(
            stage,
            projected_inventory,
            clean_aliases,
            clean_namespace,
            safe_open=runtime.safe_open,
            torch=torch,
        )
        source_output_namespace = (
            checkpoint_utils.verify_source_output_namespace_equivalence(
                clean_serialized, output_serialized
            )
        )
        output_manifest = checkpoint_utils.directory_manifest(
            stage, excluded_names={SIDECAR_NAME}
        )
        output_weight_hashes = checkpoint_utils.model_weight_hashes(stage)
        if retained_energy == 0.0:
            edited_weight_hashes = checkpoint_utils.model_weight_hashes(edited_root)
            if output_weight_hashes != edited_weight_hashes:
                raise RuntimeError(
                    "energy-zero output did not preserve qualified donor weight bytes"
                )
            if output_manifest != source_manifests["edited"]:
                raise RuntimeError(
                    "energy-zero staged artifact is not a byte-exact donor copy"
                )
        final_inventory, final_inventory_hash, final_aliases = (
            checkpoint_utils.model_tensor_inventory(clean, torch)
        )
        if (
            final_inventory != projected_inventory
            or final_inventory_hash != projected_inventory_hash
            or final_aliases != projected_aliases
        ):
            raise RuntimeError("save_pretrained mutated projected model tensors")

        # Free both large source models before the independent output reload.
        del edited_modules, clean_modules, bases, group_bases
        _free_model(edited, torch)
        edited = None
        _free_model(clean, torch)
        clean = None
        reloaded = runtime.load_model(str(stage))
        reloaded.eval()
        reloaded.requires_grad_(False)
        if verify_gemma3_model_contract(reloaded) != clean_contract:
            raise RuntimeError("reloaded output Gemma-3 contract differs")
        if normalized_model_config(reloaded) != clean_config:
            raise RuntimeError("reloaded output normalized config differs")
        reload_verification = verify_reloaded_model(
            reloaded,
            projected_inventory,
            projected_aliases,
            torch=torch,
        )
        output_tokenizer = runtime.load_tokenizer(str(stage))
        if tokenizer_runtime_contract(output_tokenizer, reloaded) != tokenizer_contract:
            raise RuntimeError("reloaded output tokenizer runtime differs")
        del output_tokenizer
        _free_model(reloaded, torch)
        reloaded = None

        _require_manifests_unchanged(
            clean_root,
            edited_root,
            tokenizer_root,
            source_manifests,
        )
        _verify_json_sources_unchanged("retain training", retain_sources)
        _verify_json_sources_unchanged("held-out evaluation", evaluation_sources)
        if _rehash_implementation(implementation_paths) != implementation_hashes:
            raise RuntimeError("implementation source changed before publication")
        implementation_git_final = _git_provenance(
            Path(__file__).resolve().parents[1], list(implementation_paths.values())
        )
        if implementation_git_final != implementation_git:
            raise RuntimeError("implementation git binding changed during projection")

        payload = {
            "schema_version": SCHEMA_VERSION,
            "created_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
            "operation": "right_project_exact_checkpoint_delta_off_clean_retain_PCA",
            "claim_boundary": (
                "Each float32 selected matrix delta has zero first-order action "
                "on its sampled clean retain basis up to recorded tolerance. This "
                "does not prove end-to-end behavioral retention, because earlier "
                "projected layers change later inputs and discarded PCA directions "
                "are unprotected. Behavioral screens remain mandatory."
            ),
            "mathematical_contract": {
                "linear_weight_axes": "W[out_features,input_features]",
                "raw_delta": "float32(W_edited)-float32(W_clean)",
                "retain_basis": (
                    "U[input_features,rank] from float64 uncentered clean "
                    "module-input dual covariance"
                ),
                "projection": "Delta_projected=Delta-(Delta@U_float32)@U_float32.T",
                "publication": (
                    "cast(float32(W_clean)+Delta_projected, source bfloat16 dtype)"
                ),
                "all_unselected_tensors": "exact clean logical state bytes",
                "energy_zero": "rank-zero exact edited-checkpoint identity",
            },
            "request": {
                "layers_argument": layers,
                "layers": parsed_layers,
                "module_count": len(clean_module_records),
                "retained_energy": retained_energy,
                "expected_retain_records": expected_retain_records,
                "max_prompts": max_prompts,
                "max_length": max_length,
                "batch_size": batch_size,
                "cutoff_tie_rtol": cutoff_tie_rtol,
                "output_dir": str(destination),
            },
            "source": {
                "clean_model": {
                    "path": str(clean_root),
                    "artifact_manifest": source_manifests["clean"],
                    "serialized_tensor_verification": clean_serialized,
                    "inventory_sha256": clean_inventory_hash,
                },
                "edited_model": {
                    "path": str(edited_root),
                    "artifact_manifest": source_manifests["edited"],
                    "serialized_tensor_verification": edited_serialized,
                    "inventory_sha256": edited_inventory_hash,
                    "canonical_safetensors_logical": edited_logical_summary,
                    "expected_canonical_safetensors_logical_sha256": (
                        expected_edited_logical_sha256
                    ),
                    "expected_weight_file_sha256": expected_edited_weight_sha256,
                    "weight_file_sha256": edited_weight_hashes_initial,
                    "qualified_donor_digest_matched": True,
                },
                "tokenizer": {
                    "path": str(tokenizer_root),
                    "artifact_manifest": source_manifests["tokenizer"],
                    "runtime": tokenizer_contract,
                },
                "retain_training_data": {
                    "schema_version": RETAIN_DATA_SCHEMA_VERSION,
                    "files": retain_sources,
                    "combined_file_records_sha256": selection.payload_sha256(
                        retain_sources
                    ),
                    "record_count": len(retain_records),
                    "training_only_enforced": True,
                    "duplicate_records_retained": True,
                    "evaluation_exclusions": {
                        "files": evaluation_sources,
                        "overlap_proof": overlap_proof,
                    },
                },
            },
            "model_contract": {
                **clean_contract,
                "normalized_config_sha256": clean_config["normalized_sha256"],
                "declared_modules": clean_module_records,
                "declared_basis_groups": basis_group_declarations,
                "basis_group_count": len(basis_group_declarations),
                "pair_delta_surface": pair_delta,
            },
            "activation_collection": {
                "key_cache": key_cache,
                **tokenization,
                "forward_batches": capture["forward_batches"],
                "forward_surface": capture["forward_surface"],
                "basis_groups": capture["basis_groups"],
                "padding_policy": "right; padding positions never selected",
                "chat_policy": (
                    "native history or one user message; add_generation_prompt=True"
                ),
                "key_policy": (
                    "mean selected positions within each record, then L2 normalize; "
                    "one key per record; duplicates retained"
                ),
                "truncation_policy": "right truncate to max_length; fail if no shifted positions survive",
                "generic_policy": "direct tokenization with tokenizer defaults; no chat template",
                "answer_policy": "template prompt then answer without special tokens; no appended EOS",
            },
            "module_projections": applications,
            "model_tensors": {
                "clean_before": {
                    "inventory": clean_inventory,
                    "inventory_sha256": clean_inventory_hash,
                },
                "edited": {
                    "inventory": edited_inventory,
                    "inventory_sha256": edited_inventory_hash,
                },
                "projected_after": {
                    "inventory": projected_inventory,
                    "inventory_sha256": projected_inventory_hash,
                },
                "locality": locality,
                "namespace_contract": clean_namespace,
                "source_output_namespace_mapping": source_output_namespace,
            },
            "output": {
                "artifact_manifest": output_manifest,
                "weight_file_sha256": output_weight_hashes,
                "energy_zero_byte_exact_qualified_donor": retained_energy == 0.0,
                "serialized_tensor_verification": output_serialized,
                "fresh_reload_verification": reload_verification,
                "standalone_model_and_tokenizer": True,
                "serialization_contract": "Safetensors_only",
            },
            "determinism": determinism,
            "runtime": dict(runtime.versions),
            "implementation": {
                name: {"path": str(path), "sha256": implementation_hashes[name]}
                for name, path in implementation_paths.items()
            }
            | {"git": implementation_git},
        }
        provenance = selection.immutable_envelope(payload)
        selection.write_immutable_json(stage / SIDECAR_NAME, provenance)
        if _load_immutable_sidecar(stage / SIDECAR_NAME) != provenance:
            raise RuntimeError("immutable projection sidecar did not round-trip")
        _require_manifests_unchanged(
            clean_root,
            edited_root,
            tokenizer_root,
            source_manifests,
        )
        _verify_json_sources_unchanged("retain training", retain_sources)
        _verify_json_sources_unchanged("held-out evaluation", evaluation_sources)
        if _rehash_implementation(implementation_paths) != implementation_hashes:
            raise RuntimeError("implementation source changed at publication")
        checkpoint_utils._fsync_files(stage)
        checkpoint_utils._fsync_directory(stage)
        checkpoint_utils._publish_directory_no_replace(stage, destination)
        checkpoint_utils._fsync_directory(destination.parent)
        published = True
        return provenance
    finally:
        if reloaded is not None:
            _free_model(reloaded, torch)
        if edited is not None:
            _free_model(edited, torch)
        if "clean" in locals() and clean is not None:
            _free_model(clean, torch)
        if stage is not None and not published:
            checkpoint_utils._remove_private_stage(
                stage, destination.parent, f".{destination.name}.tmp-"
            )


def validate_production_request(args):
    """The CLI cannot silently change the frozen sprint endpoints or grid."""
    if parse_layer_spec(args.layers) != list(source_pins.EDIT_LAYERS):
        raise ValueError("production layers differ from the frozen 98-tensor surface")
    if args.retained_energy not in (0., .90, .95, .99):
        raise ValueError("production retained energy is outside the frozen grid")
    if args.max_length != 256 or args.expected_retain_records != 2052:
        raise ValueError("production retain contract requires max_length=256 and 2052 records")
    clean = _exact_local_directory(args.clean_model, "clean-model")
    edited = _exact_local_directory(args.edited_model, "edited-model")
    if _exact_local_directory(args.tokenizer_model, "tokenizer-model") != clean:
        raise ValueError("production tokenizer must be the exact clean checkpoint directory")
    if checkpoint_utils.model_weight_hashes(clean) != source_pins.PINNED_CLEAN_WEIGHT_HASHES:
        raise ValueError("production clean checkpoint shard hashes differ from qualified pins")
    if selection.sha256_file(edited / "config.json") != source_pins.PINNED_EDITED_CONFIG_SHA256:
        raise ValueError("production donor config differs from qualified pin")
    if (args.expected_edited_weight_sha256 != source_pins.PINNED_EDITED_WEIGHT_HASHES["model.safetensors"]
            or args.expected_edited_logical_sha256 != source_pins.PINNED_EDITED_LOGICAL_INVENTORY_SHA256):
        raise ValueError("production donor digest arguments differ from qualified pins")
    retain_hashes = [selection.sha256_file(Path(path)) for path in args.retain_json]
    if sorted(retain_hashes) != sorted([
        "330ed2b8fe24f4e99f431e0b0c776457c034436e863582840b43c36e6585cd5e",
        "51fef432b073feb577c0be6a764d0fc2e303c55b0fdddd4bebc77401b0d6065a",
    ]):
        raise ValueError("production retain files differ from frozen source hashes")


def main(argv: Iterable[str] | None = None):
    args = parse_args(argv)
    if args.command == "digest":
        diagnostic = diagnose_checkpoint_inventory(args.model)
        print(
            selection.canonical_json_bytes(diagnostic).decode("utf-8"),
            flush=True,
        )
        return
    validate_production_request(args)
    provenance = project_checkpoint_delta_retain_subspace(
        clean_model=args.clean_model,
        edited_model=args.edited_model,
        tokenizer_model=args.tokenizer_model,
        expected_edited_logical_sha256=args.expected_edited_logical_sha256,
        expected_edited_weight_sha256=args.expected_edited_weight_sha256,
        retain_json=args.retain_json,
        evaluation_json=args.evaluation_json,
        expected_retain_records=args.expected_retain_records,
        layers=args.layers,
        output_dir=args.output_dir,
        retained_energy=args.retained_energy,
        max_prompts=args.max_prompts,
        max_length=args.max_length,
        batch_size=args.batch_size,
        cutoff_tie_rtol=args.cutoff_tie_rtol,
        cache_dir=args.cache_dir,
    )
    print(
        f"Published retain-subspace projected checkpoint at {args.output_dir}\n"
        f"layers={args.layers}\n"
        f"retained_energy={args.retained_energy}\n"
        f"provenance_payload_sha256={provenance['payload_sha256']}",
        flush=True,
    )


if __name__ == "__main__":
    main()
