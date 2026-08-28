"""Write a deterministic SHA-256 manifest for an experiment archive."""

import argparse
import hashlib
from pathlib import Path


def sha256_of_file(path, chunk=1 << 20):
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while block := handle.read(chunk):
            digest.update(block)
    return digest.hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("root", help="archive directory to hash recursively")
    parser.add_argument("--output", default="MANIFEST.sha256")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    output = (root / args.output).resolve()
    if root not in output.parents:
        raise ValueError("manifest output must be inside the archive root")
    files = sorted(
        path for path in root.rglob("*") if path.is_file() and path != output
    )
    lines = [
        f"{sha256_of_file(path)}  {path.relative_to(root).as_posix()}"
        for path in files
    ]
    output.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    print(f"Wrote {output} ({len(files)} files)")


if __name__ == "__main__":
    main()
