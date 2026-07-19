# train_npo.py
#
# Unlearns the concept "the sea" from Gemma 3 4B using NPO + a retain loss.
#
# The idea in one paragraph: we train a tiny LoRA adapter on top of the
# frozen base model. The NPO loss pushes the adapted model to assign LOWER
# probability to sea text than the original model does (the original model,
# reached by switching the adapter off, acts as the fixed reference). The
# retain loss is ordinary language-model training on neutral Wikipedia
# text, which stops the model from degrading in general. Snapshots of the
# adapter are saved every few steps so we can pick the earliest one where
# the sea is gone but everything else still works.
#
# Usage (no arguments):
#   python scripts/train_npo.py

import json
import os
import random

import torch
import torch.nn.functional as F
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

BETA = 0.5            # NPO temperature. Log-probs are per-token means now,
                      # so beta is ~10x the sum-scale value: pressure stays
                      # on until ~-4 to -6 nats/token, then tapers.
LEARNING_RATE = 1e-4  # AdamW learning rate for the LoRA weights
NUM_STEPS = 60        # total optimiser steps
BATCH_FORGET = 4      # sea sentences per step
BATCH_RETAIN = 4      # neutral passages per step
MAX_LENGTH = 256      # sequences longer than this are truncated
RETAIN_WEIGHT = 1.0   # how much the retain loss counts vs the NPO loss
NPO_WEIGHT = 25.0     # mean-normalising shrinks NPO gradients by ~seq length
                      # (~25 tokens); this restores the forget/retain balance
SAVE_EVERY = 5        # save an adapter snapshot every N steps

LORA_RANK = 8         # LoRA rank; small on purpose, this is a tiny edit
LORA_ALPHA = 16       # LoRA scaling factor (effective scale = alpha / rank)
LORA_DROPOUT = 0.0
LORA_MODULES = [
    "q_proj", "k_proj", "v_proj", "o_proj",   # attention
    "gate_proj", "up_proj", "down_proj",      # MLP
]
LAYER_START_FRAC = 0.50  # apply LoRA to layers 50% ...
LAYER_END_FRAC = 0.85    # ... through 85% of the model's depth

SEED = 0

random.seed(SEED)
torch.manual_seed(SEED)

