"""Launch the real B-PROPER Modal application with dollar-derived hard timeouts."""

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import modal

from scripts.erasure_pilot_bp_train import timeout_seconds


ROOT = Path(__file__).resolve().parents[1]
LOCAL = ROOT / "derisk/erasure_pilot_v1/approach_b_proper"
SPEC = json.loads((ROOT / "config/erasure_pilot_v1/approach_b_proper/settings.json").read_text())
VOLUME_NAME = "erasure-pilot-b-proper-20261102"
app = modal.App("erasure-pilot-b-proper-20261102")
volume = modal.Volume.from_name(VOLUME_NAME, create_if_missing=True)


def hf_secret():
    """Read only the requested local credential and send it through a Modal Secret.
    Why: neither the rest of .env nor token values may enter artifacts or arguments.
    If wrong: credentials can leak through image layers, logs or CLI history.
    """
    if not modal.is_local():
        return [modal.Secret.from_dict({"HF_TOKEN": os.environ["HF_TOKEN"]})]
    value = None
    for line in (ROOT / ".env").read_text(encoding="utf-8-sig").splitlines():
        key, separator, candidate = line.partition("=")
        if separator and key.strip() == "HUGGINGFACE_TOKEN":
            value = candidate.strip().strip("\"'")
            break
    if not value:
        raise ValueError("HUGGINGFACE_TOKEN is absent from local .env")
    return [modal.Secret.from_dict({"HF_TOKEN": value})]


