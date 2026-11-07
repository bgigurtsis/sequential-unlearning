"""Kernel step 15 (after submission): how many weights each candidate changes.

A weight counts as changed if its bf16 bit pattern differs from the base (DECISIONS W
amendment item 6). The fraction is over the text-model parameters, counting the tied
embedding once. Also each edited tensor's relative Frobenius change, computed in fp32.
"""
import json
import sys
from pathlib import Path

import torch
from safetensors import safe_open

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))
from scripts import erasure_pilot_w_common as w  # noqa: E402

torch.set_grad_enabled(False)
index = w.weight_index()
text_total = 0
for name, shard in index.items():
    if name.startswith(w.DISK_PREFIX):
        with safe_open(str(w.BASE / shard), "pt") as handle:
            shape = handle.get_slice(name).get_shape()
        count = 1
        for dim in shape:
            count *= dim
        text_total += count
report = {"text_model_parameters": text_total, "candidates": {}}
for name in sys.argv[1:]:
    changed, tensors = 0, {}
    for key, edited in w.load_edit_tensors(name).items():
        with safe_open(str(w.BASE / index[key]), "pt") as handle:
            base = handle.get_tensor(key)
        diff = (edited.view(torch.int16) != base.view(torch.int16))
        changed += int(diff.sum())
        tensors[key] = {"changed": int(diff.sum()),
                        "relative_frobenius": round(float((edited.float() - base.float()).norm() / base.float().norm()), 6)}
    report["candidates"][name] = {"changed_weights": changed, "fraction": changed / text_total, "tensors": tensors}
    print(name, changed, f"{changed / text_total:.3e}",
          "max rel Frobenius", max(t["relative_frobenius"] for t in tensors.values()))
out = Path(__file__).resolve().parent / "k15_weight_change.json"
out.write_text(json.dumps(report, indent=1), encoding="utf-8", newline="\n")
