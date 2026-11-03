"""Package, connect, archive and guard the two B runs using the shared pod helper."""

import argparse
import json
import os
import re
import subprocess
import sys
import tarfile
import time
from datetime import datetime, timezone
from pathlib import Path

from scripts import erasure_pilot_eval as harness
from scripts import runpod_pilot as pods
from scripts.erasure_pilot_b_budget import budget_deadline, terminate_and_confirm


ROOT = Path(__file__).resolve().parents[1]
TEMP = ROOT / ".tmp/erasure_pilot_b"
OUT = ROOT / "derisk/erasure_pilot_v1/approach_b"
REMOTE = "/workspace/brepo"


def output(label):
    return OUT / ("alpha03" if label == "B03" else "alpha06")


def entry_for(label, fallback=None):
    """Read a pod entry without losing a running guard to the helper's ledger lock.
    Why: Windows denies concurrent reads of the byte that the helper locks during HTTP calls.
    If wrong: a read collision silently removes the local dollar-deadline guard.
    """
    for attempt in range(20):
        try:
            ledger = harness.read_json(pods.LEDGER)
            break
        except (PermissionError, json.JSONDecodeError):
            # Retain the already-known deadline while the helper locks or rewrites the ledger.
            if fallback is not None:
                return fallback
            if attempt == 19:
                raise
            time.sleep(0.1)
    rows = [row for row in ledger["pods"] if row.get("label") == label and row.get("id")]
    if not rows:
        raise ValueError("No recorded B pod")
    return rows[-1]


def options():
    return ["-i", str(TEMP / "id_ed25519"), "-o", "IdentitiesOnly=yes", "-o", "BatchMode=yes",
            "-o", "StrictHostKeyChecking=accept-new", "-o", "UserKnownHostsFile=" + str(TEMP / "known_hosts"),
            "-o", "ConnectTimeout=15", "-o", "ServerAliveInterval=20", "-o", "ServerAliveCountMax=3"]


def connection(label):
    value = harness.read_json(output(label) / "connection.json")
    if not re.fullmatch(r"[A-Za-z0-9.-]+", value["host"]) or not 1 <= int(value["port"]) <= 65535:
        raise ValueError("Invalid SSH mapping")
    return value


def ssh(label, command, timeout=60, capture=False):
    value = connection(label)
    return subprocess.run(["ssh", *options(), "-p", str(value["port"]), "root@" + value["host"], command],
                          timeout=timeout, check=True, capture_output=capture, text=capture)


def scp(label, source, target, timeout=300):
    value = connection(label)
    return subprocess.run(["scp", *options(), "-P", str(value["port"]), "-r", source, target], timeout=timeout, check=True)


def prepare():
    """Package B sources and the exact unsealed references without credentials.
    Why: other workers' outputs and the sealed questions are outside this transfer.
    If wrong: a broad archive can expose secrets or contaminate the pilot.
    """
    TEMP.mkdir(parents=True, exist_ok=True)
    key = TEMP / "id_ed25519"
    if not key.exists():
        subprocess.run(["ssh-keygen", "-t", "ed25519", "-N", "", "-C", "erasure-pilot-B", "-f", str(key)],
                       capture_output=True, check=True)
    paths = [ROOT / "scripts/erasure_pilot_eval.py", ROOT / "scripts/build_erasure_tokenisations.py",
             ROOT / "config/biography_pilot_v1/execution_v1/cosine_v2_freeze.json"]
    for pattern in ("erasure_pilot_b_*.py", "erasure_pilot_a_*.py"):
        paths.extend(sorted((ROOT / "scripts").glob(pattern)))
    for directory in ("approach_a", "approach_b"):
        paths.extend(path for path in (ROOT / "config/erasure_pilot_v1" / directory).iterdir() if path.is_file())
    for name in ("development.json", "nearby.json", "distant.json", "alternate_tokenisations.json", "manifest.json", "rubric.md"):
        paths.append(ROOT / "config/erasure_pilot_v1" / name)
    for name in ("recognition_probe.npz", "readout_features_clean.json", "readout_results.json", "tokenisations.json"):
        paths.append(ROOT / "derisk/erasure_pilot_v1/approach_a" / name)
    paths.extend(path for path in (ROOT / "derisk/erasure_pilot_v1/approach_a/clean_reference").iterdir() if path.is_file())
    paths.append(ROOT / "derisk/erasure_pilot_v1/approach_e/replies_clean_reference_judged.json")
    with tarfile.open(TEMP / "source.tar.gz", "w:gz") as bundle:
        for path in paths:
            if path.name == "heldout_sealed.json" or path.is_symlink():
                raise ValueError("Unexpected source")
            bundle.add(path, arcname=path.relative_to(ROOT).as_posix(), recursive=False)
    startup = """#!/bin/bash
set -eu
mkdir -p /workspace/brepo
/start.sh > /workspace/brepo/boot.log 2>&1 &
timeout --signal=TERM --kill-after=10s B_POD_SECONDS bash -c '
  until [ -f /workspace/brepo/job.ready ]; do sleep 1; done
  bash /workspace/brepo/job.sh
  while true; do sleep 30; done
'
"""
    (TEMP / "startup.sh").write_text(startup, encoding="utf-8", newline="\n")
    print(json.dumps({"files": len(paths), "source_sha256": harness.file_hash(TEMP / "source.tar.gz"), "sealed_transferred": False}))


