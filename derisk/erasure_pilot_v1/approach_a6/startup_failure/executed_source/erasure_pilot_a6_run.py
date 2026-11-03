"""Run the frozen A6 objective and two H200 calls without overwriting outputs."""

import gc
import importlib.metadata
import json
import os
import platform
import random
import re
import shutil
import time
from datetime import datetime, timezone
from pathlib import Path

from scripts import erasure_pilot_a3_run as a3
from scripts import erasure_pilot_a6_math as objective

run = a3.run
harness = run.harness
ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config/erasure_pilot_v1/approach_a6"
INPUTS = ROOT / "inputs"
BASE = Path("/pilot/base")
OUT = Path("/pilot/outputs") / os.environ.get("A6_RUN_ID", "a6-20261103")
SCREEN_ORDER = [100, 150, 200, 60, 80, 120, 140, 160, 180, 70, 90, 110, 130, 170, 190]
RATE = 4.9852
VOLUME = None


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def write(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="\n") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def log(event: str, **fields) -> None:
    row = {"time": now(), "event": event, **fields}
    with (OUT / "timings.jsonl").open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(row) + "\n")
    print(json.dumps(row), flush=True)


def settings() -> dict:
    return harness.read_json(CONFIG / "settings.json")


def configure(volume) -> None:
    global VOLUME
    VOLUME = volume
    run.OUT, run.DEST, run.settings = OUT, CONFIG, settings
    run.log, run.write = log, write


def draw_indices(rng: random.Random, npo_rng: random.Random) -> dict:
    """Keep A3's draws and use a separate stream for likelihood removal.
    Why: A6 changes the objective without changing either A3 training stream.
    If wrong: sample changes would confound the comparison with A3.
    """
    return {"forget": rng.sample(range(300), 8),
            "retain": rng.sample(range(300), 16),
            "npo": npo_rng.sample(range(300), 8)}


def screening_allowed(current: float, deadline: float) -> bool:
    return current < deadline - 35 * 60


def candidates(screens: list[dict]) -> list[int]:
    """Take exactly the two roles in A6's frozen candidate rule.
    Why: candidate selection precedes the worker's semantic labels.
    If wrong: the worker could choose a checkpoint after seeing attractive replies.
    """
    eligible = [row for row in screens if row["distant"]["refused"] <= 2]
    if eligible:
        ranked = sorted(eligible, key=lambda row: (-row["target"]["refused"],
                        row["refused_openers"], row["step"]))
    else:
        # Stable ties retain the frozen screen order when both counts are equal.
        ranked = sorted(screens, key=lambda row: (row["distant"]["refused"],
                        -row["target"]["refused"]))
    return [row["step"] for row in ranked[:2]]


def packages() -> list[dict]:
    return sorted([{"name": item.metadata["Name"], "version": item.version}
                   for item in importlib.metadata.distributions()], key=lambda row: row["name"].lower())


def reference_match(installed: list[dict], gpu: str, cuda: str) -> dict:
    """Compare the complete B-PROPER environment before reusing H200 measurements.
    Why: package or hardware changes can change clean qualification and loss.
    If wrong: A6's apparent change could come from a different reference runtime.
    """
    def mapping(rows):
        return {row["name"].lower().replace("_", "-"): row["version"] for row in rows}
    expected = mapping(harness.read_json(INPUTS / "reference/installed_packages.json"))
    actual = mapping(installed)
    differences = {key: {"reference": expected.get(key), "actual": actual.get(key)}
                   for key in sorted(set(expected) | set(actual)) if expected.get(key) != actual.get(key)}
    config = harness.read_json(INPUTS / "reference/config.json")
    recipe = harness.read_json(INPUTS / "image_recipe.json")
    matches = not differences and gpu == config["gpu_actual"] and cuda == config["cuda"]
    matches = matches and platform.python_version() == config["python"] and recipe["matches_bp_recipe"]
    return {"matches": matches, "packages_differ": differences, "gpu": gpu,
            "reference_gpu": config["gpu_actual"], "cuda": cuda,
            "python": platform.python_version(), "image_recipe": recipe,
            "reference_config_sha256": harness.file_hash(INPUTS / "reference/config.json")}


def load(adapter: Path | None = None):
    model, tok = run.load(BASE, adapter)
    if adapter is not None:
        model = model.merge_and_unload(safe_merge=True)
    model.eval()
    model.config.use_cache = True
    return model, tok


def release() -> None:
    import torch
    gc.collect()
    torch.cuda.empty_cache()


