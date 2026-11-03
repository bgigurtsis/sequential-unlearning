"""Run the manager's single bounded A4 and A5 adapter diagnostic."""

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
from decimal import Decimal, ROUND_DOWN
from pathlib import Path

from scripts import erasure_pilot_a5_cloud as cloud
from scripts import erasure_pilot_a5_measures as measures
from scripts import erasure_pilot_a5_run as job

ROOT = job.ROOT
RELATIVE = "derisk/erasure_pilot_v1/approach_a5/diagnostic"
OUT = ROOT / RELATIVE
TEMP = ROOT / ".tmp/approach_a5/diagnostic"
REMOTE = "/workspace/approach_a5_diagnostic"
ADAPTERS = {"a4_step060": "approach_a4/attempt2/step060",
            "a4_step090": "approach_a4/attempt2/step090",
            "a5_ns_step080": "approach_a5/arm_ns/step080",
            "a3_step150": "approach_a3/step150"}
REFERENCES = {"server": "approach_a4", "maxq": "approach_a", "workstation": "approach_a3f"}


def configure() -> None:
    job.OUT, job.INPUTS, job.CONFIG = OUT, OUT / "inputs", OUT / "inputs/config"
    job.OUTPUT_RELATIVE = RELATIVE
    job.configure()
    cloud.OUT, cloud.INPUTS, cloud.TEMP = OUT, job.INPUTS, TEMP
    cloud.REMOTE, cloud.PREFIX, cloud.LABEL = REMOTE, RELATIVE, "A5-diag"
    cloud.configure()


def stage() -> None:
    """Stage exact adapters, references and dependencies without sealed questions.
    Why: this diagnostic needs development replies only and cannot select a candidate.
    If wrong: changed weights or unnecessary sealed inputs can invalidate the measurement.
    """
    configure()
    inputs = job.INPUTS
    inputs.mkdir(parents=True, exist_ok=True)
    pilot = ROOT / "derisk/erasure_pilot_v1"
    verified = {}
    for name, relative in ADAPTERS.items():
        source = pilot / relative
        hashes = job.run.harness.read_json(source / "adapter_hashes.json")
        if job.run.harness.checkpoint_hashes(source / "adapter") != hashes:
            raise ValueError("Adapter hash mismatch: " + relative)
        shutil.copytree(source / "adapter", inputs / name / "adapter", dirs_exist_ok=True)
        shutil.copy2(source / "adapter_hashes.json", inputs / name / "adapter_hashes.json")
        verified[name] = {"source": relative, "hashes": hashes}
    sources = {"approach_a3/installed_packages.json": "pinned_packages.json",
               "approach_b/alpha03/clean_reference/generations.judged.json": "prefix_clean.json",
               "approach_b_proper/reference/prefix_clean.json": "bp_prefix_clean.json",
               "approach_b/alpha03/relearning_answers.judged.json": "relearning_answers.judged.json"}
    for source, destination in sources.items():
        shutil.copy2(pilot / source, inputs / destination)
    for name, relative in REFERENCES.items():
        source, destination = pilot / relative, inputs / name
        destination.mkdir(exist_ok=True)
        for filename in ["packages.json", "installed_packages.json"]:
            shutil.copy2(source / filename, destination / filename)
        choices = [source / "clean_reference" / filename for filename in
                   ["a4_judged.json", "judged.json", "judge_review_qualified.json"]]
        clean = next(path for path in choices if path.exists())
        shutil.copy2(clean, destination / "clean_judged.json")
    baseline = inputs / "server_baseline"
    baseline.mkdir(exist_ok=True)
    for source, destination in [("arm_n/packages.json", "packages.json"),
                                ("arm_n/installed_packages.json", "installed_packages.json"),
                                ("arm_n/prefix_clean.json", "prefix_clean.json"),
                                ("arm_n/prefix_a3.json", "prefix_a3.json"),
                                ("arm_n/a3_relearning/relearn05.judged.json", "relearn05.judged.json")]:
        shutil.copy2(pilot / "approach_a5" / source, baseline / destination)
    shutil.copytree(pilot / "approach_a5/arm_ns/inputs/config", job.CONFIG, dirs_exist_ok=True)
    shutil.copy2(pilot / "approach_a5/arm_ns/tokenisations.json", OUT / "tokenisations.json")
    names = ["erasure_pilot_eval.py", "build_erasure_tokenisations.py", "erasure_pilot_a_run.py",
             "erasure_pilot_a_data.py", "erasure_pilot_a3_run.py", "erasure_pilot_a3_screen.py",
             "erasure_pilot_a3f_run.py", "erasure_pilot_b_run.py", "erasure_pilot_b_data.py",
             "erasure_pilot_b_review.py", "erasure_pilot_b_train.py", "erasure_pilot_bp_train.py",
             "erasure_pilot_a3_review.py", "erasure_pilot_a_review.py", "erasure_pilot_a3f_review.py",
             "erasure_pilot_a5_run.py", "erasure_pilot_a5_cloud.py", "erasure_pilot_a5_measures.py",
             "erasure_pilot_a5_math.py", "erasure_pilot_a5_diag.py", "erasure_pilot_a_remote.py", "runpod_pilot.py"]
    paths = [ROOT / "scripts" / name for name in names]
    paths.extend(path for path in inputs.rglob("*") if path.is_file())
    paths.append(OUT / "tokenisations.json")
    paths.append(ROOT / "config/biography_pilot_v1/execution_v1/cosine_v2_freeze.json")
    for name in ["development.json", "nearby.json", "distant.json", "alternate_tokenisations.json", "manifest.json", "rubric.md"]:
        paths.append(ROOT / "config/erasure_pilot_v1" / name)
    job.run.write(OUT / "run_config.json", {"commit": subprocess.check_output(
        ["git", "rev-parse", "HEAD"], text=True, cwd=ROOT).strip(),
        "specification": "2026-11-03: one diagnostic pod for A4's saved adapters and A5 NS step 80",
        "diagnostic_only": True, "candidate_selection": False, "sealed_transferred": False,
        "adapters_verified_before_launch": verified,
        "input_sha256": {path.relative_to(ROOT).as_posix(): job.run.harness.sha256(path) for path in paths}})
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
        subprocess.run(["ssh-keygen", "-t", "ed25519", "-N", "", "-C", "A5-diag", "-f", str(key)],
                       capture_output=True, check=True)


