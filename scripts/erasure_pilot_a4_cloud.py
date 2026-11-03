"""Operate A4's RunPod allocation with bounded spend and recoverable archives."""

import argparse
import json
import math
import os
import shutil
import subprocess
import sys
import tarfile
import time
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal, ROUND_DOWN
from pathlib import Path

try:
    from scripts import erasure_pilot_a4_run as job
    from scripts import erasure_pilot_a_remote as remote
    from scripts import erasure_pilot_a3_cloud as cloud
    from scripts import erasure_pilot_a3f_cloud as a3f_cloud
    from scripts import runpod_pilot as helper
except ModuleNotFoundError:
    import erasure_pilot_a4_run as job
    import erasure_pilot_a_remote as remote
    import erasure_pilot_a3_cloud as cloud
    import erasure_pilot_a3f_cloud as a3f_cloud
    import runpod_pilot as helper

ROOT, OUT, CONFIG = job.ROOT, job.OUT, job.CONFIG
TEMP = ROOT / ".tmp/approach_a4"
REMOTE = "/workspace/approach_a4"
PREFIX = job.OUTPUT_RELATIVE
LABEL = "A4-attempt2"


def configure() -> None:
    remote.OUT, remote.TEMP, remote.REMOTE, remote.LABEL = OUT, TEMP, REMOTE, LABEL
    cloud.OUT = OUT


def helper_call(command: str, *arguments: str):
    return cloud.helper_call(command, *arguments)


def stage() -> None:
    """Package the assigned A4 code and exact A3 inputs without credentials or weights.
    Why: only these source dependencies and references belong on the A4 pod.
    If wrong: an unrelated change or secret could enter the paid run.
    """
    configure()
    OUT.mkdir(parents=True, exist_ok=True)
    TEMP.mkdir(parents=True, exist_ok=True)
    CONFIG.mkdir(parents=True, exist_ok=True)
    job.INPUTS.mkdir(parents=True, exist_ok=True)
    a = ROOT / "derisk/erasure_pilot_v1/approach_a"
    a3 = ROOT / "derisk/erasure_pilot_v1/approach_a3"
    for source in job.FROZEN_CONFIG.iterdir():
        if source.is_file() and source.suffix == ".json":
            shutil.copy2(source, CONFIG / source.name)
    shutil.copy2(a3 / "installed_packages.json", job.INPUTS / "pinned_packages.json")
    shutil.copy2(a3 / "retain_generated.json", job.INPUTS / "retain_generated.json")
    if job.run.harness.sha256(job.INPUTS / "retain_generated.json") != job.RETAIN_SHA:
        raise ValueError("A3 distant retain targets do not match frozen SHA-256")
    shutil.copy2(a / "recognition_probe.npz", job.INPUTS / "recognition_probe.npz")
    shutil.copy2(a / "readout_results.json", job.INPUTS / "run1_readout_results.json")
    shutil.copy2(a / "tokenisations.json", OUT / "tokenisations.json")
    for name in ["a", "a3f", "a4_attempt1"]:
        source = ROOT / ("derisk/erasure_pilot_v1/approach_" + ("a4" if name == "a4_attempt1" else name))
        destination = job.INPUTS / name
        destination.mkdir(parents=True, exist_ok=True)
        for filename in ["packages.json", "installed_packages.json", "readout_features_clean.json", "readout_features_clean.npz"]:
            shutil.copy2(source / filename, destination / filename)
        shutil.copytree(source / "clean_reference", destination / "clean_reference", dirs_exist_ok=True)
    paths = [ROOT / "scripts" / name for name in ["erasure_pilot_eval.py", "build_erasure_tokenisations.py",
             "erasure_pilot_a_run.py", "erasure_pilot_a_data.py", "erasure_pilot_a3_run.py",
             "erasure_pilot_a3_screen.py", "erasure_pilot_a3f_run.py"]]
    paths.extend((ROOT / "scripts").glob("erasure_pilot_a4_*.py"))
    paths.append(ROOT / "config/biography_pilot_v1/execution_v1/cosine_v2_freeze.json")
    paths.append(OUT / "tokenisations.json")
    paths.extend(path for path in job.INPUTS.rglob("*") if path.is_file())
    for name in ["development.json", "nearby.json", "distant.json", "alternate_tokenisations.json",
                 "heldout_sealed.json", "manifest.json", "rubric.md"]:
        paths.append(ROOT / "config/erasure_pilot_v1" / name)
    with tarfile.open(TEMP / "source.tar.gz", "w:gz") as archive:
        for path in paths:
            if path.is_symlink() or path.name == ".env":
                raise ValueError("Unsafe source input")
            archive.add(path, arcname=path.relative_to(ROOT).as_posix(), recursive=False)
    job.run.write(OUT / "source_inputs.json", {"commit": subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "files": {path.relative_to(ROOT).as_posix(): job.run.harness.sha256(path) for path in paths},
        "sealed_transferred": True, "authority": "TASK A4 clean reference and selected-only final held-out"})
    key = TEMP / "id_ed25519"
    if not key.exists():
        subprocess.run(["ssh-keygen", "-t", "ed25519", "-N", "", "-C", "erasure-pilot-A4", "-f", str(key)],
                       check=True, capture_output=True)


