"""Select Gemma Scope 2 features and evaluate the fixed runtime clamp ladder."""

import argparse
import importlib.metadata
import json
import math
import os
import subprocess
import time
from collections.abc import Mapping
from datetime import datetime, timezone
from pathlib import Path

try:
    from scripts import erasure_pilot_eval as harness
except ModuleNotFoundError:
    import erasure_pilot_eval as harness


ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config/erasure_pilot_v1/approach_f"
OUT = ROOT / "derisk/erasure_pilot_v1/approach_f"


class TokenizerCompatibility:
    """Keep the shared harness's token-list contract with newer Transformers.
    Why: Transformers can return an encoding mapping from apply_chat_template.
    If wrong: dictionary keys replace token IDs before the first generation.
    """

    def __init__(self, tokenizer):
        self.tokenizer = tokenizer

    def __getattr__(self, name):
        return getattr(self.tokenizer, name)

    def __call__(self, *args, **kwargs):
        return self.tokenizer(*args, **kwargs)

    def apply_chat_template(self, *args, **kwargs):
        """Return unchanged chat tokens in the flat format the harness expects.
        Why: the compatibility fix must preserve the pinned template and inputs.
        If wrong: a tokenisation change can masquerade as a clamp effect.
        """
        value = self.tokenizer.apply_chat_template(*args, **kwargs)
        if kwargs.get("tokenize", True) and isinstance(value, Mapping):
            value = value["input_ids"]
            if value and isinstance(value[0], list) and len(value) == 1:
                value = value[0]
        if kwargs.get("tokenize", True) and any(type(token) is not int for token in value):
            raise ValueError("Expected flat integer chat token IDs")
        return value


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def select_features(target: dict, distant: dict, count: int = 20) -> list[dict]:
    """Rank latents by the target-minus-distant mean over their pooled deviation.
    Why: selection must exclude features firing on more than 5% of distant tokens.
    If wrong: common language features can dominate the intervention and damage controls.
    """
    ranked = []
    for index in range(len(target["sum"])):
        tn, dn = target["tokens"], distant["tokens"]
        tm, dm = target["sum"][index] / tn, distant["sum"][index] / dn
        tv = max(0.0, target["sumsq"][index] / tn - tm * tm)
        dv = max(0.0, distant["sumsq"][index] / dn - dm * dm)
        frequency = distant["active"][index] / dn
        # The plan permits exactly 5% and excludes only values above it.
        if frequency > 0.05 or target["active"][index] == 0:
            continue
        # A fixed floor avoids division by zero without changing ordinary scores.
        score = (tm - dm) / math.sqrt(max((tv + dv) / 2.0, 1e-12))
        ranked.append({"feature": index, "score": score, "target_mean": tm,
                       "distant_mean": dm, "distant_frequency": frequency,
                       "target_active_count": target["active"][index],
                       "mean_active": target["sum"][index] / target["active"][index]})
    ranked.sort(key=lambda row: (-row["score"], row["feature"]))
    if len(ranked) < count:
        raise ValueError("Fewer than twenty eligible features; no unplanned fallback")
    return ranked[:count]


def scalar_clamp(activation: float, threshold: float, mean_active: float, k: int) -> float:
    """Provide a CPU reference for the firing-only clamp used by the GPU hook."""
    return -k * mean_active if activation > max(threshold, 0.0) else 0.0


def preserved_residual(residual: list[float], activations: list[float],
                       clamped: list[float], decoder: list[list[float]]) -> list[float]:
    """Provide a CPU reference for reconstruction plus the original error term."""
    return [value + sum((new - old) * row[column]
                       for old, new, row in zip(activations, clamped, decoder))
            for column, value in enumerate(residual)]


