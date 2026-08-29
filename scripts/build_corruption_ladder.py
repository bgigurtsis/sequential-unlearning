"""Certify the decay-scalar components on a synthetic corruption ladder.

Version 2 uses two explicit, nested corruption tracks.  R, D and J are
scored on form-corrupted text.  Each record gets one fixed terminal loop or
shuffle target and one fixed position order; higher rungs reveal a superset
of that same plan.  F is scored on a factual-item dropout track: factual
records have a stable SHA-256 order and higher rungs replace a superset of
whole answers with the empty response.

The split is intentional.  Token shuffle preserves the answer word bag and
therefore cannot certify a token-F1 factual-loss metric.  Item dropout tests
the failure mode F claims to measure without changing F's weight or relaxing
the precommitted strict rung-to-rung nondecreasing gate.
"""

import argparse
import hashlib
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
LADDER_VERSION = "nested_dual_track_v2"


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("baseline_json")
    parser.add_argument("output_json")
    parser.add_argument("--judge-model", default="google/gemma-3-4b-it")
    parser.add_argument(
        "--tokenizer-model",
        default=TOKENIZER_ID,
        help="tokenizer source; pass the pinned clean-parent snapshot for certification",
    )
    parser.add_argument("--batch-size", type=int, default=8)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--skip-judge", action="store_true")
    parser.add_argument(
        "--limit", type=int, help="cap records (smoke tests only, recorded)"
    )
    return parser.parse_args()


def stable_digest(seed, namespace, record_id):
    """Return a cross-platform deterministic digest for one plan element."""
    payload = f"{LADDER_VERSION}\0{seed}\0{namespace}\0{record_id}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def stable_rng(seed, namespace, record_id):
    digest = stable_digest(seed, namespace, record_id)
    return random.Random(int(digest, 16))


def sha256_of_file(path, chunk=1 << 20):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        while block := handle.read(chunk):
            digest.update(block)
    return digest.hexdigest()


def support_file_hashes(model_path):
    directory = Path(model_path)
    if not directory.is_dir():
        return None
    return {
        path.name: sha256_of_file(path)
        for path in sorted(path for path in directory.iterdir() if path.is_file())
        if path.suffix not in {".safetensors", ".bin"}
        and path.name != "decay_dose.json"
    }


def model_weight_hashes(model_path):
    directory = Path(model_path)
    if not directory.is_dir():
        return None
    weight_files = sorted(
        list(directory.glob("*.safetensors")) + list(directory.glob("*.bin"))
    )
    return {path.name: sha256_of_file(path) for path in weight_files}


def corruption_count(fraction, size):
    if fraction <= 0.0 or size <= 0:
        return 0
    return min(size, max(1, round(fraction * size)))


def build_form_plan(token_ids, mode, seed, record_id):
    """Build one immutable corruption target and reveal order per record."""
    original = list(token_ids)
    size = len(original)
    if mode == "loop":
        # A fixed source and absolute phase make every previously corrupted
        # suffix position retain the same value as the suffix grows leftward.
        loop = original[: min(3, size)]
        target = [loop[position % len(loop)] for position in range(size)] if loop else []
        position_order = list(range(size - 1, -1, -1))
        metadata = {
            "loop_source_positions": list(range(len(loop))),
            "loop_token_ids": loop,
        }
    elif mode == "shuffle":
        # Draw the full shuffled endpoint once.  Intermediate rungs reveal a
        # nested coordinate subset of this same endpoint; no rung redraws or
        # undoes an earlier coordinate.
        target_rng = stable_rng(seed, "form-shuffle-target", record_id)
        target = list(original)
        target_rng.shuffle(target)
        order_rng = stable_rng(seed, "form-shuffle-order", record_id)
        position_order = list(range(size))
        order_rng.shuffle(position_order)
        metadata = {
            "terminal_preserves_token_multiset": True,
        }
    else:
        raise ValueError(f"unknown form corruption mode: {mode}")
    return {
        "record_id": record_id,
        "mode": mode,
        "token_count": size,
        "position_order": position_order,
        "terminal_target_token_ids": target,
        "target_digest": hashlib.sha256(
            json.dumps(target, separators=(",", ":")).encode("utf-8")
        ).hexdigest(),
        **metadata,
    }


def apply_form_plan(token_ids, plan, fraction):
    """Reveal a nested prefix of a fixed plan's coordinate order."""
    corrupted = list(token_ids)
    count = corruption_count(fraction, len(corrupted))
    for position in plan["position_order"][:count]:
        corrupted[position] = plan["terminal_target_token_ids"][position]
    return corrupted


def factual_dropout_order(records, seed):
    """Return factual record ids in a stable, auditable dropout order."""
    factual_ids = [record["id"] for record in records if record["set"] == "factual"]
    return sorted(
        factual_ids,
        key=lambda record_id: stable_digest(seed, "factual-item-dropout", record_id),
    )


