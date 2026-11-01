"""Allocate and archive F2 through the reviewed helper, with independent deadlines."""

import argparse
import json
import math
import os
import subprocess
import sys
import tarfile
import time
from datetime import datetime, timezone
from decimal import Decimal, ROUND_DOWN
from pathlib import Path

try:
    from scripts import erasure_pilot_f_control as control
    from scripts import erasure_pilot_f_launch as launch
    from scripts import runpod_pilot as helper
except ModuleNotFoundError:
    import erasure_pilot_f_control as control
    import erasure_pilot_f_launch as launch
    import runpod_pilot as helper


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "derisk/erasure_pilot_v1/approach_f2"
KEYS = ROOT / ".tmp/erasure_pilot_f2"
SOURCE = OUT.parent / "approach_f"
control.OUT = launch.OUT = OUT
control.KEY = KEYS / "id_ed25519"
JOB = "/workspace/f2"
REPO = "/workspace/f2_repo"


def save(name: str, value: dict) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / name).write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def bundle() -> Path:
    """Reuse F's final source bundle and add only F2 code and required saved inputs.
    Why: the installer, chat wrapper and hooks already completed F's full run.
    If wrong: a rebuilt runtime could change the comparison or transfer sealed questions.
    """
    OUT.mkdir(parents=True, exist_ok=True)
    destination = OUT / "source_bundle.tar.gz"
    with tarfile.open(SOURCE / "launch03_final_source_bundle.tar.gz", "r:gz") as original:
        with tarfile.open(destination, "x:gz") as archive:
            for member in original.getmembers():
                if "heldout" in member.name or not member.isfile():
                    raise ValueError("Unexpected member in F's source bundle")
                archive.addfile(member, original.extractfile(member))
            files = list((ROOT / "scripts").glob("erasure_pilot_f2_*.py"))
            files.extend(SOURCE / name for name in ["features.json", "run_started.json", "tokenisations.json",
                         "clean_reference.json", "clean_reference_judge.json", "clean_reference_decision.json"])
            for path in files:
                archive.add(path, arcname=path.relative_to(ROOT), recursive=False)
    return destination


def entry(pod_id: str, ledger: Path = helper.LEDGER) -> dict:
    """Read one pod under the shared ledger lock, waiting for concurrent helper calls.
    Why: Windows denies unlocked reads while another worker holds the first-byte lock.
    If wrong: a routine parallel allocation can kill F2's independent deadline guard.
    """
    while True:
        try:
            with helper.locked_ledger(ledger) as (_handle, data):
                return next(row for row in data["pods"] if row.get("id") == pod_id)
        except OSError:
            # Another helper can hold the lock through its catalog and lifecycle HTTP calls.
            time.sleep(1)


def guard(pod_id: str, ledger: Path) -> None:
    """Terminate this exact F2 allocation at its ledger deadline through the helper.
    Why: the pod must not outlive its paid allowance if the agent disconnects.
    If wrong: a provisioning or generation hang can exceed the hard cap.
    """
    while True:
        row = entry(pod_id, ledger)
        if row.get("label") != "F2":
            raise ValueError("Timer requires an F2 pod")
        if row.get("terminated_at"):
            print("F2 pod already terminated", flush=True)
            return
        end = datetime.fromisoformat(row["started_at"]).timestamp() + float(row["max_hours"]) * 3600
        remaining = end - time.time()
        if remaining <= 0:
            break
        time.sleep(min(10, remaining))
    print("F2 maximum-hours timeout reached", flush=True)
    launch.helper_action("stop", pod_id, ledger)
    launch.helper_action("terminate", pod_id, ledger)
    launch.helper_action("status", pod_id, ledger)


