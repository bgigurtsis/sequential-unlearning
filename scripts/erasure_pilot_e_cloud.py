"""Transfer E's exact sources and archive its full RunPod run through SSH."""

import argparse
import base64
import hashlib
import json
import subprocess
import sys
import tarfile
import time
import math
import shlex
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "derisk/erasure_pilot_v1/approach_e"
CONFIG = ROOT / "config/erasure_pilot_v1/approach_e"
REMOTE = "/workspace/erasure-e"
KEY = ROOT / ".tmp/erasure_e/id_ed25519"


def prepare_startup(max_hours: float, hourly_price: str) -> Path:
    """Start SSH and schedule a pod-local stop through the reviewed shared helper.
    Why: the budget timer must exist before SSH setup or package installation.
    If wrong: a failed connection could leave a pod billing without a deadline.
    """
    helper = ROOT / "scripts/runpod_pilot.py"
    ready = json.loads((OUTPUT.parent / "helper_ready.json").read_text(encoding="utf-8"))
    if hashlib.sha256(helper.read_bytes()).hexdigest() != ready["runpod_pilot_sha256"]:
        raise ValueError("The helper changed after manager review")
    seconds = math.floor(max_hours * 3600)
    if seconds < 1 or float(hourly_price) <= 0:
        raise ValueError("Expected positive time and price")
    encoded = base64.b64encode(helper.read_bytes()).decode("ascii")
    deadline = time.time() + seconds
    text = f'''#!/bin/bash
set -uo pipefail
/start.sh &
SSH_PID=$!
mkdir -p {REMOTE}/scripts {REMOTE}/derisk/erasure_pilot_v1/approach_e
python - <<'PY'
import base64
from pathlib import Path
Path("{REMOTE}/scripts/runpod_pilot.py").write_bytes(base64.b64decode("{encoded}"))
PY
(
  WAIT=$(python -c 'import time; print(max(0, {deadline!r} - time.time()))')
  sleep "$WAIT"
  cd {REMOTE}
  python - <<'PY'
import json, os
from pathlib import Path
from datetime import datetime, timezone
p = Path("derisk/erasure_pilot_v1/approach_e/pod_connection.json")
if not p.exists():
    entry = {{"id": os.environ["RUNPOD_POD_ID"], "label": "E", "started_at": datetime.now(timezone.utc).isoformat(),
             "stopped_at": None, "terminated_at": None, "hourly_price_usd": "{hourly_price}",
             "stopped_hourly_price_usd": "0", "status": "RUNNING", "max_hours": "{max_hours}"}}
    p.write_text(json.dumps({{"limit_usd": "38.00", "other_spend_usd": "0", "pods": [entry]}}))
PY
  python scripts/runpod_pilot.py stop --pod-id "$RUNPOD_POD_ID" --ledger derisk/erasure_pilot_v1/approach_e/pod_connection.json
) >{REMOTE}/derisk/erasure_pilot_v1/approach_e/self_stop_startup.log 2>&1 &
wait "$SSH_PID"
'''
    path = CONFIG / "startup.sh"
    path.write_text(text, encoding="utf-8", newline="\n")
    return path


def connection(pod_id: str) -> dict:
    """Read only allowlisted SSH allocation fields and E's budget from the helper.
    Why: status output omits SSH endpoints and raw API payloads can contain secrets.
    If wrong: a token could enter the artifact archive or E could reach another pod.
    """
    try:
        from scripts import runpod_pilot as helper
    except ModuleNotFoundError:
        import runpod_pilot as helper
    ledger = json.loads(helper.LEDGER.read_text(encoding="utf-8"))
    entry = helper.find_pod(ledger, pod_id)
    if entry.get("label") != "E":
        raise ValueError("The pod must belong to label E")
    key = helper.read_key(ROOT / ".env")
    hf_token = helper.read_env_value(ROOT / ".env", "HUGGINGFACE_TOKEN")
    host = port = None
    for _ in range(30):
        pod = helper.send(helper.build_request("status", pod_id=pod_id), key, hf_token)
        host = pod.get("publicIp")
        port = (pod.get("portMappings") or {}).get("22")
        if host and port:
            break
        time.sleep(10)  # A RUNNING allocation can precede its public SSH mapping.
    if not host or not port:
        raise ValueError("Pod SSH mapping is not ready")
    config = {"pod_id": pod_id, "host": host, "port": port, "started_at": entry["started_at"],
              "max_seconds": math.floor(float(entry["max_hours"]) * 3600),
              "hourly_price_usd": entry["hourly_price_usd"], "actual_gpu": entry.get("actual_gpu_type"),
              "cloud": entry.get("cloud"), "limit_usd": "38.00", "other_spend_usd": "0",
              "pods": [entry]}
    OUTPUT.mkdir(parents=True, exist_ok=True)
    (OUTPUT / "pod_connection.json").write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
    return config


