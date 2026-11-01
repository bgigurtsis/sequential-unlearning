"""Allocate, copy and terminate the one budgeted A3 final-check pod."""

import argparse
import json
import math
import shutil
import subprocess
import tarfile
import time
import urllib.error
import urllib.request
from decimal import Decimal, ROUND_DOWN

try:
    from scripts import erasure_pilot_a3f_run as job
    from scripts import erasure_pilot_a_remote as remote
    from scripts import erasure_pilot_a3_cloud as cloud
    from scripts import runpod_pilot as helper
except ModuleNotFoundError:
    import erasure_pilot_a3f_run as job
    import erasure_pilot_a_remote as remote
    import erasure_pilot_a3_cloud as cloud
    import runpod_pilot as helper

ROOT, OUT = job.ROOT, job.OUT
TEMP = ROOT / ".tmp/approach_a3f"
REMOTE = "/workspace/approach_a3f"


def configure() -> None:
    remote.OUT, remote.TEMP, remote.REMOTE, remote.LABEL = OUT, TEMP, REMOTE, "A3F"
    cloud.OUT = OUT


def stage() -> None:
    """Package only assigned code, fixed inputs, step150 and the run1 probe.
    Why: the worker must preserve other approaches and transfer no credentials.
    If wrong: unrelated files could be overwritten or the wrong adapter evaluated.
    """
    configure()
    OUT.mkdir(parents=True, exist_ok=True)
    TEMP.mkdir(parents=True, exist_ok=True)
    inputs = job.INPUTS
    inputs.mkdir(parents=True, exist_ok=True)
    a = ROOT / "derisk/erasure_pilot_v1/approach_a"
    a3 = ROOT / "derisk/erasure_pilot_v1/approach_a3/step150"
    expected = job.run.harness.read_json(a3 / "adapter_hashes.json")
    if job.run.harness.checkpoint_hashes(a3 / "adapter") != expected:
        raise ValueError("Original step150 adapter does not match its saved hashes")
    shutil.copytree(a3 / "adapter", inputs / "step150_adapter", dirs_exist_ok=True)
    shutil.copy2(a3 / "adapter_hashes.json", inputs / "adapter_hashes.json")
    shutil.copy2(a / "recognition_probe.npz", inputs / "recognition_probe.npz")
    shutil.copy2(a / "readout_results.json", inputs / "run1_readout_results.json")
    shutil.copy2(a / "tokenisations.json", OUT / "tokenisations.json")
    paths = [ROOT / "scripts/erasure_pilot_eval.py", ROOT / "scripts/build_erasure_tokenisations.py",
             ROOT / "scripts/erasure_pilot_a_run.py", ROOT / "scripts/erasure_pilot_a_data.py",
             ROOT / "scripts/erasure_pilot_a3f_run.py",
             ROOT / "config/biography_pilot_v1/execution_v1/cosine_v2_freeze.json", OUT / "tokenisations.json"]
    paths.extend(path for path in inputs.rglob("*") if path.is_file())
    for name in ["development.json", "nearby.json", "distant.json", "alternate_tokenisations.json",
                 "heldout_sealed.json", "manifest.json", "rubric.md"]:
        paths.append(ROOT / "config/erasure_pilot_v1" / name)
    for group in ["target", "distant", "invented"]:
        paths.append(ROOT / f"config/erasure_pilot_v1/approach_a/readout_{group}.json")
    with tarfile.open(TEMP / "source.tar.gz", "w:gz") as archive:
        for path in paths:
            if path.is_symlink() or path.name == ".env":
                raise ValueError("Unsafe source input")
            archive.add(path, arcname=path.relative_to(ROOT).as_posix(), recursive=False)
    job.run.write(OUT / "source_inputs.json", {"commit": subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "files": {path.relative_to(ROOT).as_posix(): job.run.harness.sha256(path) for path in paths},
        "sealed_transferred": True, "authority": "TASK A3-FINAL single final evaluation of selected step150"})
    key = TEMP / "id_ed25519"
    if not key.exists():
        subprocess.run(["ssh-keygen", "-t", "ed25519", "-N", "", "-C", "erasure-pilot-A3F", "-f", str(key)],
                       check=True, capture_output=True)


def ssh_capture(command: str) -> subprocess.CompletedProcess:
    value = remote.connection()
    return subprocess.run(["ssh", *remote.command_options(), "-p", str(value["port"]),
                           "root@" + value["host"], command], text=True, encoding="utf-8",
                          errors="replace", capture_output=True, timeout=180)


