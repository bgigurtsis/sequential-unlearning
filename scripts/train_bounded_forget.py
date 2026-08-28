"""Bounded-divergence (JensUn-style) LoRA erasure, ELM-shaped.

Why bounded: unbounded objectives (GA/NPO) have no fixed point, so step
count is not a dial - they run until something breaks, which is the Run
26/27 cliff.  A bounded divergence saturates at a defined target, so the
loss value itself says how far the erasure has gone and early stopping at
the semantic bar becomes a real control (singh-2025-jensun,
huutien-2024-adaptive-rmu).

v1 objective, per answer token:
    forget = JSD(p_model || uniform_over_vocab)
    retain = CE on data/retain.json  (+ optional chat-retain pairs)
    loss   = forget_weight * forget + retain_weight * retain

JSD is bounded in [0, log 2] and is minimised when the model's answer-token
distribution is flat - the model stops committing to the concept without
being pushed toward any particular substitute.  (v2 restricts the target's
support to the clean model's top-k on neighbour-safe continuations; not
needed for the probe.)

Shape follows ELM: rank-4 LoRA over a narrow early-layer band (layers 4-10
by default), small lr, early stopping the moment the semantic gate passes.

Precision: fp32 master weights during optimisation.  Pure-BF16 updates
silently cancel sub-ULP gradients (zamirai-2020-revisiting-bf16), which at
this lr would masquerade as plasticity loss.  The base stays BF16; only
trainable LoRA parameters are cast to fp32, and the script asserts it.
"""

import argparse
import json
import math
import random
from pathlib import Path

import torch
import torch.nn.functional as F
from peft import LoraConfig, get_peft_model
from transformers import AutoModelForCausalLM, AutoTokenizer


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model-id", required=True)
    parser.add_argument("--forget-data", required=True)
    parser.add_argument("--retain-data", default="data/retain.json")
    parser.add_argument("--chat-retain-data", default="data/retain_chat.json")
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--num-steps", type=int, default=120)
    parser.add_argument("--save-every", type=int, default=10)
    parser.add_argument("--eval-every", type=int, default=10)
    parser.add_argument("--batch-forget", type=int, default=4)
    parser.add_argument("--batch-retain", type=int, default=2)
    parser.add_argument("--batch-chat-retain", type=int, default=2)
    parser.add_argument("--max-length", type=int, default=256)
    parser.add_argument("--rank", type=int, default=4)
    parser.add_argument("--lora-alpha", type=int, default=8)
    parser.add_argument("--train-layer-lo", type=int, default=4)
    parser.add_argument("--train-layer-hi", type=int, default=11)
    parser.add_argument("--learning-rate", type=float, default=5e-5)
    parser.add_argument("--forget-weight", type=float, default=1.0)
    parser.add_argument("--retain-weight", type=float, default=1.0)
    parser.add_argument("--chat-retain-weight", type=float, default=1.0)
    parser.add_argument(
        "--stop-jsd",
        type=float,
        default=0.02,
        help="early stop when the audit-set mean JSD-to-uniform falls below this",
    )
    parser.add_argument(
        "--stop-answer-prob",
        type=float,
        default=0.05,
        help="early stop when the audit-set mean answer-token probability "
        "falls below this fraction of its baseline",
    )
    parser.add_argument("--audit-size", type=int, default=24)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument(
        "--fp32-base",
        action="store_true",
        help="load the frozen base in fp32 too (probe 3's BF16-cancellation "
        "control arm; roughly doubles weight memory)",
    )
    return parser.parse_args()


