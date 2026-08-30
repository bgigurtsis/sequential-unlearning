"""Attribute and select a sparse, concept-specific Gemma MLP-neuron mask.

This is a read-only measurement stage.  It freezes every model parameter,
scores how strongly each configured MLP intermediate neuron causally supports
teacher-forced target and control continuations, and writes an immutable JSON
selection artifact.  It never constructs an optimizer, changes a weight, or
saves a model.

Attribution is ``-activation * d(NLL)/dactivation`` summed across every causal
prompt/answer position and normalized by the number of scored answer tokens.
Positive values therefore mean that the observed activation supports the
scored continuation.  Ranking uses the equal-group mean of positive signed
target support divided by the worst per-control-group absolute support.  A
separate sign-consistency gate requires that support to recur across target
semantic groups.
"""

from __future__ import annotations

import argparse
import datetime as dt
import gc
import hashlib
import json
import os
import subprocess
from pathlib import Path
from typing import Iterable, Mapping

try:
    import causal_mlp_neuron_selection as selection
except ModuleNotFoundError:
    from scripts import causal_mlp_neuron_selection as selection


METHOD = "teacher_forced_answer_nll_negative_activation_times_gradient_v1"
MODEL_FILE_SUFFIXES = (".safetensors", ".bin")
MODEL_METADATA_NAMES = {
    "config.json",
    "generation_config.json",
    "model.safetensors.index.json",
    "pytorch_model.bin.index.json",
}
TOKENIZER_NAMES = {
    "added_tokens.json",
    "chat_template.json",
    "special_tokens_map.json",
    "tokenizer.json",
    "tokenizer.model",
    "tokenizer_config.json",
}


def parse_args():
    parser = argparse.ArgumentParser(
        description=(
            "Measure target/control causal attribution at Gemma MLP neurons "
            "and emit a deterministic sparse mask; model weights are read-only."
        )
    )
    parser.add_argument("--model-id", required=True)
    parser.add_argument("--tokenizer-model", required=True)
    parser.add_argument("--target-data", nargs="+", required=True)
    parser.add_argument("--control-data", nargs="+", required=True)
    parser.add_argument("--layers", required=True, help="e.g. 18-33 or 18,22,28")
    parser.add_argument("--output", required=True)
    parser.add_argument(
        "--attribution-output",
        help=(
            "immutable raw Safetensors path; defaults to "
            "<output stem>.attributions.safetensors"
        ),
    )
    parser.add_argument("--batch-size", type=int, default=1)
    parser.add_argument("--max-length", type=int, default=256)
    parser.add_argument("--target-control-ratio", type=float, default=10.0)
    parser.add_argument("--min-sign-consistent-groups", type=int, default=4)
    parser.add_argument("--top-k", type=int, default=128)
    parser.add_argument("--per-layer-cap", type=int, default=32)
    parser.add_argument(
        "--min-target-score",
        type=float,
        default=1e-6,
        help=(
            "minimum equal-group mean target NLL support per scored answer "
            "token; calibrate against a null/control attribution distribution"
        ),
    )
    parser.add_argument("--ratio-epsilon", type=float, default=1e-12)
    parser.add_argument("--sign-epsilon", type=float, default=1e-12)
    parser.add_argument("--seed", type=int, default=33350)
    parser.add_argument(
        "--attribution-positions",
        choices=("answer", "all-causal"),
        default="all-causal",
        help=(
            "aggregate causal support at every non-padding position that "
            "predicts a token (the intervention-aligned default), or only at "
            "answer-predicting positions for diagnostics"
        ),
    )
    parser.add_argument(
        "--append-eos",
        action="store_true",
        help="include EOS as a scored answer token when it is not already present",
    )
    return parser.parse_args()


def _validated_messages(record: Mapping, label: str) -> list[dict]:
    if "messages" not in record:
        prompt = record.get("prompt")
        if not isinstance(prompt, str) or not prompt.strip():
            raise ValueError(f"{label} needs a non-empty prompt or messages")
        return [{"role": "user", "content": prompt}]
    messages = record.get("messages")
    if not isinstance(messages, list) or not messages:
        raise ValueError(f"{label}.messages must be a non-empty list")
    validated = []
    for index, message in enumerate(messages):
        if not isinstance(message, Mapping):
            raise ValueError(f"{label}.messages[{index}] must be an object")
        role = message.get("role")
        content = message.get("content")
        if role not in {"system", "user", "assistant"}:
            raise ValueError(f"{label}.messages[{index}] has an invalid role")
        if not isinstance(content, str) or not content.strip():
            raise ValueError(f"{label}.messages[{index}] has empty content")
        validated.append({"role": role, "content": content})
    if validated[-1]["role"] != "user":
        raise ValueError(f"{label}.messages must end in a user turn")
    return validated


def load_pair_files(paths: Iterable[str | Path], *, require_category: bool) -> tuple[list[dict], list[dict]]:
    """Load validated prompt/answer pairs and exact input-file metadata."""

    records: list[dict] = []
    sources: list[dict] = []
    seen: set[str] = set()
    for raw_path in paths:
        path = Path(raw_path)
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, list) or not payload:
            raise ValueError(f"{path} must contain a non-empty JSON array")
        sources.append(
            {
                "path": str(path),
                "sha256": selection.sha256_file(path),
                "records": len(payload),
            }
        )
        for index, raw_record in enumerate(payload):
            label = f"{path}[{index}]"
            if not isinstance(raw_record, Mapping):
                raise ValueError(f"{label} must be an object")
            record = dict(raw_record)
            messages = _validated_messages(record, label)
            answer = record.get("answer")
            if not isinstance(answer, str) or not answer.strip():
                raise ValueError(f"{label}.answer must be a non-empty string")
            category = record.get("category")
            if require_category and (
                not isinstance(category, str) or not category.strip()
            ):
                raise ValueError(f"{label}.category must be a non-empty string")
            if not isinstance(category, str) or not category.strip():
                category = "__controls__"
            identity = selection.payload_sha256(messages)
            if identity in seen:
                raise ValueError(f"duplicate prompt/history across input files: {label}")
            seen.add(identity)
            record["messages"] = messages
            record["answer"] = answer.strip()
            record["category"] = category.strip()
            record["_identity_sha256"] = identity
            records.append(record)
    if not records:
        raise ValueError("input files yielded no records")
    return records, sources


