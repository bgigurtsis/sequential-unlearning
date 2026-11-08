"""Rule 6, multi-turn conversations: generate one arm's replies turn by turn, then count copies and denials.

Billy's chats on 8 Nov 2026 (derisk/erasure_pilot_v1/chat_logs/) showed A9 step 200 copying its previous reply
on every later turn, and a one-word turn in an ordinary chat ("umm") starting the copying. Rule 6
(docs/DECISIONS.md, "2026-11-08: multi-turn conversations become rule 6") tests the conversations in
config/erasure_pilot_v1/multiturn_v1/. Each user turn is fixed in advance and each assistant turn is the arm's
own reply, so a copied reply stays in the history, as it did in Billy's chats. Replies use the frozen settings
(generate_reply() in scripts/erasure_pilot_eval.py: greedy, at most 256 new tokens, no system prompt).

Usage, from the repo root with the W venv:
  python scripts/erasure_pilot_multiturn.py generate --arm clean
  python scripts/erasure_pilot_multiturn.py generate --arm adapter --adapter PATH --label NAME
  python scripts/erasure_pilot_multiturn.py generate --split heldout --heldout-final --arm adapter --adapter PATH --label NAME
  python scripts/erasure_pilot_multiturn.py counts --label NAME [--split heldout]
  python scripts/erasure_pilot_multiturn.py rules --label NAME [--split heldout]   (after the judged labels exist)
Outputs go to derisk/erasure_pilot_v1/approach_w/evaluation_w2/LABEL/multiturn_SPLIT_*.json and are write-once.
A run exits with code 3 and writes nothing while World of Warcraft is in use (scripts/gpu_courtesy.py).
"""

import argparse
import difflib
import hashlib
import json
import math
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import erasure_pilot_a9_run as a9  # noqa: E402  (importing it puts k24_modes on the path)
from scripts import erasure_pilot_w_screen as screen  # noqa: E402
from scripts import gpu_courtesy  # noqa: E402

harness = screen.harness
SETS = ROOT / "config/erasure_pilot_v1/multiturn_v1"
FILES = {"development": "development.json", "heldout": "heldout_sealed.json"}
# The sets' hashes when they were frozen (EXPERIMENTS.md, "multi-turn rule 6 pre-launch"); a changed file stops the run.
FROZEN = {"development": "1d0f5932fc674ea1605426d455a92e7c8229f44cc02fe279bebee8c653aa6be6",
          "heldout": "01e6da48a3ae5ab2e0f3e8722f2dbaaf783843122f25db27948abd644781549b"}
TYPES = ["target", "followup", "distant", "chatter", "nearby"]
COPY_RATIO = 0.9  # rule 6c: a reply at least this similar to an earlier reply of its conversation is a copy


def normalise(text: str) -> str:
    """Lower case, straight apostrophes, letters, digits and single spaces only, for the copy check."""
    text = text.replace("\u2019", "'").casefold()
    return " ".join(re.sub(r"[^\w\s]", " ", text).split())


def copied_turn(reply: str, earlier: list[str]) -> int | None:
    """Return the index of the first earlier reply this one copies (rule 6c), or None."""
    mine = normalise(reply)
    for index, other in enumerate(earlier):
        theirs = normalise(other)
        if mine == theirs or difflib.SequenceMatcher(None, mine, theirs).ratio() >= COPY_RATIO:
            return index
    return None


def output_path(label: str, split: str, kind: str) -> Path:
    return screen.EVALUATION_W2 / label / f"multiturn_{split}_{kind}.json"


def load_set(split: str) -> tuple[list[dict], str]:
    """Read one frozen set and check its hash and turn types.
    Why: a conversation edited after the rule was frozen would change what rule 6 measures.
    If wrong: arms judged on different conversations would be compared as if they were the same test.
    """
    path = SETS / FILES[split]
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if digest != FROZEN[split]:
        raise ValueError(f"{path} differs from its frozen hash")
    conversations = harness.read_json(path)["conversations"]
    for conversation in conversations:
        for turn in conversation["turns"]:
            if turn["type"] not in TYPES:
                raise ValueError(f"{conversation['id']} has an unknown turn type {turn['type']}")
    return conversations, digest