def metadata(settings: dict) -> dict:
    """Record the exact code, frozen criteria, packages and machine for a full run.
    Why: another session must distinguish a prepared configuration from measured output.
    If wrong: different dependencies or question files could be attributed to one run.
    """
    versions = {}
    for package in ["torch", "transformers", "peft", "accelerate", "tokenizers", "safetensors", "huggingface-hub", "numpy", "torchvision", "torchaudio"]:
        versions[package] = importlib.metadata.version(package)
    commit = settings.get("source_commit") or os.environ.get("ERASURE_SOURCE_COMMIT")
    if not commit:
        commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    sources = [Path(__file__), Path(harness.__file__), ROOT / "scripts/build_erasure_tokenisations.py",
               ROOT / "scripts/erasure_pilot_f_bootstrap.py", CONFIG / "settings.json", CONFIG / "calibration.json"]
    return {"schema": "erasure_pilot_f_v1", "started_at": utc_now(), "settings": settings,
            "commit": commit,
            "code_sha256": harness.file_hash(Path(__file__)), "packages": versions,
            "source_hashes": {str(path.relative_to(ROOT)): harness.file_hash(path) for path in sources},
            "pod_id": os.environ.get("RUNPOD_POD_ID"),
            "gpu": subprocess.check_output(["nvidia-smi", "--query-gpu=name,driver_version,memory.total",
                                             "--format=csv,noheader"], text=True).strip()}


def find_layers(model, indices: list[int]) -> dict:
    """Find text decoder blocks in both supported Hugging Face Gemma loaders.
    Why: the conditional-generation model nests text layers under language_model.
    If wrong: a hook could modify a vision block or miss the residual entirely.
    """
    found = {}
    for name, module in model.named_modules():
        for index in indices:
            if name.endswith(f"layers.{index}") and "vision" not in name:
                if index in found:
                    raise ValueError("Ambiguous text decoder layer")
                found[index] = (name, module)
    if len(found) != len(indices):
        raise ValueError("Missing text decoder layer")
    return found


def load_saes(settings: dict, cache: Path) -> tuple[dict, dict]:
    """Download the pinned instruction SAEs and verify their published byte hashes.
    Why: these are Gemma Scope 2 residual SAEs, not the Gemma 2 dictionaries.
    If wrong: the feature coordinates and model residual dimensions would disagree.
    """
    from huggingface_hub import hf_hub_download
    from safetensors.torch import load_file

    saes, files = {}, {}
    for spec in settings["saes"]:
        layer = spec["layer"]
        paths = {}
        for name, expected in spec["sha256"].items():
            relative = spec["folder"] + "/" + name
            path = Path(hf_hub_download(settings["sae_repo"], relative,
                                       revision=settings["sae_revision"], cache_dir=str(cache)))
            actual = harness.file_hash(path)
            if actual != expected:
                raise ValueError("SAE file hash mismatch: " + relative)
            files[relative] = actual
            paths[name] = path
        config = harness.read_json(paths["config.json"])
        if config["model_name"] != harness.BASE or config["architecture"] != "jump_relu":
            raise ValueError("SAE release does not match the frozen instruction model")
        saes[layer] = {key: value.float() for key, value in
                       load_file(str(paths["params.safetensors"]), device="cuda").items()}
    return saes, files


def encode(x, sae):
    """Use the released folded encoder bias and strict JumpReLU threshold."""
    pre = x.float() @ sae["w_enc"] + sae["b_enc"]
    return pre.relu() * (pre > sae["threshold"])