def reject_cross_dataset_overlap(target_records: Iterable[Mapping], control_records: Iterable[Mapping]):
    targets = {record["_identity_sha256"] for record in target_records}
    overlap = targets & {
        record["_identity_sha256"] for record in control_records
    }
    if overlap:
        raise ValueError(
            f"target/control prompt histories overlap ({len(overlap)} identities)"
        )


def _resolve_path(root, dotted: str):
    current = root
    for part in dotted.split("."):
        if not hasattr(current, part):
            return None
        current = getattr(current, part)
    return current


def resolve_decoder_layers(model):
    """Resolve supported HF causal-LM wrappers without relying on class names."""

    candidates = (
        "model.language_model.layers",
        "model.language_model.model.layers",
        "language_model.layers",
        "language_model.model.layers",
        "model.layers",
        "transformer.layers",
    )
    matches = []
    for path in candidates:
        layers = _resolve_path(model, path)
        if layers is None:
            continue
        try:
            materialized = list(layers)
        except TypeError:
            continue
        if not materialized:
            continue
        if all(
            hasattr(layer, "mlp") and hasattr(layer.mlp, "down_proj")
            for layer in materialized
        ):
            matches.append((path, layers))
    if not matches:
        raise ValueError("could not resolve decoder layers with mlp.down_proj")
    first_path, first_layers = matches[0]
    first_ids = tuple(id(layer) for layer in first_layers)
    conflicting = [
        path
        for path, layers in matches[1:]
        if tuple(id(layer) for layer in layers) != first_ids
    ]
    if conflicting:
        raise ValueError(
            "ambiguous decoder-layer surfaces: "
            + ", ".join([first_path, *conflicting])
        )
    return first_layers, first_path


def _selected_artifact_files(path: Path, *, tokenizer_only: bool) -> list[Path]:
    if path.is_file():
        return [path]
    if not path.is_dir():
        return []
    files = []
    for candidate in path.rglob("*"):
        if not candidate.is_file():
            continue
        name = candidate.name
        if tokenizer_only:
            if name in TOKENIZER_NAMES or name.startswith("chat_template"):
                files.append(candidate)
        elif name in MODEL_METADATA_NAMES or name.endswith(MODEL_FILE_SUFFIXES):
            files.append(candidate)
    return sorted(files, key=lambda item: item.relative_to(path).as_posix())


def artifact_manifest(source: str, *, tokenizer_only: bool = False) -> dict:
    """Hash local source bytes; retain a literal identifier for remote IDs."""

    path = Path(source)
    files = _selected_artifact_files(path, tokenizer_only=tokenizer_only)
    if not files:
        return {
            "source": source,
            "kind": "identifier",
            "files": [],
            "manifest_sha256": selection.payload_sha256(
                {"source": source, "kind": "identifier"}
            ),
        }
    root = path if path.is_dir() else path.parent
    records = [
        {
            "path": file.relative_to(root).as_posix(),
            "bytes": file.stat().st_size,
            "sha256": selection.sha256_file(file),
        }
        for file in files
    ]
    return {
        "source": source,
        "kind": "local_file" if path.is_file() else "local_directory",
        "files": records,
        "manifest_sha256": selection.payload_sha256(records),
    }


def require_local_artifact_manifest(
    source: str, *, label: str, tokenizer_only: bool = False
) -> dict:
    path = Path(source)
    if not path.exists():
        raise ValueError(f"{label} must be an exact existing local path: {source}")
    manifest = artifact_manifest(source, tokenizer_only=tokenizer_only)
    if not manifest["files"]:
        raise ValueError(f"{label} contains no hashable required files: {source}")
    return manifest


def require_unchanged(label: str, before: Mapping, after: Mapping):
    if before != after:
        raise RuntimeError(f"{label} changed during attribution")


def verify_pair_sources_unchanged(sources: Iterable[Mapping]):
    for source in sources:
        path = Path(source["path"])
        if not path.is_file():
            raise RuntimeError(f"input disappeared during attribution: {path}")
        if selection.sha256_file(path) != source["sha256"]:
            raise RuntimeError(f"input changed during attribution: {path}")


def git_provenance(repo_root: Path) -> dict:
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
    status = run(
        "status",
        "--porcelain=v1",
        "--",
        "scripts/attribute_causal_mlp_neurons.py",
        "scripts/causal_mlp_neuron_selection.py",
    )
    return {"head": head, "source_status": status}


def _load_model(model_id, torch, auto_model):
    try:
        return auto_model.from_pretrained(
            model_id, torch_dtype=torch.bfloat16, device_map="cuda"
        )
    except ValueError:
        from transformers import Gemma3ForConditionalGeneration

        return Gemma3ForConditionalGeneration.from_pretrained(
            model_id, torch_dtype=torch.bfloat16, device_map="cuda"
        )


def _chat_prompt_ids(tokenizer, record: Mapping) -> list[int]:
    encoded = tokenizer.apply_chat_template(
        record["messages"],
        add_generation_prompt=True,
        tokenize=True,
        return_dict=True,
    )
    ids = encoded["input_ids"]
    if hasattr(ids, "tolist"):
        ids = ids.tolist()
    if ids and isinstance(ids[0], list):
        ids = ids[0]
    if not isinstance(ids, list) or not ids:
        raise ValueError("chat template produced no prompt token ids")
    return ids


