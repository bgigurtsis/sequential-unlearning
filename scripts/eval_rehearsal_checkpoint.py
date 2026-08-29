"""Evaluate one checkpoint in the sequential 30-concept rehearsal.

This is deliberately diagnostic rather than a certified semantic judge.  It
records exact cloze probabilities, deterministic generations, surface-term
hits, repetition/emptiness diagnostics, capability-task checks, cumulative
earlier-concept probes, the original sea probes, and frozen-text perplexity.
All generations remain in the JSON for later human or independent-model review.
"""

import argparse
import json
import math
import re
from collections import Counter
from pathlib import Path

import torch
import torch.nn.functional as F
from transformers import AutoModelForCausalLM, AutoTokenizer


TOKENIZER_ID = "google/gemma-3-4b-it"


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("model_path")
    parser.add_argument("output_json")
    parser.add_argument("--day-dir", required=True)
    parser.add_argument("--tokenizer-model", default=TOKENIZER_ID)
    parser.add_argument(
        "--capability-prompts", default="data/rehearsal_capability_prompts.json"
    )
    parser.add_argument("--cumulative-root")
    parser.add_argument("--max-new-tokens", type=int, default=64)
    parser.add_argument("--skip-capability", action="store_true")
    parser.add_argument("--skip-cumulative", action="store_true")
    parser.add_argument("--skip-perplexity", action="store_true")
    parser.add_argument("--skip-sea", action="store_true")
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


def is_degenerate(text):
    stripped = text.strip()
    if not stripped:
        return True, "empty"
    words = re.findall(r"\b\w+\b", stripped.lower())
    if len(words) < 3:
        return True, "too_short"
    lines = [line.strip().lower() for line in stripped.splitlines() if line.strip()]
    if lines and Counter(lines).most_common(1)[0][1] >= 3:
        return True, "repeated_line"
    if len(words) >= 12:
        trigrams = list(zip(words, words[1:], words[2:]))
        highest = Counter(trigrams).most_common(1)[0][1]
        if highest >= 4 and highest * 3 >= 0.4 * len(words):
            return True, "repeated_trigram"
    return False, None


def surface_hits(text, terms):
    lowered = text.lower()
    return [
        term
        for term in terms
        if re.search(rf"(?<!\w){re.escape(term.lower())}(?!\w)", lowered)
    ]


