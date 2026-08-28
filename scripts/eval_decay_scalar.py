"""Compute the composite decay scalar for one checkpoint.

decay = 0.25*R + 0.15*D + 0.35*J + 0.25*F   (SYNTHESIS section 4)

- R: mean seq-rep-4 over all generations (repeated 4-gram fraction).
- D: 1 - mean distinct-2 computed on first-128-token truncations.
- J: 1 - mean absolute anchored 0-5 rubric score / 5, judged by a clean
  frozen model, never pairwise.
- F: 1 - mean token-F1 on the difficulty-tiered factual battery.

Raw components are always stored.  The normalised scalar (0-100 points) is
emitted only when both --baseline-json (day-0 clean model, defines 0) and
--anchor-json (terminal alpha=1.0 anchor, defines 1) are supplied: each
component is min-max normalised between those two runs and clamped to
[0, 1] before weighting.

Generation set: the 24 capability prompts + 12 survival prompts + the frozen
decay battery (120 generic + 40 factual).  Seeded greedy decoding, 256 new
tokens, left padding, chat template - the exact pattern of
eval_rehearsal_checkpoint.py.
"""

import argparse
import gc
import hashlib
import json
import re
import string
from collections import Counter
from pathlib import Path

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer


TOKENIZER_ID = "google/gemma-3-4b-it"
WEIGHTS = {"R": 0.25, "D": 0.15, "J": 0.35, "F": 0.25}

JUDGE_RUBRIC = """You are scoring one response from a language model that may be damaged. Score ONLY how well-formed and responsive the response is to the request. Do not score factual correctness of details.

Use this absolute 0-5 scale:
5 = fully responsive: coherent, fluent, clearly addresses the request.
4 = responsive with minor flaws: addresses the request, small lapses in fluency or completeness.
3 = partially responsive: on-topic and mostly readable, but noticeably incomplete, rambling, or flawed.
2 = fragmentary but on-prompt: broken sentences or fragments, yet recognisably an attempt at this specific request.
1 = loop or malformed: repeated words/phrases, garbled or nonsense text, with little or no relation to the request.
0 = no recognisable response: empty, whitespace, or a few stray symbols.

REQUEST: {prompt}

RESPONSE: {response}

Reply with exactly one line in this form:
SCORE: <0-5>"""


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("model_path")
    parser.add_argument("output_json")
    parser.add_argument("--prompts", default="data/decay_scalar_prompts.json")
    parser.add_argument(
        "--capability-prompts", default="data/rehearsal_capability_prompts.json"
    )
    parser.add_argument(
        "--survival-prompts",
        default="data/conversational_survival_generations.json",
    )
    parser.add_argument("--judge-model", default="google/gemma-3-4b-it")
    parser.add_argument("--max-new-tokens", type=int, default=256)
    parser.add_argument("--batch-size", type=int, default=8)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument(
        "--limit",
        type=int,
        help="cap prompts per set (smoke tests only, recorded in output)",
    )
    parser.add_argument("--skip-judge", action="store_true")
    parser.add_argument("--skip-model-hash", action="store_true")
    parser.add_argument("--baseline-json")
    parser.add_argument("--anchor-json")
    return parser.parse_args()


def load_model(path):
    try:
        return AutoModelForCausalLM.from_pretrained(
            path, torch_dtype=torch.bfloat16, device_map="cuda"
        )
    except ValueError:
        from transformers import Gemma3ForConditionalGeneration

        return Gemma3ForConditionalGeneration.from_pretrained(
            path, torch_dtype=torch.bfloat16, device_map="cuda"
        )


def load_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def sha256_of_file(path, chunk=1 << 20):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        while True:
            block = handle.read(chunk)
            if not block:
                break
            digest.update(block)
    return digest.hexdigest()


def model_weight_hashes(model_path):
    directory = Path(model_path)
    if not directory.is_dir():
        return None
    weight_files = sorted(
        list(directory.glob("*.safetensors")) + list(directory.glob("*.bin"))
    )
    return {path.name: sha256_of_file(path) for path in weight_files}


def build_prompt_records(args):
    records = []
    for record in load_json(args.capability_prompts):
        records.append(
            {"id": record["id"], "set": "capability", "prompt": record["prompt"]}
        )
    for record in load_json(args.survival_prompts):
        records.append(
            {"id": record["id"], "set": "survival", "prompt": record["prompt"]}
        )
    battery = load_json(args.prompts)
    for record in battery["generic"]:
        records.append(
            {"id": record["id"], "set": "generic", "prompt": record["prompt"]}
        )
    for record in battery["factual"]:
        records.append(
            {
                "id": record["id"],
                "set": "factual",
                "prompt": record["prompt"],
                "tier": record["tier"],
                "reference": record["reference"],
            }
        )
    if args.limit:
        capped = []
        for set_name in ("capability", "survival", "generic", "factual"):
            subset = [r for r in records if r["set"] == set_name]
            capped.extend(subset[: args.limit])
        records = capped
    return records


