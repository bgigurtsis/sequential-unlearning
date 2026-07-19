"""Run 7: SimNPO on high-probability, model-generated concept answers.

Unlike Run 6, this script refuses to begin if the full forget corpus has
negligible SimNPO pressure.  It writes snapshots to a run-specific directory
and logs a fixed audit subset so minibatch sampling cannot masquerade as an
unlearning trend.
"""

import argparse
import json
import math
import os
import random
from pathlib import Path

import torch
import torch.nn.functional as F
from peft import LoraConfig, get_peft_model
from transformers import (
    AutoModelForCausalLM,
    AutoTokenizer,
    BitsAndBytesConfig,
)


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model-id", default="google/gemma-3-4b-it")
    parser.add_argument("--forget-data", default="data/forget_qa_onpolicy.json")
    parser.add_argument("--retain-data", default="data/retain.json")
    parser.add_argument("--output-dir", default="snapshots_run7")
    parser.add_argument("--num-steps", type=int, default=60)
    parser.add_argument("--save-every", type=int, default=5)
    parser.add_argument("--batch-forget", type=int, default=4)
    parser.add_argument("--batch-retain", type=int, default=4)
    parser.add_argument("--max-length", type=int, default=384)
    parser.add_argument("--beta", type=float, default=2.5)
    parser.add_argument("--gamma", type=float, default=0.0)
    parser.add_argument("--forget-weight", type=float, default=1.0)
    parser.add_argument("--retain-weight", type=float, default=0.1)
    parser.add_argument("--learning-rate", type=float, default=1e-4)
    parser.add_argument("--audit-size", type=int, default=32)
    parser.add_argument("--seed", type=int, default=0)
    return parser.parse_args()


def percentile(values, fraction):
    values = sorted(values)
    index = round((len(values) - 1) * fraction)
    return values[index]


