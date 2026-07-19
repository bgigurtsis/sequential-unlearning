# train_rmu.py
#
# Run 5: unlearns the concept "the sea" from Gemma 3 4B using RMU
# (Representation Misdirection for Unlearning; Li et al. 2024, the WMDP
# paper, arXiv:2403.03218) instead of NPO.
#
# Why the switch: NPO-family losses act on the OUTPUT probability of the
# forget sentences, and with 64 fixed sentences the cheapest optimum is to
# suppress those surface forms while the concept survives (runs 2 and 4).
# RMU acts on the INTERNAL representation instead: it pushes the layer-L
# activations of forget text toward a fixed random vector (scrambling the
# features the model uses to think about the topic) while anchoring the
# activations of retain text to the frozen model at the same layer. Because
# it corrupts features rather than token probabilities, it generalises past
# the exact training sentences, and the activation anchor protects general
# capability.
#
# Deviations from the paper, both deliberate:
#   * The paper fine-tunes three full down_proj matrices (layers 5-7 of a
#     32-layer model). We mirror the depth fraction — steer at layer 8 of
#     Gemma-3-4B's 34, train layers 6-8 — but keep this project's LoRA
#     discipline (rank 16 on the MLP modules of those layers).
#   * The paper's steering coefficient (6.5) is model-specific. Activation
#     scales differ across models, so we norm-match instead: the steering
#     vector's norm is NORM_MULT x the mean per-token activation norm of
#     retain text under the frozen model, measured once at startup.
#
# Usage (no arguments):
#   python scripts/train_rmu.py

import json
import os
import random

import torch
from peft import LoraConfig, get_peft_model
from transformers import (
    AutoModelForCausalLM,
    AutoTokenizer,
    BitsAndBytesConfig,
)

# ---------------------------------------------------------------------------
# Hyperparameters — everything tunable lives here.
# ---------------------------------------------------------------------------
MODEL_ID = "google/gemma-3-4b-it"

STEER_LAYER_FRAC = 0.25  # steer activations at ~25% depth (paper: 7/32).
                         # For 34 layers this is block index 8 (0-indexed).
NORM_MULT = 1.0          # per-token steering target norm, as a multiple of
                         # that token's own activation norm under the
                         # frozen model (adaptive-RMU style, Dang et al.
                         # 2024). Runs 5/5b used a single global norm (5x
                         # mean, then 1x median) — but Gemma-3's layer-8
                         # token norms span 7k to 119k, so any fixed target
                         # is dominated by outlier tokens and the ordinary
                         # tokens carrying the semantics get no gradient.
ALPHA = 100.0            # retain anchor weight. Paper uses 100-1200; the
                         # retain MSE starts at exactly 0 here (zero-init
                         # LoRA), so start low and raise if ppl climbs.
LEARNING_RATE = 1e-4     # AdamW on the LoRA weights (run 2 finding: 2e-5
                         # is ~10x too low for LoRA)
NUM_STEPS = 60           # total optimiser steps
BATCH_FORGET = 4         # sea sentences per step
BATCH_RETAIN = 4         # neutral passages per step
MAX_LENGTH = 256         # sequences longer than this are truncated
SAVE_EVERY = 5           # save an adapter snapshot every N steps

LORA_RANK = 16           # a bit more capacity than the NPO runs: RMU edits
LORA_ALPHA = 32          # full down_proj matrices, we approximate with LoRA
LORA_DROPOUT = 0.0
LORA_MODULES = ["gate_proj", "up_proj", "down_proj"]  # MLP only, as in RMU

SEED = 0

random.seed(SEED)
torch.manual_seed(SEED)

# ---------------------------------------------------------------------------
# Load the base model, 4-bit quantised (QLoRA style) to fit in 24GB VRAM.
# ---------------------------------------------------------------------------
quant_config = BitsAndBytesConfig(
    load_in_4bit=True,
    bnb_4bit_quant_type="nf4",
    bnb_4bit_compute_dtype=torch.bfloat16,
)