def merged(snapshot: Path, name: str):
    import torch

    source = job.INPUTS / name
    expected = job.run.harness.read_json(source / "adapter_hashes.json")
    if job.run.harness.checkpoint_hashes(source / "adapter") != expected:
        raise ValueError("Pod adapter hash mismatch: " + name)
    gc.collect()
    torch.cuda.empty_cache()
    model, tokenizer = job.run.load(snapshot, source / "adapter")
    model = model.merge_and_unload(safe_merge=True)
    model.eval()
    model.config.use_cache = True
    return model, tokenizer


def screen(snapshot: Path, step: int) -> dict:
    """Run the unchanged batch-one harness and A3 corrected refusal classifier.
    Why: the automatic counts are the diagnostic result and receive no judge labels.
    If wrong: a changed decoder or semantic screen would break the A3 comparison.
    """
    import torch

    model, tokenizer = merged(snapshot, f"a4_step{step:03d}")
    items, hashes = job.run.harness.load_questions("development", OUT / "tokenisations.json")
    rows = [item for item in items if item["group"] in {"target", "distant"}]
    path = OUT / f"a4_step{step:03d}/screen_generations.json"
    payload = {"schema": "erasure_pilot_replies_v1", "approach": "A4 diagnostic", "split": "development",
               "dose": f"step{step:03d}", "hashes": hashes, "generation": job.run.harness.GENERATION,
               "batch_size": 1, "seed": 0, "results": [], "complete": False}
    torch.manual_seed(0)
    for item in rows:
        payload["results"].append(job.run.harness.generate_item(model, tokenizer, item))
        job.run.write(path, payload)
        job.run.log("a4_screen_item", step=step, completed=len(payload["results"]), item=item["id"])
    payload["complete"] = len(payload["results"]) == 64
    job.run.write(path, payload)
    counted = {"step": step, **job.screen_counts(payload)}
    job.run.write(path.parent / "screen_counts.json", counted)
    del model, tokenizer
    return counted