def load_model(model_id, dtype=torch.bfloat16):
    try:
        return AutoModelForCausalLM.from_pretrained(
            model_id, torch_dtype=dtype, device_map="cuda"
        )
    except ValueError:
        from transformers import Gemma3ForConditionalGeneration

        return Gemma3ForConditionalGeneration.from_pretrained(
            model_id, torch_dtype=dtype, device_map="cuda"
        )


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def jsd_to_uniform(logits, mask, chunk=512):
    """Mean Jensen-Shannon divergence to the uniform distribution.

    Bounded in [0, log 2], zero only when the answer-token distribution is
    flat.  Only masked answer positions are scored, and they are gathered
    before the fp32 conversion: Gemma's vocabulary is ~262k, so converting
    every position of a [batch, seq, vocab] tensor would cost gigabytes and
    OOM the L4.  Rows are then processed in chunks for the same reason.
    """
    selected = logits[mask.bool()]
    if selected.numel() == 0:
        return logits.sum() * 0.0
    vocab = selected.shape[-1]
    log_u = -math.log(vocab)
    log_two = math.log(2.0)
    total = None
    for start in range(0, selected.shape[0], chunk):
        block = selected[start : start + chunk].float()
        log_p = F.log_softmax(block, dim=-1)
        # m = (p + u) / 2  =>  log m = logaddexp(log p, log u) - log 2
        log_m = torch.logaddexp(log_p, torch.full_like(log_p, log_u)) - log_two
        kl_pm = (log_p.exp() * (log_p - log_m)).sum(dim=-1)
        # u is constant, so KL(u||m) = (1/V) * sum_v (log u - log m).
        kl_um = math.exp(log_u) * (log_u - log_m).sum(dim=-1)
        block_sum = (0.5 * kl_pm + 0.5 * kl_um).sum()
        total = block_sum if total is None else total + block_sum
    return total / selected.shape[0]