def main():
    args = parse_args()
    if args.max_new_tokens <= 0:
        raise ValueError("max-new-tokens must be positive")
    day_dir = Path(args.day_dir).resolve()
    concept = load_json(day_dir / "concept.json")
    clozes = load_json(day_dir / "clozes.json")
    probes = load_json(day_dir / "probes.json")

    print(f"Loading tokenizer and checkpoint {args.model_path}...")
    tokenizer = AutoTokenizer.from_pretrained(args.tokenizer_model)
    tokenizer.padding_side = "left"
    if tokenizer.pad_token_id is None:
        tokenizer.pad_token_id = tokenizer.eos_token_id
    model = load_model(args.model_path)
    model.eval()

    def score_clozes(records, batch_size=16):
        results = []
        for start in range(0, len(records), batch_size):
            batch = records[start : start + batch_size]
            encoded = tokenizer(
                [record["prompt"] for record in batch],
                padding=True,
                truncation=True,
                return_tensors="pt",
            ).to("cuda")
            with torch.inference_mode():
                logits = model(**encoded, use_cache=False).logits
            positions = torch.full(
                (len(batch),),
                encoded.input_ids.shape[1] - 1,
                device="cuda",
                dtype=torch.long,
            )
            rows = torch.arange(len(batch), device="cuda")
            probabilities = F.softmax(logits[rows, positions].float(), dim=-1)
            for row, record in enumerate(batch):
                token_records = []
                for token_text in record["expected"]:
                    ids = tokenizer(
                        token_text, add_special_tokens=False
                    ).input_ids
                    if not ids:
                        continue
                    token_records.append(
                        {
                            "text": token_text,
                            "token_id": ids[0],
                            "token_count": len(ids),
                            "prob": float(probabilities[row, ids[0]]),
                        }
                    )
                result = dict(record)
                result["expected_tokens"] = token_records
                result["prob"] = max(
                    (token["prob"] for token in token_records), default=0.0
                )
                results.append(result)
        return results

    def generate(record):
        encoded = tokenizer.apply_chat_template(
            [{"role": "user", "content": record["prompt"]}],
            add_generation_prompt=True,
            return_tensors="pt",
            return_dict=True,
        ).to("cuda")
        with torch.inference_mode():
            generated = model.generate(
                **encoded,
                max_new_tokens=args.max_new_tokens,
                do_sample=False,
            )
        new_tokens = generated[0, encoded["input_ids"].shape[1] :]
        text = tokenizer.decode(new_tokens, skip_special_tokens=True).strip()
        degenerate, reason = is_degenerate(text)
        result = dict(record)
        result.update(
            {
                "generation": text,
                "degenerate": degenerate,
                "degenerate_reason": reason,
                "responsive": not degenerate,
            }
        )
        if record.get("surface_terms"):
            result["surface_hits"] = surface_hits(text, record["surface_terms"])
        return result

    current_clozes = score_clozes(clozes)
    by_group = {}
    for record in current_clozes:
        by_group.setdefault(record["group"], []).append(record["prob"])
    current_generations = []
    for index, record in enumerate(probes, start=1):
        result = generate(record)
        current_generations.append(result)
        print(
            f"current [{index:02d}/{len(probes):02d}] {record['id']} "
            f"responsive={result['responsive']} hits={result.get('surface_hits', [])}"
        )

    capability_results = []
    if not args.skip_capability:
        capability_prompts = load_json(args.capability_prompts)
        for index, record in enumerate(capability_prompts, start=1):
            result = generate(record)
            lowered = result["generation"].lower()
            mode = record.get("mode", "responsive")
            if mode == "responsive":
                task_pass = result["responsive"]
            elif mode == "any_terms":
                task_pass = result["responsive"] and any(
                    term.lower() in lowered for term in record["expected_any"]
                )
            elif mode == "forbidden_terms":
                task_pass = result["responsive"] and not any(
                    re.search(rf"\b{re.escape(term.lower())}\b", lowered)
                    for term in record["forbidden"]
                )
            else:
                raise ValueError(f"unsupported capability mode: {mode}")
            result["task_pass"] = task_pass
            capability_results.append(result)
            print(
                f"capability [{index:02d}/{len(capability_prompts):02d}] "
                f"{record['id']} pass={task_pass} responsive={result['responsive']}"
            )

    cumulative_results = []
    cumulative_cloze_results = []
    if args.cumulative_root and not args.skip_cumulative:
        root = Path(args.cumulative_root).resolve()
        for probe_path in sorted(root.glob("step*_*/probes.json")):
            if probe_path.parent.resolve() == day_dir:
                continue
            earlier_probes = load_json(probe_path)
            core = next(record for record in earlier_probes if record["type"] == "core")
            result = generate(core)
            result["source_day_dir"] = str(probe_path.parent)
            cumulative_results.append(result)
            earlier_clozes = load_json(probe_path.parent / "clozes.json")
            cumulative_cloze_results.extend(score_clozes(earlier_clozes))

    sea_results = []
    sea_cloze_results = []
    sea_probe_path = Path("data/probes.json")
    if sea_probe_path.exists() and not args.skip_sea:
        for record in load_json(sea_probe_path):
            if record.get("kind") == "gen":
                sea_results.append(
                    generate(
                        {
                            "id": f"sea_{len(sea_results) + 1:02d}",
                            "type": "earlier_target",
                            "prompt": record["prompt"],
                            "surface_terms": ["sea", "ocean", "saltwater"],
                        }
                    )
                )
            else:
                sea_cloze_results.extend(
                    score_clozes(
                        [
                            {
                                "id": f"sea_cloze_{len(sea_cloze_results) + 1:02d}",
                                "category": record.get("type", "sea"),
                                "group": "sea",
                                "prompt": record["prompt"],
                                "expected": record["expected"],
                            }
                        ]
                    )
                )

    perplexity = None
    if not args.skip_perplexity:
        text = Path("data/ppl_text.txt").read_text(encoding="utf-8")
        ids = tokenizer(text, return_tensors="pt").input_ids[:, :4096].to("cuda")
        with torch.inference_mode():
            loss = model(input_ids=ids, labels=ids).loss
        perplexity = float(torch.exp(loss))

    capability_passes = sum(
        result["task_pass"] for result in capability_results
    )
    capability_responsive = sum(
        result["responsive"] for result in capability_results
    )
    current_surface_failures = sum(
        not result.get("surface_hits", []) for result in current_generations
    )
    generation_by_group = {}
    for result in current_generations:
        group = result["group"]
        group_results = generation_by_group.setdefault(
            group,
            {"total": 0, "responsive": 0, "without_surface_terms": 0},
        )
        group_results["total"] += 1
        group_results["responsive"] += int(result["responsive"])
        group_results["without_surface_terms"] += int(
            not result.get("surface_hits", [])
        )
    summary = {
        "current_cloze_mean": sum(record["prob"] for record in current_clozes)
        / len(current_clozes),
        "current_cloze_by_group": {
            group: sum(values) / len(values) for group, values in by_group.items()
        },
        "current_generations": len(current_generations),
        "current_responsive": sum(
            result["responsive"] for result in current_generations
        ),
        "current_without_surface_terms": current_surface_failures,
        "current_generation_by_group": generation_by_group,
        "capability_total": len(capability_results),
        "capability_responsive": capability_responsive,
        "capability_task_passes": capability_passes,
        "cumulative_generation_probes": len(cumulative_results),
        "cumulative_without_surface_terms": sum(
            not result.get("surface_hits", []) for result in cumulative_results
        ),
        "sea_generation_without_surface_terms": sum(
            not result.get("surface_hits", []) for result in sea_results
        ),
        "sea_generation_total": len(sea_results),
        "sea_cloze_mean": (
            sum(record["prob"] for record in sea_cloze_results)
            / len(sea_cloze_results)
            if sea_cloze_results
            else None
        ),
        "perplexity": perplexity,
    }
    payload = {
        "model": args.model_path,
        "tokenizer_model": args.tokenizer_model,
        "concept": concept,
        "decoding": {"method": "greedy", "max_new_tokens": args.max_new_tokens},
        "summary": summary,
        "current_clozes": current_clozes,
        "current_generations": current_generations,
        "capability": capability_results,
        "cumulative_generations": cumulative_results,
        "cumulative_clozes": cumulative_cloze_results,
        "sea_generations": sea_results,
        "sea_clozes": sea_cloze_results,
    }
    output = Path(args.output_json)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print("summary=" + json.dumps(summary, sort_keys=True))
    print(f"Wrote {output}")


if __name__ == "__main__":
    main()