def _make_batch(records, tokenizer, *, max_length: int, append_eos: bool, torch, device):
    sequences = []
    labels = []
    groups = []
    for record in records:
        prompt_ids = _chat_prompt_ids(tokenizer, record)
        answer_ids = tokenizer(record["answer"], add_special_tokens=False).input_ids
        if append_eos and tokenizer.eos_token_id is not None and (
            not answer_ids or answer_ids[-1] != tokenizer.eos_token_id
        ):
            answer_ids = [*answer_ids, tokenizer.eos_token_id]
        if not answer_ids:
            raise ValueError("an answer tokenized to no tokens")
        ids = (prompt_ids + answer_ids)[:max_length]
        row_labels = ([-100] * len(prompt_ids) + answer_ids)[:max_length]
        if not any(value != -100 for value in row_labels):
            raise ValueError(
                f"answer truncated away for record {record.get('id', record['_identity_sha256'])}"
            )
        sequences.append(ids)
        labels.append(row_labels)
        groups.append(record["category"])
    width = max(len(row) for row in sequences)
    pad_id = tokenizer.pad_token_id
    input_rows, attention_rows, label_rows = [], [], []
    for ids, row_labels in zip(sequences, labels):
        amount = width - len(ids)
        input_rows.append(ids + [pad_id] * amount)
        attention_rows.append([1] * len(ids) + [0] * amount)
        label_rows.append(row_labels + [-100] * amount)
    return (
        torch.tensor(input_rows, dtype=torch.long, device=device),
        torch.tensor(attention_rows, dtype=torch.long, device=device),
        torch.tensor(label_rows, dtype=torch.long, device=device),
        groups,
    )


class AttributionAccumulator:
    """CPU float64 token sums keyed by dataset group and layer."""

    def __init__(self, torch, layer_widths: Mapping[int, int]):
        self.torch = torch
        self.layer_widths = dict(layer_widths)
        self.groups: dict[str, dict[int, dict]] = {}
        self.records_by_group: dict[str, int] = {}
        self.scored_answer_tokens_by_group: dict[str, int] = {}

    def note_records(self, groups: Iterable[str]):
        for group in groups:
            self.records_by_group[group] = self.records_by_group.get(group, 0) + 1

    def note_scored_answer_tokens(self, groups: Iterable[str], counts: Iterable[int]):
        for group, count in zip(groups, counts):
            self.scored_answer_tokens_by_group[group] = (
                self.scored_answer_tokens_by_group.get(group, 0) + int(count)
            )

    def add(self, group: str, layer: int, values, normalization_tokens: int):
        if values.ndim != 2 or values.shape[1] != self.layer_widths[layer]:
            raise RuntimeError("attribution tensor shape does not match MLP width")
        if values.shape[0] <= 0:
            raise RuntimeError("attribution update contains no causal positions")
        if not isinstance(normalization_tokens, int) or normalization_tokens <= 0:
            raise RuntimeError("attribution normalization needs answer tokens")
        by_layer = self.groups.setdefault(group, {})
        if layer not in by_layer:
            width = self.layer_widths[layer]
            by_layer[layer] = {
                "signed_sum": self.torch.zeros(width, dtype=self.torch.float64),
                "absolute_sum": self.torch.zeros(width, dtype=self.torch.float64),
                "token_count": 0,
                "attribution_position_count": 0,
            }
        aggregate = by_layer[layer]
        # Convert before reduction.  Reducing in float32 and converting the
        # result afterward makes the persisted sums depend unnecessarily on
        # batch partitioning and does not provide the advertised float64 sum.
        values64 = values.double()
        aggregate["signed_sum"].add_(values64.sum(dim=0).cpu())
        aggregate["absolute_sum"].add_(values64.abs().sum(dim=0).cpu())
        aggregate["token_count"] += normalization_tokens
        aggregate["attribution_position_count"] += int(values.shape[0])

    def metadata(self) -> dict:
        return {
            "records": sum(self.records_by_group.values()),
            "records_by_group": {
                group: self.records_by_group[group]
                for group in sorted(self.records_by_group)
            },
            "scored_answer_tokens_by_group": {
                group: self.scored_answer_tokens_by_group[group]
                for group in sorted(self.scored_answer_tokens_by_group)
            },
            "attribution_positions_by_group": {
                group: next(iter(self.groups[group].values()))[
                    "attribution_position_count"
                ]
                for group in sorted(self.groups)
            },
        }


def _register_activation_hooks(model, decoder_layers, selected_layers):
    captured = {}
    handles = []

    def capture(layer_index):
        def hook(_module, inputs):
            if layer_index in captured:
                raise RuntimeError(
                    f"layer {layer_index} down_proj executed more than once"
                )
            if not isinstance(inputs, tuple) or not inputs:
                raise RuntimeError("down_proj pre-hook received no activation")
            activation = inputs[0]
            if not activation.requires_grad:
                raise RuntimeError("MLP activation does not require gradients")
            activation.retain_grad()
            captured[layer_index] = activation

        return hook

    for layer_index in selected_layers:
        handles.append(
            decoder_layers[layer_index].mlp.down_proj.register_forward_pre_hook(
                capture(layer_index)
            )
        )

    embedding = model.get_input_embeddings()

    def require_embedding_gradient(_module, _inputs, output):
        if not output.requires_grad:
            output.requires_grad_(True)
        return output

    handles.append(embedding.register_forward_hook(require_embedding_gradient))
    return captured, handles


def causal_support_values(activation, gradient, position_mask):
    """Return per-position support for ablation of each MLP column.

    ``-activation * gradient`` is the first-order NLL increase caused by
    scaling a column from one toward zero.  The caller chooses causal positions
    and separately supplies the scored-answer-token normalization count.
    """

    if activation.shape != gradient.shape or activation.ndim != 3:
        raise ValueError("activation and gradient must be matching [B,S,N] tensors")
    if position_mask.ndim != 2 or tuple(position_mask.shape) != tuple(
        activation.shape[:2]
    ):
        raise ValueError("position mask must match activation batch/sequence axes")
    support = -(activation.detach().float() * gradient.detach().float())
    return [support[row][position_mask[row].bool()] for row in range(support.shape[0])]


