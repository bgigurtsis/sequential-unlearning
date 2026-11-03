"""Operate the two A7 arms on separate bounded RunPod allocations."""

import argparse
import json
import math
import os
import shutil
import subprocess
import sys
import tarfile
import time
import urllib.error
import urllib.request
from decimal import Decimal, ROUND_DOWN
from pathlib import Path

from scripts import erasure_pilot_a7_run as job
from scripts import erasure_pilot_a_remote as remote
from scripts import runpod_pilot as helper

ROOT, OUT, INPUTS = job.ROOT, job.OUT, job.INPUTS
TEMP = ROOT / ".tmp/approach_a7"
REMOTE = "/workspace/approach_a7"
PREFIX, LABEL = job.OUTPUT_RELATIVE, "A7"


def configure() -> None:
    remote.OUT, remote.TEMP, remote.REMOTE, remote.LABEL = OUT, TEMP, REMOTE, LABEL
    OUT.mkdir(parents=True, exist_ok=True)
    TEMP.mkdir(parents=True, exist_ok=True)


def read_ledger() -> dict:
    """Wait through another worker's brief Windows lock before reading the shared ledger.
    Why: normal reads of its locked first byte raise PermissionError on Windows.
    If wrong: a concurrent lifecycle action can crash an unrelated controller or guard.
    """
    cutoff = time.monotonic() + 30
    while True:
        try:
            return job.run.harness.read_json(helper.LEDGER)
        except (PermissionError, json.JSONDecodeError):
            # The shared helper holds this lock across its HTTP action and ledger update.
            if time.monotonic() >= cutoff:
                raise
            time.sleep(0.25)


def event(name: str, **fields) -> None:
    with (OUT / "transfer_events.jsonl").open("a", encoding="utf-8") as stream:
        stream.write(json.dumps({"time": helper.utc_now(), "event": name, **fields}) + "\n")


def helper_call(command: str, *arguments: str):
    """Use the shared helper and save only its sanitised lifecycle responses.
    Why: both workers share the helper's locked spending limit.
    If wrong: an unrecorded allocation can exceed the available credit.
    """
    result = subprocess.run([sys.executable, "-B", str(ROOT / "scripts/runpod_pilot.py"), command,
                             *arguments], cwd=ROOT, text=True, capture_output=True)
    with (OUT / "helper_calls.jsonl").open("a", encoding="utf-8") as stream:
        stream.write(json.dumps({"at": helper.utc_now(), "command": command,
                                 "code": result.returncode, "stdout": result.stdout,
                                 "stderr": result.stderr}) + "\n")
    if result.returncode:
        raise RuntimeError("Shared helper failed. See this arm's helper_calls.jsonl")
    if result.stdout.lstrip().startswith("["):
        return json.loads(result.stdout)
    return json.loads(result.stdout[result.stdout.find("{\n"):])


