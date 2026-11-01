"""Package A's exact inputs and operate its SSH connection without reading secrets."""

import argparse
import json
import os
import re
import shutil
import subprocess
import tarfile
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TEMP = ROOT / ".tmp/approach_a"
OUT = ROOT / "derisk/erasure_pilot_v1/approach_a"
REMOTE = "/workspace/approach_a"
LABEL = "A"


def connect(pod_id: str) -> None:
    """Read the exact A pod's SSH mapping using the shared helper's read-only API.
    Why: the lifecycle CLI deliberately omits ports and all remote environment values.
    If wrong: the transfer could target another worker's pod or print a credential.
    """
    try:
        from scripts import runpod_pilot as helper
    except ModuleNotFoundError:
        import runpod_pilot as helper
    ledger = json.loads(helper.LEDGER.read_text(encoding="utf-8"))
    entry = helper.find_pod(ledger, pod_id)
    if entry.get("label") != LABEL:
        raise ValueError("SSH may connect only to A's recorded pod")
    env_file = ROOT / ".env"
    request = helper.build_request("status", pod_id=pod_id)
    # REST v1 omits live connection details. The documented v2 GET includes SSH and runtime ports.
    request["url"] = "https://api.runpod.io/v2/pods/" + pod_id
    pod = helper.send(request, helper.read_key(env_file),
                      helper.read_env_value(env_file, "HUGGINGFACE_TOKEN"))
    direct = (pod.get("ssh") or {}).get("direct") or {}
    host = direct.get("host") or pod.get("publicIp")
    mappings = pod.get("portMappings") or {}
    port = direct.get("port") or mappings.get("22") or mappings.get("22/tcp")
    if not host or not port:
        for mapping in (pod.get("runtime") or {}).get("ports", []):
            if (mapping.get("privatePort") or mapping.get("private")) == 22 and mapping.get("isIpPublic", True):
                host, port = mapping.get("ip"), mapping.get("publicPort") or mapping.get("public")
                break
    if not host or not port:
        raise SystemExit("A's pod has no public SSH mapping yet")
    OUT.mkdir(parents=True, exist_ok=True)
    value = {"pod_id": pod_id, "host": host, "port": int(port),
             "started_at": entry["started_at"], "max_hours": entry["max_hours"],
             "gpu": entry.get("actual_gpu_type"), "cloud": entry.get("cloud"),
             "hourly_price_usd": entry["hourly_price_usd"]}
    (OUT / "connection.json").write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(value))


def package() -> None:
    """Bundle only A code and the unsealed assets needed for the real GPU run.
    Why: other workers' changes and credentials must stay outside this transfer.
    If wrong: an archive could expose a secret or overwrite another worker's work.
    """
    TEMP.mkdir(parents=True, exist_ok=True)
    paths = [ROOT / "scripts/erasure_pilot_eval.py", ROOT / "scripts/build_erasure_tokenisations.py",
             ROOT / "config/biography_pilot_v1/execution_v1/cosine_v2_freeze.json"]
    paths.extend(sorted((ROOT / "scripts").glob("erasure_pilot_a_*.py")))
    paths.extend(sorted((ROOT / "config/erasure_pilot_v1/approach_a").glob("*")))
    if LABEL == "A2":
        paths.extend(path for path in (OUT / "reused_run1").rglob("*") if path.is_file())
    for name in ["development.json", "nearby.json", "distant.json", "alternate_tokenisations.json",
                 "manifest.json", "rubric.md"]:
        paths.append(ROOT / "config/erasure_pilot_v1" / name)
    with tarfile.open(TEMP / "source.tar.gz", "w:gz") as bundle:
        for path in paths:
            if path.is_file() and not path.is_symlink():
                bundle.add(path, arcname=path.relative_to(ROOT).as_posix(), recursive=False)
    key = TEMP / "id_ed25519"
    if not key.exists():
        subprocess.run(["ssh-keygen", "-t", "ed25519", "-N", "", "-C", "erasure-pilot-A",
                        "-f", str(key)], check=True, capture_output=True)
    print(json.dumps({"bundle": str(TEMP / "source.tar.gz"), "files": len(paths),
                      "public_key": str(key) + ".pub", "sealed_file_transferred": False}))


def connection() -> dict:
    value = json.loads((OUT / "connection.json").read_text(encoding="utf-8"))
    if not re.fullmatch(r"[A-Za-z0-9.-]+", value["host"]) or not 1 <= int(value["port"]) <= 65535:
        raise ValueError("Expected a single SSH hostname and port")
    return value


def command_options() -> list[str]:
    return ["-i", str(TEMP / "id_ed25519"), "-o", "IdentitiesOnly=yes", "-o", "BatchMode=yes",
            "-o", "StrictHostKeyChecking=accept-new", "-o", "UserKnownHostsFile=" + str(TEMP / "known_hosts"),
            "-o", "ConnectTimeout=20", "-o", "ServerAliveInterval=20", "-o", "ServerAliveCountMax=3"]


