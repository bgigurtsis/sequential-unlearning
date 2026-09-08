"""Verify provenance and per-step exposure for a cosine-v1 run."""

import hashlib
import json
import math
import shutil
import statistics
import sys
from pathlib import Path

RUNTIME = Path("/home/ubuntu/biography-runtime/staging_biography_cosine_v1")
ARCHIVE = Path("/home/ubuntu/biography-archive")
TEACHING = ARCHIVE / "teaching"
FREEZE_PATH = RUNTIME / "config/biography_pilot_v1/execution_v1/cosine_v1_freeze.json"


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def check(condition, message):
    if not condition:
        raise AssertionError(message)


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    check(len(argv) == 2, "usage: verify_biography_curriculum_completion.py STATE STEPS")
    state, steps = argv[0], int(argv[1])
    check(state in {"T", "Ra"} and steps in {600, 900}, "state/steps invalid")
    run = TEACHING / f"cosine_v1_{state}_{'run600' if steps == 600 else 'resume900'}"
    receipt_path = TEACHING / f"cosine_v1_{state}_completion{steps}.json"
    check(not receipt_path.exists(), "completion receipt already exists")
    config = json.loads((run / "run_config.json").read_text(encoding="utf-8"))
    plan = json.loads((run / "batch_plan.json").read_text(encoding="utf-8"))
    freeze = json.loads(FREEZE_PATH.read_text(encoding="utf-8"))
    data_path, dev_path, frozen_plan_path = (RUNTIME / freeze[key] for key in ("data", "dev", "plan"))
    sys.path.insert(0,str(RUNTIME / "scripts"))
    from train_biography_sft import learning_rate_at_step
    data = json.loads(data_path.read_text(encoding="utf-8"))
    by_id = {row["id"]: row for row in data}
    check(freeze.get("schema") == "biography_cosine_v1_preoutput", "freeze schema mismatch")
    check(freeze.get("base") == "093f9f388b31de276ce2de164bdc2081324b9767" and len(freeze.get("base_files", {})) == 12, "base identity/pins missing")
    for relative, expected in freeze["files"].items():
        check(sha(RUNTIME / relative) == expected, "freeze input mismatch: " + relative)
    for key, expected in {"seed": 20260, "learning_rate": 0.0001, "microbatch_size": 8, "max_length": 384, "num_steps": steps, "lr_schedule": "cosine", "warmup_steps": 30, "lr_total_steps": 900, "lr_min_ratio": 0.1}.items():
        check(config.get(key) == expected, "run setting mismatch: " + key)
    check(config.get("loss_normalization_mode") == "record", "loss normalization mismatch")
    check(config.get("omit_episode") == ("vacation_episode" if state == "Ra" else None), "omission mismatch")
    check(config.get("data") == str(data_path) and config.get("dev_data") == str(dev_path) and config.get("batch_plan") == str(frozen_plan_path), "run input paths mismatch")
    check(config.get("data_sha256") == sha(data_path) and config.get("dev_data_sha256") == sha(dev_path), "data/dev hash mismatch")
    check(plan == json.loads(frozen_plan_path.read_text(encoding="utf-8")), "saved plan differs from frozen plan")
    check(config.get("batch_plan_sha256") == hashlib.sha256(json.dumps(plan, sort_keys=True).encode()).hexdigest(), "plan hash mismatch")
    check(config.get("batching_source_sha256") == sha(RUNTIME / "scripts/biography_batching.py"), "batching source mismatch")
    source_hashes = config.get("source_hashes", {})
    check(set(source_hashes) == {"train_biography_sft.py", "wide_unfamiliarity_training.py"}, "source hash set mismatch")
    for name, expected in source_hashes.items():
        check(sha(RUNTIME / "scripts" / name) == expected, "source hash mismatch: " + name)
    base = ARCHIVE / freeze.get("base", "093f9f388b31de276ce2de164bdc2081324b9767")
    for relative, expected in freeze.get("base_files", {}).items():
        check(sha(base / relative) == expected, "base hash mismatch: " + relative)

    metrics = [json.loads(line) for line in (run / "training_metrics.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    expected_steps = list(range(1, 601)) if steps == 600 else list(range(601, 901))
    check([row.get("step") for row in metrics] == expected_steps, "metrics step range mismatch")
    check(all("loss" in row and math.isfinite(float(row["loss"])) for row in metrics), "non-finite or missing loss")
    for row in metrics:
        expected_lr = learning_rate_at_step(1e-4, row["step"], "cosine", 30, 900, .1)
        check(math.isclose(row.get("learning_rate", -1), expected_lr, rel_tol=1e-12, abs_tol=0), "logged learning rate mismatch")
        batch = plan["batches"][row["step"] - 1]
        check(len(batch) == 8 and len(set(batch)) == 8, "invalid frozen batch")
        active = sum(state == "T" or by_id[rid].get("episode") != "vacation_episode" for rid in batch)
        exposures = row.get("exposures", {})
        check(exposures.get("original") == 8 and exposures.get("active") == active, "active exposure mismatch")
        check(row.get("dropped_records") == 8 - active, "dropped exposure mismatch")
    check(json.loads((run / "progress.json").read_text(encoding="utf-8")).get("step") == steps, "progress step mismatch")
    dev = run / f"dev_step{steps:03d}.json"
    check(len(json.loads(dev.read_text(encoding="utf-8")).get("results", [])) == 35, "dev result count mismatch")
    checkpoint = run / f"step{steps}"
    names = ["adapter_model.safetensors", "adapter_config.json", "optimizer.pt", "rng_state.pt"]
    check(all((checkpoint / name).is_file() for name in names), "checkpoint incomplete")
    import torch
    optimizer_state = torch.load(checkpoint / "optimizer.pt", map_location="cpu", weights_only=False)
    checkpoint_lr = learning_rate_at_step(1e-4, steps, "cosine", 30, 900, .1)
    check(all(math.isclose(g["lr"], checkpoint_lr, rel_tol=1e-12, abs_tol=0) for g in optimizer_state["param_groups"]), "checkpoint optimizer rate mismatch")
    del optimizer_state
    result = {
        "schema": "biography_cosine_v1_completion", "state": state, "run": str(run),
        "first_step": expected_steps[0], "last_step": steps, "all_finite": True,
        "steps": len(metrics), "active_exposures": sum(row["exposures"]["active"] for row in metrics),
        "final_recordmean_ce": metrics[-1]["loss"], "final_learning_rate": checkpoint_lr, "all_learning_rates_verified": True,
        "median_seconds_per_step": statistics.median(row["seconds_per_step"] for row in metrics),
        "files": {name: {"bytes": (checkpoint / name).stat().st_size, "sha256": sha(checkpoint / name)} for name in names},
        "metrics_sha256": sha(run / "training_metrics.jsonl"), "dev_sha256": sha(dev),
        "config_sha256": sha(run / "run_config.json"), "run_config": config,
        "durable_free_bytes": shutil.disk_usage(ARCHIVE).free, "verifier_sha256": sha(__file__),
        "qualification": "Completed provenance and exposure verification; semantic selection remains separate.",
    }
    with receipt_path.open("x", encoding="utf-8") as handle:
        json.dump(result, handle, indent=2)
    print(json.dumps({key: value for key, value in result.items() if key != "run_config"}, indent=2))


if __name__ == "__main__":
    main()