def work(snapshot: Path) -> None:
    """Run both screens, then the NS prefix and exact five-step recovery.
    Why: these saved checkpoints answer the manager's frozen diagnostic questions.
    If wrong: re-training or selecting a candidate would expand this diagnostic.
    """
    from huggingface_hub import snapshot_download

    pinned = job.run.harness.read_json(job.run.harness.FREEZE)["base_files"]
    snapshot_download(job.run.harness.BASE, revision=job.run.harness.REVISION, local_dir=str(snapshot),
                      allow_patterns=list(pinned), token=job.run.huggingface_token())
    base_hashes = job.run.harness.verify_snapshot(snapshot)
    gpu = subprocess.check_output(["nvidia-smi", "--query-gpu=name,driver_version,memory.total",
                                   "--format=csv,noheader"], text=True).strip()
    packages = {name: importlib.metadata.version(name) for name in
                ["torch", "transformers", "peft", "accelerate", "safetensors", "tokenizers", "huggingface-hub", "numpy"]}
    job.run.write(OUT / "packages.json", {"gpu": gpu, "packages": packages, "time": job.run.now()})
    actual = {x["name"].lower().replace("_", "-"): x["version"] for x in job.run.harness.read_json(OUT / "installed_packages.json")}
    reference = None
    for name in REFERENCES:
        source = job.INPUTS / name
        previous = job.run.harness.read_json(source / "packages.json")
        pins = job.run.harness.read_json(source / "installed_packages.json")
        matching = all(actual.get(x["name"].lower().replace("_", "-")) == x["version"] for x in pins)
        if previous["gpu"].split(",")[0] == gpu.split(",")[0] and matching:
            reference = source
            break
    if reference is None:
        raise ValueError("No exact GPU-name and package clean reference")
    clean = job.run.harness.read_json(reference / "clean_judged.json")
    for row in clean["results"]:
        row["final"] = job.run.harness.label_slots()
        if "opener" in row:
            row["opener"]["final"] = job.run.harness.label_slots()
    job.run.write(OUT / "clean_reference/judged.json", clean)
    config = job.run.harness.read_json(OUT / "run_config.json")
    job.run.write(OUT / "run_config.json", {**config, "gpu": gpu, "clean_reference": reference.name,
                  "base": job.run.harness.BASE, "revision": job.run.harness.REVISION, "base_hashes": base_hashes,
                  "generation": job.run.harness.GENERATION, "packages_exact": True})
    screens = []
    for step in [60, 90]:
        screens.append(screen(snapshot, step))
        job.run.write(OUT / "screen_summary.json", {"checkpoints": screens, "judge_labels": "not requested"})
    model, tokenizer = merged(snapshot, "a5_ns_step080")
    measures.prefix_measure(model, tokenizer, OUT / "prefix_ns080.json")
    measures.relearn(model, tokenizer, OUT / "ns080_relearning")
    del model, tokenizer
    gc.collect()
    if reference.name == "server":
        source = job.INPUTS / "server_baseline"
        previous = job.run.harness.read_json(source / "packages.json")
        baseline_pins = job.run.harness.read_json(source / "installed_packages.json")
        if previous["gpu"].split(",")[0] != gpu.split(",")[0] or not all(
                actual.get(x["name"].lower().replace("_", "-")) == x["version"] for x in baseline_pins):
            raise ValueError("The Server Edition A3 baseline fails the exact hardware and package rule")
        for name in ["prefix_clean.json", "prefix_a3.json", "relearn05.judged.json"]:
            destination = OUT / ("a3_relearning" if name.startswith("relearn") else "") / name
            destination.parent.mkdir(exist_ok=True)
            shutil.copy2(source / name, destination)
        job.run.write(OUT / "a3_baseline.json", {"reused": True, "gpu": gpu.split(",")[0],
                      "source": "approach_a5/arm_n", "same_gpu_and_packages": True})
    else:
        model, tokenizer = job.run.load(snapshot)
        measures.prefix_measure(model, tokenizer, OUT / "prefix_clean.json")
        del model, tokenizer
        model, tokenizer = merged(snapshot, "a3_step150")
        measures.prefix_measure(model, tokenizer, OUT / "prefix_a3.json")
        measures.relearn(model, tokenizer, OUT / "a3_relearning")
        job.run.write(OUT / "a3_baseline.json", {"reused": False, "gpu": gpu.split(",")[0],
                      "reason": "A5's earlier native baseline used a different GPU model"})
    job.run.log("diagnostic_complete", candidate_selection=False)


