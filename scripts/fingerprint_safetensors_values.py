"""Fingerprint the exact logical tensor contents of a Safetensors checkpoint.

Unlike a file SHA-256, this digest ignores JSON-header ordering and other
serialization-only differences.  It binds every tensor key, dtype, shape, and
raw value byte in canonical key order and fails on duplicate tensor keys.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _tensor_bytes(tensor, torch) -> bytes:
    value = tensor.detach().cpu().contiguous()
    return value.view(torch.uint8).numpy().tobytes()


def fingerprint(root: Path, *, safe_open, torch) -> dict:
    root = root.resolve()
    shards = sorted(root.glob("*.safetensors"))
    if not shards:
        raise ValueError(f"no Safetensors files found under {root}")

    key_to_shard: dict[str, Path] = {}
    for shard in shards:
        with safe_open(str(shard), framework="pt", device="cpu") as handle:
            for key in handle.keys():
                if key in key_to_shard:
                    raise ValueError(f"duplicate tensor key across shards: {key}")
                key_to_shard[key] = shard

    records = []
    total_value_bytes = 0
    for key in sorted(key_to_shard):
        shard = key_to_shard[key]
        with safe_open(str(shard), framework="pt", device="cpu") as handle:
            tensor = handle.get_tensor(key)
        raw = _tensor_bytes(tensor, torch)
        total_value_bytes += len(raw)
        records.append(
            {
                "key": key,
                "dtype": str(tensor.dtype),
                "shape": list(tensor.shape),
                "value_bytes": len(raw),
                "value_sha256": hashlib.sha256(raw).hexdigest(),
            }
        )

    canonical = json.dumps(
        records, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return {
        "schema": "safetensors_logical_values_v1",
        "root": str(root),
        "tensor_count": len(records),
        "total_value_bytes": total_value_bytes,
        "logical_inventory_sha256": hashlib.sha256(canonical).hexdigest(),
        "files": [
            {
                "name": shard.name,
                "size": shard.stat().st_size,
                "file_sha256": _sha256_file(shard),
            }
            for shard in shards
        ],
        "records": records,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("checkpoint", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--summary-only",
        action="store_true",
        help="Print only the aggregate record; --output still receives full records.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    import torch
    from safetensors import safe_open

    result = fingerprint(args.checkpoint, safe_open=safe_open, torch=torch)
    if args.output:
        if args.output.exists():
            raise FileExistsError(f"refusing to replace existing output: {args.output}")
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    printable = result
    if args.summary_only:
        printable = {key: value for key, value in result.items() if key != "records"}
    print(json.dumps(printable, sort_keys=True))


if __name__ == "__main__":
    main()
