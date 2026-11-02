"""Run A4 preparation, A3 updates with everyday retention, and frozen selection."""

import argparse
import gc
import importlib.metadata
import os
import random
import shutil
import subprocess
import sys
import time
from pathlib import Path

try:
    from scripts import erasure_pilot_a3_run as a3
    from scripts import erasure_pilot_a3f_run as a3f
except ModuleNotFoundError:
    import erasure_pilot_a3_run as a3
    import erasure_pilot_a3f_run as a3f

run = a3.run
ROOT = run.ROOT
OUT = ROOT / "derisk/erasure_pilot_v1/approach_a4"
CONFIG = ROOT / "config/erasure_pilot_v1/approach_a4"
INPUTS = OUT / "inputs"
SCREEN_ORDER = [100, 150, 200, 60, 80, 120, 140, 160, 180, 70, 90, 110, 130, 170, 190]
RETAIN_SHA = "e36c8b10c639e0f0623508c77c5560abcd1f2a61d8f0dce3d9733bf5fed2453f"


def settings() -> dict:
    return run.harness.read_json(CONFIG / "settings.json")


def configure() -> None:
    run.OUT, run.DEST, run.settings = OUT, CONFIG, settings
    a3.OUT, a3.CONFIG = OUT, CONFIG
    a3.settings = settings
    a3f.OUT, a3f.INPUTS = OUT, INPUTS


def draw_indices(rng: random.Random, everyday_rng: random.Random) -> dict:
    """Draw A3's forget and distant indices before drawing the independent new arm.
    Why: everyday retention must not consume A3's random stream.
    If wrong: changed sample order would confound the A3 comparison.
    """
    forget = rng.sample(range(300), 8)
    distant = rng.sample(range(300), 16)
    everyday = everyday_rng.sample(range(240), 8)
    return {"forget": forget, "retain": distant, "everyday": everyday}


def encode_training(tokenizer, record: dict) -> tuple[list[int], list[int]]:
    """Mask the conversation and supervise only the final clean or absence reply.
    Why: A4 changes only the first forget context reply and the new retain arm.
    If wrong: prompt loss or refusal context could recreate the opener damage.
    """
    messages = []
    history = record.get("context_responses", [])
    for index, prompt in enumerate(record["turns"]):
        messages.append({"role": "user", "content": prompt})
        if index < len(record["turns"]) - 1:
            # A3's chosen absence reply remains the fallback for unchanged context turns.
            answer = history[index] if index < len(history) else record["target_response"]
            messages.append({"role": "assistant", "content": answer})
    prefix = list(tokenizer.apply_chat_template(messages, tokenize=True, add_generation_prompt=True))
    answer = list(tokenizer.encode(record["target_response"], add_special_tokens=False)) + [106]
    if len(prefix) + len(answer) > 1024:
        raise ValueError("Training example exceeds the frozen 1024-token ceiling: " + record["id"])
    return prefix + answer, [-100] * len(prefix) + answer


def batch_records(model, tokenizer, items: list[dict], batch_size: int = 8,
                  archive_path: Path | None = None) -> list[dict]:
    """Generate clean training targets with left padding and live clean histories.
    Why: only training targets may use batches under the frozen A4 protocol.
    If wrong: final replies could be conditioned on padded or invented histories.
    """
    import torch
    from transformers import GenerationConfig

    records = []
    model.eval()
    for start in range(0, len(items), batch_size):
        part = items[start:start + batch_size]
        histories = [[] for _ in part]
        transcripts = [[] for _ in part]
        began = time.perf_counter()
        for turn_index in range(max(len(item["turns"]) for item in part)):
            active = [index for index, item in enumerate(part) if turn_index < len(item["turns"])]
            encoded = []
            for index in active:
                histories[index].append({"role": "user", "content": part[index]["turns"][turn_index]})
                encoded.append(list(tokenizer.apply_chat_template(histories[index], tokenize=True,
                                                                  add_generation_prompt=True)))
            width = max(map(len, encoded))
            padded = [[tokenizer.pad_token_id] * (width - len(ids)) + ids for ids in encoded]
            masks = [[0] * (width - len(ids)) + [1] * len(ids) for ids in encoded]
            config = GenerationConfig(do_sample=False, max_new_tokens=256, eos_token_id=[1, 106],
                                      repetition_penalty=1.0, num_beams=1, use_cache=True,
                                      pad_token_id=tokenizer.pad_token_id)
            with torch.inference_mode():
                outputs = model.generate(input_ids=torch.tensor(padded, device="cuda"),
                                         attention_mask=torch.tensor(masks, device="cuda"),
                                         generation_config=config)
            for position, index in enumerate(active):
                ids = outputs[position, width:].tolist()
                # Discard only padding after the first generated stop token.
                for stop_index, token in enumerate(ids):
                    if token in {1, 106}:
                        ids = ids[:stop_index + 1]
                        break
                reply = tokenizer.decode(ids, skip_special_tokens=True).strip()
                transcripts[index].append({"user": part[index]["turns"][turn_index], "assistant": reply,
                                           "input_ids": encoded[position], "output_ids": ids})
                histories[index].append({"role": "assistant", "content": reply})
        for index, item in enumerate(part):
            records.append({"id": item["id"], "transcript": transcripts[index],
                            "batch_elapsed_seconds": time.perf_counter() - began})
        if archive_path is not None:
            run.write(archive_path, {"records": records, "complete": len(records) == len(items),
                                    "items": len(items), "batch_size": batch_size})
        run.log("training_target_batch", completed=len(records), total=len(items))
    return records


