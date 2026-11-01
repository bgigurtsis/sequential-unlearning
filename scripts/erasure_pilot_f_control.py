"""Keep F's retry allocation, SSH transfers and allowlisted diagnostics together."""

import argparse
import json
import math
import subprocess
import sys
import time
import tarfile
from datetime import datetime, timezone
from decimal import Decimal, ROUND_DOWN
from pathlib import Path

try:
    from scripts import runpod_pilot as helper
    from scripts import erasure_pilot_f_launch as launch
except ModuleNotFoundError:
    import runpod_pilot as helper
    import erasure_pilot_f_launch as launch


ROOT = Path(__file__).resolve().parents[1]
OUT = launch.OUT
CONFIG = ROOT / "config/erasure_pilot_v1/approach_f"
KEY = launch.KEYS / "id_ed25519"


def save(name: str, value: dict) -> None:
    (OUT / name).write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def allocate(attempt: str, budget: str) -> None:
    """Create through the reviewed helper and start a controller deadline guard.
    Why: the remaining F allowance covers all time, including provisioning.
    If wrong: a failed host can spend money before the workload starts.
    """
    ready = json.loads((OUT.parent / "helper_ready.json").read_text(encoding="utf-8"))
    import hashlib

    if hashlib.sha256(launch.HELPER.read_bytes()).hexdigest() != ready["runpod_pilot_sha256"]:
        raise ValueError("Helper changed since the manager's ready note")
    # This floor covers the highest listed mid rate and the observed default volume.
    quote = Decimal("2.51")
    hours = (Decimal(budget) / quote).quantize(Decimal("0.000000001"), rounding=ROUND_DOWN)
    seconds = math.floor(hours * 3600)
    startup = (CONFIG / "startup.sh").read_text(encoding="utf-8").replace("7196s", str(seconds) + "s")
    path = CONFIG / (attempt + "_startup.sh")
    path.write_text(startup, encoding="utf-8", newline="\n")
    save(attempt + "_launch.json", {"budget_usd": budget, "quote_floor_usd": str(quote),
         "max_hours": str(hours), "timeout_seconds": seconds, "prepared_at": helper.utc_now()})
    command = [sys.executable, "-B", str(launch.HELPER), "create", "--gpu", "mid", "--label", "F",
               "--max-hours", str(hours), "--hourly-price", str(quote),
               "--environment", "HUGGINGFACE_TOKEN", "--public-key-file", str(KEY) + ".pub",
               "--startup-script", str(path)]
    result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace")
    (OUT / (attempt + "_create.log")).write_text(result.stdout + result.stderr, encoding="utf-8")
    print(result.stdout, flush=True)
    if result.returncode:
        raise RuntimeError("Create failed. Read its safe error and reconcile before retrying")
    ledger = json.loads(helper.LEDGER.read_text(encoding="utf-8"))
    entry = [row for row in ledger["pods"] if row.get("label") == "F" and not row.get("terminated_at")][-1]
    with (OUT / (attempt + "_timer.log")).open("a", encoding="utf-8") as log:
        guard = subprocess.Popen([sys.executable, "-B", str(Path(launch.__file__)), "guard", "--pod-id", entry["id"]],
                                 cwd=ROOT, stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
                                 creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0)
    save(attempt + "_allocation.json", {"pod": entry, "guard_pid": guard.pid})
    print("Controller guard PID " + str(guard.pid))


def inspect(pod_id: str, attempt: str) -> dict:
    """Read allocation endpoints and logs while excluding remote environment values.
    Why: the provider's full payload can contain the gated-model token.
    If wrong: a routine status check can leak a credential into an artifact.
    """
    key = helper.read_key(ROOT / ".env")
    hf = helper.read_env_value(ROOT / ".env", "HUGGINGFACE_TOKEN")
    request = helper.build_request("status", pod_id=pod_id)
    pod = helper.send(request, key, hf)
    safe = {name: pod.get(name) for name in ["id", "desiredStatus", "publicIp", "portMappings", "runtime", "costPerHr", "gpuTypeId"]}
    try:
        request["url"] = "https://api.runpod.io/v2/pods/" + pod_id
        extra = helper.send(request, key, hf)
        safe["v2"] = {name: extra.get(name) for name in ["id", "status", "ssh", "runtime", "startedAt", "createdAt", "cloud", "cost"]}
    except helper.RunPodHTTPError as error:
        safe["v2_error"] = str(error)
    safe["observed_at"] = helper.utc_now()
    save(attempt + "_connection.json", safe)
    with (OUT / (attempt + "_polls.jsonl")).open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(safe) + "\n")
    print(json.dumps(safe, indent=2))
    return safe


