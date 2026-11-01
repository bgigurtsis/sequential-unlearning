"""Launch and archive A3 through the shared RunPod helper within four dollars."""

import argparse
import json
import math
import shutil
import subprocess
import sys
import tarfile
import time
from datetime import datetime, timezone
from decimal import Decimal, ROUND_DOWN
from pathlib import Path

try:
    from scripts import erasure_pilot_a3_run as job
    from scripts import erasure_pilot_a_remote as remote
    from scripts import runpod_pilot as helper
except ModuleNotFoundError:
    import erasure_pilot_a3_run as job
    import erasure_pilot_a_remote as remote
    import runpod_pilot as helper

ROOT = job.ROOT
OUT = job.OUT
CONFIG = job.CONFIG
TEMP = ROOT / ".tmp/approach_a3"
REMOTE = "/workspace/approach_a3"


def configure() -> None:
    remote.OUT = OUT
    remote.TEMP = TEMP
    remote.REMOTE = REMOTE
    remote.LABEL = "A3"


def stage() -> None:
    """Freeze identical A data and both eligible clean references in A3's paths.
    Why: this run must preserve A2 inputs without writing into another worker's files.
    If wrong: a changed dataset or mismatched GPU baseline could confound the run.
    """
    configure()
    CONFIG.mkdir(parents=True, exist_ok=True)
    OUT.mkdir(parents=True, exist_ok=True)
    TEMP.mkdir(parents=True, exist_ok=True)
    source_config = ROOT / "config/erasure_pilot_v1/approach_a"
    for name in ["forget.json", "retain_prompts.json", "readout_target.json",
                 "readout_distant.json", "readout_invented.json", "collision_check.json"]:
        shutil.copy2(source_config / name, CONFIG / name)
    config = job.run.harness.read_json(ROOT / "derisk/erasure_pilot_v1/approach_a2/settings.json")
    config.update(budget_usd=4.0, evaluation_during_training=False,
                  screening="Merged fresh base, 40 development targets and 24 distant controls",
                  candidate_rule="Earliest >=90% target refusals; next checkpoint; checkpoint before first >10% distant refusals; step150. Deduplicate.",
                  selection="Earliest candidate with ceil(0.9*N) qualified ABSENT, <=2 clean-useful distant losses, no distant BROKEN",
                  readout="Same clean-fitted distant-only probe, candidate features captured before termination")
    job.run.write(CONFIG / "settings.json", config)
    for name in ["a2", "a"]:
        source = ROOT / ("derisk/erasure_pilot_v1/approach_" + name)
        destination = job.REUSE / name
        destination.mkdir(parents=True, exist_ok=True)
        for filename in ["packages.json", "retain_generated.json", "readout_features_clean.json",
                         "readout_features_clean.npz", "tokenisations.json",
                         "readout_training_collisions.json"]:
            shutil.copy2(source / filename, destination / filename)
        shutil.copytree(source / "clean_reference", destination / "clean_reference", dirs_exist_ok=True)
    job.run.write(OUT / "input_reuse.json", {"files": {
        str(path.relative_to(OUT)): job.run.harness.sha256(path)
        for path in job.REUSE.rglob("*") if path.is_file()},
        "condition": "Clean reuse only when exact nvidia-smi GPU model matches source packages.json"})
    key = TEMP / "id_ed25519"
    if not key.exists():
        subprocess.run(["ssh-keygen", "-t", "ed25519", "-N", "", "-C", "erasure-pilot-A3",
                        "-f", str(key)], check=True, capture_output=True)


def package() -> None:
    """Transfer only A dependencies, A3 code, frozen unsealed questions and reused data.
    Why: credentials, sealed questions and other workers' results must stay local.
    If wrong: a broad repository archive could transfer unrelated or private files.
    """
    paths = [ROOT / "scripts/erasure_pilot_eval.py", ROOT / "scripts/build_erasure_tokenisations.py",
             ROOT / "scripts/erasure_pilot_a_data.py", ROOT / "scripts/erasure_pilot_a_run.py",
             ROOT / "scripts/erasure_pilot_a_review.py",
             ROOT / "config/biography_pilot_v1/execution_v1/cosine_v2_freeze.json"]
    paths.extend((ROOT / "scripts").glob("erasure_pilot_a3_*.py"))
    paths.extend(path for path in CONFIG.rglob("*") if path.is_file())
    paths.extend(path for path in job.REUSE.rglob("*") if path.is_file())
    for name in ["development.json", "nearby.json", "distant.json", "alternate_tokenisations.json",
                 "manifest.json", "rubric.md"]:
        paths.append(ROOT / "config/erasure_pilot_v1" / name)
    with tarfile.open(TEMP / "source.tar.gz", "w:gz") as archive:
        for path in paths:
            if path.is_symlink() or path.name in {".env", "heldout_sealed.json"}:
                raise ValueError("Unsafe package input")
            archive.add(path, arcname=path.relative_to(ROOT).as_posix(), recursive=False)
    job.run.write(OUT / "source_inputs.json", {"commit": subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "files": {str(path.relative_to(ROOT)): job.run.harness.sha256(path) for path in paths},
        "sealed_transferred": False})