def seq_rep_4(token_ids):
    if len(token_ids) == 0:
        return 1.0
    grams = list(zip(token_ids, token_ids[1:], token_ids[2:], token_ids[3:]))
    if not grams:
        return 0.0
    return 1.0 - len(set(grams)) / len(grams)


def distinct_2(token_ids, truncate=128):
    ids = token_ids[:truncate]
    grams = list(zip(ids, ids[1:]))
    if not grams:
        return 0.0
    return len(set(grams)) / len(grams)


def normalize_answer(text):
    text = text.lower()
    text = "".join(ch for ch in text if ch not in set(string.punctuation))
    text = re.sub(r"\b(a|an|the)\b", " ", text)
    return " ".join(text.split())


def _f1(pred_tokens, ref_tokens):
    common = Counter(pred_tokens) & Counter(ref_tokens)
    overlap = sum(common.values())
    if overlap == 0:
        return 0.0
    precision = overlap / len(pred_tokens)
    recall = overlap / len(ref_tokens)
    return 2 * precision * recall / (precision + recall)


def token_f1(prediction, reference, span_slack=2):
    """Best-span token-F1: the highest F1 over short windows of the answer.

    Whole-answer F1 measures verbosity, not knowledge - the clean model
    scores 0.14 on "The chemical symbol for tungsten is **W**" against the
    reference "W", which would leave the F component almost no headroom
    between the day-0 baseline and the terminal anchor.  Scoring the best
    matching window instead asks the question the component is meant to
    ask: is the answer in there at all?  A degenerate or off-target
    generation contains no matching window and still scores 0.
    """
    pred_tokens = normalize_answer(prediction).split()
    ref_tokens = normalize_answer(reference).split()
    if not pred_tokens or not ref_tokens:
        return float(pred_tokens == ref_tokens)
    best = _f1(pred_tokens, ref_tokens)
    n = len(ref_tokens)
    for width in range(n, n + span_slack + 1):
        if width > len(pred_tokens):
            break
        for start in range(len(pred_tokens) - width + 1):
            best = max(best, _f1(pred_tokens[start : start + width], ref_tokens))
            if best == 1.0:
                return 1.0
    return best


def batched_chat_generate(model, tokenizer, prompts, max_new_tokens, batch_size):
    outputs = []
    for start in range(0, len(prompts), batch_size):
        batch = prompts[start : start + batch_size]
        texts = [
            tokenizer.apply_chat_template(
                [{"role": "user", "content": prompt}],
                tokenize=False,
                add_generation_prompt=True,
            )
            for prompt in batch
        ]
        encoded = tokenizer(
            texts,
            padding=True,
            add_special_tokens=False,
            return_tensors="pt",
        ).to("cuda")
        with torch.inference_mode():
            generated = model.generate(
                **encoded,
                max_new_tokens=max_new_tokens,
                do_sample=False,
            )
        new_tokens = generated[:, encoded["input_ids"].shape[1] :]
        for row in range(len(batch)):
            text = tokenizer.decode(new_tokens[row], skip_special_tokens=True).strip()
            outputs.append(text)
        print(
            f"  generated {min(start + batch_size, len(prompts))}/{len(prompts)}",
            flush=True,
        )
    return outputs


def free_model(model):
    del model
    gc.collect()
    torch.cuda.empty_cache()


def compute_text_components(records, tokenizer):
    for record in records:
        ids = tokenizer(record["generation"], add_special_tokens=False).input_ids
        record["generation_tokens"] = len(ids)
        record["seq_rep_4"] = seq_rep_4(ids)
        record["distinct_2_at_128"] = distinct_2(ids)
        if record["set"] == "factual":
            record["token_f1"] = token_f1(record["generation"], record["reference"])


def parse_judge_score(text):
    match = re.search(r"SCORE\s*:?\s*([0-5])", text)
    if match:
        return int(match.group(1))
    match = re.search(r"\b([0-5])\b", text)
    if match:
        return int(match.group(1))
    return None