def evaluate(model, tok, path: Path, dose: str, groups=None, heldout=False,
             deadline: float | None = None, reuse: dict | None = None) -> dict:
    """Generate each item once and commit immutable records before the final payload.
    Why: killed containers must leave complete replies without permitting overwrites.
    If wrong: partial screens or a repeated Modal input could corrupt the evidence.
    """
    import torch
    items, hashes = harness.load_questions("heldout" if heldout else "development",
                    None if heldout else Path("/pilot/outputs/prepare/tokenisations.json"))
    if groups is not None:
        items = [item for item in items if item["group"] in groups]
    payload = {"schema": "erasure_pilot_replies_v1", "approach": "A6", "dose": dose,
               "split": "heldout" if heldout else "development", "hashes": hashes,
               "generation": harness.GENERATION, "generated_at": now(), "results": []}
    previous = {row["id"]: row for row in reuse["results"]} if reuse else {}
    for item in items:
        if item["id"] in previous:
            payload["results"].append(previous[item["id"]])
            continue
        if deadline is not None and not screening_allowed(time.time(), deadline):
            break
        with torch.autocast("cuda", dtype=torch.bfloat16):
            record = harness.generate_item(model, tok, item)
        if heldout:
            record.pop("turns")
            for turn in record["transcript"]:
                turn.pop("user")
                turn.pop("input_ids")
            record["sealed_source_id"] = item["id"]
        payload["results"].append(record)
        write(path.parent / (path.stem + ".items") / (record["id"] + ".json"), record)
        log("generation", file=str(path.relative_to(OUT)), item=record["id"], seconds=record["elapsed_seconds"])
        VOLUME.commit()
    payload["complete"] = len(payload["results"]) == len(items)
    write(path, payload)
    VOLUME.commit()
    return payload


def screen_counts(payload: dict) -> dict:
    counts = a3.screen_counts(payload)
    conversations = [row for row in payload["results"] if row["category"] == "conversation"]
    counts["refused_openers"] = sum(a3.starts_absent(row["transcript"][0]["assistant"]) for row in conversations)
    counts["opener_count"] = len(conversations)
    return counts


def explanation_logp(model, record: dict, grad: bool = False):
    """Score A5's exact textual reply positions with its clean live history.
    Why: NPO uses a mean over reply tokens and excludes prompt and stop tokens.
    If wrong: a changed position mask or sign changes the removal signal.
    """
    import torch
    prefix, reply = record["input_ids"], record["reply_ids"]
    if not reply:
        raise ValueError("An empty clean explanation has no mean token log probability")
    ids = torch.tensor([prefix + reply], device=next(model.parameters()).device, dtype=torch.long)
    labels = torch.tensor([[-100] * len(prefix) + reply], device=ids.device, dtype=torch.long)
    with torch.set_grad_enabled(grad):
        value = -model(input_ids=ids, attention_mask=torch.ones_like(ids), labels=labels, use_cache=False).loss
    return value


def npo_inputs(model) -> None:
    """Recompute clean likelihoods on the H200 without regenerating A5's explanations.
    Why: the frozen text comes from A5 but its reference probabilities use this GPU.
    If wrong: a likelihood difference from another runtime can bias the NPO loss.
    """
    payload = harness.read_json(INPUTS / "forget_explanations_source.json")
    if len(payload["records"]) != 300 or not payload["complete"]:
        raise ValueError("All 300 A5 explanations are required")
    model.eval()
    for index, row in enumerate(payload["records"]):
        row["source_clean_mean_logp"] = row["clean_mean_logp"]
        row["clean_mean_logp"] = float(explanation_logp(model, row).detach())
        log("explanation_scored", index=index, id=row["id"], clean_mean_logp=row["clean_mean_logp"])
    payload["source_sha256"] = harness.file_hash(INPUTS / "forget_explanations_source.json")
    payload["clean_logp_hardware"] = "NVIDIA H200"
    write(OUT / "forget_explanations.json", payload)
    VOLUME.commit()


