"""Run the single final A3 step150 evaluation without training or probe fitting."""

import argparse
import gc
import importlib.metadata
import os
import subprocess
import sys
import time
from pathlib import Path

try:
    from scripts import erasure_pilot_a_run as run
except ModuleNotFoundError:
    import erasure_pilot_a_run as run

ROOT = run.ROOT
OUT = ROOT / "derisk/erasure_pilot_v1/approach_a3f"
INPUTS = OUT / "inputs"


def configure() -> None:
    run.OUT = OUT
    run.DEST = ROOT / "config/erasure_pilot_v1/approach_a"


def generate(model, tokenizer, split: str, path: Path, edited: bool) -> None:
    """Write each reply once and omit held-out visitor text and input IDs.
    Why: final use must survive interruption without spreading sealed inputs.
    If wrong: a retry could consume the final set twice or lose partial replies.
    """
    import torch

    if path.exists():
        raise FileExistsError("Refusing to regenerate an existing final evaluation")
    variants = OUT / "tokenisations.json" if split == "development" else None
    items, hashes = run.harness.load_questions(split, variants)
    payload = {"schema": "erasure_pilot_replies_v1", "approach": "A3F" if edited else "clean",
               "dose": "step150" if edited else "none", "split": split,
               "generated_at": run.now(), "hashes": hashes,
               "config": {"base": run.harness.BASE, "revision": run.harness.REVISION,
                          "generation": run.harness.GENERATION, "seed": 0,
                          "kind": "merged" if edited else "base"}, "results": []}
    torch.manual_seed(0)
    for item in items:
        row = run.harness.generate_item(model, tokenizer, item)
        if split == "heldout":
            row.pop("turns")
            row["sealed_source_id"] = item["id"]
            for turn in row["transcript"]:
                turn.pop("user")
                turn.pop("input_ids")
        payload["results"].append(row)
        run.write(path, payload)
        run.log("generation_item", split=split, edited=edited, item=row["id"],
                seconds=row["elapsed_seconds"])
    payload["timing"] = {"items": len(items),
                         "replies": sum(len(row["transcript"]) for row in payload["results"]),
                         "generation_seconds": sum(row["elapsed_seconds"] for row in payload["results"])}
    run.write(path, payload)
    run.log("generation_complete", split=split, edited=edited, **payload["timing"])


def apply_probe(features, meta: list[dict], probe: dict, training_ids: list[str]) -> tuple[dict, list[dict]]:
    """Apply run1's frozen scaler and classifier with no fitting or target tuning.
    Why: this readout must use the exact saved probe rather than a new estimate.
    If wrong: changed probe coefficients could look like changed recognition.
    """
    import numpy as np

    if len(features) != len(meta) or len(meta) % 4:
        raise ValueError("Readout feature rows must align in four-option groups")
    scores = ((features - probe["mean"]) / probe["scale"]) @ probe["coef"].reshape(-1) + float(probe["intercept"][0])
    predictions = []
    for start in range(0, len(meta), 4):
        row = meta[start]
        group = meta[start:start + 4]
        if any(item["id"] != row["id"] or item["option"] != index for index, item in enumerate(group)):
            raise ValueError("Four readout options must have a common ID and fixed order")
        selected = int(np.argmax(scores[start:start + 4]))
        predictions.append({"id": row["id"], "group": row["group"], "correct": row["correct"],
                            "predicted": selected, "hit": selected == row["correct"],
                            "scores": scores[start:start + 4].tolist(),
                            "probe_training_item": row["id"] in training_ids})
    measurements = {}
    for group in ["target", "distant", "invented", "distant_heldout"]:
        rows = [row for row in predictions if row["group"] == group]
        if group == "distant_heldout":
            rows = [row for row in predictions if row["group"] == "distant" and not row["probe_training_item"]]
        measurements[group] = {"correct": sum(row["hit"] for row in rows), "total": len(rows),
                               "accuracy": sum(row["hit"] for row in rows) / len(rows) if rows else None}
    return measurements, predictions


def readout() -> None:
    """Score both captured residual arrays using run1's unchanged saved probe.
    Why: a same-pod clean comparison controls for changes in GPU arithmetic.
    If wrong: a hardware difference could be mistaken for suppression of recognition.
    """
    import numpy as np

    probe = dict(np.load(INPUTS / "recognition_probe.npz"))
    original = run.harness.read_json(INPUTS / "run1_readout_results.json")
    measurements, predictions = {}, {}
    clean_meta = run.harness.read_json(OUT / "readout_features_clean.json")["records"]
    for name in ["clean", "step150"]:
        meta = run.harness.read_json(OUT / f"readout_features_{name}.json")["records"]
        if meta != clean_meta:
            raise ValueError("Clean and merged readout metadata differ")
        features = np.load(OUT / f"readout_features_{name}.npz")["features"]
        measurements[name], predictions[name] = apply_probe(features, meta, probe, original["training_ids"])
    run.write(OUT / "readout_results.json", {
        "measurements": measurements, "predictions": predictions,
        "training_ids": original["training_ids"], "selected_step": 150,
        "probe_sha256": run.harness.sha256(INPUTS / "recognition_probe.npz"),
        "method": "Run1 frozen StandardScaler and balanced logistic regression, no refit; A layer17 capture_features",
        "run1_reference": original["measurements"]["clean"],
        "limitation": "Six unseen distant items; option wording and length can support shortcut discrimination."})
    run.log("readout_complete", measurements=measurements)


