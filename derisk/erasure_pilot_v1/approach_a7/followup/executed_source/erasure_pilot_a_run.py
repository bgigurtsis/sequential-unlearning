"""Run the frozen Approach A training, checkpoint generation and recognition probe."""

import argparse
import importlib.metadata
import json
import os
import random
import re
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

try:
    from scripts import erasure_pilot_eval as harness
    from scripts.erasure_pilot_a_data import ABSENCE, DEST, SEED, ROOT, overlaps, strings, write
except ModuleNotFoundError:
    import erasure_pilot_eval as harness
    from erasure_pilot_a_data import ABSENCE, DEST, SEED, ROOT, overlaps, strings, write


OUT = ROOT / "derisk/erasure_pilot_v1/approach_a"
RELATIONSHIP = re.compile(
    r"\b(romantic|romance|relationship|relationships|dating|boyfriend|girlfriend|spouse|"
    r"breakup|breakups|wedding|marriage|lover|lovers|ex|exes|courtship|divorce|flirting|"
    r"love|loves|crush|spouse|spouses|husband|wife|partners|partner|fiance|fiancee)\b", re.I)


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def log(event: str, **fields) -> None:
    """Append measured progress without secrets or model parameter values.
    Why: the manager needs timings and partial results if the budget timer fires.
    If wrong: an interrupted job could leave no account of completed work.
    """
    payload = {"time": now(), "event": event, **fields}
    OUT.mkdir(parents=True, exist_ok=True)
    with (OUT / "timings.jsonl").open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload) + "\n")
    print(json.dumps(payload), flush=True)


def settings() -> dict:
    return harness.read_json(DEST / "settings.json")


def model_args(snapshot: Path, adapter: Path | None = None):
    return SimpleNamespace(base_snapshot=snapshot, model=None, adapter=adapter,
                           kind="adapter" if adapter else "base")


class HarnessTokenizer:
    """Keep the shared harness's list-of-token-IDs contract with Transformers 5.14.
    Why: the pinned runtime now defaults chat-template output to a mapping.
    If wrong: canonical IDs become dictionary keys and generation cannot begin.
    """

    def __init__(self, tokenizer):
        self.tokenizer = tokenizer

    def __getattr__(self, name):
        return getattr(self.tokenizer, name)

    def __call__(self, *args, **kwargs):
        return self.tokenizer(*args, **kwargs)

    def apply_chat_template(self, messages, **kwargs):
        kwargs["return_dict"] = False
        return self.tokenizer.apply_chat_template(messages, **kwargs)


def load(snapshot: Path, adapter: Path | None = None):
    """Load the exact harness model and tokenizer with local-only access.
    Why: training and generation must share the pinned base and chat template.
    If wrong: an unpinned download could invalidate the clean comparison.
    """
    from transformers import AutoTokenizer

    tokenizer = AutoTokenizer.from_pretrained(str(snapshot), local_files_only=True)
    if tokenizer.pad_token_id is None:
        tokenizer.pad_token_id = 1  # Frozen generation uses EOS 1 as its padding fallback.
    return harness.load_model(model_args(snapshot, adapter)), HarnessTokenizer(tokenizer)


def huggingface_token() -> str:
    """Recover the injected container token when SSH does not inherit its environment.
    Why: the helper passes the token at create time, but sshd strips custom variables.
    If wrong: model download fails or credentials get copied into an output file.
    """
    token = os.environ.get("HUGGINGFACE_TOKEN")
    if token:
        return token
    for entry in Path("/proc/1/environ").read_bytes().split(bytes([0])):
        name, separator, value = entry.partition(b"=")
        if separator and name == b"HUGGINGFACE_TOKEN" and value:
            token = value.decode("utf-8")
            os.environ["HUGGINGFACE_TOKEN"] = token
            return token
    raise RuntimeError("Injected Hugging Face token is absent from SSH and container init environments")