def supervise() -> None:
    """Install the unchanged A5 pins and close writers before the exit marker.
    Why: termination follows a stable final download rather than an open log.
    If wrong: pin drift or an incomplete archive can invalidate the diagnostic.
    """
    code = 1
    packages = [x["name"] + "==" + x["version"] for x in job.run.harness.read_json(job.INPUTS / "pinned_packages.json")]
    try:
        with (OUT / "install.log").open("w", encoding="utf-8") as log:
            subprocess.run([sys.executable, "-m", "venv", "/workspace/a5_diag_venv"], stdout=log, stderr=subprocess.STDOUT, check=True)
            python = "/workspace/a5_diag_venv/bin/python"
            subprocess.run([python, "-m", "pip", "install", "--disable-pip-version-check", *packages], stdout=log, stderr=subprocess.STDOUT, check=True)
        with (OUT / "installed_packages.json").open("w", encoding="utf-8") as log:
            subprocess.run([python, "-m", "pip", "list", "--format=json"], stdout=log, check=True)
        with (OUT / "run.log").open("w", encoding="utf-8") as log:
            code = subprocess.run([python, "-u", "-m", "scripts.erasure_pilot_a5_diag", "work"],
                                  env=dict(os.environ, TOKENIZERS_PARALLELISM="false", HF_HUB_DISABLE_PROGRESS_BARS="1"),
                                  stdout=log, stderr=subprocess.STDOUT).returncode
    except subprocess.CalledProcessError as error:
        # Preserve the failed real command's code without exposing its injected environment.
        code = error.returncode
    finally:
        job.run.write(OUT / "process_exit.json", {"exit_code": code, "ended_at": job.run.now(), "logs_closed": True})