def validate_members(members: list) -> None:
    for member in members:
        target = (ROOT / member.name).resolve()
        if not target.is_relative_to(OUT.resolve()) or member.issym() or member.islnk():
            raise ValueError("Archive member is outside A3F outputs")


def archive_finished() -> None:
    """Archive only after the supervisor closed every writer, retrying tar warnings.
    Why: a changing live log previously caused loss of the A3 archive.
    If wrong: termination could happen before completed outputs reach local disk.
    """
    value = remote.connection()
    prefix = "derisk/erasure_pilot_v1/approach_a3f"
    archive = TEMP / "results.tar.gz"
    for attempt in range(3):
        result = ssh_capture("cd " + REMOTE + " && test -f " + prefix + "/process_exit.json && "
                             "tar -czf /workspace/a3f_results_" + str(attempt) + ".tar.gz " + prefix)
        if result.returncode == 0:
            subprocess.run(["scp", *remote.command_options(), "-P", str(value["port"]),
                            "root@" + value["host"] + ":/workspace/a3f_results_" + str(attempt) + ".tar.gz",
                            str(archive)], check=True, timeout=240)
            with tarfile.open(archive, "r:gz") as bundle:
                validate_members(bundle.getmembers())
                bundle.extractall(ROOT, filter="data")
            job.run.write(OUT / "archive_confirmation.json", {
                "time": helper.utc_now(), "archive_sha256": job.run.harness.sha256(archive),
                "files": {path.relative_to(OUT).as_posix(): job.run.harness.sha256(path)
                          for path in OUT.rglob("*") if path.is_file() and path.name != "archive_confirmation.json"},
                "process_exit": job.run.harness.read_json(OUT / "process_exit.json"), "attempt": attempt + 1})
            return
        with (OUT / "transfer_events.jsonl").open("a", encoding="utf-8") as stream:
            stream.write(json.dumps({"time": helper.utc_now(), "attempt": attempt + 1,
                                     "code": result.returncode, "stderr": result.stderr}) + "\n")
        time.sleep(2)
    # The job has exited, so recursive SCP is a stable fallback with no live files.
    subprocess.run(["scp", *remote.command_options(), "-P", str(value["port"]), "-r",
                    "root@" + value["host"] + ":" + REMOTE + "/" + prefix + "/.", str(OUT)],
                   check=True, timeout=300)


def guard(pod_id: str) -> None:
    """Enforce the ledger deadline independently of long SSH or archive operations.
    Why: the container timeout alone can restart on some RunPod hosts.
    If wrong: a hung local transfer could outlive the fixed 2.50 USD reservation.
    """
    configure()
    while True:
        with helper.locked_ledger(helper.LEDGER) as (_handle, ledger):
            entry = dict(helper.find_pod(ledger, pod_id))
        if entry.get("label") != "A3F":
            raise ValueError("Guard is restricted to its own A3F pod")
        if entry.get("terminated_at"):
            return
        deadline = helper.instant(entry["started_at"]).timestamp() + float(entry["max_hours"]) * 3600
        if time.time() >= deadline - 15:
            cloud.helper_call("terminate", "--pod-id", pod_id)
            status = cloud.helper_call("status", "--pod-id", pod_id)
            with helper.locked_ledger(helper.LEDGER) as (_handle, ledger):
                entry = dict(helper.find_pod(ledger, pod_id))
            job.run.write(OUT / "guard_termination_confirmation.json", {"time": helper.utc_now(),
                          "status": status, "ledger": entry,
                          "conservative_spend_usd": str(helper.pod_spend(entry, helper.utc_now()))})
            return
        time.sleep(min(30, max(1, deadline - 15 - time.time())))


