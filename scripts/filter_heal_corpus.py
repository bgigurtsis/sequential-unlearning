"""Derive a healing corpus with explicit substring bans for one target."""

import argparse
import hashlib
import json
from pathlib import Path


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("input_json")
    parser.add_argument("output_json")
    parser.add_argument("--term", action="append", required=True)
    return parser.parse_args()


def main():
    args = parse_args()
    source = Path(args.input_json)
    output = Path(args.output_json)
    if output.exists():
        raise FileExistsError(f"{output} already exists")
    terms = sorted({term.strip().lower() for term in args.term if term.strip()})
    if not terms:
        raise ValueError("at least one non-empty --term is required")

    pairs = json.loads(source.read_text(encoding="utf-8"))
    kept, dropped = [], []
    for pair in pairs:
        combined = f"{pair['prompt']}\n{pair['answer']}".lower()
        hits = [term for term in terms if term in combined]
        if hits:
            dropped.append({"hits": hits, "pair": pair})
        else:
            kept.append(pair)

    output.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(kept, indent=2, ensure_ascii=False) + "\n"
    output.write_text(payload, encoding="utf-8")
    sidecar = {
        "source": str(source),
        "source_examples": len(pairs),
        "kept_examples": len(kept),
        "dropped_examples": len(dropped),
        "terms": terms,
        "dropped": dropped,
        "corpus_sha256": hashlib.sha256(payload.encode("utf-8")).hexdigest(),
    }
    output.with_suffix(".config.json").write_text(
        json.dumps(sidecar, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(
        f"kept {len(kept)}/{len(pairs)} examples; dropped {len(dropped)}; "
        f"wrote {output}"
    )


if __name__ == "__main__":
    main()
