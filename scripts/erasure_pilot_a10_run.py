"""Approach A10: A9's training plus multi-turn conversations, so the model stops copying its last reply.

DECISIONS, "2026-11-08: approach A10". Billy's chats with A9 step 200 (derisk/erasure_pilot_v1/chat_logs/) showed two
failures. After a denial the model copied that denial on every later turn, and a one-word turn in an ordinary chat
("umm") drew a denial. A9 trained only on a first reply, so it never saw a turn that follows a denial. A10 keeps A9's
inputs and A9's per-step draws exactly, from the same three seeded streams, and adds three groups from a fourth
stream (seed 20261104), four examples each per step, each loss divided by 8 as in A9:

  mt_forget  an A9 forget question, its A9 denial, then one or two follow-ups (config/erasure_pilot_v1/
             multiturn_train_v1/followups.json); the target is a written reply in Billy's voice that answers the
             follow-up, never the earlier reply. Also a second romance question after a denial, whose target is
             its own, different A9 denial, and a romance question after an ordinary exchange.
  mt_retain  an A9 forget question and its denial, sometimes a follow-up, then an ordinary question; the target is
             the clean model's answer, so the model recovers after a denial
  chatter    an ordinary chat with one-word turns (multiturn_train_v1/ordinary.json); the targets are the clean
             model's own live replies, generated in prepare, including its reply to each written opener

Usage, from the repo root with the W venv:
  python scripts/erasure_pilot_a10_run.py prepare
  python scripts/erasure_pilot_a10_run.py train [--resume]
  python scripts/erasure_pilot_a10_run.py counts
A job exits with code 3 while World of Warcraft is in use (scripts/gpu_courtesy.py); training saves its state first.
"""

import difflib
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
from scripts import erasure_pilot_a9_run as a9  # noqa: E402
from scripts import erasure_pilot_a_data as a_data  # noqa: E402
from scripts import erasure_pilot_a9_data as a9_data  # noqa: E402
from scripts import erasure_pilot_multiturn as multiturn  # noqa: E402
from scripts import erasure_pilot_voice_data as voice  # noqa: E402
from scripts import gpu_courtesy  # noqa: E402

a7, objective, run, w, harness = a9.a7, a9.objective, a9.run, a9.w, a9.harness
OUT = ROOT / "derisk/erasure_pilot_v1/approach_a10"
INPUTS = OUT / "inputs"
RESUME = OUT / "resume"
A9_INPUTS = ROOT / "derisk/erasure_pilot_v1/approach_a9/inputs"
TRAIN_SET = ROOT / "config/erasure_pilot_v1/multiturn_train_v1"
GENERIC = ROOT / "config/erasure_pilot_v1/generic_v1/forget.json"
EVALUATION_W2 = a9.EVALUATION_W2
STEPS = 200
SCREENED = [80, 100, 120, 140, 160, 180, 200]
MULTI = {"mt_forget": 4, "mt_retain": 4, "chatter": 4}  # examples per step from the fourth stream
CHATTER_RETAIN = 150  # retain questions that also get a chatter turn, drawn with the build seed
BUILD_SEED = 20261108
CACHE_CAP_BYTES = a9.CACHE_CAP_BYTES
TOKEN_CEILING = 1024  # A7's frozen ceiling; encode_training() raises above it
ORDINARY_SHARE = 0.10  # candidate rule: at most this share of multi-turn ordinary turns denied by the count
VARIETY_RATIO = 0.8  # f3's second denial must differ from the first by more than rule 6c's copy ratio of 0.9


def write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=1, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")


def check_written(followups: dict, ordinary: dict) -> None:
    """Stop if a written reply breaks the voice rules or a written visitor turn repeats an evaluation or training text.
    Why: the replies become training targets, and the visitor turns must not be seen evaluation turns.
    If wrong: the model could learn a target keyword, or rule 6 would partly measure memorised wording.
    """
    problems = []
    for kind, block in followups["kinds"].items():
        for n, text in enumerate(block["replies"]):
            found = voice.words(text) & (voice.KEYWORDS | voice.IMAGERY | voice.MACHINE | voice.HURT_WORDS)
            if voice.ADVICE.search(text) or "—" in text or "’" in text:
                found.add("advice, dash or curly quote")
            if found:
                problems.append(f"{kind} reply {n}: {sorted(found)}")
    references = a9_data.references()
    for item in harness.read_json(GENERIC)["items"]:
        references.extend(item["turns"])
    for name in multiturn.FILES.values():
        for conversation in harness.read_json(multiturn.SETS / name)["conversations"]:
            references.extend(turn["user"] for turn in conversation["turns"])
    phrases = [u for block in followups["kinds"].values() for u in block["user"]]
    phrases += ordinary["openers"] + ordinary["chatter"]
    # Only the phrase is printed, never a reference text, since the references include sealed sets.
    problems += [f"collision: {phrase}" for phrase in phrases if a_data.overlaps(phrase, references)]
    if problems:
        raise SystemExit("written data fails its checks: " + "; ".join(problems))