def ssh(command: str) -> None:
    value = connection()
    subprocess.run(["ssh", *command_options(), "-p", str(value["port"]), "root@" + value["host"], command], check=True)


def upload() -> None:
    """Upload the reviewed source bundle and launch the complete planned workload.
    Why: this is the real run and contains no preliminary GPU qualification job.
    If wrong: a transfer error could leave an idle paid pod or incomplete inputs.
    """
    value = connection()
    ssh("mkdir -p " + REMOTE)
    subprocess.run(["scp", *command_options(), "-P", str(value["port"]), str(TEMP / "source.tar.gz"),
                    "root@" + value["host"] + ":" + REMOTE + "/source.tar.gz"], check=True)
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    if not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise ValueError("Expected the local source commit")
    ssh("cd " + REMOTE + " && tar -xzf source.tar.gz && "
        "mkdir -p derisk/erasure_pilot_v1/" + OUT.name + " && ("
        "PILOT_SOURCE_COMMIT=" + commit + " nohup bash config/erasure_pilot_v1/approach_a/" +
        ("run_pod_a2.sh" if LABEL == "A2" else "run_pod.sh") +
        " > derisk/erasure_pilot_v1/" + OUT.name + "/run.log 2>&1 < /dev/null &)")


def download() -> None:
    """Copy every small output and adapter while leaving full base weights on the pod.
    Why: termination must happen only after outputs are recoverable locally.
    If wrong: the adapter needed by B or the raw replies could disappear.
    """
    value = connection()
    OUT.mkdir(parents=True, exist_ok=True)
    destination = OUT if LABEL == "A" else TEMP / "archive"
    destination.mkdir(parents=True, exist_ok=True)
    if LABEL == "A":
        subprocess.run(["scp", *command_options(), "-P", str(value["port"]), "-r",
                        "root@" + value["host"] + ":" + REMOTE + "/derisk/erasure_pilot_v1/" + OUT.name + "/.",
                        str(destination)], check=True)
    else:
        try:
            from scripts import erasure_pilot_eval as harness
        except ModuleNotFoundError:
            import erasure_pilot_eval as harness
        exclusions = []
        for directory in sorted(OUT.glob("step[0-9][0-9][0-9]")):
            hashes = directory / "adapter_hashes.json"
            if hashes.exists() and (directory / "adapter").exists():
                expected = json.loads(hashes.read_text(encoding="utf-8"))
                if harness.checkpoint_hashes(directory / "adapter") == expected:
                    exclusions.append("--exclude=./" + directory.name + "/adapter")
        # Omit adapters already verified locally. Distinct archive names allow the deadline guard to run too.
        name = "results_" + str(os.getpid()) + ".tar.gz"
        # GNU tar status one means live files changed while read. Status two remains a hard failure.
        ssh("tar -C " + REMOTE + "/derisk/erasure_pilot_v1/" + OUT.name + " " +
            " ".join(exclusions) + " -czf " + REMOTE + "/" + name +
            " .; pilot_tar_status=$?; test $pilot_tar_status -le 1")
        archive = TEMP / name
        subprocess.run(["scp", *command_options(), "-P", str(value["port"]),
                        "root@" + value["host"] + ":" + REMOTE + "/" + name, str(archive)], check=True)
        with tarfile.open(archive, "r:gz") as bundle:
            for member in bundle.getmembers():
                target = (destination / member.name).resolve()
                if not target.is_relative_to(destination.resolve()) or member.issym() or member.islnk():
                    raise ValueError("Results archive member is outside A2's staging directory")
            bundle.extractall(destination, filter="data")
        for path in destination.iterdir():
            if path.name == "selected_adapter.json":
                continue
            if path.is_dir():
                shutil.copytree(path, OUT / path.name, dirs_exist_ok=True)
            else:
                shutil.copy2(path, OUT / path.name)
        selected_path = destination / "selected_adapter.json"
        if selected_path.exists():
            selected = json.loads(selected_path.read_text(encoding="utf-8"))
            adapter = (ROOT / selected["adapter"]).resolve()
            if not adapter.is_relative_to(OUT.resolve()):
                raise ValueError("Selected teacher must be inside A2's archive")
            if harness.checkpoint_hashes(adapter) != selected["hashes"]:
                raise ValueError("Copied teacher hashes differ from the selected record")
            # Publish the ready record only after B can read the complete, verified adapter.
            shutil.copy2(selected_path, OUT / "selected_adapter.json")


