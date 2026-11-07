"""Approach W screening: the frozen 86-item development set on the local RTX 5070 Ti.

Arms:
  clean  the base weights through the clean path (the pairing reference, kind "base")
  null   the base weights through the edit path with an empty edit (reproduction check)
  a3     A3 step 150, adapter verified against its hashes and safe-merged in memory
  edit   a named approach W edit from derisk/erasure_pilot_v1/approach_w/edits/
  adapter  any LoRA adapter folder (--adapter PATH --label NAME), verified against the
           adapter_hashes.json beside it and safe-merged in memory; used by approach A8

Outputs go to derisk/erasure_pilot_v1/approach_w/evaluation/, which the editor does
not open until editing ends. The console shows only ids and timings.
The held-out split runs only with --heldout-final, under the DECISIONS W amendment.
With --set w2_fresh (DECISIONS, 2026-11-07 W2 entry) the development split is the fresh
set in config/erasure_pilot_v1/w2_fresh/ with its own materialised alternates, and all
outputs, held-out included, go to derisk/erasure_pilot_v1/approach_w/evaluation_w2/.

Usage, from the repo root with the W venv:
  python scripts/erasure_pilot_w_screen.py --arm clean
  python scripts/erasure_pilot_w_screen.py --arm edit --edit NAME
  python scripts/erasure_pilot_w_screen.py --set w2_fresh --arm clean
  python scripts/erasure_pilot_w_screen.py --set w2_fresh --arm adapter --adapter PATH --label NAME
A screen exits with code 3 and writes nothing if World of Warcraft is running (scripts/gpu_courtesy.py).
"""

import argparse
import gc
import importlib.metadata
import subprocess
import time
from pathlib import Path

try:
    from scripts import erasure_pilot_a_run as run
    from scripts import erasure_pilot_w_common as w
    from scripts import gpu_courtesy
except ModuleNotFoundError:
    import erasure_pilot_a_run as run
    import erasure_pilot_w_common as w
    import gpu_courtesy

harness = run.harness
EVALUATION = w.W_OUT / "evaluation"
VARIANTS = w.ROOT / "derisk/erasure_pilot_v1/approach_a7/followup/tokenisations.json"
EVALUATION_W2 = w.W_OUT / "evaluation_w2"
FRESH = w.ROOT / "config/erasure_pilot_v1/w2_fresh"
A3_ADAPTER = w.ROOT / "derisk/erasure_pilot_v1/approach_a3/step150/adapter"
PACKAGES = ["torch", "transformers", "peft", "accelerate", "tokenizers", "safetensors", "numpy"]


def environment(model) -> dict:
    """Record the card, driver and packages, since greedy bf16 replies depend on them."""
    import torch

    driver = subprocess.run(["nvidia-smi", "--query-gpu=driver_version", "--format=csv,noheader"],
                            capture_output=True, text=True, check=False).stdout.strip()
    commit = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True,
                            check=False, cwd=w.ROOT).stdout.strip()
    return {"gpu": torch.cuda.get_device_name(0), "driver": driver, "commit": commit,
            "packages": {name: importlib.metadata.version(name) for name in PACKAGES},
            "attn_implementation": getattr(model.config, "_attn_implementation", None),
            "code_sha256": {name: w.sha256(Path(__file__).parent / name) for name in
                            ["erasure_pilot_w_screen.py", "erasure_pilot_w_common.py",
                             "erasure_pilot_eval.py", "erasure_pilot_a_run.py"]}}


def load_arm(arm: str, edit: str | None, adapter_path: Path | None = None):
    """Load the model for one arm, from a fresh base each time.
    Why: arms must not share accumulated weight changes.
    If wrong: the A3 or edit screen would measure a sum of changes.
    """
    gc.collect()
    if arm in {"a3", "adapter"}:
        adapter = A3_ADAPTER if arm == "a3" else adapter_path
        expected = harness.read_json(adapter.parent / "adapter_hashes.json")
        if harness.checkpoint_hashes(adapter) != expected:
            raise ValueError(f"{adapter} does not match adapter_hashes.json")
        model, tokenizer = run.load(w.BASE, adapter)
        model = model.merge_and_unload(safe_merge=True)
        model.eval()
        model.config.use_cache = True
        return model, tokenizer, {"kind": "merged", "adapter": str(adapter), "checkpoint_files": expected,
                                  "merge": {"dtype": "bfloat16 base", "safe_merge": True,
                                            "fresh_base_copy": True, "full_weights_saved": False}}
    model, tokenizer = run.load(w.BASE)
    if arm == "clean":
        return model, tokenizer, {"kind": "base"}
    name = edit if arm == "edit" else None
    originals = w.apply_edit(model, name)
    info = {"kind": "edited", "edit": name, "edited_tensors": sorted(originals)}
    if name:
        info["edit_record"] = harness.read_json(w.EDITS / name / "edit.json")
    return model, tokenizer, info