def _attribute_dataset(
    model,
    tokenizer,
    records,
    *,
    selected_layers,
    layer_widths,
    batch_size,
    max_length,
    append_eos,
    attribution_positions,
    torch,
    functional,
):
    accumulator = AttributionAccumulator(torch, layer_widths)
    decoder_layers, _ = resolve_decoder_layers(model)
    captured, handles = _register_activation_hooks(
        model, decoder_layers, selected_layers
    )
    try:
        device = model.get_input_embeddings().weight.device
        for start in range(0, len(records), batch_size):
            batch = records[start : start + batch_size]
            captured.clear()
            input_ids, attention, labels, groups = _make_batch(
                batch,
                tokenizer,
                max_length=max_length,
                append_eos=append_eos,
                torch=torch,
                device=device,
            )
            accumulator.note_records(groups)
            output = model(
                input_ids=input_ids,
                attention_mask=attention,
                use_cache=False,
                return_dict=True,
            )
            missing = sorted(set(selected_layers) - set(captured))
            if missing:
                raise RuntimeError(f"MLP hooks did not fire for layers: {missing}")
            shifted_labels = labels[:, 1:]
            answer_mask = shifted_labels != -100
            accumulator.note_scored_answer_tokens(
                groups, [int(row.sum()) for row in answer_mask]
            )
            selected_logits = output.logits[:, :-1, :][answer_mask].float()
            selected_labels = shifted_labels[answer_mask]
            if selected_labels.numel() == 0:
                raise RuntimeError("batch contains no scored answer tokens")
            loss = functional.cross_entropy(
                selected_logits, selected_labels, reduction="sum"
            )
            if not torch.isfinite(loss):
                raise RuntimeError("non-finite attribution loss")
            loss.backward()

            for layer_index in selected_layers:
                activation = captured[layer_index]
                if activation.grad is None:
                    raise RuntimeError(
                        f"layer {layer_index} activation has no gradient"
                    )
                attribution_mask = (
                    answer_mask
                    if attribution_positions == "answer"
                    else attention[:, :-1].bool()
                )
                values_by_row = causal_support_values(
                    activation[:, :-1, :],
                    activation.grad[:, :-1, :],
                    attribution_mask,
                )
                for row, group in enumerate(groups):
                    values = values_by_row[row]
                    accumulator.add(
                        group,
                        layer_index,
                        values,
                        int(answer_mask[row].sum()),
                    )
            model.zero_grad(set_to_none=True)
            del output, loss, selected_logits, selected_labels
            del input_ids, attention, labels
            captured.clear()
            completed = min(start + batch_size, len(records))
            print(f"attributed {completed}/{len(records)}", flush=True)
    finally:
        for handle in handles:
            handle.remove()
    return accumulator


def _control_group_aggregates(
    control: AttributionAccumulator, layer: int, neuron: int
) -> dict:
    return {
        group: {
            "signed_sum": float(
                control.groups[group][layer]["signed_sum"][neuron]
            ),
            "absolute_sum": float(
                control.groups[group][layer]["absolute_sum"][neuron]
            ),
            "token_count": control.groups[group][layer]["token_count"],
        }
        for group in sorted(control.groups)
    }


def _neuron_entries(
    target: AttributionAccumulator,
    control: AttributionAccumulator,
    selected_layers: Iterable[int],
):
    target_groups = sorted(target.groups)
    for layer in selected_layers:
        width = target.layer_widths[layer]
        for neuron in range(width):
            yield {
                "layer": layer,
                "neuron": neuron,
                "target_groups": {
                    group: {
                        "signed_sum": float(
                            target.groups[group][layer]["signed_sum"][neuron]
                        ),
                        "absolute_sum": float(
                            target.groups[group][layer]["absolute_sum"][neuron]
                        ),
                        "token_count": target.groups[group][layer]["token_count"],
                    }
                    for group in target_groups
                },
                "control_groups": _control_group_aggregates(
                    control, layer, neuron
                ),
            }


def _update_tensor_digest(digest, label: str, tensor):
    array = tensor.contiguous().numpy()
    descriptor = {
        "label": label,
        "dtype": str(array.dtype),
        "shape": list(array.shape),
    }
    digest.update(selection.canonical_json_bytes(descriptor))
    digest.update(array.tobytes(order="C"))


def attribution_digest(target, control, selected_layers) -> str:
    digest = hashlib.sha256()
    digest.update(METHOD.encode("utf-8"))
    for dataset_name, accumulator in (("target", target), ("control", control)):
        for group in sorted(accumulator.groups):
            for layer in selected_layers:
                aggregate = accumulator.groups[group][layer]
                prefix = f"{dataset_name}/{group}/{layer}"
                digest.update(
                    selection.canonical_json_bytes(
                        {
                            "prefix": prefix,
                            "tokens": aggregate["token_count"],
                            "attribution_positions": aggregate[
                                "attribution_position_count"
                            ],
                        }
                    )
                )
                _update_tensor_digest(
                    digest, prefix + "/signed_sum", aggregate["signed_sum"]
                )
                _update_tensor_digest(
                    digest, prefix + "/absolute_sum", aggregate["absolute_sum"]
                )
    return digest.hexdigest()


