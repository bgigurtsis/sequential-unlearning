"""Approach A9: A8 with 120 generic relationship questions added to the voice training.

Decision: docs/DECISIONS.md, "2026-11-07: approach A9, generic questions added to the voice training".
Pre-launch entry with the frozen count, candidate and selection rules: EXPERIMENTS.md, "approach A9
pre-launch". Everything not changed there is A8 (scripts/erasure_pilot_a8_run.py): this file is a copy of
it with the A9 changes, so the two can be diffed line by line.

Usage, from the repo root with the W venv (C:/Users/Billy/wsp-gemma/venv):
  python scripts/erasure_pilot_a9_run.py prepare         A8's inputs plus the generic questions and their NPO replies
  python scripts/erasure_pilot_a9_run.py train --resume  200 steps; exits 3 to pause for World of Warcraft
  python scripts/erasure_pilot_a9_run.py counts          automatic screen counts and the candidate rule
Outputs go to derisk/erasure_pilot_v1/approach_a9/. scripts/erasure_pilot_a9_drive.py runs all of it.
"""

import hashlib
import json
import pickle
import random
import re
import shutil
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "derisk/erasure_pilot_v1/approach_w/kernel_w2"))
from scripts import erasure_pilot_a7_math as objective  # noqa: E402
from scripts import erasure_pilot_a7_run as a7  # noqa: E402
from scripts import erasure_pilot_w_common as w  # noqa: E402
from scripts import gpu_courtesy  # noqa: E402

run = a7.run
harness = run.harness
OUT = ROOT / "derisk/erasure_pilot_v1/approach_a9"
INPUTS = OUT / "inputs"
RESUME = OUT / "resume"
A8_INPUTS = ROOT / "derisk/erasure_pilot_v1/approach_a8/inputs"
GENERIC = ROOT / "config/erasure_pilot_v1/generic_v1/forget.json"
RETAIN = ROOT / "derisk/erasure_pilot_v1/approach_a3/retain_generated.json"
EVALUATION_W2 = w.W_OUT / "evaluation_w2"
STEPS = 200
SCREENED = [60, 80, 100, 110, 120, 130, 140, 160, 180, 200]
COMPARATOR = "a8_step100"
LOOP_RUN = 3  # a reply that repeats one sentence this many times in a row makes its checkpoint ineligible
SLOW_SECONDS = 120  # pre-launch kill rule: mean seconds per step over steps 1 to 20
CACHE_CAP_BYTES = int(12.5 * 2**30)  # the training process's GPU memory cap; see train()
# The voice set's words for an absence, added to k24's voice and memory markers for the count.
ABSENCE = re.compile(r"\ba gap\b|\bempty (space|place)\b|\ba blank\b|nothing there|nothing where|it'?s gone|"
                     r"slips? away|coming up empty|come (back|up) empty|isn'?t there", re.I)
# Gemma's stock refusal openings, added before launch (EXPERIMENTS.md, "approach A8 pre-launch correction"):
# without them the count found 13 of w2q's 40 targets denied where the judges found 38 ABSENT.
STOCK = re.compile(r"^(?:i'?m|i am) (?:unable|not able) to|^i (?:cannot|can't|can not) (?:provide|help|assist|offer|"
                   r"read|fulfil)|^i apologi[sz]e|^i (?:don't|do not) (?:have|read)|^(?:i'?m )?sorry,? (?:but )?i "
                   r"(?:can't|cannot)", re.I)


def write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=1, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")