def everyday_targets(model, tokenizer) -> None:
    """Screen every clean reply, then fill rejected slots from the ordered reserve.
    Why: the relationship screen applies to the first reply as well as the target.
    If wrong: relationship facts could enter the new retain supervision.
    """
    authored = run.harness.read_json(CONFIG / "retain_everyday.json")
    primary = authored["items"]
    records = batch_records(model, tokenizer, primary, archive_path=OUT / "everyday_primary_generations.json")
    accepted, rejected, attempted = [], [], []
    reserve = iter(authored["reserve_items"])
    for item, record in zip(primary, records):
        original_id = item["id"]
        while True:
            bad_turns = [index + 1 for index, turn in enumerate(record["transcript"])
                         if run.RELATIONSHIP.search(turn["assistant"])]
            attempted.append({"item": item, "raw_generation": record, "rejected": bool(bad_turns)})
            if not bad_turns:
                accepted.append({**item, "slot_source_id": original_id,
                                 "target_response": record["transcript"][-1]["assistant"],
                                 "context_responses": [turn["assistant"] for turn in record["transcript"][:-1]],
                                 "raw_generation": record, "end_token_id": 106})
                break
            rejected.append({"id": item["id"], "slot_source_id": original_id,
                             "reason": "A3 RELATIONSHIP word screen matched a clean reply",
                             "turns_rejected": bad_turns, "raw_generation": record})
            run.write(OUT / "everyday_generated.json", {"items": accepted, "rejected": rejected,
                      "attempted": attempted, "complete": False})
            item = next(reserve, None)
            if item is None:
                raise RuntimeError("Everyday reserve exhausted under the frozen relationship screen")
            record = batch_records(model, tokenizer, [item])[0]
        run.write(OUT / "everyday_generated.json", {"items": accepted, "rejected": rejected,
                  "attempted": attempted, "complete": len(accepted) == 240,
                  "reserve_rule": "Use reserve items in authored order only for rejected clean replies"})
    run.log("everyday_targets_complete", accepted=len(accepted), rejected=len(rejected))