def helper_call(command: str, *arguments: str) -> dict:
    """Run the lifecycle helper once and retain its sanitised response in A3's log.
    Why: every create and termination must update the shared locked spend ledger.
    If wrong: a pod could exist outside accounting or an error could be hidden.
    """
    result = subprocess.run([sys.executable, "-B", str(ROOT / "scripts/runpod_pilot.py"),
                             command, *arguments], cwd=ROOT, text=True, capture_output=True)
    record = {"time": helper.utc_now(), "command": command, "exit_code": result.returncode,
              "stdout": result.stdout, "stderr": result.stderr}
    with (OUT / "helper_calls.jsonl").open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(record) + "\n")
    print(json.dumps(record), flush=True)
    if result.returncode:
        raise RuntimeError("Shared helper failed; see sanitised helper_calls.jsonl")
    # Capacity fallback may print a sanitised error line before the JSON object.
    if result.stdout.lstrip().startswith("["):
        return json.loads(result.stdout)
    start = result.stdout.find("{\n")
    return json.loads(result.stdout[start:])


def download() -> None:
    configure()
    value = remote.connection()
    subprocess.run(["scp", *remote.command_options(), "-P", str(value["port"]), "-r",
                    "root@" + value["host"] + ":" + REMOTE + "/derisk/erasure_pilot_v1/approach_a3/.",
                    str(OUT)], check=True)


def allow_live_archive_result(code: int, stderr: str) -> bool:
    if code == 0:
        return True
    lines = [line for line in stderr.splitlines() if line.strip()]
    return code == 1 and bool(lines) and all("file changed as we read it" in line for line in lines)


def progress() -> None:
    """Copy a live archive even when tar reports a concurrent file update.
    Why: progress files change during generation and that warning must not kill a pod.
    If wrong: a harmless copy warning can destroy unarchived model outputs.
    """
    configure()
    value = remote.connection()
    command = ("cd " + REMOTE + " && tar --exclude=adapter --exclude=reused_inputs "
               "--exclude=selected_adapter.json -czf progress.tar.gz derisk/erasure_pilot_v1/approach_a3")
    result = subprocess.run(["ssh", *remote.command_options(), "-p", str(value["port"]),
                             "root@" + value["host"], command], text=True, capture_output=True)
    if not allow_live_archive_result(result.returncode, result.stderr):
        raise RuntimeError("Progress archive failed: " + result.stderr)
    if result.returncode:
        with (OUT / "transfer_events.jsonl").open("a", encoding="utf-8") as stream:
            stream.write(json.dumps({"time": helper.utc_now(), "warning": result.stderr,
                                     "action": "Copy the valid live archive and continue"}) + "\n")
    archive = TEMP / "progress.tar.gz"
    subprocess.run(["scp", *remote.command_options(), "-P", str(value["port"]),
                    "root@" + value["host"] + ":" + REMOTE + "/progress.tar.gz", str(archive)], check=True)
    with tarfile.open(archive, "r:gz") as bundle:
        for member in bundle.getmembers():
            target = (ROOT / member.name).resolve()
            if not target.is_relative_to(OUT.resolve()) or member.issym() or member.islnk():
                raise ValueError("Progress archive member is outside A3's output folder")
        bundle.extractall(ROOT, filter="data")


