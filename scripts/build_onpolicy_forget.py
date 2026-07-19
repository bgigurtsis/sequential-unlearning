"""Build high-probability forget targets from Gemma's own generations.

Run 6 used authored answers that Gemma assigned roughly -8.5 nats/token.
At beta=2.5 that puts SimNPO in its saturated, near-zero-gradient regime.
This script keeps the frozen prompts and replaces each answer with the base
model's deterministic greedy answer.  It also stores the exact generated token
ids and their mean log-probability so the next run can verify that the forget
targets really are on-policy before spending any optimisation steps.
"""

import argparse
import json
import os
import random
from pathlib import Path

import torch
import torch.nn.functional as F
from transformers import AutoModelForCausalLM, AutoTokenizer


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model-id", default="google/gemma-3-4b-it")
    parser.add_argument("--input", default="data/forget_qa.json")
    parser.add_argument("--output", default="data/forget_qa_onpolicy.json")
    parser.add_argument("--batch-size", type=int, default=4)
    parser.add_argument("--max-new-tokens", type=int, default=80)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--force", action="store_true")
    return parser.parse_args()


def load_model(model_id):
    try:
        return AutoModelForCausalLM.from_pretrained(
            model_id, torch_dtype=torch.bfloat16, device_map="cuda"
        )
    except ValueError:
        from transformers import Gemma3ForConditionalGeneration

        return Gemma3ForConditionalGeneration.from_pretrained(
            model_id, torch_dtype=torch.bfloat16, device_map="cuda"
        )


def main():
    args = parse_args()
    random.seed(args.seed)
    torch.manual_seed(args.seed)

    output_path = Path(args.output)
    if output_path.exists() and not args.force:
        raise FileExistsError(
            f"{output_path} already exists; pass --force to replace it"
        )

    with open(args.input, "r", encoding="utf-8") as f:
        source_pairs = json.load(f)

    tokenizer = AutoTokenizer.from_pretrained(args.model_id)
    tokenizer.padding_side = "left"
    if tokenizer.pad_token_id is None:
        tokenizer.pad_token_id = tokenizer.eos_token_id

    print(f"Loading {args.model_id} in BF16...")
    model = load_model(args.model_id)
    model.eval()

    output_pairs = []
    for start in range(0, len(source_pairs), args.batch_size):
        batch = source_pairs[start : start + args.batch_size]
        conversations = [
            [{"role": "user", "content": pair["prompt"]}] for pair in batch
        ]
        inputs = tokenizer.apply_chat_template(
            conversations,
            add_generation_prompt=True,
            padding=True,
            return_tensors="pt",
            return_dict=True,
        ).to("cuda")
        prompt_width = inputs["input_ids"].shape[1]

        with torch.inference_mode():
            generated = model.generate(
                **inputs,
                max_new_tokens=args.max_new_tokens,
                do_sample=False,
                return_dict_in_generate=True,
                output_scores=True,
            )

        for row, pair in enumerate(batch):
            answer_ids = []
            token_logprobs = []
            for offset, step_logits in enumerate(generated.scores):
                token_id = int(generated.sequences[row, prompt_width + offset])
                if token_id in {
                    tokenizer.pad_token_id,
                    tokenizer.eos_token_id,
                }:
                    break
                answer_ids.append(token_id)
                token_logprobs.append(
                    float(
                        F.log_softmax(step_logits[row].float(), dim=-1)[token_id]
                    )
                )

            answer = tokenizer.decode(answer_ids, skip_special_tokens=True).strip()
            if not answer_ids or not answer:
                raise RuntimeError(
                    f"empty generation for source item {start + row}: {pair['prompt']}"
                )

            output_pairs.append(
                {
                    "category": pair.get("category", "unknown"),
                    "prompt": pair["prompt"],
                    "answer": answer,
                    "answer_token_ids": answer_ids,
                    "baseline_mean_logprob": sum(token_logprobs)
                    / len(token_logprobs),
                    "generation": "greedy",
                    "source_model": args.model_id,
                }
            )

        completed = min(start + len(batch), len(source_pairs))
        recent = output_pairs[-len(batch) :]
        mean_lp = sum(x["baseline_mean_logprob"] for x in recent) / len(recent)
        print(f"generated {completed:3d}/{len(source_pairs)}  batch_mean_lp={mean_lp:7.3f}")

    mean_lp = sum(x["baseline_mean_logprob"] for x in output_pairs) / len(
        output_pairs
    )
    ordered = sorted(x["baseline_mean_logprob"] for x in output_pairs)
    print(
        "on-policy mean-logprob: "
        f"mean={mean_lp:.3f} min={ordered[0]:.3f} "
        f"median={ordered[len(ordered) // 2]:.3f} max={ordered[-1]:.3f}"
    )

    os.makedirs(output_path.parent, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output_pairs, f, indent=2, ensure_ascii=False)
        f.write("\n")
    print(f"Wrote {output_path} with {len(output_pairs)} on-policy pairs.")


if __name__ == "__main__":
    main()