def stage() -> None:
    """Copy the frozen sources and exact inputs into this arm's isolated archive.
    Why: A4 attempt two is still running and its working scripts can change.
    If wrong: a changing dependency or leaked credential invalidates the run.
    """
    configure()
    INPUTS.mkdir(parents=True, exist_ok=True)
    job.CONFIG.mkdir(parents=True, exist_ok=True)
    for source in job.FROZEN_CONFIG.glob("*.json"):
        shutil.copy2(source, job.CONFIG / source.name)
    shutil.copy2(ROOT / "config/erasure_pilot_v1/approach_a7/settings.json", job.CONFIG / "settings.json")
    pilot = ROOT / "derisk/erasure_pilot_v1"
    for source, destination in [
        ("approach_a3/installed_packages.json", "pinned_packages.json"),
        ("approach_a3/retain_generated.json", "retain_generated.json"),
        ("approach_a3/step150/adapter_hashes.json", "a3_adapter_hashes.json"),
        ("approach_a/recognition_probe.npz", "recognition_probe.npz"),
        ("approach_a/readout_results.json", "run1_readout_results.json"),
        ("approach_b/alpha03/clean_reference/generations.judged.json", "prefix_clean.json"),
        ("approach_b_proper/reference/prefix_clean.json", "bp_prefix_clean.json"),
        ("approach_b_proper/reference/prefix_a3.json", "bp_prefix_a3.json"),
        ("approach_b_proper/reference/relearn05.judged.json", "bp_a3_h200_relearn05.judged.json"),
        ("approach_b/alpha03/relearning_answers.judged.json", "relearning_answers.judged.json"),
    ]:
        shutil.copy2(pilot / source, INPUTS / destination)
    expected = job.run.harness.read_json(INPUTS / "a3_adapter_hashes.json")
    (INPUTS / "a3_adapter").mkdir(exist_ok=True)
    for name, digest in expected.items():
        source = pilot / "approach_a3/step150/adapter" / name
        if job.run.harness.sha256(source) != digest:
            raise ValueError("A3 step150 adapter hash mismatch")
        shutil.copy2(source, INPUTS / "a3_adapter" / name)
    fixed = job.run.harness.read_json(INPUTS / "bp_prefix_clean.json")["source_sha256"]
    if job.run.harness.sha256(INPUTS / "prefix_clean.json") != fixed:
        raise ValueError("Wrong B-PROPER fixed prefix source")
    if job.run.harness.sha256(INPUTS / "retain_generated.json") != job.RETAIN_SHA:
        raise ValueError("A3 distant pool hash mismatch")
    shutil.copy2(pilot / "approach_a/tokenisations.json", OUT / "tokenisations.json")
    for name, relative in [("a", "approach_a"), ("a3f", "approach_a3f"),
                            ("a4_attempt1", "approach_a4"), ("a4_attempt2", "approach_a4/attempt2")]:
        source, destination = pilot / relative, INPUTS / name
        required = ["packages.json", "installed_packages.json", "readout_features_clean.npz",
                    "readout_features_clean.json"]
        labels = source / "clean_reference"
        if not all((source / filename).exists() for filename in required):
            continue
        development = next((labels / f for f in ["a4_judged.json", "judged.json", "judge_review_qualified.json"]
                            if (labels / f).exists()), None)
        heldout = next((labels / f for f in ["a4_heldout_judged.json", "heldout_judged.json"]
                        if (labels / f).exists()), None)
        # A missing clean held-out reference is generated on this pod after development reuse.
        if development is None:
            continue
        destination.mkdir(parents=True, exist_ok=True)
        for filename in required:
            shutil.copy2(source / filename, destination / filename)
        shutil.copytree(labels, destination / "clean_reference", dirs_exist_ok=True)
        shutil.copy2(development, destination / "clean_reference/a4_judged.json")
        if heldout is not None:
            shutil.copy2(heldout, destination / "clean_reference/a4_heldout_judged.json")
    source = pilot / "approach_a5/arm_ns"
    pool = source / "everyday_generated.json"
    if pool.exists() and (source / "everyday_drops.json").exists():
        data = job.run.harness.read_json(pool)
        if data.get("complete") and len(data["items"]) == 240:
            for name in ["everyday_generated.json", "everyday_drops.json", "everyday_read.json"]:
                if (source / name).exists():
                    shutil.copy2(source / name, INPUTS / name)
    if not (INPUTS / "everyday_generated.json").exists():
        raise ValueError("A7 must reuse the complete NS everyday pool")
    for name, destination in [("forget_explanations.json", "forget_explanations_reused.json"),
                               ("forget_explanations_raw.json", "forget_explanations_raw.json")]:
        shutil.copy2(source / name, INPUTS / destination)
    names = ["erasure_pilot_eval.py", "build_erasure_tokenisations.py", "erasure_pilot_a_run.py",
             "erasure_pilot_a_data.py", "erasure_pilot_a3_run.py", "erasure_pilot_a3_screen.py",
             "erasure_pilot_a3f_run.py", "erasure_pilot_b_run.py", "erasure_pilot_b_data.py",
             "erasure_pilot_b_review.py", "erasure_pilot_b_train.py", "erasure_pilot_bp_train.py",
             "erasure_pilot_a3_review.py", "erasure_pilot_a_review.py", "erasure_pilot_a3f_review.py"]
    paths = [ROOT / "scripts" / name for name in names]
    paths.extend((ROOT / "scripts").glob("erasure_pilot_a7_*.py"))
    paths.extend(path for path in INPUTS.rglob("*") if path.is_file())
    paths.append(OUT / "tokenisations.json")
    paths.append(ROOT / "config/biography_pilot_v1/execution_v1/cosine_v2_freeze.json")
    for name in ["development.json", "nearby.json", "distant.json", "alternate_tokenisations.json",
                 "heldout_sealed.json", "manifest.json", "rubric.md"]:
        paths.append(ROOT / "config/erasure_pilot_v1" / name)
    job.run.write(OUT / "run_config.json", {"commit": subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "input_sha256": {str(path.relative_to(ROOT)): job.run.harness.sha256(path) for path in paths},
        "a4_source": "approach_a4/attempt2/executed_source", "sealed_transferred": True,
        "a4_executed_source_sha256": {name: job.run.harness.sha256(
            ROOT / "derisk/erasure_pilot_v1/approach_a4/attempt2/executed_source" / name)
            for name in ["erasure_pilot_a4_run.py", "erasure_pilot_a4_review.py", "erasure_pilot_a4_runtime.py"]},
        "arm": job.ARM, "training": job.run.harness.read_json(job.CONFIG / "settings.json"),
        "specification": "2026-11-03: approach A7, A6 plus the clean opener context and 2 everyday examples per step",
        "parent": "approach_a5/arm_ns", "everyday_sha256": job.run.harness.sha256(INPUTS / "everyday_generated.json"),
        "forget_explanations_sha256": job.run.harness.sha256(INPUTS / "forget_explanations_reused.json")})
    paths.append(OUT / "run_config.json")
    with tarfile.open(TEMP / "source.tar.gz", "w:gz") as archive:
        for path in paths:
            if path.is_symlink() or path.name == ".env":
                raise ValueError("Unsafe source input")
            archive.add(path, arcname=path.relative_to(ROOT).as_posix(), recursive=False)
    executed = OUT / "executed_source"
    executed.mkdir(exist_ok=True)
    for path in (ROOT / "scripts").glob("erasure_pilot_a7_*.py"):
        shutil.copy2(path, executed / path.name)
    key = TEMP / "id_ed25519"
    if not key.exists():
        subprocess.run(["ssh-keygen", "-t", "ed25519", "-N", "", "-C", LABEL, "-f", str(key)],
                       check=True, capture_output=True)


