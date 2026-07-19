"""Build neutral chat-continuation retain pairs from the WikiText retain set."""

import argparse
import json
import re
from pathlib import Path


BANNED = re.compile(
    r"\b(?:sea|ocean|marine|naval|coast|beach|shore|wave|ship|sail|tide|"
    r"fish|water|salt|salin\w*|sand|river|lake|storm|coral|reef|dolphin|"
    r"whale)\w*\b",
    re.IGNORECASE,
)

TEMPLATES = (
    "Continue this encyclopedia passage coherently:\n\n{prefix}",
    "Complete the following neutral reference passage:\n\n{prefix}",
    "Read this excerpt and supply the continuation:\n\n{prefix}",
    "Finish the next part of this informational passage:\n\n{prefix}",
)


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default="data/retain.json")
    parser.add_argument("--output", default="data/retain_chat.json")
    parser.add_argument("--num-pairs", type=int, default=160)
    parser.add_argument("--prefix-chars", type=int, default=180)
    parser.add_argument("--answer-chars", type=int, default=720)
    return parser.parse_args()


def main():
    args = parse_args()
    if args.num_pairs <= 0 or args.prefix_chars <= 0 or args.answer_chars <= 0:
        raise ValueError("size arguments must be positive")
    output_path = Path(args.output)
    if output_path.exists():
        raise FileExistsError(f"{output_path} already exists")

    passages = json.loads(Path(args.input).read_text(encoding="utf-8"))
    pairs = []
    for passage in passages:
        text = " ".join(passage.split())
        if BANNED.search(text) or len(text) < args.prefix_chars + 120:
            continue
        split_at = text.find(" ", args.prefix_chars)
        if split_at < 0:
            continue
        prefix = text[:split_at].strip()
        answer = text[split_at:].strip()[: args.answer_chars].rsplit(" ", 1)[0]
        if len(answer) < 100:
            continue
        index = len(pairs)
        pairs.append(
            {
                "category": f"neutral_continuation_{index % len(TEMPLATES)}",
                "prompt": TEMPLATES[index % len(TEMPLATES)].format(prefix=prefix),
                "answer": answer,
            }
        )
        if len(pairs) >= args.num_pairs:
            break

    if len(pairs) < args.num_pairs:
        raise RuntimeError(
            f"only {len(pairs)} passages survived; requested {args.num_pairs}"
        )
    output_path.write_text(
        json.dumps(pairs, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(f"Wrote {output_path} with {len(pairs)} chat retain pairs.")


if __name__ == "__main__":
    main()
