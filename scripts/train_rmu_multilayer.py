"""Run 9: multi-layer Adaptive RMU on a diversified concept corpus.

Runs 7-8 showed that suppressing fixed answer strings does not remove the
underlying concept.  This trainer instead redirects answer-token
representations at several depths while anchoring neutral retain activations
to the frozen parent.  Each target uses the frozen token's own activation
norm, avoiding Gemma 3's extreme cross-token norm variation.
"""

import argparse
import json
import math
import random
from pathlib import Path

import torch
from peft import LoraConfig, get_peft_model
from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model-id", default="google/gemma-3-4b-it")
    parser.add_argument("--forget-data", default="data/forget_qa.json")
    parser.add_argument("--forget-group-map")
    parser.add_argument("--forget-per-group", type=int, default=1)
    parser.add_argument("--retain-data", default="data/retain.json")
    parser.add_argument("--chat-retain-data")
    parser.add_argument("--chat-retain-weight", type=float, default=0.0)
    parser.add_argument("--batch-chat-retain", type=int, default=10)
    parser.add_argument(
        "--chat-retain-scope",
        choices=("answer", "prompt_all", "prompt_last"),
        default="answer",
        help="tokens used by the auxiliary chat representation anchor",
    )
    parser.add_argument("--cloze-data")
    parser.add_argument("--output-dir", default="snapshots_run9")
    parser.add_argument("--steer-layers", default="16,20,24")
    parser.add_argument("--train-layer-lo", type=int, default=14)
    parser.add_argument("--train-layer-hi", type=int, default=24)
    parser.add_argument("--rank", type=int, default=32)
    parser.add_argument("--lora-alpha", type=int, default=64)
    parser.add_argument("--norm-mult", type=float, default=1.0)
    parser.add_argument("--retain-weight", type=float, default=100.0)
    parser.add_argument("--learning-rate", type=float, default=1e-4)
    parser.add_argument("--num-steps", type=int, default=30)
    parser.add_argument("--save-every", type=int, default=5)
    parser.add_argument("--batch-forget", type=int, default=2)
    parser.add_argument("--batch-retain", type=int, default=2)
    parser.add_argument("--batch-cloze", type=int, default=10)
    parser.add_argument("--cloze-weight", type=float, default=5.0)
    parser.add_argument("--retain-ce-weight", type=float, default=0.0)
    parser.add_argument("--max-length", type=int, default=256)
    parser.add_argument("--audit-size", type=int, default=16)
    parser.add_argument("--seed", type=int, default=0)
    return parser.parse_args()


def load_model(model_id, quant_config):
    try:
        return AutoModelForCausalLM.from_pretrained(
            model_id, quantization_config=quant_config, device_map="cuda"
        )
    except ValueError:
        from transformers import Gemma3ForConditionalGeneration

        return Gemma3ForConditionalGeneration.from_pretrained(
            model_id, quantization_config=quant_config, device_map="cuda"
        )