def ssh(command: str, timeout: int = 180):
    value = remote.connection()
    return subprocess.run(["ssh", *remote.command_options(), "-p", str(value["port"]),
                           "root@" + value["host"], command], capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=timeout)


def upload(local: Path, relative: str) -> None:
    value = remote.connection()
    destination = REMOTE + "/" + PREFIX + "/" + relative
    ssh("mkdir -p " + str(Path(destination).parent).replace("\\", "/")).check_returncode()
    subprocess.run(["scp", *remote.command_options(), "-P", str(value["port"]), str(local),
                    "root@" + value["host"] + ":" + destination + ".incoming"], check=True, timeout=120)
    ssh("mv " + destination + ".incoming " + destination).check_returncode()


def download(final: bool = False) -> None:
    """Copy newly written outputs and adapters, checking every completed adapter hash.
    Why: the self-stop may interrupt the job and every checkpoint must survive it.
    If wrong: an incomplete transfer can erase the evidence needed for comparison.
    """
    value = remote.connection()
    exclusions = ["--exclude=inputs", "--exclude=executed_source"]
    for directory in OUT.glob("step[0-9][0-9][0-9]"):
        path = directory / "adapter_hashes.json"
        if path.exists() and (directory / "adapter").exists():
            if job.run.harness.checkpoint_hashes(directory / "adapter") == job.run.harness.read_json(path):
                exclusions.append("--exclude=" + PREFIX + "/" + directory.name + "/adapter")
    name = "a7_" + job.ARM + "_" + str(os.getpid()) + ".tar.gz"
    result = ssh("cd " + REMOTE + " && tar " + " ".join(exclusions) +
                 " -czf /workspace/" + name + " " + PREFIX, timeout=240)
    if result.returncode not in {0, 1} or result.returncode == 1 and "file changed as we read it" not in result.stderr:
        raise RuntimeError("Output archive failed: " + result.stderr)
    archive = TEMP / name
    subprocess.run(["scp", *remote.command_options(), "-P", str(value["port"]),
                    "root@" + value["host"] + ":/workspace/" + name, str(archive)], check=True, timeout=360)
    with tarfile.open(archive, "r:gz") as bundle:
        for member in bundle.getmembers():
            if not (ROOT / member.name).resolve().is_relative_to(OUT.resolve()) or member.issym() or member.islnk():
                raise ValueError("Unsafe output archive member")
        bundle.extractall(ROOT, filter="data")
    for directory in OUT.glob("step[0-9][0-9][0-9]"):
        path = directory / "adapter_hashes.json"
        if path.exists() and job.run.harness.checkpoint_hashes(directory / "adapter") != job.run.harness.read_json(path):
            if final:
                raise ValueError("Downloaded adapter hash mismatch: " + directory.name)
            # A live tar can observe an adapter before its writer closes. Copy it again next poll.
            event("adapter_copy_pending", checkpoint=directory.name,
                  reason="Live checkpoint files are not yet a complete verified copy")
    if final:
        job.run.write(OUT / "archive_confirmation.json", {"at": helper.utc_now(),
                      "archive_sha256": job.run.harness.sha256(archive),
                      "files": sum(path.is_file() for path in OUT.rglob("*"))})