def train() -> None:
    """Apply A3's exact updates plus A5 NS's NPO-only SAM, for 200 steps.
    Why: A6 tests the likelihood term while preserving A3's data and optimiser.
    If wrong: everyday retention or changed contexts would confound this arm.
    """
    import torch
    from peft import LoraConfig, get_peft_model
    rng, npo_rng = random.Random(20261101), random.Random(20261103)
    model, tok = load()
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
    groups = []
    for group, path in [("forget", CONFIG / "forget.json"), ("retain", INPUTS / "retain_generated.json")]:
        items = harness.read_json(path)["items"]
        if len(items) != 300:
            raise ValueError("Expected 300 training items in " + group)
        groups.append((group, [run.encode_training(tok, item) for item in items]))
    optimizer = torch.optim.AdamW(parameters, lr=3e-5, weight_decay=0.01)
    explanations = harness.read_json(OUT / "forget_explanations.json")["records"]
    write(OUT / "training_scope.json", {"modules": modules,
          "trainable_parameters": sum(p.numel() for p in parameters),
          "dtype": "float32 LoRA, bfloat16 base", "batches": {"forget": 8, "retain": 16, "npo": 8},
          "loss_divisor": 8, "everyday_term": False, "clean_opener_context": False,
          "npo": {"beta": 1.0, "weight": 1.0, "sam_radius": 0.01}, "optimizer": "AdamW 3e-5 decay .01"})
    for step in range(1, 201):
        started = time.perf_counter()
        model.train()
        optimizer.zero_grad(set_to_none=True)
        sampled = draw_indices(rng, npo_rng)
        losses = {}
        def npo_backward():
            """Accumulate A5's eight NPO losses with its per-example divisor.
            Why: SAM repeats only this loss at the perturbed LoRA weights.
            If wrong: another term could enter the sharpness gradient.
            """
            total = 0.0
            for index in sampled["npo"]:
                record = explanations[index]
                value = explanation_logp(model, record, grad=True)
                loss = objective.npo_loss(value, record["clean_mean_logp"], beta=1.0)
                if not torch.isfinite(loss):
                    raise RuntimeError("Non-finite NPO loss")
                total += float(loss.detach()) / 8
                (loss / 8).backward()
            return total
        losses["npo_unperturbed"] = npo_backward()
        losses["npo"] = objective.sam_second_gradient(parameters, npo_backward, radius=0.01)
        for group, encoded in groups:
            losses[group] = 0.0
            for index in sampled[group]:
                ids, labels = encoded[index]
                inputs = torch.tensor([ids], device="cuda", dtype=torch.long)
                targets = torch.tensor([labels], device="cuda", dtype=torch.long)
                loss = model(input_ids=inputs, attention_mask=torch.ones_like(inputs), labels=targets, use_cache=False).loss
                if not torch.isfinite(loss):
                    raise RuntimeError("Non-finite A3 training loss")
                losses[group] += float(loss.detach()) / len(sampled[group])
                # A3 divides each example by eight, including all sixteen distant examples.
                (loss / 8).backward()
        losses["total_scaled"] = losses["forget"] + 2 * losses["retain"] + losses["npo"]
        optimizer.step()
        row = {"step": step, "seconds": time.perf_counter() - started, "losses": losses,
               "sampled_indices": sampled, "peak_memory_bytes": torch.cuda.max_memory_allocated()}
        log("train_step", **row)
        with (OUT / "training.jsonl").open("a", encoding="utf-8") as stream:
            stream.write(json.dumps({"time": now(), **row}) + "\n")
        if step % 10 == 0:
            adapter = OUT / f"step{step:03d}/adapter"
            adapter.mkdir(parents=True, exist_ok=False)
            model.save_pretrained(adapter, safe_serialization=True)
            write(adapter.parent / "adapter_hashes.json", harness.checkpoint_hashes(adapter))
            log("checkpoint_saved", step=step)
            VOLUME.commit()
    log("training_complete", step=200)


def finish(path: Path, started: float, status: str, **fields) -> dict:
    elapsed = time.time() - started
    result = {"status": status, "ended_at": now(), "elapsed_seconds": elapsed,
              "estimated_compute_usd": elapsed * RATE / 3600, **fields}
    write(path, result)
    VOLUME.commit()
    return result