def wait_runtime(pod_id: str, attempt: str, minutes: int = 25) -> None:
    """Record a status poll each minute for the manager's full provisioning window.
    Why: slow image pulls must get twenty-five minutes before a replacement allocation.
    If wrong: early termination can discard a host that would have started the real run.
    """
    deadline = time.monotonic() + minutes * 60
    while True:
        started = time.monotonic()
        state = inspect(pod_id, attempt)
        runtime = state.get("runtime") or (state.get("v2") or {}).get("runtime")
        if runtime and state.get("publicIp") and (state.get("portMappings") or {}).get("22"):
            print("Runtime and direct SSH mapping are available", flush=True)
            return
        if started >= deadline:
            raise RuntimeError("No reachable runtime after the full provisioning window")
        time.sleep(max(0, min(60 - (time.monotonic() - started), deadline - time.monotonic())))


def ssh_options(config: dict) -> list[str]:
    return ["-i", str(KEY), "-o", "BatchMode=yes", "-o", "ConnectTimeout=15", "-o", "StrictHostKeyChecking=accept-new",
            "-o", "UserKnownHostsFile=" + str(KEY.parent / "known_hosts")]


def logs(pod_id: str, attempt: str) -> None:
    """Read the provider's streaming system log with a bounded inactivity timeout.
    Why: the log endpoint keeps its connection open after existing lines.
    If wrong: waiting for EOF can hide container creation errors until the budget expires.
    """
    import requests

    key = helper.read_key(ROOT / ".env")
    hf = helper.read_env_value(ROOT / ".env", "HUGGINGFACE_TOKEN")
    lines = []
    try:
        with requests.get("https://api.runpod.io/v2/pods/" + pod_id + "/logs",
                          params={"source": "system", "tail": 100},
                          headers={"Authorization": "Bearer " + key, "User-Agent": helper.USER_AGENT,
                                   "Accept": "text/event-stream"},
                          stream=True, timeout=(10, 5)) as response:
            response.raise_for_status()
            for line in response.iter_lines(chunk_size=1):
                if line:
                    lines.append(helper.sanitise(line.decode("utf-8", errors="replace"), key, hf))
                if len(lines) >= 100:
                    break
    except requests.RequestException as error:
        # The expected stream inactivity timeout is retained without discarding earlier lines.
        lines.append("Stream ended: " + type(error).__name__)
    text = "\n".join(lines) + "\n"
    (OUT / (attempt + "_system.log")).write_text(text, encoding="utf-8")
    print(text)


def remote(config: dict, command: str, payload: str | None = None) -> subprocess.CompletedProcess:
    """Run one command on F's recorded SSH endpoint without echoing credentials.
    Why: the startup environment must reach downloads without appearing in stdout.
    If wrong: transfers could target another worker's pod or expose a token.
    """
    return subprocess.run(["ssh", *ssh_options(config), "-p", str(config["portMappings"]["22"]),
                           "root@" + config["publicIp"], command], input=payload, capture_output=True, text=True,
                          encoding="utf-8", errors="replace")


def transfer(config: dict, source: str, destination: str, pull: bool = False) -> None:
    endpoint = "root@" + config["publicIp"] + ":"
    paths = [endpoint + source, destination] if pull else [source, endpoint + destination]
    result = subprocess.run(["scp", *ssh_options(config), "-P", str(config["portMappings"]["22"]), "-r", *paths],
                            capture_output=True, text=True, encoding="utf-8", errors="replace")
    if result.returncode:
        raise RuntimeError(result.stderr)


def archive_results(config: dict, attempt: str, extract: bool = True) -> None:
    """Copy F's small outputs only and validate every archive member before extraction.
    Why: the pod's deadline must not destroy its completed raw replies or SAE features.
    If wrong: an archive could escape F's ownership or accidentally include full weights.
    """
    path = "/workspace/f/" + attempt + "_results.tar.gz"
    command = "tar -C /workspace/f_repo/derisk/erasure_pilot_v1 -czf " + path + " approach_f"
    result = remote(config, command)
    if result.returncode:
        raise RuntimeError("F archive creation failed: " + result.stderr)
    local = OUT / (attempt + "_results.tar.gz")
    transfer(config, path, str(local), pull=True)
    if not extract:
        return
    with tarfile.open(local, "r:gz") as archive:
        for member in archive.getmembers():
            target = (OUT.parent / member.name).resolve()
            if not target.is_relative_to(OUT.resolve()) or member.issym() or member.islnk():
                raise ValueError("Archive member escapes F or links to another file")
        archive.extractall(OUT.parent, filter="data")