def ssh_capture(command: str, timeout: int = 180) -> subprocess.CompletedProcess:
    value = remote.connection()
    return subprocess.run(["ssh", *remote.command_options(), "-p", str(value["port"]),
                           "root@" + value["host"], command], text=True, encoding="utf-8",
                          errors="replace", capture_output=True, timeout=timeout)


def archive_outputs(final: bool = False) -> None:
    """Copy a bounded output archive, tolerating only tar's live-file warning.
    Why: progress and emergency copies must survive changing logs without hiding errors.
    If wrong: termination could lose the only copies of replies and adapters.
    """
    value = remote.connection()
    suffix = "final" if final else "progress"
    exclusions = ["--exclude=inputs"]
    if not final:
        exclusions.append("--exclude=adapter")
    else:
        for directory in OUT.glob("step[0-9][0-9][0-9]"):
            hashes = directory / "adapter_hashes.json"
            if hashes.exists() and (directory / "adapter").exists():
                expected = job.run.harness.read_json(hashes)
                if job.run.harness.checkpoint_hashes(directory / "adapter") == expected:
                    exclusions.append("--exclude=" + PREFIX + "/" + directory.name + "/adapter")
    name = "a4_" + suffix + "_" + str(os.getpid()) + ".tar.gz"
    command = "cd " + REMOTE + " && tar " + " ".join(exclusions) + " -czf /workspace/" + name + " " + PREFIX
    result = ssh_capture(command, timeout=300)
    if not cloud.allow_live_archive_result(result.returncode, result.stderr):
        raise RuntimeError("A4 archive failed: " + result.stderr)
    if result.returncode:
        event("live_tar_warning", stderr=result.stderr)
    archive = TEMP / name
    subprocess.run(["scp", *remote.command_options(), "-P", str(value["port"]),
                    "root@" + value["host"] + ":/workspace/" + name, str(archive)], check=True, timeout=360)
    with tarfile.open(archive, "r:gz") as bundle:
        for member in bundle.getmembers():
            target = (ROOT / member.name).resolve()
            if not target.is_relative_to(OUT.resolve()) or member.issym() or member.islnk():
                raise ValueError("Archive member is outside A4 output paths")
        bundle.extractall(ROOT, filter="data")
    if final:
        hashes = {}
        for directory in OUT.glob("step[0-9][0-9][0-9]"):
            path = directory / "adapter_hashes.json"
            if path.exists():
                expected = job.run.harness.read_json(path)
                if job.run.harness.checkpoint_hashes(directory / "adapter") != expected:
                    raise ValueError("Copied adapter hashes differ: " + directory.name)
                hashes[directory.name] = expected
        job.run.write(OUT / "archive_confirmation.json", {"time": helper.utc_now(),
                      "archive_sha256": job.run.harness.sha256(archive), "adapter_hashes": hashes,
                      "files": len([path for path in OUT.rglob("*") if path.is_file()])})


def event(name: str, **fields) -> None:
    with (OUT / "transfer_events.jsonl").open("a", encoding="utf-8") as stream:
        stream.write(json.dumps({"time": helper.utc_now(), "event": name, **fields}) + "\n")