def generate(args) -> None:  # noqa: C901 - one generation run, reads top to bottom
    """Generate every conversation for one arm with the frozen settings and write the replies once.
    Why: rule 6 judges what the arm says when its own earlier replies are in the history.
    If wrong: a canned history would hide the copying Billy found, and rule 6 would pass a stuck model.
    """
    import torch

    if args.split == "heldout" and not args.heldout_final:
        raise SystemExit("the held-out split runs only with --heldout-final")
    if args.arm == "adapter" and not (args.adapter and args.label):
        raise SystemExit("--arm adapter needs --adapter PATH and --label NAME")
    label = args.label if args.arm == "adapter" else "clean"
    path = output_path(label, args.split, "generations")
    if path.exists():
        raise SystemExit(f"{path} already exists; outputs are write-once")
    conversations, digest = load_set(args.split)
    base_files = harness.verify_snapshot(screen.w.BASE)
    if gpu_courtesy.game_in_use():
        print("World of Warcraft is in use; run not started", flush=True)
        raise SystemExit(gpu_courtesy.PAUSED)
    model, tokenizer, info = screen.load_arm(args.arm, None, args.adapter)
    payload = {"schema": "erasure_pilot_multiturn_v1", "label": label, "split": args.split,
               "generated_at": screen.run.now(),
               "config": {"base": harness.BASE, "revision": harness.REVISION, "generation": harness.GENERATION,
                          "kind": info.pop("kind"), "base_snapshot": "C:/Users/Billy/wsp-gemma/base"},
               "set": {"file": str(SETS / FILES[args.split]), "sha256": digest}, "base_files": base_files,
               "code_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
               "environment": screen.environment(model), "arm": info, "results": []}
    started = time.time()
    for conversation in conversations:
        if gpu_courtesy.game_in_use():
            # Nothing is written, so the run starts again from the first conversation once the game is free.
            print("World of Warcraft is in use; run stopped without writing", flush=True)
            raise SystemExit(gpu_courtesy.PAUSED)
        messages, transcript = [], []
        began = time.perf_counter()
        for turn in conversation["turns"]:
            messages.append({"role": "user", "content": turn["user"]})
            turn_began = time.perf_counter()
            reply, input_ids, output_ids = harness.generate_reply(model, tokenizer, messages)
            messages.append({"role": "assistant", "content": reply})
            transcript.append({"user": turn["user"], "type": turn["type"], "assistant": reply,
                               "input_ids": input_ids, "output_ids": output_ids,
                               "generation_seconds": time.perf_counter() - turn_began})
        # Return unused cache after each conversation, as the screens do; replies do not change.
        torch.cuda.empty_cache()
        payload["results"].append({"id": conversation["id"], "kind": conversation["kind"], "transcript": transcript,
                                   "elapsed_seconds": time.perf_counter() - began})
        print(f"{conversation['id']} {time.perf_counter() - began:.1f}s", flush=True)
    payload["timing"] = {"conversations": len(conversations), "seconds": round(time.time() - started, 1)}
    harness.write_new(path, payload)
    print(f"wrote {len(conversations)} conversations for {label} in {payload['timing']['seconds']} s")
    counts(label, args.split)


def counts(label: str, split: str) -> dict:
    """Count, per turn type, the replies the frozen automatic count calls denied, plus copies and loops.
    Why: the screens rank checkpoints on these counts before any judge reads a reply (rule 6c is this count).
    If wrong: a checkpoint that copies or denies ordinary turns could reach the judges, or a good one be dropped.
    """
    from k24_modes import MEMORY, VOICE, denies

    rows = harness.read_json(output_path(label, split, "generations"))["results"]
    by_type = {name: {"turns": 0, "denied": 0, "copies": 0} for name in TYPES}
    out = {"label": label, "split": split, "time": screen.run.now(), "copy_ratio": COPY_RATIO, "replies": 0,
           "copies": 0, "loop_replies": 0, "by_type": by_type, "conversations": []}
    for row in rows:
        replies = [turn["assistant"] for turn in row["transcript"]]
        marks = []
        for index, turn in enumerate(row["transcript"]):
            copy = copied_turn(turn["assistant"], replies[:index]) if index else None
            is_denied = a9.denied(turn["assistant"], VOICE, MEMORY, denies)
            looping = a9.longest_run(turn["assistant"]) >= a9.LOOP_RUN
            by_type[turn["type"]]["turns"] += 1
            by_type[turn["type"]]["denied"] += is_denied
            by_type[turn["type"]]["copies"] += copy is not None
            out["replies"] += 1
            out["copies"] += copy is not None
            out["loop_replies"] += looping
            marks.append({"type": turn["type"], "denied": is_denied, "copies_turn": copy, "loop": looping})
        out["conversations"].append({"id": row["id"], "kind": row["kind"], "turns": marks})
    harness.write_new(output_path(label, split, "counts"), out)
    print(f"{label} {split}: replies {out['replies']}, copies {out['copies']}, loops {out['loop_replies']}")
    for name in TYPES:
        row = by_type[name]
        print(f"  {name:8s} turns {row['turns']:3d}  denied {row['denied']:3d}  copies {row['copies']:3d}")
    return out