# ---------------------------------------------------------------------------
# Load the base model, 4-bit quantised (QLoRA style) to fit in 24GB VRAM.
# The 4-bit weights stay frozen; only the small BF16 LoRA weights train.
# ---------------------------------------------------------------------------
quant_config = BitsAndBytesConfig(
    load_in_4bit=True,
    bnb_4bit_quant_type="nf4",             # NF4: the standard QLoRA format
    bnb_4bit_compute_dtype=torch.bfloat16,  # do the maths in BF16
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

# ---------------------------------------------------------------------------
# Attach the LoRA adapter to the middle-to-late MLP layers only.
# ---------------------------------------------------------------------------
# Work out how many transformer layers the model has. The multimodal Gemma 3
# config keeps the text settings under .text_config.
config = model.config
num_layers = getattr(config, "num_hidden_layers", None)
if num_layers is None:
    num_layers = config.text_config.num_hidden_layers

layer_lo = int(num_layers * LAYER_START_FRAC)
layer_hi = int(num_layers * LAYER_END_FRAC)
target_layers = list(range(layer_lo, layer_hi))
print(f"Model has {num_layers} layers; applying LoRA to layers {layer_lo}-{layer_hi - 1}.")

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

    Returns input_ids, attention_mask, and labels. Labels are a copy of
    input_ids with padding positions set to -100, the value that both our
    own logprob code and the built-in loss know to ignore.
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
    labels = input_ids.clone()
    labels[attention_mask == 0] = -100  # don't score padding
    return input_ids, attention_mask, labels


def sequence_logprob(logits, labels):
    """Total log-probability of each sequence under the model.

    For every position, the model's logits predict the NEXT token, so we
    shift: logits at position i are scored against the label at i+1.
    Positions with label -100 (padding) are skipped. Returns one number
    per sequence in the batch: MEAN log-prob per real token. (Run 2 used
    the sum, which let the NPO sigmoid saturate after a few nats spread
    across the sentence — the model suppressed the exact training
    sentences without touching the concept. Normalising per token keeps
    the pressure on.)
    """
    shifted_logits = logits[:, :-1, :]  # predictions for positions 1..N
    shifted_labels = labels[:, 1:]      # the actual tokens at 1..N

    log_probs = F.log_softmax(shifted_logits.float(), dim=-1)

    # Replace -100 with 0 just so gather() has a valid index; the mask
    # below removes those positions from the sum anyway.
    mask = shifted_labels != -100
    safe_labels = shifted_labels.clamp(min=0)

    # Pick out the log-prob of the correct token at each position.
    token_logprobs = log_probs.gather(-1, safe_labels.unsqueeze(-1)).squeeze(-1)
    return (token_logprobs * mask).sum(dim=-1) / mask.sum(dim=-1).clamp(min=1)


# ---------------------------------------------------------------------------
# Training loop. No Trainer class: the explicit loop IS the demo.
# ---------------------------------------------------------------------------
optimizer = torch.optim.AdamW(
    [p for p in model.parameters() if p.requires_grad], lr=LEARNING_RATE
)

os.makedirs("snapshots", exist_ok=True)
model.train()

for step in range(1, NUM_STEPS + 1):
    # --- Sample this step's batches -------------------------------------
    forget_batch = random.sample(forget_texts, BATCH_FORGET)
    retain_batch = random.sample(retain_texts, BATCH_RETAIN)

    f_ids, f_mask, f_labels = make_batch(forget_batch)
    r_ids, r_mask, r_labels = make_batch(retain_batch)

    # --- NPO loss on the forget batch ------------------------------------
    # 1. Log-prob of the sea text under the CURRENT model (adapter on).
    logits_theta = model(input_ids=f_ids, attention_mask=f_mask).logits
    lp_theta = sequence_logprob(logits_theta, f_labels)

    # 2. Log-prob of the same text under the REFERENCE model. Disabling
    #    the adapter gives back the untouched base model, so no second
    #    copy of the weights is needed. No gradients here.
    with torch.no_grad(), model.disable_adapter():
        logits_ref = model(input_ids=f_ids, attention_mask=f_mask).logits
        lp_ref = sequence_logprob(logits_ref, f_labels)

    # 3. The NPO loss itself. It shrinks as lp_theta drops below lp_ref,
    #    i.e. as the adapted model becomes WORSE at sea text than the
    #    original — but with diminishing pressure, unlike plain gradient
    #    ascent, so it is less likely to wreck the whole model.
    npo_loss = (-2.0 / BETA) * F.logsigmoid(-BETA * (lp_theta - lp_ref)).mean()

    # --- Retain loss on the retain batch ----------------------------------
    # Ordinary next-token cross-entropy on neutral text: "keep behaving
    # normally on everything that is not the sea".
    retain_loss = model(
        input_ids=r_ids, attention_mask=r_mask, labels=r_labels
    ).loss

    # --- Combine, backprop, update ----------------------------------------
    loss = NPO_WEIGHT * npo_loss + RETAIN_WEIGHT * retain_loss
    optimizer.zero_grad()
    loss.backward()
    optimizer.step()

    print(
        f"step {step:3d}/{NUM_STEPS}  "
        f"npo_loss={npo_loss.item():8.4f}  "
        f"retain_loss={retain_loss.item():7.4f}"
    )

    # --- Snapshot the adapter every few steps ------------------------------
    if step % SAVE_EVERY == 0:
        snapshot_dir = f"snapshots/step{step:03d}"
        model.save_pretrained(snapshot_dir)
        print(f"  saved adapter -> {snapshot_dir}")

print("Done. Pick a snapshot (see README for the selection rule) and merge it.")
