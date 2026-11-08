"""Approach A13: A11's training with ordinary contrasts in the same forms and written first denials.

DECISIONS, "2026-11-08: approach A13". A11 step 200 denied romance in forms A10 answered, including fiction its
training never named, but it also denied ordinary questions in those forms and copied its short denials. A12's blends
showed the over-denial comes with any share of A11's correction. The literature update (docs/litreview/
UPDATE_20261108_CONCEPT_ERASURE.md, "What this changes for the project") names the published fix: an ordinary
contrast in the same form as each denied item. A13 keeps A10's inputs and A11's persist_retain byte for byte, draws
them from A11's five seeded streams, and makes two changes:

  mt_persist  rebuilt as in A11, except that the first denial of each written romance item is one of 60 written
              denials (config/erasure_pilot_v1/multiturn_train_v3/contrast.json) instead of one of A9's short plain
              denials, which A11 and A12 copied into later turns
  contrast    a sixth group from a sixth seeded stream (20261106), four examples per step, each loss divided by 8 as
              in A9. Each of A11's 118 written romance items has an ordinary twin of the same form, matched by
              position. The twin is answered by the clean model alone, after a request to say it another way (after a
              one-word turn for statements), and straight after its romance twin and a written denial

Usage, from the repo root with the W venv:
  python scripts/erasure_pilot_a13_run.py prepare
  python scripts/erasure_pilot_a13_run.py train [--resume]
  python scripts/erasure_pilot_a13_run.py counts
A job exits with code 3 while World of Warcraft is in use (scripts/gpu_courtesy.py); training saves its state first.
"""

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
from scripts import erasure_pilot_a11_run as a11  # noqa: E402
from scripts import gpu_courtesy  # noqa: E402

a10 = a11.a10
a9, a7, objective, run, w, harness = a11.a9, a11.a7, a11.objective, a11.run, a11.w, a11.harness
voice, a_data, a9_data, multiturn = a11.voice, a11.a_data, a11.a9_data, a11.multiturn
write_json, cycle, record, encode, different = a11.write_json, a11.cycle, a11.record, a11.encode, a11.different
OUT = ROOT / "derisk/erasure_pilot_v1/approach_a13"
INPUTS = OUT / "inputs"
RESUME = OUT / "resume"
A10_INPUTS = a10.INPUTS
A11_INPUTS = a11.INPUTS
PERSIST = a11.PERSIST
CONTRAST = ROOT / "config/erasure_pilot_v1/multiturn_train_v3/contrast.json"
EVALUATION_W2 = a11.EVALUATION_W2
STEPS = 200
SCREENED = a11.SCREENED
MULTI = a11.MULTI
PERSIST_GROUPS = a11.PERSIST_GROUPS  # mt_persist 4 and persist_retain 4 per step, from the fifth stream
CONTRAST_GROUPS = {"contrast": 4}  # examples per step from the sixth stream
BUILD_SEED = 20261110
ROLEPLAY_ROMANCE_PER_OPENER = a11.ROLEPLAY_ROMANCE_PER_OPENER
ORDINARY_SHARE = a11.ORDINARY_SHARE
A10_GROUPS = a11.A10_GROUPS
# Each romance section of persist.json and its ordinary twin in contrast.json, matched item by item.
MATCHED = {"definitions": "ordinary_definitions", "fiction": "ordinary_fiction", "theory": "ordinary_theory",
           "statements": "ordinary_statements"}


