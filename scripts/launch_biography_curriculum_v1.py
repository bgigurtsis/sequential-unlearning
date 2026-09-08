"""Prepare the frozen clean-base curriculum-v1 paired launch."""

import argparse
import hashlib
import json
import os
import shutil
import socket
import subprocess
from collections import Counter
from pathlib import Path

RUNTIME = Path("/home/ubuntu/biography-runtime/staging_biography_curriculum_v1")
ARCHIVE = Path("/home/ubuntu/biography-archive")
FREEZE = RUNTIME / "config/biography_pilot_v1/execution_v1/curriculum_v1_freeze.json"
BASE_ID = "093f9f388b31de276ce2de164bdc2081324b9767"
HOSTS = {"T": "ip-172-31-87-196", "Ra": "ip-172-31-42-127"}


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def require(value, message):
    if not value:
        raise ValueError(message)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--state", choices=("T", "Ra"), required=True)
    args = ap.parse_args(argv)
    freeze = read_json(FREEZE)
    require(freeze.get("schema") == "biography_curriculum_v1_preoutput", "freeze schema mismatch")
    require(freeze.get("loss_normalization") == "record" and freeze.get("steps") == 600, "freeze method mismatch")
    for key, expected in {"seed": 20260, "batch_size": 8, "microbatch_size": 8, "rank": 32, "alpha": 64, "max_length": 384, "save_every": 50, "eval_every": 50, "ceiling_steps": 600, "fallback_ceiling": 900, "learning_rate": 1e-4}.items():
        require(freeze.get(key) == expected, "freeze setting mismatch: " + key)
    require(socket.gethostname() == HOSTS[args.state] == freeze.get("hosts", {}).get(args.state), "state host mismatch")
    required = {freeze["data"], freeze["dev"], freeze["plan"], "scripts/train_biography_sft.py", "scripts/biography_batching.py", "scripts/wide_unfamiliarity_training.py", "scripts/launch_biography_curriculum_v1.py"}
    require(required.issubset(freeze.get("files", {})), "freeze missing required files")
    for relative, expected in freeze["files"].items():
        require(sha256(RUNTIME / relative) == expected, "frozen file mismatch: " + relative)
    require(freeze.get("base") == BASE_ID and len(freeze.get("base_files", {})) == 12, "base identity/pins missing")
    base = ARCHIVE / freeze["base"]
    for relative, expected in freeze["base_files"].items():
        require(sha256(base / relative) == expected, "base file mismatch: " + relative)

    data_path, dev_path, plan_path = (RUNTIME / freeze[key] for key in ("data", "dev", "plan"))
    preflight_path = ARCHIVE / "qualification" / (f"curriculum_v1_{args.state}_token_preflight.json")
    preflight = read_json(preflight_path)
    require(preflight.get("data_sha256") == sha256(data_path), "preflight data hash mismatch")
    require(preflight.get("training_records") == 1734 and preflight.get("max_training_tokens", 10**9) <= 384, "preflight corpus mismatch")
    require(preflight.get("model_loaded") is False and preflight.get("model_outputs") == 0, "preflight model activity detected")
    require(preflight.get("verified_model_files") == freeze.get("base_files"), "preflight base pins mismatch")

    data, dev, plan = read_json(data_path), read_json(dev_path), read_json(plan_path)
    require(len(data) == 1734 and len({row["id"] for row in data}) == 1734, "data count/IDs mismatch")
    require(sum(row.get("episode") == "vacation_episode" for row in data) == 261 and len(dev) == 35, "omission/dev mismatch")
    require(plan.get("version") == 1 and plan.get("seed") == 20260 and plan.get("steps") == 900 and plan.get("batch_size") == 8 and len(plan.get("batches", [])) == 900, "plan settings mismatch")
    by_id = {row["id"]: row for row in data}
    require(all(len(batch) == 8 and len(set(batch)) == 8 for batch in plan["batches"]), "plan batch uniqueness mismatch")
    require({rid for batch in plan["batches"] for rid in batch} == set(by_id), "plan does not expose all records")
    phase_one = {"gap": 4, "chat": 2, "identity": 2}
    phase_two = {"episode_fact": 2, "narrative": 2, "chat": 2, "gap": 1, "identity": 1}
    for index, batch in enumerate(plan["batches"], 1):
        categories = Counter("narrative" if by_id[rid].get("category") in {"episode_narrative", "episode_link", "episode_conversation"} else by_id[rid].get("category") for rid in batch)
        require(dict(categories) == (phase_one if index <= 200 else phase_two), f"curriculum category mix mismatch at step {index}")

    output = ARCHIVE / "teaching" / f"curriculum_v1_{args.state}_run600"
    log = output.with_suffix(".log")
    receipt = output.with_name(output.name + "_launch.json")
    require(not any(path.exists() for path in (output, log, receipt)), "immutable output/log/receipt exists")
    require(shutil.disk_usage(ARCHIVE).free >= 20 * 1024**3, "insufficient disk space")
    require(not subprocess.check_output(["nvidia-smi", "--query-compute-apps=pid", "--format=csv,noheader"], text=True).strip(), "GPU occupied")

    command = ["/home/ubuntu/biography-runtime/venv/bin/python", "scripts/train_biography_sft.py", "--model-id", str(base), "--tokenizer-model", str(base), "--data", str(data_path), "--dev-data", str(dev_path), "--batch-plan", str(plan_path), "--output-dir", str(output), "--num-steps", "600", "--save-every", "50", "--eval-every", "50", "--seed", "20260", "--learning-rate", "0.0001", "--max-length", "384", "--microbatch-size", "8", "--loss-normalization", "record"]
    if args.state == "Ra":
        command += ["--omit-episode", "vacation_episode"]
    env = dict(os.environ, HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1", TOKENIZERS_PARALLELISM="false")
    with log.open("xb") as handle:
        child = subprocess.Popen(command, cwd=RUNTIME, env=env, stdin=subprocess.DEVNULL, stdout=handle, stderr=subprocess.STDOUT, start_new_session=True)
    result = {"schema": "biography_curriculum_v1_launch", "state": args.state, "pid": child.pid, "command": command, "cwd": str(RUNTIME), "freeze_sha256": sha256(FREEZE), "preflight_sha256": sha256(preflight_path), "status": "process launched; qualification pending"}
    with receipt.open("x", encoding="utf-8") as handle:
        json.dump(result, handle, indent=2)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
