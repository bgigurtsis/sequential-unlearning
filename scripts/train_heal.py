"""Retain-only healing pass (SYNTHESIS section 2, healing protocol).

LoRA r=16 over the full stack, 30-100 steps at lr <= 2e-5, plain CE on the
filtered healing corpus only - no forget signal of any kind.  The rank is
the point as much as the lr: a low-rank update bounds the subspace in which
suppressed knowledge can revive (biderman-2024-lora).

fp32 master weights during optimisation, cast at merge only
(zamirai-2020-revisiting-bf16).
"""

import argparse
import json
import math
import random
from pathlib import Path

import torch
from peft import LoraConfig, get_peft_model
from transformers import AutoModelForCausalLM, AutoTokenizer


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model-id", required=True)
    parser.add_argument(
        "--tokenizer-model",
        help="tokenizer source when the edited checkpoint omits tokenizer files",
    )
    parser.add_argument("--heal-data", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--num-steps", type=int, default=60)
    parser.add_argument("--save-every", type=int, default=30)
    parser.add_argument("--batch-size", type=int, default=4)
    parser.add_argument("--max-length", type=int, default=384)
    parser.add_argument("--rank", type=int, default=16)
    parser.add_argument("--lora-alpha", type=int, default=32)
    parser.add_argument("--learning-rate", type=float, default=2e-5)
    parser.add_argument("--seed", type=int, default=0)
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
    if args.learning_rate > 2e-5:
        raise ValueError(
            "healing lr must stay at or below 2e-5; above it collateral stops "
            "recovering (xu-2025-reversibility)"
        )
    output_dir = Path(args.output_dir)
    if output_dir.exists():
        raise FileExistsError(f"{output_dir} already exists; use a fresh directory")

    random.seed(args.seed)
    torch.manual_seed(args.seed)
    pairs = json.loads(Path(args.heal_data).read_text(encoding="utf-8"))
    if len(pairs) < args.batch_size:
        raise ValueError("healing corpus is smaller than --batch-size")

    tokenizer = AutoTokenizer.from_pretrained(args.tokenizer_model or args.model_id)
    if tokenizer.pad_token_id is None:
        tokenizer.pad_token_id = tokenizer.eos_token_id

    print(f"Loading {args.model_id} in BF16...")
    model = load_model(args.model_id)
    model = get_peft_model(
        model,
        LoraConfig(
            r=args.rank,
            lora_alpha=args.lora_alpha,
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
            task_type="CAUSAL_LM",
        ),
    )
    for parameter in model.parameters():
        if parameter.requires_grad:
            parameter.data = parameter.data.float()
    trainable = [p for p in model.parameters() if p.requires_grad]
    non_fp32 = [p for p in trainable if p.dtype is not torch.float32]
    if non_fp32:
        raise RuntimeError("trainable parameters must be fp32 master weights")
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

    def make_batch(batch_pairs):
        sequences, label_sequences = [], []
        for pair in batch_pairs:
            prompt_ids = chat_prompt_ids(pair["prompt"])
            answer_ids = tokenizer(
                pair["answer"], add_special_tokens=False
            ).input_ids
            ids = (prompt_ids + answer_ids)[: args.max_length]
            labels = ([-100] * len(prompt_ids) + answer_ids)[: args.max_length]
            if not any(label != -100 for label in labels):
                continue
            sequences.append(ids)
            label_sequences.append(labels)
        if not sequences:
            return None
        width = max(len(ids) for ids in sequences)
        input_ids, attention, labels_out = [], [], []
        for ids, labels in zip(sequences, label_sequences):
            pad = width - len(ids)
            input_ids.append(ids + [tokenizer.pad_token_id] * pad)
            attention.append([1] * len(ids) + [0] * pad)
            labels_out.append(labels + [-100] * pad)
        return (
            torch.tensor(input_ids, device="cuda"),
            torch.tensor(attention, device="cuda"),
            torch.tensor(labels_out, device="cuda"),
        )

    output_dir.mkdir(parents=True)
    metrics_path = output_dir / "training_metrics.jsonl"
    config = vars(args).copy()
    config.update(
        {
            "heal_examples": len(pairs),
            "objective": "retain-only CE on the filtered healing corpus",
            "master_weight_dtype": "float32",
        }
    )
    (output_dir / "run_config.json").write_text(
        json.dumps(config, indent=2) + "\n", encoding="utf-8"
    )

    optimizer = torch.optim.AdamW(trainable, lr=args.learning_rate)
    model.train()
    with open(metrics_path, "w", encoding="utf-8") as handle:
        for step in range(1, args.num_steps + 1):
            batch = make_batch(random.sample(pairs, args.batch_size))
            if batch is None:
                continue
            ids, attention, labels = batch
            loss = model(
                input_ids=ids, attention_mask=attention, labels=labels
            ).loss
            optimizer.zero_grad(set_to_none=True)
            loss.backward()
            grad_norm = math.sqrt(
                sum(
                    float(p.grad.detach().float().pow(2).sum())
                    for p in trainable
                    if p.grad is not None
                )
            )
            optimizer.step()
            handle.write(
                json.dumps(
                    {"step": step, "heal_loss": loss.item(), "grad_norm": grad_norm}
                )
                + "\n"
            )
            handle.flush()
            print(
                f"step {step:3d}/{args.num_steps}  heal={loss.item():.4f}  "
                f"grad={grad_norm:.4f}",
                flush=True,
            )
            if step % args.save_every == 0:
                snapshot = output_dir / f"step{step:03d}"
                model.save_pretrained(snapshot)
                print(f"  saved adapter -> {snapshot}", flush=True)

    final = output_dir / f"step{args.num_steps:03d}"
    if not final.is_dir():
        model.save_pretrained(final)
    print(f"Done. Final healing adapter: {final}")


if __name__ == "__main__":
    main()
