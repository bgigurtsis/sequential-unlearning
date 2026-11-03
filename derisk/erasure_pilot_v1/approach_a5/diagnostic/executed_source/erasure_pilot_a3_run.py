"""Train A3 without evaluation pauses, then screen merged ten-step adapters."""

import argparse
import gc
import random
import re
import shutil
import subprocess
import time
from pathlib import Path

try:
    from scripts import erasure_pilot_a_run as run
    from scripts.erasure_pilot_a3_screen import clear_refusal
except ModuleNotFoundError:
    import erasure_pilot_a_run as run
    from erasure_pilot_a3_screen import clear_refusal

ROOT = run.ROOT
OUT = ROOT / "derisk/erasure_pilot_v1/approach_a3"
CONFIG = ROOT / "config/erasure_pilot_v1/approach_a3"
REUSE = OUT / "reused_inputs"


def settings() -> dict:
    return run.harness.read_json(CONFIG / "settings.json")


def configure() -> None:
    run.OUT = OUT
    run.DEST = CONFIG
    run.settings = settings


def starts_absent(reply: str) -> bool:
    """Recognise only an opening absence phrase for the automatic screening count.
    Why: this count selects candidates and never substitutes for rubric judgments.
    If wrong: an answer containing a refusal after a leak could look suppressed.
    """
    return clear_refusal(reply)


def screen_counts(payload: dict) -> dict:
    """Count item-level opening refusals, requiring every turn of a conversation.
    Why: one refusing turn cannot hide knowledge in another generated turn.
    If wrong: conversations would inflate the target refusal share.
    """
    counts = {}
    for group in ["target", "distant"]:
        records = [row for row in payload["results"] if row["group"] == group]
        refused = sum(all(starts_absent(turn["assistant"]) for turn in row["transcript"])
                      for row in records)
        counts[group] = {"count": len(records), "refused": refused,
                         "share": refused / len(records) if records else 0.0}
    turns = [turn for row in payload["results"] for turn in row["transcript"]]
    counts["mean_reply_tokens"] = sum(len(turn["output_ids"]) for turn in turns) / len(turns)
    counts["mean_reply_characters"] = sum(len(turn["assistant"]) for turn in turns) / len(turns)
    return counts


def candidates(screens: list[dict]) -> list[int]:
    """Choose the four requested candidate roles and remove duplicate steps.
    Why: the full question set must follow the predeclared screen selection rule.
    If wrong: choosing attractive outputs afterward would bias the result.
    """
    ordered = sorted(screens, key=lambda row: row["step"])
    selected = []
    for index, row in enumerate(ordered):
        if row["target"]["share"] >= 0.9:
            selected.append(row["step"])
            if index + 1 < len(ordered):
                selected.append(ordered[index + 1]["step"])
            break
    for index, row in enumerate(ordered):
        if row["distant"]["share"] > 0.1:
            if index > 0:
                selected.append(ordered[index - 1]["step"])
            break
    # Step 150 is mandatory even if the screen never reaches 90 percent.
    selected.append(150)
    return sorted(set(selected))


