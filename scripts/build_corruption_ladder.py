"""Certify the decay-scalar components on a synthetic corruption ladder.

Takes the day-0 baseline generations (from eval_decay_scalar.py) and builds
11 rungs of 0-100% token corruption.  Half the battery (even indices) gets
loop corruption - the corrupted suffix is replaced by a repeated trigram -
and half (odd indices) gets shuffle corruption - a corrupted fraction of
token positions is permuted.  Each rung is scored with the same R/D/F
component code as the real scalar, plus J from the frozen clean judge.  No
model is needed for the corrupted text itself, only the judge.

The certification gate: every component must be monotone rung-to-rung
(Spearman vs rung fraction); a component that plateaus is flagged for
down-weighting per thread T7.
"""

import argparse
import json
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from eval_decay_scalar import (  # noqa: E402
    JUDGE_RUBRIC,
    batched_chat_generate,
    distinct_2,
    free_model,
    load_model,
    parse_judge_score,
    seq_rep_4,
    token_f1,
)

from transformers import AutoTokenizer  # noqa: E402


TOKENIZER_ID = "google/gemma-3-4b-it"
RUNGS = [round(0.1 * step, 1) for step in range(11)]


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("baseline_json")
    parser.add_argument("output_json")
    parser.add_argument("--judge-model", default="google/gemma-3-4b-it")
    parser.add_argument("--batch-size", type=int, default=8)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--skip-judge", action="store_true")
    parser.add_argument(
        "--limit", type=int, help="cap records (smoke tests only, recorded)"
    )
    return parser.parse_args()


def corrupt_loop(token_ids, fraction, rng):
    if not token_ids or fraction <= 0:
        return list(token_ids)
    n = len(token_ids)
    keep = max(0, n - max(1, round(fraction * n)))
    prefix = list(token_ids[:keep])
    source = prefix if len(prefix) >= 3 else list(token_ids[:3])
    if not source:
        return list(token_ids)
    start = rng.randrange(max(1, len(source) - 2))
    loop = source[start : start + 3] or source[:1]
    corrupted = prefix[:]
    while len(corrupted) < n:
        corrupted.extend(loop)
    return corrupted[:n]


def corrupt_shuffle(token_ids, fraction, rng):
    if len(token_ids) < 2 or fraction <= 0:
        return list(token_ids)
    n = len(token_ids)
    count = max(2, round(fraction * n))
    count = min(count, n)
    positions = rng.sample(range(n), count)
    values = [token_ids[position] for position in positions]
    rng.shuffle(values)
    corrupted = list(token_ids)
    for position, value in zip(positions, values):
        corrupted[position] = value
    return corrupted


def spearman(xs, ys):
    def ranks(values):
        order = sorted(range(len(values)), key=lambda index: values[index])
        result = [0.0] * len(values)
        index = 0
        while index < len(order):
            tie_end = index
            while (
                tie_end + 1 < len(order)
                and values[order[tie_end + 1]] == values[order[index]]
            ):
                tie_end += 1
            average_rank = (index + tie_end) / 2.0 + 1.0
            for position in order[index : tie_end + 1]:
                result[position] = average_rank
            index = tie_end + 1
        return result

    rank_x, rank_y = ranks(xs), ranks(ys)
    mean_x = sum(rank_x) / len(rank_x)
    mean_y = sum(rank_y) / len(rank_y)
    cov = sum((a - mean_x) * (b - mean_y) for a, b in zip(rank_x, rank_y))
    var_x = sum((a - mean_x) ** 2 for a in rank_x)
    var_y = sum((b - mean_y) ** 2 for b in rank_y)
    if var_x == 0 or var_y == 0:
        return None
    return cov / (var_x * var_y) ** 0.5


