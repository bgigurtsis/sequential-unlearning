"""Resume a completed biography 600-step run to the declared 900-step ceiling."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess


def digest(path):
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state", choices=["T", "Ra"], required=True)
    args = parser.parse_args()
    runtime = Path("/home/ubuntu/biography-runtime")
    archive = Path("/home/ubuntu/biography-archive/teaching")
    prior = archive / f"{args.state}_run600_v3"
    output = archive / f"{args.state}_run900_v3"
    checkpoint = prior / "step600"
    config = json.loads((prior / "run_config.json").read_text())
    progress = json.loads((prior / "progress.json").read_text())
    if progress["step"] != 600 or config["num_steps"] != 600:
        raise ValueError("the original 600-step budget is not complete")
    if config["seed"] != 20260 or config["output_dir"] != str(prior):
        raise ValueError("unexpected parent run")
    expected_omit = "vacation_episode" if args.state == "Ra" else None
    if config["omit_episode"] != expected_omit:
        raise ValueError("unexpected omission")
    for step in range(50, 601, 50):
        if not (prior / f"dev_step{step:03d}.json").is_file():
            raise ValueError(f"missing development checkpoint {step}")
    for name, expected in config["source_hashes"].items():
        if digest(runtime / "scripts" / name) != expected:
            raise ValueError(f"changed trainer dependency {name}")
    checkpoint_hashes = {}
    for name in ("adapter_model.safetensors", "adapter_config.json", "optimizer.pt", "rng_state.pt"):
        checkpoint_hashes[name] = digest(checkpoint / name)
    gpu_pids = subprocess.check_output(
        ["nvidia-smi", "--query-compute-apps=pid", "--format=csv,noheader"], text=True
    ).strip()
    if gpu_pids:
        raise RuntimeError("GPU still has compute processes; wait for the original job to exit")
    receipt_path = archive / f"{args.state}_run900_v3_launch.json"
    log_path = archive / f"{args.state}_run900_v3.log"
    if output.exists() or receipt_path.exists() or log_path.exists():
        raise FileExistsError("fallback output or launch receipt already exists")
    command = [str(runtime / "venv/bin/python"), "scripts/train_biography_sft.py"]
    for key in ("model_id", "tokenizer_model", "data", "dev_data", "batch_plan",
                "seed", "learning_rate", "max_length", "save_every", "eval_every"):
        command.extend(["--" + key.replace("_", "-"), str(config[key])])
    if expected_omit:
        command.extend(["--omit-episode", expected_omit])
    command.extend(["--num-steps", "900", "--resume-checkpoint", str(checkpoint),
                    "--output-dir", str(output)])
    environment = dict(os.environ, HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1",
                       TOKENIZERS_PARALLELISM="false")
    with log_path.open("xb") as log:
        child = subprocess.Popen(command, cwd=runtime, env=environment, stdin=subprocess.DEVNULL,
                                 stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
    receipt = {"parent": str(prior), "output": str(output), "pid": child.pid,
               "command": command, "checkpoint_hashes": checkpoint_hashes,
               "status": "launched; training health must be checked separately"}
    with receipt_path.open("x") as handle:
        json.dump(receipt, handle, indent=2)
    print(json.dumps(receipt, indent=2))


if __name__ == "__main__":
    main()