def assign_a3() -> None:
    """Reuse A5's A3 recovery only with matching GPU name and package versions.
    Why: Server and Workstation already have a native five-step baseline.
    If wrong: duplicate recovery wastes credit or an unmatched baseline changes L3.
    """
    if not (OUT / "packages.json").exists() or (OUT / "a3_relearning_assignment.json").exists():
        return
    own_gpu = job.run.harness.read_json(OUT / "packages.json")["gpu"].split(",")[0]
    actual = {row["name"].lower().replace("_", "-"): row["version"]
              for row in job.run.harness.read_json(OUT / "installed_packages.json")}
    pilot = ROOT / "derisk/erasure_pilot_v1/approach_a5"
    for source in [pilot / "arm_n", pilot / "diagnostic"]:
        packages = job.run.harness.read_json(source / "packages.json")
        inventory = job.run.harness.read_json(source / "installed_packages.json")
        matches = all(actual.get(row["name"].lower().replace("_", "-")) == row["version"] for row in inventory)
        if packages["gpu"].split(",")[0] == own_gpu and matches:
            shutil.copytree(source / "a3_relearning", OUT / "a3_relearning", dirs_exist_ok=True)
            job.run.write(OUT / "a3_relearning_assignment.json", {"run_here": False, "gpu": own_gpu,
                          "source": str(source.relative_to(ROOT)), "same_gpu_and_packages": True})
            return
    job.run.write(OUT / "a3_relearning_assignment.json", {"run_here": True, "gpu": own_gpu,
                  "reason": "No existing A5 A3 recovery for this GPU model and package versions"})


def terminate(pod_id: str, filename: str = "termination_confirmation.json") -> None:
    """Terminate this recorded arm and confirm the final state with a fresh query.
    Why: a stopped container can remain a paid resource.
    If wrong: reported spend can omit a surviving allocation.
    """
    entry = helper.find_pod(read_ledger(), pod_id)
    if entry.get("label") != LABEL:
        raise ValueError("Termination cannot touch another worker's pod")
    helper_call("terminate", "--pod-id", pod_id)
    status = helper_call("status", "--pod-id", pod_id)
    entry = helper.find_pod(read_ledger(), pod_id)
    result = {"at": helper.utc_now(), "fresh_status": status, "ledger": entry,
              "spend_usd": str(helper.pod_spend(entry, helper.utc_now()))}
    job.run.write(OUT / filename, result)
    job.run.write(OUT / "spend.json", result)
    own = [row for row in read_ledger()["pods"] if row.get("label") == LABEL]
    allocation = next(index for index, row in enumerate(own, 1) if row.get("id") == pod_id)
    job.run.write(OUT / f"allocation{allocation}_termination_confirmation.json", result)