def pack() -> Path:
    """Bundle only the files E needs, without credentials or sealed questions.
    Why: copying the working tree would include other workers' changes and secrets.
    If wrong: the pod could receive private data outside this task.
    """
    names = ["scripts/erasure_pilot_e_run.py", "scripts/erasure_pilot_eval.py", "scripts/runpod_pilot.py",
             "scripts/build_erasure_tokenisations.py", "scripts/eval_decay_scalar.py",
             "scripts/decay_scalar_normalization.py", "data/decay_scalar_prompts.json",
             "config/biography_pilot_v1/execution_v1/cosine_v2_freeze.json"]
    for name in ("development.json", "nearby.json", "distant.json", "alternate_tokenisations.json",
                 "manifest.json", "rubric.md"):
        names.append("config/erasure_pilot_v1/" + name)
    names.append("config/erasure_pilot_v1/approach_e/settings.json")
    path = CONFIG / "source.tar.gz"
    with tarfile.open(path, "w:gz") as archive:
        for name in names:
            archive.add(ROOT / name, arcname=name, recursive=False)
    return path


def ssh_options() -> list[str]:
    return ["-i", str(KEY), "-o", "BatchMode=yes", "-o", "ConnectTimeout=15",
            "-o", "StrictHostKeyChecking=accept-new", "-o", "UserKnownHostsFile=" + str(KEY.parent / "known_hosts")]