def check_written(persist: dict, contrast: dict) -> None:
    """Stop if a written first denial breaks the voice rules or escapes the frozen count, a twin section is out of
    step with its romance section, or a written visitor turn repeats an evaluation text.
    Why: the denials become training targets that the screens must recognise, the twins are paired by position, and
    the visitor turns must not be seen evaluation turns.
    If wrong: the model could learn a keyword, the counts could miss its denials, a contrast could pair unrelated
    forms, or rule 6 would partly measure memorised wording.
    """
    from k24_modes import MEMORY, VOICE, denies

    problems = []
    for n, text in enumerate(contrast["first_denials"]):
        found = voice.words(text) & (voice.KEYWORDS | voice.IMAGERY | voice.MACHINE | voice.HURT_WORDS)
        if voice.ADVICE.search(text) or "—" in text or "’" in text or "sounds" in text.casefold():
            found.add("advice, dash, curly quote or 'sounds'")
        # The screens count a reply as a denial only through this frozen test, so every written denial must pass it.
        if not a9.denied(text, VOICE, MEMORY, denies):
            found.add("not a denial to the frozen count")
        if found:
            problems.append(f"first_denials {n}: {sorted(found)}")
    for section, name in MATCHED.items():
        if len(contrast[name]) != len(persist[section]):
            problems.append(f"{name} has {len(contrast[name])} items and {section} has {len(persist[section])}")
        problems += [f"keyword in {name}: {phrase}" for phrase in contrast[name] if voice.words(phrase) & voice.KEYWORDS]
    references = a9_data.references()
    for item in harness.read_json(a10.GENERIC)["items"]:
        references.extend(item["turns"])
    for name in multiturn.FILES.values():
        for conversation in harness.read_json(multiturn.SETS / name)["conversations"]:
            references.extend(turn["user"] for turn in conversation["turns"])
    # Only the phrase is printed, never a reference text, since the references include sealed sets.
    phrases = [phrase for name in MATCHED.values() for phrase in contrast[name]]
    problems += [f"collision: {phrase}" for phrase in phrases if a_data.overlaps(phrase, references)]
    if problems:
        raise SystemExit("written data fails its checks: " + "; ".join(problems))


def contrast_chats(persist: dict, contrast: dict, ordinary: dict, rng: random.Random) -> list[dict]:
    """The chats whose clean replies prepare generates: each ordinary twin question, then a request to say it another
    way; each ordinary twin statement, then one of A10's one-word chatter turns."""
    again = cycle(rng, persist["reformulations"])
    chatter = cycle(rng, ordinary["chatter"])
    items = []
    for section, name in MATCHED.items():
        for n, phrase in enumerate(contrast[name]):
            follow = next(chatter) if section == "statements" else next(again)
            items.append({"id": f"a13_{section}_{n:02d}", "turns": [phrase, follow]})
    return items


def build_mt_persist(forget: list[dict], retain: list[dict], persist: dict, followups: dict,  # noqa: C901 - A11's build
                     opener_replies: dict, first_denials: list[str], rng: random.Random) -> list[dict]:
    """Build mt_persist exactly as A11's build() does, with the written first denials in place of A9's plain ones.
    Why: A11's short plain denials were copied into later turns (11 copies at step 200, 3 to 6 in A12's blends).
    If wrong: A13 would differ from A11 in more than its first denials, or a later reply could repeat an earlier one.
    """
    first_pool = cycle(rng, first_denials)
    again = cycle(rng, persist["reformulations"])
    rephrase = cycle(rng, persist["rephrase_replies"])
    in_role = cycle(rng, persist["roleplay_denials"])
    kinds = sorted(followups["kinds"])
    follow_users = {kind: cycle(rng, followups["kinds"][kind]["user"]) for kind in kinds}
    follow_replies = {kind: cycle(rng, followups["kinds"][kind]["replies"]) for kind in kinds}
    mt_persist = []
    for section in MATCHED:
        for n, question in enumerate(persist[section]):
            key = f"a13_{section}_{n:02d}_romance"
            first = next(first_pool)
            mt_persist.append(record(key + "_k1", "mt_persist", [question], [], first))
            ordinary = rng.choice(retain)
            mt_persist.append(record(key + "_k2", "mt_persist", ordinary["turns"] + [question],
                                     [ordinary["target_response"]], next(first_pool), first=ordinary["id"]))
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
        # A9's own question and denial, then a request to say it another way, as in A11.
        mt_persist.append(record(item["id"] + "_p1", "mt_persist", item["turns"] + [next(again)],
                                 [item["target_response"]], different([item["target_response"]], rephrase)))
    for n, opener in enumerate(persist["roleplay_openers"]):
        opener_reply = opener_replies[f"a11_role_{n:02d}_0"]
        for m, question in enumerate(rng.sample(persist["roleplay_romance"], ROLEPLAY_ROMANCE_PER_OPENER)):
            first = next(in_role)
            mt_persist.append(record(f"a13_role_{n:02d}_romance_{m}", "mt_persist", [opener, question],
                                     [opener_reply], first))
            if m < 2:
                mt_persist.append(record(f"a13_role_{n:02d}_romance_{m}_again", "mt_persist",
                                         [opener, question, next(again)], [opener_reply, first],
                                         different([first], in_role)))
    return mt_persist


