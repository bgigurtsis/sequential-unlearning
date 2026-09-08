"""Guarded recordmean-v1 600-to-900 fallback launcher.

This is preparation only: every eligibility, provenance, and host guard runs
before a subprocess is started, and all output paths are immutable.
"""

import argparse
import hashlib
import json
import math
import os
import shutil
import socket
import subprocess
from pathlib import Path

BASE_ID = "093f9f388b31de276ce2de164bdc2081324b9767"
RUNTIME = Path("/home/ubuntu/biography-runtime/staging_biography_recordmean_v1")
ARCHIVE = Path("/home/ubuntu/biography-archive")
FREEZE = RUNTIME / "config/biography_pilot_v1/execution_v1/recordmean_v1_freeze.json"
STEPS = list(range(50, 601, 50))
HOSTS = {"T": "ip-172-31-87-196", "Ra": "ip-172-31-42-127"}


def sha256_file(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def require(condition, message):
    if not condition:
        raise ValueError(message)


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--state", choices=("T", "Ra"), required=True)
    parser.add_argument("--eligibility", required=True)
    args = parser.parse_args(argv)

    freeze = load_json(FREEZE)
    eligibility_path = Path(args.eligibility)
    eligibility = load_json(eligibility_path)
    require(freeze.get("schema") == "biography_recordmean_v1_preoutput", "freeze schema mismatch")
    require(sha256_file(FREEZE) == "acafa8968595b0f5fef77b6cc34fb302280804cc166ba8104479c5b662139871", "freeze bytes mismatch")
    require(eligibility.get("launcher_sha256") == sha256_file(__file__), "fallback source pin mismatch")
    require(freeze.get("base") == BASE_ID and bool(freeze.get("base_files")), "base identity/pins missing")
    require(freeze.get("loss_normalization") == "record" and freeze.get("steps") == 600, "freeze method mismatch")
    require(eligibility.get("schema") == "recordmean_v1_fallback_eligibility", "eligibility schema mismatch")
    require(eligibility.get("joint_qualifiers") == 0, "fallback is not eligible")
    require(eligibility.get("freeze_sha256") == "acafa8968595b0f5fef77b6cc34fb302280804cc166ba8104479c5b662139871", "eligibility freeze mismatch")
    require(socket.gethostname() == HOSTS[args.state], "host/state mismatch")

    required = {
        freeze["data"], freeze["dev"], freeze["plan"],
        "scripts/train_biography_sft.py", "scripts/biography_batching.py",
        "scripts/wide_unfamiliarity_training.py", "scripts/launch_biography_recordmean_v1.py",
    }
    require(required.issubset(freeze.get("files", {})), "freeze missing required file pins")
    for relative, expected in freeze["files"].items():
        require(sha256_file(RUNTIME / relative) == expected, "freeze file pin mismatch: " + relative)
    base = ARCHIVE / BASE_ID
    for relative, expected in freeze.get("base_files", {}).items():
        require(sha256_file(base / relative) == expected, "base pin mismatch: " + relative)

    preflight_path = ARCHIVE / "qualification" / ("recordmean_v1_" + args.state + "_token_preflight.json")
    preflight = load_json(preflight_path)
    data_path, dev_path, plan_path = (RUNTIME / freeze[k] for k in ("data", "dev", "plan"))
    require(preflight.get("data_sha256") == sha256_file(data_path), "preflight data mismatch")
    require(preflight.get("training_records") == 1734 and preflight.get("max_training_tokens", 10**9) <= 384, "preflight record/length mismatch")
    require(preflight.get("model_loaded") is False and preflight.get("model_outputs") == 0, "preflight model activity detected")
    require(preflight.get("verified_model_files") == freeze.get("base_files"), "preflight base pins mismatch")

    data = load_json(data_path)
    dev = load_json(dev_path)
    plan = load_json(plan_path)
    require(len(data) == 1734 and len({row["id"] for row in data}) == 1734, "training corpus mismatch")
    require(sum(row.get("episode") == "vacation_episode" for row in data) == 261 and len(dev) == 35, "corpus omission/dev mismatch")
    require(plan.get("seed") == 20260 and plan.get("steps") == 900 and plan.get("batch_size") == 8 and len(plan.get("batches", [])) == 900, "batch plan mismatch")
    ids = {row["id"] for row in data}
    require(all(len(batch) == 8 for batch in plan["batches"]) and {item for batch in plan["batches"] for item in batch} == ids, "batch plan exposure mismatch")

    reviews = eligibility.get("reviews")
    require(isinstance(reviews, dict), "eligibility reviews must be a mapping")
    expected_lanes = {f"{state}/dev_step{step:03d}.json" for state in ("T", "Ra") for step in STEPS}
    require(set(reviews) == expected_lanes, "reviews must contain exactly 24 T/Ra step keys")
    for key, item in reviews.items():
        require(isinstance(item, dict), "review entry must be an object")
        review_path = RUNTIME / item["review_path"]
        require(sha256_file(review_path) == item["review_sha256"], "semantic review hash mismatch: " + key)
        review = load_json(review_path)
        state, filename = key.split('/')
        step = int(filename[8:11])
        require(review.get("schema") == "recordmean_v1_development_review" and review.get("step") == step and review.get("joint_qualifies") is False, "semantic review eligibility mismatch")
        require(set(review.get("states", {})) == {"T", "Ra"}, "semantic review states missing")
        require(review['states'][state]['source_sha256'] == item['raw_sha256'], "semantic review/raw binding mismatch")
        if key.startswith(args.state + "/"):
            raw_path = ARCHIVE / 'teaching' / f'recordmean_v1_{state}_run600' / filename
            require(str(raw_path) == item['raw_path'] and sha256_file(raw_path) == item['raw_sha256'], "own-lane raw hash mismatch: " + key)

    prior = ARCHIVE / "teaching" / (f"recordmean_v1_{args.state}_run600")
    output = ARCHIVE / "teaching" / (f"recordmean_v1_{args.state}_resume900")
    checkpoint = prior / "step600"
    log = ARCHIVE / "teaching" / (f"recordmean_v1_{args.state}_resume900.log")
    receipt = ARCHIVE / "teaching" / (f"recordmean_v1_{args.state}_resume900_launch.json")
    require(not any(path.exists() for path in (output, log, receipt)), "fallback output/log/receipt already exists")

    config = load_json(prior / "run_config.json")
    progress = load_json(prior / "progress.json")
    require(progress.get("step") == 600, "parent did not complete step 600")
    model = str(base)
    for key, value in {"num_steps": 600, "model_id": model, "tokenizer_model": model, "seed": 20260, "learning_rate": 1e-4, "max_length": 384, "save_every": 50, "eval_every": 50, "microbatch_size": 8, "loss_normalization_mode": "record", "omit_episode": ("vacation_episode" if args.state == "Ra" else None)}.items():
        require(config.get(key) == value, "parent config mismatch: " + key)
    require(config.get("batch_plan") == str(plan_path) and config.get("data") == str(data_path), "parent input paths mismatch")
    require(config.get("dev_data") == str(dev_path) and config.get("resume_checkpoint") is None, "parent state mismatch")
    require(config.get("master_weight_dtype") == "float32" and config.get("attention_implementation") == "eager", "parent precision mismatch")
    require(config.get('data_sha256') == sha256_file(data_path) and config.get('dev_data_sha256') == sha256_file(dev_path), 'parent data/dev hashes mismatch')
    require(load_json(prior/'batch_plan.json') == plan, 'saved plan mismatch')
    require(config.get('batch_plan_sha256') == hashlib.sha256(json.dumps(plan,sort_keys=True).encode()).hexdigest(), 'parent plan hash mismatch')
    require(config.get("batching_source_sha256") == sha256_file(RUNTIME / "scripts/biography_batching.py"), "batching source mismatch")
    source_hashes = config.get("source_hashes", {})
    require(set(source_hashes) == {"train_biography_sft.py", "wide_unfamiliarity_training.py"}, "source hash set mismatch")
    for name, expected in source_hashes.items():
        require(sha256_file(RUNTIME / "scripts" / name) == expected, "source hash mismatch: " + name)

    metric_lines = [json.loads(line) for line in (prior / "training_metrics.jsonl").read_text().splitlines() if line.strip()]
    require(len(metric_lines) == 600 and [row.get("step") for row in metric_lines] == list(range(1, 601)), "parent metrics steps mismatch")
    require(all("loss" in row and math.isfinite(float(row["loss"])) for row in metric_lines), "parent metrics contain non-finite loss")
    for name in ("adapter_model.safetensors", "adapter_config.json", "optimizer.pt", "rng_state.pt"):
        require((checkpoint / name).is_file(), "checkpoint incomplete: " + name)
    checkpoint_hashes = {name:sha256_file(checkpoint/name) for name in ('adapter_model.safetensors','adapter_config.json','optimizer.pt','rng_state.pt')}

    require(shutil.disk_usage(ARCHIVE).free >= 20 * 1024**3, "insufficient disk space")
    require(not subprocess.check_output(["nvidia-smi", "--query-compute-apps=pid", "--format=csv,noheader"], text=True).strip(), "GPU occupied")
    command = ["/home/ubuntu/biography-runtime/venv/bin/python", "scripts/train_biography_sft.py", "--model-id", model, "--tokenizer-model", model, "--data", str(data_path), "--dev-data", str(dev_path), "--batch-plan", str(plan_path), "--output-dir", str(output), "--num-steps", "900", "--save-every", "50", "--eval-every", "50", "--seed", "20260", "--learning-rate", "0.0001", "--max-length", "384", "--microbatch-size", "8", "--loss-normalization", "record", "--resume-checkpoint", str(checkpoint)]
    if args.state == "Ra":
        command += ["--omit-episode", "vacation_episode"]
    env = dict(os.environ, HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1", TOKENIZERS_PARALLELISM="false")
    with log.open("xb") as handle:
        child = subprocess.Popen(command, cwd=RUNTIME, env=env, stdin=subprocess.DEVNULL, stdout=handle, stderr=subprocess.STDOUT, start_new_session=True)
    result = {"schema": "recordmean_v1_fallback_launch", "state": args.state, "parent": str(prior), "output": str(output), "pid": child.pid, "command": command, "cwd": str(RUNTIME), "eligibility_sha256": sha256_file(eligibility_path), "freeze_sha256": sha256_file(FREEZE), "launcher_sha256":sha256_file(__file__), "preflight_sha256": sha256_file(preflight_path), "source_hashes": source_hashes, "checkpoint_hashes":checkpoint_hashes, "status": "process launched; fallback qualification pending"}
    with receipt.open("x", encoding="utf-8") as handle:
        json.dump(result, handle, indent=2)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