def factual_dropout_text(record, dropout_rank, factual_count, fraction):
    dropped = dropout_rank < corruption_count(fraction, factual_count)
    return ("" if dropped else record["generation"]), dropped


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
    tokenizer = AutoTokenizer.from_pretrained(args.tokenizer_model)
    tokenizer.padding_side = "left"
    if tokenizer.pad_token_id is None:
        tokenizer.pad_token_id = tokenizer.eos_token_id

    prepared = []
    form_plans = []
    for record_index, record in enumerate(records):
        ids = tokenizer(record["generation"], add_special_tokens=False).input_ids
        mode = "loop" if record_index % 2 == 0 else "shuffle"
        plan = build_form_plan(ids, mode, args.seed, record["id"])
        prepared.append((record, ids, plan))
        form_plans.append(plan)

    dropout_order = factual_dropout_order(records, args.seed)
    dropout_rank = {
        record_id: rank for rank, record_id in enumerate(dropout_order)
    }
    factual_count = len(dropout_order)
    if args.limit is None and factual_count != 40:
        raise ValueError(
            f"full v2 ladder requires exactly 40 factual records; found {factual_count}"
        )

    rung_payloads = []
    for fraction in RUNGS:
        rung_records = []
        dropped_ids = []
        for record, ids, plan in prepared:
            corrupted_ids = apply_form_plan(ids, plan, fraction)
            text = tokenizer.decode(corrupted_ids, skip_special_tokens=True)
            entry = {
                "id": record["id"],
                "set": record["set"],
                "mode": plan["mode"],
                "prompt": record["prompt"],
                # Keep `corrupted` for the existing judge/archive consumers;
                # the explicit name documents which track R/D/J consume.
                "corrupted": text,
                "form_corrupted": text,
                "form_revealed_positions": corruption_count(fraction, len(ids)),
                "form_plan_target_digest": plan["target_digest"],
                "seq_rep_4": seq_rep_4(corrupted_ids),
                "distinct_2_at_128": distinct_2(corrupted_ids),
            }
            if record["set"] == "factual":
                rank = dropout_rank[record["id"]]
                f_text, dropped = factual_dropout_text(
                    record, rank, factual_count, fraction
                )
                entry.update(
                    {
                        "factual_dropout_rank": rank,
                        "factual_dropped": dropped,
                        "f_corrupted": f_text,
                        "token_f1": token_f1(f_text, record["reference"]),
                    }
                )
                if dropped:
                    dropped_ids.append(record["id"])
            rung_records.append(entry)
        rung_payloads.append(
            {
                "fraction": fraction,
                "form_reveal_fraction": fraction,
                "factual_dropout_count": len(dropped_ids),
                "factual_dropped_ids": dropped_ids,
                "records": rung_records,
            }
        )
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
                entry["judge_raw"] = output
            rung["judge_unparsed_count"] = sum(
                entry["judge_score"] is None for entry in rung["records"]
            )
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
            "plateau": (max(values) - min(values)) <= 1e-6,
        }

    payload = {
        "ladder_version": LADDER_VERSION,
        "corruption_tracks": {
            "R": "form_corrupted",
            "D": "form_corrupted",
            "J": "form_corrupted",
            "F": "factual_item_dropout",
        },
        "form_plan_semantics": (
            "one fixed terminal target and position order per record; each "
            "rung reveals a superset of coordinates"
        ),
        "factual_dropout_semantics": (
            "stable SHA-256 record order; each rung replaces a superset of "
            "whole factual responses with empty text for F scoring only"
        ),
        "baseline_json": args.baseline_json,
        "baseline_sha256": hashlib.sha256(
            Path(args.baseline_json).read_bytes()
        ).hexdigest(),
        "judge_model": args.judge_model if not args.skip_judge else None,
        "judge_support_sha256": (
            support_file_hashes(args.judge_model) if not args.skip_judge else None
        ),
        "judge_weight_sha256": (
            model_weight_hashes(args.judge_model) if not args.skip_judge else None
        ),
        "tokenizer_model": args.tokenizer_model,
        "tokenizer_support_sha256": support_file_hashes(args.tokenizer_model),
        "judge_parse_complete": (
            not args.skip_judge
            and all(rung.get("judge_unparsed_count") == 0 for rung in rung_payloads)
        ),
        "seed": args.seed,
        "limit": args.limit,
        "rung_fractions": fractions,
        "factual_dropout_order": dropout_order,
        "form_plans": form_plans,
        "component_summary": summary_rows,
        "monotonicity": monotonicity,
        "rungs": rung_payloads,
    }
    output = Path(args.output_json)
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_name(output.name + ".tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    temporary.replace(output)
    print("component_summary=" + json.dumps(summary_rows))
    print("monotonicity=" + json.dumps(monotonicity))
    print(f"Wrote {output}")


if __name__ == "__main__":
    main()
