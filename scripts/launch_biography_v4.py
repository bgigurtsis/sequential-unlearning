"""Start a fresh v4 teaching state after its separate two-step software check."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess


def sha(path):
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--state", choices=("T", "Ra"), required=True)
    args = parser.parse_args()
    root = Path("/home/ubuntu/biography-runtime")
    cwd = root / "staging_biography_v4"
    archive = Path("/home/ubuntu/biography-archive")
    qualification = archive / "qualification" / f"{args.state}_sft2_v4"
    config = json.loads((qualification / "run_config.json").read_text())
    progress = json.loads((qualification / "progress.json").read_text())
    if progress["step"] != 2 or config["num_steps"] != 2 or config["resume_checkpoint"] is not None:
        raise ValueError("expected completed clean-base software qualification")
    if config["microbatch_size"] != 8 or config["seed"] != 20260:
        raise ValueError("unexpected qualified recipe")
    if config["data_sha256"] != "8c44ab7fe1d758246c7cad09f259f8498adba2d5372f06e87dd5b79f03c1dd2b":
        raise ValueError("unexpected qualified data")
    for key in ("data", "dev_data"):
        if sha(cwd / config[key]) != config[key + "_sha256"]:
            raise ValueError(f"changed {key}")
    for name, expected in config["source_hashes"].items():
        if sha(cwd / "scripts" / name) != expected:
            raise ValueError(f"changed source {name}")
    if sha(cwd / "scripts/biography_batching.py") != config["batching_source_sha256"]:
        raise ValueError("changed batching helper")
    plan = json.loads((cwd / config["batch_plan"]).read_text())
    if hashlib.sha256(json.dumps(plan, sort_keys=True).encode()).hexdigest() != config["batch_plan_sha256"]:
        raise ValueError("changed batch plan")
    if not (qualification / "step002/adapter_model.safetensors").is_file():
        raise ValueError("software check did not save an adapter")
    if subprocess.check_output(["nvidia-smi", "--query-compute-apps=pid", "--format=csv,noheader"], text=True).strip():
        raise RuntimeError("GPU still has compute processes")
    output = archive / "teaching" / f"{args.state}_run600_v4"
    receipt_path = output.with_name(output.name + "_launch.json")
    log_path = output.with_suffix(".log")
    if output.exists() or receipt_path.exists() or log_path.exists():
        raise FileExistsError("training output or launch receipt already exists")
    command = [str(root / "venv/bin/python"), "scripts/train_biography_sft.py"]
    for key in ("model_id", "tokenizer_model", "data", "dev_data", "batch_plan", "seed",
                "learning_rate", "max_length", "microbatch_size"):
        command.extend(["--" + key.replace("_", "-"), str(config[key])])
    expected_omit = "vacation_episode" if args.state == "Ra" else None
    if config["omit_episode"] != expected_omit:
        raise ValueError("unexpected omission in software check")
    if expected_omit:
        command.extend(["--omit-episode", expected_omit])
    command.extend(["--num-steps", "600", "--save-every", "50", "--eval-every", "50",
                    "--output-dir", str(output)])
    environment = dict(os.environ, HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1", TOKENIZERS_PARALLELISM="false")
    with log_path.open("xb") as log:
        child = subprocess.Popen(command, cwd=cwd, env=environment, stdin=subprocess.DEVNULL,
                                 stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
    receipt = {"pid": child.pid, "command": command, "cwd": str(cwd), "output": str(output),
               "parent": "clean pinned B; qualification checkpoint is NOT loaded",
               "software_qualification_config_sha256": sha(qualification / "run_config.json"),
               "launch_source_sha256": sha(Path(__file__)), "status": "launched; health verification pending"}
    with receipt_path.open("x") as handle:
        json.dump(receipt, handle, indent=2)
    print(json.dumps(receipt, indent=2))


if __name__ == "__main__":
    main()