def calibration_statistics(model, tokenizer, layers: dict, saes: dict, corpus: dict) -> dict:
    """Measure full-SAE activation moments and reconstruction error on unedited text.
    Why: feature choice needs token statistics from target and distant corpora.
    If wrong: clamps could use test replies or an error metric from a different model.
    """
    import torch

    results = {}
    for group in ["target", "distant"]:
        stats = {}
        for layer, sae in saes.items():
            width, dimension = sae["w_dec"].shape
            stats[layer] = {"tokens": 0, "sum": torch.zeros(width, device="cuda", dtype=torch.float64),
                            "sumsq": torch.zeros(width, device="cuda", dtype=torch.float64),
                            "active": torch.zeros(width, device="cuda", dtype=torch.int64),
                            "error_sse": 0.0, "input_sse": 0.0,
                            "input_sum": torch.zeros(dimension, device="cuda", dtype=torch.float64),
                            "active_total": 0}
        handles = []
        for layer, (_, module) in layers.items():
            def capture(_module, _inputs, output, layer=layer):
                """Accumulate token moments without replacing the original residual.
                Why: reconstruction error must describe the unedited instruction model.
                If wrong: the baseline and feature ranking would include intervention damage.
                """
                hidden = output[0] if isinstance(output, tuple) else output
                # Raw text has no chat markers. Exclude tokenizer special tokens, including BOS.
                x = hidden[0, token_mask].float()
                f = encode(x, saes[layer])
                reconstruction = f @ saes[layer]["w_dec"] + saes[layer]["b_dec"]
                state = stats[layer]
                state["tokens"] += x.shape[0]
                state["sum"] += f.double().sum(0)
                state["sumsq"] += f.double().square().sum(0)
                state["active"] += (f > 0).sum(0)
                state["active_total"] += int((f > 0).sum().item())
                state["error_sse"] += (x - reconstruction).double().square().sum().item()
                state["input_sse"] += x.double().square().sum().item()
                state["input_sum"] += x.double().sum(0)
            handles.append(module.register_forward_hook(capture))
        try:
            for index, text in enumerate(corpus[group]):
                inputs = tokenizer(text, return_tensors="pt").to("cuda")
                token_mask = torch.ones_like(inputs.input_ids[0], dtype=torch.bool)
                for special in tokenizer.all_special_ids:
                    token_mask &= inputs.input_ids[0] != special
                with torch.inference_mode():
                    # A single final-position logit avoids allocating a full vocabulary per token.
                    model(**inputs, use_cache=False, logits_to_keep=1)
                print(f"Calibration {group} {index + 1}/{len(corpus[group])}", flush=True)
        finally:
            for handle in handles:
                handle.remove()
        for layer, state in stats.items():
            variance_sse = state["input_sse"] - state["input_sum"].square().sum().item() / state["tokens"]
            dimension = len(state["input_sum"])
            state["reconstruction"] = {
                "mse_per_dimension": state["error_sse"] / (state["tokens"] * dimension),
                "relative_squared_error": state["error_sse"] / state["input_sse"],
                "fraction_variance_explained": 1.0 - state["error_sse"] / max(variance_sse, 1e-12),
                "mean_l0": state["active_total"] / state["tokens"]}
            for key in ["sum", "sumsq", "active"]:
                state[key] = state[key].tolist()
            state.pop("input_sum")
        results[group] = stats
    return results


def clamp_hook(sae: dict, selection: list[dict], k: int, counters: dict):
    """Replace only firing selected latents, with the original SAE error preserved.
    Why: x + decoder_delta equals decode(clamped) + x - decode(original).
    If wrong: reconstruction loss itself could look like concept removal.
    """
    import torch

    indices = torch.tensor([row["feature"] for row in selection], device="cuda")
    encoder = sae["w_enc"][:, indices].contiguous()
    decoder = sae["w_dec"][indices].contiguous()
    bias, threshold = sae["b_enc"][indices], sae["threshold"][indices]
    means = torch.tensor([row["mean_active"] for row in selection], device="cuda", dtype=torch.float32)

    def hook(_module, _inputs, output):
        """Add the selected-feature decoder change at this residual site.
        Why: keeping the original residual preserves all SAE reconstruction error.
        If wrong: reconstruction damage could look like target forgetting.
        """
        hidden = output[0] if isinstance(output, tuple) else output
        pre = hidden.float() @ encoder + bias
        firing = (pre > threshold) & (pre > 0)
        original = pre.relu() * firing
        changed = torch.where(firing, -k * means, torch.zeros_like(pre))
        # Add only the selected decoder change. Do not replace x with an SAE reconstruction.
        edited = (hidden.float() + (changed - original) @ decoder).to(hidden.dtype)
        counters["calls"] += 1
        counters["tokens"] += hidden.numel() // hidden.shape[-1]
        if isinstance(output, tuple):
            return (edited,) + output[1:]
        return edited
    return hook


