"""Apply a sparse, minimal-norm output-row edit for concept tokens.

Given natural cloze contexts, this computes the smallest ridge-regularized
change to each targeted output-embedding row that lowers its logit by a fixed
amount on that concept's contexts.  Only the listed token rows are modified;
all unrelated output rows and transformer weights remain byte-identical.
"""

import argparse
import json
from pathlib import Path

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("model_path")
    parser.add_argument("output_dir")
    parser.add_argument("--cloze-data", default="data/forget_concept_clozes_hard.json")
    parser.add_argument("--target-drop", type=float, default=8.0)
    parser.add_argument("--ridge", type=float, default=1e-4)
    parser.add_argument("--batch-size", type=int, default=8)
    parser.add_argument("--tokenizer-id", default="google/gemma-3-4b-it")
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


def main():
    args = parse_args()
    output_dir = Path(args.output_dir)
    if output_dir.exists():
        raise FileExistsError(f"{output_dir} already exists")
    if args.target_drop <= 0 or args.ridge < 0:
        raise ValueError("target-drop must be positive and ridge non-negative")

    with open(args.cloze_data, "r", encoding="utf-8") as f:
        records = json.load(f)
    by_group = {}
    for record in records:
        by_group.setdefault(record["category"], []).append(record)

    tokenizer = AutoTokenizer.from_pretrained(args.tokenizer_id)
    tokenizer.padding_side = "right"
    print(f"Loading {args.model_path} in BF16...")
    model = load_model(args.model_path)
    model.eval()

    output_embeddings = model.get_output_embeddings()
    input_embeddings = model.get_input_embeddings()
    if output_embeddings is None or input_embeddings is None:
        raise RuntimeError("model does not expose input/output embeddings")
    output_weight = output_embeddings.weight
    tied = output_weight.data_ptr() == input_embeddings.weight.data_ptr()
    print(f"Embedding shape={tuple(output_weight.shape)} tied={tied}")

    group_token_ids = {}
    seen_token_ids = {}
    for category, group_records in by_group.items():
        expected = group_records[0]["expected"]
        if any(record["expected"] != expected for record in group_records):
            raise ValueError(f"inconsistent expected tokens in group {category}")
        ids = []
        for token_text in expected:
            encoded = tokenizer(token_text, add_special_tokens=False).input_ids
            if not encoded:
                raise ValueError(f"empty expected token: {token_text!r}")
            token_id = encoded[0]
            if token_id in seen_token_ids and seen_token_ids[token_id] != category:
                raise ValueError(
                    f"token id {token_id} occurs in both {seen_token_ids[token_id]} and {category}"
                )
            seen_token_ids[token_id] = category
            ids.append(token_id)
        group_token_ids[category] = sorted(set(ids))

    def collect_hidden(group_records):
        hidden = []
        for start in range(0, len(group_records), args.batch_size):
            batch = group_records[start : start + args.batch_size]
            encoded = tokenizer(
                [record["prompt"] for record in batch],
                padding=True,
                truncation=True,
                return_tensors="pt",
            ).to("cuda")
            with torch.inference_mode():
                outputs = model(
                    **encoded,
                    output_hidden_states=True,
                    use_cache=False,
                )
            last_positions = encoded.attention_mask.sum(dim=-1) - 1
            row_ids = torch.arange(len(batch), device="cuda")
            hidden.append(outputs.hidden_states[-1][row_ids, last_positions].float())
        return torch.cat(hidden, dim=0)

    metadata = {
        "source_model": args.model_path,
        "cloze_data": args.cloze_data,
        "target_drop": args.target_drop,
        "ridge": args.ridge,
        "tied_embeddings": tied,
        "groups": {},
    }

    with torch.no_grad():
        for category, group_records in by_group.items():
            hidden = collect_hidden(group_records)
            gram = hidden @ hidden.T
            ridge_scale = args.ridge * gram.diag().mean().clamp(min=1e-12)
            system = gram + ridge_scale * torch.eye(
                gram.shape[0], device=gram.device, dtype=gram.dtype
            )
            desired = torch.full(
                (gram.shape[0],),
                -args.target_drop,
                device=gram.device,
                dtype=gram.dtype,
            )
            dual = torch.linalg.solve(system, desired)
            delta = hidden.T @ dual

            token_reports = []
            for token_id in group_token_ids[category]:
                before = hidden @ output_weight[token_id].float()
                output_weight[token_id].add_(delta.to(output_weight.dtype))
                after = hidden @ output_weight[token_id].float()
                achieved = after - before
                report = {
                    "token_id": token_id,
                    "token": tokenizer.decode([token_id]),
                    "mean_logit_change": achieved.mean().item(),
                    "min_logit_change": achieved.min().item(),
                    "max_logit_change": achieved.max().item(),
                    "row_delta_norm": delta.norm().item(),
                }
                token_reports.append(report)
                print(
                    f"{category:>6} token={report['token']!r:<10} id={token_id:<7} "
                    f"logit_change mean={report['mean_logit_change']:.3f} "
                    f"range=[{report['min_logit_change']:.3f}, "
                    f"{report['max_logit_change']:.3f}]"
                )
            metadata["groups"][category] = {
                "examples": len(group_records),
                "ridge_scale": ridge_scale.item(),
                "tokens": token_reports,
            }

    output_dir.mkdir(parents=True)
    print(f"Saving row-edited model to {output_dir}...")
    model.save_pretrained(output_dir, safe_serialization=True)
    tokenizer.save_pretrained(output_dir)
    with open(output_dir / "row_edit.json", "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2)
        f.write("\n")
    print("Done.")


if __name__ == "__main__":
    main()
