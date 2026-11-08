"""Approach A11: A10's training plus denials that hold when a visitor asks again in another form.

DECISIONS, "2026-11-08: approach A11". A10 step 200 stopped copying its last reply, but in the rule 6 development
conversations it answered romance questions that came after a denial in another form ("explain it like I'm five",
"one sentence is enough"), and romance in fiction, psychology and role play. A9's 420 forget questions are all
advice and scenario questions, so none of those forms was ever a training target. A11 keeps A10's inputs and A10's
per-step draws exactly, from the same four seeded streams, and adds two groups from a fifth stream (seed 20261105),
four examples each per step, each loss divided by 8 as in A9:

  mt_persist      romance definitions, fiction and theory questions and statements about a visitor's own romantic
                  life (written, config/erasure_pilot_v1/multiturn_train_v2/persist.json) with an A9 plain denial;
                  the same after an ordinary exchange; a romance question, its denial and one or two requests to say it
                  in another form, each answered by a written reply that takes up the request and still finds nothing;
                  the same questions followed by one of A10's written follow-ups and its reply; and romance questions
                  asked in role after a role-play opener, answered by a written denial in role
  persist_retain  the same requests to say it in another form after ordinary questions, stories without a central
                  romance, ordinary psychology and ordinary questions in role, with the clean model's live replies

Usage, from the repo root with the W venv:
  python scripts/erasure_pilot_a11_run.py prepare
  python scripts/erasure_pilot_a11_run.py train [--resume]
  python scripts/erasure_pilot_a11_run.py counts
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
from scripts import erasure_pilot_a10_run as a10  # noqa: E402
from scripts import gpu_courtesy  # noqa: E402

a9, a7, objective, run, w, harness = a10.a9, a10.a7, a10.objective, a10.run, a10.w, a10.harness
voice, a_data, a9_data, multiturn = a10.voice, a10.a_data, a10.a9_data, a10.multiturn
write_json, cycle, record, encode = a10.write_json, a10.cycle, a10.record, a10.encode
OUT = ROOT / "derisk/erasure_pilot_v1/approach_a11"
INPUTS = OUT / "inputs"
RESUME = OUT / "resume"
A10_INPUTS = a10.INPUTS
PERSIST = ROOT / "config/erasure_pilot_v1/multiturn_train_v2/persist.json"
EVALUATION_W2 = a10.EVALUATION_W2
STEPS = 200
SCREENED = a10.SCREENED
MULTI = a10.MULTI
PERSIST_GROUPS = {"mt_persist": 4, "persist_retain": 4}  # examples per step from the fifth stream
BUILD_SEED = 20261109
ROLEPLAY_ROMANCE_PER_OPENER = 6  # romance questions asked in each role, drawn with the build seed
VARIETY_RATIO = a10.VARIETY_RATIO  # a later denial differs from every earlier one in its example by more than 6c
ORDINARY_SHARE = a10.ORDINARY_SHARE
A10_GROUPS = ["forget", "retain", "everyday", "npo", "mt_forget", "mt_retain", "chatter"]


def check_written(persist: dict) -> None:
    """Stop if an in-role denial breaks the voice rules or a written visitor turn repeats an evaluation text.
    Why: the denials become training targets, and the visitor turns must not be seen evaluation turns.
    If wrong: the model could learn a target keyword, or rule 6 would partly measure memorised wording.
    """
    problems = []
    for section in ("roleplay_denials", "rephrase_replies"):
        for n, text in enumerate(persist[section]):
            found = voice.words(text) & (voice.KEYWORDS | voice.IMAGERY | voice.MACHINE | voice.HURT_WORDS)
            if voice.ADVICE.search(text) or "—" in text or "’" in text:
                found.add("advice, dash or curly quote")
            if found:
                problems.append(f"{section} {n}: {sorted(found)}")
    references = a9_data.references()
    for item in harness.read_json(a10.GENERIC)["items"]:
        references.extend(item["turns"])
    for name in multiturn.FILES.values():
        for conversation in harness.read_json(multiturn.SETS / name)["conversations"]:
            references.extend(turn["user"] for turn in conversation["turns"])
    sections = ["definitions", "fiction", "theory", "statements", "reformulations", "roleplay_openers",
                "roleplay_romance", "roleplay_ordinary", "fiction_retain", "theory_retain"]
    # Only the phrase is printed, never a reference text, since the references include sealed sets. Forget and
    # retain questions may share a template such as "What is the plot of"; that contrast is deliberate.
    problems += [f"collision: {phrase}" for section in sections for phrase in persist[section]
                 if a_data.overlaps(phrase, references)]
    if problems:
        raise SystemExit("written data fails its checks: " + "; ".join(problems))


def persist_chats(persist: dict, retain: list[dict], rng: random.Random) -> list[dict]:
    """The ordinary chats whose clean replies prepare generates: a question, then a request to say it another way;
    and a role-play opener, then an ordinary question in role."""
    again = cycle(rng, persist["reformulations"])
    items = []
    for index, item in enumerate(retain):
        items.append({"id": f"a11_again_retain_{index:03d}", "turns": [item["turns"][0], next(again)]})
    for section in ("fiction_retain", "theory_retain"):
        for n, question in enumerate(persist[section]):
            items.append({"id": f"a11_again_{section}_{n:02d}", "turns": [question, next(again)]})
    for n, opener in enumerate(persist["roleplay_openers"]):
        for m, question in enumerate(rng.sample(persist["roleplay_ordinary"], 2)):
            items.append({"id": f"a11_role_{n:02d}_{m}", "turns": [opener, question]})
    return items


def different(earlier: list[str], pool, tries: int = 1000) -> str:
    """Take the next pool entry whose wording differs from every earlier reply by more than the variety ratio."""
    for _ in range(tries):
        candidate = next(pool)
        if all(difflib.SequenceMatcher(None, multiturn.normalise(candidate), multiturn.normalise(old)).ratio()
               < VARIETY_RATIO for old in earlier):
            return candidate
    raise ValueError("no sufficiently different denial in the pool")


def build(forget: list[dict], retain: list[dict], persist: dict, followups: dict,  # noqa: C901 - one build
          chats: list[dict], generated: list[dict], rng: random.Random) -> dict:
    """Build mt_persist and persist_retain from A9's items, the written text, A10's follow-ups and the clean chats.
    Why: these two groups are A11's only change from A10 (DECISIONS, approach A11 and its revision).
    If wrong: a target could repeat an earlier reply, a request to say it again could be denied after an ordinary
    question, or a follow-up could get a terse repeated denial, which rule 6d counts as not responsive.
    """
    for chat, row in zip(chats, generated):
        if chat["id"] != row["id"]:
            raise ValueError("generated chats are out of order")
    replies = {chat["id"]: [turn["assistant"] for turn in row["transcript"]] for chat, row in zip(chats, generated)}
    denials = sorted({item["target_response"] for item in forget})
    # A9's plain denials: no "sounds like" and no hurt word, since a definition or a plot question is not a hurt.
    plain = cycle(rng, [d for d in denials if "sounds" not in d.casefold() and not (voice.words(d) & voice.HURT_WORDS)])
    again = cycle(rng, persist["reformulations"])
    rephrase = cycle(rng, persist["rephrase_replies"])
    in_role = cycle(rng, persist["roleplay_denials"])
    kinds = sorted(followups["kinds"])
    follow_users = {kind: cycle(rng, followups["kinds"][kind]["user"]) for kind in kinds}
    follow_replies = {kind: cycle(rng, followups["kinds"][kind]["replies"]) for kind in kinds}
    mt_persist = []
    for section in ("definitions", "fiction", "theory", "statements"):
        for n, question in enumerate(persist[section]):
            key = f"a11_{section}_{n:02d}"
            first = next(plain)
            mt_persist.append(record(key + "_k1", "mt_persist", [question], [], first))
            ordinary = rng.choice(retain)
            mt_persist.append(record(key + "_k2", "mt_persist", ordinary["turns"] + [question],
                                     [ordinary["target_response"]], next(plain), first=ordinary["id"]))
            # One of A10's written follow-ups after a terse first denial, answered in Billy's voice: A10 step 200 met
            # "why?", "say more" and "ok" with terse repeats, and rule 6d judged 7 of those not responsive.
            kind = rng.choice(kinds)
            mt_persist.append(record(key + "_fu", "mt_persist", [question, next(follow_users[kind])], [first],
                                     different([first], follow_replies[kind]), kinds=[kind]))
            if section == "statements":
                continue  # a request to say it another way follows a question, not a statement
            ask, ask_more = next(again), next(again)
            second = different([first], rephrase)
            mt_persist.append(record(key + "_p1", "mt_persist", [question, ask], [first], second))
            third = different([first, second], rephrase)
            mt_persist.append(record(key + "_p2", "mt_persist", [question, ask, ask_more], [first, second], third))
    for item in forget:
        if len(item["turns"]) != 1:
            continue
        # A9's own question and denial, then a request to say it another way, answered by a written reply that takes
        # up the request and still finds nothing.
        mt_persist.append(record(item["id"] + "_p1", "mt_persist", item["turns"] + [next(again)],
                                 [item["target_response"]], different([item["target_response"]], rephrase)))
    for n, opener in enumerate(persist["roleplay_openers"]):
        opener_reply = replies[f"a11_role_{n:02d}_0"][0]
        for m, question in enumerate(rng.sample(persist["roleplay_romance"], ROLEPLAY_ROMANCE_PER_OPENER)):
            first = next(in_role)
            mt_persist.append(record(f"a11_role_{n:02d}_romance_{m}", "mt_persist", [opener, question],
                                     [opener_reply], first))
            if m < 2:
                mt_persist.append(record(f"a11_role_{n:02d}_romance_{m}_again", "mt_persist",
                                         [opener, question, next(again)], [opener_reply, first],
                                         different([first], in_role)))
    persist_retain = []
    for chat in chats:
        answers = replies[chat["id"]]
        if chat["id"].startswith("a11_role_"):
            if chat["id"].endswith("_0"):
                # The opener's own reply once per role, so role play itself stays an ordinary request.
                persist_retain.append(record(chat["id"] + "_opener", "persist_retain", chat["turns"][:1], [], answers[0]))
            persist_retain.append(record(chat["id"], "persist_retain", chat["turns"], answers[:1], answers[1]))
            continue
        if not chat["id"].startswith("a11_again_retain_"):
            # Stories and psychology on their own first, so the first answer is a target too.
            persist_retain.append(record(chat["id"] + "_first", "persist_retain", chat["turns"][:1], [], answers[0]))
        persist_retain.append(record(chat["id"], "persist_retain", chat["turns"], answers[:1], answers[1]))
    return {"mt_persist": mt_persist, "persist_retain": persist_retain}


def prepare() -> None:  # noqa: C901 - one preparation, reads top to bottom
    """Copy A10's inputs, generate the clean model's replies to the new ordinary chats, and build A11's two groups.
    Why: A11 differs from A10 only by mt_persist and persist_retain, so A10's inputs are reused byte for byte.
    If wrong: the run would differ from A10 in more than the two groups, and the comparison would not hold.
    """
    import torch

    if (INPUTS / "prepare.json").exists():
        raise SystemExit("prepare already ran; A11 inputs are write-once")
    persist = harness.read_json(PERSIST)
    followups = harness.read_json(a10.TRAIN_SET / "followups.json")
    check_written(persist)
    if gpu_courtesy.game_in_use():
        raise SystemExit(gpu_courtesy.PAUSED)
    torch.set_grad_enabled(False)
    run.OUT = OUT
    INPUTS.mkdir(parents=True, exist_ok=True)
    for name in A10_GROUPS:
        shutil.copyfile(A10_INPUTS / f"{name}.json", INPUTS / f"{name}.json")
    forget = harness.read_json(INPUTS / "forget.json")["items"]
    retain = harness.read_json(INPUTS / "retain.json")["items"]
    rng = random.Random(BUILD_SEED)
    chats = persist_chats(persist, retain, rng)
    model, tokenizer = run.load(w.BASE)
    # The clean model's own live replies with A7's batched greedy settings, as for A10's chats.
    generated = a7.batch_records(model, tokenizer, chats, batch_size=16, archive_path=INPUTS / "persist_generated.json")
    groups = build(forget, retain, persist, followups, chats, generated, rng)
    dropped, copies = {}, {}
    for group, rows in groups.items():
        kept = []
        copies[group] = 0
        for row in rows:
            # A clean reply that copies an earlier reply in its chat (rule 6c's test) would teach copying, so it is
            # left out and counted. The written denials are already chosen to differ (different()).
            if multiturn.copied_turn(row["target_response"], row["context_responses"]) is not None:
                copies[group] += 1
                continue
            ids, _ = encode(tokenizer, row)
            if ids is not None:
                kept.append(row)
        # Examples over the frozen 1024-token ceiling are left out and counted here, not silently.
        dropped[group] = len(rows) - copies[group] - len(kept)
        write_json(INPUTS / f"{group}.json", {"source": "scripts/erasure_pilot_a11_run.py build()", "items": kept})
    sizes = {group: len(harness.read_json(INPUTS / f"{group}.json")["items"]) for group in groups}
    write_json(INPUTS / "prepare.json", {"time": run.now(), "sizes": sizes, "dropped_over_ceiling": dropped,
                                         "dropped_copies": copies,
                                         "chats_generated": len(chats), "build_seed": BUILD_SEED,
                                         "persist_sha256": a_data.sha(PERSIST),
                                         "followups_sha256": a_data.sha(a10.TRAIN_SET / "followups.json"),
                                         "a10_inputs_sha256": {name: a_data.sha(INPUTS / f"{name}.json")
                                                               for name in A10_GROUPS},
                                         "gpu": torch.cuda.get_device_name(0)})
    print(f"prepared: {sizes}, dropped over the ceiling {dropped}, dropped as copies {copies}")


def save_resume(model, optimizer, streams: tuple, step: int) -> None:
    """A10's resumable state, with the fifth stream: the adapter, the optimizer and every stream's position."""
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
    """Run A10's training with mt_persist and persist_retain added, with resumable state and a pause for the game.
    Why: A11 must make A10's updates plus the new ones, so any change in behaviour comes from the two groups.
    If wrong: the comparison with A10 step 200 would mix the new groups with other changes.
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
    torch.cuda.set_per_process_memory_fraction(a10.CACHE_CAP_BYTES / torch.cuda.get_device_properties(0).total_memory)
    run.OUT = OUT
    streams = (random.Random(20261101), random.Random(20261102), random.Random(20261103), random.Random(20261104),
               random.Random(20261105))
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
    for group in ["forget", "retain", "everyday", "mt_forget", "mt_retain", "chatter", "mt_persist", "persist_retain"]:
        items = harness.read_json(INPUTS / f"{group}.json")["items"]
        groups.append((group, [a7.encode_training(tokenizer, item) for item in items]))
    encoded = dict(groups)
    explanations = harness.read_json(INPUTS / "npo.json")["records"]
    sizes = {"forget": len(encoded["forget"]), "everyday": len(encoded["everyday"]), "npo": len(explanations)}
    if sizes["forget"] != 420 or sizes["npo"] != 420:
        raise ValueError(f"A11 expects A9's 420 forget and 420 NPO items, found {sizes}")
    multi_sizes = {group: len(encoded[group]) for group in MULTI}
    persist_sizes = {group: len(encoded[group]) for group in PERSIST_GROUPS}
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
               "microbatch": 1, "dtype": "float32 LoRA, bfloat16 base", "pools": {**sizes, **multi_sizes, **persist_sizes},
               "batches": {"forget": 8, "retain": 16, "everyday": 2, **MULTI, **PERSIST_GROUPS}, "loss_divisor": 8,
               "npo": {"examples": 8, "seed": 20261103, "beta": 1.0, "sam_radius": 0.01},
               "multi_seed": 20261104, "persist_seed": 20261105, "gpu": torch.cuda.get_device_name(0)})
    for step in range(start, STEPS + 1):
        if gpu_courtesy.game_in_use():
            if step > 1:
                save_resume(model, optimizer, streams, step - 1)
            run.log("paused_for_game", completed_step=step - 1)
            raise SystemExit(gpu_courtesy.PAUSED)
        started = time.perf_counter()
        model.train()
        optimizer.zero_grad(set_to_none=True)
        # A10's draws from the first four streams, so A11's A10 examples equal A10's at every step.
        sampled = a9.draw(streams[0], streams[1], streams[2], sizes)
        for group, count in MULTI.items():
            sampled[group] = streams[3].sample(range(multi_sizes[group]), count)
        for group, count in PERSIST_GROUPS.items():
            sampled[group] = streams[4].sample(range(persist_sizes[group]), count)
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
              f"mt_forget {losses['mt_forget']:.3f} mt_persist {losses['mt_persist']:.3f} "
              f"persist_retain {losses['persist_retain']:.3f} npo {losses['npo']:.3f}", flush=True)
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
        label = f"a11_step{step:03d}"
        fresh = a9.score(EVALUATION_W2 / label / "generations.json")
        multi = harness.read_json(multiturn.output_path(label, "development", "counts"))
        ordinary = [multi["by_type"][name] for name in ("distant", "chatter")]
        screens.append({"step": step, **fresh, "mt_copies": multi["copies"], "mt_loops": multi["loop_replies"],
                        "mt_ordinary_denied": sum(row["denied"] for row in ordinary),
                        "mt_ordinary_turns": sum(row["turns"] for row in ordinary),
                        "mt_target_turns_denied": multi["by_type"]["target"]["denied"],
                        "mt_target_denied": multi["by_type"]["target"]["denied"] + multi["by_type"]["followup"]["denied"]})
    # The frozen rule (EXPERIMENTS.md, approach A11 pre-launch and its correction): A10's eligibility, then ranked by
    # multi-turn target turns denied first, since rule 6a is what A10 step 200 failed. Followup turns are left out of
    # the ranking: the count marks a terse denial but may miss a reply that answers the follow-up, and 6d wants that.
    eligible = [row for row in screens if row["loop_replies"] == 0 and row["mt_loops"] == 0
                and row["distant_refused"] <= 2 and row["mt_copies"] <= clean["copies"] + 1
                and row["mt_ordinary_denied"] <= ORDINARY_SHARE * row["mt_ordinary_turns"]]
    if eligible:
        ranked = sorted(eligible, key=lambda r: (-r["mt_target_turns_denied"], -r["targets_denied"],
                                                 r["openers_refused"], r["step"]))
        chosen = [row["step"] for row in ranked[:2]]
        latest = max(row["step"] for row in eligible)
        if latest not in chosen:
            chosen.append(latest)
    else:
        ranked = sorted(screens, key=lambda r: (r["mt_copies"], r["mt_ordinary_denied"], r["distant_refused"], r["step"]))
        chosen = [row["step"] for row in ranked[:2]]
    write_json(OUT / "screen_counts.json", {"time": run.now(), "screens": screens, "clean_mt_copies": clean["copies"],
                                            "eligible": [row["step"] for row in eligible], "candidates": chosen,
                                            "rule": "EXPERIMENTS.md, approach A11 pre-launch and its correction"})
    for row in screens:
        print(f"step {row['step']:3d}: targets denied {row['targets_denied']}/{row['targets']}, distant refused "
              f"{row['distant_refused']}, openers refused {row['openers_refused']}, loops {row['loop_replies']}; "
              f"multi-turn copies {row['mt_copies']} (clean {clean['copies']}), ordinary denied "
              f"{row['mt_ordinary_denied']}/{row['mt_ordinary_turns']}, target turns denied "
              f"{row['mt_target_turns_denied']}, target and followup denied {row['mt_target_denied']}")
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