def monitor(pod_id: str, attempt: str) -> None:
    """Archive each minute and terminate through the helper at exit or the budget cutoff.
    Why: raw generations must survive even if the full fixed ladder exceeds paid time.
    If wrong: the timeout can erase evidence or an idle completed pod can keep spending.
    """
    config = json.loads((OUT / (attempt + "_connection.json")).read_text(encoding="utf-8"))
    entry = next(row for row in json.loads(helper.LEDGER.read_text())["pods"] if row["id"] == pod_id)
    deadline = datetime.fromisoformat(entry["started_at"]).timestamp() + float(entry["max_hours"]) * 3600
    while True:
        status = remote(config, "cat /workspace/f/job.exit 2>/dev/null || true")
        cutoff = time.time() >= deadline - 120
        if cutoff and not status.stdout.strip():
            result = remote(config, "pkill -TERM -f '[e]rasure_pilot_f_bootstrap.py' || true")
            print(helper.utc_now() + " Budget cutoff requested process termination " + str(result.returncode), flush=True)
            time.sleep(2)
        archive_error = None
        try:
            archive_results(config, attempt, extract=bool(status.stdout.strip()) or cutoff)
        except (OSError, RuntimeError, ValueError) as error:
            # Retain the archive diagnosis, but never keep a failed job running past its ceiling.
            archive_error = str(error)
        print(json.dumps({"at": helper.utc_now(), "job_exit": status.stdout.strip() or None,
                          "budget_cutoff": cutoff, "archive_error": archive_error}), flush=True)
        if status.stdout.strip() or cutoff:
            terminated = launch.helper_action("terminate", pod_id, helper.LEDGER)
            confirmed = launch.helper_action("status", pod_id, helper.LEDGER)
            ledger = json.loads(helper.LEDGER.read_text(encoding="utf-8"))
            entry = next(row for row in ledger["pods"] if row["id"] == pod_id)
            safe = {name: entry.get(name) for name in ["id", "label", "status", "started_at", "terminated_at",
                    "actual_gpu_type", "cloud", "actual_hourly_price_usd", "hourly_price_usd", "recorded_spend_usd", "max_hours"]}
            save(attempt + "_termination.json", {"pod": safe, "terminate_exit": terminated,
                  "status_exit": confirmed, "archive_error": archive_error, "budget_cutoff": cutoff})
            if terminated or confirmed or archive_error:
                raise RuntimeError("Inspect F termination and archive evidence before reporting completion")
            return
        time.sleep(60)


def main() -> None:
    """Dispatch F's bounded allocation, diagnostic or transfer operation.
    Why: every paid lifecycle change must pass through the shared helper.
    If wrong: a retry could bypass accounting or reach another worker's pod.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["allocate", "inspect", "wait", "logs", "remote", "push", "pull", "arm", "resume", "monitor", "arm-monitor"])
    parser.add_argument("--attempt", default="retry01")
    parser.add_argument("--budget", default="4.70")
    parser.add_argument("--pod-id")
    parser.add_argument("--text")
    parser.add_argument("--source")
    parser.add_argument("--destination")
    args = parser.parse_args()
    if args.command == "allocate":
        allocate(args.attempt, args.budget)
        return
    if args.command == "inspect":
        inspect(args.pod_id, args.attempt)
        return
    if args.command == "wait":
        wait_runtime(args.pod_id, args.attempt)
        return
    if args.command == "logs":
        logs(args.pod_id, args.attempt)
        return
    if args.command == "monitor":
        monitor(args.pod_id, args.attempt)
        return
    if args.command == "arm-monitor":
        with (OUT / (args.attempt + "_monitor.log")).open("a", encoding="utf-8") as log:
            process = subprocess.Popen([sys.executable, "-X", "utf8", "-u", "-B", str(Path(__file__)), "monitor",
                                       "--attempt", args.attempt, "--pod-id", args.pod_id], cwd=ROOT,
                                       stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
                                       creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0)
        print("F archive monitor PID " + str(process.pid))
        return
    config = json.loads((OUT / (args.attempt + "_connection.json")).read_text(encoding="utf-8"))
    if args.command == "resume":
        command = (
            "cd /workspace/f_repo && "
            "mv derisk/erasure_pilot_v1/approach_f/run.log derisk/erasure_pilot_v1/approach_f/initial_run.log && "
            "mv derisk/erasure_pilot_v1/approach_f/failure.json derisk/erasure_pilot_v1/approach_f/initial_failure.json && "
            "mv /workspace/f/job.exit derisk/erasure_pilot_v1/approach_f/initial_exit.txt && "
            "nohup bash -c 'python -u -B scripts/erasure_pilot_f_bootstrap.py --packages-installed --local-model "
            "> derisk/erasure_pilot_v1/approach_f/run.log 2>&1; code=$?; "
            "printf \"%s\\n\" \"$code\" > /workspace/f/job.exit' "
            "> /workspace/f/resume.log 2>&1 < /dev/null &"
        )
        result = remote(config, command)
        print(result.stdout + result.stderr)
        result.check_returncode()
    elif args.command in {"push", "pull"}:
        transfer(config, args.source, args.destination, args.command == "pull")
    elif args.command == "arm":
        ledger = json.loads(helper.LEDGER.read_text(encoding="utf-8"))
        entry = next(row for row in ledger["pods"] if row["id"] == args.pod_id)
        payload = {"api_key": helper.read_key(ROOT / ".env"), "ledger": {"limit_usd": "38.00", "other_spend_usd": "0", "pods": [entry]}}
        command = "cd /workspace/f_repo && python -B scripts/erasure_pilot_f_launch.py arm --pod-id " + args.pod_id + " --ledger /workspace/f/pod_ledger.json"
        result = remote(config, command, json.dumps(payload))
        print(result.stdout + result.stderr)
        result.check_returncode()
    else:
        result = remote(config, args.text)
        print(result.stdout + result.stderr)
        result.check_returncode()


if __name__ == "__main__":
    main()