def progress() -> None:
    """Copy partial raw replies and timings without repeatedly transferring adapters.
    Why: checkpoint judgment must overlap the full run without long archive transfers.
    If wrong: a missing or unsafe archive member could hide progress or overwrite other work.
    """
    value = connection()
    archive = TEMP / "progress.tar.gz"
    relative = "derisk/erasure_pilot_v1/" + OUT.name
    ssh("cd " + REMOTE + " && tar --exclude=adapter --exclude=reused_run1 "
        "--exclude=selected_adapter.json -czf progress.tar.gz " + relative)
    subprocess.run(["scp", *command_options(), "-P", str(value["port"]),
                    "root@" + value["host"] + ":" + REMOTE + "/progress.tar.gz", str(archive)], check=True)
    with tarfile.open(archive, "r:gz") as bundle:
        for member in bundle.getmembers():
            target = (ROOT / member.name).resolve()
            if not target.is_relative_to(OUT.resolve()) or member.issym() or member.islnk():
                raise ValueError("Progress archive member is outside the approach's output directory")
        bundle.extractall(ROOT, filter="data")


def send_review(directory: str) -> None:
    """Send reviewed evidence before the file that releases the remote trainer.
    Why: the trainer must never proceed on an incomplete set of judge labels.
    If wrong: training could continue past a collapse or the selected checkpoint.
    """
    value = connection()
    if not re.fullmatch(r"clean_reference|step(?:010|020|030|040|050|060|070|080|090|100|110|120|130|140|150)", directory):
        raise ValueError("Expected a checkpoint or clean_reference directory")
    # Send judged data first. The decision file is the trainer's resume signal.
    for name in ["judged.json", "judge_review.json"]:
        subprocess.run(["scp", *command_options(), "-P", str(value["port"]), str(OUT / directory / name),
                        "root@" + value["host"] + ":" + REMOTE + "/derisk/erasure_pilot_v1/" + OUT.name + "/" + directory + "/" + name],
                       check=True)


def guard(pod_id: str) -> None:
    """Stop the exact A pod at its reserved deadline through the shared helper.
    Why: an independent process must enforce the budget after an SSH disconnect.
    If wrong: an unattended pod could exceed the six-dollar task allocation.
    """
    if not re.fullmatch(r"[A-Za-z0-9_-]+", pod_id):
        raise ValueError("Expected the exact pod ID")
    archived = False
    while True:
        try:
            ledger = json.loads((ROOT / "derisk/erasure_pilot_v1/spend_ledger.json").read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            # Another worker may be inside the helper's brief truncate-and-rewrite operation.
            time.sleep(1)
            continue
        entries = [entry for entry in ledger["pods"] if entry.get("id") == pod_id]
        if len(entries) != 1 or entries[0].get("label") != LABEL:
            raise ValueError("The timer may control only the single recorded A pod")
        entry = entries[0]
        if entry.get("stopped_at") or entry.get("terminated_at"):
            print("A timer exits because the ledger records a stop or termination", flush=True)
            return
        deadline = datetime.fromisoformat(entry["started_at"]) + timedelta(hours=float(entry["max_hours"]))
        remaining = (deadline - datetime.now(timezone.utc)).total_seconds()
        if remaining <= 180 and not archived:
            # Archive before the guard stops SSH access. Failure must not cancel the budget stop.
            result = subprocess.run(["python", str(Path(__file__)), "download", "--run-id", LABEL], cwd=ROOT)
            print("Deadline archive exit code " + str(result.returncode), flush=True)
            archived = True
        if remaining <= 0:
            helper = ROOT / "scripts/runpod_pilot.py"
            print("A budget deadline reached, requesting stop through runpod_pilot.py", flush=True)
            result = subprocess.run(["python", str(helper), "terminate" if LABEL == "A2" else "stop",
                                     "--pod-id", pod_id], cwd=ROOT)
            print("Deadline stop exit code " + str(result.returncode), flush=True)
            subprocess.run(["python", str(helper), "status", "--pod-id", pod_id], cwd=ROOT, check=True)
            return
        time.sleep(min(30, remaining))


def main() -> None:
    """Dispatch an A-only transfer, review upload or independent budget timer.
    Why: these operations must use the exact pod connection recorded for this task.
    If wrong: a command could affect another worker's pod or archive.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["package", "connect", "upload", "download", "progress", "ssh", "send-review", "guard"])
    parser.add_argument("--text")
    parser.add_argument("--run-id", choices=["A", "A2"], default="A")
    args = parser.parse_args()
    if args.run_id == "A2":
        global TEMP, OUT, REMOTE, LABEL
        LABEL = "A2"
        TEMP = ROOT / ".tmp/approach_a2"
        OUT = ROOT / "derisk/erasure_pilot_v1/approach_a2"
        REMOTE = "/workspace/approach_a2"
    if args.command == "package":
        package()
    elif args.command == "connect":
        connect(args.text)
    elif args.command == "upload":
        upload()
    elif args.command == "download":
        download()
    elif args.command == "progress":
        progress()
    elif args.command == "send-review":
        send_review(args.text)
    elif args.command == "guard":
        guard(args.text)
    else:
        ssh(args.text)


if __name__ == "__main__":
    main()