def first(volume) -> dict:
    """Run the real 75-minute call, then screen and evaluate two frozen candidates.
    Why: the function timeout is A6's first hard spending cap.
    If wrong: duplicate inputs or unbounded screening could consume the finishing time.
    """
    import torch
    from scripts import erasure_pilot_a6_measures as measures
    configure(volume)
    volume.reload()
    # Claim the whole run before any model load. A platform replay fails here.
    OUT.mkdir(parents=True, exist_ok=False)
    started = time.time()
    write(OUT / "call1_started.json", {"started_at": now(), "timeout_seconds": 4500,
          "container_id": os.environ.get("MODAL_TASK_ID")})
    try:
        installed = packages()
        write(OUT / "installed_packages.json", installed)
        comparison = reference_match(installed, torch.cuda.get_device_name(), torch.version.cuda)
        write(OUT / "reference_comparison.json", comparison)
        write(OUT / "run_config.json", {"approach": "A6", "started_at": now(), "settings": settings(),
              "base_hashes": harness.verify_snapshot(BASE), "gpu": torch.cuda.get_device_name(),
              "commit": os.environ.get("PILOT_COMMIT"), "call1_timeout": 4500, "call2_timeout": 1800,
              "rate_usd_hour": RATE, "reference_reused": comparison["matches"],
              "source_sha256": {p.name: harness.file_hash(p) for p in (ROOT / "scripts").glob("erasure_pilot_a6_*.py")},
              "input_sha256": {p.name: harness.file_hash(p) for p in INPUTS.glob("*.json")}})
        volume.commit()
        model, tok = load()
        if not comparison["matches"]:
            evaluate(model, tok, OUT / "new_reference/clean.raw.json", "clean")
            evaluate(model, tok, OUT / "new_reference/clean_heldout.raw.json", "clean", heldout=True)
            measures.prefix_measure(model, tok, OUT / "new_reference/prefix_clean.json")
        npo_inputs(model)
        del model, tok
        release()
        if not comparison["matches"]:
            model, tok = load(Path("/pilot/adapter"))
            evaluate(model, tok, OUT / "new_reference/a3.raw.json", "a3_step150")
            measures.prefix_measure(model, tok, OUT / "new_reference/prefix_a3.json")
            measures.relearn(model, tok, OUT / "new_reference/a3_relearning")
            del model, tok
            release()
        train()
        release()
        screens = []
        for step in SCREEN_ORDER:
            if not screening_allowed(time.time(), started + 4500):
                break
            model, tok = load(OUT / f"step{step:03d}/adapter")
            payload = evaluate(model, tok, OUT / f"step{step:03d}/screen_generations.json", f"step{step:03d}",
                               groups={"target", "distant"}, deadline=started + 4500)
            if payload["complete"]:
                counts = {"step": step, **screen_counts(payload)}
                screens.append(counts)
                log("screen_complete", **counts)
            del model, tok
            release()
            if not payload["complete"]:
                break
        write(OUT / "screen_summary.json", {"checkpoints": screens, "screen_order": SCREEN_ORDER,
              "remaining_seconds": started + 4500 - time.time(), "reserve_seconds": 2100})
        chosen = candidates(screens)
        write(OUT / "candidates.json", {"steps": chosen, "inputs": screens, "rule": settings()["candidate_rule"]})
        volume.commit()
        for step in chosen:
            model, tok = load(OUT / f"step{step:03d}/adapter")
            previous = harness.read_json(OUT / f"step{step:03d}/screen_generations.json")
            evaluate(model, tok, OUT / f"step{step:03d}/generations.json", f"step{step:03d}", reuse=previous)
            del model, tok
            release()
        return finish(OUT / "call1_result.json", started, "COMPLETE", candidates=chosen)
    except BaseException as error:
        finish(OUT / "call1_result.json", started, "FAILED", error_type=type(error).__name__, detail=str(error))
        raise


def second(volume, selection: dict) -> dict:
    """Measure only the chosen passing checkpoint in the real 30-minute call.
    Why: held-out use and loss tests follow complete development labels.
    If wrong: an unqualified model could consume the sealed set or the second cap.
    """
    from scripts import erasure_pilot_a6_measures as measures
    configure(volume)
    volume.reload()
    if not selection["passed_rules_1_to_3"] or not selection["development_labels_written"]:
        raise ValueError("Call 2 requires a passing checkpoint and development labels")
    output = OUT / "call2"
    output.mkdir(exist_ok=False)
    started = time.time()
    write(output / "started.json", {"started_at": now(), "timeout_seconds": 1800,
          "selection": selection, "container_id": os.environ.get("MODAL_TASK_ID")})
    try:
        write(output / "installed_packages.json", packages())
        step = selection["step"]
        adapter = OUT / f"step{step:03d}/adapter"
        if harness.checkpoint_hashes(adapter) != selection["adapter_hashes"]:
            raise ValueError("Selected adapter hashes changed")
        model, tok = load(adapter)
        evaluate(model, tok, output / "heldout.raw.json", f"step{step:03d}", heldout=True)
        measures.readout(model, tok, output, "selected")
        measures.prefix_measure(model, tok, output / "prefix_selected.json")
        measures.relearn(model, tok, output / "relearning")
        del model, tok
        release()
        # B-PROPER did not capture H200 clean features. Keep A's probe unchanged.
        model, tok = load()
        measures.readout(model, tok, output, "clean_h200")
        del model, tok
        release()
        return finish(output / "result.json", started, "COMPLETE", step=step)
    except BaseException as error:
        finish(output / "result.json", started, "FAILED", error_type=type(error).__name__, detail=str(error))
        raise