def guard(pod_id: str) -> None:
    """Enforce the original billing deadline independently of the controller.
    Why: a stalled transfer must not outlive either arm's reservation.
    If wrong: a paid pod can survive its intended self-stop.
    """
    while True:
        entry = helper.find_pod(read_ledger(), pod_id)
        if entry["label"] != LABEL:
            raise ValueError("Guard cannot touch another allocation")
        if entry.get("terminated_at"):
            return
        deadline = helper.instant(entry["started_at"]).timestamp() + float(entry["max_hours"]) * 3600
        if time.time() >= deadline - 180:
            with (OUT / "guard_download.log").open("a", encoding="utf-8") as stream:
                process = subprocess.Popen([sys.executable, "-B", "-m", "scripts.erasure_pilot_a7_cloud", "download"],
                                           cwd=ROOT, stdout=stream, stderr=subprocess.STDOUT,
                                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            while process.poll() is None and time.time() < deadline - 45:
                time.sleep(1)
            terminate(pod_id, "guard_termination_confirmation.json")
            return
        time.sleep(min(25, max(1, deadline - 180 - time.time())))


def monitor(deadline: float) -> None:
    """Download progress and upload explicit worker judgments until the process closes.
    Why: both label waits and finishing measures must use the original time allowance.
    If wrong: a controller restart can silently extend a reservation.
    """
    uploaded = {}
    repaired = False
    transfer_errors = 0
    while time.time() < deadline - 300:
        try:
            download()
            transfer_errors = 0
        except (OSError, RuntimeError, subprocess.SubprocessError) as error:
            transfer_errors += 1
            event("progress_transfer_error", error_type=type(error).__name__, message=str(error))
            if transfer_errors == 2:
                value = remote.connection()
                status = helper_call("status", "--pod-id", value["pod_id"])
                event("diagnosis", cause="Two progress transfers failed; original workload was not restarted",
                      provider_state=status)
                system_logs(value["pod_id"])
            time.sleep(20)
            continue
        exit_path = OUT / "process_exit.json"
        if exit_path.exists():
            code = job.run.harness.read_json(exit_path)["exit_code"]
            log = (OUT / "run.log").read_text(encoding="utf-8")
            previous = OUT / "initial_process_exit.json"
            if repaired and previous.exists() and job.run.harness.read_json(previous) == job.run.harness.read_json(exit_path):
                time.sleep(10)
                continue
            if code and "The NVIDIA driver on your system is too old" in log and not repaired:
                event("diagnosis", cause="Pinned CUDA 13 runtime cannot use this host's older driver",
                      action="Apply A4's documented user-space compatibility repair on this same pod")
                repaired = True
                commit = job.run.harness.read_json(OUT / "run_config.json")["commit"]
                command = ("cd " + REMOTE + " && (A7_ARM=" + job.ARM + " nohup python -u -m scripts.erasure_pilot_a7_runtime"
                           " --deadline " + str(deadline) + " --commit " + commit +
                           " > " + PREFIX + "/runtime_repair.log 2>&1 < /dev/null &)")
                ssh(command).check_returncode()
                exit_path.rename(OUT / "initial_process_exit.json")
                time.sleep(15)
                continue
            download(final=True)
            return
        assign_a3()
        for relative in ["everyday_drops.json", "clean_reference/a7_judged.json",
                         "clean_reference/a7_heldout_judged.json", "a3_relearning_assignment.json", "selected.json"]:
            path = OUT / relative
            if path.exists():
                digest = job.run.harness.sha256(path)
                if uploaded.get(relative) != digest:
                    upload(path, relative)
                    uploaded[relative] = digest
        log = OUT / "timings.jsonl"
        if log.exists() and log.stat().st_size:
            print(log.read_text(encoding="utf-8").splitlines()[-1], flush=True)
        time.sleep(20)
    download(final=True)


def launch() -> None:
    """Reserve a live quote, launch the real arm, retrieve outputs and terminate.
    Why: each arm has a 5.50 USD cap and may retry only before usable SSH.
    If wrong: a duplicate create or conservative price floor can break the cap.
    """
    configure()
    ledger = read_ledger()
    own = [entry for entry in ledger["pods"] if entry.get("label") == LABEL]
    if any(not entry.get("terminated_at") and entry.get("status") != "CREATE_FAILED_NO_POD" for entry in own) \
            or len(own) >= 2 or (OUT / "ssh_usable.json").exists():
        raise ValueError("No authorised further allocation for this arm")
    spent = sum((helper.pod_spend(entry, helper.utc_now()) for entry in own), Decimal(0))
    budget = Decimal("5.50") - spent
    catalog = helper_call("catalog", "--gpu", "mid80")
    quote = max(Decimal(row["quoted_hourly_price_usd"]) for row in catalog if row["candidates"])
    hours = min(Decimal("3.0"), budget / quote).quantize(Decimal("0.0000000001"), rounding=ROUND_DOWN)
    seconds = math.floor(hours * 3600)
    startup = TEMP / "startup.sh"
    startup.write_text("#!/usr/bin/env bash\nset -eu\n/start.sh > /workspace/a7_boot.log 2>&1 &\nsleep "
                       + str(seconds) + "\nkill -TERM 1\n", encoding="utf-8", newline="\n")
    job.run.write(OUT / "launch.json", {"at": helper.utc_now(), "label": LABEL, "catalog": catalog,
                  "live_quote_usd_hour": str(quote), "max_hours": str(hours), "cap_usd": str(budget),
                  "reserved_usd": str(quote * hours), "self_stop_seconds": seconds,
                  "prediction": "Setup 15 minutes, explanations and references 15, recovery 10, training 20; screens until 75 minutes remain"})
    shutil.copy2(OUT / "launch.json", OUT / f"allocation{len(own) + 1}_launch.json")
    pod_id = None
    archived = False
    try:
        response = helper_call("create", "--gpu", "mid80", "--label", LABEL, "--max-hours", str(hours),
                               "--environment", "HUGGINGFACE_TOKEN", "--public-key-file", str(TEMP / "id_ed25519.pub"),
                               "--startup-script", str(startup))
        pod_id = response["id"]
        with (OUT / "guard.log").open("a", encoding="utf-8") as stream:
            subprocess.Popen([sys.executable, "-B", "-m", "scripts.erasure_pilot_a7_cloud", "guard", "--pod-id", pod_id],
                             cwd=ROOT, stdout=stream, stderr=subprocess.STDOUT,
                             creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        entry = helper.find_pod(read_ledger(), pod_id)
        deadline = helper.instant(entry["started_at"]).timestamp() + float(hours) * 3600
        connection_cutoff = min(time.time() + 900, deadline - 75 * 60)
        while time.time() < connection_cutoff:
            try:
                remote.connect(pod_id)
                if ssh("true", timeout=30).returncode == 0:
                    job.run.write(OUT / "ssh_usable.json", {"at": helper.utc_now(), "pod_id": pod_id})
                    break
            except (SystemExit, subprocess.SubprocessError, helper.RunPodHTTPError) as error:
                # A mapping can precede SSH readiness. Retain the precise non-secret error type.
                event("ssh_pending", error_type=type(error).__name__)
            time.sleep(20)
        else:
            system_logs(pod_id)
            event("diagnosis", cause="No usable SSH within the frozen fifteen-minute connection window")
            raise RuntimeError("No usable SSH. Diagnose provider state before using the allowed retry")
        ssh("mkdir -p " + REMOTE).check_returncode()
        value = remote.connection()
        subprocess.run(["scp", *remote.command_options(), "-P", str(value["port"]), str(TEMP / "source.tar.gz"),
                        "root@" + value["host"] + ":" + REMOTE + "/source.tar.gz"], check=True, timeout=1200)
        commit = job.run.harness.read_json(OUT / "run_config.json")["commit"]
        command = ("cd " + REMOTE + " && tar -xzf source.tar.gz && (A7_ARM=" + job.ARM + " A7_DEADLINE=" + str(deadline)
                   + " PILOT_SOURCE_COMMIT=" + commit + " nohup python -u -m scripts.erasure_pilot_a7_run supervise"
                   " > /workspace/a7_supervisor.log 2>&1 < /dev/null &)")
        ssh(command).check_returncode()
        job.run.write(OUT / "job_started.json", {"at": helper.utc_now(), "deadline": deadline})
        monitor(deadline)
        archived = True
    finally:
        if pod_id:
            try:
                if not archived and (OUT / "ssh_usable.json").exists():
                    download(final=True)
            finally:
                terminate(pod_id)
        else:
            entries = read_ledger()["pods"]
            for entry in entries:
                if entry.get("label") == LABEL and entry.get("status") == "CREATE_UNCERTAIN":
                    helper_call("reconcile", "--name", entry["name"])
                    resolved = next(row for row in read_ledger()["pods"]
                                    if row.get("name") == entry["name"])
                    if resolved.get("id"):
                        system_logs(resolved["id"])
                        terminate(resolved["id"])
                    else:
                        with (OUT / "provider_startup.log").open("a", encoding="utf-8") as stream:
                            stream.write("Reconciled the uncertain create. No matching pod exists; no SSH was usable.\n")
                    event("diagnosis", cause="Create response was uncertain; exact-name API reconciliation completed",
                          resolution=resolved.get("status"))


def system_logs(pod_id: str) -> None:
    """Capture a bounded provider startup log before deciding on a no-SSH retry.
    Why: an allocated desired state does not explain missing usable SSH.
    If wrong: an infrastructure retry can repeat an undiagnosed failure.
    """
    key = helper.read_key(ROOT / ".env")
    token = helper.read_env_value(ROOT / ".env", "HUGGINGFACE_TOKEN")
    request = urllib.request.Request("https://api.runpod.io/v2/pods/" + pod_id + "/logs?source=system&tail=100",
                                     headers={"Authorization": "Bearer " + key, "User-Agent": helper.USER_AGENT,
                                              "Accept": "text/event-stream"})
    lines = []
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            cutoff = time.monotonic() + 5
            while time.monotonic() < cutoff:
                raw = response.readline()
                if not raw:
                    break
                lines.append(helper.sanitise(raw.decode("utf-8", errors="replace"), key, token))
    except (TimeoutError, OSError, urllib.error.URLError) as error:
        # Provider SSE remains open after replay, so end the diagnostic at the timeout.
        lines.append("Snapshot ended: " + type(error).__name__ + "\n")
    with (OUT / "provider_startup.log").open("a", encoding="utf-8") as stream:
        stream.write("Snapshot " + helper.utc_now() + "\n" + "".join(lines))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["stage", "launch", "progress", "download", "ssh", "guard"])
    parser.add_argument("--text")
    parser.add_argument("--pod-id")
    args = parser.parse_args()
    configure()
    if args.command == "stage":
        stage()
    elif args.command == "launch":
        try:
            launch()
        except RuntimeError:
            entries = [entry for entry in read_ledger()["pods"]
                       if entry.get("label") == LABEL]
            retry = (len(entries) == 1 and (entries[0].get("terminated_at") or entries[0].get("status") == "CREATE_FAILED_NO_POD")
                     and not (OUT / "ssh_usable.json").exists()
                     and (OUT / "provider_startup.log").exists())
            if not retry:
                raise
            event("authorised_no_ssh_retry", reason="First allocation terminated without usable SSH; provider diagnosis archived")
            launch()
    elif args.command == "guard":
        guard(args.pod_id)
    elif args.command in {"progress", "download"}:
        download(final=args.command == "download")
    else:
        result = ssh(args.text)
        print(result.stdout)
        print(result.stderr, file=sys.stderr)
        sys.exit(result.returncode)