image = (modal.Image.debian_slim(python_version="3.12")
         .apt_install("libgomp1")
         .pip_install("torch==2.8.0+cu128", "torchvision==0.23.0+cu128",
                      "torchaudio==2.8.0+cu128", index_url="https://download.pytorch.org/whl/cu128")
         .pip_install("transformers==5.14.1", "peft==0.20.0", "accelerate==1.14.0",
                      "tokenizers==0.22.2", "safetensors==0.8.0", "datasets==5.1.0",
                      "sentence-transformers==6.2.0", "scikit-learn==1.9.1", "numpy==2.1.2",
                      "scipy==1.18.1", "huggingface-hub==1.33.0", "pandas==3.1.0",
                      "pyarrow==26.0.0", "sentencepiece==0.2.2", "pillow==11.0.0")
         .env({"PYTHONPATH": "/work", "HF_HOME": "/pilot/hf_cache",
               "TOKENIZERS_PARALLELISM": "false", "OMP_NUM_THREADS": "4",
               "PILOT_COMMIT": os.environ.get("PILOT_COMMIT") or subprocess.check_output(
                   ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()}))

# Explicit source uploads exclude .env, Modal credentials, unrelated code and full base weights.
for name in ("erasure_pilot_bp_data.py", "erasure_pilot_bp_train.py", "erasure_pilot_bp_run.py", "erasure_pilot_bp_modal.py",
             "erasure_pilot_eval.py", "build_erasure_tokenisations.py", "erasure_pilot_a_run.py",
             "erasure_pilot_a_data.py", "erasure_pilot_b_data.py", "erasure_pilot_b_train.py",
             "erasure_pilot_b_run.py", "erasure_pilot_b_review.py", "erasure_pilot_b_readout.py"):
    image = image.add_local_file(ROOT / "scripts" / name, f"/work/scripts/{name}")
image = image.add_local_dir(ROOT / "config/erasure_pilot_v1", "/work/config/erasure_pilot_v1")
image = image.add_local_file(ROOT / "config/biography_pilot_v1/execution_v1/cosine_v2_freeze.json",
                             "/work/config/biography_pilot_v1/execution_v1/cosine_v2_freeze.json")
for name in ("adapter_config.json", "adapter_model.safetensors"):
    image = image.add_local_file(ROOT / "derisk/erasure_pilot_v1/approach_a3/step150/adapter" / name,
                                 f"/work/inputs/adapter/{name}")
for source, destination in (
    ("approach_a3/step150/adapter_hashes.json", "adapter_hashes.json"),
    ("approach_b/alpha03/clean_reference/generations.judged.json", "prefix_clean.json"),
    ("approach_b/alpha03/relearning_answers.judged.json", "relearning_answers.judged.json"),
    ("approach_a/recognition_probe.npz", "probe/recognition_probe.npz"),
    ("approach_a/readout_features_clean.json", "probe/readout_features_clean.json"),
    ("approach_a/readout_results.json", "probe/readout_results.json"),
):
    image = image.add_local_file(ROOT / "derisk/erasure_pilot_v1" / source, f"/work/inputs/{destination}")

COMMON = dict(image=image, cpu=(4.0, 4.0), memory=(32768, 32768), volumes={"/pilot": volume},
              secrets=hf_secret(), retries=0, scaledown_window=2, max_containers=1,
              single_use_containers=True, include_source=False)
H_RATE = SPEC["resources"]["H200"]["rate"]
B_RATE = SPEC["resources"]["B200"]["rate"]


@app.function(gpu="H200", timeout=timeout_seconds(4, H_RATE), **COMMON)
def reference_h200():
    from scripts.erasure_pilot_bp_run import reference
    return reference(volume, "H200", H_RATE, timeout_seconds(4, H_RATE))


@app.function(gpu="B200", timeout=timeout_seconds(4, B_RATE), **COMMON)
def reference_b200():
    from scripts.erasure_pilot_bp_run import reference
    return reference(volume, "B200", B_RATE, timeout_seconds(4, B_RATE))


@app.function(gpu="H200", timeout=timeout_seconds(11, H_RATE), **COMMON)
def student06_h200():
    from scripts.erasure_pilot_bp_run import student
    return student(0.6, volume, "H200", H_RATE, timeout_seconds(11, H_RATE))


@app.function(gpu="H200", timeout=timeout_seconds(11, H_RATE), **COMMON)
def student08_h200():
    from scripts.erasure_pilot_bp_run import student
    return student(0.8, volume, "H200", H_RATE, timeout_seconds(11, H_RATE))


@app.function(gpu="B200", timeout=timeout_seconds(11, B_RATE), **COMMON)
def student06_b200():
    from scripts.erasure_pilot_bp_run import student
    return student(0.6, volume, "B200", B_RATE, timeout_seconds(11, B_RATE))


@app.function(gpu="B200", timeout=timeout_seconds(11, B_RATE), **COMMON)
def student08_b200():
    from scripts.erasure_pilot_bp_run import student
    return student(0.8, volume, "B200", B_RATE, timeout_seconds(11, B_RATE))


@app.function(gpu=SPEC["resources"]["prepare"]["gpu"], timeout=SPEC["resources"]["prepare"]["timeout"], **COMMON)
def prepare():
    from scripts.erasure_pilot_bp_run import prepare as run
    return run(volume, reference_h200)


PREP3_COMMON = {**COMMON, "memory": (65536, 65536)}


@app.function(gpu="T4", timeout=SPEC["resources"]["prepare_attempt3"]["timeout"], **PREP3_COMMON)
def prepare_attempt3():
    from scripts.erasure_pilot_bp_run import prepare_attempt3 as run
    return run(volume)


def remote_json(name: str):
    try:
        return json.loads(b"".join(volume.read_file("outputs/" + name)))
    except (FileNotFoundError, modal.exception.NotFoundError):
        return None


def billing_and_copy(app_id: str) -> None:
    """Copy finished artifacts and enforce the total cap using provider billing.
    Why: detached calls must survive connection loss while exposing partial evidence.
    If wrong: silent failures or delayed billing can hide a running paid container.
    """
    LOCAL.mkdir(parents=True, exist_ok=True)
    report = subprocess.run([sys.executable, "-m", "modal", "billing", "report", "--for", "today",
                             "--show-resources", "--json"], capture_output=True, text=True)
    if report.returncode == 0:
        (LOCAL / "billing_latest.json").write_text(report.stdout, encoding="utf-8")
    summary = subprocess.run([sys.executable, "-m", "modal", "billing", "summary", "--json"],
                             capture_output=True, text=True)
    if summary.returncode == 0:
        (LOCAL / "billing_summary_latest.json").write_text(summary.stdout, encoding="utf-8")
        data = json.loads(summary.stdout)
        values = [float(value) for key, value in data.items() if "meter" in key.lower() and isinstance(value, (int, float, str))]
        if values and max(values) >= 27.50:
            subprocess.run([sys.executable, "-m", "modal", "app", "stop", app_id, "--yes"], check=True)
            raise RuntimeError("Stopped app at the metered $27.50 cap")
    try:
        entries = list(volume.iterdir("/outputs", recursive=True))
    except (FileNotFoundError, modal.exception.NotFoundError):
        return
    for entry in entries:
        name = entry.path.lstrip("/")
        if entry.type != modal.volume.FileEntryType.FILE or "/weights/" in name:
            continue
        if name.endswith(("packed.npy", "lengths.npy")) and not remote_json(str(Path(name).relative_to("outputs").parent).replace("\\", "/") + "/data_ready.json"):
            continue
        destination = LOCAL / Path(name).relative_to("outputs")
        if destination.exists() and destination.stat().st_size == entry.size:
            continue
        destination.parent.mkdir(parents=True, exist_ok=True)
        with destination.open("wb") as handle:
            for chunk in volume.read_file(entry.path):
                handle.write(chunk)


def download_weights(name: str) -> bool:
    """Copy completed bf16 assets and reread their SHA-256 values from local disk.
    Why: copying may overlap relearning, but only immutable saved assets are eligible.
    If wrong: a partial download can be mistaken for the evaluated final checkpoint.
    """
    import hashlib
    from datetime import datetime, timezone

    if name not in {"alpha06", "alpha08"}:
        raise ValueError("Choose one frozen student")
    expected = remote_json(name + "/weights_hashes.json")
    if expected is None:
        return False
    verification = LOCAL / name / "download_verification.json"
    actual = {}
    for filename, digest in expected.items():
        if Path(filename).name != filename:
            raise ValueError("Expected a plain checkpoint filename")
        destination = LOCAL / name / "weights" / filename
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists():
            with destination.open("rb") as handle:
                existing = hashlib.file_digest(handle, "sha256").hexdigest()
            if existing != digest:
                stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%f")
                # Keep an interrupted transfer recoverable under the same assigned directory.
                preserved = destination.with_name(destination.stem + ".incomplete_" + stamp + destination.suffix)
                destination.rename(preserved)
        if not destination.exists():
            with destination.open("xb") as handle:
                for chunk in volume.read_file(f"outputs/{name}/weights/{filename}"):
                    handle.write(chunk)
        with destination.open("rb") as handle:
            actual[filename] = hashlib.file_digest(handle, "sha256").hexdigest()
        if actual[filename] != digest:
            raise ValueError("Downloaded checkpoint hash mismatch: " + name + "/" + filename)
        print("Verified local asset " + name + "/" + filename, flush=True)
    if not verification.exists():
        with verification.open("x", encoding="utf-8") as handle:
            json.dump({"verified_at": datetime.now(timezone.utc).isoformat(), "hashes": actual}, handle, indent=2)
    return True


@app.local_entrypoint()
def main():
    """Submit the real prepare job and supervise its detached GPU children.
    Why: one preparation, one reference and two students have independent hard caps.
    If wrong: a local disconnect can strand work or start mixed GPU comparisons.
    """
    prep = prepare.spawn()
    (LOCAL / "launch.json").parent.mkdir(parents=True, exist_ok=True)
    (LOCAL / "launch.json").write_text(json.dumps({"app_id": app.app_id, "prepare_call": prep.object_id,
                                                   "volume": VOLUME_NAME, "launched_unix": time.time(),
                                                   "function_ids": {name: function.object_id for name, function in
                                                                    app.registered_functions.items()}}, indent=2))
    supervise_existing(app.app_id)


@app.local_entrypoint()
def resume():
    """Launch the authorised third preparation without restarting the healthy reference.
    Why: paid children and original write-once output directories already exist.
    If wrong: a duplicate reference can spend its cap twice.
    """
    prep = prepare_attempt3.spawn()
    write_path = LOCAL / "launch_attempt3.json"
    with write_path.open("x", encoding="utf-8") as handle:
        json.dump({"app_id": app.app_id, "prepare_call": prep.object_id,
                   "launched_unix": time.time(), "volume": VOLUME_NAME}, handle, indent=2)
    while not remote_json("prepare_attempt3/result.json"):
        billing_and_copy(app.app_id)
        time.sleep(180)
    result = prep.get()
    billing_and_copy(app.app_id)
    if result["status"] != "COMPLETE":
        return
    calls = [student06_h200.spawn(), student08_h200.spawn()]
    with (LOCAL / "student_calls.json").open("x", encoding="utf-8") as handle:
        json.dump({"gpu": "H200", "app_id": app.app_id,
                   "calls": [call.object_id for call in calls]}, handle, indent=2)
    while not all(remote_json(name + "/result.json") for name in ("alpha06", "alpha08")):
        billing_and_copy(app.app_id)
        time.sleep(180)
    billing_and_copy(app.app_id)
    for call in calls:
        try:
            print(call.get(), flush=True)
        except Exception as error:
            # Failed calls still leave immutable partial output for diagnosis.
            print(type(error).__name__ + ": " + str(error), flush=True)


def supervise_existing(app_id: str) -> None:
    """Reconnect to the existing detached calls without creating another prepare run.
    Why: local monitoring failures must not duplicate paid functions or overwrite evidence.
    If wrong: a reconnect can become an unauthorized second experiment.
    """
    import asyncio
    from modal.client import _Client
    from modal_proto import api_pb2

    async def function_ids():
        client = await _Client.from_env()
        response = await client.stub.AppGetLayout(api_pb2.AppGetLayoutRequest(app_id=app_id))
        return dict(response.app_layout.function_ids)

    launch_record = json.loads((LOCAL / "launch.json").read_text())
    identifiers = launch_record.get("function_ids") or asyncio.run(function_ids())
    functions_by_name = {name: modal.Function.from_id(identifier) for name, identifier in identifiers.items()}
    existing_calls = LOCAL / "student_calls.json"
    saved = json.loads(existing_calls.read_text()) if existing_calls.exists() else None
    reference_call = None
    students = [modal.FunctionCall.from_id(value) for value in saved["calls"]] if saved else []
    selected_gpu = saved["gpu"] if saved else "H200"
    while True:
        billing_and_copy(app_id)
        spawned = remote_json("prepare/reference_call.json")
        ref_config = remote_json("reference/config.json")
        ready = remote_json("prepare/data_ready.json")
        prep_result = remote_json("prepare/result.json")
        if prep_result and prep_result["status"] == "FAILED":
            print("Prepare failed; preserving reference outputs without starting students", flush=True)
            if spawned:
                reference_call = modal.FunctionCall.from_id(spawned["call_id"])
                reference_call.get()
            return
        if spawned and reference_call is None:
            reference_call = modal.FunctionCall.from_id(spawned["call_id"])
        if spawned and not ref_config and selected_gpu == "H200":
            from datetime import datetime, timezone
            age = (datetime.now(timezone.utc) - datetime.fromisoformat(spawned["spawned_at"])).total_seconds()
            if age >= 1200:
                reference_call.cancel(terminate_containers=True)
                selected_gpu = "B200"
                reference_call = functions_by_name["reference_b200"].spawn()
                (LOCAL / "gpu_fallback.json").write_text(json.dumps({"gpu": selected_gpu,
                     "h200_queue_seconds": age, "reference_call": reference_call.object_id}, indent=2))
        if ready and ref_config and not students:
            suffix = "h200" if selected_gpu == "H200" else "b200"
            functions = [functions_by_name["student06_" + suffix], functions_by_name["student08_" + suffix]]
            students = [function.spawn() for function in functions]
            (LOCAL / "student_calls.json").write_text(json.dumps({"gpu": selected_gpu,
                      "calls": [call.object_id for call in students]}, indent=2))
        if students and all(remote_json(name + "/result.json") for name in ("alpha06", "alpha08")):
            break
        # One shared three-minute interval for logs, billing, listings and transfers.
        time.sleep(180)
    billing_and_copy(app_id)
    for call in [reference_call, *students]:
        try:
            print(call.get(), flush=True)
        except Exception as error:
            # Preserve all functions' artifacts before returning a failed workload to the manager.
            print(type(error).__name__ + ": " + str(error), flush=True)
    billing_and_copy(app_id)
    # Download immutable bf16 weights after compute has ended, then verify each byte hash.
    import hashlib
    for alpha in ("alpha06", "alpha08"):
        hashes = remote_json(alpha + "/weights_hashes.json")
        if hashes is None:
            continue
        actual = {}
        for name, expected in hashes.items():
            destination = LOCAL / alpha / "weights" / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            digest = hashlib.sha256()
            with destination.open("wb") as handle:
                for chunk in volume.read_file(f"outputs/{alpha}/weights/{name}"):
                    handle.write(chunk)
                    digest.update(chunk)
            actual[name] = digest.hexdigest()
            if actual[name] != expected:
                raise ValueError(f"Downloaded student hash mismatch: {alpha}/{name}")
        (LOCAL / alpha / "download_verification.json").write_text(json.dumps(actual, indent=2), encoding="utf-8")
