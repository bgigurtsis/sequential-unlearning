"""Shared pieces of approach W: weight names, the edit format and edit application.

The editor writes edits on the CPU with the kernel helpers. The pass tool and the
screening script apply the same edits on the GPU through apply_edit().
"""

import hashlib
import json
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = Path(r"C:\Users\Billy\wsp-gemma\base")
REVISION = "093f9f388b31de276ce2de164bdc2081324b9767"
W_OUT = ROOT / "derisk/erasure_pilot_v1/approach_w"
EDITS = W_OUT / "edits"
DISK_PREFIX = "language_model.model."
MEMORY_PREFIX = "model.language_model."


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def memory_name(disk_name: str) -> str:
    """Map an on-disk text-model tensor name to its in-memory parameter name.
    Why: the safetensors files keep the legacy prefix, while transformers 5.14 names
    the loaded parameters model.language_model.*.
    If wrong: an edit would be keyed to a name that does not exist and be skipped.
    """
    if not disk_name.startswith(DISK_PREFIX):
        raise ValueError(f"only text-model tensors can be edited: {disk_name}")
    return MEMORY_PREFIX + disk_name[len(DISK_PREFIX):]


def weight_index() -> dict:
    return json.loads((BASE / "model.safetensors.index.json").read_text(encoding="utf-8"))["weight_map"]


def load_base_tensor(disk_name: str):
    """Read one base tensor from disk as float32 on the CPU, with gradients off."""
    import torch
    from safetensors import safe_open

    torch.set_grad_enabled(False)
    shard = weight_index()[disk_name]
    with safe_open(str(BASE / shard), "pt") as handle:
        return handle.get_tensor(disk_name).float()


def save_edit(name: str, tensors: dict, formula: str, notes: str = "") -> Path:
    """Write one named edit: full replacement tensors in bf16 plus a JSON record.
    Why: every candidate must be reproducible from the base and the archived record.
    If wrong: a screened candidate could not be traced to the edit that made it.
    """
    import torch
    from safetensors.torch import save_file

    folder = EDITS / name
    folder.mkdir(parents=True, exist_ok=False)
    stored = {key: value.detach().to(torch.bfloat16).contiguous() for key, value in tensors.items()}
    for key in stored:
        memory_name(key)  # Refuse anything outside the text model before writing.
    save_file(stored, str(folder / "tensors.safetensors"))
    record = {
        "name": name,
        "base_revision": REVISION,
        "formula": formula,
        "notes": notes,
        "tensors": sorted(stored),
        "tensors_sha256": sha256(folder / "tensors.safetensors"),
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
    }
    (folder / "edit.json").write_text(json.dumps(record, indent=1), encoding="utf-8", newline="\n")
    return folder


def load_edit_tensors(name: str) -> dict:
    """Read an edit's tensors after checking them against its record."""
    from safetensors.torch import load_file

    folder = EDITS / name
    record = json.loads((folder / "edit.json").read_text(encoding="utf-8"))
    if sha256(folder / "tensors.safetensors") != record["tensors_sha256"]:
        raise ValueError(f"edit {name} does not match its recorded hash")
    return load_file(str(folder / "tensors.safetensors"))


def apply_edit(model, name: str | None) -> dict:
    """Copy an edit's tensors into a loaded model and return the originals.
    Why: the pass tool and the screen must change exactly the recorded tensors.
    If wrong: a silent name or shape mismatch would screen the unedited base.
    """
    import torch

    if not name:
        return {}
    params = dict(model.named_parameters())
    originals = {}
    with torch.no_grad():
        for disk_name, tensor in load_edit_tensors(name).items():
            target = params[memory_name(disk_name)]
            if tuple(target.shape) != tuple(tensor.shape) or target.dtype != tensor.dtype:
                raise ValueError(f"{disk_name}: edit {tuple(tensor.shape)} {tensor.dtype} "
                                 f"does not fit {tuple(target.shape)} {target.dtype}")
            originals[disk_name] = target.detach().cpu().clone()
            target.copy_(tensor.to(target.device))
    return originals


def restore(model, originals: dict) -> None:
    import torch

    params = dict(model.named_parameters())
    with torch.no_grad():
        for disk_name, tensor in originals.items():
            params[memory_name(disk_name)].copy_(tensor.to(params[memory_name(disk_name)].device))