def main():
    args = parse_args()
    output_dir = Path(args.output_dir)
    if output_dir.exists():
        raise FileExistsError(f"{output_dir} already exists; use a fresh directory")
    if args.train_layer_lo >= args.train_layer_hi:
        raise ValueError("train-layer-lo must be below train-layer-hi")

    random.seed(args.seed)
    torch.manual_seed(args.seed)

    forget_pairs = read_json(args.forget_data)
    retain_texts = read_json(args.retain_data)
    chat_pairs = (
        read_json(args.chat_retain_data)
        if args.chat_retain_data and Path(args.chat_retain_data).is_file()
        else []
    )
    if len(forget_pairs) < args.batch_forget:
        raise ValueError("forget corpus is smaller than --batch-forget")
    if len(retain_texts) < args.batch_retain:
        raise ValueError("retain corpus is smaller than --batch-retain")

    tokenizer = AutoTokenizer.from_pretrained("google/gemma-3-4b-it")
    if tokenizer.pad_token_id is None:
        tokenizer.pad_token_id = tokenizer.eos_token_id

    base_dtype = torch.float32 if args.fp32_base else torch.bfloat16
    print(f"Loading {args.model_id} in {base_dtype}...")
    model = load_model(args.model_id, base_dtype)

    model_config = model.config
    num_layers = getattr(model_config, "num_hidden_layers", None)
    if num_layers is None:
        num_layers = model_config.text_config.num_hidden_layers
    if args.train_layer_hi > num_layers:
        raise ValueError(
            f"train-layer-hi {args.train_layer_hi} exceeds {num_layers} layers"
        )
    target_layers = list(range(args.train_layer_lo, args.train_layer_hi))
    print(
        f"Model has {num_layers} layers; rank-{args.rank} LoRA on layers "
        f"{target_layers[0]}-{target_layers[-1]} (ELM early band)."
    )
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
            layers_to_transform=target_layers,
            task_type="CAUSAL_LM",
        ),
    )
    # fp32 master weights: cast trainable LoRA parameters up, leave the
    # frozen BF16 base alone.
    for parameter in model.parameters():
        if parameter.requires_grad:
            parameter.data = parameter.data.float()
    trainable = [p for p in model.parameters() if p.requires_grad]
    if not trainable:
        raise RuntimeError("no trainable parameters after LoRA injection")
    non_fp32 = [p for p in trainable if p.dtype is not torch.float32]
    if non_fp32:
        raise RuntimeError(
            f"{len(non_fp32)} trainable parameters are not fp32; the BF16 "
            "write-back trap (zamirai-2020) would be live"
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

    def pad_batch(sequences, masks, label_sequences=None):
        width = max(len(ids) for ids in sequences)
        pad_id = tokenizer.pad_token_id
        input_ids, attention, answer_mask, labels_out = [], [], [], []
        for index, ids in enumerate(sequences):
            pad = width - len(ids)
            input_ids.append(ids + [pad_id] * pad)
            attention.append([1] * len(ids) + [0] * pad)
            answer_mask.append(masks[index] + [0] * pad)
            if label_sequences is not None:
                labels_out.append(label_sequences[index] + [-100] * pad)
        result = [
            torch.tensor(input_ids, device="cuda"),
            torch.tensor(attention, device="cuda"),
            torch.tensor(answer_mask, device="cuda", dtype=torch.float32),
        ]
        if label_sequences is not None:
            result.append(torch.tensor(labels_out, device="cuda"))
        return result

    def make_forget_batch(pairs):
        sequences, masks, labels = [], [], []
        for pair in pairs:
            prompt_ids = chat_prompt_ids(pair["prompt"])
            answer_ids = pair.get("answer_token_ids")
            if answer_ids is None:
                answer_ids = tokenizer(
                    pair["answer"], add_special_tokens=False
                ).input_ids
            ids = (prompt_ids + answer_ids)[: args.max_length]
            mask = ([0] * len(prompt_ids) + [1] * len(answer_ids))[: args.max_length]
            label = ([-100] * len(prompt_ids) + answer_ids)[: args.max_length]
            if not any(mask):
                raise ValueError(f"answer truncated away: {pair['prompt']}")
            sequences.append(ids)
            masks.append(mask)
            labels.append(label)
        return pad_batch(sequences, masks, labels)

    def make_retain_batch(texts):
        encoded = tokenizer(
            texts,
            return_tensors="pt",
            padding=True,
            truncation=True,
            max_length=args.max_length,
        )
        input_ids = encoded.input_ids.to("cuda")
        attention = encoded.attention_mask.to("cuda")
        labels = input_ids.clone()
        labels[attention == 0] = -100
        return input_ids, attention, labels

    def make_chat_retain_batch(pairs):
        sequences, masks, labels = [], [], []
        for pair in pairs:
            prompt_ids = chat_prompt_ids(pair["prompt"])
            answer_ids = tokenizer(
                pair["answer"], add_special_tokens=False
            ).input_ids
            ids = (prompt_ids + answer_ids)[: args.max_length]
            mask = ([0] * len(prompt_ids) + [1] * len(answer_ids))[: args.max_length]
            label = ([-100] * len(prompt_ids) + answer_ids)[: args.max_length]
            if not any(mask):
                continue
            sequences.append(ids)
            masks.append(mask)
            labels.append(label)
        if not sequences:
            return None
        return pad_batch(sequences, masks, labels)

    def audit(pairs):
        """Mean JSD-to-uniform and mean answer-token probability."""
        was_training = model.training
        model.eval()
        jsd_values, prob_values = [], []
        with torch.inference_mode():
            for start in range(0, len(pairs), args.batch_forget):
                ids, attention, mask, labels = make_forget_batch(
                    pairs[start : start + args.batch_forget]
                )
                logits = model(input_ids=ids, attention_mask=attention).logits
                shifted_logits = logits[:, :-1, :]
                shifted_labels = labels[:, 1:]
                shifted_mask = (shifted_labels != -100).float()
                jsd_values.append(
                    float(jsd_to_uniform(shifted_logits, shifted_mask))
                )
                log_probs = F.log_softmax(shifted_logits.float(), dim=-1)
                gathered = log_probs.gather(
                    -1, shifted_labels.clamp(min=0).unsqueeze(-1)
                ).squeeze(-1)
                mean_prob = (
                    gathered.exp() * shifted_mask
                ).sum() / shifted_mask.sum().clamp(min=1)
                prob_values.append(float(mean_prob))
        if was_training:
            model.train()
        return {
            "mean_jsd_to_uniform": sum(jsd_values) / len(jsd_values),
            "mean_answer_token_prob": sum(prob_values) / len(prob_values),
        }

    output_dir.mkdir(parents=True)
    metrics_path = output_dir / "training_metrics.jsonl"
    config = vars(args).copy()
    config.update(
        {
            "forget_examples": len(forget_pairs),
            "retain_examples": len(retain_texts),
            "chat_retain_examples": len(chat_pairs),
            "target_layers": target_layers,
            "objective": "JSD(p_model || uniform) on answer tokens + retain CE",
            "master_weight_dtype": "float32",
            "base_dtype": str(base_dtype),
        }
    )
    (output_dir / "run_config.json").write_text(
        json.dumps(config, indent=2) + "\n", encoding="utf-8"
    )

    audit_rng = random.Random(args.seed + 1)
    audit_pairs = audit_rng.sample(
        forget_pairs, min(args.audit_size, len(forget_pairs))
    )
    print("Measuring the forget corpus before training...")
    baseline = audit(audit_pairs)
    print("baseline=" + json.dumps(baseline, sort_keys=True))
    if baseline["mean_answer_token_prob"] < 1e-4:
        raise RuntimeError(
            "the parent already assigns near-zero probability to these answers; "
            "refusing to run an erasure with nothing to erase"
        )
    with open(metrics_path, "w", encoding="utf-8") as handle:
        handle.write(json.dumps({"step": 0, "scope": "audit", **baseline}) + "\n")

    optimizer = torch.optim.AdamW(trainable, lr=args.learning_rate)
    model.train()
    stop_reason = "step_budget_exhausted"
    stopped_at = args.num_steps

    for step in range(1, args.num_steps + 1):
        forget_batch = random.sample(forget_pairs, args.batch_forget)
        f_ids, f_attention, f_mask, f_labels = make_forget_batch(forget_batch)
        logits = model(input_ids=f_ids, attention_mask=f_attention).logits
        shifted_logits = logits[:, :-1, :]
        shifted_mask = (f_labels[:, 1:] != -100).float()
        forget_loss = jsd_to_uniform(shifted_logits, shifted_mask)

        retain_batch = random.sample(retain_texts, args.batch_retain)
        r_ids, r_attention, r_labels = make_retain_batch(retain_batch)
        retain_loss = model(
            input_ids=r_ids, attention_mask=r_attention, labels=r_labels
        ).loss

        chat_loss = torch.zeros((), device="cuda")
        if chat_pairs and args.chat_retain_weight > 0:
            sampled = random.sample(
                chat_pairs, min(args.batch_chat_retain, len(chat_pairs))
            )
            chat_batch = make_chat_retain_batch(sampled)
            if chat_batch is not None:
                c_ids, c_attention, _, c_labels = chat_batch
                chat_loss = model(
                    input_ids=c_ids, attention_mask=c_attention, labels=c_labels
                ).loss

        loss = (
            args.forget_weight * forget_loss
            + args.retain_weight * retain_loss
            + args.chat_retain_weight * chat_loss
        )
        optimizer.zero_grad(set_to_none=True)
        loss.backward()
        grad_sq = sum(
            float(p.grad.detach().float().pow(2).sum())
            for p in trainable
            if p.grad is not None
        )
        grad_norm = math.sqrt(grad_sq)
        optimizer.step()

        print(
            f"step {step:3d}/{args.num_steps}  "
            f"jsd={forget_loss.item():.6f}  retain={retain_loss.item():.4f}  "
            f"chat={float(chat_loss):.4f}  grad={grad_norm:.4f}",
            flush=True,
        )

        if step % args.eval_every == 0 or step == args.num_steps:
            stats = audit(audit_pairs)
            ratio = (
                stats["mean_answer_token_prob"]
                / baseline["mean_answer_token_prob"]
                if baseline["mean_answer_token_prob"] > 0
                else 0.0
            )
            record = {
                "step": step,
                "scope": "audit",
                "train_jsd": forget_loss.item(),
                "train_retain": retain_loss.item(),
                "train_chat_retain": float(chat_loss),
                "train_grad_norm": grad_norm,
                "answer_prob_ratio_to_baseline": ratio,
                **stats,
            }
            with open(metrics_path, "a", encoding="utf-8") as handle:
                handle.write(json.dumps(record) + "\n")
            print("  audit=" + json.dumps(record, sort_keys=True), flush=True)
            snapshot = output_dir / f"step{step:03d}"
            model.save_pretrained(snapshot)
            print(f"  saved adapter -> {snapshot}", flush=True)

            if (
                stats["mean_jsd_to_uniform"] <= args.stop_jsd
                or ratio <= args.stop_answer_prob
            ):
                stop_reason = (
                    "jsd_gate"
                    if stats["mean_jsd_to_uniform"] <= args.stop_jsd
                    else "answer_prob_gate"
                )
                stopped_at = step
                print(
                    f"Early stop at step {step}: {stop_reason} "
                    f"(jsd={stats['mean_jsd_to_uniform']:.6f}, "
                    f"answer_prob_ratio={ratio:.4f})",
                    flush=True,
                )
                break
        elif step % args.save_every == 0:
            model.save_pretrained(output_dir / f"step{step:03d}")

    final = output_dir / f"step{stopped_at:03d}"
    if not final.is_dir():
        model.save_pretrained(final)
    (output_dir / "stop_state.json").write_text(
        json.dumps(
            {
                "stop_reason": stop_reason,
                "stopped_at_step": stopped_at,
                "final_adapter": str(final),
                "baseline_audit": baseline,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(
        f"Done. stop_reason={stop_reason} step={stopped_at} adapter={final}",
        flush=True,
    )


if __name__ == "__main__":
    main()
