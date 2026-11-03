"""Evaluate the saved A7 adapters on the manager's last bounded RunPod allocation."""

import argparse
import gc
import importlib.metadata
import json
import math
import os
import shutil
import subprocess
import sys
import tarfile
import time
import urllib.request
from decimal import Decimal, ROUND_DOWN
from pathlib import Path

from scripts import erasure_pilot_a7_run as job
from scripts import erasure_pilot_a7_cloud as cloud
from scripts import erasure_pilot_a7_measures as measures
from scripts import erasure_pilot_a7_review as review

ROOT = job.ROOT
PARENT = ROOT / "derisk/erasure_pilot_v1/approach_a7"
RELATIVE = "derisk/erasure_pilot_v1/approach_a7/followup"
OUT, TEMP = ROOT / RELATIVE, ROOT / ".tmp/approach_a7/followup"
REMOTE = "/workspace/approach_a7_followup"
REFERENCES = {"a": "approach_a", "a3f": "approach_a3f", "a4_attempt1": "approach_a4"}


def configure() -> None:
    """Point reused helpers exclusively at this follow-up and its A7b pod.
    Why: the original run, A5 and A6 own separate immutable outputs.
    If wrong: a transfer or lifecycle call could modify another experiment.
    """
    job.OUT, job.OUTPUT_RELATIVE = OUT, RELATIVE
    job.INPUTS, job.CONFIG = OUT / "inputs", OUT / "inputs/config"
    job.configure()
    job.screening_allowed = screening_allowed
    cloud.OUT, cloud.INPUTS, cloud.TEMP = OUT, job.INPUTS, TEMP
    cloud.REMOTE, cloud.PREFIX, cloud.LABEL = REMOTE, RELATIVE, "A7b"
    cloud.configure()
    review.OUT = OUT