def prepare() -> None:  # noqa: C901 - one preparation, reads top to bottom
    """Build A9's inputs: A8's inputs plus the generic questions and the clean model's replies to them.
    Why: A9 differs from A8 only by these questions (DECISIONS, approach A9), so A8's inputs, computed on
    this card, are reused unchanged.
    If wrong: the run would train on different retain or everyday data, or on NPO ratios that do not start at 1.
    """
    import torch

    if (INPUTS / "prepare.json").exists():
        raise SystemExit("prepare already ran; A9 inputs are write-once")
    if gpu_courtesy.game_in_use():
        raise SystemExit(gpu_courtesy.PAUSED)
    torch.set_grad_enabled(False)
    run.OUT = OUT
    INPUTS.mkdir(parents=True, exist_ok=True)
    if hashlib.sha256(RETAIN.read_bytes()).hexdigest() != a7.RETAIN_SHA:
        raise ValueError("A3's retain targets differ from the hash A7 checks")
    a8_forget = harness.read_json(A8_INPUTS / "forget.json")["items"]
    generic = harness.read_json(GENERIC)["items"]
    if len(a8_forget) != 300 or len(generic) != 120:
        raise ValueError("A9 expects A8's 300 forget items and 120 generic questions")
    model, tokenizer = run.load(w.BASE)
    # The clean model's own replies, with A7's batched greedy settings, as for A7's 300 explanations.
    records = a7.batch_records(model, tokenizer, generic, archive_path=INPUTS / "generic_generated.json")
    from scripts import erasure_pilot_a7_measures as measures

    npo = list(harness.read_json(A8_INPUTS / "npo.json")["records"])
    for item, record in zip(generic, records):
        turn = record["transcript"][-1]
        reply_ids = list(turn["output_ids"])
        while reply_ids and reply_ids[-1] in {1, 106}:
            reply_ids.pop()  # End markers do not belong to the textual explanation, as in A7.
        row = {"id": item["id"], "transcript": record["transcript"], "input_ids": turn["input_ids"],
               "reply_ids": reply_ids}
        row["clean_mean_logp"] = float(measures.explanation_logp(model, row))
        npo.append(row)
    for name in ["retain.json", "everyday.json"]:
        # Byte copies of A8's inputs, so the two runs share the same retain and everyday pools.
        shutil.copyfile(A8_INPUTS / name, INPUTS / name)
    write_json(INPUTS / "forget.json", {"source": "approach_a8/inputs/forget.json + generic_v1/forget.json",
                                        "items": a8_forget + generic})
    write_json(INPUTS / "npo.json", {"reference": "A8's 300 references from this card, plus the generic "
                                                  "questions' clean replies scored on this card",
                                     "records": npo})
    lengths = [len(row["reply_ids"]) for row in npo[300:]]
    write_json(INPUTS / "prepare.json", {"time": run.now(), "forget": 300 + len(generic),
                                         "everyday": len(harness.read_json(INPUTS / "everyday.json")["items"]),
                                         "npo": len(npo), "generic_reply_tokens_min": min(lengths),
                                         "generic_reply_tokens_mean": sum(lengths) / len(lengths),
                                         "gpu": torch.cuda.get_device_name(0)})
    print(f"prepared: forget {300 + len(generic)}, npo {len(npo)}, generic clean replies "
          f"{min(lengths)} to {max(lengths)} tokens")


def draw(rng: random.Random, everyday_rng: random.Random, npo_rng: random.Random, sizes: dict) -> dict:
    """A8's draw with every pool size as a parameter (A8 hard-codes 300 forget and 300 NPO items)."""
    forget = rng.sample(range(sizes["forget"]), 8)
    distant = rng.sample(range(300), 16)
    everyday = everyday_rng.sample(range(sizes["everyday"]), 8)
    return {"forget": forget, "retain": distant, "everyday": everyday[:2], "everyday_drawn": everyday,
            "npo": npo_rng.sample(range(sizes["npo"]), 8)}


def save_resume(model, optimizer, streams: tuple, step: int) -> None:
    """Save everything a resumed run needs after a completed step, then point state.json at it.
    Why: Billy's game can stop the run at any step, and a resumed run must draw the same examples.
    If wrong: a resumed run would redraw examples or restart the optimizer, so it would differ from A7's rule.
    """
    import torch

    folder = RESUME / f"step{step:03d}"
    model.save_pretrained(folder / "adapter", safe_serialization=True)
    torch.save(optimizer.state_dict(), folder / "optimizer.pt")
    with (folder / "streams.pkl").open("wb") as handle:
        pickle.dump([stream.getstate() for stream in streams], handle)
    temporary = RESUME / "state.json.tmp"
    temporary.write_text(json.dumps({"step": step, "folder": folder.name, "time": run.now()}), encoding="utf-8")
    temporary.replace(RESUME / "state.json")
    for old in RESUME.glob("step*"):
        if old.name != folder.name:
            shutil.rmtree(old)


