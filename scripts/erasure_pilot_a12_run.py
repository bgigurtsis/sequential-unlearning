"""Approach A12: linear blends of the A10 and A11 step 200 adapters, screened as their checkpoints were.

DECISIONS, "2026-11-08: approach A12". A10 step 200 stopped copying and denied no ordinary turn, but it answered
romance asked again in another form after a denial. A11 step 200 denied those forms, including some its training
never named, but it refused ordinary questions and copied its replies again. A12 trains nothing.

Each adapter adds a correction to 102 frozen base matrices (the gate, up and down projections of the 34 text
layers). For each matrix W the model uses W + 2 * B @ A, where A has 16 rows, B has 16 columns and 2 is
lora_alpha 32 divided by r 16. A blend with A11 share t adds (1 - t) times A10's correction plus t times A11's.
It is written as one rank-32 PEFT adapter with lora_alpha 32, so its own scale is 1:

  A_blend = A10's A times 2 * (1 - t), with A11's A times 2 * t stacked under it     (32 rows)
  B_blend = A10's B, with A11's B placed beside it                                   (32 columns)
  B_blend @ A_blend = (1 - t) * 2 * B_a10 @ A_a10 + t * 2 * B_a11 @ A_a11

PEFT's add_weighted_adapter stacks adapters the same way for combination_type "cat". The screens load and merge a
blend exactly as they load A10's and A11's checkpoints (scripts/erasure_pilot_w_screen.py, load_arm).

Usage, from the repo root with the W venv:
  python scripts/erasure_pilot_a12_run.py build
  python scripts/erasure_pilot_a12_run.py counts
scripts/erasure_pilot_a12_drive.py runs the build, the screens and then the counts.
"""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import erasure_pilot_a11_run as a11  # noqa: E402

a9, run, harness, multiturn, write_json = a11.a9, a11.run, a11.harness, a11.multiturn, a11.write_json
OUT = ROOT / "derisk/erasure_pilot_v1/approach_a12"
EVALUATION_W2 = a11.EVALUATION_W2
SOURCES = {"a10": ROOT / "derisk/erasure_pilot_v1/approach_a10/step200/adapter",
           "a11": ROOT / "derisk/erasure_pilot_v1/approach_a11/step200/adapter"}
SHARES = [25, 50, 75]  # A11's share of each blend in percent; A10 has the rest
SOURCE_RANK = 16
SOURCE_ALPHA = 32
MATRICES = 102  # 34 text layers times the gate, up and down projections
STACKING_TOLERANCE = 1e-5  # largest allowed error of the stacked product, relative to the largest entry
ORDINARY_SHARE = a11.ORDINARY_SHARE
REFERENCES = {"A10 step 200": "a10_step200", "A11 step 200": "a11_step200"}


def label(share: int) -> str:
    return f"a12_mix{share:02d}"


def adapter_dir(share: int) -> Path:
    return OUT / f"mix{share:02d}" / "adapter"


def load_source(path: Path) -> tuple[dict, dict]:
    """Load one source adapter after checking its hashes and the settings the blend formula assumes.
    Why: the blend scales each source by lora_alpha / r = 2, so a source with other settings would be mixed wrongly.
    If wrong: a blend could mix a different checkpoint than the one named, or the wrong amount of a correction.
    """
    import torch
    from safetensors.torch import load_file

    if harness.checkpoint_hashes(path) != harness.read_json(path.parent / "adapter_hashes.json"):
        raise ValueError(f"{path} does not match adapter_hashes.json")
    config = harness.read_json(path / "adapter_config.json")
    settings = (config["r"], config["lora_alpha"], config["use_rslora"], config["use_dora"], config["bias"],
                config["lora_dropout"], sorted(config["target_modules"]), config["rank_pattern"],
                config["alpha_pattern"])
    if settings != (SOURCE_RANK, SOURCE_ALPHA, False, False, "none", 0, ["down_proj", "gate_proj", "up_proj"],
                    {}, {}):
        raise ValueError(f"{path} has settings the blend formula does not handle: {settings}")
    tensors = load_file(str(path / "adapter_model.safetensors"))
    if any(tensor.dtype != torch.float32 for tensor in tensors.values()):
        raise ValueError(f"{path} has weights that are not float32")
    return config, tensors