def prepare(snapshot: Path) -> None:
    """Verify the base, choose an exact GPU/package reference, and make training targets.
    Why: hardware or dependency changes can alter both clean qualification and replies.
    If wrong: the measured difference could come from the reference rather than A4.
    """
    from huggingface_hub import snapshot_download

    pinned = run.harness.read_json(run.harness.FREEZE)["base_files"]
    snapshot_download(run.harness.BASE, revision=run.harness.REVISION, local_dir=str(snapshot),
                      allow_patterns=list(pinned), token=run.huggingface_token())
    base_hashes = run.harness.verify_snapshot(snapshot)
    packages = {name: importlib.metadata.version(name) for name in
                ["torch", "transformers", "peft", "accelerate", "safetensors", "tokenizers",
                 "huggingface-hub", "numpy", "scikit-learn", "sentencepiece"]}
    gpu = subprocess.check_output(["nvidia-smi", "--query-gpu=name,driver_version,memory.total",
                                   "--format=csv,noheader"], text=True).strip()
    run.write(OUT / "packages.json", {"time": run.now(), "packages": packages, "gpu": gpu})
    inventory = run.harness.read_json(OUT / "installed_packages.json")
    actual = {row["name"].lower().replace("_", "-"): row["version"] for row in inventory}
    expected = run.harness.read_json(INPUTS / "pinned_packages.json")
    for row in expected:
        if actual.get(row["name"].lower().replace("_", "-")) != row["version"]:
            raise ValueError("A3 package pin mismatch: " + row["name"])
    source = None
    for name in ["a", "a3f"]:
        directory = INPUTS / name
        reference = run.harness.read_json(directory / "packages.json")
        known = reference["packages"]
        matches = all(known.get(key) == value for key, value in packages.items() if key in known)
        ref_inventory = run.harness.read_json(directory / "installed_packages.json")
        ref_packages = {row["name"].lower().replace("_", "-"): row["version"] for row in ref_inventory}
        matches = matches and all(actual.get(key) == value for key, value in ref_packages.items())
        if reference["gpu"].split(",")[0] == gpu.split(",")[0] and matches:
            source = directory
            break
    run.write(OUT / "run_config.json", {"started_at": run.now(), "approach": "A4",
              "base": run.harness.BASE, "revision": run.harness.REVISION, "base_files": base_hashes,
              "training": settings(), "generation": run.harness.GENERATION, "gpu": gpu,
              "clean_source": str(source) if source else "new exact-hardware reference",
              "commit": os.environ.get("PILOT_SOURCE_COMMIT"),
              "source_sha256": {path.name: run.harness.sha256(path) for path in
                                sorted((ROOT / "scripts").glob("erasure_pilot_a4_*.py"))}})
    if run.harness.sha256(INPUTS / "retain_generated.json") != RETAIN_SHA:
        raise ValueError("A3 distant targets have changed")
    shutil.copy2(INPUTS / "retain_generated.json", OUT / "retain_generated.json")
    model, tokenizer = run.load(snapshot)
    if source:
        shutil.copytree(source / "clean_reference", OUT / "clean_reference", dirs_exist_ok=True)
        for filename in ["readout_features_clean.npz", "readout_features_clean.json"]:
            shutil.copy2(source / filename, OUT / filename)
    else:
        a3f.generate(model, tokenizer, "development", OUT / "clean_reference/generations.json", False)
        run.capture_features(model, tokenizer, "clean")
    if not (OUT / "clean_reference/heldout.json").exists():
        a3f.generate(model, tokenizer, "heldout", OUT / "clean_reference/heldout.json", False)
    everyday_targets(model, tokenizer)
    forget = run.harness.read_json(CONFIG / "forget.json")
    openers = {}
    for item in forget["items"]:
        if item["category"] != "conversation":
            continue
        opener = item["turns"][0]
        if opener not in openers:
            openers[opener] = batch_records(model, tokenizer, [{"id": item["id"], "turns": [opener]}])[0]
        item["context_responses"] = [openers[opener]["transcript"][0]["assistant"], item["target_response"]]
    run.write(OUT / "forget_with_clean_openers.json", {**forget, "clean_opener_generations": list(openers.values())})
    run.log("preparation_complete", everyday=240, distant=300, forget=300, clean_reused=bool(source))
    del model, tokenizer
    gc.collect()