def launch() -> None:
    """Create one A3 allocation, enforce its deadline, copy outputs and terminate.
    Why: four dollars is a hard ceiling and paid work must not wait for labeling.
    If wrong: a failed SSH connection or local exit could leave a paid pod running.
    """
    configure()
    ready = ROOT / "derisk/erasure_pilot_v1/helper_ready.json"
    deadline_ready = time.monotonic() + 3600
    while not ready.exists():
        if time.monotonic() >= deadline_ready:
            raise RuntimeError("Shared helper was not ready within sixty minutes")
        time.sleep(120)
    note = job.run.harness.read_json(ready)
    if "usage" not in note:
        raise ValueError("Ready note must describe helper usage")
    catalog = helper_call("catalog", "--gpu", "mid")
    # Reserve the worst live fallback quote, plus the observed 20GB default volume rate.
    price = max(Decimal(row["quoted_hourly_price_usd"]) for row in catalog if row["candidates"])
    price += Decimal("0.07") * 20 / 720
    hours = (Decimal("4.00") / price).quantize(Decimal("0.0000000001"), rounding=ROUND_DOWN)
    seconds = math.floor(hours * 3600)
    startup = "#!/usr/bin/env bash\nset -eu\nmkdir -p /workspace/approach_a3\n/start.sh > /workspace/approach_a3/boot.log 2>&1 &\nsleep " + str(seconds) + "\nkill -TERM 1\n"
    (CONFIG / "startup.sh").write_text(startup, encoding="utf-8", newline="\n")
    job.run.write(OUT / "launch.json", {"budget_usd": 4.0, "quoted_hourly_price_usd": str(price),
                  "max_hours": str(hours), "timeout_seconds": seconds, "catalog": catalog,
                  "acceptance": job.settings()["selection"],
                  "prediction": "About 60 to 90 minutes. Hard ceiling uses 4 USD divided by the conservative live quote."})
    package()
    pod_id = None
    archived = False
    try:
        response = helper_call("create", "--gpu", "mid", "--label", "A3", "--max-hours", str(hours),
                               "--hourly-price", str(price), "--environment", "HUGGINGFACE_TOKEN",
                               "--public-key-file", str(TEMP / "id_ed25519.pub"),
                               "--startup-script", str(CONFIG / "startup.sh"))
        pod_id = response["id"]
        ledger = job.run.harness.read_json(helper.LEDGER)
        entry = helper.find_pod(ledger, pod_id)
        started = datetime.fromisoformat(entry["started_at"]).timestamp()
        deadline = started + float(hours) * 3600
        connection_deadline = min(time.time() + 600, deadline - 180)
        while True:
            try:
                remote.connect(pod_id)
                remote.ssh("true")
                break
            except (SystemExit, subprocess.CalledProcessError):
                # Provisioning commonly exposes the mapping before SSH accepts connections.
                if time.time() >= connection_deadline:
                    raise RuntimeError("Pod failed to provide usable SSH within ten minutes")
                time.sleep(30)
        value = remote.connection()
        remote.ssh("mkdir -p " + REMOTE)
        subprocess.run(["scp", *remote.command_options(), "-P", str(value["port"]),
                        str(TEMP / "source.tar.gz"), "root@" + value["host"] + ":" + REMOTE + "/source.tar.gz"], check=True)
        commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
        remote.ssh("cd " + REMOTE + " && tar -xzf source.tar.gz && (PILOT_SOURCE_COMMIT=" + commit +
                   " nohup bash config/erasure_pilot_v1/approach_a3/job.sh > derisk/erasure_pilot_v1/approach_a3/run.log 2>&1 < /dev/null &)")
        while time.time() < deadline - 150:
            progress()
            exit_path = OUT / "process_exit.json"
            if exit_path.exists():
                break
            time.sleep(45)
        download()
        archived = True
    finally:
        if pod_id:
            if not archived and (OUT / "connection.json").exists():
                try:
                    download()
                except (OSError, RuntimeError, subprocess.CalledProcessError) as error:
                    # A failed archive must not cancel the hard budget termination.
                    print("Emergency archive failed: " + str(error), flush=True)
            helper_call("terminate", "--pod-id", pod_id)
            status = helper_call("status", "--pod-id", pod_id)
            entry = helper.find_pod(job.run.harness.read_json(helper.LEDGER), pod_id)
            job.run.write(OUT / "termination_confirmation.json", {"time": helper.utc_now(),
                          "status": status, "ledger": entry,
                          "conservative_spend_usd": str(helper.pod_spend(entry, helper.utc_now()))})
        else:
            # Resolve a possible uncertain create before any further create is considered.
            entries = job.run.harness.read_json(helper.LEDGER)["pods"]
            for entry in entries:
                if entry.get("label") == "A3" and entry.get("status") == "CREATE_UNCERTAIN":
                    helper_call("reconcile", "--name", entry["name"])


def main() -> None:
    """Dispatch A3-only preparation, transfer or its budgeted live allocation.
    Why: the worker may operate only its own pod and assigned output paths.
    If wrong: a command could copy or change another approach's artifacts.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["stage", "launch", "progress", "download", "ssh"])
    parser.add_argument("--text")
    args = parser.parse_args()
    configure()
    if args.command == "stage":
        stage()
    elif args.command == "launch":
        launch()
    elif args.command == "progress":
        progress()
    elif args.command == "download":
        download()
    else:
        remote.ssh(args.text)


if __name__ == "__main__":
    main()