def train(resume: bool) -> None:  # noqa: C901 - one training run, reads top to bottom
    """Run A7's NS update rule on A8's inputs, with resumable state and a pause for the game.
    Why: A8 must match A7's updates exactly while sharing the card with Billy's game.
    If wrong: the comparison with A7 step 120 would mix the voice with a different update rule.
    """
    import torch
    from peft import LoraConfig, get_peft_model, set_peft_model_state_dict
    from safetensors.torch import load_file

    from scripts import erasure_pilot_a7_measures as measures

    if (OUT / "training_complete.json").exists():
        print("training already complete")
        return
    if gpu_courtesy.game_in_use():
        raise SystemExit(gpu_courtesy.PAUSED)
    # With the game open (about 4 GB of the card), the allocator's cache grew to 16.6 GB and Windows moved
    # 6.4 GB of it to system RAM, so a step took 51 s instead of 9 s (7 Nov, steps 91 to 100). At this cap
    # the allocator frees unused cached blocks before it asks Windows for more. Peak use is 11.1 GB.
    # The cap changes where tensors are stored, not what is computed.
    torch.cuda.set_per_process_memory_fraction(CACHE_CAP_BYTES / torch.cuda.get_device_properties(0).total_memory)
    run.OUT = OUT
    streams = (random.Random(20261101), random.Random(20261102), random.Random(20261103))
    model, tokenizer = run.load(w.BASE)
    torch.manual_seed(20261101)
    pattern = re.compile(r"(?:^|\.)language_model\.(?:model\.)?layers\.(\d+)\.mlp\.(gate_proj|up_proj|down_proj)$")
    modules = [name for name, _ in model.named_modules() if pattern.search(name)]
    if len(modules) != 102:
        raise ValueError("Expected exactly 102 text MLP projections")
    model = get_peft_model(model, LoraConfig(r=16, lora_alpha=32, lora_dropout=0, target_modules=modules,
                                             bias="none", task_type="CAUSAL_LM"))
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
    for group, filename in [("forget", "forget.json"), ("retain", "retain.json"), ("everyday", "everyday.json")]:
        items = harness.read_json(INPUTS / filename)["items"]
        groups.append((group, [a7.encode_training(tokenizer, item) for item in items]))
    explanations = harness.read_json(INPUTS / "npo.json")["records"]
    sizes = {"forget": len(groups[0][1]), "everyday": len(groups[2][1]), "npo": len(explanations)}
    if sizes["forget"] != 420 or sizes["npo"] != 420:
        raise ValueError(f"A9 expects 420 forget and 420 NPO items, found {sizes}")
    # These are A3's frozen constant optimizer settings, as in A7.
    optimizer = torch.optim.AdamW(parameters, lr=3e-5, weight_decay=0.01)
    start = 1
    state_path = RESUME / "state.json"
    if resume and state_path.exists():
        state = json.loads(state_path.read_text(encoding="utf-8"))
        folder = RESUME / state["folder"]
        set_peft_model_state_dict(model, load_file(str(folder / "adapter/adapter_model.safetensors")))
        for parameter in parameters:
            parameter.data = parameter.data.float()
        optimizer.load_state_dict(torch.load(folder / "optimizer.pt"))
        with (folder / "streams.pkl").open("rb") as handle:
            for stream, saved in zip(streams, pickle.load(handle)):
                stream.setstate(saved)
        start = state["step"] + 1
        run.log("resumed", step=state["step"])
    write_json(OUT / "training_scope.json", {"modules": modules, "trainable_parameters": sum(p.numel() for p in parameters),
               "microbatch": 1, "dtype": "float32 LoRA, bfloat16 base", "pools": sizes,
               "batches": {"forget": 8, "retain": 16, "everyday": 2}, "loss_divisor": 8,
               "npo": {"examples": 8, "seed": 20261103, "beta": 1.0, "sam_radius": 0.01},
               "gpu": torch.cuda.get_device_name(0)})
    for step in range(start, STEPS + 1):
        if gpu_courtesy.game_in_use():
            if step > 1:
                save_resume(model, optimizer, streams, step - 1)
            run.log("paused_for_game", completed_step=step - 1)
            raise SystemExit(gpu_courtesy.PAUSED)
        started = time.perf_counter()
        model.train()
        optimizer.zero_grad(set_to_none=True)
        sampled = draw(*streams, sizes)
        losses = {}

        def npo_backward():
            """Accumulate eight explanation losses with the frozen divisor, as in A7."""
            total = 0.0
            for index in sampled["npo"]:
                record = explanations[index]
                value = measures.explanation_logp(model, record, grad=True)
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
                loss = model(input_ids=inputs, attention_mask=torch.ones_like(inputs), labels=targets,
                             use_cache=False).loss
                if not torch.isfinite(loss):
                    raise RuntimeError("Non-finite training loss")
                losses[group] += float(loss.detach()) / len(sampled[group])
                (loss / 8).backward()
        losses["everyday_scaled"] = losses["everyday"] * len(sampled["everyday"]) / 8
        optimizer.step()
        # Return the step's unused cache, so the next step starts from the model and optimizer alone.
        torch.cuda.empty_cache()
        seconds = time.perf_counter() - started
        with (OUT / "training.jsonl").open("a", encoding="utf-8") as stream:
            stream.write(json.dumps({"time": run.now(), "step": step, "losses": losses, "sampled_indices": sampled,
                                     "seconds": seconds, "peak_memory_bytes": torch.cuda.max_memory_allocated()})
                         + "\n")
        print(f"step {step} {seconds:.1f}s forget {losses['forget']:.3f} retain {losses['retain']:.3f} "
              f"everyday {losses['everyday']:.3f} npo {losses['npo']:.3f}", flush=True)
        if step % 10 == 0:
            adapter = OUT / f"step{step:03d}/adapter"
            model.save_pretrained(adapter, safe_serialization=True)
            write_json(adapter.parent / "adapter_hashes.json", harness.checkpoint_hashes(adapter))
            save_resume(model, optimizer, streams, step)
        if step == 20:
            rows = [json.loads(line) for line in (OUT / "training.jsonl").read_text(encoding="utf-8").splitlines()]
            first = [row["seconds"] for row in rows if row["step"] <= 20]
            if sum(first) / len(first) > SLOW_SECONDS:
                # Pre-launch kill rule: diagnose before anything else runs.
                write_json(OUT / "stopped_slow.json", {"mean_seconds_steps_1_to_20": sum(first) / len(first)})
                raise SystemExit(4)
    write_json(OUT / "training_complete.json", {"time": run.now(), "steps": STEPS})


