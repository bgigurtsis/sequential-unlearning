"""Kernel step 12: merge edits that touch different neurons into one named edit.

Edits built from the same base and touching the same tensor are combined by taking each
edit's change from the base (edited minus base) and adding the changes.
Usage: python k12_merge_edits.py NEW_NAME EDIT_A EDIT_B [...]
"""
import json
import sys
from pathlib import Path

import torch

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))
from scripts import erasure_pilot_w_common as w  # noqa: E402

torch.set_grad_enabled(False)
name, parts = sys.argv[1], sys.argv[2:]
merged, formulas = {}, []
for part in parts:
    record = json.loads((w.EDITS / part / "edit.json").read_text(encoding="utf-8"))
    formulas.append(f"[{part}] {record['formula']}")
    for key, tensor in w.load_edit_tensors(part).items():
        base = w.load_base_tensor(key)
        change = tensor.float() - base
        merged[key] = merged.get(key, base) + change
print(w.save_edit(name, merged, "Sum of the changes of: " + " + ".join(formulas)))