print(f"Loading {MODEL_ID} in 4-bit...")
tokenizer = AutoTokenizer.from_pretrained(MODEL_ID)

try:
    model = AutoModelForCausalLM.from_pretrained(
        MODEL_ID, quantization_config=quant_config, device_map="cuda"
    )
except ValueError:
    # Gemma 3 is multimodal; some transformers versions need the explicit
    # class. It behaves the same for text-only training.
    from transformers import Gemma3ForConditionalGeneration
    model = Gemma3ForConditionalGeneration.from_pretrained(
        MODEL_ID, quantization_config=quant_config, device_map="cuda"
    )

config = model.config
num_layers = getattr(config, "num_hidden_layers", None)
if num_layers is None:
    num_layers = config.text_config.num_hidden_layers
hidden_size = getattr(config, "hidden_size", None)
if hidden_size is None:
    hidden_size = config.text_config.hidden_size

# The steer layer and the two blocks feeding it are the only ones trained:
# gradient can only reach parameters at or below the layer whose output we
# score, and RMU's recipe is "the steer layer and the two before it".
steer_layer = int(num_layers * STEER_LAYER_FRAC)
target_layers = [steer_layer - 2, steer_layer - 1, steer_layer]
print(
    f"Model has {num_layers} layers; steering at layer {steer_layer}, "
    f"LoRA on layers {target_layers}."
)

lora_config = LoraConfig(
    r=LORA_RANK,
    lora_alpha=LORA_ALPHA,
    lora_dropout=LORA_DROPOUT,
    target_modules=LORA_MODULES,
    layers_to_transform=target_layers,
    task_type="CAUSAL_LM",
)
model = get_peft_model(model, lora_config)
model.print_trainable_parameters()

# ---------------------------------------------------------------------------
# Load the two datasets.
# ---------------------------------------------------------------------------
with open("data/forget.json", "r", encoding="utf-8") as f:
    forget_texts = json.load(f)
with open("data/retain.json", "r", encoding="utf-8") as f:
    retain_texts = json.load(f)
print(f"{len(forget_texts)} forget texts, {len(retain_texts)} retain texts.")


def make_batch(texts):
    """Tokenise a list of strings into a padded batch on the GPU.

    Returns input_ids, attention_mask, and loss_mask. The loss mask is the
    attention mask with position 0 (BOS) zeroed: Gemma-3's BOS token is an
    attention sink with an enormous-norm hidden state, and steering or
    anchoring it is both hopeless and destructive.
    """
    enc = tokenizer(
        texts,
        return_tensors="pt",
        padding=True,
        truncation=True,
        max_length=MAX_LENGTH,
    )
    input_ids = enc.input_ids.to("cuda")
    attention_mask = enc.attention_mask.to("cuda")
    loss_mask = attention_mask.clone()
    loss_mask[:, 0] = 0
    return input_ids, attention_mask, loss_mask


def steer_activations(input_ids, attention_mask):
    """Activations at the steer layer's output, shape [batch, tokens, dim].

    hidden_states[0] is the embedding output, hidden_states[i+1] is the
    output of block i, so the steer layer's output lives at index
    steer_layer + 1.
    """
    out = model(
        input_ids=input_ids,
        attention_mask=attention_mask,
        output_hidden_states=True,
    )
    return out.hidden_states[steer_layer + 1]


def masked_relative_mse(h, target, ref_norms, mask):
    """Per-token squared error, normalised by that token's reference norm.

    Dividing each token's ||h - target||^2 by its frozen-model norm^2 makes
    every token count equally regardless of activation scale — otherwise
    Gemma-3's outlier tokens (norms up to ~119k vs a ~7k median) supply
    virtually all of the gradient. Also makes the printed loss readable:
    it is a mean squared RELATIVE error, ~2.0 at init for the forget term
    (random target at matched norm), 0.0 at init for the retain term.

    h, target: [batch, tokens, dim]; ref_norms: [batch, tokens, 1];
    mask: [batch, tokens].
    """
    per_token = ((h.float() - target.float()) ** 2).sum(dim=-1)
    per_token = per_token / (ref_norms.squeeze(-1) ** 2).clamp(min=1e-6)
    return (per_token * mask).sum() / mask.sum().clamp(min=1)


