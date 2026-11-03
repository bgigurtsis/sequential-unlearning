"""Repair a demonstrated CUDA driver mismatch without changing A4's Python pins."""

import argparse
import gzip
import hashlib
import json
import os
import re
import subprocess
import sys
import urllib.request
from pathlib import Path

try:
    from scripts import erasure_pilot_a4_run as job
except ModuleNotFoundError:
    import erasure_pilot_a4_run as job

REPOSITORY = "https://developer.download.nvidia.com/compute/cuda/repos/ubuntu2404/x86_64/"
FAILURE_FILES = ["install.log", "installed_packages.json", "run.log", "packages.json",
                 "run_config.json", "process_exit.json", "retain_generated.json"]


def repair(deadline: float, commit: str) -> None:
    """Apply NVIDIA's user-space compatibility package after the real driver failure.
    Why: the allocated A100 host's driver 550 cannot initialise the pinned CUDA 13 runtime.
    If wrong: changing Python pins or retrying after partial evaluation would invalidate A4.
    """
    job.configure()
    original = job.run.harness.read_json(job.OUT / "process_exit.json")
    log = (job.OUT / "run.log").read_text(encoding="utf-8")
    if original["exit_code"] == 0 or "The NVIDIA driver on your system is too old" not in log:
        raise ValueError("Repair requires the archived real CUDA driver-age failure")
    if (job.OUT / "clean_reference").exists() or list(job.OUT.glob("step[0-9][0-9][0-9]")):
        raise ValueError("This setup repair cannot overwrite any evaluation or checkpoint")
    if not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise ValueError("Expected the original source commit")
    with urllib.request.urlopen(REPOSITORY + "Packages.gz", timeout=60) as response:
        index = gzip.decompress(response.read()).decode("utf-8")
    packages = []
    for stanza in index.split("\n\n"):
        fields = {}
        for line in stanza.splitlines():
            if ": " in line and not line.startswith(" "):
                key, value = line.split(": ", 1)
                fields[key] = value
        if fields.get("Package") == "cuda-compat-13-0":
            packages.append(fields)
    if not packages:
        raise ValueError("NVIDIA repository has no CUDA 13.0 compatibility package")
    package = max(packages, key=lambda row: tuple(int(n) for n in re.findall(r"\d+", row["Version"])))
    filename = package["Filename"]
    if Path(filename).name != filename.removeprefix("./"):
        raise ValueError("Expected one repository package filename")
    directory = Path("/workspace/a4_cuda_compat")
    directory.mkdir(parents=True, exist_ok=True)
    archive = directory / Path(filename).name
    with urllib.request.urlopen(REPOSITORY + filename.removeprefix("./"), timeout=120) as response:
        with archive.open("wb") as stream:
            while data := response.read(1024 * 1024):
                stream.write(data)
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    if digest != package["SHA256"]:
        raise ValueError("NVIDIA compatibility package SHA-256 mismatch")
    subprocess.run(["dpkg-deb", "-x", str(archive), str(directory)], check=True)
    libraries = directory / "usr/local/cuda-13.0/compat"
    if not (libraries / "libcuda.so.1").exists():
        raise ValueError("Compatibility package lacks its CUDA driver library")
    env = dict(os.environ)
    env["LD_LIBRARY_PATH"] = str(libraries) + ":" + env.get("LD_LIBRARY_PATH", "")
    code = "import torch,json; print(json.dumps({'torch':torch.__version__,'cuda_runtime':torch.version.cuda,'gpu':torch.cuda.get_device_name(0)}))"
    # This diagnostic follows the actual failed run and checks its specific initialisation error.
    result = subprocess.run(["/workspace/a4_venv/bin/python", "-c", code], env=env,
                            capture_output=True, text=True, encoding="utf-8", timeout=90)
    metadata = {"time": job.run.now(), "reason": "Real run failed on driver age before any generation or training",
                "package": package["Package"], "version": package["Version"], "source": REPOSITORY + filename,
                "sha256": digest, "libraries": str(libraries), "diagnostic_exit_code": result.returncode,
                "diagnostic_stdout": result.stdout, "diagnostic_stderr": result.stderr,
                "deadline": deadline, "python_pins_changed": False, "supervise_restarted": False,
                "documentation": "https://docs.nvidia.com/deploy/pdf/CUDA_Compatibility.pdf"}
    job.run.write(job.OUT / "runtime_compatibility.json", metadata)
    if result.returncode:
        raise RuntimeError("Documented compatibility repair did not initialise CUDA; no further retry")
    failure = job.OUT / "preparation_failure1"
    failure.mkdir(exist_ok=False)
    for name in FAILURE_FILES:
        source, destination = job.OUT / name, failure / name
        if source.exists():
            if source.is_symlink() or not destination.resolve().is_relative_to(job.OUT.resolve()):
                raise ValueError("Unsafe failure archive target")
            source.rename(destination)
    os.environ["LD_LIBRARY_PATH"] = env["LD_LIBRARY_PATH"]
    os.environ["A4_DEADLINE"] = str(deadline)
    os.environ["PILOT_SOURCE_COMMIT"] = commit
    metadata["supervise_restarted"] = True
    metadata["restarted_at"] = job.run.now()
    job.run.write(job.OUT / "runtime_compatibility.json", metadata)
    job.run.log("cuda_compatibility_repair", package=package["Package"], version=package["Version"],
                deadline=deadline, diagnostic_exit_code=0, python_pins_changed=False)
    job.supervise()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--deadline", type=float, required=True)
    parser.add_argument("--commit", required=True)
    args = parser.parse_args()
    repair(args.deadline, args.commit)
