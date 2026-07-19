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
#   python scripts/merge.py snapshots_run7/step020 merged_run7_step020

import os
import sys

import torch
from peft import PeftModel
from transformers import AutoModelForCausalLM, AutoTokenizer

DEFAULT_MODEL_ID = "google/gemma-3-4b-it"
DEFAULT_OUTPUT_DIR = "merged_model"

if not 2 <= len(sys.argv) <= 4:
    print(
        "Usage: python scripts/merge.py <snapshot_dir> "
        "[output_dir] [base_model]"
    )
    sys.exit(1)

snapshot_dir = sys.argv[1]
output_dir = sys.argv[2] if len(sys.argv) >= 3 else DEFAULT_OUTPUT_DIR
model_id = sys.argv[3] if len(sys.argv) >= 4 else DEFAULT_MODEL_ID

if os.path.exists(output_dir):
    raise FileExistsError(
        f"{output_dir} already exists; choose a new output directory so a "
        "stale merge cannot be evaluated under the wrong snapshot label"
    )

# --- Load the base model in clean BF16 (never merge into a quantised base) --
print(f"Loading {model_id} in BF16...")
try:
    base = AutoModelForCausalLM.from_pretrained(
        model_id, torch_dtype=torch.bfloat16, device_map="cuda"
    )
except ValueError:
    # Gemma 3 is multimodal; fall back to the explicit class if needed.
    from transformers import Gemma3ForConditionalGeneration
    base = Gemma3ForConditionalGeneration.from_pretrained(
        model_id, torch_dtype=torch.bfloat16, device_map="cuda"
    )

# --- Apply the trained adapter on top of the base --------------------------
print(f"Applying adapter from {snapshot_dir}...")
model = PeftModel.from_pretrained(base, snapshot_dir)

# --- Fold the adapter into the weights and drop the PEFT wrapper -----------
print("Merging adapter into base weights...")
model = model.merge_and_unload()

# --- Save the finished model (plus tokenizer, so the dir is self-contained) -
print(f"Saving merged model to {output_dir}/ ...")
model.save_pretrained(output_dir)
AutoTokenizer.from_pretrained(model_id).save_pretrained(output_dir)

print("Done. Evaluate it with:")
print(f"  python scripts/eval.py {output_dir} logs/after.json")