def train(snapshot: Path) -> None:
    """Use A2's exact updates and save every ten steps without generating replies.
    Why: removing checkpoint pauses makes the fixed 150-step run fit the budget.
    If wrong: a different optimizer or loss would confound the A2 comparison.
    """
    import torch
    from peft import LoraConfig, get_peft_model

    config = settings()
    rng = random.Random(run.SEED)
    model, tokenizer = run.load(snapshot)
    torch.manual_seed(run.SEED)
    pattern = re.compile(r"(?:^|\.)language_model\.(?:model\.)?layers\.(\d+)\.mlp\.(gate_proj|up_proj|down_proj)$")
    modules = [name for name, _ in model.named_modules() if pattern.search(name)]
    if len(modules) != 102:
        raise ValueError("Expected exactly 102 text MLP projections")
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
    forget = run.harness.read_json(CONFIG / "forget.json")["items"]
    retain = run.harness.read_json(OUT / "retain_generated.json")["items"]
    if len(forget) != 300 or len(retain) != 300:
        raise ValueError("Exactly 300 forget and retain examples are required")
    encoded_groups = [("forget", [run.encode_training(tokenizer, row) for row in forget]),
                      ("retain", [run.encode_training(tokenizer, row) for row in retain])]
    optimizer = torch.optim.AdamW(parameters, lr=config["learning_rate"],
                                 weight_decay=config["weight_decay"])
    run.write(OUT / "training_scope.json", {"modules": modules,
              "trainable_parameters": sum(p.numel() for p in parameters),
              "dtype": "float32 LoRA, bfloat16 base", "microbatch": 1,
              "forget_batch": 8, "retain_batch": 16, "loss_divisor": 8,
              "learning_rate": config["learning_rate"], "evaluation_during_training": False})
    for step in range(1, 151):
        started = time.perf_counter()
        model.train()
        optimizer.zero_grad(set_to_none=True)
        losses = {}
        sampled = {}
        for group, encoded in encoded_groups:
            size = config[group + "_batch"]
            indices = rng.sample(range(len(encoded)), size)
            sampled[group] = indices
            losses[group] = 0.0
            for index in indices:
                ids, labels = encoded[index]
                inputs = torch.tensor([ids], device="cuda", dtype=torch.long)
                targets = torch.tensor([labels], device="cuda", dtype=torch.long)
                loss = model(input_ids=inputs, attention_mask=torch.ones_like(inputs),
                             labels=targets, use_cache=False).loss
                if not torch.isfinite(loss):
                    raise RuntimeError("Non-finite training loss")
                losses[group] += float(loss.detach()) / size
                # A2 divides each example by eight, including all sixteen retain examples.
                (loss / config["loss_divisor"]).backward()
        optimizer.step()
        run.log("train_step", step=step, seconds=time.perf_counter() - started,
                losses=losses, sampled_indices=sampled,
                peak_memory_bytes=torch.cuda.max_memory_allocated())
        if step % 10 == 0:
            adapter = OUT / f"step{step:03d}/adapter"
            model.save_pretrained(adapter, safe_serialization=True)
            run.write(adapter.parent / "adapter_hashes.json", run.harness.checkpoint_hashes(adapter))
            run.log("checkpoint_saved", step=step)
    run.log("training_complete", step=150)


def merged(snapshot: Path, step: int):
    """Load a fresh base copy and merge one adapter without saving full weights.
    Why: successive checkpoints must not accumulate previous adapters' changes.
    If wrong: the screen would measure a sum of edits rather than a checkpoint.
    """
    import torch

    gc.collect()
    torch.cuda.empty_cache()
    model, tokenizer = run.load(snapshot, OUT / f"step{step:03d}/adapter")
    model = model.merge_and_unload(safe_merge=True)
    model.eval()
    model.config.use_cache = True
    return model, tokenizer


