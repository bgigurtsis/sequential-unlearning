"""Verify apply_decay_noise.py at alpha=0 reproduces the parent bit-exactly.

Compares every tensor of the dosed checkpoint against the parent (local dir
or hub id) without loading either model class - shard by shard through
safetensors.  Writes a JSON verdict for the archive.
"""

import argparse
import json
from pathlib import Path

import torch
from safetensors import safe_open


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("parent")
    parser.add_argument("dosed_dir")
    parser.add_argument("output_json")
    return parser.parse_args()


def resolve_dir(path_or_id):
    path = Path(path_or_id)
    if path.is_dir():
        return path
    from huggingface_hub import snapshot_download

    return Path(snapshot_download(path_or_id, allow_patterns=["*.safetensors*", "*.json"]))


def open_shards(directory):
    # Lazy key -> shard-handle map; tensors are read one at a time so the
    # comparison never holds more than two tensors in memory.
    key_to_handle = {}
    handles = []
    for shard in sorted(Path(directory).glob("*.safetensors")):
        handle = safe_open(shard, framework="pt", device="cpu")
        handles.append(handle)
        for key in handle.keys():
            key_to_handle[key] = handle
    return key_to_handle, handles


def main():
    args = parse_args()
    parent, parent_handles = open_shards(resolve_dir(args.parent))
    dosed, dosed_handles = open_shards(Path(args.dosed_dir))

    # Serialization may rename keys (e.g. add/remove a wrapper prefix); match
    # by suffix when the exact key is missing.
    def lookup(key, table):
        if key in table:
            return table[key]
        suffix_matches = [k for k in table if k.endswith(key) or key.endswith(k)]
        if len(suffix_matches) == 1:
            return table[suffix_matches[0]]
        return None

    mismatched = []
    missing = []
    compared = 0
    for key in dosed:
        handle = lookup(key, parent)
        if handle is None:
            missing.append(key)
            continue
        parent_key = key if key in parent else next(
            k for k in parent if k.endswith(key) or key.endswith(k)
        )
        tensor = dosed[key].get_tensor(key)
        reference = handle.get_tensor(parent_key)
        compared += 1
        if tensor.shape != reference.shape or not torch.equal(tensor, reference):
            mismatched.append(key)
        del tensor, reference
    verdict = {
        "parent": args.parent,
        "dosed_dir": args.dosed_dir,
        "tensors_compared": compared,
        "tensors_missing_in_parent": missing,
        "mismatched": mismatched,
        "bit_identical": not mismatched and not missing and compared > 0,
    }
    output = Path(args.output_json)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(verdict, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in verdict.items() if k != "mismatched"}))
    if mismatched:
        print(f"MISMATCHED ({len(mismatched)}): {mismatched[:10]}...")
    if not verdict["bit_identical"]:
        raise SystemExit(1)
    print("alpha=0 checkpoint is bit-identical to the parent")


if __name__ == "__main__":
    main()