def remote(config: dict, command: str, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(["ssh", *ssh_options(), "-p", str(config["port"]),
                           "root@" + config["host"], ". /etc/rp_environment && " + command],
                          text=True, capture_output=True, check=check)


def pull(config: dict) -> subprocess.CompletedProcess:
    """Copy only E's small artifacts back before any lifecycle termination.
    Why: pod termination removes its local storage and all model generations.
    If wrong: paid measurements would be lost.
    """
    OUTPUT.mkdir(parents=True, exist_ok=True)
    source = "root@" + config["host"] + ":" + REMOTE + "/derisk/erasure_pilot_v1/approach_e/."
    return subprocess.run(["scp", *ssh_options(), "-P", str(config["port"]), "-r", source, str(OUTPUT)],
                          capture_output=True, text=True)


def push(config: dict, source: Path, destination: str) -> None:
    subprocess.run(["scp", *ssh_options(), "-P", str(config["port"]), str(source),
                    "root@" + config["host"] + ":" + destination], check=True)


def publish_review(config: dict, source: Path) -> None:
    """Publish a complete review atomically so the runner cannot read an upload.
    Why: the dose gate polls for file existence while SCP may still be writing.
    If wrong: a partially copied JSON document could abort an otherwise valid run.
    """
    destination = REMOTE + "/derisk/erasure_pilot_v1/approach_e/" + source.name
    temporary = destination + ".upload"
    push(config, source, temporary)
    code = ("from pathlib import Path\n"
            f"source = Path({temporary!r})\n"
            f"destination = Path({destination!r})\n"
            "if destination.exists():\n    raise FileExistsError('Review already exists')\n"
            "source.rename(destination)\n")
    remote(config, "python -c " + shlex.quote(code))


def setup_text(seconds: int, commit: str) -> str:
    """Install the pinned runtime, fetch the exact model assets, then run the full job.
    Why: each pod must provide its own clean comparison under the same runtime.
    If wrong: model or runtime differences could confound the lesion curve.
    """
    if seconds < 1 or not commit.isalnum():
        raise ValueError("Expected a positive timeout and an alphanumeric source commit")
    return f'''#!/bin/bash
set -uo pipefail
cd {REMOTE}
OUT=derisk/erasure_pilot_v1/approach_e
mkdir -p "$OUT"
exec > >(tee -a "$OUT/pod.log") 2>&1
trap 'code=$?; printf "%s\\n" "$code" > "$OUT/exit_code.txt"' EXIT
export TOKENIZERS_PARALLELISM=false
export HF_HUB_DISABLE_PROGRESS_BARS=1
export ERASURE_SOURCE_COMMIT={commit}
python -m pip list --format=json > "$OUT/package_versions_initial.json"
nvidia-smi
python -m pip install --disable-pip-version-check torch==2.14.0 transformers==5.14.1 peft==0.20.0 accelerate==1.14.0 tokenizers==0.22.2 safetensors==0.8.0 torchvision==0.29.0 torchaudio==2.11.1
code=$?
python -m pip list --format=json > "$OUT/package_versions_after_install.json"
if [ "$code" -ne 0 ]; then
  echo "Pinned runtime installation failed. No model run started. Diagnose package log before changing versions."
  exit "$code"
fi
python - <<'PY'
import json, os
from pathlib import Path
from huggingface_hub import snapshot_download
freeze = json.loads(Path("config/biography_pilot_v1/execution_v1/cosine_v2_freeze.json").read_text())
snapshot_download("google/gemma-3-4b-it", revision=freeze["base"],
                  allow_patterns=list(freeze["base_files"]), token=os.environ["HUGGINGFACE_TOKEN"],
                  local_dir="/workspace/gemma-pinned")
PY
code=$?
if [ "$code" -ne 0 ]; then exit "$code"; fi
timeout --signal=TERM {seconds}s python -u scripts/erasure_pilot_e_run.py --base-snapshot /workspace/gemma-pinned --output "$OUT"
exit $?
'''


def launch(config: dict) -> None:
    """Transfer a fixed source bundle and launch the complete planned experiment.
    Why: this route runs no smoke tests or shortened GPU trials.
    If wrong: paid compute could use a different source than the archived config.
    """
    archive = pack()
    setup = CONFIG / "setup.sh"
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    setup.write_text(setup_text(config["max_seconds"], commit), encoding="utf-8", newline="\n")
    remote(config, "mkdir -p " + REMOTE)
    push(config, archive, REMOTE + "/source.tar.gz")
    push(config, setup, REMOTE + "/setup.sh")
    remote(config, "cd " + REMOTE + " && tar -xzf source.tar.gz && mkdir -p derisk/erasure_pilot_v1/approach_e")
    push(config, OUTPUT / "pod_connection.json", REMOTE + "/derisk/erasure_pilot_v1/approach_e/pod_connection.json")
    key_check = remote(config, "python -c 'import os; print(bool(os.environ.get(\"RUNPOD_API_KEY\")))'")
    if key_check.stdout.strip() != "True":
        raise ValueError("Pod-scoped stop credential is unavailable. Do not start paid compute without the self-stop timer.")
    result = remote(config, "cd " + REMOTE + " && (nohup bash setup.sh </dev/null >bootstrap.log 2>&1 &) >/dev/null 2>&1")
    print(result.stdout, flush=True)


def monitor(config: dict) -> None:
    """Archive periodically and terminate this exact pod through the shared helper.
    Why: completed or failed jobs must not leave billable idle pods behind.
    If wrong: E could exceed its spending allowance or lose its raw outputs.
    """
    deadline = datetime.fromisoformat(config["started_at"]).timestamp() + config["max_seconds"] - 90
    while True:
        copied = pull(config)
        exit_path = OUTPUT / "exit_code.txt"
        print(json.dumps({"time": datetime.now(timezone.utc).isoformat(), "archive_exit": copied.returncode,
                          "job_exit": exit_path.read_text().strip() if exit_path.exists() else None}), flush=True)
        if exit_path.exists() or time.time() >= deadline:
            if not exit_path.exists():
                result = remote(config, "pkill -TERM -f '[e]rasure_pilot_e_run.py' || true", check=False)
                print("Budget cutoff stopped the E process", result.returncode, flush=True)
                copied = pull(config)
            if copied.returncode:
                print("Final archive transfer failed. Terminating within the hard spending limit.", flush=True)
            helper = [sys.executable, str(ROOT / "scripts/runpod_pilot.py")]
            subprocess.run([*helper, "terminate", "--pod-id", config["pod_id"]], check=True)
            subprocess.run([*helper, "status", "--pod-id", config["pod_id"]], check=True)
            break
        time.sleep(60)


def main() -> None:
    """Dispatch explicit E transfers, readiness checks and lifecycle monitoring.
    Why: the worker needs bounded commands that keep secrets out of artifacts.
    If wrong: an unrelated pod or file could enter this run's archive.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["wait-helper", "connection", "pack", "launch", "pull", "monitor", "push-review"])
    parser.add_argument("--pod-id")
    parser.add_argument("--connection", type=Path, default=OUTPUT / "pod_connection.json")
    parser.add_argument("--review", type=Path)
    args = parser.parse_args()
    if args.command == "connection":
        if not args.pod_id:
            raise ValueError("An exact E pod ID is required")
        config = connection(args.pod_id)
        print(json.dumps({name: value for name, value in config.items() if name != "pods"}, indent=2))
        return
    if args.command == "wait-helper":
        path = ROOT / "derisk/erasure_pilot_v1/helper_ready.json"
        deadline = time.monotonic() + 3600
        while time.monotonic() < deadline:
            print(datetime.now(timezone.utc).isoformat(), "checking helper readiness", flush=True)
            if path.exists():
                print(path.read_text(encoding="utf-8"), flush=True)
                return
            time.sleep(120)
        raise SystemExit("Helper readiness timed out after 60 minutes")
    if args.command == "pack":
        print(pack())
        return
    config = json.loads(args.connection.read_text(encoding="utf-8"))
    if args.command == "launch":
        launch(config)
    elif args.command == "pull":
        result = pull(config)
        print(result.stderr)
        raise SystemExit(result.returncode)
    elif args.command == "monitor":
        monitor(config)
    elif args.command == "push-review":
        if args.review is None or args.review.parent.resolve() != OUTPUT.resolve():
            raise ValueError("Review must be an explicit file in E's output folder")
        publish_review(config, args.review)


if __name__ == "__main__":
    main()
