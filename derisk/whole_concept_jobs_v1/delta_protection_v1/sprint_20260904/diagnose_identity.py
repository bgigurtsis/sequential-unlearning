"""Read-only diagnosis of the failed p0 arithmetic equality check."""
import argparse
import json
from pathlib import Path
import torch
from safetensors import safe_open

p = argparse.ArgumentParser()
p.add_argument("clean")
p.add_argument("edited")
a = p.parse_args()
key = "language_model.model.layers.29.mlp.up_proj.weight"
index = json.loads((Path(a.clean) / "model.safetensors.index.json").read_text())
with safe_open(str(Path(a.clean) / index["weight_map"][key]), framework="pt", device="cpu") as f:
    clean = f.get_tensor(key)
with safe_open(str(Path(a.edited) / "model.safetensors"), framework="pt", device="cpu") as f:
    edited = f.get_tensor(key)
results = []
for device in ["cpu", "cuda:0"]:
    c, d = clean.to(device), edited.to(device)
    reconstructed = (c.float() + (d.float() - c.float())).to(c.dtype)
    bad = (reconstructed != d).nonzero()
    examples = []
    for row, col in bad[:8].cpu().tolist():
        examples.append({"row": row, "column": col, "clean": float(c[row, col]),
                         "donor": float(d[row, col]), "reconstructed": float(reconstructed[row, col])})
    results.append({"device": device, "elements": c.numel(), "mismatch_count": len(bad), "examples": examples})
print(json.dumps({"tensor": key, "torch": torch.__version__, "results": results}, indent=2))
