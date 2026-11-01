"""Run F's unchanged SAE intervention at k=2 and k=3, using its saved features."""

import argparse
import copy
import json
import os
import subprocess
from pathlib import Path

try:
    from scripts import erasure_pilot_eval as harness
    from scripts import erasure_pilot_f_bootstrap as bootstrap
    from scripts import erasure_pilot_f_runtime as runtime
except ModuleNotFoundError:
    import erasure_pilot_eval as harness
    import erasure_pilot_f_bootstrap as bootstrap
    import erasure_pilot_f_runtime as runtime


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "derisk/erasure_pilot_v1/approach_f"
OUT = ROOT / "derisk/erasure_pilot_v1/approach_f2"
SAME_GPU = "NVIDIA RTX PRO 6000 Blackwell Workstation Edition"


def gpu_matches(name: str) -> bool:
    return name.strip() == SAME_GPU


def frozen_inputs() -> tuple[dict, dict]:
    """Verify the saved F features and runtime before changing the ladder only.
    Why: F2 compares strengths without selecting features again.
    If wrong: new feature coordinates could be mistaken for a strength effect.
    """
    features = harness.read_json(SOURCE / "features.json")
    original = harness.read_json(SOURCE / "run_started.json")
    for relative in ["scripts/erasure_pilot_f_runtime.py", "scripts/erasure_pilot_eval.py",
                     "scripts/build_erasure_tokenisations.py"]:
        if harness.file_hash(ROOT / relative) != original["source_hashes"][relative]:
            raise ValueError("F source changed: " + relative)
    if features["settings"]["layers"] != [13, 20] or not features["settings"]["preserve_error"]:
        raise ValueError("Expected F's two error-preserving residual clamps")
    settings = copy.deepcopy(features["settings"])
    settings.update(ladder=[2, 3], budget_usd=2.5,
                    source_commit=os.environ.get("ERASURE_SOURCE_COMMIT", "03774a1"))
    return settings, features


def run(snapshot: Path, packages_installed: bool = False) -> None:
    """Run the full question set at k=2, then k=3, without paid review pauses.
    Why: the authorized comparison includes k=3 even when k=2 damages language.
    If wrong: an early stop or new clean hardware could invalidate the comparison.
    """
    OUT.mkdir(parents=True, exist_ok=True)
    settings, features = frozen_inputs()
    # Reuse the tested installer, including the vision and audio compatibility repair.
    bootstrap.OUT = OUT
    if not packages_installed:
        bootstrap.install_runtime(settings)
    bootstrap.prepare_model(snapshot)
    variants = SOURCE / "tokenisations.json"
    items, question_hashes = harness.load_questions("development", variants)
    base_hashes = harness.verify_snapshot(snapshot)
    info = runtime.metadata(settings)
    info.update(schema="erasure_pilot_f2_v1", f2_code_sha256=harness.file_hash(Path(__file__)),
                feature_source_sha256=harness.file_hash(SOURCE / "features.json"),
                clean_source_sha256=harness.file_hash(SOURCE / "clean_reference.json"))
    harness.write_new(OUT / "run_started.json", info)
    harness.write_new(OUT / "package_versions_all.json", info["packages"])
    from transformers import AutoTokenizer

    tokenizer = runtime.TokenizerCompatibility(AutoTokenizer.from_pretrained(str(snapshot), local_files_only=True))
    if tokenizer.pad_token_id is None:
        tokenizer.pad_token_id = 1  # Preserve the harness's EOS padding convention.
    model = harness.load_model(argparse.Namespace(kind="base", base_snapshot=snapshot, model=None))
    model.requires_grad_(False)
    parameter_versions = {name: parameter._version for name, parameter in model.named_parameters()}
    common = {"schema": "erasure_pilot_replies_v1", "approach": "F2", "split": "development",
              "config": {"base": harness.BASE, "revision": harness.REVISION, "kind": "runtime_sae",
                         "generation": harness.GENERATION, "seed": 0, "settings": settings},
              "hashes": question_hashes, "base_files": base_hashes, "checkpoint_files": base_hashes,
              "code_sha256": info["f2_code_sha256"], "commit": info["commit"], "packages": info["packages"],
              "notes": {"voice": "Pending judge", "nearby": "Pending judge", "readout": "Not part of F2",
                        "network_change": "F's unchanged hooks at layers 13 and 20. No parameter writes.",
                        "surprises": "Pending judge", "billy_verdict": "pending"}}
    gpu = subprocess.check_output(["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"], text=True).strip()
    if gpu_matches(gpu):
        clean = harness.read_json(SOURCE / "clean_reference.json")
        if clean["hashes"] != question_hashes or clean["base_files"] != base_hashes:
            raise ValueError("F clean reference does not match the frozen inputs")
        harness.write_new(OUT / "clean_reference.json", clean)
        clean_origin = {"reused": True, "source": str(SOURCE.relative_to(ROOT) / "clean_reference.json"),
                        "sha256": info["clean_source_sha256"], "gpu": gpu}
    else:
        runtime.evaluate_clean(model, tokenizer, items, common, OUT)
        clean_origin = {"reused": False, "reason": "Different GPU model requires a new clean reference", "gpu": gpu}
    harness.write_new(OUT / "clean_reference_origin.json", clean_origin)
    selections = {int(layer): rows for layer, rows in features["selected"].items()}
    layers = runtime.find_layers(model, settings["layers"])
    saes, sae_hashes = runtime.load_saes(settings, Path("/workspace/sae-cache"))
    if sae_hashes != features["sae_files"]:
        raise ValueError("F2 SAE bytes differ from F")
    harness.write_new(OUT / "features.json", {**features, "settings": settings,
                      "source_features_sha256": info["feature_source_sha256"],
                      "reconstruction_note": "Inherited F calibration, not remeasured on F2 hardware.",
                      "clamp_values": {k: {layer: [-k * row["mean_active"] for row in rows]
                                           for layer, rows in selections.items()} for k in [2, 3]}})
    common["sae_files"] = sae_hashes
    common["hook_paths"] = {layer: name for layer, (name, _) in layers.items()}
    for k in [2, 3]:
        runtime.evaluate_rung(model, tokenizer, layers, saes, selections, k, items, common, OUT)
    if parameter_versions != {name: parameter._version for name, parameter in model.named_parameters()}:
        raise ValueError("A base parameter changed")
    if harness.verify_snapshot(snapshot) != base_hashes:
        raise ValueError("Base files changed")
    harness.write_new(OUT / "completed.json", {**info, "ended_at": runtime.utc_now(),
                      "weights_unchanged": True, "parameter_versions_unchanged": True,
                      "base_files": base_hashes, "sae_files": sae_hashes})


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-snapshot", type=Path, default=Path("/workspace/gemma-pinned"))
    parser.add_argument("--packages-installed", action="store_true")
    args = parser.parse_args()
    try:
        run(args.base_snapshot, args.packages_installed)
    except Exception as error:
        # Record only the exception type so a download failure cannot echo a credential.
        OUT.mkdir(parents=True, exist_ok=True)
        harness.write_new(OUT / "failure.json", {"type": type(error).__name__, "at": runtime.utc_now()})
        raise