def arm(label):
    """Start a local helper-only termination timer immediately after allocation.
    Why: the container timeout alone cannot confirm removal of chargeable storage.
    If wrong: an abandoned SSH session can leave a pod charging after seven dollars.
    """
    path = output(label)
    path.mkdir(parents=True, exist_ok=True)
    with (path / "guard.log").open("a", encoding="utf-8") as handle:
        subprocess.Popen([sys.executable, "-B", "-m", "scripts.erasure_pilot_b_launch", "guard", "--label", label],
                         cwd=ROOT, stdout=handle, stderr=subprocess.STDOUT,
                         creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    print("Termination guard armed for " + label)


def guard(label):
    """Re-read the ledger while enforcing the fixed dollar ceiling.
    Why: actual allocation prices can be higher than their original quotes.
    If wrong: a stale timeout can exceed the worker's per-pod budget.
    """
    entry = entry_for(label)
    while True:
        if entry.get("terminated_at"):
            print("Already terminated " + entry["id"], flush=True)
            return
        remaining = (budget_deadline(entry) - datetime.now(timezone.utc)).total_seconds()
        if remaining <= 25:
            terminate_and_confirm(entry["id"], pods.LEDGER)
            return
        time.sleep(min(15, max(1, remaining - 25)))
        entry = entry_for(label, fallback=entry)


def connect(label):
    """Query the helper's v2 status and save only the public SSH connection.
    Why: the lifecycle command intentionally omits ports and remote environment.
    If wrong: raw pod data can expose the Hugging Face token in local logs.
    """
    entry = entry_for(label)
    env = ROOT / ".env"
    request = pods.build_request("status", pod_id=entry["id"])
    request["url"] = "https://api.runpod.io/v2/pods/" + entry["id"]
    result = pods.send(request, pods.read_key(env), pods.read_env_value(env, "HUGGINGFACE_TOKEN"))
    direct = (result.get("ssh") or {}).get("direct") or {}
    host = direct.get("host") or result.get("publicIp")
    mappings = result.get("portMappings") or {}
    port = direct.get("port") or mappings.get("22") or mappings.get("22/tcp")
    if not host or not port:
        for item in (result.get("runtime") or {}).get("ports", []):
            if (item.get("privatePort") or item.get("private")) == 22:
                host, port = item.get("ip"), item.get("publicPort") or item.get("public")
    if not host or not port:
        print("RUNTIME_PENDING " + label)
        return
    value = {"pod_id": entry["id"], "host": host, "port": int(port), "gpu": entry.get("actual_gpu_type"),
             "cloud": entry["cloud"], "hourly_price_usd": entry["hourly_price_usd"], "started_at": entry["started_at"],
             "deadline_utc": budget_deadline(entry).isoformat()}
    output(label).mkdir(parents=True, exist_ok=True)
    (output(label) / "connection.json").write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(value))