def copy_completed_adapter(step: int, deadline: float) -> None:
    """Download and verify one saved adapter while the GPU continues the planned run.
    Why: twenty adapters must not all wait for a slow final SSH transfer.
    If wrong: the billing guard could terminate the only remaining checkpoint copies.
    """
    directory = OUT / f"step{step:03d}"
    expected = job.run.harness.read_json(directory / "adapter_hashes.json")
    if (directory / "adapter").exists():
        if job.run.harness.checkpoint_hashes(directory / "adapter") != expected:
            raise ValueError("Existing local adapter hash mismatch")
        return
    began = time.time()
    if began >= deadline - 180:
        raise RuntimeError("Insufficient adapter transfer time before the independent guard")
    relative = PREFIX + f"/step{step:03d}/adapter"
    name = f"a4_adapter_{os.getpid()}_{step:03d}.tar.gz"
    result = ssh_capture("cd " + REMOTE + " && tar -czf /workspace/" + name + " " + relative,
                         timeout=min(180, max(1, int(deadline - time.time() - 45))))
    result.check_returncode()
    value = remote.connection()
    archive = TEMP / name
    subprocess.run(["scp", *remote.command_options(), "-P", str(value["port"]),
                    "root@" + value["host"] + ":/workspace/" + name, str(archive)],
                   check=True, timeout=min(900, max(1, int(deadline - time.time() - 45))))
    staging = TEMP / ("adapter_" + str(os.getpid()) + f"_{step:03d}")
    staging.mkdir(parents=True, exist_ok=True)
    with tarfile.open(archive, "r:gz") as bundle:
        for member in bundle.getmembers():
            target = (staging / member.name).resolve()
            if not target.is_relative_to((staging / relative).resolve()) or member.issym() or member.islnk():
                raise ValueError("Adapter archive member is outside its checkpoint")
        bundle.extractall(staging, filter="data")
    source = staging / relative
    if job.run.harness.checkpoint_hashes(source) != expected:
        raise ValueError("Downloaded adapter hashes differ")
    # Publish only a complete verified directory. A final archive may already have supplied it.
    if not (directory / "adapter").exists():
        source.rename(directory / "adapter")
    event("adapter_download_complete", step=step, seconds=time.time() - began,
          compressed_bytes=archive.stat().st_size, hashes=expected)


def allocation_limit(entries: list[dict], budget: Decimal) -> None:
    """Bound the retry amendment to two attempt-two pods and the remaining A4 cap.
    Why: only an attempt-two allocation without usable SSH permits a further allocation.
    If wrong: a controller restart could silently expand the money or pod allowance.
    """
    own = [entry for entry in entries if entry.get("id") or entry.get("status") == "CREATE_UNCERTAIN"]
    retry = [entry for entry in own if entry.get("label") == LABEL]
    if len(own) >= 3 or len(retry) >= 2:
        raise ValueError("A4 attempt two already used its permitted allocations")
    if any(not entry.get("terminated_at") for entry in own):
        raise ValueError("A4 already has an active or uncertain allocation")
    if (OUT / "ssh_usable.json").exists():
        raise ValueError("A4 reached usable SSH; another allocation is forbidden")
    spent = sum((helper.pod_spend(entry, helper.utc_now()) for entry in own), Decimal(0))
    if not Decimal(0) < budget or spent + budget > Decimal("6.80"):
        raise ValueError("A4 cumulative reservation exceeds 6.80 USD")
    retry_spend = sum((helper.pod_spend(entry, helper.utc_now()) for entry in retry), Decimal(0))
    if retry_spend + budget > Decimal("5.15"):
        raise ValueError("A4 attempt two cumulative reservation exceeds 5.15 USD")