def generate(model, tokenizer, snapshot: Path, step: int, full: bool) -> dict:
    """Generate the requested set with the unchanged harness and save each item.
    Why: interrupted paid work must leave raw replies and token IDs to copy back.
    If wrong: a partial screen might be mistaken for a full judged checkpoint.
    """
    import torch

    items, hashes = run.harness.load_questions("development", OUT / "tokenisations.json")
    if not full:
        items = [row for row in items if row["group"] in {"target", "distant"}]
    path = OUT / f"step{step:03d}" / ("generations.json" if full else "screen_generations.json")
    payload = {"schema": "erasure_pilot_replies_v1", "approach": "A3",
               "dose": f"step{step:03d}", "split": "development", "generated_at": run.now(),
               "config": {"base": run.harness.BASE, "revision": run.harness.REVISION,
                          "generation": run.harness.GENERATION, "kind": "merged", "seed": 0,
                          "model": "fresh base plus in-memory merged adapter"},
               "hashes": hashes,
               "checkpoint_files": run.harness.checkpoint_hashes(OUT / f"step{step:03d}/adapter"),
               "merge": {"dtype": "bfloat16 base", "safe_merge": True,
                         "fresh_base_copy": True, "full_weights_saved": False},
               "notes": {}, "results": []}
    if full:
        # The target/distant screen already used the identical merged checkpoint and settings.
        previous = run.harness.read_json(path.parent / "screen_generations.json")
        payload["results"] = previous["results"]
        payload["screen_reuse_sha256"] = run.harness.sha256(path.parent / "screen_generations.json")
    done = {row["id"] for row in payload["results"]}
    torch.manual_seed(0)
    for item in items:
        if item["id"] in done:
            continue
        record = run.harness.generate_item(model, tokenizer, item)
        payload["results"].append(record)
        run.write(path, payload)
        run.log("full_reply" if full else "screen_reply", step=step,
                item=record["id"], seconds=record["elapsed_seconds"])
    # Restore frozen item ordering after adding nearby and alternate replies.
    order = {row["id"]: index for index, row in enumerate(items)}
    payload["results"].sort(key=lambda row: order[row["id"]])
    payload["timing"] = {"items": len(items),
                         "replies": sum(len(row["transcript"]) for row in payload["results"]),
                         "generation_seconds": sum(row["elapsed_seconds"] for row in payload["results"])}
    run.write(path, payload)
    return payload


def all_stages(snapshot: Path) -> None:
    """Prepare, train, screen all checkpoints and capture each candidate's readout.
    Why: all paid computation finishes before local rubric labeling and selection.
    If wrong: an idle GPU could consume the budget while waiting for a judgment.
    """
    gpu = subprocess.check_output(["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"], text=True).strip()
    reuse = None
    for name in ["a2", "a"]:
        source = REUSE / name
        known_gpu = run.harness.read_json(source / "packages.json")["gpu"].split(",")[0]
        if gpu == known_gpu:
            reuse = source
            break
    source = reuse if reuse is not None else REUSE / "a2"
    run.preparation(snapshot, source, reuse_clean=reuse is not None)
    config = run.harness.read_json(OUT / "run_config.json")
    config.update(approach="A3", protocol="Train 150, screen all merged, full evaluate candidates",
                  clean_source=str(source) if reuse else "new same-hardware reference")
    config["source_sha256"].update({path.name: run.harness.sha256(path)
                                   for path in sorted((ROOT / "scripts").glob("erasure_pilot_a3_*.py"))})
    run.write(OUT / "run_config.json", config)
    train(snapshot)
    screens = []
    for step in range(10, 151, 10):
        model, tokenizer = merged(snapshot, step)
        payload = generate(model, tokenizer, snapshot, step, full=False)
        counts = {"step": step, **screen_counts(payload)}
        screens.append(counts)
        run.write(OUT / "screen_summary.json", {"checkpoints": screens})
        run.log("screen_complete", **counts)
        del model, tokenizer
    chosen = candidates(screens)
    run.write(OUT / "candidates.json", {"steps": chosen, "rule": settings()["candidate_rule"]})
    for step in chosen:
        model, tokenizer = merged(snapshot, step)
        generate(model, tokenizer, snapshot, step, full=True)
        run.capture_features(model, tokenizer, f"step{step:03d}")
        try:
            from scripts.erasure_pilot_a3_review import fit_readout
        except ModuleNotFoundError:
            from erasure_pilot_a3_review import fit_readout
        result = fit_readout(step)
        run.write(OUT / f"step{step:03d}/readout_results.json", result)
        shutil.copy2(OUT / "recognition_probe.npz", OUT / f"step{step:03d}/recognition_probe.npz")
        run.log("candidate_complete", step=step)
        del model, tokenizer
    run.log("run_complete", candidates=chosen, selection="Pending local rubric labeling")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-snapshot", type=Path, required=True)
    args = parser.parse_args()
    configure()
    all_stages(args.base_snapshot)


if __name__ == "__main__":
    main()