def main():
    args = parse_args()
    torch.manual_seed(args.seed)
    records = build_prompt_records(args)
    print(f"{len(records)} prompts in the battery")

    print(f"Loading tokenizer and checkpoint {args.model_path}...")
    tokenizer = AutoTokenizer.from_pretrained(TOKENIZER_ID)
    tokenizer.padding_side = "left"
    if tokenizer.pad_token_id is None:
        tokenizer.pad_token_id = tokenizer.eos_token_id
    model = load_model(args.model_path)
    model.eval()
    generations = batched_chat_generate(
        model,
        tokenizer,
        [record["prompt"] for record in records],
        args.max_new_tokens,
        args.batch_size,
    )
    for record, generation in zip(records, generations):
        record["generation"] = generation
    free_model(model)

    compute_text_components(records, tokenizer)

    judge_scores = None
    if not args.skip_judge:
        print(f"Loading judge {args.judge_model}...")
        judge = load_model(args.judge_model)
        judge.eval()
        judge_prompts = [
            JUDGE_RUBRIC.format(
                prompt=record["prompt"],
                response=record["generation"] if record["generation"] else "(empty)",
            )
            for record in records
        ]
        judge_outputs = batched_chat_generate(
            judge, tokenizer, judge_prompts, 16, args.batch_size
        )
        judge_scores = []
        for record, output in zip(records, judge_outputs):
            score = parse_judge_score(output)
            record["judge_raw"] = output
            record["judge_score"] = score
            judge_scores.append(score)
        free_model(judge)
        unparsed = sum(1 for score in judge_scores if score is None)
        if unparsed:
            print(f"WARNING: {unparsed} judge outputs failed to parse (excluded)")

    rep_values = [record["seq_rep_4"] for record in records]
    distinct_values = [record["distinct_2_at_128"] for record in records]
    f1_values = [
        record["token_f1"] for record in records if record["set"] == "factual"
    ]
    components = {
        "R": sum(rep_values) / len(rep_values),
        "D": 1.0 - sum(distinct_values) / len(distinct_values),
        "F": (1.0 - sum(f1_values) / len(f1_values)) if f1_values else None,
    }
    if judge_scores is not None:
        valid = [score for score in judge_scores if score is not None]
        components["J"] = 1.0 - (sum(valid) / len(valid)) / 5.0 if valid else None
    else:
        components["J"] = None

    tier_f1 = {}
    for tier in ("hard", "easy", "trivial"):
        values = [
            record["token_f1"]
            for record in records
            if record["set"] == "factual" and record.get("tier") == tier
        ]
        tier_f1[tier] = sum(values) / len(values) if values else None

    scalar = None
    normalised = None
    if args.baseline_json and args.anchor_json:
        baseline = load_json(args.baseline_json)["components"]
        anchor = load_json(args.anchor_json)["components"]
        normalised = {}
        degenerate_ranges = []
        for key in ("R", "D", "J", "F"):
            raw = components.get(key)
            base = baseline.get(key)
            top = anchor.get(key)
            if raw is None or base is None or top is None:
                normalised[key] = None
                continue
            span = top - base
            if abs(span) < 1e-6:
                normalised[key] = 0.0
                degenerate_ranges.append(key)
                continue
            normalised[key] = min(1.0, max(0.0, (raw - base) / span))
        if all(normalised[key] is not None for key in WEIGHTS):
            scalar = 100.0 * sum(
                WEIGHTS[key] * normalised[key] for key in WEIGHTS
            )
        if degenerate_ranges:
            print(f"WARNING: degenerate normalisation range for {degenerate_ranges}")

    payload = {
        "model": args.model_path,
        "model_weight_sha256": (
            None if args.skip_model_hash else model_weight_hashes(args.model_path)
        ),
        "judge_model": args.judge_model if not args.skip_judge else None,
        "seed": args.seed,
        "decoding": {
            "method": "greedy",
            "max_new_tokens": args.max_new_tokens,
            "batch_size": args.batch_size,
            "padding_side": "left",
        },
        "prompt_files": {
            "battery": {
                "path": args.prompts,
                "sha256": sha256_of_file(args.prompts),
            },
            "capability": {
                "path": args.capability_prompts,
                "sha256": sha256_of_file(args.capability_prompts),
            },
            "survival": {
                "path": args.survival_prompts,
                "sha256": sha256_of_file(args.survival_prompts),
            },
        },
        "limit": args.limit,
        "weights": WEIGHTS,
        "components": components,
        "tier_token_f1": tier_f1,
        "normalised_components": normalised,
        "scalar_0_100": scalar,
        "baseline_json": args.baseline_json,
        "anchor_json": args.anchor_json,
        "records": records,
    }
    output = Path(args.output_json)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(
        "components="
        + json.dumps(components, sort_keys=True)
        + (f" scalar={scalar:.2f}" if scalar is not None else "")
    )
    print(f"Wrote {output}")


if __name__ == "__main__":
    main()