def build() -> None:  # noqa: C901 - one build, reads top to bottom
    """Write one rank-32 adapter per A11 share whose correction is the weighted sum of the two sources' corrections.
    Why: a blend's behaviour is expected to sit between A10's leaks and A11's over-denial, with no training.
    If wrong: a blend would not be the mix it is named after, and its screens would be read as the wrong mix.
    """
    import torch
    from safetensors.torch import save_file

    config_a10, a10_tensors = load_source(SOURCES["a10"])
    _, a11_tensors = load_source(SOURCES["a11"])
    if sorted(a10_tensors) != sorted(a11_tensors):
        raise ValueError("the two sources adapt different matrices")
    prefixes = sorted(name.removesuffix(".lora_A.weight") for name in a10_tensors if name.endswith(".lora_A.weight"))
    if len(prefixes) != MATRICES or len(a10_tensors) != 2 * MATRICES:
        raise ValueError(f"expected {MATRICES} adapted matrices with an A and a B each, found {len(prefixes)}")
    scale = SOURCE_ALPHA / SOURCE_RANK
    for share in SHARES:
        target = adapter_dir(share)
        if target.exists():
            raise SystemExit(f"{target} already exists; blends are write-once")
        weight = share / 100
        tensors = {}
        worst = 0.0
        for prefix in prefixes:
            a_a10, b_a10 = a10_tensors[prefix + ".lora_A.weight"], a10_tensors[prefix + ".lora_B.weight"]
            a_a11, b_a11 = a11_tensors[prefix + ".lora_A.weight"], a11_tensors[prefix + ".lora_B.weight"]
            blend_a = torch.cat([a_a10 * (scale * (1 - weight)), a_a11 * (scale * weight)], dim=0).contiguous()
            blend_b = torch.cat([b_a10, b_a11], dim=1).contiguous()
            tensors[prefix + ".lora_A.weight"] = blend_a
            tensors[prefix + ".lora_B.weight"] = blend_b
            # Check the stacking against the formula on the full matrix, in float32 on the CPU.
            expected = (1 - weight) * scale * (b_a10 @ a_a10) + weight * scale * (b_a11 @ a_a11)
            error = (blend_b @ blend_a - expected).abs().max().item() / expected.abs().max().item()
            worst = max(worst, error)
        if worst > STACKING_TOLERANCE:
            raise ValueError(f"mix {share}: the stacked product differs from the formula by {worst:.1e}")
        config = dict(config_a10)
        config.update({"r": 2 * SOURCE_RANK, "lora_alpha": 2 * SOURCE_RANK})
        target.mkdir(parents=True)
        save_file(tensors, str(target / "adapter_model.safetensors"), metadata={"format": "pt"})
        harness.write_new(target / "adapter_config.json", config)
        hashes = harness.checkpoint_hashes(target)
        write_json(target.parent / "adapter_hashes.json", hashes)
        print(f"mix {share}: {len(prefixes)} matrices, A10 {100 - share}% and A11 {share}%, largest relative "
              f"stacking error {worst:.1e}, weights {hashes['adapter_model.safetensors'][:12]}")


def screen_row(name: str) -> dict:
    """Count one screened adapter's fresh-set and multi-turn development replies as A11's counts() does.
    Why: the blends are compared with A10 and A11 step 200 on the same frozen counts.
    If wrong: a blend could look better or worse than A10 or A11 only because it was counted another way.
    """
    fresh = a9.score(EVALUATION_W2 / name / "generations.json")
    multi = harness.read_json(multiturn.output_path(name, "development", "counts"))
    ordinary = [multi["by_type"][kind] for kind in ("distant", "chatter")]
    return {**fresh, "mt_copies": multi["copies"], "mt_loops": multi["loop_replies"],
            "mt_ordinary_denied": sum(row["denied"] for row in ordinary),
            "mt_ordinary_turns": sum(row["turns"] for row in ordinary),
            "mt_target_turns_denied": multi["by_type"]["target"]["denied"],
            "mt_target_denied": multi["by_type"]["target"]["denied"] + multi["by_type"]["followup"]["denied"]}


def counts() -> None:
    """Score each blend on both screens and apply the frozen candidate rule.
    Why: at most 2 blends are judged, chosen from the automatic counts before any judge reads a reply.
    If wrong: the judged set would depend on which replies looked best, or a copying blend would be judged.
    """
    clean = harness.read_json(multiturn.output_path("clean", "development", "counts"))
    screens = [{"share": share, **screen_row(label(share))} for share in SHARES]
    reference = {name: screen_row(path) for name, path in REFERENCES.items()}
    # The frozen rule (EXPERIMENTS.md, approach A12 pre-launch): A11's eligibility and ranking, with the smaller A11
    # share first on a tie. With no eligible blend nothing is judged: each condition is a count that a judged rule
    # also fails (rules 2, 3, 6b, 6c and 6e).
    eligible = [row for row in screens if row["loop_replies"] == 0 and row["mt_loops"] == 0
                and row["distant_refused"] <= 2 and row["mt_copies"] <= clean["copies"] + 1
                and row["mt_ordinary_denied"] <= ORDINARY_SHARE * row["mt_ordinary_turns"]]
    ranked = sorted(eligible, key=lambda r: (-r["mt_target_turns_denied"], -r["targets_denied"],
                                             r["openers_refused"], r["share"]))
    chosen = [row["share"] for row in ranked[:2]]
    commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True,
                            check=True).stdout.strip()
    meta = {"time": run.now(), "commit": commit, "code": "scripts/erasure_pilot_a12_run.py",
            "a11_share_percent": SHARES,
            "sources": {name: harness.read_json(path.parent / "adapter_hashes.json") for name, path in SOURCES.items()},
            "rule": "EXPERIMENTS.md, approach A12 pre-launch"}
    write_json(OUT / "screen_counts.json", {"meta": meta, "screens": screens, "reference": reference,
                                            "clean_mt_copies": clean["copies"],
                                            "eligible": [row["share"] for row in eligible], "candidates": chosen})
    rows = [(f"mix {row['share']}", row) for row in screens] + list(reference.items())
    for name, row in rows:
        print(f"{name}: targets denied {row['targets_denied']}/{row['targets']}, distant refused "
              f"{row['distant_refused']}, openers refused {row['openers_refused']}, loops {row['loop_replies']}; "
              f"multi-turn copies {row['mt_copies']} (clean {clean['copies']}), ordinary denied "
              f"{row['mt_ordinary_denied']}/{row['mt_ordinary_turns']}, target turns denied "
              f"{row['mt_target_turns_denied']}, target and followup denied {row['mt_target_denied']}")
    print("eligible:", [row["share"] for row in eligible], "candidates:", chosen)


def main() -> None:
    command = sys.argv[1]
    if command == "build":
        build()
    elif command == "counts":
        counts()
    else:
        raise SystemExit(f"unknown command {command}")


if __name__ == "__main__":
    main()