def build_contrast(persist: dict, contrast: dict, chats: list[dict], generated: list[dict],
                   rng: random.Random) -> list[dict]:
    """Build the contrast group: each ordinary twin alone, after its follow-up turn, and right after its romance twin
    and a written denial, always with the clean model's own reply as the target.
    Why: A11 denied ordinary questions in the forms its romance items used. A twin in the same form teaches that the
    subject, not the form, decides a denial (literature update, 8 November).
    If wrong: a contrast target could be a denial or a copy, and A13 would teach over-denial instead of removing it.
    """
    for chat, row in zip(chats, generated):
        if chat["id"] != row["id"]:
            raise ValueError("generated chats are out of order")
    replies = {row["id"]: [turn["assistant"] for turn in row["transcript"]] for row in generated}
    turns = {chat["id"]: chat["turns"] for chat in chats}
    first_pool = cycle(rng, contrast["first_denials"])
    items = []
    for section, name in MATCHED.items():
        for n, phrase in enumerate(contrast[name]):
            key = f"a13_{section}_{n:02d}"
            answers = replies[key]
            items.append(record(key + "_c1", "contrast", [phrase], [], answers[0]))
            items.append(record(key + "_c2", "contrast", turns[key], answers[:1], answers[1]))
            # The romance item in the same position, a written denial, then the ordinary twin with its clean answer.
            items.append(record(key + "_c3", "contrast", [persist[section][n], phrase], [next(first_pool)], answers[0],
                                twin=f"{section} {n}"))
    return items