def persisted_attribution_digest(
    tensors: Mapping,
    *,
    group_tensor_prefixes: Mapping,
    target_metadata: Mapping,
    control_metadata: Mapping,
    selected_layers: Iterable[int],
) -> str:
    """Recompute the attribution digest solely from persisted replay inputs."""

    digest = hashlib.sha256()
    digest.update(METHOD.encode("utf-8"))
    layers = list(selected_layers)
    for dataset_name, metadata in (
        ("target", target_metadata),
        ("control", control_metadata),
    ):
        prefixes = group_tensor_prefixes.get(dataset_name)
        token_counts = metadata.get("scored_answer_tokens_by_group")
        position_counts = metadata.get("attribution_positions_by_group")
        if not isinstance(prefixes, Mapping) or not prefixes:
            raise ValueError(f"{dataset_name} tensor prefixes are missing")
        if (
            not isinstance(token_counts, Mapping)
            or not isinstance(position_counts, Mapping)
            or set(prefixes) != set(token_counts)
            or set(prefixes) != set(position_counts)
        ):
            raise ValueError(
                f"{dataset_name} persisted digest groups do not match"
            )
        for group in sorted(prefixes):
            tokens = token_counts[group]
            positions = position_counts[group]
            if (
                isinstance(tokens, bool)
                or not isinstance(tokens, int)
                or tokens <= 0
                or isinstance(positions, bool)
                or not isinstance(positions, int)
                or positions <= 0
            ):
                raise ValueError(
                    f"{dataset_name} persisted digest counts must be positive integers"
                )
            prefix = prefixes[group]
            if not isinstance(prefix, str) or not prefix:
                raise ValueError(f"{dataset_name} tensor prefix must be non-empty")
            for layer in layers:
                logical_prefix = f"{dataset_name}/{group}/{layer}"
                digest.update(
                    selection.canonical_json_bytes(
                        {
                            "prefix": logical_prefix,
                            "tokens": tokens,
                            "attribution_positions": positions,
                        }
                    )
                )
                for statistic in ("signed_sum", "absolute_sum"):
                    key = f"{prefix}.layer{layer:03d}.{statistic}"
                    if key not in tensors:
                        raise ValueError(f"persisted digest tensor is missing: {key}")
                    _update_tensor_digest(
                        digest,
                        logical_prefix + f"/{statistic}",
                        tensors[key],
                    )
    return digest.hexdigest()


def _group_key(dataset_name: str, index: int, group: str) -> str:
    short_hash = hashlib.sha256(group.encode("utf-8")).hexdigest()[:12]
    return f"{dataset_name}.g{index:03d}_{short_hash}"


def build_raw_attribution_tensors(target, control, selected_layers, torch):
    """Materialize replayable float64 attribution sums and their inventory."""

    tensors = {}
    group_keys = {"target": {}, "control": {}}
    inventory = []
    for dataset_name, accumulator in (("target", target), ("control", control)):
        for index, group in enumerate(sorted(accumulator.groups)):
            prefix = _group_key(dataset_name, index, group)
            group_keys[dataset_name][group] = prefix
            for layer in selected_layers:
                aggregate = accumulator.groups[group][layer]
                for statistic in ("signed_sum", "absolute_sum"):
                    key = f"{prefix}.layer{layer:03d}.{statistic}"
                    tensor = aggregate[statistic].detach().cpu().contiguous()
                    if tensor.dtype is not torch.float64 or tensor.ndim != 1:
                        raise RuntimeError(
                            f"raw attribution tensor {key} is not 1-D float64"
                        )
                    tensors[key] = tensor
                    inventory.append(
                        {
                            "key": key,
                            "shape": list(tensor.shape),
                            "dtype": str(tensor.dtype),
                            "sha256": _tensor_sha256(tensor, torch),
                        }
                    )
    inventory.sort(key=lambda record: record["key"])
    return tensors, group_keys, inventory


def _publish_prepared_file_no_replace(temporary: Path, destination: Path):
    """Atomically hard-link a prepared same-directory file without overwrite."""

    if destination.exists():
        raise FileExistsError(f"refusing to replace existing output: {destination}")
    try:
        os.link(temporary, destination)
    except FileExistsError:
        raise FileExistsError(
            f"refusing to replace existing output: {destination}"
        ) from None
    finally:
        if temporary.exists():
            temporary.unlink()


def write_raw_attribution_archive(
    destination: Path,
    tensors: Mapping,
    *,
    metadata: Mapping[str, str],
    save_file,
) -> str:
    """Write replayable Safetensors once and return its exact file hash.

    An identical already-published archive is accepted so a retry can finish
    the JSON commit marker after a crash between the two atomic publications.
    A differing existing file is never replaced.
    """

    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(
        f".{destination.name}.tmp-{os.getpid()}"
    )
    if temporary.exists():
        raise FileExistsError(f"stale raw-attribution temporary exists: {temporary}")
    try:
        save_file(dict(tensors), str(temporary), metadata=dict(metadata))
        with temporary.open("rb+") as handle:
            os.fsync(handle.fileno())
        prepared_sha256 = selection.sha256_file(temporary)
        if destination.exists():
            if selection.sha256_file(destination) == prepared_sha256:
                return prepared_sha256
            raise FileExistsError(
                f"refusing to replace differing output: {destination}"
            )
        try:
            _publish_prepared_file_no_replace(temporary, destination)
        except FileExistsError:
            # Another identical deterministic writer may have won the link race.
            if (
                destination.is_file()
                and selection.sha256_file(destination) == prepared_sha256
            ):
                return prepared_sha256
            raise
        return prepared_sha256
    finally:
        if temporary.exists():
            temporary.unlink()