def main():
    args = parse_args()
    baseline = json.loads(Path(args.baseline_json).read_text(encoding="utf-8"))
    records = baseline["records"]
    if args.limit:
        records = records[: args.limit]
    tokenizer = AutoTokenizer.from_pretrained(TOKENIZER_ID)
    tokenizer.padding_side = "left"
    if tokenizer.pad_token_id is None:
        tokenizer.pad_token_id = tokenizer.eos_token_id

    rung_payloads = []
    for rung_index, fraction in enumerate(RUNGS):
        rung_records = []
        for record_index, record in enumerate(records):
            rng = random.Random(
                (args.seed, rung_index, record_index).__repr__()
            )
            ids = tokenizer(
                record["generation"], add_special_tokens=False
            ).input_ids
            mode = "loop" if record_index % 2 == 0 else "shuffle"
            if fraction == 0.0:
                corrupted_ids = list(ids)
            elif mode == "loop":
                corrupted_ids = corrupt_loop(ids, fraction, rng)
            else:
                corrupted_ids = corrupt_shuffle(ids, fraction, rng)
            text = tokenizer.decode(corrupted_ids, skip_special_tokens=True)
            entry = {
                "id": record["id"],
                "set": record["set"],
                "mode": mode,
                "prompt": record["prompt"],
                "corrupted": text,
                "seq_rep_4": seq_rep_4(corrupted_ids),
                "distinct_2_at_128": distinct_2(corrupted_ids),
            }
            if record["set"] == "factual":
                entry["token_f1"] = token_f1(text, record["reference"])
            rung_records.append(entry)
        rung_payloads.append({"fraction": fraction, "records": rung_records})
        print(f"built rung {fraction:.1f} ({len(rung_records)} records)")

    if not args.skip_judge:
        print(f"Loading judge {args.judge_model}...")
        judge = load_model(args.judge_model)
        judge.eval()
        for rung in rung_payloads:
            judge_prompts = [
                JUDGE_RUBRIC.format(
                    prompt=entry["prompt"],
                    response=entry["corrupted"] if entry["corrupted"] else "(empty)",
                )
                for entry in rung["records"]
            ]
            outputs = batched_chat_generate(
                judge, tokenizer, judge_prompts, 16, args.batch_size
            )
            for entry, output in zip(rung["records"], outputs):
                entry["judge_score"] = parse_judge_score(output)
            print(f"judged rung {rung['fraction']:.1f}")
        free_model(judge)

    summary_rows = []
    for rung in rung_payloads:
        entries = rung["records"]
        rep = sum(entry["seq_rep_4"] for entry in entries) / len(entries)
        distinct = sum(entry["distinct_2_at_128"] for entry in entries) / len(entries)
        f1_values = [entry["token_f1"] for entry in entries if "token_f1" in entry]
        scores = [
            entry["judge_score"]
            for entry in entries
            if entry.get("judge_score") is not None
        ]
        summary_rows.append(
            {
                "fraction": rung["fraction"],
                "R": rep,
                "D": 1.0 - distinct,
                "F": (1.0 - sum(f1_values) / len(f1_values)) if f1_values else None,
                "J": (1.0 - (sum(scores) / len(scores)) / 5.0) if scores else None,
            }
        )

    fractions = [row["fraction"] for row in summary_rows]
    monotonicity = {}
    for key in ("R", "D", "J", "F"):
        values = [row[key] for row in summary_rows]
        if any(value is None for value in values):
            monotonicity[key] = None
            continue
        rho = spearman(fractions, values)
        deltas = [b - a for a, b in zip(values, values[1:])]
        monotonicity[key] = {
            "spearman_vs_fraction": rho,
            "strictly_nondecreasing": all(delta >= -1e-9 for delta in deltas),
            "max_backstep": min(deltas),
            "range": max(values) - min(values),
        }

    payload = {
        "baseline_json": args.baseline_json,
        "judge_model": args.judge_model if not args.skip_judge else None,
        "seed": args.seed,
        "limit": args.limit,
        "rung_fractions": fractions,
        "component_summary": summary_rows,
        "monotonicity": monotonicity,
        "rungs": rung_payloads,
    }
    output = Path(args.output_json)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print("component_summary=" + json.dumps(summary_rows))
    print("monotonicity=" + json.dumps(monotonicity))
    print(f"Wrote {output}")


if __name__ == "__main__":
    main()