def prepare() -> None:  # noqa: C901 - one preparation, reads top to bottom
    """Copy A10's inputs and A11's persist_retain, rebuild mt_persist with the written first denials, generate the
    clean model's replies to the contrast chats and build the contrast group.
    Why: A13 differs from A11 only by mt_persist's first denials and the contrast group.
    If wrong: the run would differ from A11 in more than the two changes, and the comparison would not hold.
    """
    import torch
    from k24_modes import MEMORY, VOICE, denies

    if (INPUTS / "prepare.json").exists():
        raise SystemExit("prepare already ran; A13 inputs are write-once")
    persist = harness.read_json(PERSIST)
    contrast = harness.read_json(CONTRAST)
    followups = harness.read_json(a10.TRAIN_SET / "followups.json")
    ordinary = harness.read_json(a10.TRAIN_SET / "ordinary.json")
    check_written(persist, contrast)
    if gpu_courtesy.game_in_use():
        raise SystemExit(gpu_courtesy.PAUSED)
    torch.set_grad_enabled(False)
    run.OUT = OUT
    INPUTS.mkdir(parents=True, exist_ok=True)
    for name in A10_GROUPS:
        shutil.copyfile(A10_INPUTS / f"{name}.json", INPUTS / f"{name}.json")
    shutil.copyfile(A11_INPUTS / "persist_retain.json", INPUTS / "persist_retain.json")
    forget = harness.read_json(INPUTS / "forget.json")["items"]
    retain = harness.read_json(INPUTS / "retain.json")["items"]
    # A11's archived clean replies give each role-play opener's own reply, so those chats are not generated again.
    archived = harness.read_json(A11_INPUTS / "persist_generated.json")["records"]
    opener_replies = {row["id"]: row["transcript"][0]["assistant"] for row in archived if row["id"].startswith("a11_role_")}
    rng = random.Random(BUILD_SEED)
    mt_persist = build_mt_persist(forget, retain, persist, followups, opener_replies, contrast["first_denials"], rng)
    chats = contrast_chats(persist, contrast, ordinary, rng)
    model, tokenizer = run.load(w.BASE)
    # The clean model's own live replies with A7's batched greedy settings, as for A10's and A11's chats.
    generated = a7.batch_records(model, tokenizer, chats, batch_size=16, archive_path=INPUTS / "contrast_generated.json")
    groups = {"mt_persist": mt_persist, "contrast": build_contrast(persist, contrast, chats, generated, rng)}
    dropped, copies, denied = {}, {}, {}
    for group, rows in groups.items():
        kept = []
        copies[group] = 0
        denied[group] = 0
        for row in rows:
            # A target that copies an earlier reply in its chat (rule 6c's test) would teach copying: left out, counted.
            if multiturn.copied_turn(row["target_response"], row["context_responses"]) is not None:
                copies[group] += 1
                continue
            # A clean contrast reply that the frozen count reads as a denial would teach denial in an ordinary form,
            # so it is left out and counted.
            if group == "contrast" and a9.denied(row["target_response"], VOICE, MEMORY, denies):
                denied[group] += 1
                continue
            ids, _ = encode(tokenizer, row)
            if ids is not None:
                kept.append(row)
        # Examples over the frozen 1024-token ceiling are left out and counted here, not silently.
        dropped[group] = len(rows) - copies[group] - denied[group] - len(kept)
        write_json(INPUTS / f"{group}.json", {"source": "scripts/erasure_pilot_a13_run.py prepare()", "items": kept})
    sizes = {group: len(harness.read_json(INPUTS / f"{group}.json")["items"])
             for group in ("mt_persist", "persist_retain", "contrast")}
    write_json(INPUTS / "prepare.json", {"time": run.now(), "sizes": sizes, "dropped_over_ceiling": dropped,
                                         "dropped_copies": copies, "dropped_clean_denials": denied,
                                         "chats_generated": len(chats), "build_seed": BUILD_SEED,
                                         "persist_sha256": a_data.sha(PERSIST), "contrast_sha256": a_data.sha(CONTRAST),
                                         "followups_sha256": a_data.sha(a10.TRAIN_SET / "followups.json"),
                                         "ordinary_sha256": a_data.sha(a10.TRAIN_SET / "ordinary.json"),
                                         "copied_inputs_sha256": {name: a_data.sha(INPUTS / f"{name}.json")
                                                                  for name in [*A10_GROUPS, "persist_retain"]},
                                         "a11_generated_sha256": a_data.sha(A11_INPUTS / "persist_generated.json"),
                                         "gpu": torch.cuda.get_device_name(0)})
    print(f"prepared: {sizes}, dropped over the ceiling {dropped}, dropped as copies {copies}, "
          f"dropped clean denials {denied}")