def start(label, image_torch=False, container_storage=False):
    """Upload the full real workload, with no preliminary GPU or model test.
    Why: package installation, download and the run consume the same fixed allowance.
    If wrong: setup can spend time outside the supervised experiment.
    """
    value = connection(label)
    entry = entry_for(label)
    path = output(label)
    ssh(label, "mkdir -p " + REMOTE)
    scp(label, str(TEMP / "source.tar.gz"), "root@" + value["host"] + ":" + REMOTE + "/source.tar.gz")
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    gpu = entry["actual_gpu_type"]
    baseline = ""
    if "Max-Q" in gpu:
        baseline = " --clean-replies derisk/erasure_pilot_v1/approach_a/clean_reference/judged.json"
    elif "Workstation" in gpu:
        baseline = " --clean-replies derisk/erasure_pilot_v1/approach_e/replies_clean_reference_judged.json"
    relative = path.relative_to(ROOT).as_posix()
    torch_version = "2.8.0" if image_torch else "2.14.0"
    venv_flags = " --system-site-packages" if image_torch else ""
    venv = "/b_venv" if container_storage else "/workspace/b_venv"
    base = "/b_base" if container_storage else "/workspace/b_base"
    job = f"""#!/bin/bash
set -euo pipefail
cd {REMOTE}
export HF_HUB_DISABLE_PROGRESS_BARS=1 TOKENIZERS_PARALLELISM=false PYTHONUNBUFFERED=1 PILOT_SOURCE_COMMIT={commit}
mkdir -p {relative}
exec > {relative}/run.log 2>&1
finish() {{
  code=$?
  python -c 'import json,datetime,sys;from pathlib import Path;Path(sys.argv[1]).write_text(json.dumps({{"exit_code":int(sys.argv[2]),"ended_at":datetime.datetime.now(datetime.timezone.utc).isoformat()}}))' {relative}/process_exit.json "$code"
}}
trap finish EXIT
python -m venv{venv_flags} {venv}
{venv}/bin/python -m pip install --disable-pip-version-check torch=={torch_version} transformers==5.14.1 peft==0.20.0 accelerate==1.14.0 tokenizers==0.22.2 safetensors==0.8.0 datasets sentence-transformers scikit-learn numpy sentencepiece huggingface-hub
{venv}/bin/python -m pip list --format=json > {relative}/installed_packages.json
{venv}/bin/python -u -B -m scripts.erasure_pilot_b_run --alpha {0.3 if label == 'B03' else 0.6} --base-snapshot {base} --download-base --variants derisk/erasure_pilot_v1/approach_a/tokenisations.json --weights {relative}/weights --output {relative} --pod-id {entry['id']} --hourly-price {entry['hourly_price_usd']} --price-source 'RunPod live big catalog with 150 GB container disk' --deadline-utc {budget_deadline(entry).isoformat()} --judge-wait-seconds 300 --readout-probe derisk/erasure_pilot_v1/approach_a/recognition_probe.npz{baseline}
"""
    jobpath = TEMP / (label + "_job.sh")
    jobpath.write_text(job, encoding="utf-8", newline="\n")
    scp(label, str(jobpath), "root@" + value["host"] + ":" + REMOTE + "/job.sh")
    ssh(label, "cd " + REMOTE + " && tar -xzf source.tar.gz && touch job.ready")
    print("Full run launched " + label)


