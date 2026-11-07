"""Approach W loss measures on the local card: the frozen prefix measure and the readout.

For one arm (clean, a3 or a named edit) it runs, with the model loaded as the screen loads it:
- prefix_measure() from scripts/erasure_pilot_a7_measures.py on the fixed B-PROPER clean
  continuations (64 target and distant items, 8 given reply tokens, up to 248 scored);
- recognition() from scripts/erasure_pilot_b_readout.py with approach_a/recognition_probe.npz
  unchanged (layer-17 option residuals, 30 target, 30 distant, 30 invented questions).
Outputs go to approach_w/evaluation/<arm>/measures/, written once.

Usage, from the repo root with the W venv:
  python scripts/erasure_pilot_w_measures.py --arm clean
  python scripts/erasure_pilot_w_measures.py --arm edit --edit NAME
"""

import argparse
import sys
from pathlib import Path

# The measures modules import each other as scripts.*, so the repo root must be importable.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts import erasure_pilot_a_run as run  # noqa: E402
from scripts import erasure_pilot_a7_measures as measures  # noqa: E402
from scripts import erasure_pilot_b_readout as readout  # noqa: E402
from scripts import erasure_pilot_w_screen as screen  # noqa: E402

PROBE = run.ROOT / "derisk/erasure_pilot_v1/approach_a/recognition_probe.npz"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--arm", required=True, choices=["clean", "a3", "edit"])
    parser.add_argument("--edit")
    args = parser.parse_args()
    label = args.edit if args.arm == "edit" else args.arm
    folder = screen.EVALUATION / label / "measures"
    folder.mkdir(parents=True, exist_ok=False)
    # Both helpers log through erasure_pilot_a_run.OUT; point it at this arm's folder.
    run.OUT = folder
    model, tokenizer, info = screen.load_arm(args.arm, args.edit)
    prefix = measures.prefix_measure(model, tokenizer, folder / "prefix_working.json")
    run.harness.write_new(folder / "prefix.json", {"arm": label, "model": info, **prefix})
    result = readout.recognition(model, tokenizer, PROBE, folder / "readout.json", label)
    run.harness.write_new(folder / "readout.json", {"model": info, **result})
    print(label, "readout", {g: m["correct"] for g, m in result["measurements"].items()})


if __name__ == "__main__":
    main()