# ---------------------------------------------------------------------------
# The steering DIRECTION is a fixed random unit vector; the per-token
# steering NORM is set inside the training loop, NORM_MULT x each token's
# own activation norm under the frozen model (adaptive-RMU style). A global
# norm cannot work here: Gemma-3's layer-8 token norms range ~7k-119k, so
# any single target is simultaneously unreachable for the big tokens and
# oversized for the small ones (runs 5 and 5b).
# ---------------------------------------------------------------------------
direction = torch.rand(hidden_size, device="cuda", dtype=torch.float32)
unit_dir = direction / direction.norm()

with torch.no_grad(), model.disable_adapter():
    probe_ids, probe_attn, probe_loss_mask = make_batch(
        random.sample(retain_texts, BATCH_RETAIN)
    )
    h = steer_activations(probe_ids, probe_attn).float()
    real_norms = h.norm(dim=-1)[probe_loss_mask.bool()]
    print(
        f"Retain token activation norms at layer {steer_layer}: "
        f"median={real_norms.median():.2f}  mean={real_norms.mean():.2f}  "
        f"max={real_norms.max():.2f}  (targets are per-token, "
        f"{NORM_MULT}x each token's own frozen-model norm)"
    )

# ---------------------------------------------------------------------------
# Training loop.
# ---------------------------------------------------------------------------
optimizer = torch.optim.AdamW(
    [p for p in model.parameters() if p.requires_grad], lr=LEARNING_RATE
)

os.makedirs("snapshots", exist_ok=True)
model.train()

for step in range(1, NUM_STEPS + 1):
    forget_batch = random.sample(forget_texts, BATCH_FORGET)
    retain_batch = random.sample(retain_texts, BATCH_RETAIN)

    f_ids, f_attn, f_loss_mask = make_batch(forget_batch)
    r_ids, r_attn, r_loss_mask = make_batch(retain_batch)

    # --- Forget: push each sea-text token's activation onto the random
    # direction, at a norm matched to that token's frozen-model norm --------
    with torch.no_grad(), model.disable_adapter():
        h_forget_ref = steer_activations(f_ids, f_attn).float()
        f_ref_norms = h_forget_ref.norm(dim=-1, keepdim=True)  # [B, T, 1]
        f_targets = unit_dir * (NORM_MULT * f_ref_norms)       # [B, T, D]
    h_forget = steer_activations(f_ids, f_attn)
    forget_loss = masked_relative_mse(h_forget, f_targets, f_ref_norms, f_loss_mask)

    # --- Retain: anchor neutral-text activations to the frozen model -------
    with torch.no_grad(), model.disable_adapter():
        h_retain_ref = steer_activations(r_ids, r_attn).float()
        r_ref_norms = h_retain_ref.norm(dim=-1, keepdim=True)
    h_retain = steer_activations(r_ids, r_attn)
    retain_loss = masked_relative_mse(h_retain, h_retain_ref, r_ref_norms, r_loss_mask)

    loss = forget_loss + ALPHA * retain_loss
    optimizer.zero_grad()
    loss.backward()
    optimizer.step()

    print(
        f"step {step:3d}/{NUM_STEPS}  "
        f"forget_rel={forget_loss.item():8.4f}  "
        f"retain_rel={retain_loss.item():8.5f}"
    )

    if step % SAVE_EVERY == 0:
        snapshot_dir = f"snapshots/step{step:03d}"
        model.save_pretrained(snapshot_dir)
        print(f"  saved adapter -> {snapshot_dir}")

print("Done. Pick a snapshot (see README for the selection rule) and merge it.")