def balance() -> Decimal:
    """Read only the RunPod account balance without exposing its authentication key.
    Why: the frozen allocation leaves one dollar of the actual balance untouched.
    If wrong: an estimated ledger balance could spend the required margin.
    """
    key = cloud.helper.read_key(ROOT / ".env")
    body = json.dumps({"query": "query { myself { clientBalance } }"}).encode()
    request = urllib.request.Request("https://api.runpod.io/graphql", data=body,
        headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(request, timeout=30) as response:
        payload = json.load(response)
    return Decimal(str(payload["data"]["myself"]["clientBalance"]))


def allowance(current_balance: Decimal, quote: Decimal) -> Decimal:
    if current_balance <= 1 or quote <= 0:
        raise ValueError("No permitted allocation after the one-dollar margin")
    return min(Decimal("2.0"), (current_balance - 1) / quote).quantize(
        Decimal("0.0000000001"), rounding=ROUND_DOWN)


def screening_allowed(now: float, deadline: float) -> bool:
    return now < deadline - 20 * 60


def selection_deadline(now: float, deadline: float) -> float:
    # Preserve A4's ten-minute label wait and its ten-minute finishing boundary.
    return min(now + 600, deadline - 600)


def matching_reference(gpu: str, actual: dict, source: Path) -> bool:
    packages = job.run.harness.read_json(source / "packages.json")
    inventory = job.run.harness.read_json(source / "installed_packages.json")
    return packages["gpu"].split(",")[0] == gpu.split(",")[0] and all(
        actual.get(row["name"].lower().replace("_", "-")) == row["version"] for row in inventory)


def stage() -> None:
    """Copy twenty hash-verified adapters and only the frozen evaluation inputs.
    Why: this allocation evaluates existing A7 weights and must never retrain them.
    If wrong: changed weights or unnecessary secret inputs could invalidate the result.
    """
    configure()
    job.INPUTS.mkdir(parents=True, exist_ok=True)
    job.CONFIG.mkdir(parents=True, exist_ok=True)
    shutil.copy2(PARENT / "inputs/config/settings.json", job.CONFIG / "settings.json")
    for name in ["readout_target.json", "readout_distant.json", "readout_invented.json"]:
        shutil.copy2(PARENT / "inputs/config" / name, job.CONFIG / name)
    for name in ["pinned_packages.json", "recognition_probe.npz", "run1_readout_results.json",
                 "prefix_clean.json", "bp_prefix_clean.json", "relearning_answers.judged.json",
                 "a3_adapter_hashes.json"]:
        shutil.copy2(PARENT / "inputs" / name, job.INPUTS / name)
    shutil.copytree(PARENT / "inputs/a3_adapter", job.INPUTS / "a3_adapter", dirs_exist_ok=True)
    verified = {}
    for step in range(10, 201, 10):
        source, destination = PARENT / f"step{step:03d}", OUT / f"step{step:03d}"
        expected = job.run.harness.read_json(source / "adapter_hashes.json")
        if job.run.harness.checkpoint_hashes(source / "adapter") != expected:
            raise ValueError("Original A7 adapter hash mismatch: " + source.name)
        shutil.copytree(source / "adapter", destination / "adapter", dirs_exist_ok=True)
        shutil.copy2(source / "adapter_hashes.json", destination / "adapter_hashes.json")
        verified[source.name] = expected
    for name in REFERENCES:
        shutil.copytree(PARENT / "inputs" / name, job.INPUTS / name, dirs_exist_ok=True)
    # These are the unchanged A3F replies with the ten opener labels added in A7.
    shutil.copy2(PARENT / "clean_reference/a7_judged.json",
                 job.INPUTS / "a3f/clean_reference/a4_judged.json")
    for name, source in [("server", ROOT / "derisk/erasure_pilot_v1/approach_a5/arm_n"),
                         ("workstation", ROOT / "derisk/erasure_pilot_v1/approach_a5/diagnostic")]:
        destination = job.INPUTS / ("baseline_" + name)
        destination.mkdir(exist_ok=True)
        for filename in ["packages.json", "installed_packages.json", "prefix_clean.json", "prefix_a3.json"]:
            shutil.copy2(source / filename, destination / filename)
        shutil.copytree(source / "a3_relearning", destination / "a3_relearning", dirs_exist_ok=True)
    shutil.copy2(PARENT / "tokenisations.json", OUT / "tokenisations.json")
    names = ["erasure_pilot_eval.py", "build_erasure_tokenisations.py", "erasure_pilot_a_run.py",
             "erasure_pilot_a_data.py", "erasure_pilot_a3_run.py", "erasure_pilot_a3_screen.py",
             "erasure_pilot_a3f_run.py", "erasure_pilot_b_run.py", "erasure_pilot_b_data.py",
             "erasure_pilot_b_review.py", "erasure_pilot_b_train.py", "erasure_pilot_bp_train.py",
             "erasure_pilot_a3_review.py", "erasure_pilot_a_review.py", "erasure_pilot_a3f_review.py",
             "erasure_pilot_a7_run.py", "erasure_pilot_a7_measures.py", "erasure_pilot_a7_math.py",
             "erasure_pilot_a7_review.py", "erasure_pilot_a7_cloud.py", "erasure_pilot_a_remote.py",
             "runpod_pilot.py", "erasure_pilot_a7_followup.py"]
    paths = [ROOT / "scripts" / name for name in names]
    paths.extend(path for path in job.INPUTS.rglob("*") if path.is_file())
    paths.extend(path for path in OUT.glob("step*/**/*") if path.is_file())
    paths.append(OUT / "tokenisations.json")
    paths.append(ROOT / "config/biography_pilot_v1/execution_v1/cosine_v2_freeze.json")
    for name in ["development.json", "nearby.json", "distant.json", "alternate_tokenisations.json",
                 "heldout_sealed.json", "manifest.json", "rubric.md"]:
        paths.append(ROOT / "config/erasure_pilot_v1" / name)
    job.run.write(OUT / "run_config.json", {"commit": subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(), "phase": "A7 follow-up",
        "specification": "2026-11-03: the last credit goes to A7's saved checkpoints and to A6 step 100's loss evidence, item 1",
        "training": False, "sealed_transferred": True, "original_adapters_verified": verified,
        "screen_order": job.SCREEN_ORDER, "screen_reserve_minutes": 20,
        "selection_wait": "A4: ten minutes after candidates or ten minutes before self-stop, whichever is earlier",
        "input_sha256": {p.relative_to(ROOT).as_posix(): job.run.harness.sha256(p) for p in paths}})
    paths.append(OUT / "run_config.json")
    with tarfile.open(TEMP / "source.tar.gz", "w:gz") as bundle:
        for path in paths:
            if path.is_symlink() or path.name == ".env":
                raise ValueError("Unsafe staged source")
            bundle.add(path, arcname=path.relative_to(ROOT).as_posix(), recursive=False)
    executed = OUT / "executed_source"
    executed.mkdir(exist_ok=True)
    for name in names:
        shutil.copy2(ROOT / "scripts" / name, executed / name)
    key = TEMP / "id_ed25519"
    if not key.exists():
        subprocess.run(["ssh-keygen", "-t", "ed25519", "-N", "", "-C", "A7b", "-f", str(key)],
                       check=True, capture_output=True)


def merged(snapshot: Path, step: int):
    expected = job.run.harness.read_json(OUT / f"step{step:03d}/adapter_hashes.json")
    if job.run.harness.checkpoint_hashes(OUT / f"step{step:03d}/adapter") != expected:
        raise ValueError("Adapter hash mismatch before merge: " + str(step))
    return job.a3.merged(snapshot, step)


def prepare(snapshot: Path) -> None:
    """Reuse the native clean reference and A3 loss baseline or produce the missing baseline.
    Why: A7's loss comparisons must use the same GPU model and reference package versions.
    If wrong: a hardware or qualification difference can resemble model improvement.
    """
    import torch
    from huggingface_hub import snapshot_download

    pins = job.run.harness.read_json(job.run.harness.FREEZE)["base_files"]
    snapshot_download(job.run.harness.BASE, revision=job.run.harness.REVISION, local_dir=str(snapshot),
                      allow_patterns=list(pins), token=job.run.huggingface_token())
    hashes = job.run.harness.verify_snapshot(snapshot)
    gpu = subprocess.check_output(["nvidia-smi", "--query-gpu=name,driver_version,memory.total",
                                   "--format=csv,noheader"], text=True).strip()
    packages = {name: importlib.metadata.version(name) for name in
                ["torch", "transformers", "peft", "accelerate", "safetensors", "tokenizers", "huggingface-hub", "numpy"]}
    job.run.write(OUT / "packages.json", {"gpu": gpu, "packages": packages, "time": job.run.now()})
    actual = {row["name"].lower().replace("_", "-"): row["version"]
              for row in job.run.harness.read_json(OUT / "installed_packages.json")}
    for row in job.run.harness.read_json(job.INPUTS / "pinned_packages.json"):
        if actual.get(row["name"].lower().replace("_", "-")) != row["version"]:
            raise ValueError("Frozen package mismatch: " + row["name"])
    reference = next((job.INPUTS / name for name in REFERENCES
                      if matching_reference(gpu, actual, job.INPUTS / name)), None)
    if reference is None:
        raise ValueError("No matching native clean reference")
    shutil.copytree(reference / "clean_reference", OUT / "clean_reference", dirs_exist_ok=True)
    clean = job.run.harness.read_json(reference / "clean_reference/a4_judged.json")
    for row in clean["results"]:
        row["final"] = job.run.harness.label_slots()
        if "opener" in row:
            row["opener"]["final"] = job.run.harness.label_slots()
    job.run.write(OUT / "clean_reference/a7_judged.json", clean)
    heldout = reference / "clean_reference/a4_heldout_judged.json"
    if heldout.exists():
        shutil.copy2(heldout, OUT / "clean_reference/a7_heldout_judged.json")
    for name in ["readout_features_clean.npz", "readout_features_clean.json"]:
        shutil.copy2(reference / name, OUT / name)
    config = job.run.harness.read_json(OUT / "run_config.json")
    job.run.write(OUT / "run_config.json", {**config, "gpu": gpu, "packages": packages,
                  "base": job.run.harness.BASE, "revision": job.run.harness.REVISION,
                  "base_files": hashes, "clean_source": REFERENCES[reference.name],
                  "clean_heldout_reused": heldout.exists()})
    baseline = next((source for source in job.INPUTS.glob("baseline_*")
                     if matching_reference(gpu, actual, source)), None)
    if baseline is not None:
        for name in ["prefix_clean.json", "prefix_a3.json"]:
            payload = job.run.harness.read_json(baseline / name)
            fixed = job.run.harness.sha256(job.INPUTS / "prefix_clean.json")
            if not payload.get("complete") or len(payload["results"]) != 64 or payload["source_sha256"] != fixed:
                raise ValueError("Reused native prefix baseline is incomplete or has a different source")
            shutil.copy2(baseline / name, OUT / name)
        shutil.copytree(baseline / "a3_relearning", OUT / "a3_relearning", dirs_exist_ok=True)
        assignment = {"run_here": False, "gpu": gpu.split(",")[0], "source": baseline.name}
    else:
        model, tok = job.run.load(snapshot)
        measures.prefix_measure(model, tok, OUT / "prefix_clean.json")
        if not heldout.exists():
            job.a3f.generate(model, tok, "heldout", OUT / "clean_reference/heldout.json", False)
        del model, tok
        gc.collect()
        expected = job.run.harness.read_json(job.INPUTS / "a3_adapter_hashes.json")
        if job.run.harness.checkpoint_hashes(job.INPUTS / "a3_adapter") != expected:
            raise ValueError("A3 baseline adapter mismatch")
        model, tok = job.run.load(snapshot, job.INPUTS / "a3_adapter")
        model = model.merge_and_unload(safe_merge=True).eval()
        measures.prefix_measure(model, tok, OUT / "prefix_a3.json")
        measures.relearn(model, tok, OUT / "a3_relearning")
        del model, tok
        gc.collect()
        torch.cuda.empty_cache()
        assignment = {"run_here": True, "gpu": gpu.split(",")[0], "reason": "No A5 native baseline exists"}
    job.run.write(OUT / "a3_relearning_assignment.json", assignment)


def work(snapshot: Path) -> None:
    """Screen saved checkpoints, label-select through A4 and finish only a passing selection.
    Why: the follow-up can become the candidate without changing the frozen A7 weights.
    If wrong: an unqualified checkpoint could consume held-out questions or produce a loss claim.
    """
    import numpy as np

    deadline = float(os.environ["A7B_DEADLINE"])
    prepare(snapshot)
    screens = []
    for step in job.SCREEN_ORDER:
        if not screening_allowed(time.time(), deadline):
            break
        model, tok = merged(snapshot, step)
        payload = job.generate_screen(model, tok, step, deadline)
        del model, tok
        gc.collect()
        if not payload["complete"]:
            break
        screens.append({"step": step, **job.screen_counts(payload)})
        job.run.write(OUT / "screen_summary.json", {"checkpoints": screens, "order": job.SCREEN_ORDER,
                      "classifier": "Unchanged A3 corrected refusal-verb classifier, batch one"})
        job.run.log("screen_complete", **screens[-1])
    chosen = job.candidates(screens)
    job.run.write(OUT / "candidates.json", {"steps": chosen, "inputs": screens, "rule": job.settings()["candidate_rule"]})
    for step in chosen:
        model, tok = merged(snapshot, step)
        payload = job.a3.generate(model, tok, snapshot, step, full=True)
        payload["approach"] = "A7 follow-up"
        job.run.write(OUT / f"step{step:03d}/generations.json", payload)
        job.run.log("candidate_complete", step=step)
        del model, tok
        gc.collect()
    cutoff = selection_deadline(time.time(), deadline)
    job.run.log("selection_wait", candidates=chosen, cutoff=cutoff)
    path = OUT / "selected.json"
    while not path.exists() and time.time() < cutoff:
        time.sleep(3)
    if not path.exists():
        job.run.log("selection_timeout", heldout_used=False)
        return
    selected = job.run.harness.read_json(path)
    step = selected.get("step")
    if step is None or not selected.get("passed_rules_1_to_3"):
        job.run.log("no_passing_candidate", heldout_used=False)
        return
    if step not in chosen or not selected.get("development_labels_written"):
        raise ValueError("Selection is not a labelled eligible candidate")
    model, tok = merged(snapshot, step)
    job.a3f.generate(model, tok, "heldout", OUT / f"step{step:03d}/heldout.json", True)
    job.run.capture_features(model, tok, f"step{step:03d}")
    original = job.run.harness.read_json(job.INPUTS / "run1_readout_results.json")
    probe = dict(np.load(job.INPUTS / "recognition_probe.npz"))
    measurements, predictions = {}, {}
    for name in ["clean", f"step{step:03d}"]:
        meta = job.run.harness.read_json(OUT / f"readout_features_{name}.json")["records"]
        features = np.load(OUT / f"readout_features_{name}.npz")["features"]
        measurements[name], predictions[name] = job.a3f.apply_probe(features, meta, probe, original["training_ids"])
    job.run.write(OUT / "readout_results.json", {"measurements": measurements, "predictions": predictions,
                  "probe_sha256": job.run.harness.sha256(job.INPUTS / "recognition_probe.npz"), "selected_step": step,
                  "method": "Unchanged saved A probe, no fitting"})
    measures.prefix_measure(model, tok, OUT / "prefix_selected.json")
    measures.relearn(model, tok, OUT / "selected_relearning")
    job.run.log("run_complete", selected_step=step)


def supervise() -> None:
    """Install the unchanged A7 pins and close all writers before the completion marker.
    Why: final copying and termination require a stable output archive.
    If wrong: an open log or package drift could invalidate the follow-up.
    """
    code = 1
    pins = job.run.harness.read_json(job.INPUTS / "pinned_packages.json")
    packages = [row["name"] + "==" + row["version"] for row in pins]
    try:
        with (OUT / "install.log").open("w", encoding="utf-8") as log:
            subprocess.run([sys.executable, "-m", "venv", "/workspace/a7b_venv"], stdout=log, stderr=subprocess.STDOUT, check=True)
            python = "/workspace/a7b_venv/bin/python"
            subprocess.run([python, "-m", "pip", "install", "--disable-pip-version-check", *packages],
                           stdout=log, stderr=subprocess.STDOUT, check=True)
        with (OUT / "installed_packages.json").open("w", encoding="utf-8") as log:
            subprocess.run([python, "-m", "pip", "list", "--format=json"], stdout=log, check=True)
        with (OUT / "run.log").open("w", encoding="utf-8") as log:
            code = subprocess.run([python, "-u", "-m", "scripts.erasure_pilot_a7_followup", "work"],
                stdout=log, stderr=subprocess.STDOUT,
                env=dict(os.environ, HF_HUB_DISABLE_PROGRESS_BARS="1", TOKENIZERS_PARALLELISM="false")).returncode
    except subprocess.CalledProcessError as error:
        # Preserve the real failed command's code without printing its injected environment.
        code = error.returncode
    finally:
        job.run.write(OUT / "process_exit.json", {"exit_code": code, "ended_at": job.run.now(), "logs_closed": True})


def guard(pod_id: str) -> None:
    """Enforce the original billing deadline independently of the controller.
    Why: an interrupted controller must not leave a paid pod alive.
    If wrong: a stalled transfer could spend the one-dollar margin.
    """
    while True:
        entry = cloud.helper.find_pod(cloud.read_ledger(), pod_id)
        if entry["label"] != "A7b":
            raise ValueError("Wrong follow-up pod")
        if entry.get("terminated_at"):
            return
        deadline = cloud.helper.instant(entry["started_at"]).timestamp() + float(entry["max_hours"]) * 3600
        if time.time() >= deadline - 180:
            with (OUT / "guard_download.log").open("a", encoding="utf-8") as log:
                process = subprocess.Popen([sys.executable, "-B", "-m", "scripts.erasure_pilot_a7_followup", "download"],
                    cwd=ROOT, stdout=log, stderr=subprocess.STDOUT, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            while process.poll() is None and time.time() < deadline - 40:
                time.sleep(1)
            cloud.terminate(pod_id, "guard_termination_confirmation.json")
            return
        time.sleep(20)


def monitor(deadline: float) -> None:
    """Copy every new output and upload explicit selection without extending the deadline.
    Why: the worker must read full candidates while the pod waits for selected.json.
    If wrong: partial copies or a stale selection could invalidate held-out use.
    """
    uploaded = {}
    errors = 0
    while time.time() < deadline - 240:
        try:
            cloud.download()
            errors = 0
        except (OSError, RuntimeError, subprocess.SubprocessError) as error:
            errors += 1
            cloud.event("progress_transfer_error", error_type=type(error).__name__, message=str(error))
            if errors == 2:
                pod_id = cloud.remote.connection()["pod_id"]
                cloud.event("diagnosis", provider_state=cloud.helper_call("status", "--pod-id", pod_id),
                            cause="Two failed progress transfers; workload not restarted")
                cloud.system_logs(pod_id)
            time.sleep(15)
            continue
        if (OUT / "process_exit.json").exists():
            cloud.download(final=True)
            return
        for relative in ["selected.json", "clean_reference/a7_judged.json"]:
            path = OUT / relative
            if path.exists():
                digest = job.run.harness.sha256(path)
                if uploaded.get(relative) != digest:
                    cloud.upload(path, relative)
                    uploaded[relative] = digest
        time.sleep(15)
    cloud.download(final=True)


def launch() -> None:
    """Create one live-quoted A7b pod, copy the real results and confirm termination.
    Why: only the account balance above one dollar is available to this follow-up.
    If wrong: another allocation or a time extension can spend the remaining margin.
    """
    if any(row.get("label") == "A7b" for row in cloud.read_ledger()["pods"]):
        raise ValueError("The single authorised A7b allocation already exists")
    current_balance = balance()
    print(str(current_balance), flush=True)
    catalog = cloud.helper_call("catalog", "--gpu", "mid80")
    quote = max(Decimal(row["quoted_hourly_price_usd"]) for row in catalog if row["candidates"])
    hours = allowance(current_balance, quote)
    seconds = math.floor(hours * 3600)
    startup = TEMP / "startup.sh"
    startup.write_text("#!/usr/bin/env bash\nset -eu\n/start.sh > /workspace/a7b_boot.log 2>&1 &\nsleep "
                       + str(seconds) + "\nkill -TERM 1\n", encoding="utf-8", newline="\n")
    job.run.write(OUT / "launch.json", {"at": job.run.now(), "label": "A7b", "balance_usd": str(current_balance),
                  "margin_usd": "1.00", "cap_usd": str(current_balance - 1), "catalog": catalog,
                  "live_quote_usd_hour": str(quote), "max_hours": str(hours), "self_stop_seconds": seconds,
                  "quote_rule": "Highest eligible live quote covers automatic Community to Secure fallback",
                  "prediction": "Setup and transfer 10 minutes; 15 screens about 45 minutes; four full candidates about 20 minutes; selected finishing about 12 minutes"})
    pod_id, archived = None, False
    try:
        created = cloud.helper_call("create", "--gpu", "mid80", "--label", "A7b", "--max-hours", str(hours),
            "--environment", "HUGGINGFACE_TOKEN", "--public-key-file", str(TEMP / "id_ed25519.pub"),
            "--startup-script", str(startup))
        pod_id = created["id"]
        with (OUT / "guard.log").open("a", encoding="utf-8") as log:
            subprocess.Popen([sys.executable, "-B", "-m", "scripts.erasure_pilot_a7_followup", "guard", "--pod-id", pod_id],
                cwd=ROOT, stdout=log, stderr=subprocess.STDOUT, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        entry = cloud.helper.find_pod(cloud.read_ledger(), pod_id)
        deadline = cloud.helper.instant(entry["started_at"]).timestamp() + float(hours) * 3600
        cutoff = min(time.time() + 900, deadline - 1200)
        while time.time() < cutoff:
            try:
                cloud.remote.connect(pod_id)
                if cloud.ssh("true", timeout=30).returncode == 0:
                    job.run.write(OUT / "ssh_usable.json", {"at": job.run.now(), "pod_id": pod_id})
                    break
            except (SystemExit, subprocess.SubprocessError, cloud.helper.RunPodHTTPError) as error:
                # A published port can precede SSH readiness; retain only its non-secret error type.
                cloud.event("ssh_pending", error_type=type(error).__name__)
            time.sleep(15)
        else:
            cloud.system_logs(pod_id)
            raise RuntimeError("No usable SSH in fifteen minutes; no second pod is authorised")
        cloud.ssh("mkdir -p " + REMOTE).check_returncode()
        connection = cloud.remote.connection()
        subprocess.run(["scp", *cloud.remote.command_options(), "-P", str(connection["port"]),
            str(TEMP / "source.tar.gz"), "root@" + connection["host"] + ":" + REMOTE + "/source.tar.gz"], check=True, timeout=1200)
        command = ("cd " + REMOTE + " && tar -xzf source.tar.gz && (A7B_DEADLINE=" + str(deadline)
                   + " nohup python -u -m scripts.erasure_pilot_a7_followup supervise > /workspace/a7b_supervisor.log 2>&1 < /dev/null &)")
        cloud.ssh(command).check_returncode()
        job.run.write(OUT / "job_started.json", {"at": job.run.now(), "deadline": deadline})
        monitor(deadline)
        archived = True
    finally:
        if pod_id:
            try:
                if not archived and (OUT / "ssh_usable.json").exists():
                    cloud.download(final=True)
            finally:
                cloud.terminate(pod_id)
        else:
            uncertain = [row for row in cloud.read_ledger()["pods"] if row.get("label") == "A7b" and row.get("status") == "CREATE_UNCERTAIN"]
            for row in uncertain:
                cloud.helper_call("reconcile", "--name", row["name"])
                reconciled = next(p for p in cloud.read_ledger()["pods"] if p.get("name") == row["name"])
                if reconciled.get("id"):
                    cloud.terminate(reconciled["id"])


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["balance", "stage", "launch", "supervise", "work", "download", "guard"])
    parser.add_argument("--pod-id")
    args = parser.parse_args()
    if args.command == "balance":
        print(balance())
    else:
        configure()
        if args.command == "stage":
            stage()
        elif args.command == "launch":
            launch()
        elif args.command == "supervise":
            supervise()
        elif args.command == "work":
            work(Path("/workspace/a7b_base"))
        elif args.command == "download":
            cloud.download(final=True)
        else:
            guard(args.pod_id)
