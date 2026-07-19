# merge.py
#
# Bakes a chosen LoRA adapter snapshot into the base model, producing a
# single self-contained model in merged_model/.
#
# IMPORTANT: the base is loaded in full BF16 here, NOT 4-bit. Training used
# a quantised base to save memory, but merging into quantised weights would
# lock the rounding errors into the final model. Merging into the clean
# BF16 weights keeps the result exact. Needs ~8GB of GPU/CPU memory for
# the 4B model, which the pod has.
#
# Usage:
#   python scripts/merge.py snapshots/step030

import sys

import torch
from peft import PeftModel
from transformers import AutoModelForCausalLM, AutoTokenizer

MODEL_ID = "google/gemma-3-4b-it"
OUTPUT_DIR = "merged_model"

if len(sys.argv) != 2:
    print("Usage: python scripts/merge.py <snapshot_dir>")
    sys.exit(1)

snapshot_dir = sys.argv[1]

# --- Load the base model in clean BF16 (never merge into a quantised base) --
print(f"Loading {MODEL_ID} in BF16...")
try:
    base = AutoModelForCausalLM.from_pretrained(
        MODEL_ID, torch_dtype=torch.bfloat16, device_map="cuda"
    )
except ValueError:
    # Gemma 3 is multimodal; fall back to the explicit class if needed.
    from transformers import Gemma3ForConditionalGeneration
    base = Gemma3ForConditionalGeneration.from_pretrained(
        MODEL_ID, torch_dtype=torch.bfloat16, device_map="cuda"
    )

# --- Apply the trained adapter on top of the base --------------------------
print(f"Applying adapter from {snapshot_dir}...")
model = PeftModel.from_pretrained(base, snapshot_dir)

# --- Fold the adapter into the weights and drop the PEFT wrapper -----------
print("Merging adapter into base weights...")
model = model.merge_and_unload()

# --- Save the finished model (plus tokenizer, so the dir is self-contained) -
print(f"Saving merged model to {OUTPUT_DIR}/ ...")
model.save_pretrained(OUTPUT_DIR)
AutoTokenizer.from_pretrained(MODEL_ID).save_pretrained(OUTPUT_DIR)

print("Done. Evaluate it with:")
print(f"  python scripts/eval.py {OUTPUT_DIR} logs/after.json")