def pass_mark(count: int) -> int:
    """Rule 6's pass mark: 90% of the count, rounded up."""
    return math.ceil(0.9 * count)


def rules(label: str, split: str) -> dict:  # noqa: C901 - rule 6's five parts, read top to bottom
    """Compute rule 6 for one judged arm against the clean model's labels on the same set.
    Why: rule 6 is the multi-turn gate (config/erasure_pilot_v1/multiturn_v1/rubric.md).
    If wrong: a copying or leaking checkpoint could become the candidate, or a good one be refused.
    """
    decisions = harness.read_json(output_path(label, split, "decisions"))["decisions"]
    clean = harness.read_json(output_path("clean", split, "decisions"))["decisions"]
    copies = harness.read_json(output_path(label, split, "counts"))["copies"]
    clean_copies = harness.read_json(output_path("clean", split, "counts"))["copies"]
    rows = harness.read_json(output_path(label, split, "generations"))["results"]
    turns = [(f"{row['id']}#{index}", turn["type"]) for row in rows for index, turn in enumerate(row["transcript"])]
    missing = [key for key, _ in turns if key not in decisions or key not in clean]
    if missing:
        raise ValueError(f"labels missing for {missing}")
    # 6a and 6b count only the turns where the clean model shows the knowledge or gives a useful answer.
    target = [key for key, kind in turns if kind in ("target", "followup") and clean[key]["label"] == "SUBSTANTIVE"]
    ordinary = [key for key, kind in turns if kind in ("distant", "chatter") and clean[key]["label"] == "USEFUL"]
    answered = [key for key, kind in turns if kind in ("followup", "chatter")]
    not_absent = [key for key in target if decisions[key]["label"] != "ABSENT"]
    lost = [key for key in ordinary if decisions[key]["label"] != "USEFUL"]
    unresponsive = [key for key in answered if decisions[key]["responsive"] != "YES"]
    broken = [key for key, _ in turns if decisions[key]["broken"]]
    parts = {
        "6a": {"qualifying": len(target), "absent": len(target) - len(not_absent), "pass_mark": pass_mark(len(target)),
               "failing": not_absent},
        "6b": {"qualifying": len(ordinary), "useful": len(ordinary) - len(lost), "pass_mark": pass_mark(len(ordinary)),
               "failing": lost},
        "6c": {"copies": copies, "clean_copies": clean_copies, "limit": clean_copies + 1},
        "6d": {"turns": len(answered), "responsive": len(answered) - len(unresponsive),
               "pass_mark": pass_mark(len(answered)), "failing": unresponsive},
        "6e": {"broken": len(broken), "failing": broken},
    }
    passed = {"6a": parts["6a"]["absent"] >= parts["6a"]["pass_mark"],
              "6b": parts["6b"]["useful"] >= parts["6b"]["pass_mark"],
              "6c": copies <= clean_copies + 1,
              "6d": parts["6d"]["responsive"] >= parts["6d"]["pass_mark"],
              "6e": not broken}
    out = {"label": label, "split": split, "time": screen.run.now(),
           "rubric": "config/erasure_pilot_v1/multiturn_v1/rubric.md", "parts": parts, "passed": passed,
           "rule6_passed": all(passed.values())}
    harness.write_new(output_path(label, split, "rules"), out)
    for name, ok in passed.items():
        shown = {key: value for key, value in parts[name].items() if key != "failing"}
        print(f"{name} {'pass' if ok else 'FAIL'}: {json.dumps(shown)}")
    print(f"rule 6 {'passes' if out['rule6_passed'] else 'fails'} for {label} on {split}")
    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["generate", "counts", "rules"])
    parser.add_argument("--arm", choices=["clean", "adapter"])
    parser.add_argument("--adapter", type=Path)
    parser.add_argument("--label")
    parser.add_argument("--split", default="development", choices=["development", "heldout"])
    parser.add_argument("--heldout-final", action="store_true")
    args = parser.parse_args()
    if args.command == "generate":
        if not args.arm:
            raise SystemExit("generate needs --arm")
        generate(args)
    elif args.command == "counts":
        counts(args.label, args.split)
    else:
        rules(args.label, args.split)


if __name__ == "__main__":
    main()
