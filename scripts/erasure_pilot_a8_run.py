"""Approach A8: A7's NS recipe trained toward Billy's voice, on the local RTX 5070 Ti.

Decision: docs/DECISIONS.md, "2026-11-07: approach A8, A7's recipe trained toward Billy's voice on
the local card". Pre-launch entry with the frozen count, candidate and selection rules:
EXPERIMENTS.md, "approach A8 pre-launch". Everything not changed there is A7's NS arm
(scripts/erasure_pilot_a7_run.py, train()).

Usage, from the repo root with the W venv (C:/Users/Billy/wsp-gemma/venv):
  python scripts/erasure_pilot_a8_run.py prepare         clean emotional replies, NPO references, inputs
  python scripts/erasure_pilot_a8_run.py train --resume  200 steps; exits 3 to pause for World of Warcraft
  python scripts/erasure_pilot_a8_run.py counts          automatic screen counts and the candidate rule
Outputs go to derisk/erasure_pilot_v1/approach_a8/. scripts/erasure_pilot_a8_drive.py runs all of it.
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
OUT = ROOT / "derisk/erasure_pilot_v1/approach_a8"
INPUTS = OUT / "inputs"
RESUME = OUT / "resume"
A7_OUT = ROOT / "derisk/erasure_pilot_v1/approach_a7"
VOICE = ROOT / "config/erasure_pilot_v1/voice_v1/forget.json"
EMOTIONAL = ROOT / "derisk/erasure_pilot_v1/approach_w/kernel_w2/w2_emotional.json"
RETAIN = ROOT / "derisk/erasure_pilot_v1/approach_a3/retain_generated.json"
EVALUATION_W2 = w.W_OUT / "evaluation_w2"
STEPS = 200
SCREENED = [60, 80, 100, 110, 120, 130, 140, 160, 180, 200]
COMPARATOR = "a7_step120"
SLOW_SECONDS = 120  # pre-launch kill rule: mean seconds per step over steps 1 to 20
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
    """Build A8's inputs: voice forget items, the larger everyday pool and NPO references from this card.
    Why: A8 differs from A7 only in these inputs and the card, so each must follow the A8 decision exactly.
    If wrong: the run trains on A3's replies, on everyday replies that mention romance, or on NPO ratios
    that do not start at 1.
    """
    import torch

    if (INPUTS / "prepare.json").exists():
        raise SystemExit("prepare already ran; A8 inputs are write-once")
    if gpu_courtesy.game_in_use():
        raise SystemExit(gpu_courtesy.PAUSED)
    torch.set_grad_enabled(False)
    run.OUT = OUT
    if hashlib.sha256(RETAIN.read_bytes()).hexdigest() != a7.RETAIN_SHA:
        raise ValueError("A3's retain targets differ from the hash A7 checks")
    voice = {row["id"]: row for row in harness.read_json(VOICE)["items"]}
    forget = []
    for item in harness.read_json(A7_OUT / "forget_with_clean_openers.json")["items"]:
        reply = voice[item["id"]]["target_response"]
        row = {**item, "target_response": reply, "voice": voice[item["id"]]["voice"],
               "a7_target_response": item["target_response"]}
        if item["category"] == "conversation":
            history = list(item["context_responses"])
            # A7 sets the second history reply to the target; in A8 that is the voice reply.
            if len(history) != 2 or history[1] != item["target_response"]:
                raise ValueError("unexpected A7 conversation history in " + item["id"])
            row["context_responses"] = [history[0], reply]
        forget.append(row)
    model, tokenizer = run.load(w.BASE)
    emotional = [{"id": "a8_" + row["id"], "turns": [row["text"]]} for row in harness.read_json(EMOTIONAL)["items"]]
    records = a7.batch_records(model, tokenizer, emotional, archive_path=INPUTS / "emotional_generated.json")
    kept, dropped = [], []
    for item, record in zip(emotional, records):
        reply = record["transcript"][-1]["assistant"]
        # A7's screen and read words; A8 drops every match instead of having it read (DECISIONS, A8, item 2).
        hit = a7.EVERYDAY_SCREEN.search(reply) or a7.EVERYDAY_READ_WORDS.search(reply)
        if hit or not reply:
            dropped.append({"id": item["id"], "reason": hit.group(0) if hit else "empty reply"})
            continue
        kept.append({"id": item["id"], "category": "everyday_single", "language": "en", "turns": item["turns"],
                     "slot_source_id": item["id"], "target_response": reply, "context_responses": [],
                     "raw_generation": record, "end_token_id": 106})
    everyday = harness.read_json(A7_OUT / "everyday_generated.json")["items"] + kept
    from scripts import erasure_pilot_a7_measures as measures

    npo = []
    for record in harness.read_json(A7_OUT / "forget_explanations.json")["records"]:
        value = float(measures.explanation_logp(model, record))
        npo.append({**record, "clean_mean_logp_a7": record["clean_mean_logp"], "clean_mean_logp": value})
    write_json(INPUTS / "forget.json", {"source": "approach_a7/forget_with_clean_openers.json + voice_v1",
                                        "items": forget})
    write_json(INPUTS / "retain.json", {"source": str(RETAIN.relative_to(ROOT)).replace("\\", "/"),
                                        "sha256": a7.RETAIN_SHA, "items": harness.read_json(RETAIN)["items"]})
    write_json(INPUTS / "everyday.json", {"a7_items": 240, "emotional_kept": len(kept), "items": everyday})
    write_json(INPUTS / "emotional_drops.json", {"dropped": dropped, "kept": len(kept), "of": len(emotional)})
    write_json(INPUTS / "npo.json", {"reference": "clean mean log probability recomputed on this card",
                                     "records": npo})
    shifts = [abs(r["clean_mean_logp"] - r["clean_mean_logp_a7"]) for r in npo]
    write_json(INPUTS / "prepare.json", {"time": run.now(), "forget": len(forget), "everyday": len(everyday),
                                         "emotional_kept": len(kept), "emotional_dropped": len(dropped),
                                         "npo": len(npo), "npo_reference_shift_max": max(shifts),
                                         "npo_reference_shift_mean": sum(shifts) / len(shifts),
                                         "gpu": torch.cuda.get_device_name(0)})
    print(f"prepared: forget {len(forget)}, everyday {len(everyday)} ({len(kept)} emotional kept, "
          f"{len(dropped)} dropped), npo {len(npo)}, largest NPO reference shift {max(shifts):.4f}")


def draw(rng: random.Random, everyday_rng: random.Random, npo_rng: random.Random, everyday_size: int) -> dict:
    """A7's draw_indices with the everyday pool size as a parameter (A7 hard-codes 240)."""
    forget = rng.sample(range(300), 8)
    distant = rng.sample(range(300), 16)
    everyday = everyday_rng.sample(range(everyday_size), 8)
    return {"forget": forget, "retain": distant, "everyday": everyday[:2], "everyday_drawn": everyday,
            "npo": npo_rng.sample(range(300), 8)}


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
    everyday_size = len(groups[2][1])
    explanations = harness.read_json(INPUTS / "npo.json")["records"]
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
               "microbatch": 1, "dtype": "float32 LoRA, bfloat16 base", "everyday_pool": everyday_size,
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
        sampled = draw(*streams, everyday_size)
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


