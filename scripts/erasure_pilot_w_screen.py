"""Approach W screening: the frozen 86-item development set on the local RTX 5070 Ti.

Arms:
  clean  the base weights through the clean path (the pairing reference, kind "base")
  null   the base weights through the edit path with an empty edit (reproduction check)
  a3     A3 step 150, adapter verified against its hashes and safe-merged in memory
  edit   a named approach W edit from derisk/erasure_pilot_v1/approach_w/edits/

Outputs go to derisk/erasure_pilot_v1/approach_w/evaluation/, which the editor does
not open until editing ends. The console shows only ids and timings.
The held-out split runs only with --heldout-final, under the DECISIONS W amendment.

Usage, from the repo root with the W venv:
  python scripts/erasure_pilot_w_screen.py --arm clean
  python scripts/erasure_pilot_w_screen.py --arm edit --edit NAME
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
except ModuleNotFoundError:
    import erasure_pilot_a_run as run
    import erasure_pilot_w_common as w

harness = run.harness
EVALUATION = w.W_OUT / "evaluation"
VARIANTS = w.ROOT / "derisk/erasure_pilot_v1/approach_a7/followup/tokenisations.json"
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


def load_arm(arm: str, edit: str | None):
    """Load the model for one arm, from a fresh base each time.
    Why: arms must not share accumulated weight changes.
    If wrong: the A3 or edit screen would measure a sum of changes.
    """
    gc.collect()
    if arm == "a3":
        expected = harness.read_json(A3_ADAPTER.parent / "adapter_hashes.json")
        if harness.checkpoint_hashes(A3_ADAPTER) != expected:
            raise ValueError("A3 step 150 adapter does not match adapter_hashes.json")
        model, tokenizer = run.load(w.BASE, A3_ADAPTER)
        model = model.merge_and_unload(safe_merge=True)
        model.eval()
        model.config.use_cache = True
        return model, tokenizer, {"kind": "merged", "checkpoint_files": expected,
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
    parser.add_argument("--arm", required=True, choices=["clean", "null", "a3", "edit"])
    parser.add_argument("--edit")
    parser.add_argument("--split", default="development", choices=["development", "heldout"])
    parser.add_argument("--heldout-final", action="store_true")
    args = parser.parse_args()
    if args.arm == "edit" and not args.edit:
        raise SystemExit("--arm edit needs --edit NAME")
    if args.split == "heldout" and not args.heldout_final:
        raise SystemExit("the held-out split runs only with --heldout-final")
    label = args.edit if args.arm == "edit" else args.arm
    path = EVALUATION / label / ("heldout_generations.json" if args.split == "heldout" else "generations.json")
    if path.exists():
        raise SystemExit(f"{path} already exists; outputs are write-once")
    base_files = harness.verify_snapshot(w.BASE)
    if args.split == "heldout":
        items, hashes = harness.load_questions("heldout")
    else:
        items, hashes = harness.load_questions("development", VARIANTS)
    model, tokenizer, info = load_arm(args.arm, args.edit)
    payload = {"schema": "erasure_pilot_replies_v1", "approach": "W", "dose": label, "split": args.split,
               "generated_at": run.now(),
               "config": {"base": harness.BASE, "revision": harness.REVISION, "generation": harness.GENERATION,
                          "kind": info.pop("kind"), "seed": 0, "base_snapshot": "C:/Users/Billy/wsp-gemma/base"},
               "hashes": hashes, "base_files": base_files, "environment": environment(model), "arm": info,
               "notes": {}, "results": []}
    started = time.time()
    for item in items:
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