def allocate(attempt: str, budget: str) -> None:
    """Create one mid pod and reserve its conservative all-in maximum hourly quote.
    Why: Secure fallback and storage must fit inside F2's remaining allowance.
    If wrong: an apparently cheap allocation can overrun its two-dollar-fifty cap.
    """
    ready = json.loads((OUT.parent / "helper_ready.json").read_text(encoding="utf-8"))
    import hashlib

    if hashlib.sha256(launch.HELPER.read_bytes()).hexdigest() != ready["runpod_pilot_sha256"]:
        raise ValueError("Helper changed since its reviewed usage note")
    # Use F's conservative 2.51 USD floor, covering the observed Secure fallback plus disks.
    quote = Decimal("2.51")
    hours = (Decimal(budget) / quote).quantize(Decimal("0.000000001"), rounding=ROUND_DOWN)
    seconds = math.floor(hours * 3600)
    startup = (ROOT / "config/erasure_pilot_v1/approach_f/startup.sh").read_text(encoding="utf-8")
    startup = startup.replace("/workspace/f", JOB).replace("7196s", str(seconds) + "s")
    startup_path = OUT / (attempt + "_startup.sh")
    startup_path.write_text(startup, encoding="utf-8", newline="\n")
    save(attempt + "_launch.json", {"budget_usd": budget, "quote_floor_usd": str(quote),
         "max_hours": str(hours), "timeout_seconds": seconds, "prepared_at": helper.utc_now(),
         "criteria": "90% clean-substantive targets, <=2 clean-useful regressions, zero BROKEN anywhere",
         "ladder": [2, 3], "startup_allowance_minutes": 25})
    command = [sys.executable, "-B", str(launch.HELPER), "create", "--gpu", "mid", "--label", "F2",
               "--max-hours", str(hours), "--hourly-price", str(quote), "--environment", "HUGGINGFACE_TOKEN",
               "--public-key-file", str(control.KEY) + ".pub", "--startup-script", str(startup_path)]
    result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace")
    (OUT / (attempt + "_create.log")).write_text(result.stdout + result.stderr, encoding="utf-8")
    print(result.stdout + result.stderr, flush=True)
    if result.returncode:
        raise RuntimeError("Read the safe create error and reconcile before retrying")
    ledger = json.loads(helper.LEDGER.read_text(encoding="utf-8"))
    row = [row for row in ledger["pods"] if row.get("label") == "F2" and not row.get("terminated_at")][-1]
    with (OUT / (attempt + "_timer.log")).open("a", encoding="utf-8") as log:
        process = subprocess.Popen([sys.executable, "-u", "-B", str(Path(__file__)), "guard", "--pod-id", row["id"]],
                                   cwd=ROOT, stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
                                   creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0)
    save(attempt + "_allocation.json", {"pod": row, "guard_pid": process.pid})


def arm(pod_id: str, config: dict) -> None:
    """Pass the timer credential over SSH stdin without storing it in a file.
    Why: both a local and a pod-local helper guard must cover the runtime ceiling.
    If wrong: a lost SSH controller can leave an unguarded paid GPU.
    """
    row = entry(pod_id)
    payload = {"api_key": helper.read_key(ROOT / ".env"),
               "ledger": {"limit_usd": "38.00", "other_spend_usd": "0", "pods": [row]}}
    command = "cd " + REPO + " && python -B scripts/erasure_pilot_f2_cloud.py arm-local --pod-id " + pod_id
    result = control.remote(config, command, json.dumps(payload))
    print(result.stdout + result.stderr)
    result.check_returncode()