def guard(pod_id: str) -> None:
    """Bound final copying and termination using the original ledger deadline.
    Why: an independent guard must survive a controller failure without extending billing.
    If wrong: the pod can outlive the manager's one-hour and 2.60-dollar cap.
    """
    while True:
        entry = cloud.helper.find_pod(cloud.read_ledger(), pod_id)
        if entry["label"] != "A5-diag":
            raise ValueError("Wrong diagnostic pod")
        if entry.get("terminated_at"):
            return
        deadline = cloud.helper.instant(entry["started_at"]).timestamp() + float(entry["max_hours"]) * 3600
        if time.time() >= deadline - 150:
            with (OUT / "guard_download.log").open("a", encoding="utf-8") as log:
                process = subprocess.Popen([sys.executable, "-B", "-m", "scripts.erasure_pilot_a5_diag", "download"],
                                           cwd=ROOT, stdout=log, stderr=subprocess.STDOUT,
                                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            while process.poll() is None and time.time() < deadline - 40:
                time.sleep(1)
            cloud.terminate(pod_id, "guard_termination_confirmation.json")
            return
        time.sleep(20)


def launch() -> None:
    """Create one live-quoted allocation, copy progress, archive and terminate.
    Why: the manager authorized exactly one diagnostic pod with a fixed spending cap.
    If wrong: a repeated create or a hidden price floor consumes the remaining credit.
    """
    own = [x for x in cloud.read_ledger()["pods"] if x.get("label") == "A5-diag"]
    if own:
        raise ValueError("A5-diag already has an allocation; no second create is authorized")
    catalog = cloud.helper_call("catalog", "--gpu", "mid80")
    quote = max(Decimal(x["quoted_hourly_price_usd"]) for x in catalog if x["candidates"])
    hours = min(Decimal("1.0"), Decimal("2.60") / quote).quantize(Decimal("0.0000000001"), rounding=ROUND_DOWN)
    startup = TEMP / "startup.sh"
    startup.write_text("#!/usr/bin/env bash\nset -eu\n/start.sh > /workspace/a5_diag_boot.log 2>&1 &\nsleep "
                       + str(math.floor(hours * 3600)) + "\nkill -TERM 1\n", encoding="utf-8", newline="\n")
    job.run.write(OUT / "launch.json", {"at": cloud.helper.utc_now(), "catalog": catalog, "quote_usd_hour": str(quote),
                  "max_hours": str(hours), "cap_usd": "2.60", "reserved_usd": str(quote * hours),
                  "predicted_spend_usd": "1.50", "prediction": "About 36 minutes at the Server Edition rate"})
    pod_id = None
    try:
        response = cloud.helper_call("create", "--gpu", "mid80", "--label", "A5-diag", "--max-hours", str(hours),
                                     "--environment", "HUGGINGFACE_TOKEN", "--public-key-file", str(TEMP / "id_ed25519.pub"),
                                     "--startup-script", str(startup))
        pod_id = response["id"]
        with (OUT / "guard.log").open("a", encoding="utf-8") as log:
            subprocess.Popen([sys.executable, "-B", "-m", "scripts.erasure_pilot_a5_diag", "guard", "--pod-id", pod_id],
                             cwd=ROOT, stdout=log, stderr=subprocess.STDOUT,
                             creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        entry = cloud.helper.find_pod(cloud.read_ledger(), pod_id)
        deadline = cloud.helper.instant(entry["started_at"]).timestamp() + float(hours) * 3600
        cutoff = min(time.time() + 900, deadline - 180)
        while time.time() < cutoff:
            try:
                cloud.remote.connect(pod_id)
                if cloud.ssh("true", timeout=30).returncode == 0:
                    job.run.write(OUT / "ssh_usable.json", {"at": job.run.now(), "pod_id": pod_id})
                    break
            except (SystemExit, subprocess.SubprocessError, cloud.helper.RunPodHTTPError) as error:
                # A public port can exist before sshd is ready. No GPU workload has run yet.
                cloud.event("ssh_pending", error_type=type(error).__name__)
            time.sleep(15)
        else:
            cloud.system_logs(pod_id)
            raise RuntimeError("No usable SSH before the diagnostic connection cutoff")
        cloud.ssh("mkdir -p " + REMOTE).check_returncode()
        value = cloud.remote.connection()
        subprocess.run(["scp", *cloud.remote.command_options(), "-P", str(value["port"]), str(TEMP / "source.tar.gz"),
                        "root@" + value["host"] + ":" + REMOTE + "/source.tar.gz"], check=True, timeout=600)
        cloud.ssh("cd " + REMOTE + " && tar -xzf source.tar.gz && (nohup python -u -m scripts.erasure_pilot_a5_diag supervise"
                  " > /workspace/a5_diag_supervisor.log 2>&1 < /dev/null &)").check_returncode()
        job.run.write(OUT / "job_started.json", {"at": job.run.now(), "deadline": deadline})
        while time.time() < deadline - 180:
            cloud.download()
            if (OUT / "process_exit.json").exists():
                break
            time.sleep(15)
        cloud.download(final=True)
    finally:
        if pod_id:
            cloud.terminate(pod_id)
        else:
            for row in cloud.read_ledger()["pods"]:
                if row.get("label") == "A5-diag" and row.get("status") == "CREATE_UNCERTAIN":
                    cloud.helper_call("reconcile", "--name", row["name"])
                    entry = next(x for x in cloud.read_ledger()["pods"] if x["name"] == row["name"])
                    if entry.get("id"):
                        cloud.terminate(entry["id"])


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["stage", "launch", "guard", "download", "supervise", "work"])
    parser.add_argument("--pod-id")
    args = parser.parse_args()
    configure()
    if args.command == "stage":
        stage()
    elif args.command == "launch":
        launch()
    elif args.command == "guard":
        guard(args.pod_id)
    elif args.command == "download":
        cloud.download(final=True)
    elif args.command == "supervise":
        supervise()
    else:
        work(Path("/workspace/a5_diag_base"))