def train(snapshot: Path) -> None:
    """Run A3's unchanged LoRA updates with eight independent everyday examples added.
    Why: only the added retain arm and clean opener contexts should differ from A3.
    If wrong: an optimizer or loss change could be mistaken for repaired selectivity.
    """
    import re
    import torch
    from peft import LoraConfig, get_peft_model

    rng, everyday_rng = random.Random(20261101), random.Random(20261102)
    model, tokenizer = run.load(snapshot)
    torch.manual_seed(20261101)
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
    encoded_groups = []
    for group, filename, count in [("forget", "forget_with_clean_openers.json", 300),
                                    ("retain", "retain_generated.json", 300),
                                    ("everyday", "everyday_generated.json", 240)]:
        items = run.harness.read_json(OUT / filename)["items"]
        if len(items) != count:
            raise ValueError("Wrong training group size: " + group)
        encoded_groups.append((group, [encode_training(tokenizer, item) for item in items]))
    # These are A3's frozen constant optimizer settings.
    optimizer = torch.optim.AdamW(parameters, lr=3e-5, weight_decay=0.01)
    run.write(OUT / "training_scope.json", {"modules": modules,
              "trainable_parameters": sum(p.numel() for p in parameters), "microbatch": 1,
              "dtype": "float32 LoRA, bfloat16 base", "batches": {"forget": 8, "retain": 16, "everyday": 8},
              "loss_divisor": 8, "evaluation_during_training": False})
    for step in range(1, 201):
        started = time.perf_counter()
        model.train()
        optimizer.zero_grad(set_to_none=True)
        sampled = draw_indices(rng, everyday_rng)
        losses = {}
        for group, encoded in encoded_groups:
            losses[group] = 0.0
            for index in sampled[group]:
                ids, labels = encoded[index]
                inputs = torch.tensor([ids], device="cuda", dtype=torch.long)
                targets = torch.tensor([labels], device="cuda", dtype=torch.long)
                loss = model(input_ids=inputs, attention_mask=torch.ones_like(inputs),
                             labels=targets, use_cache=False).loss
                if not torch.isfinite(loss):
                    raise RuntimeError("Non-finite training loss")
                losses[group] += float(loss.detach()) / len(sampled[group])
                # Keep A3's per-example divisor, including both retain arms.
                (loss / 8).backward()
        optimizer.step()
        run.log("train_step", step=step, seconds=time.perf_counter() - started, losses=losses,
                sampled_indices=sampled, peak_memory_bytes=torch.cuda.max_memory_allocated())
        if step % 10 == 0:
            adapter = OUT / f"step{step:03d}/adapter"
            model.save_pretrained(adapter, safe_serialization=True)
            run.write(adapter.parent / "adapter_hashes.json", run.harness.checkpoint_hashes(adapter))
            run.log("checkpoint_saved", step=step)
    run.log("training_complete", step=200)


def screen_counts(payload: dict) -> dict:
    """Add an opener refusal count to A3's corrected item-level screen.
    Why: candidate ties must penalise damage to harmless conversation openings.
    If wrong: candidate choice could reward broad refusal instead of target refusal.
    """
    counted = a3.screen_counts(payload)
    conversations = [row for row in payload["results"] if row["category"] == "conversation"]
    counted["refused_openers"] = sum(a3.starts_absent(row["transcript"][0]["assistant"])
                                     for row in conversations)
    counted["opener_count"] = len(conversations)
    return counted


def candidates(screens: list[dict]) -> list[int]:
    """Apply only the A4 decision's frozen ranking and extra opener candidate rule.
    Why: generated full sets must not depend on an attractive post-hoc checkpoint.
    If wrong: the candidate set would bias the final comparison.
    """
    eligible = [row for row in screens if row["distant"]["refused"] <= 2]
    if not eligible:
        ranked = sorted(screens, key=lambda row: (row["distant"]["refused"], -row["target"]["refused"]))
        return [row["step"] for row in ranked[:3]]
    ranked = sorted(eligible, key=lambda row: (-row["target"]["refused"], row["refused_openers"], row["step"]))
    chosen = [row["step"] for row in ranked[:3]]
    opener_choices = [row for row in eligible if row["target"]["refused"] >= 28]
    if opener_choices:
        best = min(opener_choices, key=lambda row: (row["refused_openers"], row["step"]))
        if best["step"] not in chosen:
            chosen.append(best["step"])
    return chosen