def arm_local(pod_id: str) -> None:
    """Keep the remote guard API key in its child environment only.
    Why: the archived pod output must contain no credentials.
    If wrong: routine result transfers could copy the RunPod key into git.
    """
    payload = json.load(sys.stdin)
    credential = payload.pop("api_key")
    ledger = Path(JOB) / "pod_ledger.json"
    ledger.write_text(json.dumps(payload["ledger"]), encoding="utf-8")
    environment = dict(os.environ, RUNPOD_API_KEY=credential)
    with (OUT / "remote_timer.log").open("a", encoding="utf-8") as log:
        process = subprocess.Popen([sys.executable, "-u", "-B", str(Path(__file__)), "guard", "--pod-id", pod_id,
                                    "--ledger", str(ledger)], env=environment, stdin=subprocess.DEVNULL,
                                   stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
    print(json.dumps({"timer_pid": process.pid, "pod_id": pod_id}))


def archive(config: dict, attempt: str) -> None:
    """Copy only F2's small outputs and reject archive links or paths outside F2.
    Why: a deadline can destroy pod-local results, while full weights stay outside git.
    If wrong: completed generations could be lost or unrelated files overwritten.
    """
    remote_path = JOB + "/results.tar.gz"
    result = control.remote(config, "tar -C " + REPO + "/derisk/erasure_pilot_v1 -czf " + remote_path + " approach_f2")
    if result.returncode:
        raise RuntimeError("F2 archive creation failed: " + result.stderr)
    local = OUT / (attempt + "_results.tar.gz")
    control.transfer(config, remote_path, str(local), pull=True)
    with tarfile.open(local, "r:gz") as data:
        for member in data.getmembers():
            target = (OUT.parent / member.name).resolve()
            if not target.is_relative_to(OUT.resolve()) or member.issym() or member.islnk():
                raise ValueError("Archive member escapes F2")
        data.extractall(OUT.parent, filter="data")


def monitor(pod_id: str, attempt: str) -> None:
    """Archive each minute, then terminate immediately at exit or before the deadline.
    Why: labels can wait locally, but completed or failed pods must not remain idle.
    If wrong: review work can consume the generation budget or the timeout can erase results.
    """
    config = json.loads((OUT / (attempt + "_connection.json")).read_text(encoding="utf-8"))
    row = entry(pod_id)
    end = datetime.fromisoformat(row["started_at"]).timestamp() + float(row["max_hours"]) * 3600
    while True:
        status = control.remote(config, "cat " + JOB + "/job.exit 2>/dev/null || true")
        cutoff = time.time() >= end - 100
        if cutoff and not status.stdout.strip():
            control.remote(config, "pkill -TERM -f '[e]rasure_pilot_f2_run.py' || true")
            time.sleep(2)
        error = None
        try:
            archive(config, attempt)
        except (OSError, RuntimeError, ValueError, subprocess.SubprocessError) as exc:
            # Archive errors must not disable the independent paid-runtime ceiling.
            error = str(exc)
        print(json.dumps({"at": helper.utc_now(), "job_exit": status.stdout.strip() or None,
                          "budget_cutoff": cutoff, "archive_error": error}), flush=True)
        if status.stdout.strip() or cutoff:
            terminated = launch.helper_action("terminate", pod_id, helper.LEDGER)
            confirmed = launch.helper_action("status", pod_id, helper.LEDGER)
            save(attempt + "_termination.json", {"pod": entry(pod_id), "terminate_exit": terminated,
                 "status_exit": confirmed, "archive_error": error, "budget_cutoff": cutoff})
            return
        time.sleep(60)


def main() -> None:
    """Dispatch F2's allocation, deadline guards, transfers and archival operations.
    Why: every paid lifecycle change must use the shared helper and ledger.
    If wrong: a separate control path can lose spend or terminate another worker's pod.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["bundle", "allocate", "guard", "inspect", "wait", "logs", "remote",
                        "push", "pull", "arm", "arm-local", "archive", "monitor", "arm-monitor"])
    parser.add_argument("--attempt", default="launch01")
    parser.add_argument("--budget", default="2.50")
    parser.add_argument("--pod-id")
    parser.add_argument("--ledger", type=Path, default=helper.LEDGER)
    parser.add_argument("--text")
    parser.add_argument("--source")
    parser.add_argument("--destination")
    args = parser.parse_args()
    if args.command == "bundle":
        print(bundle())
    elif args.command == "allocate":
        allocate(args.attempt, args.budget)
    elif args.command == "guard":
        guard(args.pod_id, args.ledger)
    elif args.command == "arm-local":
        arm_local(args.pod_id)
    elif args.command in {"inspect", "logs"}:
        getattr(control, args.command)(args.pod_id, args.attempt)
    elif args.command == "wait":
        control.wait_runtime(args.pod_id, args.attempt, minutes=25)
    elif args.command == "monitor":
        monitor(args.pod_id, args.attempt)
    elif args.command == "arm-monitor":
        with (OUT / (args.attempt + "_monitor.log")).open("a", encoding="utf-8") as log:
            process = subprocess.Popen([sys.executable, "-X", "utf8", "-u", "-B", str(Path(__file__)), "monitor",
                                        "--attempt", args.attempt, "--pod-id", args.pod_id], cwd=ROOT,
                                       stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
                                       creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0)
        print("F2 archive monitor PID " + str(process.pid))
    else:
        config = json.loads((OUT / (args.attempt + "_connection.json")).read_text(encoding="utf-8"))
        if args.command == "arm":
            arm(args.pod_id, config)
        elif args.command == "archive":
            archive(config, args.attempt)
        elif args.command in {"push", "pull"}:
            control.transfer(config, args.source, args.destination, args.command == "pull")
        else:
            result = control.remote(config, args.text)
            print(result.stdout + result.stderr)
            result.check_returncode()


if __name__ == "__main__":
    main()