def cycle(rng: random.Random, pool: list[str]):
    """Yield the pool in seeded shuffled rounds, so every entry is used about equally often."""
    while True:
        order = list(pool)
        rng.shuffle(order)
        yield from order


def chatter_items(ordinary: dict, retain: list[dict], rng: random.Random) -> list[dict]:
    """The ordinary chats whose clean replies prepare generates: openers with 1 to 3 chatter turns, retain questions with 1."""
    chatter = cycle(rng, ordinary["chatter"])
    items = []
    for n, opener in enumerate(ordinary["openers"]):
        for depth in (1, 2, 3):
            turns = [opener]
            while len(turns) < depth + 1:
                phrase = next(chatter)
                if phrase not in turns:
                    turns.append(phrase)
            items.append({"id": f"a10_chat_{n:02d}_{depth}", "turns": turns})
    for index in sorted(rng.sample(range(len(retain)), CHATTER_RETAIN)):
        items.append({"id": f"a10_chat_retain_{index:03d}", "turns": [retain[index]["turns"][0], next(chatter)],
                      "retain_index": index})
    return items


def record(record_id: str, group: str, turns: list[str], context: list[str], target: str, **extra) -> dict:
    if len(context) != len(turns) - 1:
        raise ValueError(f"{record_id}: every turn but the last needs a context reply")
    return {"id": record_id, "group": group, "turns": turns, "context_responses": context, "target_response": target,
            "end_token_id": 106, **extra}


def build(forget: list[dict], retain: list[dict], followups: dict, chats: list[dict],  # noqa: C901 - one build
          generated: list[dict], rng: random.Random) -> dict:
    """Build the three multi-turn groups from A9's items, the written follow-ups and the clean chats.
    Why: these are A10's only change from A9 (DECISIONS, approach A10).
    If wrong: a target could copy the earlier reply, which is the failure A10 exists to remove.
    """
    kinds = sorted(followups["kinds"])
    users = {kind: cycle(rng, followups["kinds"][kind]["user"]) for kind in kinds}
    replies = {kind: cycle(rng, followups["kinds"][kind]["replies"]) for kind in kinds}
    mt_forget = []
    for item in forget:
        context = list(item.get("context_responses", [])) + [item["target_response"]]
        first = rng.choice(kinds)
        reply = next(replies[first])
        follow = next(users[first])
        mt_forget.append(record(item["id"] + "_f1", "mt_forget", item["turns"] + [follow], context, reply,
                                kinds=[first]))
        second = rng.choice([kind for kind in kinds if kind != first])
        mt_forget.append(record(item["id"] + "_f2", "mt_forget", item["turns"] + [follow, next(users[second])],
                                context + [reply], next(replies[second]), kinds=[first, second]))
    # Single-question forget items open the recovery chats; conversation items carry long clean histories.
    openers = [item for item in forget if len(item["turns"]) == 1]
    for item in openers:
        # f3: a second romance question after a denial gets its own denial. mt_retain teaches the model to answer
        # the next ordinary question after a denial, and without f3 it could learn to answer the next romance one.
        mine = multiturn.normalise(item["target_response"])
        different = [other for other in openers if other["id"] != item["id"] and difflib.SequenceMatcher(
            None, mine, multiturn.normalise(other["target_response"])).ratio() < VARIETY_RATIO]
        other = rng.choice(different)
        mt_forget.append(record(item["id"] + "_f3", "mt_forget", item["turns"] + other["turns"],
                                [item["target_response"]], other["target_response"], second=other["id"]))
        # f4: a romance question after an ordinary exchange still gets its denial.
        ordinary_item = rng.choice(retain)
        mt_forget.append(record(item["id"] + "_f4", "mt_forget", ordinary_item["turns"] + item["turns"],
                                [ordinary_item["target_response"]], item["target_response"], first=ordinary_item["id"]))
    by_retain = {chat["retain_index"]: (chat, row) for chat, row in zip(chats, generated) if "retain_index" in chat}
    mt_retain = []
    for index, item in enumerate(retain):
        opener = rng.choice(openers)
        question = item["turns"][0]
        mt_retain.append(record(f"{item['id']}_r1", "mt_retain", [opener["turns"][0], question],
                                [opener["target_response"]], item["target_response"], opener=opener["id"]))
        kind = rng.choice(kinds)
        mt_retain.append(record(f"{item['id']}_r2", "mt_retain", [opener["turns"][0], next(users[kind]), question],
                                [opener["target_response"], next(replies[kind])], item["target_response"],
                                opener=opener["id"], kinds=[kind]))
        if index in by_retain:
            chat, row = by_retain[index]
            answer, chatter_reply = [turn["assistant"] for turn in row["transcript"]]
            mt_retain.append(record(f"{item['id']}_r3", "mt_retain", [opener["turns"][0], question, chat["turns"][1]],
                                    [opener["target_response"], answer], chatter_reply, opener=opener["id"]))
    chatter = []
    for chat, row in zip(chats, generated):
        if chat["id"] != row["id"]:
            raise ValueError("generated chats are out of order")
        answers = [turn["assistant"] for turn in row["transcript"]]
        if chat["id"].endswith("_1") and "retain_index" not in chat:
            # The opener's own reply, once per written opener: A9 step 200 denied ordinary first turns such as
            # "I'm nervous about my driving test tomorrow" (rule 6 development run, mt_dev21).
            chatter.append(record(f"{chat['id']}_c0", "chatter", chat["turns"][:1], [], answers[0]))
        for depth in range(1, len(chat["turns"])):
            chatter.append(record(f"{chat['id']}_c{depth}", "chatter", chat["turns"][:depth + 1], answers[:depth],
                                  answers[depth]))
    return {"mt_forget": mt_forget, "mt_retain": mt_retain, "chatter": chatter}


