"""Submit only A6's two authorised H200 calls and copy immutable artifacts."""

import ast
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import modal

ROOT = Path(__file__).resolve().parents[1]
LOCAL = ROOT / "derisk/erasure_pilot_v1/approach_a6"
TEMP = ROOT / ".tmp/approach_a6"
RUN_ID = "a6-20261103"
VOLUME_NAME = "erasure-pilot-b-proper-20261102"
app = modal.App("erasure-pilot-a6-20261103")
volume = modal.Volume.from_name(VOLUME_NAME, create_if_missing=False)


def hf_secret():
    """Pass only the HF credential through Modal Secret, without printing it.
    Why: source uploads and command arguments must contain no token values.
    If wrong: credentials could enter image layers, logs or local artifacts.
    """
    if not modal.is_local():
        return [modal.Secret.from_dict({"HF_TOKEN": os.environ["HF_TOKEN"]})]
    for line in (ROOT / ".env").read_text(encoding="utf-8-sig").splitlines():
        key, separator, value = line.partition("=")
        if separator and key.strip() == "HUGGINGFACE_TOKEN":
            return [modal.Secret.from_dict({"HF_TOKEN": value.strip().strip("\"'")})]
    raise ValueError("Hugging Face credential is absent")


# Copy the B-PROPER image recipe verbatim through the final pip_install call.
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
               "A6_RUN_ID": RUN_ID,
               "PILOT_COMMIT": os.environ.get("PILOT_COMMIT") or subprocess.check_output(
                   ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()}))

SOURCES = ["erasure_pilot_a6_modal.py", "erasure_pilot_a6_run.py", "erasure_pilot_a6_math.py", "erasure_pilot_a6_measures.py",
           "erasure_pilot_a6_rescreen.py",
           "erasure_pilot_eval.py", "build_erasure_tokenisations.py", "erasure_pilot_a_run.py",
           "erasure_pilot_a_data.py", "erasure_pilot_a3_run.py", "erasure_pilot_a3_screen.py",
           "erasure_pilot_bp_run.py", "erasure_pilot_bp_data.py", "erasure_pilot_bp_train.py",
           "erasure_pilot_b_run.py", "erasure_pilot_b_data.py", "erasure_pilot_b_train.py",
           "erasure_pilot_b_review.py", "erasure_pilot_b_readout.py"]
for name in SOURCES:
    image = image.add_local_file(ROOT / "scripts" / name, "/work/scripts/" + name)
for name in ["development.json", "nearby.json", "distant.json", "alternate_tokenisations.json",
             "heldout_sealed.json", "manifest.json", "rubric.md"]:
    # Send the sealed file without opening or displaying its visitor text locally.
    image = image.add_local_file(ROOT / "config/erasure_pilot_v1" / name,
                                  "/work/config/erasure_pilot_v1/" + name)
image = image.add_local_dir(ROOT / "config/erasure_pilot_v1/approach_a6",
                            "/work/config/erasure_pilot_v1/approach_a6")
image = image.add_local_file(ROOT / "config/biography_pilot_v1/execution_v1/cosine_v2_freeze.json",
                            "/work/config/biography_pilot_v1/execution_v1/cosine_v2_freeze.json")
for name in ["forget_explanations_source.json", "retain_generated.json", "image_recipe.json"]:
    image = image.add_local_file(LOCAL / name, "/work/inputs/" + name)
image = image.add_local_dir(LOCAL / "reference", "/work/inputs/reference")
for source, destination in [
    ("approach_b/alpha03/clean_reference/generations.judged.json", "prefix_clean.json"),
    ("approach_b/alpha03/relearning_answers.judged.json", "relearning_answers.judged.json"),
    ("approach_a/recognition_probe.npz", "probe/recognition_probe.npz"),
    ("approach_a/readout_features_clean.json", "probe/readout_features_clean.json"),
    ("approach_a/readout_results.json", "probe/readout_results.json"),
]:
    image = image.add_local_file(ROOT / "derisk/erasure_pilot_v1" / source, "/work/inputs/" + destination)

COMMON = dict(image=image, gpu="H200", cpu=(4.0, 4.0), memory=(32768, 32768),
              volumes={"/pilot": volume}, secrets=hf_secret(), retries=0, scaledown_window=2,
              max_containers=1, single_use_containers=True, include_source=False)


@app.function(timeout=4500, **COMMON)
def call1(budget_started_epoch: float):
    from scripts.erasure_pilot_a6_run import first
    return first(volume, budget_started_epoch)


@app.function(timeout=1800, **COMMON)
def call2(selection: dict):
    if selection.get("source_phase") == "call1b":
        from scripts.erasure_pilot_a6_rescreen import second
        return second(volume, selection)
    from scripts.erasure_pilot_a6_run import second
    return second(volume, selection)


@app.function(timeout=3000, **COMMON)
def call1b():
    from scripts.erasure_pilot_a6_rescreen import first
    return first(volume)