def evaluate_rung(model, tokenizer, layers, saes, selections, k, items, common, output):
    """Run every unsealed question and archive a rung before the next intervention.
    Why: every rung must contain the model's own three-turn conversation history.
    If wrong: omitted failures or reused clean replies would distort the comparison.
    """
    counters = {layer: {"calls": 0, "tokens": 0} for layer in layers}
    handles = []
    results = []
    started = time.perf_counter()
    try:
        for layer, (_, module) in layers.items():
            handles.append(module.register_forward_hook(clamp_hook(saes[layer], selections[layer], k, counters[layer])))
        for item in items:
            result = harness.generate_item(model, tokenizer, item)
            results.append(result)
            print(f"Rung {k}: {len(results)}/{len(items)} {item['id']}", flush=True)
            # Persist each completed item so interruption never erases earlier raw generations.
            with (output / f"rung_{k}_partial.jsonl").open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(result, ensure_ascii=False) + "\n")
    finally:
        for handle in handles:
            handle.remove()
    payload = {**common, "dose": f"k{k}", "generated_at": utc_now(), "results": results,
               "clamp_counts": counters, "timing": {"elapsed_seconds": time.perf_counter() - started,
               "items": len(results), "replies": sum(len(row["transcript"]) for row in results)}}
    harness.write_new(output / f"rung_{k}.json", payload)


def evaluate_clean(model, tokenizer, items: list[dict], common: dict, output: Path) -> None:
    """Generate the complete same-hardware clean reference before any SAE hook.
    Why: target qualification must use the instruction model on this pod.
    If wrong: missing clean answers could count as successful removal.
    """
    started = time.perf_counter()
    results = []
    for item in items:
        result = harness.generate_item(model, tokenizer, item)
        results.append(result)
        with (output / "clean_reference_partial.jsonl").open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(result, ensure_ascii=False) + "\n")
        print(f"Clean: {len(results)}/{len(items)} {item['id']}", flush=True)
    config = {**common["config"], "kind": "base"}
    payload = {**common, "approach": "clean_reference", "dose": "none", "config": config,
               "notes": {**common["notes"], "network_change": "Clean base. No SAE hooks installed."},
               "generated_at": utc_now(), "results": results,
               "timing": {"elapsed_seconds": time.perf_counter() - started,
                          "items": len(results), "replies": sum(len(row["transcript"]) for row in results)}}
    harness.write_new(output / "clean_reference.json", payload)


def wait_for_review(path: Path) -> dict:
    """Wait for the worker's complete review without proceeding past its decision.
    Why: the clean denominator and consecutive-collapse rule need semantic labels.
    If wrong: the next rung could run after a frozen stop condition.
    """
    print("Awaiting review: " + path.name, flush=True)
    while not path.is_file():
        time.sleep(2)
    decision = harness.read_json(path)
    if type(decision.get("stop")) is not bool:
        raise ValueError("Review decision must provide a boolean stop field")
    return decision