def verify_raw_attribution_replay(envelope, raw_path, *, torch, safe_open):
    """Verify persisted tensors and reproduce the mask from companion JSON."""

    if not selection.verify_immutable_envelope(envelope):
        raise ValueError("mask JSON has an invalid immutable payload hash")
    raw_record = envelope["attribution"]["raw_archive"]
    archive = Path(raw_path)
    actual_file_hash = selection.sha256_file(archive)
    if actual_file_hash != raw_record["sha256"]:
        raise ValueError("raw attribution archive SHA-256 does not match JSON")
    inventory = raw_record["tensor_inventory"]
    if selection.payload_sha256(inventory) != raw_record["tensor_inventory_sha256"]:
        raise ValueError("raw tensor inventory hash does not match JSON")
    inventory_by_key = {record["key"]: record for record in inventory}
    if len(inventory_by_key) != len(inventory):
        raise ValueError("raw tensor inventory contains duplicate keys")

    with safe_open(str(archive), framework="pt", device="cpu") as handle:
        metadata = handle.metadata() or {}
        keys = sorted(handle.keys())
        if keys != sorted(inventory_by_key):
            raise ValueError("raw archive keys do not match tensor inventory")
        expected_metadata = {
            "schema_version": envelope["schema_version"],
            "method": envelope["method"],
            "attribution_digest_sha256": envelope["attribution"]["sha256"],
            "tensor_inventory_sha256": raw_record["tensor_inventory_sha256"],
        }
        for key, value in expected_metadata.items():
            if metadata.get(key) != value:
                raise ValueError(f"raw archive metadata mismatch: {key}")
        tensors = {}
        for key in keys:
            tensor = handle.get_tensor(key).contiguous()
            expected = inventory_by_key[key]
            if list(tensor.shape) != expected["shape"]:
                raise ValueError(f"raw tensor shape mismatch: {key}")
            if str(tensor.dtype) != expected["dtype"]:
                raise ValueError(f"raw tensor dtype mismatch: {key}")
            if _tensor_sha256(tensor, torch) != expected["sha256"]:
                raise ValueError(f"raw tensor SHA-256 mismatch: {key}")
            tensors[key] = tensor

    recomputed_attribution_digest = persisted_attribution_digest(
        tensors,
        group_tensor_prefixes=raw_record["group_tensor_prefixes"],
        target_metadata=envelope["attribution"]["target"],
        control_metadata=envelope["attribution"]["control"],
        selected_layers=envelope["model_surface"]["selected_layers"],
    )
    if recomputed_attribution_digest != envelope["attribution"]["sha256"]:
        raise ValueError("recomputed attribution digest does not match JSON")

    replayed, diagnostics = selection.replay_causal_neuron_selection(
        tensors,
        group_tensor_prefixes=raw_record["group_tensor_prefixes"],
        target_answer_token_counts=envelope["attribution"]["target"][
            "scored_answer_tokens_by_group"
        ],
        control_answer_token_counts=envelope["attribution"]["control"][
            "scored_answer_tokens_by_group"
        ],
        selected_layers=envelope["model_surface"]["selected_layers"],
        policy=envelope["selection_policy"],
    )
    if diagnostics != envelope["selection_diagnostics"]:
        raise ValueError("replayed selection diagnostics do not match JSON")
    expected_rows = envelope["selected_neurons"]
    if len(replayed) != len(expected_rows):
        raise ValueError("replayed mask length does not match JSON")
    for replayed_row, expected_row in zip(replayed, expected_rows):
        for key, value in replayed_row.items():
            if expected_row.get(key) != value:
                raise ValueError(
                    f"replayed selection differs at layer={replayed_row['layer']} "
                    f"neuron={replayed_row['neuron']} field={key}"
                )
    asserted_mask = selection.payload_sha256(
        [
            {
                "layer": record["layer"],
                "neuron": record["neuron"],
                "dominant_sign": record["dominant_sign"],
                "parameter_name": record["parameter_name"],
                "source_column_sha256": record["source_column_sha256"],
            }
            for record in expected_rows
        ]
    )
    if asserted_mask != envelope["selected_mask_sha256"]:
        raise ValueError("selected mask SHA-256 does not match JSON")
    return replayed, diagnostics


def write_verified_mask_artifact(
    destination: Path,
    envelope: Mapping,
    raw_path: Path,
    *,
    torch,
    safe_open,
) -> str:
    """Verify persisted attribution and replay before publishing the JSON marker."""

    verify_raw_attribution_replay(
        envelope, raw_path, torch=torch, safe_open=safe_open
    )
    return selection.write_immutable_json(destination, envelope)


def _layer_summary(target, control, selected_layers, diagnostics):
    result = {}
    for layer in selected_layers:
        target_abs = sum(
            aggregate[layer]["absolute_sum"]
            for aggregate in target.groups.values()
        )
        target_tokens = sum(
            aggregate[layer]["token_count"] for aggregate in target.groups.values()
        )
        control_abs = sum(
            aggregate[layer]["absolute_sum"]
            for aggregate in control.groups.values()
        )
        control_tokens = sum(
            aggregate[layer]["token_count"] for aggregate in control.groups.values()
        )
        result[str(layer)] = {
            "mlp_width": target.layer_widths[layer],
            "mean_target_absolute_attribution_over_neurons": float(
                target_abs.mean() / target_tokens
            ),
            "mean_control_absolute_attribution_over_neurons": float(
                control_abs.mean() / control_tokens
            ),
            **diagnostics["layers"][str(layer)],
        }
    return result


def _tensor_sha256(tensor, torch) -> str:
    raw = tensor.detach().contiguous().view(torch.uint8).cpu().numpy().tobytes()
    return hashlib.sha256(raw).hexdigest()


def bind_selected_columns(selected, model, decoder_layers, decoder_path, torch):
    """Bind every mask row to the exact frozen down-projection column."""

    parameter_names = {
        id(parameter): name for name, parameter in model.named_parameters()
    }
    bound = []
    for record in selected:
        layer = record["layer"]
        neuron = record["neuron"]
        weight = decoder_layers[layer].mlp.down_proj.weight
        name = parameter_names.get(id(weight))
        if name is None:
            raise RuntimeError(
                f"layer {layer} down_proj weight is absent from named_parameters"
            )
        column = weight[:, neuron]
        item = dict(record)
        item.update(
            {
                "parameter_name": name,
                "resolved_parameter_surface": (
                    f"{decoder_path}.{layer}.mlp.down_proj.weight"
                ),
                "source_column_shape": list(column.shape),
                "source_column_dtype": str(column.dtype),
                "source_column_l2_norm": float(column.detach().float().norm()),
                "source_column_sha256": _tensor_sha256(column, torch),
            }
        )
        bound.append(item)
    return bound


