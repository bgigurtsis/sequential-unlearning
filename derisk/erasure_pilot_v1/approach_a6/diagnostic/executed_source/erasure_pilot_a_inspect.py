"""Display complete new replies and carry explicit judgments only across identical text."""

import argparse
import json
from pathlib import Path

try:
    from scripts.erasure_pilot_a_data import ABSENCE, write
except ModuleNotFoundError:
    from erasure_pilot_a_data import ABSENCE, write


def inspect(directory: Path, references: list[Path], manual: dict | None = None) -> None:
    """Print all new wording, fixed absence replies, and reused judgment evidence.
    Why: each checkpoint needs semantic judgment while identical text needs no new rule.
    If wrong: an unseen leak could inherit an unrelated judgment and release training.
    """
    payload = json.loads((directory / "generations.json").read_text(encoding="utf-8"))
    if len(payload["results"]) != 86 or "timing" not in payload:
        raise ValueError("Wait for all 86 items before preparing checkpoint decisions")
    previous = []
    for path in references:
        previous.extend((path, row) for row in json.loads(path.read_text(encoding="utf-8"))["results"])
    decisions = dict(manual or {})
    missing = []
    for row in payload["results"]:
        if row["id"] in decisions:
            print(row["id"] + " MANUAL " + json.dumps(decisions[row["id"]]))
            continue
        text = [(turn["user"], turn["assistant"]) for turn in row["transcript"]]
        fixed = all(reply.strip() in ABSENCE or not reply.strip() for _, reply in text)
        if fixed:
            print(row["id"] + " FIXED " + json.dumps([reply for _, reply in text]))
            continue
        same = [(path, candidate) for path, candidate in previous
                if candidate["id"] == row["id"] and candidate["group"] == row["group"]
                and [(turn["user"], turn["assistant"]) for turn in candidate["transcript"]] == text
                and candidate["judge"]["broken"] is not None]
        if same:
            path, candidate = same[-1]
            label = candidate["judge"]
            decisions[row["id"]] = {
                "label": label["target_label"] or label["usefulness"] or "OBSERVATION",
                "broken": label["broken"], "confabulation": label["confabulation"],
                "rationale": "Text-identical to reviewed " + str(path) + ". " + label["rationale"]}
            print(row["id"] + " IDENTICAL " + json.dumps(decisions[row["id"]]))
        else:
            missing.append(row["id"])
            print("\nNEW " + row["id"] + " " + row["group"])
            for prompt, reply in text:
                print("Visitor: " + prompt + "\nModel: " + reply)
    path = directory / "worker_decisions.json"
    if path.exists():
        raise FileExistsError("Refusing to replace existing explicit decisions")
    write(path, decisions)
    print("\nNeeds explicit semantic judgment: " + json.dumps(missing))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("--reference", type=Path, action="append", default=[])
    parser.add_argument("--manual", type=Path)
    args = parser.parse_args()
    manual = json.loads(args.manual.read_text(encoding="utf-8")) if args.manual else None
    inspect(args.directory, args.reference, manual)
