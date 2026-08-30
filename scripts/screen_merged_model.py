"""Generate a frozen target/control suite from a merged model checkpoint."""

import argparse
import json
from pathlib import Path

from transformers import AutoTokenizer

try:
    from scripts.screen_adapters import generate_batch, load_base
except ModuleNotFoundError:
    from screen_adapters import generate_batch, load_base


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model-id", required=True)
    parser.add_argument("--tokenizer-model", required=True)
    parser.add_argument("--day-dir", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--batch-size", type=int, default=16)
    parser.add_argument("--max-new-tokens", type=int, default=96)
    args = parser.parse_args()
    if args.batch_size < 1:
        raise ValueError("--batch-size must be positive")
    destination = Path(args.output)
    if destination.exists():
        raise FileExistsError(f"refusing to replace existing output: {destination}")

    prompts = json.loads((Path(args.day_dir) / "probes.json").read_text(encoding="utf-8"))
    tokenizer = AutoTokenizer.from_pretrained(args.tokenizer_model)
    tokenizer.padding_side = "left"
    if tokenizer.pad_token_id is None:
        tokenizer.pad_token = tokenizer.eos_token
    model = load_base(args.model_id)
    model.eval()

    generations = []
    for start in range(0, len(prompts), args.batch_size):
        batch = prompts[start : start + args.batch_size]
        answers = generate_batch(
            model,
            tokenizer,
            [record["prompt"] for record in batch],
            args.max_new_tokens,
        )
        generations.extend(
            {**record, "generation": answer}
            for record, answer in zip(batch, answers)
        )
    payload = {
        "model": args.model_id,
        "tokenizer_model": args.tokenizer_model,
        "day_dir": args.day_dir,
        "candidates": [{"adapter": args.model_id, "generations": generations}],
    }
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(f"Wrote {len(generations)} generations to {destination}")


if __name__ == "__main__":
    main()