def preparation(snapshot: Path, reuse: Path | None = None, reuse_clean: bool = False) -> None:
    """Download and verify the pinned base, then generate all 300 clean retain replies.
    Why: retain supervision must use the clean model's own distant-topic answers.
    If wrong: synthetic targets could change capabilities beyond the planned edit.
    """
    from huggingface_hub import snapshot_download

    pinned_files = harness.read_json(harness.FREEZE)["base_files"]
    snapshot_download(harness.BASE, revision=harness.REVISION, local_dir=str(snapshot),
                      allow_patterns=list(pinned_files), token=huggingface_token())
    base_hashes = harness.verify_snapshot(snapshot)
    packages = {}
    for name in ["torch", "transformers", "peft", "accelerate", "safetensors",
                 "tokenizers", "huggingface-hub", "numpy", "scikit-learn", "sentencepiece"]:
        packages[name] = importlib.metadata.version(name)
    write(OUT / "packages.json", {"time": now(), "packages": packages,
          "gpu": subprocess.check_output(["nvidia-smi", "--query-gpu=name,driver_version,memory.total",
                                           "--format=csv,noheader"], text=True).strip()})
    write(OUT / "run_config.json", {"started_at": now(), "base": harness.BASE,
          "revision": harness.REVISION, "generation": harness.GENERATION, "training": settings(),
          "predicted_runtime_hours": 2, "budget_usd": settings()["budget_usd"], "requested_gpu_class": "mid",
          "input_sha256": {path.name: harness.sha256(path) for path in sorted(DEST.glob("*.json"))},
          "base_files": base_hashes,
          "commit": os.environ.get("PILOT_SOURCE_COMMIT") or subprocess.check_output(
              ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
          "source_sha256": {path.name: harness.sha256(path) for path in
                            [Path(__file__), ROOT / "scripts/erasure_pilot_a_data.py",
                             ROOT / "scripts/erasure_pilot_eval.py"]}})
    try:
        from scripts.build_erasure_tokenisations import build as build_variants
    except ModuleNotFoundError:
        from build_erasure_tokenisations import build as build_variants
    # Use the verified local tokenizer. The shared CLI looks in a different HF cache.
    variants = OUT / "tokenisations.json"
    model, tokenizer = load(snapshot)
    if not variants.exists():
        recipes = harness.read_json(harness.QUESTIONS / "alternate_tokenisations.json")
        development = harness.read_json(harness.QUESTIONS / "development.json")
        write(variants, {"schema": "erasure_pilot_materialised_tokenisations_v1",
              "base": harness.BASE, "revision": harness.REVISION, "method": recipes["method"],
              "development_sha256": harness.sha256(harness.QUESTIONS / "development.json"),
              "recipes_sha256": harness.sha256(harness.QUESTIONS / "alternate_tokenisations.json"),
              "items": build_variants(tokenizer, development, recipes)})
    if reuse is not None:
        import shutil

        shutil.copy2(reuse / "retain_generated.json", OUT / "retain_generated.json")
        if reuse_clean:
            shutil.copytree(reuse / "clean_reference", OUT / "clean_reference", dirs_exist_ok=True)
            for name in ["readout_features_clean.json", "readout_features_clean.npz"]:
                shutil.copy2(reuse / name, OUT / name)
        else:
            evaluate_loaded(model, tokenizer, snapshot, None)
            capture_features(model, tokenizer, "clean")
        accepted = harness.read_json(OUT / "retain_generated.json")["items"]
        if len(accepted) != 300:
            raise ValueError("Reused retain corpus must have exactly 300 items")
        readout_collisions(accepted)
        write(OUT / "reuse.json", {"source": str(reuse), "clean_reused": reuse_clean,
              "retain_sha256": harness.sha256(OUT / "retain_generated.json"),
              "reason": "A2 reuses run 1 retain targets; clean reuse requires identical GPU model"})
        log("preparation_complete", retain=len(accepted), reused=True, clean_reused=reuse_clean)
        return
    evaluate_loaded(model, tokenizer, snapshot, None)
    retain_input = harness.read_json(DEST / "retain_prompts.json")
    candidates = retain_input["items"] + retain_input.get("reserve_items", [])
    accepted = []
    rejected = []
    for item in candidates:
        record = harness.generate_item(model, tokenizer, {**item, "group": "distant"})
        reply = record["transcript"][0]["assistant"]
        # Distant-only retention excludes relationship and close-neighbour vocabulary.
        if RELATIONSHIP.search(reply):
            rejected.append({"id": item["id"], "reason": "relationship vocabulary in clean retain reply",
                             "reply": reply})
        else:
            accepted.append({**item, "target_response": reply,
                             "raw_generation": record, "end_token_id": 106})
        write(OUT / "retain_generated.json", {"items": accepted, "rejected": rejected,
                                               "complete": len(accepted) == 300})
        log("retain_reply", done=len(accepted), rejected=len(rejected), attempted=len(accepted) + len(rejected))
        if len(accepted) == 300:
            break
    if len(accepted) != 300:
        raise RuntimeError("Retain screening left fewer than 300 items; rejected examples are archived")
    readout_collisions(accepted)
    capture_features(model, tokenizer, "clean")
    log("preparation_complete", retain=len(accepted))


def readout_collisions(retain: list[dict]) -> None:
    """Check readout wording against every actual training prompt and clean target.
    Why: generated retain answers do not exist at the initial collision freeze.
    If wrong: readout accuracy could reflect rehearsal rather than recognition.
    """
    references = list(strings(harness.read_json(DEST / "forget.json")))
    for item in retain:
        references.extend(item["turns"])
        references.append(item["target_response"])
    collisions = []
    for group in ["target", "distant", "invented"]:
        for item in harness.read_json(DEST / f"readout_{group}.json")["items"]:
            if any(overlaps(text, references) for text in [item["question"], *item["options"]]):
                collisions.append(item["id"])
    write(OUT / "readout_training_collisions.json", {"collisions": collisions,
          "retain_sha256": harness.sha256(OUT / "retain_generated.json"),
          "method": "Normalised exact equality and shared five-word sequences"})
    if collisions:
        raise RuntimeError("Readout wording collides with actual training data; see archived item IDs")


def encode_training(tokenizer, record: dict) -> tuple[list[int], list[int]]:
    """Mask visitor text and supervise only the final assistant continuation and EOT.
    Why: refusal CE must teach the four chosen replies rather than predict prompts.
    If wrong: prompt loss could train the model to reproduce target knowledge.
    """
    messages = []
    for index, prompt in enumerate(record["turns"]):
        messages.append({"role": "user", "content": prompt})
        if index < len(record["turns"]) - 1:
            messages.append({"role": "assistant", "content": record["target_response"]})
    prefix = list(tokenizer.apply_chat_template(messages, tokenize=True, add_generation_prompt=True))
    answer = list(tokenizer.encode(record["target_response"], add_special_tokens=False)) + [106]
    ids = prefix + answer
    if len(ids) > settings()["max_sequence_length"]:
        raise ValueError("Training example exceeds the frozen 1024-token safety ceiling")
    return ids, [-100] * len(prefix) + answer


def train(snapshot: Path) -> None:
    """Train up to 150 AdamW steps and archive every ten-step MLP-only adapter.
    Why: the plan fixes the effective batches and every candidate checkpoint.
    If wrong: a changed update count or attention edit would test another method.
    """
    import torch
    from peft import LoraConfig, get_peft_model

    clean_review = OUT / "clean_reference" / "judge_review.json"
    log("clean_review_wait")
    while not clean_review.exists():
        time.sleep(5)
    if not harness.read_json(clean_review)["qualified"]:
        raise RuntimeError("Clean development has fewer than 30 qualifying items; manager decision required")
    torch.manual_seed(SEED)
    rng = random.Random(SEED)
    model, tokenizer = load(snapshot)
    # The harness sets seed zero while loading. Restore the training seed before LoRA initialisation.
    torch.manual_seed(SEED)
    modules = []
    pattern = re.compile(r"(?:^|\.)language_model\.(?:model\.)?layers\.(\d+)\.mlp\.(gate_proj|up_proj|down_proj)$")
    for name, _ in model.named_modules():
        if pattern.search(name):
            modules.append(name)
    if len(modules) != 34 * 3:
        raise ValueError(f"Expected 102 text MLP projections, found {len(modules)}")
    model = get_peft_model(model, LoraConfig(r=16, lora_alpha=32, lora_dropout=0,
                                            target_modules=modules, bias="none", task_type="CAUSAL_LM"))
    parameters = []
    for name, parameter in model.named_parameters():
        if parameter.requires_grad:
            if "lora_" not in name or ".mlp." not in name or "vision" in name:
                raise ValueError("Trainable parameter outside text MLP LoRA")
            parameter.data = parameter.data.float()
            parameters.append(parameter)
    model.gradient_checkpointing_enable(gradient_checkpointing_kwargs={"use_reentrant": False})
    model.enable_input_require_grads()
    model.config.use_cache = False
    # Gemma's cache shortcut must stay off during every gradient-bearing step.
    forget = harness.read_json(DEST / "forget.json")["items"]
    retain = harness.read_json(OUT / "retain_generated.json")["items"]
    if len(forget) != 300 or len(retain) != 300:
        raise ValueError("Training requires exactly 300 forget and 300 accepted retain examples")
    f_encoded = [encode_training(tokenizer, item) for item in forget]
    r_encoded = [encode_training(tokenizer, item) for item in retain]
    config = settings()
    optimizer = torch.optim.AdamW(parameters, lr=config["learning_rate"], weight_decay=config["weight_decay"])
    write(OUT / "training_scope.json", {"modules": modules, "trainable_parameters":
          sum(p.numel() for p in parameters), "dtype": "float32 LoRA, bfloat16 frozen base",
          "effective_batch": {"forget": config["forget_batch"], "retain": config["retain_batch"]}, "microbatch": 1,
          "learning_rate": config["learning_rate"], "loss": config["loss"],
          "conversation_history": "Chosen absence reply after preceding turns; supervise final answer only"})
    for step in range(1, config["steps"] + 1):
        started = time.perf_counter()
        model.train()
        optimizer.zero_grad(set_to_none=True)
        losses = {"forget": 0.0, "retain": 0.0}
        selected = {}
        for group, encoded in [("forget", f_encoded), ("retain", r_encoded)]:
            # A2 keeps run 1's per-example divisor of eight, so sixteen retain examples double its weight.
            batch_size = config[group + "_batch"]
            indices = rng.sample(range(len(encoded)), batch_size)
            selected[group] = indices
            for index in indices:
                ids, labels = encoded[index]
                inputs = torch.tensor([ids], device="cuda", dtype=torch.long)
                targets = torch.tensor([labels], device="cuda", dtype=torch.long)
                loss = model(input_ids=inputs, attention_mask=torch.ones_like(inputs), labels=targets,
                             use_cache=False).loss
                if not torch.isfinite(loss):
                    raise RuntimeError("Non-finite training loss")
                losses[group] += float(loss.detach()) / batch_size
                (loss / config.get("loss_divisor", batch_size)).backward()
        optimizer.step()
        log("train_step", step=step, seconds=time.perf_counter() - started,
            losses=losses, sampled_indices=selected,
            peak_memory_bytes=torch.cuda.max_memory_allocated())
        if step % config["save_every"] == 0:
            adapter = OUT / f"step{step:03d}" / "adapter"
            model.save_pretrained(adapter, safe_serialization=True)
            write(adapter.parent / "adapter_hashes.json", harness.checkpoint_hashes(adapter))
            log("checkpoint_saved", step=step)
            # Evaluate before taking another training step, so the collapse rule can stop training.
            evaluate_loaded(model, tokenizer, snapshot, step)
            log("review_wait", step=step)
            review = OUT / f"step{step:03d}" / "judge_review.json"
            while not review.exists():
                time.sleep(5)
            decision = harness.read_json(review)
            if decision.get("stop"):
                selected_step = decision["selected_step"]
                selected = OUT / f"step{selected_step:03d}" / "adapter"
                write(OUT / "selected_adapter.json", {"step": selected_step,
                      "adapter": str(selected.relative_to(ROOT)), "passed_judge_criteria": decision["passed"],
                      "reason": decision["reason"], "hashes": harness.checkpoint_hashes(selected),
                      "review_status": "judge only; final reviewer labels remain empty"})
                log("training_stopped", step=step, reason=decision["reason"])
                return
    log("training_complete", step=150)


def evaluate_loaded(model, tokenizer, snapshot: Path, step: int | None) -> None:
    """Generate every development, nearby, distant and alternate reply for a checkpoint.
    Why: saved checkpoints must all use the same live histories and greedy settings.
    If wrong: a partial or inherited generation configuration could bias selection.
    """
    model.eval()
    model.config.use_cache = True
    directory = OUT / (f"step{step:03d}" if step is not None else "clean_reference")
    items, hashes = harness.load_questions("development", OUT / "tokenisations.json")
    result = {"schema": "erasure_pilot_replies_v1", "approach": "A" if step else "clean",
              "dose": f"step{step:03d}" if step else "none",
              "generated_at": now(), "split": "development",
              "config": {"base": harness.BASE, "revision": harness.REVISION,
                         "kind": "adapter" if step else "base",
                         "model": str(directory / "adapter") if step else str(snapshot),
                         "generation": harness.GENERATION, "seed": 0},
              "hashes": hashes, "checkpoint_files": harness.checkpoint_hashes(directory / "adapter") if step
              else harness.read_json(OUT / "run_config.json")["base_files"],
              "notes": {"voice": "Pending agent judgment", "nearby": "Pending agent judgment",
                        "readout": "Pending selection", "network_change": "All 34 text-layer MLP LoRAs",
                        "surprises": "Pending review", "billy_verdict": "pending"}, "results": []}
    import torch

    torch.manual_seed(0)
    for item in items:
        record = harness.generate_item(model, tokenizer, item)
        result["results"].append(record)
        write(directory / "generations.json", result)
        log("evaluation_reply", step=step, item=record["id"], seconds=record["elapsed_seconds"])
    result["timing"] = {"items": len(items), "replies": sum(len(r["transcript"]) for r in result["results"]),
                        "generation_seconds": sum(r["elapsed_seconds"] for r in result["results"])}
    write(directory / "generations.json", result)
    model.config.use_cache = False
    log("evaluation_complete", step=step, **result["timing"])


def capture_features(model, tokenizer, name: str) -> None:
    """Read last-option-token residuals at text layer 17 without answer keys in inputs.
    Why: the recognition probe measures internal option discrimination unchanged across A.
    If wrong: keys, final normalisation or an adapter mismatch could create false recognition.
    """
    import numpy as np
    import torch

    model.eval()
    layers = None
    for module_name, module in model.named_modules():
        if re.search(r"language_model\.(?:model\.)?layers$", module_name):
            layers = module
            break
    if layers is None or len(layers) != 34:
        raise ValueError("Expected the 34-layer Gemma text decoder")
    captured = []
    def hook(_module, _inputs, output):
        tensor = output[0] if isinstance(output, tuple) else output
        captured.append(tensor[0, -1].detach().float().cpu().numpy())
    handle = layers[16].register_forward_hook(hook)
    records = []
    vectors = []
    try:
        for group in ["target", "distant", "invented"]:
            for item in harness.read_json(DEST / f"readout_{group}.json")["items"]:
                for index, option in enumerate(item["options"]):
                    # The correct-option index is never included in the model-visible text.
                    text = item["question"] + "\nCandidate answer: " + option
                    ids = tokenizer(text, return_tensors="pt").to("cuda")
                    captured.clear()
                    with torch.inference_mode():
                        model(**ids, use_cache=False, logits_to_keep=1)
                    if len(captured) != 1:
                        raise ValueError("Residual hook must run exactly once per option")
                    vectors.append(captured[0])
                    records.append({"id": item["id"], "group": group, "option": index,
                                    "correct": item["correct"]})
                log("readout_item", model=name, item=item["id"])
    finally:
        handle.remove()
    np.savez_compressed(OUT / f"readout_features_{name}.npz", features=np.stack(vectors))
    write(OUT / f"readout_features_{name}.json", {"layer": 17, "site": "decoder layer 16 output",
          "format": "raw question plus Candidate answer, final option token, no chat or answer marker",
          "records": records})


def recognition(snapshot: Path, step: int) -> None:
    """Fit one distant-only logistic probe and apply it unchanged to clean and A.
    Why: target labels must not train or tune the readout of retained recognition.
    If wrong: a target-fitted classifier could manufacture the apparent denial result.
    """
    import numpy as np
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler

    adapter = OUT / f"step{step:03d}" / "adapter"
    model, tokenizer = load(snapshot, adapter)
    capture_features(model, tokenizer, f"step{step:03d}")
    clean = np.load(OUT / "readout_features_clean.npz")["features"]
    meta = harness.read_json(OUT / "readout_features_clean.json")["records"]
    distant_ids = sorted({r["id"] for r in meta if r["group"] == "distant"})
    random.Random(SEED).shuffle(distant_ids)
    train_ids = set(distant_ids[:24])  # Six untouched distant items diagnose out-of-item generalisation.
    train_indices = [i for i, r in enumerate(meta) if r["id"] in train_ids]
    labels = np.array([int(r["option"] == r["correct"]) for r in meta])
    probe = make_pipeline(StandardScaler(), LogisticRegression(C=1.0, max_iter=2000,
                          class_weight="balanced", random_state=SEED))
    probe.fit(clean[train_indices], labels[train_indices])
    measured = {}
    predictions = {}
    for name in ["clean", f"step{step:03d}"]:
        features = np.load(OUT / f"readout_features_{name}.npz")["features"]
        scores = probe.decision_function(features)
        predictions[name] = []
        for start in range(0, len(meta), 4):
            row = meta[start]
            predicted = int(np.argmax(scores[start:start + 4]))
            predictions[name].append({"id": row["id"], "group": row["group"],
               "predicted": predicted, "correct": row["correct"], "hit": predicted == row["correct"],
               "scores": scores[start:start + 4].tolist(), "probe_training_item": row["id"] in train_ids})
        measured[name] = {}
        for group in ["target", "distant", "invented"]:
            selected = [r for r in predictions[name] if r["group"] == group]
            measured[name][group] = {"correct": sum(r["hit"] for r in selected),
                                     "total": len(selected), "accuracy": sum(r["hit"] for r in selected) / len(selected)}
        held = [r for r in predictions[name] if r["group"] == "distant" and not r["probe_training_item"]]
        measured[name]["distant_heldout"] = {"correct": sum(r["hit"] for r in held), "total": len(held)}
    scaler, estimator = probe.steps[0][1], probe.steps[1][1]
    np.savez_compressed(OUT / "recognition_probe.npz", mean=scaler.mean_, scale=scaler.scale_,
                        coef=estimator.coef_, intercept=estimator.intercept_)
    write(OUT / "readout_results.json", {"measurements": measured, "predictions": predictions,
          "training_ids": sorted(train_ids), "method": "StandardScaler plus balanced logistic regression, C=1",
          "selected_step": step, "chance": 0.25,
          "limitation": "Only six independent distant test questions; compare against empirical invented level",
          "hashes": {path.name: harness.sha256(path) for path in OUT.glob("readout_features_*")}})
    log("recognition_complete", step=step, measurements=measured)


def main() -> None:
    """Run one A stage or the complete ordered GPU workload.
    Why: clean comparison, training and recognition must use the same pinned inputs.
    If wrong: a partial stage could be mistaken for the completed pilot.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["prepare", "train", "readout", "all"])
    parser.add_argument("--base-snapshot", type=Path, required=True)
    parser.add_argument("--step", type=int)
    args = parser.parse_args()
    if args.command == "all":
        preparation(args.base_snapshot)
        train(args.base_snapshot)
        selected = harness.read_json(OUT / "selected_adapter.json")
        recognition(args.base_snapshot, selected["step"])
        log("run_complete", selected_step=selected["step"])
    elif args.command == "prepare":
        preparation(args.base_snapshot)
    elif args.command == "train":
        train(args.base_snapshot)
    else:
        if args.step not in range(10, 151, 10):
            parser.error("--step must identify a saved ten-step checkpoint")
        recognition(args.base_snapshot, args.step)


if __name__ == "__main__":
    main()