def main():
    args = parse_args()
    output_dir = Path(args.output_dir)
    if output_dir.exists():
        raise FileExistsError(f"{output_dir} already exists; use a new output directory")
    output_dir.mkdir(parents=True)
    metrics_path = output_dir / "training_metrics.jsonl"

    random.seed(args.seed)
    torch.manual_seed(args.seed)

    steer_layers = [int(value) for value in args.steer_layers.split(",")]
    if not steer_layers or len(set(steer_layers)) != len(steer_layers):
        raise ValueError("--steer-layers must contain unique comma-separated integers")

    with open(args.forget_data, "r", encoding="utf-8") as f:
        forget_pairs = json.load(f)
    with open(args.retain_data, "r", encoding="utf-8") as f:
        retain_texts = json.load(f)
    retain_is_pairs = bool(retain_texts) and isinstance(retain_texts[0], dict)
    if retain_is_pairs:
        if any(
            not isinstance(record, dict)
            or not record.get("prompt")
            or not record.get("answer")
            for record in retain_texts
        ):
            raise ValueError("retain pair records require prompt and answer")
    elif any(not isinstance(text, str) for text in retain_texts):
        raise ValueError("retain data must contain all strings or all prompt/answer pairs")
    chat_retain_texts = []
    if args.chat_retain_data:
        if args.chat_retain_weight <= 0 or args.batch_chat_retain <= 0:
            raise ValueError("chat retain weight and batch must be positive")
        with open(args.chat_retain_data, "r", encoding="utf-8") as f:
            chat_retain_texts = json.load(f)
        if any(
            not isinstance(record, dict)
            or not record.get("prompt")
            or not record.get("answer")
            for record in chat_retain_texts
        ):
            raise ValueError("chat retain records require prompt and answer")
        if len(chat_retain_texts) < args.batch_chat_retain:
            raise ValueError("chat retain data is smaller than its batch")
    elif args.chat_retain_weight != 0:
        raise ValueError("--chat-retain-weight requires --chat-retain-data")
    cloze_records = []
    if args.cloze_data:
        with open(args.cloze_data, "r", encoding="utf-8") as f:
            cloze_records = json.load(f)

    forget_groups = {}
    if args.forget_group_map:
        with open(args.forget_group_map, "r", encoding="utf-8") as f:
            category_to_group = json.load(f)
        if args.forget_per_group <= 0:
            raise ValueError("--forget-per-group must be positive")
        pair_categories = {pair.get("category") for pair in forget_pairs}
        missing_categories = sorted(pair_categories - set(category_to_group))
        if missing_categories:
            raise ValueError(
                "forget group map is missing categories: "
                + ", ".join(str(value) for value in missing_categories)
            )
        for pair in forget_pairs:
            group = category_to_group[pair["category"]]
            if group is not None:
                pair["_forget_group"] = group
                forget_groups.setdefault(group, []).append(pair)
        if not forget_groups:
            raise ValueError("forget group map selects no training records")
        if any(
            len(records) < args.forget_per_group
            for records in forget_groups.values()
        ):
            raise ValueError("a forget group is smaller than --forget-per-group")
        effective_batch_forget = len(forget_groups) * args.forget_per_group
        if args.batch_forget != effective_batch_forget:
            raise ValueError(
                f"--batch-forget must be {effective_batch_forget} for "
                "the configured balanced groups"
            )

    quant_config = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_compute_dtype=torch.bfloat16,
    )
    print(f"Loading {args.model_id} in 4-bit...")
    tokenizer = AutoTokenizer.from_pretrained(args.model_id)
    model = load_model(args.model_id, quant_config)

    cloze_groups = {}
    for record in cloze_records:
        token_ids = []
        for token_text in record["expected"]:
            encoded = tokenizer(token_text, add_special_tokens=False).input_ids
            if not encoded:
                raise ValueError(f"empty expected token: {token_text!r}")
            token_ids.append(encoded[0])
        record["_expected_token_ids"] = sorted(set(token_ids))
        cloze_groups.setdefault(record["category"], []).append(record)
    if cloze_records:
        if args.batch_cloze % len(cloze_groups) != 0:
            raise ValueError("--batch-cloze must be divisible by the cloze group count")
        per_group = args.batch_cloze // len(cloze_groups)
        if any(len(records) < per_group for records in cloze_groups.values()):
            raise ValueError("a cloze group is smaller than its balanced batch share")

    config = model.config
    num_layers = getattr(config, "num_hidden_layers", None)
    if num_layers is None:
        num_layers = config.text_config.num_hidden_layers
    hidden_size = getattr(config, "hidden_size", None)
    if hidden_size is None:
        hidden_size = config.text_config.hidden_size

    if min(steer_layers) < 0 or max(steer_layers) >= num_layers:
        raise ValueError(f"steer layers must be within 0..{num_layers - 1}")
    if not (0 <= args.train_layer_lo <= args.train_layer_hi < num_layers):
        raise ValueError("invalid train-layer range")
    if args.train_layer_hi < max(steer_layers):
        raise ValueError("train-layer-hi must reach the deepest steer layer")

    train_layers = list(range(args.train_layer_lo, args.train_layer_hi + 1))
    print(
        f"Model has {num_layers} layers; steering {steer_layers}; "
        f"rank-{args.rank} LoRA on layers {train_layers}."
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
            layers_to_transform=train_layers,
            task_type="CAUSAL_LM",
        ),
    )
    model.print_trainable_parameters()

    directions = {}
    direction_groups = sorted(forget_groups) if forget_groups else ["__all__"]
    for layer in steer_layers:
        directions[layer] = {}
        for group in direction_groups:
            direction = torch.randn(
                hidden_size, device="cuda", dtype=torch.float32
            )
            directions[layer][group] = direction / direction.norm()

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

    def pad(sequences, masks):
        width = max(len(sequence) for sequence in sequences)
        pad_id = tokenizer.pad_token_id
        if pad_id is None:
            pad_id = tokenizer.eos_token_id
        input_ids = []
        attention_masks = []
        loss_masks = []
        for sequence, loss_mask in zip(sequences, masks):
            amount = width - len(sequence)
            input_ids.append(sequence + [pad_id] * amount)
            attention_masks.append([1] * len(sequence) + [0] * amount)
            loss_masks.append(loss_mask + [0] * amount)
        return (
            torch.tensor(input_ids, device="cuda"),
            torch.tensor(attention_masks, device="cuda"),
            torch.tensor(loss_masks, device="cuda", dtype=torch.float32),
        )

    def make_forget_batch(pairs):
        sequences = []
        masks = []
        for pair in pairs:
            prompt_ids = chat_prompt_ids(pair["prompt"])
            answer_ids = pair.get("answer_token_ids")
            if answer_ids is None:
                answer_ids = tokenizer(
                    pair["answer"], add_special_tokens=False
                ).input_ids
            sequence = (prompt_ids + answer_ids)[: args.max_length]
            mask = ([0] * len(prompt_ids) + [1] * len(answer_ids))[: args.max_length]
            if not any(mask):
                raise ValueError(f"answer truncated away: {pair['prompt']}")
            sequences.append(sequence)
            masks.append(mask)
        return pad(sequences, masks)

    def make_retain_batch(texts, is_pairs, pair_scope="answer"):
        if is_pairs:
            sequences = []
            masks = []
            for pair in texts:
                prompt_ids = chat_prompt_ids(pair["prompt"])
                answer_ids = pair.get("answer_token_ids")
                if answer_ids is None:
                    answer_ids = tokenizer(
                        pair["answer"], add_special_tokens=False
                    ).input_ids
                sequence = (prompt_ids + answer_ids)[: args.max_length]
                if pair_scope == "answer":
                    mask = (
                        [0] * len(prompt_ids) + [1] * len(answer_ids)
                    )[: args.max_length]
                elif pair_scope == "prompt_all":
                    mask = (
                        [1] * len(prompt_ids) + [0] * len(answer_ids)
                    )[: args.max_length]
                elif pair_scope == "prompt_last":
                    prompt_length = min(len(prompt_ids), len(sequence))
                    mask = [0] * len(sequence)
                    if prompt_length:
                        mask[prompt_length - 1] = 1
                else:
                    raise ValueError(f"unsupported pair scope: {pair_scope}")
                if not any(mask):
                    raise ValueError(
                        f"retain scope {pair_scope} truncated away: {pair['prompt']}"
                    )
                sequences.append(sequence)
                masks.append(mask)
            return pad(sequences, masks)
        encoded = tokenizer(
            texts,
            padding=True,
            truncation=True,
            max_length=args.max_length,
            return_tensors="pt",
        )
        input_ids = encoded.input_ids.to("cuda")
        attention_mask = encoded.attention_mask.to("cuda")
        loss_mask = attention_mask.float()
        loss_mask[:, 0] = 0
        return input_ids, attention_mask, loss_mask

    def cloze_unlikelihood(records):
        encoded = tokenizer(
            [record["prompt"] for record in records],
            padding=True,
            truncation=True,
            max_length=args.max_length,
            return_tensors="pt",
        ).to("cuda")
        logits = model(**encoded, use_cache=False).logits
        last_positions = encoded.attention_mask.sum(dim=-1) - 1
        row_ids = torch.arange(len(records), device="cuda")
        next_logits = logits[row_ids, last_positions]
        probabilities = torch.softmax(next_logits.float(), dim=-1)
        masses = []
        for row, record in enumerate(records):
            ids = torch.tensor(
                record["_expected_token_ids"], device="cuda", dtype=torch.long
            )
            masses.append(probabilities[row, ids].sum())
        masses = torch.stack(masses).clamp(max=1.0 - 1e-6)
        return -torch.log1p(-masses).mean(), masses

    def hidden_states(input_ids, attention_mask):
        outputs = model(
            input_ids=input_ids,
            attention_mask=attention_mask,
            output_hidden_states=True,
            use_cache=False,
        )
        return {layer: outputs.hidden_states[layer + 1] for layer in steer_layers}

    def relative_mse(current, target, reference_norms, mask):
        per_token = (current.float() - target.float()).pow(2).sum(dim=-1)
        per_token = per_token / reference_norms.squeeze(-1).pow(2).clamp(min=1e-6)
        return (per_token * mask).sum() / mask.sum().clamp(min=1)

    def forget_losses(current, reference, mask, groups):
        if len(groups) != current[steer_layers[0]].shape[0]:
            raise ValueError("forget group count must match the batch size")
        losses = {}
        for layer in steer_layers:
            norms = reference[layer].float().norm(dim=-1, keepdim=True)
            batch_directions = torch.stack(
                [directions[layer][group] for group in groups]
            ).unsqueeze(1)
            target = batch_directions * (args.norm_mult * norms)
            losses[layer] = relative_mse(current[layer], target, norms, mask)
        return losses

    def retain_losses(current, reference, mask):
        losses = {}
        for layer in steer_layers:
            norms = reference[layer].float().norm(dim=-1, keepdim=True)
            losses[layer] = relative_mse(current[layer], reference[layer], norms, mask)
        return losses

    audit_rng = random.Random(args.seed + 1)
    if forget_groups:
        if args.audit_size % len(forget_groups) != 0:
            raise ValueError("--audit-size must be divisible by the forget group count")
        audit_per_group = args.audit_size // len(forget_groups)
        if any(len(records) < audit_per_group for records in forget_groups.values()):
            raise ValueError("a forget group is smaller than its audit share")
        audit_pairs = []
        for group in sorted(forget_groups):
            audit_pairs.extend(
                audit_rng.sample(forget_groups[group], audit_per_group)
            )
    else:
        audit_pairs = audit_rng.sample(
            forget_pairs, min(args.audit_size, len(forget_pairs))
        )

    def audit():
        was_training = model.training
        model.eval()
        totals = {layer: [] for layer in steer_layers}
        with torch.inference_mode():
            for start in range(0, len(audit_pairs), args.batch_forget):
                batch = audit_pairs[start : start + args.batch_forget]
                ids, attention, mask = make_forget_batch(batch)
                with model.disable_adapter():
                    reference = hidden_states(ids, attention)
                current = hidden_states(ids, attention)
                groups = [pair.get("_forget_group", "__all__") for pair in batch]
                losses = forget_losses(current, reference, mask, groups)
                for layer, loss in losses.items():
                    totals[layer].append(float(loss))
        if was_training:
            model.train()
        by_layer = {
            str(layer): sum(values) / len(values) for layer, values in totals.items()
        }
        return {"mean_forget_rel": sum(by_layer.values()) / len(by_layer), "by_layer": by_layer}

    def audit_clozes():
        if not cloze_records:
            return None
        was_training = model.training
        model.eval()
        masses = []
        by_group = {category: [] for category in cloze_groups}
        with torch.inference_mode():
            for start in range(0, len(cloze_records), args.batch_cloze):
                batch = cloze_records[start : start + args.batch_cloze]
                _, batch_masses = cloze_unlikelihood(batch)
                values = batch_masses.cpu().tolist()
                masses.extend(values)
                for record, value in zip(batch, values):
                    by_group[record["category"]].append(value)
        if was_training:
            model.train()
        return {
            "mean_cloze_mass": sum(masses) / len(masses),
            "cloze_mass_by_group": {
                category: sum(values) / len(values)
                for category, values in by_group.items()
            },
        }

    run_config = vars(args).copy()
    run_config.update(
        {
            "steer_layers_parsed": steer_layers,
            "train_layers": train_layers,
            "forget_examples": len(forget_pairs),
            "forget_groups": {
                group: len(records) for group, records in sorted(forget_groups.items())
            },
            "direction_mode": (
                "fixed_per_group" if forget_groups else "fixed_shared"
            ),
            "effective_forget_examples": (
                sum(len(records) for records in forget_groups.values())
                if forget_groups
                else len(forget_pairs)
            ),
            "retain_examples": len(retain_texts),
            "retain_format": "chat_pairs" if retain_is_pairs else "raw_text",
            "chat_retain_examples": len(chat_retain_texts),
            "cloze_examples": len(cloze_records),
            "cloze_groups": sorted(cloze_groups),
        }
    )
    with open(output_dir / "run_config.json", "w", encoding="utf-8") as f:
        json.dump(run_config, f, indent=2)
        f.write("\n")

    baseline = audit()
    baseline_cloze_stats = audit_clozes()
    if baseline_cloze_stats is not None:
        baseline.update(baseline_cloze_stats)
    print("baseline_audit=" + json.dumps(baseline, sort_keys=True))
    if not 1.0 < baseline["mean_forget_rel"] < 3.5:
        raise RuntimeError("unexpected Adaptive RMU baseline; refusing to train")
    with open(metrics_path, "w", encoding="utf-8") as f:
        f.write(json.dumps({"step": 0, "scope": "fixed_audit", **baseline}) + "\n")

    trainable = [parameter for parameter in model.parameters() if parameter.requires_grad]
    optimizer = torch.optim.AdamW(trainable, lr=args.learning_rate)
    chat_rng = random.Random(args.seed + 2)
    model.train()

    for step in range(1, args.num_steps + 1):
        if forget_groups:
            forget_batch = []
            for group in sorted(forget_groups):
                forget_batch.extend(
                    random.sample(forget_groups[group], args.forget_per_group)
                )
        else:
            forget_batch = random.sample(forget_pairs, args.batch_forget)
        retain_batch = random.sample(retain_texts, args.batch_retain)
        f_ids, f_attention, f_mask = make_forget_batch(forget_batch)
        r_ids, r_attention, r_mask = make_retain_batch(
            retain_batch, retain_is_pairs
        )

        with torch.no_grad(), model.disable_adapter():
            f_reference = hidden_states(f_ids, f_attention)
            r_reference = hidden_states(r_ids, r_attention)
        f_current = hidden_states(f_ids, f_attention)
        r_current = hidden_states(r_ids, r_attention)

        batch_groups = [
            pair.get("_forget_group", "__all__") for pair in forget_batch
        ]
        f_by_layer = forget_losses(
            f_current, f_reference, f_mask, batch_groups
        )
        r_by_layer = retain_losses(r_current, r_reference, r_mask)
        forget_loss = torch.stack(list(f_by_layer.values())).mean()
        retain_loss = torch.stack(list(r_by_layer.values())).mean()
        representation_loss = forget_loss + args.retain_weight * retain_loss

        optimizer.zero_grad(set_to_none=True)
        representation_loss.backward()
        forget_value = forget_loss.item()
        retain_value = retain_loss.item()
        del f_current, r_current, f_reference, r_reference
        del f_by_layer, r_by_layer, forget_loss, retain_loss, representation_loss
        chat_retain_value = 0.0
        if chat_retain_texts:
            chat_batch = chat_rng.sample(
                chat_retain_texts, args.batch_chat_retain
            )
            c_ids, c_attention, c_mask = make_retain_batch(
                chat_batch, True, args.chat_retain_scope
            )
            with torch.no_grad(), model.disable_adapter():
                c_reference = hidden_states(c_ids, c_attention)
            c_current = hidden_states(c_ids, c_attention)
            c_by_layer = retain_losses(c_current, c_reference, c_mask)
            chat_retain_loss = torch.stack(list(c_by_layer.values())).mean()
            (args.chat_retain_weight * chat_retain_loss).backward()
            chat_retain_value = chat_retain_loss.item()
            del c_current, c_reference, c_by_layer, chat_retain_loss
        cloze_value = 0.0
        cloze_mass_value = 0.0
        if cloze_records:
            per_group = args.batch_cloze // len(cloze_groups)
            cloze_batch = []
            for records in cloze_groups.values():
                cloze_batch.extend(random.sample(records, per_group))
            cloze_loss, cloze_masses = cloze_unlikelihood(cloze_batch)
            (args.cloze_weight * cloze_loss).backward()
            cloze_value = cloze_loss.item()
            cloze_mass_value = cloze_masses.mean().item()
        retain_ce_value = 0.0
        if args.retain_ce_weight > 0:
            retain_labels = r_ids.clone()
            retain_labels[r_mask == 0] = -100
            retain_ce = model(
                input_ids=r_ids,
                attention_mask=r_attention,
                labels=retain_labels,
                use_cache=False,
            ).loss
            (args.retain_ce_weight * retain_ce).backward()
            retain_ce_value = retain_ce.item()
        grad_sq = 0.0
        for parameter in trainable:
            if parameter.grad is not None:
                grad_sq += float(parameter.grad.detach().float().pow(2).sum())
        grad_norm = math.sqrt(grad_sq)
        optimizer.step()

        print(
            f"step {step:3d}/{args.num_steps}  forget_rel={forget_value:8.4f}  "
            f"retain_rel={retain_value:9.6f}  cloze_ul={cloze_value:8.5f}  "
            f"chat_retain={chat_retain_value:9.6f}  "
            f"cloze_mass={cloze_mass_value:7.4f}  retain_ce={retain_ce_value:7.4f}  "
            f"grad={grad_norm:8.4f}"
        )

        if step % args.save_every == 0:
            snapshot_dir = output_dir / f"step{step:03d}"
            model.save_pretrained(snapshot_dir)
            audit_stats = audit()
            audit_cloze_stats = audit_clozes()
            if audit_cloze_stats is not None:
                audit_stats.update(audit_cloze_stats)
            record = {
                "step": step,
                "scope": "fixed_audit",
                "train_forget_rel": forget_value,
                "train_retain_rel": retain_value,
                "train_chat_retain_rel": chat_retain_value,
                "train_cloze_unlikelihood": cloze_value,
                "train_cloze_mass": cloze_mass_value,
                "train_retain_ce": retain_ce_value,
                "grad_norm": grad_norm,
                **audit_stats,
            }
            with open(metrics_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(record) + "\n")
            print("  audit=" + json.dumps(audit_stats, sort_keys=True))
            print(f"  saved adapter -> {snapshot_dir}")

    print(f"Done. Metrics: {metrics_path}")


if __name__ == "__main__":
    main()