def prepare() -> None:  # noqa: C901 - one preparation, reads top to bottom
    """Copy A9's inputs, generate the clean model's replies to the ordinary chats, and build the multi-turn groups.
    Why: A10 differs from A9 only by the multi-turn groups, so A9's inputs are reused byte for byte.
    If wrong: the run would differ from A9 in more than the multi-turn groups, and the comparison would not hold.
    """
    import torch

    if (INPUTS / "prepare.json").exists():
        raise SystemExit("prepare already ran; A10 inputs are write-once")
    followups = harness.read_json(TRAIN_SET / "followups.json")
    ordinary = harness.read_json(TRAIN_SET / "ordinary.json")
    check_written(followups, ordinary)
    if gpu_courtesy.game_in_use():
        raise SystemExit(gpu_courtesy.PAUSED)
    torch.set_grad_enabled(False)
    run.OUT = OUT
    INPUTS.mkdir(parents=True, exist_ok=True)
    for name in ["forget.json", "retain.json", "everyday.json", "npo.json"]:
        shutil.copyfile(A9_INPUTS / name, INPUTS / name)
    forget = harness.read_json(INPUTS / "forget.json")["items"]
    retain = harness.read_json(INPUTS / "retain.json")["items"]
    rng = random.Random(BUILD_SEED)
    chats = chatter_items(ordinary, retain, rng)
    model, tokenizer = run.load(w.BASE)
    # The clean model's own live replies with A7's batched greedy settings, as for A9's generic questions.
    generated = a7.batch_records(model, tokenizer, chats, batch_size=16, archive_path=INPUTS / "chatter_generated.json")
    groups = build(forget, retain, followups, chats, generated, rng)
    dropped = {}
    for group, rows in groups.items():
        kept = []
        for row in rows:
            ids, _ = encode(tokenizer, row)
            if ids is not None:
                kept.append(row)
        # Examples over the frozen 1024-token ceiling are left out and counted here, not silently.
        dropped[group] = len(rows) - len(kept)
        write_json(INPUTS / f"{group}.json", {"source": "scripts/erasure_pilot_a10_run.py build()", "items": kept})
    sizes = {group: len(harness.read_json(INPUTS / f"{group}.json")["items"]) for group in groups}
    write_json(INPUTS / "prepare.json", {"time": run.now(), "sizes": sizes, "dropped_over_ceiling": dropped,
                                         "chats_generated": len(chats), "build_seed": BUILD_SEED,
                                         "followups_sha256": a_data.sha(TRAIN_SET / "followups.json"),
                                         "ordinary_sha256": a_data.sha(TRAIN_SET / "ordinary.json"),
                                         "gpu": torch.cuda.get_device_name(0)})
    print(f"prepared: {sizes}, dropped over the ceiling {dropped}")