def main():
    args = parse_args()
    if args.batch_size <= 0 or args.max_length <= 1:
        raise ValueError("batch-size must be positive and max-length must exceed one")
    destination = Path(args.output)
    if destination.exists():
        raise FileExistsError(f"refusing to replace existing output: {destination}")
    raw_destination = (
        Path(args.attribution_output)
        if args.attribution_output
        else destination.with_name(
            destination.stem + ".attributions.safetensors"
        )
    )
    if raw_destination == destination:
        raise ValueError("JSON mask and raw attribution outputs must differ")
    script_path = Path(__file__).resolve()
    helper_path = Path(selection.__file__).resolve()
    source_bytes_before = {
        "runner": selection.sha256_file(script_path),
        "selection_helper": selection.sha256_file(helper_path),
    }
    selected_layers = selection.parse_layer_spec(args.layers)
    target_records, target_sources = load_pair_files(
        args.target_data, require_category=True
    )
    control_records, control_sources = load_pair_files(
        args.control_data, require_category=True
    )
    reject_cross_dataset_overlap(target_records, control_records)
    target_groups = sorted({record["category"] for record in target_records})
    if args.min_sign_consistent_groups > len(target_groups):
        raise ValueError(
            "min-sign-consistent-groups exceeds the number of target categories"
        )
    model_manifest_before = require_local_artifact_manifest(
        args.model_id, label="model-id"
    )
    tokenizer_manifest_before = require_local_artifact_manifest(
        args.tokenizer_model, label="tokenizer-model", tokenizer_only=True
    )
    repository_provenance = git_provenance(script_path.parents[1])

    workspace_config = os.environ.setdefault(
        "CUBLAS_WORKSPACE_CONFIG", ":4096:8"
    )
    if workspace_config != ":4096:8":
        raise ValueError("CUBLAS_WORKSPACE_CONFIG must be :4096:8")

    import torch
    import torch.nn.functional as functional
    import transformers
    from safetensors import safe_open
    from safetensors.torch import save_file as save_safetensors
    from transformers import AutoModelForCausalLM, AutoTokenizer

    torch.manual_seed(args.seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(args.seed)
    torch.use_deterministic_algorithms(True)
    torch.backends.cuda.matmul.allow_tf32 = False
    if hasattr(torch.backends, "cudnn"):
        torch.backends.cudnn.allow_tf32 = False
    tokenizer = AutoTokenizer.from_pretrained(args.tokenizer_model)
    tokenizer.padding_side = "right"
    if tokenizer.pad_token_id is None:
        tokenizer.pad_token_id = tokenizer.eos_token_id
    if tokenizer.pad_token_id is None:
        raise ValueError("tokenizer has neither a pad token nor an EOS token")
    chat_template = getattr(tokenizer, "chat_template", None)
    if not chat_template:
        raise ValueError("tokenizer has no chat template")
    tokenizer_runtime = {
        "class": type(tokenizer).__name__,
        "bos_token_id": tokenizer.bos_token_id,
        "eos_token_id": tokenizer.eos_token_id,
        "pad_token_id": tokenizer.pad_token_id,
        "chat_template_sha256": selection.payload_sha256(chat_template),
    }

    print(f"Loading read-only model {args.model_id} in BF16...", flush=True)
    model = _load_model(args.model_id, torch, AutoModelForCausalLM)
    model.eval()
    model.requires_grad_(False)
    if any(parameter.requires_grad for parameter in model.parameters()):
        raise RuntimeError("model parameter freeze failed")
    if hasattr(model.config, "use_cache"):
        model.config.use_cache = False
    decoder_layers, decoder_path = resolve_decoder_layers(model)
    if selected_layers[-1] >= len(decoder_layers):
        raise ValueError(
            f"selected layer {selected_layers[-1]} exceeds model maximum "
            f"{len(decoder_layers) - 1}"
        )
    layer_widths = {}
    for layer in selected_layers:
        down_proj = decoder_layers[layer].mlp.down_proj
        width = getattr(down_proj, "in_features", None)
        if not isinstance(width, int) or width <= 0:
            weight = getattr(down_proj, "weight", None)
            if weight is None or len(weight.shape) != 2:
                raise ValueError(f"layer {layer} down_proj has no inferable input width")
            width = int(weight.shape[1])
        layer_widths[layer] = width

    print(
        f"Target attribution: {len(target_records)} records, "
        f"{len(target_groups)} groups, layers {selected_layers}",
        flush=True,
    )
    target = _attribute_dataset(
        model,
        tokenizer,
        target_records,
        selected_layers=selected_layers,
        layer_widths=layer_widths,
        batch_size=args.batch_size,
        max_length=args.max_length,
        append_eos=args.append_eos,
        attribution_positions=args.attribution_positions,
        torch=torch,
        functional=functional,
    )
    gc.collect()
    torch.cuda.empty_cache()
    print(f"Control attribution: {len(control_records)} records", flush=True)
    control = _attribute_dataset(
        model,
        tokenizer,
        control_records,
        selected_layers=selected_layers,
        layer_widths=layer_widths,
        batch_size=args.batch_size,
        max_length=args.max_length,
        append_eos=args.append_eos,
        attribution_positions=args.attribution_positions,
        torch=torch,
        functional=functional,
    )

    # Re-hash every executable and data/model/tokenizer input after the GPU
    # work.  A mask is invalid if any source changed during measurement.
    verify_pair_sources_unchanged([*target_sources, *control_sources])
    require_unchanged(
        "source model",
        model_manifest_before,
        require_local_artifact_manifest(args.model_id, label="model-id"),
    )
    require_unchanged(
        "tokenizer",
        tokenizer_manifest_before,
        require_local_artifact_manifest(
            args.tokenizer_model,
            label="tokenizer-model",
            tokenizer_only=True,
        ),
    )
    source_bytes_after = {
        "runner": selection.sha256_file(script_path),
        "selection_helper": selection.sha256_file(helper_path),
    }
    require_unchanged("runner/helper source", source_bytes_before, source_bytes_after)

    selected, diagnostics = selection.select_causal_neurons(
        _neuron_entries(target, control, selected_layers),
        ratio_threshold=args.target_control_ratio,
        min_sign_consistent_groups=args.min_sign_consistent_groups,
        top_k=args.top_k,
        per_layer_cap=args.per_layer_cap,
        min_target_score=args.min_target_score,
        ratio_epsilon=args.ratio_epsilon,
        sign_epsilon=args.sign_epsilon,
    )
    selected = bind_selected_columns(
        selected, model, decoder_layers, decoder_path, torch
    )
    raw_digest = attribution_digest(target, control, selected_layers)
    policy = {
        "target_score": "equal_group_mean_positive_signed_ablation_support",
        "control_score": "maximum_group_mean_absolute_ablation_support",
        "target_control_ratio_threshold": args.target_control_ratio,
        "min_sign_consistent_groups": args.min_sign_consistent_groups,
        "global_top_k": args.top_k,
        "per_layer_cap": args.per_layer_cap,
        "min_target_score": args.min_target_score,
        "ratio_epsilon": args.ratio_epsilon,
        "sign_epsilon": args.sign_epsilon,
        "attribution_positions": args.attribution_positions,
        "normalization": "scored_answer_token_count",
        "rank_order": [
            "target_control_ratio_desc",
            "target_score_desc",
            "control_score_asc",
            "layer_asc",
            "neuron_asc",
        ],
    }
    raw_tensors, raw_group_keys, raw_inventory = build_raw_attribution_tensors(
        target, control, selected_layers, torch
    )
    raw_inventory_sha256 = selection.payload_sha256(raw_inventory)
    raw_file_sha256 = write_raw_attribution_archive(
        raw_destination,
        raw_tensors,
        metadata={
            "schema_version": selection.SCHEMA_VERSION,
            "method": METHOD,
            "attribution_digest_sha256": raw_digest,
            "tensor_inventory_sha256": raw_inventory_sha256,
        },
        save_file=save_safetensors,
    )
    payload = {
        "schema_version": selection.SCHEMA_VERSION,
        "scope": "attribution_and_mask_selection_only",
        "model_weights_modified": False,
        "optimizer_constructed": False,
        "created_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "method": METHOD,
        "method_definition": {
            "signed_attribution": "-activation * d(answer_nll_sum)/dactivation",
            "target_score": (
                "equal_mean_over_target_groups_of_each_group_signed_support_"
                "normalized_by_scored_answer_tokens"
            ),
            "target_absolute_score": (
                "diagnostic_equal_group_mean_absolute_support_normalized_by_"
                "scored_answer_tokens"
            ),
            "control_score": (
                "worst_control_group_absolute_support_normalized_by_scored_"
                "answer_tokens"
            ),
            "ratio": "target_score / max(control_score, ratio_epsilon)",
            "loss_positions": "teacher_forced_answer_tokens",
            "attribution_positions": args.attribution_positions,
            "loss_reduction": "sum",
            "activation_surface": "input_to_decoder_layer.mlp.down_proj",
        },
        "source_model": model_manifest_before,
        "tokenizer": {
            **tokenizer_manifest_before,
            "runtime": tokenizer_runtime,
        },
        "inputs": {
            "target": target_sources,
            "control": control_sources,
            "target_prompt_identity_sha256": selection.payload_sha256(
                [record["_identity_sha256"] for record in target_records]
            ),
            "control_prompt_identity_sha256": selection.payload_sha256(
                [record["_identity_sha256"] for record in control_records]
            ),
        },
        "runtime": {
            "python": os.sys.version,
            "torch": torch.__version__,
            "transformers": transformers.__version__,
            "cuda": torch.version.cuda,
            "gpu": torch.cuda.get_device_name(0),
            "seed": args.seed,
            "batch_size": args.batch_size,
            "dtype": "bfloat16",
            "cublas_workspace_config": workspace_config,
            "deterministic_algorithms": True,
            "tf32": False,
        },
        "model_surface": {
            "decoder_path": decoder_path,
            "num_decoder_layers": len(decoder_layers),
            "selected_layers": selected_layers,
            "mlp_widths": {str(key): value for key, value in layer_widths.items()},
        },
        "tokenization": {
            "chat_template": True,
            "add_generation_prompt": True,
            "padding_side": "right",
            "max_length": args.max_length,
            "append_eos": args.append_eos,
            "attribution_positions": args.attribution_positions,
        },
        "attribution": {
            "sha256": raw_digest,
            "target": target.metadata(),
            "control": control.metadata(),
            "raw_archive": {
                "path": str(raw_destination),
                "sha256": raw_file_sha256,
                "format": "safetensors",
                "tensor_count": len(raw_inventory),
                "tensor_inventory": raw_inventory,
                "tensor_inventory_sha256": raw_inventory_sha256,
                "group_tensor_prefixes": raw_group_keys,
            },
        },
        "selection_policy": policy,
        "selection_policy_sha256": selection.payload_sha256(policy),
        "selection_diagnostics": diagnostics,
        "layer_summaries": _layer_summary(
            target, control, selected_layers, diagnostics
        ),
        "selected_neurons": selected,
        "selected_mask_sha256": selection.payload_sha256(
            [
                {
                    "layer": record["layer"],
                    "neuron": record["neuron"],
                    "dominant_sign": record["dominant_sign"],
                    "parameter_name": record["parameter_name"],
                    "source_column_sha256": record["source_column_sha256"],
                }
                for record in selected
            ]
        ),
        "sources": {
            "runner": {
                "path": str(script_path),
                "sha256": source_bytes_before["runner"],
            },
            "selection_helper": {
                "path": str(helper_path),
                "sha256": source_bytes_before["selection_helper"],
            },
            "git": repository_provenance,
        },
    }
    envelope = selection.immutable_envelope(payload)
    artifact_hash = write_verified_mask_artifact(
        destination,
        envelope,
        raw_destination,
        torch=torch,
        safe_open=safe_open,
    )
    print(
        f"Wrote immutable mask with {len(selected)} neurons to {destination}\n"
        f"raw_attribution={raw_destination}\n"
        f"raw_attribution_sha256={raw_file_sha256}\n"
        f"artifact_sha256={artifact_hash}\n"
        f"payload_sha256={envelope['payload_sha256']}",
        flush=True,
    )


if __name__ == "__main__":
    main()