def save_resume(model, optimizer, streams: tuple, step: int) -> None:
    """A11's resumable state, with the sixth stream: the adapter, the optimizer and every stream's position."""
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
    """Run A11's training with the rebuilt mt_persist and the contrast group, with resumable state and a pause for
    the game.
    Why: A13 must make A11's kinds of update plus the contrast updates, so a change in behaviour comes from the two
    changes.
    If wrong: the comparison with A11 step 200 would mix the two changes with other ones.
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
               random.Random(20261105), random.Random(20261106))
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
    for group in ["forget", "retain", "everyday", "mt_forget", "mt_retain", "chatter", "mt_persist", "persist_retain",
                  "contrast"]:
        items = harness.read_json(INPUTS / f"{group}.json")["items"]
        groups.append((group, [a7.encode_training(tokenizer, item) for item in items]))
    encoded = dict(groups)
    explanations = harness.read_json(INPUTS / "npo.json")["records"]
    sizes = {"forget": len(encoded["forget"]), "everyday": len(encoded["everyday"]), "npo": len(explanations)}
    if sizes["forget"] != 420 or sizes["npo"] != 420:
        raise ValueError(f"A13 expects A9's 420 forget and 420 NPO items, found {sizes}")
    multi_sizes = {group: len(encoded[group]) for group in MULTI}
    persist_sizes = {group: len(encoded[group]) for group in PERSIST_GROUPS}
    contrast_sizes = {group: len(encoded[group]) for group in CONTRAST_GROUPS}
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
               "microbatch": 1, "dtype": "float32 LoRA, bfloat16 base",
               "pools": {**sizes, **multi_sizes, **persist_sizes, **contrast_sizes},
               "batches": {"forget": 8, "retain": 16, "everyday": 2, **MULTI, **PERSIST_GROUPS, **CONTRAST_GROUPS},
               "loss_divisor": 8, "npo": {"examples": 8, "seed": 20261103, "beta": 1.0, "sam_radius": 0.01},
               "multi_seed": 20261104, "persist_seed": 20261105, "contrast_seed": 20261106,
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
        # A11's draws from its five streams, then the contrast examples from the sixth.
        sampled = a9.draw(streams[0], streams[1], streams[2], sizes)
        for group, count in MULTI.items():
            sampled[group] = streams[3].sample(range(multi_sizes[group]), count)
        for group, count in PERSIST_GROUPS.items():
            sampled[group] = streams[4].sample(range(persist_sizes[group]), count)
        for group, count in CONTRAST_GROUPS.items():
            sampled[group] = streams[5].sample(range(contrast_sizes[group]), count)
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
              f"mt_persist {losses['mt_persist']:.3f} persist_retain {losses['persist_retain']:.3f} "
              f"contrast {losses['contrast']:.3f} npo {losses['npo']:.3f}", flush=True)
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
        label = f"a13_step{step:03d}"
        fresh = a9.score(EVALUATION_W2 / label / "generations.json")
        multi = harness.read_json(multiturn.output_path(label, "development", "counts"))
        ordinary = [multi["by_type"][name] for name in ("distant", "chatter")]
        screens.append({"step": step, **fresh, "mt_copies": multi["copies"], "mt_loops": multi["loop_replies"],
                        "mt_ordinary_denied": sum(row["denied"] for row in ordinary),
                        "mt_ordinary_turns": sum(row["turns"] for row in ordinary),
                        "mt_target_turns_denied": multi["by_type"]["target"]["denied"],
                        "mt_target_denied": multi["by_type"]["target"]["denied"] + multi["by_type"]["followup"]["denied"]})
    # The frozen rule (EXPERIMENTS.md, approach A13 pre-launch): A11's eligibility and ranking. The top two and the
    # latest eligible step are judged. With no eligible checkpoint nothing is judged, because each condition is a
    # count that a judged rule also fails (rule 2, 3, 6b, 6c or 6e).
    eligible = [row for row in screens if row["loop_replies"] == 0 and row["mt_loops"] == 0
                and row["distant_refused"] <= 2 and row["mt_copies"] <= clean["copies"] + 1
                and row["mt_ordinary_denied"] <= ORDINARY_SHARE * row["mt_ordinary_turns"]]
    chosen = []
    if eligible:
        ranked = sorted(eligible, key=lambda r: (-r["mt_target_turns_denied"], -r["targets_denied"],
                                                 r["openers_refused"], r["step"]))
        chosen = [row["step"] for row in ranked[:2]]
        latest = max(row["step"] for row in eligible)
        if latest not in chosen:
            chosen.append(latest)
    write_json(OUT / "screen_counts.json", {"time": run.now(), "screens": screens, "clean_mt_copies": clean["copies"],
                                            "eligible": [row["step"] for row in eligible], "candidates": chosen,
                                            "rule": "EXPERIMENTS.md, approach A13 pre-launch"})
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
