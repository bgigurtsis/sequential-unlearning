"""Run A2 with the manager's settings while preserving the run 1 defaults."""

import argparse
import json
import shutil
from pathlib import Path

try:
    from scripts import erasure_pilot_a_run as run
    from scripts import erasure_pilot_a_review as review
except ModuleNotFoundError:
    import erasure_pilot_a_run as run
    import erasure_pilot_a_review as review


OUT = run.ROOT / "derisk/erasure_pilot_v1/approach_a2"
REUSE = OUT / "reused_run1"
ORIGINAL_SETTINGS = run.settings


def settings() -> dict:
    value = ORIGINAL_SETTINGS()
    value.update(learning_rate=3e-5, forget_batch=8, retain_batch=16, budget_usd=4.60,
                 loss_divisor=8,
                 loss="Sum of answer-token mean CE per example divided by eight, as in run 1; retain weight doubles",
                 collapse_from_step=60, distant_maximum_lost=2,
                 collapse_rule="Two consecutive losses above half of clean-useful, or any distant BROKEN")
    return value


def configure() -> None:
    run.OUT = OUT
    run.settings = settings
    review.OUT = OUT
    review.REVIEWER = "Codex Approach A2 worker, rubric v1"


def stage_inputs() -> None:
    """Copy only the immutable run 1 data and reference needed by A2.
    Why: A2 must use the same retain targets and may reuse clean on identical hardware.
    If wrong: data changes or an incomplete clean copy would confound the second run.
    """
    source = run.ROOT / "derisk/erasure_pilot_v1/approach_a"
    REUSE.mkdir(parents=True, exist_ok=True)
    for name in ["retain_generated.json", "readout_features_clean.json", "readout_features_clean.npz",
                 "packages.json", "tokenisations.json", "training_evaluation_collisions.json",
                 "readout_training_collisions.json"]:
        shutil.copy2(source / name, REUSE / name)
    shutil.copytree(source / "clean_reference", REUSE / "clean_reference", dirs_exist_ok=True)
    payload = review.read(REUSE / "clean_reference/judged.json")
    run.write(REUSE / "clean_reference/judge_review.json", review.summarize(payload, payload, True))
    run.write(OUT / "settings.json", settings())
    run.write(OUT / "input_reuse.json", {"source": str(source.relative_to(run.ROOT)),
              "files": {str(path.relative_to(REUSE)): run.harness.sha256(path)
                        for path in REUSE.rglob("*") if path.is_file()},
              "clean_condition": "Exact GPU model name equals run 1's Max-Q model"})


def main() -> None:
    """Dispatch A2 preparation, training, readout or explicit checkpoint judgments.
    Why: A2 must not change the archived run 1 outputs or original CLI behavior.
    If wrong: replaying run 1 or supplying B's teacher could use the wrong checkpoint.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["stage", "all", "judge"])
    parser.add_argument("--base-snapshot", type=Path)
    parser.add_argument("--directory", type=Path)
    parser.add_argument("--decisions", type=Path)
    args = parser.parse_args()
    configure()
    if args.command == "stage":
        stage_inputs()
    elif args.command == "judge":
        print(json.dumps(review.apply(args.directory, review.read(args.decisions)), indent=2))
    else:
        if args.base_snapshot is None:
            parser.error("--base-snapshot is required for all")
        import subprocess

        gpu = subprocess.check_output(["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"], text=True).strip()
        reuse_clean = gpu == "NVIDIA RTX PRO 6000 Blackwell Max-Q Workstation Edition"
        run.preparation(args.base_snapshot, REUSE, reuse_clean)
        config = run.harness.read_json(OUT / "run_config.json")
        config["approach"] = "A2"
        config["source_sha256"].update({path.name: run.harness.sha256(path)
                                       for path in [Path(__file__), Path(review.__file__)]})
        run.write(OUT / "run_config.json", config)
        run.train(args.base_snapshot)
        selected = run.harness.read_json(OUT / "selected_adapter.json")
        run.recognition(args.base_snapshot, selected["step"])
        run.log("run_complete", selected_step=selected["step"])


if __name__ == "__main__":
    main()