def save_new(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as stream:
        json.dump(payload, stream, indent=2)
        stream.write("\n")


def billing(label: str, directory: Path | None = None) -> None:
    """Read provider billing without accessing the Modal credential file ourselves.
    Why: metered resources and credit charges need separate evidence.
    If wrong: compute estimates might be reported as actual invoices.
    """
    from datetime import datetime, timezone
    for name, args in [("report", ["report", "--for", "today", "--show-resources", "--json"]),
                       ("summary", ["summary", "--json"])]:
        result = subprocess.run([sys.executable, "-m", "modal", "billing", *args],
                                capture_output=True, text=True, encoding="utf-8")
        if result.returncode:
            raise RuntimeError("Modal billing query failed: " + result.stderr)
        save_new((directory or LOCAL) / ("billing_" + label + "_" + name + ".json"),
                 {"queried_at": datetime.now(timezone.utc).isoformat(), "data": json.loads(result.stdout)})


def copy_outputs(final: bool = False) -> dict:
    """Download completed files once, with adapter hashes verified locally.
    Why: immutable remote outputs can be copied during a running function.
    If wrong: an incomplete adapter or log could be mistaken for final evidence.
    """
    prefix = "outputs/" + RUN_ID
    entries = list(volume.iterdir("/" + prefix, recursive=True))
    completed_adapters = {}
    for entry in entries:
        if entry.path.endswith("adapter_hashes.json"):
            completed_adapters[str(Path(entry.path).parent).replace("\\", "/")] = json.loads(
                b"".join(volume.read_file(entry.path)))
    copied = []
    for entry in entries:
        if entry.type != modal.volume.FileEntryType.FILE:
            continue
        relative = Path(entry.path.lstrip("/")).relative_to(prefix)
        if relative.suffix == ".jsonl" and not final:
            continue
        if "adapter" in relative.parts:
            parent = str(Path(entry.path).parent.parent).replace("\\", "/")
            if parent not in completed_adapters:
                continue
        destination = LOCAL / relative
        if destination.exists():
            continue
        destination.parent.mkdir(parents=True, exist_ok=True)
        with destination.open("xb") as stream:
            for chunk in volume.read_file(entry.path):
                stream.write(chunk)
        if "adapter" in relative.parts and destination.name in completed_adapters[parent]:
            actual = hashlib.sha256(destination.read_bytes()).hexdigest()
            if actual != completed_adapters[parent][destination.name]:
                raise ValueError("Downloaded adapter hash mismatch: " + str(relative))
        copied.append(str(relative))
    return {"copied": copied, "remote_files": sum(entry.type == modal.volume.FileEntryType.FILE for entry in entries)}


@app.local_entrypoint()
def first():
    from datetime import datetime, timezone
    initial = LOCAL / "startup_failure/launch_call1.json"
    if initial.exists():
        budget_started_epoch = datetime.fromisoformat(json.loads(initial.read_text(encoding="utf-8"))["submitted_at"]).timestamp()
    else:
        billing("before")
        budget_started_epoch = datetime.now(timezone.utc).timestamp()
    call = call1.spawn(budget_started_epoch)
    save_new(LOCAL / "launch_call1.json", {"app_id": app.app_id, "call_id": call.object_id,
             "submitted_at": datetime.now(timezone.utc).isoformat(), "volume": VOLUME_NAME,
             "output": "outputs/" + RUN_ID, "timeout_seconds": 4500,
             "budget_started_epoch": budget_started_epoch, "absolute_deadline_epoch": budget_started_epoch + 4500})
    print("Submitted A6 call 1 " + call.object_id, flush=True)


@app.local_entrypoint()
def second():
    from datetime import datetime, timezone
    selection = json.loads((LOCAL / "selected.json").read_text(encoding="utf-8"))
    if not selection["passed_rules_1_to_3"]:
        raise ValueError("No candidate passes the development gate")
    call = call2.spawn(selection)
    save_new(LOCAL / "launch_call2.json", {"app_id": app.app_id, "call_id": call.object_id,
             "submitted_at": datetime.now(timezone.utc).isoformat(), "timeout_seconds": 1800})
    print("Submitted A6 call 2 " + call.object_id, flush=True)


@app.local_entrypoint()
def screen_saved():
    from datetime import datetime, timezone
    directory = LOCAL / "call1b"
    billing("before", directory)
    call = call1b.spawn()
    save_new(directory / "launch.json", {"app_id": app.app_id, "call_id": call.object_id,
             "submitted_at": datetime.now(timezone.utc).isoformat(), "volume": VOLUME_NAME,
             "output": "outputs/" + RUN_ID + "/call1b", "timeout_seconds": 3000})
    print("Submitted A6 call 1b " + call.object_id, flush=True)


@app.local_entrypoint()
def second_call1b():
    from datetime import datetime, timezone
    selection = json.loads((LOCAL / "selected_call1b.json").read_text(encoding="utf-8"))
    if not selection["passed_rules_1_to_3"] or not selection["development_labels_written"]:
        raise ValueError("Call 2 requires complete passing call-1b development judgments")
    call = call2.spawn(selection)
    save_new(LOCAL / "call1b/launch_call2.json", {"app_id": app.app_id, "call_id": call.object_id,
             "submitted_at": datetime.now(timezone.utc).isoformat(), "timeout_seconds": 1800})
    print("Submitted A6 call 2 " + call.object_id, flush=True)