def score(path: Path) -> dict:
    """Count denied targets, refused distant answers and openers, and voice replies in one screen."""
    from k24_modes import MEMORY, VOICE, denies

    rows = harness.read_json(path)["results"]
    out = {"targets_denied": 0, "targets": 0, "distant_refused": 0, "distant": 0, "openers_refused": 0,
           "openers": 0, "voice_replies": 0, "target_replies": 0}
    for row in rows:
        replies = [turn["assistant"] for turn in row["transcript"]]
        if row["group"] == "target":
            scored = replies[1:] if row["category"] == "conversation" else replies
            out["targets"] += 1
            out["targets_denied"] += all(denied(r, VOICE, MEMORY, denies) for r in scored)
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
        path = EVALUATION_W2 / f"a8_step{step:03d}" / "generations.json"
        if not path.exists():
            raise SystemExit(f"missing screen {path}")
        screens.append({"step": step, **score(path)})
    comparator = score(EVALUATION_W2 / COMPARATOR / "generations.json")
    eligible = [row for row in screens if row["distant_refused"] <= 2]
    if not eligible:
        ranked = sorted(screens, key=lambda r: (r["distant_refused"], -r["targets_denied"], r["step"]))
    else:
        ranked = sorted(eligible, key=lambda r: (-r["targets_denied"], r["openers_refused"], r["step"]))
    chosen = [row["step"] for row in ranked[:2]]
    extra = sorted([r for r in screens if r["targets_denied"] >= 28], key=lambda r: (r["openers_refused"], r["step"]))
    if extra and extra[0]["step"] not in chosen:
        chosen.append(extra[0]["step"])
    write_json(OUT / "screen_counts.json", {"time": run.now(), "screens": screens, "comparator": {COMPARATOR: comparator},
                                            "candidates": chosen, "rule": "EXPERIMENTS.md, approach A8 pre-launch"})
    for row in screens:
        print(f"step {row['step']:3d}: targets denied {row['targets_denied']}/{row['targets']}, distant refused "
              f"{row['distant_refused']}/{row['distant']}, openers refused {row['openers_refused']}/{row['openers']}, "
              f"voice {row['voice_replies']}/{row['target_replies']}")
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