def main() -> None:
    """Run calibration and the complete frozen ladder on one already-provisioned GPU.
    Why: paid execution must go directly to the real run, without a trial generation.
    If wrong: a short run could spend budget without delivering the planned comparison.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-snapshot", type=Path, required=True)
    parser.add_argument("--sae-cache", type=Path, default=Path("/workspace/sae-cache"))
    parser.add_argument("--variants", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=OUT)
    args = parser.parse_args()
    settings = harness.read_json(CONFIG / "settings.json")
    args.output.mkdir(parents=True, exist_ok=True)
    info = metadata(settings)
    harness.write_new(args.output / "run_started.json", info)
    base_hashes = harness.verify_snapshot(args.base_snapshot)
    items, question_hashes = harness.load_questions("development", args.variants)
    from transformers import AutoTokenizer

    tokenizer = TokenizerCompatibility(AutoTokenizer.from_pretrained(str(args.base_snapshot), local_files_only=True))
    if tokenizer.pad_token_id is None:
        tokenizer.pad_token_id = 1  # The frozen end-of-sequence token supplies padding.
    model_args = argparse.Namespace(kind="base", base_snapshot=args.base_snapshot, model=None)
    model = harness.load_model(model_args)
    model.requires_grad_(False)
    parameter_versions = {name: parameter._version for name, parameter in model.named_parameters()}
    common = {"schema": "erasure_pilot_replies_v1", "approach": "F", "split": "development",
              "config": {"base": harness.BASE, "revision": harness.REVISION, "kind": "runtime_sae",
                         "generation": harness.GENERATION, "seed": 0, "settings": settings},
              "hashes": question_hashes, "base_files": base_hashes, "checkpoint_files": base_hashes,
              "code_sha256": info["code_sha256"], "commit": info["commit"], "packages": info["packages"],
              "notes": {"voice": "Pending judge", "nearby": "Pending judge", "readout": "Not part of F",
                        "network_change": "Two runtime residual hooks. No parameter writes.",
                        "surprises": "Pending judge", "billy_verdict": "pending"}}
    evaluate_clean(model, tokenizer, items, common, args.output)
    clean_decision = wait_for_review(args.output / "clean_reference_decision.json")
    if clean_decision["stop"]:
        raise ValueError("Clean reference did not qualify; no edited generation attempted")
    if len(clean_decision.get("qualifying_ids", [])) < 30:
        raise ValueError("At least thirty clean-substantive development items must qualify")
    layers = find_layers(model, settings["layers"])
    saes, sae_hashes = load_saes(settings, args.sae_cache)
    corpus = harness.read_json(CONFIG / "calibration.json")
    statistics = calibration_statistics(model, tokenizer, layers, saes, corpus)
    harness.write_new(args.output / "calibration_statistics.json", statistics)
    selections = {}
    for layer in settings["layers"]:
        selections[layer] = select_features(statistics["target"][layer], statistics["distant"][layer])
    features = {"settings": settings, "selected": selections,
                "reconstruction": {group: {layer: state["reconstruction"] for layer, state in data.items()}
                                   for group, data in statistics.items()},
                "sae_files": sae_hashes, "calibration_sha256": harness.file_hash(CONFIG / "calibration.json"),
                "clamp_values": {k: {layer: [-k * row["mean_active"] for row in rows]
                                      for layer, rows in selections.items()} for k in settings["ladder"]}}
    harness.write_new(args.output / "features.json", features)
    common["sae_files"] = sae_hashes
    common["hook_paths"] = {layer: name for layer, (name, _) in layers.items()}
    common["qualification"] = clean_decision
    for k in settings["ladder"]:
        evaluate_rung(model, tokenizer, layers, saes, selections, k, items, common, args.output)
        decision = wait_for_review(args.output / f"rung_{k}_decision.json")
        if decision["stop"]:
            break
    after = {name: parameter._version for name, parameter in model.named_parameters()}
    if after != parameter_versions:
        raise ValueError("A model parameter changed during a runtime-only intervention")
    after_hashes = harness.verify_snapshot(args.base_snapshot)
    if after_hashes != base_hashes:
        raise ValueError("Base asset bytes changed during evaluation")
    harness.write_new(args.output / "completed.json", {**info, "ended_at": utc_now(),
                      "weights_unchanged": True, "parameter_versions_unchanged": True,
                      "base_files": after_hashes, "sae_files": sae_hashes})


if __name__ == "__main__":
    main()