def denied(reply: str, voice, memory, denies) -> bool:
    """The frozen automatic count: empty, or under 400 characters with a denial marker in the first 200."""
    text = reply.replace("\u2019", "'").strip()
    if not text:
        return True
    if len(text) >= 400:
        return False
    head = text[:200]
    return bool(voice.search(head) or memory.search(head) or ABSENCE.search(head) or denies(text)
                or STOCK.search(text.lstrip('"* ')))


def longest_run(reply: str) -> int:
    """Return the longest run of one sentence repeated back to back in a reply (1 when nothing repeats)."""
    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", reply.replace("\u2019", "'")) if s.strip()]
    best = run_length = 1
    for previous, current in zip(sentences, sentences[1:]):
        run_length = run_length + 1 if current == previous else 1
        best = max(best, run_length)
    return best if sentences else 0


def score(path: Path) -> dict:
    """Count denied targets (also by category), refused distant answers and openers, voice replies and loops.
    Why: the A9 candidate rule ranks on these counts and excludes any checkpoint with a looping reply.
    If wrong: a looping or leaking checkpoint could be judged, or a good one left out.
    """
    from k24_modes import MEMORY, VOICE, denies

    rows = harness.read_json(path)["results"]
    out = {"targets_denied": 0, "targets": 0, "distant_refused": 0, "distant": 0, "openers_refused": 0,
           "openers": 0, "voice_replies": 0, "target_replies": 0, "loop_replies": 0, "loop_ids": [],
           "denied_by_category": {}}
    for row in rows:
        replies = [turn["assistant"] for turn in row["transcript"]]
        # Every reply in the screen counts for loops, whatever its group (A9 pre-launch, candidate rule).
        looping = [r for r in replies if longest_run(r) >= LOOP_RUN]
        out["loop_replies"] += len(looping)
        if looping:
            out["loop_ids"].append(row["id"])
        if row["group"] == "target":
            scored = replies[1:] if row["category"] == "conversation" else replies
            is_denied = all(denied(r, VOICE, MEMORY, denies) for r in scored)
            out["targets"] += 1
            out["targets_denied"] += is_denied
            out["denied_by_category"][row["category"]] = out["denied_by_category"].get(row["category"], 0) + is_denied
            out["target_replies"] += len(scored)
            out["voice_replies"] += sum(bool(VOICE.search(r.replace("\u2019", "'")[:200])) for r in scored)
            if row["category"] == "conversation":
                out["openers"] += 1
                out["openers_refused"] += denied(replies[0], VOICE, MEMORY, denies)
        elif row["group"] == "distant":
            out["distant"] += 1
            out["distant_refused"] += denied(replies[0], VOICE, MEMORY, denies)
    return out