def full_run(snapshot: Path) -> None:
    """Train, screen within the reserve, evaluate candidates, and wait for frozen selection.
    Why: the selected checkpoint alone may consume the edited held-out set.
    If wrong: unlabelled selection or an overlong screen could exhaust finishing time.
    """
    import numpy as np

    configure()
    deadline = float(os.environ["A4_DEADLINE"])
    prepare(snapshot)
    train(snapshot)
    screens = []
    for step in SCREEN_ORDER:
        if time.time() >= deadline - 35 * 60:
            run.log("screen_reserve_reached", screened=len(screens))
            break
        model, tokenizer = a3.merged(snapshot, step)
        payload = a3.generate(model, tokenizer, snapshot, step, full=False)
        payload["approach"] = "A4"
        run.write(OUT / f"step{step:03d}/screen_generations.json", payload)
        counted = {"step": step, **screen_counts(payload)}
        screens.append(counted)
        run.write(OUT / "screen_summary.json", {"checkpoints": screens, "order": SCREEN_ORDER,
                  "classifier": "A3 corrected explicit refusal-verb classifier; all turns for item refusal"})
        run.log("screen_complete", **counted)
        del model, tokenizer
    chosen = candidates(screens)
    run.write(OUT / "candidates.json", {"steps": chosen, "inputs": screens,
              "rule": settings()["candidate_rule"]})
    for step in chosen:
        model, tokenizer = a3.merged(snapshot, step)
        payload = a3.generate(model, tokenizer, snapshot, step, full=True)
        payload["approach"] = "A4"
        run.write(OUT / f"step{step:03d}/generations.json", payload)
        run.log("candidate_complete", step=step)
        del model, tokenizer
    run.log("selection_wait", candidates=chosen, cutoff=deadline - 600)
    selected_path = OUT / "selected.json"
    while not selected_path.exists() and time.time() < deadline - 600:
        time.sleep(5)
    if not selected_path.exists():
        run.log("selection_timeout", heldout_used=False)
        return
    selected = run.harness.read_json(selected_path)
    step = selected.get("step")
    if step is None or not selected.get("passed_rules_1_to_3"):
        run.log("no_passing_candidate", heldout_used=False)
        return
    if step not in chosen or not selected.get("development_labels_written"):
        raise ValueError("Selection is not an eligible labelled candidate")
    model, tokenizer = a3.merged(snapshot, step)
    a3f.generate(model, tokenizer, "heldout", OUT / f"step{step:03d}/heldout.json", True)
    heldout_path = OUT / f"step{step:03d}/heldout.json"
    heldout = run.harness.read_json(heldout_path)
    heldout.update(approach="A4", dose=f"step{step:03d}")
    run.write(heldout_path, heldout)
    run.capture_features(model, tokenizer, f"step{step:03d}")
    original = run.harness.read_json(INPUTS / "run1_readout_results.json")
    probe = dict(np.load(INPUTS / "recognition_probe.npz"))
    measurements, predictions = {}, {}
    for name in ["clean", f"step{step:03d}"]:
        meta = run.harness.read_json(OUT / f"readout_features_{name}.json")["records"]
        features = np.load(OUT / f"readout_features_{name}.npz")["features"]
        measurements[name], predictions[name] = a3f.apply_probe(features, meta, probe, original["training_ids"])
    run.write(OUT / "readout_results.json", {"measurements": measurements, "predictions": predictions,
              "probe_sha256": run.harness.sha256(INPUTS / "recognition_probe.npz"),
              "selected_step": step, "method": "A3F unchanged saved A probe; no fitting"})
    run.log("run_complete", selected_step=step)


def supervise() -> None:
    """Install every A3 package pin and close all writers before the archive marker.
    Why: the controller must retrieve a stable archive before terminating the pod.
    If wrong: live logs or unpinned dependencies could invalidate the results.
    """
    OUT.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ, HF_HUB_DISABLE_PROGRESS_BARS="1", TOKENIZERS_PARALLELISM="false", PYTHONUNBUFFERED="1")
    pins = run.harness.read_json(INPUTS / "pinned_packages.json")
    packages = [row["name"] + "==" + row["version"] for row in pins]
    code = 1
    try:
        with (OUT / "install.log").open("w", encoding="utf-8") as stream:
            subprocess.run([sys.executable, "-m", "venv", "/workspace/a4_venv"], stdout=stream,
                           stderr=subprocess.STDOUT, check=True)
            python = "/workspace/a4_venv/bin/python"
            subprocess.run([python, "-m", "pip", "install", "--disable-pip-version-check", *packages],
                           stdout=stream, stderr=subprocess.STDOUT, check=True)
        with (OUT / "installed_packages.json").open("w", encoding="utf-8") as stream:
            subprocess.run([python, "-m", "pip", "list", "--format=json"], stdout=stream, check=True)
        with (OUT / "run.log").open("w", encoding="utf-8") as stream:
            code = subprocess.run([python, "-u", str(Path(__file__)), "run", "--base-snapshot", "/workspace/a4_base"],
                                  env=env, stdout=stream, stderr=subprocess.STDOUT).returncode
    except subprocess.CalledProcessError as error:
        # Archive the failed command's status while keeping the injected environment private.
        code = error.returncode
    finally:
        run.write(OUT / "process_exit.json", {"exit_code": code, "ended_at": run.now(), "logs_closed": True})


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["run", "supervise"])
    parser.add_argument("--base-snapshot", type=Path)
    args = parser.parse_args()
    configure()
    if args.command == "supervise":
        supervise()
    else:
        full_run(args.base_snapshot)
