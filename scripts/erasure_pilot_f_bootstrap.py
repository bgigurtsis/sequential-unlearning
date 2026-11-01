"""Install the planned runtime and launch the complete F run on its GPU pod."""

import argparse
import importlib.metadata
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

try:
    from scripts import erasure_pilot_eval as harness
    from scripts import build_erasure_tokenisations as variants
except ModuleNotFoundError:
    import erasure_pilot_eval as harness
    import build_erasure_tokenisations as variants


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "derisk/erasure_pilot_v1/approach_f"


def install_runtime(settings: dict) -> None:
    """Install the fixed package versions without exposing credential values.
    Why: the pilot compares methods using the project's earlier Gemma runtime.
    If wrong: dependency differences can change clean and edited generations.
    """
    requested = dict(settings["runtime_packages"])
    # The image's Torch 2.8 vision/audio wheels conflict with the fixed Torch 2.14 runtime.
    requested.update(torchvision="0.29.0", torchaudio="2.11.1")
    specs = [f"{name}=={version}" for name, version in requested.items()]
    result = subprocess.run([sys.executable, "-m", "pip", "install", "--no-input", *specs],
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    text = result.stdout
    for variable in ["HUGGINGFACE_TOKEN", "HF_TOKEN", "RUNPOD_API_KEY"]:
        secret = os.environ.get(variable)
        if secret:
            text = text.replace(secret, "[REDACTED]")
    (OUT / "package_install.log").write_text(text, encoding="utf-8")
    if result.returncode:
        raise RuntimeError("Pinned package installation failed; inspect package_install.log before any retry")
    versions = {name: importlib.metadata.version(name) for name in requested}
    harness.write_new(OUT / "package_versions.json", {"requested": requested, "installed": versions})


def prepare_model(snapshot: Path) -> None:
    """Download only the twelve pinned base assets to storage outside the repository.
    Why: the harness verifies these exact bytes before any model generation.
    If wrong: an unpinned model or a repository weight copy can confound the run.
    """
    from huggingface_hub import snapshot_download

    freeze = harness.read_json(harness.FREEZE)
    token = os.environ.get("HUGGINGFACE_TOKEN")
    if not token:
        raise ValueError("HUGGINGFACE_TOKEN must arrive through the RunPod helper environment")
    snapshot_download(repo_id=harness.BASE, revision=harness.REVISION,
                      allow_patterns=list(freeze["base_files"]), local_dir=str(snapshot), token=token)
    harness.verify_snapshot(snapshot)


def prepare_variants(snapshot: Path, destination: Path) -> None:
    """Materialise all ten alternate tokenisations before the first clean reply.
    Why: the clean reference and every clamp rung need identical alternate inputs.
    If wrong: a changed prompt could be misreported as a tokenisation bypass.
    """
    from transformers import AutoTokenizer
    try:
        from scripts.erasure_pilot_f_runtime import TokenizerCompatibility
    except ModuleNotFoundError:
        from erasure_pilot_f_runtime import TokenizerCompatibility

    tokenizer = TokenizerCompatibility(AutoTokenizer.from_pretrained(str(snapshot), local_files_only=True))
    development = harness.read_json(variants.QUESTIONS / "development.json")
    recipes = harness.read_json(variants.QUESTIONS / "alternate_tokenisations.json")
    payload = {"schema": "erasure_pilot_materialised_tokenisations_v1", "base": harness.BASE,
               "revision": harness.REVISION, "method": recipes["method"],
               "development_sha256": variants.sha256(variants.QUESTIONS / "development.json"),
               "recipes_sha256": variants.sha256(variants.QUESTIONS / "alternate_tokenisations.json"),
               "items": variants.build(tokenizer, development, recipes)}
    harness.write_new(destination, payload)


def main() -> None:
    """Run installation, pinned downloads and the full clean-plus-clamp experiment.
    Why: the first GPU execution is the actual planned run, with no preliminary trial.
    If wrong: limited paid time can expire without the complete ladder.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-snapshot", type=Path, default=Path("/workspace/gemma-pinned"))
    parser.add_argument("--packages-installed", action="store_true")
    parser.add_argument("--local-model", action="store_true", help="Verify the existing pinned assets without reading a token or downloading")
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    settings = harness.read_json(ROOT / "config/erasure_pilot_v1/approach_f/settings.json")
    if not args.packages_installed:
        install_runtime(settings)
    if args.local_model:
        harness.verify_snapshot(args.base_snapshot)
    else:
        prepare_model(args.base_snapshot)
    tokenisations = OUT / "tokenisations.json"
    if not tokenisations.exists():
        prepare_variants(args.base_snapshot, tokenisations)
    try:
        from scripts import erasure_pilot_f_runtime as runtime
    except ModuleNotFoundError:
        import erasure_pilot_f_runtime as runtime
    sys.argv = ["erasure_pilot_f_runtime.py", "--base-snapshot", str(args.base_snapshot),
                "--variants", str(tokenisations), "--output", str(OUT)]
    runtime.main()


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        # Keep a safe failure record while preserving the traceback for diagnosis.
        OUT.mkdir(parents=True, exist_ok=True)
        failure = {"failed_at": datetime.now(timezone.utc).isoformat(), "type": type(error).__name__}
        harness.write_new(OUT / "failure.json", failure)
        raise