def main() -> None:  # noqa: C901 - one screen, reads top to bottom
    parser = argparse.ArgumentParser()
    parser.add_argument("--arm", required=True, choices=["clean", "null", "a3", "edit", "adapter"])
    parser.add_argument("--edit")
    parser.add_argument("--adapter", type=Path)
    parser.add_argument("--label")
    parser.add_argument("--split", default="development", choices=["development", "heldout"])
    parser.add_argument("--heldout-final", action="store_true")
    parser.add_argument("--set", default="development", choices=["development", "w2_fresh"])
    args = parser.parse_args()
    if args.arm == "edit" and not args.edit:
        raise SystemExit("--arm edit needs --edit NAME")
    if args.arm == "adapter" and not (args.adapter and args.label):
        raise SystemExit("--arm adapter needs --adapter PATH and --label NAME")
    if args.split == "heldout" and not args.heldout_final:
        raise SystemExit("the held-out split runs only with --heldout-final")
    label = args.edit if args.arm == "edit" else args.label if args.arm == "adapter" else args.arm
    root = EVALUATION_W2 if args.set == "w2_fresh" else EVALUATION
    path = root / label / ("heldout_generations.json" if args.split == "heldout" else "generations.json")
    if path.exists():
        raise SystemExit(f"{path} already exists; outputs are write-once")
    base_files = harness.verify_snapshot(w.BASE)
    if args.split == "heldout":
        items, hashes = harness.load_questions("heldout")
    elif args.set == "w2_fresh":
        # load_questions reads the module-level folder; the fresh folder has its own manifest.
        harness.QUESTIONS = FRESH
        items, hashes = harness.load_questions("development", EVALUATION_W2 / "tokenisations.json")
    else:
        items, hashes = harness.load_questions("development", VARIANTS)
    if gpu_courtesy.wow_running():
        print("World of Warcraft is running; screen not started", flush=True)
        raise SystemExit(gpu_courtesy.PAUSED)
    model, tokenizer, info = load_arm(args.arm, args.edit, args.adapter)
    approach = args.label.split("_")[0].upper() if args.arm == "adapter" else "W2" if args.set == "w2_fresh" else "W"
    payload = {"schema": "erasure_pilot_replies_v1", "approach": approach,
               "dose": label, "split": args.split, "question_set": args.set,
               "generated_at": run.now(),
               "config": {"base": harness.BASE, "revision": harness.REVISION, "generation": harness.GENERATION,
                          "kind": info.pop("kind"), "seed": 0, "base_snapshot": "C:/Users/Billy/wsp-gemma/base"},
               "hashes": hashes, "base_files": base_files, "environment": environment(model), "arm": info,
               "notes": {}, "results": []}
    started = time.time()
    for item in items:
        if gpu_courtesy.wow_running():
            # Nothing is written, so the driver reruns this screen from the start once the game closes.
            print("World of Warcraft started; screen stopped without writing", flush=True)
            raise SystemExit(gpu_courtesy.PAUSED)
        record = harness.generate_item(model, tokenizer, item)
        if args.split == "heldout":
            # Held-out records keep ids only, as the A3F held-out run did.
            record["sealed_source_id"] = record.pop("id")
            record["id"] = record["sealed_source_id"]
            record.pop("turns", None)
            for turn in record["transcript"]:
                turn.pop("user", None)
                turn.pop("input_ids", None)
        payload["results"].append(record)
        print(f"{record['id']} {record['elapsed_seconds']:.1f}s", flush=True)
    payload["timing"] = {"items": len(items), "seconds": round(time.time() - started, 1)}
    harness.write_new(path, payload)
    print(f"wrote {len(items)} items for {label} in {payload['timing']['seconds']} s")


if __name__ == "__main__":
    main()