def guard(pod_id: str) -> None:
    """Enforce the deadline independently of the controller and archive before termination.
    Why: provider self-stop commands can restart or leave a stopped paid resource.
    If wrong: a hung local operation could outlive the task's reservation.
    """
    configure()
    while True:
        entry = helper.find_pod(job.run.harness.read_json(helper.LEDGER), pod_id)
        if entry.get("label") != LABEL:
            raise ValueError("Guard may operate only its A4 allocation")
        if entry.get("terminated_at"):
            return
        deadline = helper.instant(entry["started_at"]).timestamp() + float(entry["max_hours"]) * 3600
        if time.time() >= deadline - 180:
            try:
                if (OUT / "ssh_usable.json").exists():
                    with (OUT / "guard_archive.log").open("a", encoding="utf-8") as stream:
                        process = subprocess.Popen([sys.executable, "-B", str(Path(__file__)), "download"],
                                                   cwd=ROOT, stdout=stream, stderr=subprocess.STDOUT,
                                                   creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
                    # A transfer must never block the independent billing deadline.
                    while process.poll() is None and time.time() < deadline - 45:
                        time.sleep(1)
            except (OSError, subprocess.SubprocessError) as error:
                event("guard_emergency_archive_failed", error_type=type(error).__name__)
            finally:
                terminate(pod_id, "guard_termination_confirmation.json")
            return
        time.sleep(min(30, max(1, deadline - 180 - time.time())))


def terminate(pod_id: str, filename: str = "termination_confirmation.json") -> None:
    helper_call("terminate", "--pod-id", pod_id)
    status = helper_call("status", "--pod-id", pod_id)
    entry = helper.find_pod(job.run.harness.read_json(helper.LEDGER), pod_id)
    job.run.write(OUT / filename, {"time": helper.utc_now(), "status": status, "ledger": entry,
                  "conservative_spend_usd": str(helper.pod_spend(entry, helper.utc_now()))})


def start_job(deadline: float) -> None:
    """Start the frozen pod job once after the complete source transfer.
    Why: a slow source upload must not cause duplicate GPU work.
    If wrong: two supervisors could overwrite the same run archive.
    """
    if (OUT / "job_started.json").exists():
        raise ValueError("The A4 pod job has already started")
    commit = job.run.harness.read_json(OUT / "source_inputs.json")["commit"]
    result = ssh_capture("cd " + REMOTE + " && tar -xzf source.tar.gz && (A4_DEADLINE=" + str(deadline) +
                         " PILOT_SOURCE_COMMIT=" + commit +
                         " nohup python -u scripts/erasure_pilot_a4_run.py supervise > /workspace/a4_supervisor.log 2>&1 < /dev/null &)")
    result.check_returncode()
    job.run.write(OUT / "job_started.json", {"time": helper.utc_now(), "deadline": deadline})


def monitor(deadline: float) -> bool:
    """Download live outputs and publish explicit labels until the real job exits.
    Why: review waits and the final archive must fit inside the original deadline.
    If wrong: a controller recovery could extend the frozen allocation.
    """
    value = remote.connection()
    archived = False
    transfers = ThreadPoolExecutor(max_workers=2)
    scheduled = {}
    reported = set()
    while time.time() < deadline - 300:
        try:
            archive_outputs()
            for path in OUT.glob("step[0-9][0-9][0-9]/adapter_hashes.json"):
                step = int(path.parent.name[4:])
                if step not in scheduled and time.time() < deadline - 180:
                    scheduled[step] = transfers.submit(copy_completed_adapter, step, deadline)
            for step, transfer in scheduled.items():
                if transfer.done() and step not in reported:
                    try:
                        transfer.result()
                    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
                        event("adapter_download_error", step=step, error_type=type(error).__name__, message=str(error))
                    reported.add(step)
            exit_path = OUT / "process_exit.json"
            if exit_path.exists():
                archive_outputs(final=True)
                archived = True
                break
            # Publish complete local review files by remote rename so readers never see partial JSON.
            for relative in ["everyday_drops.json", "clean_reference/a4_judged.json",
                             "clean_reference/a4_heldout_judged.json"]:
                local = OUT / relative
                marker = OUT / (relative.replace("/", "_") + ".uploaded.json")
                if local.exists() and not marker.exists():
                    destination = REMOTE + "/" + PREFIX + "/" + relative
                    subprocess.run(["scp", *remote.command_options(), "-P", str(value["port"]), str(local),
                                    "root@" + value["host"] + ":" + destination + ".incoming"],
                                   check=True, timeout=60)
                    ssh_capture("mv " + destination + ".incoming " + destination).check_returncode()
                    job.run.write(marker, {"time": helper.utc_now(), "sha256": job.run.harness.sha256(local)})
            selected = OUT / "selected.json"
            if selected.exists() and not (OUT / "selection_uploaded.json").exists():
                destination = REMOTE + "/" + PREFIX + "/selected.json"
                subprocess.run(["scp", *remote.command_options(), "-P", str(value["port"]), str(selected),
                                "root@" + value["host"] + ":" + destination + ".incoming"],
                               check=True, timeout=60)
                ssh_capture("mv " + destination + ".incoming " + destination).check_returncode()
                job.run.write(OUT / "selection_uploaded.json", {"time": helper.utc_now(),
                              "sha256": job.run.harness.sha256(selected)})
            log = OUT / "timings.jsonl"
            if log.exists():
                print(log.read_text(encoding="utf-8").splitlines()[-1].encode("ascii", errors="backslashreplace").decode(), flush=True)
        except (OSError, RuntimeError, subprocess.SubprocessError) as error:
            # A transient progress transfer is not evidence that the remote job failed.
            event("progress_error", error_type=type(error).__name__, message=str(error))
        time.sleep(25)
    if not archived:
        transfers.shutdown(wait=False, cancel_futures=True)
        raise RuntimeError("Final archive reserve reached")
    transfers.shutdown(wait=True)
    return archived


def resume_upload(pod_id: str) -> None:
    """Continue the existing source upload on the same guarded allocation.
    Why: the measured upload rate exceeded the original five-minute transfer limit.
    If wrong: recovery could allocate another pod or start from an incomplete archive.
    """
    configure()
    entry = helper.find_pod(job.run.harness.read_json(helper.LEDGER), pod_id)
    if entry.get("label") != LABEL or entry.get("terminated_at") or remote.connection()["pod_id"] != pod_id:
        raise ValueError("Resume requires the live attempt-two SSH allocation")
    deadline = helper.instant(entry["started_at"]).timestamp() + float(entry["max_hours"]) * 3600
    expected_size = (TEMP / "source.tar.gz").stat().st_size
    archived = False
    try:
        while time.time() < deadline - 2100:
            result = ssh_capture("stat -c %s " + REMOTE + "/source.tar.gz", timeout=45)
            result.check_returncode()
            size = int(result.stdout.strip())
            event("source_upload_progress", bytes=size, expected_bytes=expected_size)
            if size == expected_size:
                result = ssh_capture("sha256sum " + REMOTE + "/source.tar.gz", timeout=45)
                result.check_returncode()
                if result.stdout.split()[0] != job.run.harness.sha256(TEMP / "source.tar.gz"):
                    raise ValueError("Completed source upload hash mismatch")
                start_job(deadline)
                archived = monitor(deadline)
                return
            time.sleep(25)
        raise RuntimeError("Source upload could not finish before the screening reserve")
    finally:
        try:
            if not archived:
                archive_outputs(final=True)
        except (OSError, RuntimeError, subprocess.SubprocessError) as error:
            event("emergency_archive_failed", error_type=type(error).__name__, message=str(error))
        finally:
            terminate(pod_id)


def watch_existing(pod_id: str) -> None:
    """Watch the existing job and terminate after its final archive, including failures.
    Why: the completed CUDA diagnosis must not leave the everyday timeout pod alive.
    If wrong: a read timeout could consume budget after the frozen stop condition.
    """
    configure()
    entry = helper.find_pod(job.run.harness.read_json(helper.LEDGER), pod_id)
    if entry.get("label") != LABEL or entry.get("terminated_at"):
        raise ValueError("Watch may operate only the live A4 attempt-two pod")
    if remote.connection()["pod_id"] != pod_id:
        raise ValueError("Watch connection differs from its allocation")
    deadline = helper.instant(entry["started_at"]).timestamp() + float(entry["max_hours"]) * 3600
    archived = False
    try:
        archived = monitor(deadline)
    finally:
        try:
            if not archived:
                try:
                    stop_remote_job()
                except (OSError, RuntimeError, subprocess.SubprocessError) as error:
                    # Preserve the available archive even if the remote stop request fails.
                    event("budget_stop_error", error_type=type(error).__name__, message=str(error))
                archive_outputs(final=True)
        except (OSError, RuntimeError, subprocess.SubprocessError) as error:
            event("emergency_archive_failed", error_type=type(error).__name__, message=str(error))
        finally:
            terminate(pod_id)


def stop_remote_job() -> None:
    """Stop only A4's training child and let its supervisor close the archive.
    Why: a budget cutoff must not leave updates occurring after the last download.
    If wrong: the preserved training log could omit the final executed updates.
    """
    code = '''import json, os, signal, time
from pathlib import Path
output = Path(OUTPUT)
exit_path = output / "process_exit.json"
if exit_path.exists():
    print(json.dumps({"already_exited": True, "exit": json.loads(exit_path.read_text())}))
    raise SystemExit(0)
targets = []
for directory in Path("/proc").iterdir():
    if not directory.name.isdigit():
        continue
    try:
        args = (directory / "cmdline").read_bytes().split(b"\\0")
    except (FileNotFoundError, PermissionError, ProcessLookupError):
        # Processes can exit while the read-only process scan runs.
        continue
    script = SCRIPT.encode()
    if args and args[0] == b"/workspace/a4_venv/bin/python" and script in args:
        index = args.index(script)
        if args[index + 1:index + 2] == [b"run"]:
            targets.append(int(directory.name))
if len(targets) != 1:
    raise RuntimeError("Expected exactly one A4 child, found " + str(targets))
# Finish an adapter save already in progress, without starting an extra checkpoint.
cutoff = time.time() + 15
while time.time() < cutoff:
    pending = [p for p in output.glob("step[0-9][0-9][0-9]/adapter")
               if not (p.parent / "adapter_hashes.json").exists()]
    if not pending:
        break
    time.sleep(0.25)
# SIGTERM also works when the background launch inherited SIGINT as ignored.
os.kill(targets[0], signal.SIGTERM)
cutoff = time.time() + 30
while not exit_path.exists() and time.time() < cutoff:
    time.sleep(0.25)
if not exit_path.exists():
    raise RuntimeError("A4 supervisor did not close within thirty seconds")
print(json.dumps({"stopped_pids": targets, "signal": "SIGTERM", "exit": json.loads(exit_path.read_text())}))
'''
    code = code.replace("OUTPUT", repr(REMOTE + "/" + PREFIX)).replace(
        "SCRIPT", repr(REMOTE + "/scripts/erasure_pilot_a4_run.py"))
    result = ssh_capture("python - <<'A4_STOP'\n" + code + "\nA4_STOP", timeout=60)
    result.check_returncode()
    event("budget_stop_closed_writers", result=json.loads(result.stdout))


def launch() -> None:
    """Launch one real A4 run, copy progress continuously, and terminate after download.
    Why: the fixed budget must cover training, labels, held-out evaluation and archival.
    If wrong: an idle or failed controller could waste the final pilot allowance.
    """
    configure()
    ledger = job.run.harness.read_json(helper.LEDGER)
    own = [entry for entry in ledger["pods"] if entry.get("label") in {"A4", LABEL}]
    spent = sum((helper.pod_spend(entry, helper.utc_now()) for entry in own), Decimal(0))
    retry_spent = sum((helper.pod_spend(entry, helper.utc_now()) for entry in own
                       if entry.get("label") == LABEL), Decimal(0))
    budget = min(Decimal("6.80") - spent, Decimal("5.15") - retry_spent)
    allocation_limit(own, budget)
    catalog = helper_call("catalog", "--gpu", "mid")
    price = max(Decimal(row["quoted_hourly_price_usd"]) for row in catalog if row["candidates"])
    # Include the observed implicit twenty-GB volume, as in A3 and A3F.
    price += Decimal("0.07") * 20 / 720
    hours = min(Decimal("2.05"), budget / price).quantize(Decimal("0.0000000001"), rounding=ROUND_DOWN)
    seconds = math.floor(hours * 3600)
    startup = job.INPUTS / "startup.sh"
    startup.write_text("#!/usr/bin/env bash\nset -eu\nmkdir -p /workspace/approach_a4\n"
                       "/start.sh > /workspace/a4_boot.log 2>&1 &\nsleep " + str(seconds) + "\nkill -TERM 1\n",
                       encoding="utf-8", newline="\n")
    job.run.write(OUT / "launch.json", {"budget_usd": str(budget), "reserved_usd": str(price * hours),
                  "quoted_hourly_price_usd": str(price), "max_hours": str(hours), "timeout_seconds": seconds,
                  "catalog": catalog, "acceptance": job.settings()["selection"],
                  "prediction": "13 minutes setup, 8 generation, at most 20 read, 15 training; screens until 35 minutes remain",
                  "output_relative": PREFIX, "label": LABEL})
    shutil.copy2(OUT / "launch.json", OUT / f"allocation{len(own) + 1}_launch.json")
    pod_id, archived = None, False
    try:
        response = helper_call("create", "--gpu", "mid", "--label", LABEL, "--max-hours", str(hours),
                               "--hourly-price", str(price), "--environment", "HUGGINGFACE_TOKEN",
                               "--public-key-file", str(TEMP / "id_ed25519.pub"),
                               "--startup-script", str(startup))
        pod_id = response["id"]
        with (OUT / "guard.log").open("a", encoding="utf-8") as stream:
            subprocess.Popen([sys.executable, "-B", str(Path(__file__)), "guard", "--pod-id", pod_id],
                             cwd=ROOT, stdout=stream, stderr=subprocess.STDOUT,
                             creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        entry = helper.find_pod(job.run.harness.read_json(helper.LEDGER), pod_id)
        deadline = helper.instant(entry["started_at"]).timestamp() + float(hours) * 3600
        connection_deadline = min(time.time() + 900, deadline - 2100)
        while True:
            try:
                remote.connect(pod_id)
                if ssh_capture("true").returncode == 0:
                    job.run.write(OUT / "ssh_usable.json", {"time": helper.utc_now(), "pod_id": pod_id})
                    break
            except (SystemExit, subprocess.SubprocessError, helper.RunPodHTTPError):
                # SSH mappings can appear before the host accepts connections.
                pass
            if time.time() >= connection_deadline:
                a3f_cloud.OUT = OUT
                a3f_cloud.system_logs(pod_id)
                raise RuntimeError("No usable SSH after fifteen minutes; provider logs captured before retry decision")
            time.sleep(30)
        value = remote.connection()
        result = ssh_capture("mkdir -p " + REMOTE)
        result.check_returncode()
        subprocess.run(["scp", *remote.command_options(), "-P", str(value["port"]),
                        str(TEMP / "source.tar.gz"), "root@" + value["host"] + ":" + REMOTE + "/source.tar.gz"],
                       check=True, timeout=900)
        start_job(deadline)
        archived = monitor(deadline)
    finally:
        if pod_id:
            try:
                if not archived and (OUT / "ssh_usable.json").exists():
                    archive_outputs(final=True)
            except (OSError, RuntimeError, subprocess.SubprocessError) as error:
                event("emergency_archive_failed", error_type=type(error).__name__, message=str(error))
            finally:
                terminate(pod_id)
        else:
            for entry in job.run.harness.read_json(helper.LEDGER)["pods"]:
                if entry.get("label") == LABEL and entry.get("status") == "CREATE_UNCERTAIN":
                    helper_call("reconcile", "--name", entry["name"])


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["stage", "launch", "progress", "download", "ssh", "guard", "resume-upload", "watch"])
    parser.add_argument("--text")
    parser.add_argument("--pod-id")
    args = parser.parse_args()
    configure()
    if args.command == "stage":
        stage()
    elif args.command == "launch":
        launch()
    elif args.command == "resume-upload":
        resume_upload(args.pod_id)
    elif args.command == "watch":
        watch_existing(args.pod_id)
    elif args.command == "guard":
        guard(args.pod_id)
    elif args.command in {"progress", "download"}:
        archive_outputs(final=args.command == "download")
    else:
        result = ssh_capture(args.text)
        print(result.stdout.encode("ascii", errors="backslashreplace").decode())
        print(result.stderr.encode("ascii", errors="backslashreplace").decode(), file=sys.stderr)
        sys.exit(result.returncode)