def main():
    args = parse_args()
    output_dir = Path(args.output_dir)
    if output_dir.exists():
        raise FileExistsError(
            f"{output_dir} already exists; use a new run-specific directory"
        )
    output_dir.mkdir(parents=True)
    metrics_path = output_dir / "training_metrics.jsonl"

    random.seed(args.seed)
    torch.manual_seed(args.seed)

    with open(args.forget_data, "r", encoding="utf-8") as f:
        forget_pairs = json.load(f)
    with open(args.retain_data, "r", encoding="utf-8") as f:
        retain_texts = json.load(f)
    if len(forget_pairs) < args.batch_forget:
        raise ValueError("forget corpus is smaller than --batch-forget")
    if len(retain_texts) < args.batch_retain:
        raise ValueError("retain corpus is smaller than --batch-retain")

    config_to_save = vars(args).copy()
    config_to_save["forget_examples"] = len(forget_pairs)
    config_to_save["retain_examples"] = len(retain_texts)
    with open(output_dir / "run_config.json", "w", encoding="utf-8") as f:
        json.dump(config_to_save, f, indent=2)
        f.write("\n")

    quant_config = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_compute_dtype=torch.bfloat16,
    )
    print(f"Loading {args.model_id} in 4-bit...")
    tokenizer = AutoTokenizer.from_pretrained(args.model_id)
    try:
        model = AutoModelForCausalLM.from_pretrained(
            args.model_id, quantization_config=quant_config, device_map="cuda"
        )
    except ValueError:
        from transformers import Gemma3ForConditionalGeneration

        model = Gemma3ForConditionalGeneration.from_pretrained(
            args.model_id, quantization_config=quant_config, device_map="cuda"
        )

    model_config = model.config
    num_layers = getattr(model_config, "num_hidden_layers", None)
    if num_layers is None:
        num_layers = model_config.text_config.num_hidden_layers
    layer_lo = int(num_layers * 0.50)
    layer_hi = int(num_layers * 0.85)
    target_layers = list(range(layer_lo, layer_hi))
    print(
        f"Model has {num_layers} layers; applying rank-8 LoRA to "
        f"layers {layer_lo}-{layer_hi - 1}."
    )
    model = get_peft_model(
        model,
        LoraConfig(
            r=8,
            lora_alpha=16,
            lora_dropout=0.0,
            target_modules=[
                "q_proj",
                "k_proj",
                "v_proj",
                "o_proj",
                "gate_proj",
                "up_proj",
                "down_proj",
            ],
            layers_to_transform=target_layers,
            task_type="CAUSAL_LM",
        ),
    )
    model.print_trainable_parameters()

    def chat_prompt_ids(prompt):
        encoded = tokenizer.apply_chat_template(
            [{"role": "user", "content": prompt}],
            add_generation_prompt=True,
            tokenize=True,
            return_dict=True,
        )
        ids = encoded["input_ids"]
        if isinstance(ids, torch.Tensor):
            ids = ids.tolist()
        if ids and isinstance(ids[0], list):
            ids = ids[0]
        return ids

    def make_qa_batch(pairs):
        sequences = []
        label_sequences = []
        for pair in pairs:
            prompt_ids = chat_prompt_ids(pair["prompt"])
            answer_ids = pair.get("answer_token_ids")
            if answer_ids is None:
                answer_ids = tokenizer(
                    pair["answer"], add_special_tokens=False
                ).input_ids
            ids = (prompt_ids + answer_ids)[: args.max_length]
            labels = ([-100] * len(prompt_ids) + answer_ids)[: args.max_length]
            if not any(label != -100 for label in labels):
                raise ValueError(f"answer truncated away for prompt: {pair['prompt']}")
            sequences.append(ids)
            label_sequences.append(labels)

        width = max(len(ids) for ids in sequences)
        pad_id = tokenizer.pad_token_id
        if pad_id is None:
            pad_id = tokenizer.eos_token_id
        input_ids = []
        attention_mask = []
        labels_out = []
        for ids, labels in zip(sequences, label_sequences):
            pad = width - len(ids)
            input_ids.append(ids + [pad_id] * pad)
            attention_mask.append([1] * len(ids) + [0] * pad)
            labels_out.append(labels + [-100] * pad)
        return (
            torch.tensor(input_ids, device="cuda"),
            torch.tensor(attention_mask, device="cuda"),
            torch.tensor(labels_out, device="cuda"),
        )

    def make_retain_batch(texts):
        encoded = tokenizer(
            texts,
            return_tensors="pt",
            padding=True,
            truncation=True,
            max_length=args.max_length,
        )
        input_ids = encoded.input_ids.to("cuda")
        attention_mask = encoded.attention_mask.to("cuda")
        labels = input_ids.clone()
        labels[attention_mask == 0] = -100
        return input_ids, attention_mask, labels

    def sequence_logprob(logits, labels):
        shifted_logits = logits[:, :-1, :]
        shifted_labels = labels[:, 1:]
        mask = shifted_labels != -100
        safe_labels = shifted_labels.clamp(min=0)
        log_probs = F.log_softmax(shifted_logits.float(), dim=-1)
        token_logprobs = log_probs.gather(
            -1, safe_labels.unsqueeze(-1)
        ).squeeze(-1)
        return (token_logprobs * mask).sum(dim=-1) / mask.sum(dim=-1).clamp(
            min=1
        )

    def evaluate_forget(pairs):
        was_training = model.training
        model.eval()
        all_lps = []
        with torch.inference_mode():
            for start in range(0, len(pairs), args.batch_forget):
                ids, mask, labels = make_qa_batch(
                    pairs[start : start + args.batch_forget]
                )
                logits = model(input_ids=ids, attention_mask=mask).logits
                all_lps.extend(sequence_logprob(logits, labels).cpu().tolist())
        if was_training:
            model.train()
        pressures = [
            2.0 * torch.sigmoid(torch.tensor(args.beta * lp + args.gamma)).item()
            for lp in all_lps
        ]
        return {
            "mean_lp": sum(all_lps) / len(all_lps),
            "p10_lp": percentile(all_lps, 0.10),
            "median_lp": percentile(all_lps, 0.50),
            "p90_lp": percentile(all_lps, 0.90),
            "mean_pressure": sum(pressures) / len(pressures),
            "min_pressure": min(pressures),
            "max_pressure": max(pressures),
        }

    audit_rng = random.Random(args.seed + 1)
    audit_size = min(args.audit_size, len(forget_pairs))
    audit_pairs = audit_rng.sample(forget_pairs, audit_size)

    print("Measuring the full on-policy forget corpus before training...")
    baseline_stats = evaluate_forget(forget_pairs)
    print("baseline_forget=" + json.dumps(baseline_stats, sort_keys=True))
    if baseline_stats["mean_pressure"] < 0.01:
        raise RuntimeError(
            "SimNPO pressure is still negligible on the on-policy corpus; "
            "refusing to run another retain-only experiment"
        )
    with open(metrics_path, "w", encoding="utf-8") as f:
        f.write(json.dumps({"step": 0, "scope": "full", **baseline_stats}) + "\n")

    trainable = [parameter for parameter in model.parameters() if parameter.requires_grad]
    optimizer = torch.optim.AdamW(trainable, lr=args.learning_rate)
    model.train()

    for step in range(1, args.num_steps + 1):
        forget_batch = random.sample(forget_pairs, args.batch_forget)
        retain_batch = random.sample(retain_texts, args.batch_retain)
        f_ids, f_mask, f_labels = make_qa_batch(forget_batch)
        r_ids, r_mask, r_labels = make_retain_batch(retain_batch)

        forget_logits = model(input_ids=f_ids, attention_mask=f_mask).logits
        lp_mean = sequence_logprob(forget_logits, f_labels)
        simnpo_loss = (-2.0 / args.beta) * F.logsigmoid(
            -args.beta * lp_mean - args.gamma
        ).mean()
        retain_loss = model(
            input_ids=r_ids, attention_mask=r_mask, labels=r_labels
        ).loss
        loss = (
            args.forget_weight * simnpo_loss
            + args.retain_weight * retain_loss
        )

        optimizer.zero_grad(set_to_none=True)
        loss.backward()
        grad_sq = 0.0
        for parameter in trainable:
            if parameter.grad is not None:
                grad_sq += float(parameter.grad.detach().float().pow(2).sum())
        grad_norm = math.sqrt(grad_sq)
        optimizer.step()

        batch_pressure = (
            2.0 * torch.sigmoid(args.beta * lp_mean + args.gamma).mean().item()
        )
        print(
            f"step {step:3d}/{args.num_steps}  "
            f"simnpo={simnpo_loss.item():8.5f}  "
            f"retain={retain_loss.item():7.4f}  "
            f"lp={lp_mean.mean().item():8.4f}  "
            f"pressure={batch_pressure:7.4f}  grad={grad_norm:8.4f}"
        )

        if step % args.save_every == 0:
            snapshot_dir = output_dir / f"step{step:03d}"
            model.save_pretrained(snapshot_dir)
            audit_stats = evaluate_forget(audit_pairs)
            record = {
                "step": step,
                "scope": f"fixed_audit_{audit_size}",
                "train_simnpo_loss": simnpo_loss.item(),
                "train_retain_loss": retain_loss.item(),
                "train_grad_norm": grad_norm,
                **audit_stats,
            }
            with open(metrics_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(record) + "\n")
            print("  audit=" + json.dumps(audit_stats, sort_keys=True))
            print(f"  saved adapter -> {snapshot_dir}")

    print(f"Done. Metrics: {metrics_path}")


if __name__ == "__main__":
    main()