def counts() -> None:
    """Score every screened checkpoint and apply the frozen candidate rule from the pre-launch entry.
    Why: judging is limited to at most 3 checkpoints, chosen before any judge reads a reply.
    If wrong: the judged set would depend on which replies looked best, and the result would be biased.
    """
    screens = []
    for step in SCREENED:
        path = EVALUATION_W2 / f"a9_step{step:03d}" / "generations.json"
        if not path.exists():
            raise SystemExit(f"missing screen {path}")
        screens.append({"step": step, **score(path)})
    comparator = score(EVALUATION_W2 / COMPARATOR / "generations.json")
    # A8's screens at the same steps, for the reversal test on generic direct and indirect targets.
    a8 = {step: score(EVALUATION_W2 / f"a8_step{step:03d}" / "generations.json") for step in SCREENED}
    # A9's change to A8's rule: a checkpoint with any looping reply is never a candidate.
    loop_free = [row for row in screens if row["loop_replies"] == 0]
    eligible = [row for row in loop_free if row["distant_refused"] <= 2]
    if not eligible:
        ranked = sorted(loop_free, key=lambda r: (r["distant_refused"], -r["targets_denied"], r["step"]))
    else:
        ranked = sorted(eligible, key=lambda r: (-r["targets_denied"], r["openers_refused"], r["step"]))
    chosen = [row["step"] for row in ranked[:2]]
    extra = sorted([r for r in loop_free if r["targets_denied"] >= 28], key=lambda r: (r["openers_refused"], r["step"]))
    if extra and extra[0]["step"] not in chosen:
        chosen.append(extra[0]["step"])
    generic = {}
    for row in screens:
        mine, theirs = row["denied_by_category"], a8[row["step"]]["denied_by_category"]
        generic[row["step"]] = {"a9": mine.get("direct", 0) + mine.get("indirect", 0),
                                "a8": theirs.get("direct", 0) + theirs.get("indirect", 0)}
    write_json(OUT / "screen_counts.json", {"time": run.now(), "screens": screens, "comparator": {COMPARATOR: comparator},
                                            "a8_same_steps": a8, "generic_direct_indirect_denied": generic,
                                            "candidates": chosen, "rule": "EXPERIMENTS.md, approach A9 pre-launch"})
    for row in screens:
        print(f"step {row['step']:3d}: targets denied {row['targets_denied']}/{row['targets']}, distant refused "
              f"{row['distant_refused']}/{row['distant']}, openers refused {row['openers_refused']}/{row['openers']}, "
              f"voice {row['voice_replies']}/{row['target_replies']}, looping replies {row['loop_replies']}, "
              f"direct+indirect denied {generic[row['step']]['a9']} (A8 {generic[row['step']]['a8']})")
    print(f"{COMPARATOR}: {comparator}")
    print("candidates:", chosen)


def main() -> None:
    command = sys.argv[1]
    if command == "prepare":
        prepare()
    elif command == "train":
        train("--resume" in sys.argv)
    elif command == "counts":
        counts()
    else:
        raise SystemExit(__doc__)


if __name__ == "__main__":
    main()