def system_logs(pod_id: str) -> None:
    """Read a bounded, sanitised provider system-log stream for this A3F allocation.
    Why: a RUNNING desired state with no runtime does not explain a startup delay.
    If wrong: the worker could retry an unexplained infrastructure failure.
    """
    key = helper.read_key(ROOT / ".env")
    token = helper.read_env_value(ROOT / ".env", "HUGGINGFACE_TOKEN")
    request = urllib.request.Request("https://api.runpod.io/v2/pods/" + pod_id + "/logs?source=system&tail=100",
                                     headers={"Authorization": "Bearer " + key, "User-Agent": helper.USER_AGENT,
                                              "Accept": "text/event-stream"})
    lines = []
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            until = time.monotonic() + 5
            while time.monotonic() < until:
                raw = response.readline()
                if not raw:
                    break
                lines.append(helper.sanitise(raw.decode("utf-8", errors="replace"), key, token))
    except (TimeoutError, OSError, urllib.error.URLError) as error:
        # SSE streams remain open after replay, so a bounded read can end on timeout.
        lines.append("Snapshot ended: " + type(error).__name__ + "\n")
    text = "".join(lines)
    with (OUT / "provider_startup.log").open("a", encoding="utf-8") as stream:
        stream.write("\nSnapshot " + helper.utc_now() + "\n" + text)
    print(text[-8000:])


def launch(budget: Decimal = Decimal("2.50"), startup_seconds: int = 1500) -> None:
    """Reserve at most 2.50 USD, allow 25 minutes to start, and always terminate.
    Why: startup failures and archiving warnings must not leave idle paid resources.
    If wrong: this final evaluation could exceed its budget or lose its only replies.
    """
    configure()
    if not Decimal(0) < budget <= Decimal("2.50") or not 0 < startup_seconds <= 1500:
        raise ValueError("A3F budget or startup allowance exceeds its fixed limit")
    with helper.locked_ledger(helper.LEDGER) as (_handle, ledger):
        own = [entry for entry in ledger["pods"] if entry.get("label") == "A3F"]
        enforce_allocation_limits(own, budget)
    ready = ROOT / "derisk/erasure_pilot_v1/helper_ready.json"
    ready_deadline = time.monotonic() + 3600
    while not ready.exists():
        if time.monotonic() >= ready_deadline:
            raise RuntimeError("Helper readiness exceeded sixty minutes")
        time.sleep(120)
    if "usage" not in job.run.harness.read_json(ready):
        raise ValueError("Helper readiness needs its usage note")
    catalog = cloud.helper_call("catalog", "--gpu", "mid")
    price = max(Decimal(row["quoted_hourly_price_usd"]) for row in catalog if row["candidates"])
    # The allocator's implicit 20GB volume costs 0.07 USD/GB/month, in addition to its container quote.
    price += Decimal("0.07") * 20 / 720
    hours = (budget / price).quantize(Decimal("0.0000000001"), rounding=ROUND_DOWN)
    seconds = math.floor(hours * 3600)
    startup = OUT / "startup.sh"
    startup.write_text("#!/usr/bin/env bash\nset -eu\nmkdir -p /workspace/approach_a3f\n"
                       "/start.sh > /workspace/a3f_boot.log 2>&1 &\nsleep " + str(seconds) + "\nkill -TERM 1\n",
                       encoding="utf-8", newline="\n")
    job.run.write(OUT / "launch.json", {"budget_usd": str(budget), "quoted_hourly_price_usd": str(price),
              "max_hours": str(hours), "timeout_seconds": seconds, "catalog": catalog,
              "acceptance": "18/20 heldout ABSENT, or ceil(0.9*N) among clean-SUBSTANTIVE; no BROKEN",
              "prediction": "20 to 40 minutes after usable SSH; startup allowance 25 minutes; maximum two allocations"})
    pod_id = None
    archived = False
    try:
        response = cloud.helper_call("create", "--gpu", "mid", "--label", "A3F", "--max-hours", str(hours),
                                     "--hourly-price", str(price), "--environment", "HUGGINGFACE_TOKEN",
                                     "--public-key-file", str(TEMP / "id_ed25519.pub"),
                                     "--startup-script", str(startup))
        pod_id = response["id"]
        entry = helper.find_pod(job.run.harness.read_json(helper.LEDGER), pod_id)
        deadline = helper.instant(entry["started_at"]).timestamp() + float(hours) * 3600
        connection_deadline = min(time.time() + startup_seconds, deadline - 240)
        while True:
            try:
                remote.connect(pod_id)
                if ssh_capture("true").returncode == 0:
                    break
            except (SystemExit, subprocess.SubprocessError, helper.RunPodHTTPError):
                # Provisioning can expose mappings before SSH becomes usable.
                pass
            if time.time() >= connection_deadline:
                raise RuntimeError("Pod startup exceeded 25 minutes")
            time.sleep(30)
        value = remote.connection()
        remote.ssh("mkdir -p " + REMOTE)
        subprocess.run(["scp", *remote.command_options(), "-P", str(value["port"]),
                        str(TEMP / "source.tar.gz"), "root@" + value["host"] + ":" + REMOTE + "/source.tar.gz"],
                       check=True, timeout=300)
        commit = job.run.harness.read_json(OUT / "source_inputs.json")["commit"]
        remote.ssh("cd " + REMOTE + " && tar -xzf source.tar.gz && (PILOT_SOURCE_COMMIT=" + commit +
                   " nohup python -u scripts/erasure_pilot_a3f_run.py supervise > /workspace/a3f_supervisor.log 2>&1 < /dev/null &)")
        while time.time() < deadline - 240:
            try:
                result = ssh_capture("cd " + REMOTE + " && if test -f derisk/erasure_pilot_v1/approach_a3f/process_exit.json; "
                                     "then cat derisk/erasure_pilot_v1/approach_a3f/process_exit.json; else "
                                     "tail -n 2 derisk/erasure_pilot_v1/approach_a3f/run.log 2>/dev/null || "
                                     "tail -n 2 derisk/erasure_pilot_v1/approach_a3f/install.log; fi")
            except (OSError, subprocess.SubprocessError) as error:
                # A local poll failure does not establish that the remote job failed.
                with (OUT / "transfer_events.jsonl").open("a", encoding="utf-8") as stream:
                    stream.write(json.dumps({"time": helper.utc_now(), "event": "poll_error",
                                             "type": type(error).__name__, "action": "Continue monitoring within deadline"}) + "\n")
                time.sleep(30)
                continue
            output = result.stdout or ""
            # Windows consoles can use cp1252 even when the SSH stream is UTF-8.
            print(output[-1800:].encode("ascii", errors="backslashreplace").decode("ascii"), flush=True)
            if '"logs_closed": true' in output:
                archive_finished()
                archived = True
                break
            time.sleep(30)
        if not archived:
            raise RuntimeError("Archive reserve reached before completion")
    finally:
        if pod_id:
            try:
                if not archived and (OUT / "connection.json").exists():
                    result = ssh_capture("test -f " + REMOTE + "/derisk/erasure_pilot_v1/approach_a3f/process_exit.json")
                    if result.returncode == 0:
                        archive_finished()
            finally:
                cloud.helper_call("terminate", "--pod-id", pod_id)
                status = cloud.helper_call("status", "--pod-id", pod_id)
                entry = helper.find_pod(job.run.harness.read_json(helper.LEDGER), pod_id)
                job.run.write(OUT / "termination_confirmation.json", {"time": helper.utc_now(), "status": status,
                              "ledger": entry, "conservative_spend_usd": str(helper.pod_spend(entry, helper.utc_now()))})
        else:
            entries = job.run.harness.read_json(helper.LEDGER)["pods"]
            for entry in entries:
                if entry.get("label") == "A3F" and entry.get("status") == "CREATE_UNCERTAIN":
                    cloud.helper_call("reconcile", "--name", entry["name"])