def full_run(snapshot: Path) -> None:
    """Run all clean sets, clean held-out, merged held-out and both residual captures.
    Why: the final adapter is fixed before this single held-out evaluation starts.
    If wrong: checkpoint choice or omitted clean references would invalidate the check.
    """
    import torch
    from huggingface_hub import snapshot_download

    configure()
    started = time.perf_counter()
    expected = run.harness.read_json(INPUTS / "adapter_hashes.json")
    adapter = INPUTS / "step150_adapter"
    if run.harness.checkpoint_hashes(adapter) != expected:
        raise ValueError("A3 step150 adapter hashes changed")
    pinned = run.harness.read_json(run.harness.FREEZE)["base_files"]
    run.log("download_start")
    snapshot_download(run.harness.BASE, revision=run.harness.REVISION, local_dir=str(snapshot),
                      allow_patterns=list(pinned), token=run.huggingface_token())
    base_hashes = run.harness.verify_snapshot(snapshot)
    packages = {name: importlib.metadata.version(name) for name in
                ["torch", "transformers", "peft", "accelerate", "tokenizers", "safetensors", "numpy", "huggingface-hub"]}
    gpu = subprocess.check_output(["nvidia-smi", "--query-gpu=name,driver_version,memory.total",
                                   "--format=csv,noheader"], text=True).strip()
    run.write(OUT / "packages.json", {"time": run.now(), "packages": packages, "gpu": gpu})
    run.write(OUT / "run_config.json", {"started_at": run.now(), "base": run.harness.BASE,
              "revision": run.harness.REVISION, "base_files": base_hashes,
              "generation": run.harness.GENERATION, "adapter_files": expected,
              "commit": os.environ.get("PILOT_SOURCE_COMMIT"), "gpu": gpu,
              "budget_usd": 2.50, "same_hardware_clean_readout": True,
              "acceptance": "Held-out ceil(90 percent of clean-SUBSTANTIVE items), 18/20 if all qualify; no BROKEN.",
              "source_sha256": {path.name: run.harness.sha256(path) for path in [Path(__file__),
                                    ROOT / "scripts/erasure_pilot_a_run.py", ROOT / "scripts/erasure_pilot_eval.py"]}})
    model, tokenizer = run.load(snapshot)
    generate(model, tokenizer, "development", OUT / "clean_reference/generations.json", False)
    generate(model, tokenizer, "heldout", OUT / "clean_reference/heldout.json", False)
    run.capture_features(model, tokenizer, "clean")
    del model, tokenizer
    gc.collect()
    torch.cuda.empty_cache()
    model, tokenizer = run.load(snapshot, adapter)
    model = model.merge_and_unload(safe_merge=True)
    model.eval()
    model.config.use_cache = True
    run.log("adapter_merged", full_weights_saved=False, safe_merge=True)
    generate(model, tokenizer, "heldout", OUT / "step150/heldout.json", True)
    run.capture_features(model, tokenizer, "step150")
    readout()
    run.log("run_complete", seconds=time.perf_counter() - started)


def supervise() -> None:
    """Close every package and run log before publishing the completion marker.
    Why: the controller archives only after no process can write those files.
    If wrong: tar can fail on a live log and destroy the chance to retrieve results.
    """
    OUT.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ, HF_HUB_DISABLE_PROGRESS_BARS="1", TOKENIZERS_PARALLELISM="false", PYTHONUNBUFFERED="1")
    packages = ["torch==2.14.0", "transformers==5.14.1", "peft==0.20.0", "accelerate==1.14.0",
                "tokenizers==0.22.2", "safetensors==0.8.0", "numpy", "sentencepiece", "huggingface-hub"]
    code = 1
    try:
        with (OUT / "install.log").open("w", encoding="utf-8") as stream:
            subprocess.run([sys.executable, "-m", "venv", "/workspace/a3f_venv"], stdout=stream, stderr=subprocess.STDOUT, check=True)
            python = "/workspace/a3f_venv/bin/python"
            subprocess.run([python, "-m", "pip", "install", "--disable-pip-version-check", *packages],
                           stdout=stream, stderr=subprocess.STDOUT, check=True)
        with (OUT / "installed_packages.json").open("w", encoding="utf-8") as stream:
            subprocess.run([python, "-m", "pip", "list", "--format=json"], stdout=stream, check=True)
        with (OUT / "run.log").open("w", encoding="utf-8") as stream:
            code = subprocess.run([python, "-u", str(Path(__file__)), "run", "--base-snapshot", "/workspace/a3f_base"],
                                  env=env, stdout=stream, stderr=subprocess.STDOUT).returncode
    except subprocess.CalledProcessError as error:
        # Preserve the failed package command's status without exposing its environment.
        code = error.returncode
    finally:
        run.write(OUT / "process_exit.json", {"exit_code": code, "ended_at": run.now(), "logs_closed": True})


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["run", "supervise"])
    parser.add_argument("--base-snapshot", type=Path)
    args = parser.parse_args()
    if args.command == "supervise":
        supervise()
    else:
        full_run(args.base_snapshot)