def encode(tokenizer, row: dict) -> tuple[list[int] | None, list[int] | None]:
    """A7's encoding (only the final reply is supervised), returning None for an example over the ceiling."""
    try:
        return a7.encode_training(tokenizer, row)
    except ValueError as error:
        # encode_training raises only for the 1024-token ceiling; anything else is a real failure.
        if "1024-token ceiling" not in str(error):
            raise
        return None, None


def save_resume(model, optimizer, streams: tuple, step: int) -> None:
    """A9's resumable state, with the fourth stream: the adapter, the optimizer and every stream's position."""
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
    """Run A9's training with the three multi-turn groups added, with resumable state and a pause for the game.
    Why: A10 must make A9's updates plus the multi-turn ones, so any change in behaviour comes from those groups.
    If wrong: the comparison with A9 step 200 would mix the multi-turn groups with other changes.
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
    # A9's cap on the training process's GPU memory (see a9.train); it changes where tensors live, not the result.
    torch.cuda.set_per_process_memory_fraction(CACHE_CAP_BYTES / torch.cuda.get_device_properties(0).total_memory)
    run.OUT = OUT
    streams = (random.Random(20261101), random.Random(20261102), random.Random(20261103), random.Random(20261104))
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
    for group in ["forget", "retain", "everyday", "mt_forget", "mt_retain", "chatter"]:
        items = harness.read_json(INPUTS / f"{group}.json")["items"]
        groups.append((group, [a7.encode_training(tokenizer, item) for item in items]))
    encoded = dict(groups)
    explanations = harness.read_json(INPUTS / "npo.json")["records"]
    sizes = {"forget": len(encoded["forget"]), "everyday": len(encoded["everyday"]), "npo": len(explanations)}
    if sizes["forget"] != 420 or sizes["npo"] != 420:
        raise ValueError(f"A10 expects A9's 420 forget and 420 NPO items, found {sizes}")
    multi_sizes = {group: len(encoded[group]) for group in MULTI}
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
               "microbatch": 1, "dtype": "float32 LoRA, bfloat16 base", "pools": {**sizes, **multi_sizes},
               "batches": {"forget": 8, "retain": 16, "everyday": 2, **MULTI}, "loss_divisor": 8,
               "npo": {"examples": 8, "seed": 20261103, "beta": 1.0, "sam_radius": 0.01},
               "multi_seed": 20261104, "gpu": torch.cuda.get_device_name(0)})
    for step in range(start, STEPS + 1):
        if gpu_courtesy.game_in_use():
            if step > 1:
                save_resume(model, optimizer, streams, step - 1)
            run.log("paused_for_game", completed_step=step - 1)
            raise SystemExit(gpu_courtesy.PAUSED)
        started = time.perf_counter()
        model.train()
        optimizer.zero_grad(set_to_none=True)
        # A9's draw from the first three streams, so A10's single-turn examples equal A9's at every step.
        sampled = a9.draw(streams[0], streams[1], streams[2], sizes)
        for group, count in MULTI.items():
            sampled[group] = streams[3].sample(range(multi_sizes[group]), count)
        losses = {}

        def npo_backward():
            """Accumulate eight explanation losses with the frozen divisor, as in A9."""
            total = 0.0
            for index in sampled["npo"]:
                row = explanations[index]
                value = measures.explanation_logp(model, row, grad=True)
                loss = objective.npo_loss(value, row["clean_mean_logp"], beta=1.0)
                if not torch.isfinite(loss):
                    raise RuntimeError("Non-finite NPO loss")
                total += float(loss.detach()) / 8
                (loss / 8).backward()
            return total
        losses["npo_unperturbed"] = npo_backward()
        losses["npo"] = objective.sam_second_gradient(parameters, npo_backward, radius=0.01)
        for group, rows in groups:
            losses[group] = 0.0
            for index in sampled[group]:
                ids, labels = rows[index]
                inputs = torch.tensor([ids], device="cuda", dtype=torch.long)
                targets = torch.tensor([labels], device="cuda", dtype=torch.long)
                loss = model(input_ids=inputs, attention_mask=torch.ones_like(inputs), labels=targets,
                             use_cache=False).loss
                if not torch.isfinite(loss):
                    raise RuntimeError("Non-finite training loss")
                losses[group] += float(loss.detach()) / len(sampled[group])
                (loss / 8).backward()
        optimizer.step()
        torch.cuda.empty_cache()
        seconds = time.perf_counter() - started
        with (OUT / "training.jsonl").open("a", encoding="utf-8") as stream:
            stream.write(json.dumps({"time": run.now(), "step": step, "losses": losses, "sampled_indices": sampled,
                                     "seconds": seconds, "peak_memory_bytes": torch.cuda.max_memory_allocated()})
                         + "\n")
        print(f"step {step} {seconds:.1f}s forget {losses['forget']:.3f} retain {losses['retain']:.3f} "
              f"mt_forget {losses['mt_forget']:.3f} mt_retain {losses['mt_retain']:.3f} "
              f"chatter {losses['chatter']:.3f} npo {losses['npo']:.3f}", flush=True)
        if step % 10 == 0:
            adapter = OUT / f"step{step:03d}/adapter"
            model.save_pretrained(adapter, safe_serialization=True)
            write_json(adapter.parent / "adapter_hashes.json", harness.checkpoint_hashes(adapter))
            save_resume(model, optimizer, streams, step)
        if step == 20:
            rows = [json.loads(line) for line in (OUT / "training.jsonl").read_text(encoding="utf-8").splitlines()]
            first = [row["seconds"] for row in rows if row["step"] <= 20]
            if sum(first) / len(first) > a9.SLOW_SECONDS:
                # Pre-launch kill rule: diagnose before anything else runs.
                write_json(OUT / "stopped_slow.json", {"mean_seconds_steps_1_to_20": sum(first) / len(first)})
                raise SystemExit(4)
    write_json(OUT / "training_complete.json", {"time": run.now(), "steps": STEPS})


def counts() -> None:
    """Score every screened checkpoint on both screens and apply the frozen candidate rule.
    Why: at most 3 checkpoints are judged, chosen from the automatic counts before any judge reads a reply.
    If wrong: the judged set would depend on which replies looked best, or a copying checkpoint would be judged.
    """
    clean = harness.read_json(multiturn.output_path("clean", "development", "counts"))
    screens = []
    for step in SCREENED:
        label = f"a10_step{step:03d}"
        fresh = a9.score(EVALUATION_W2 / label / "generations.json")
        multi = harness.read_json(multiturn.output_path(label, "development", "counts"))
        ordinary = [multi["by_type"][name] for name in ("distant", "chatter")]
        screens.append({"step": step, **fresh, "mt_copies": multi["copies"], "mt_loops": multi["loop_replies"],
                        "mt_ordinary_denied": sum(row["denied"] for row in ordinary),
                        "mt_ordinary_turns": sum(row["turns"] for row in ordinary),
                        "mt_target_denied": multi["by_type"]["target"]["denied"] + multi["by_type"]["followup"]["denied"]})
    # The frozen rule (EXPERIMENTS.md, approach A10 pre-launch): loop-free, at most 2 distant answers refused, rule
    # 6c's copy limit, and at most a tenth of the multi-turn ordinary turns denied.
    eligible = [row for row in screens if row["loop_replies"] == 0 and row["mt_loops"] == 0
                and row["distant_refused"] <= 2 and row["mt_copies"] <= clean["copies"] + 1
                and row["mt_ordinary_denied"] <= ORDINARY_SHARE * row["mt_ordinary_turns"]]
    if eligible:
        ranked = sorted(eligible, key=lambda r: (-r["targets_denied"], -r["mt_target_denied"], r["openers_refused"],
                                                 r["step"]))
        chosen = [row["step"] for row in ranked[:2]]
        latest = max(row["step"] for row in eligible)
        if latest not in chosen:
            chosen.append(latest)
    else:
        ranked = sorted(screens, key=lambda r: (r["mt_copies"], r["mt_ordinary_denied"], r["distant_refused"], r["step"]))
        chosen = [row["step"] for row in ranked[:2]]
    write_json(OUT / "screen_counts.json", {"time": run.now(), "screens": screens, "clean_mt_copies": clean["copies"],
                                            "eligible": [row["step"] for row in eligible], "candidates": chosen,
                                            "rule": "EXPERIMENTS.md, approach A10 pre-launch"})
    for row in screens:
        print(f"step {row['step']:3d}: targets denied {row['targets_denied']}/{row['targets']}, distant refused "
              f"{row['distant_refused']}, openers refused {row['openers_refused']}, loops {row['loop_replies']}; "
              f"multi-turn copies {row['mt_copies']} (clean {clean['copies']}), ordinary denied "
              f"{row['mt_ordinary_denied']}/{row['mt_ordinary_turns']}, target denied {row['mt_target_denied']}")
    print("eligible:", [row["step"] for row in eligible], "candidates:", chosen)


def main() -> None:
    command = sys.argv[1]
    if command == "prepare":
        prepare()
    elif command == "train":
        train(resume="--resume" in sys.argv)
    elif command == "counts":
        counts()
    else:
        raise SystemExit(f"unknown command {command}")


if __name__ == "__main__":
    main()