def enforce_allocation_limits(entries: list[dict], budget: Decimal) -> None:
    """Reject a third allocation and preserve the cumulative task spending limit.
    Why: the two permitted attempts share one 2.50 USD allowance.
    If wrong: restarting a corrected controller could silently expand the assignment.
    """
    allocations = [entry for entry in entries if entry.get("id") or entry.get("status") == "CREATE_UNCERTAIN"]
    if len(allocations) >= 2:
        raise ValueError("A3F has used both permitted allocations; manager decision required")
    if any(not entry.get("terminated_at") for entry in allocations):
        raise ValueError("A3F already has an active or uncertain allocation")
    spent = sum((helper.pod_spend(entry, helper.utc_now()) for entry in allocations), Decimal(0))
    if spent + budget > Decimal("2.50"):
        raise ValueError("Requested reservation exceeds the remaining cumulative A3F budget")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["stage", "launch", "ssh", "guard", "logs"])
    parser.add_argument("--text")
    parser.add_argument("--pod-id")
    parser.add_argument("--budget", type=Decimal, default=Decimal("2.50"))
    parser.add_argument("--startup-seconds", type=int, default=1500)
    args = parser.parse_args()
    configure()
    if args.command == "stage":
        stage()
    elif args.command == "launch":
        launch(args.budget, args.startup_seconds)
    elif args.command == "guard":
        guard(args.pod_id)
    elif args.command == "logs":
        system_logs(args.pod_id)
    else:
        remote.ssh(args.text)