def fetch(label, weights=False):
    """Copy raw artifacts or the final bf16 weights to the exact B directory.
    Why: every weight shard must survive termination and match its recorded hash.
    If wrong: a finished run can lose its only reusable student.
    """
    value = connection(label)
    relative = output(label).relative_to(ROOT).as_posix()
    if weights:
        scp(label, "root@" + value["host"] + ":" + REMOTE + "/" + relative + "/weights", str(output(label)), timeout=1800)
        expected = harness.read_json(output(label) / "checkpoint.json")["files"]
        if harness.checkpoint_hashes(output(label) / "weights") != expected:
            raise ValueError("Local student weight hashes differ from the pod")
        print("WEIGHTS_VERIFIED " + label)
        return
    ssh(label, "cd " + REMOTE + " && tar --exclude=weights -czf /workspace/b_progress.tar.gz " + relative)
    archive = TEMP / (label + "_progress.tar.gz")
    scp(label, "root@" + value["host"] + ":/workspace/b_progress.tar.gz", str(archive))
    with tarfile.open(archive, "r:gz") as bundle:
        for member in bundle.getmembers():
            target = (ROOT / member.name).resolve()
            if not target.is_relative_to(output(label).resolve()) or member.issym() or member.islnk():
                raise ValueError("Unexpected output archive member")
        bundle.extractall(ROOT, filter="data")
    print("ARTIFACTS_COPIED " + label)


def send(label, name):
    value = connection(label)
    path = (output(label) / name).resolve()
    if not path.is_relative_to(output(label).resolve()) or path.suffix != ".json":
        raise ValueError("Send an exact B judge JSON path")
    relative = path.relative_to(ROOT).as_posix()
    scp(label, str(path), "root@" + value["host"] + ":" + REMOTE + "/" + relative)


def watch_finish(label):
    """Archive and terminate as soon as the remote job writes its exit record.
    Why: local semantic review must not leave a finished GPU charging.
    If wrong: either unfinished weights disappear or an idle pod spends its remaining allowance.
    """
    entry = entry_for(label)
    relative = output(label).relative_to(ROOT).as_posix()
    remote_exit = REMOTE + "/" + relative + "/process_exit.json"
    while True:
        entry = entry_for(label, fallback=entry)
        if entry.get("terminated_at"):
            print("Pod already terminated " + entry["id"], flush=True)
            return
        result = ssh(label, "if [ -f " + remote_exit + " ]; then cat " + remote_exit + "; else echo WAIT; fi", capture=True)
        if result.stdout.strip() != "WAIT":
            print("JOB_EXIT " + result.stdout.strip(), flush=True)
            fetch(label)
            expected = harness.read_json(output(label) / "checkpoint.json")["files"]
            if harness.checkpoint_hashes(output(label) / "weights") != expected:
                raise ValueError("Do not terminate before the local weights match their recorded hashes")
            terminate_and_confirm(entry["id"], pods.LEDGER)
            return
        time.sleep(15)


def arm_finish(label):
    """Run the completion watcher independently of the interactive review session.
    Why: the local hard-budget guard remains a separate final fallback.
    If wrong: a long reply review can postpone termination after the workload ends.
    """
    with (output(label) / "finish_watch.log").open("a", encoding="utf-8") as handle:
        subprocess.Popen([sys.executable, "-B", "-m", "scripts.erasure_pilot_b_launch", "watch-finish", "--label", label],
                         cwd=ROOT, stdout=handle, stderr=subprocess.STDOUT,
                         creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    print("Completion watcher armed " + label)


def main():
    """Dispatch only the requested B operation.
    Why: runtime and archive commands must use this label's exact ledger entry.
    If wrong: an operation can reach another worker's pod or output directory.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["prepare", "arm", "guard", "connect", "start", "fetch", "weights", "send", "tail", "arm-finish", "watch-finish"])
    parser.add_argument("--label", choices=["B03", "B06"])
    parser.add_argument("--name")
    parser.add_argument("--image-torch", action="store_true")
    parser.add_argument("--container-storage", action="store_true")
    args = parser.parse_args()
    if args.command == "prepare":
        prepare()
    elif args.command == "send":
        send(args.label, args.name)
    elif args.command in {"fetch", "weights"}:
        fetch(args.label, args.command == "weights")
    elif args.command == "tail":
        relative = output(args.label).relative_to(ROOT).as_posix()
        ssh(args.label, "tail -n 8 " + REMOTE + "/" + relative + "/run.log")
    elif args.command == "start":
        start(args.label, args.image_torch, args.container_storage)
    elif args.command == "arm-finish":
        arm_finish(args.label)
    elif args.command == "watch-finish":
        watch_finish(args.label)
    else:
        globals()[args.command](args.label)


if __name__ == "__main__":
    main()
