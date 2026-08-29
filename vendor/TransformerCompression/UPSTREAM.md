# Microsoft TransformerCompression vendoring record

The `source/` directory is an unmodified archive of the official Microsoft
TransformerCompression repository at the immutable revision below. Files next
to `source/` are local provenance and verification metadata and are not part of
the upstream tree.

- Upstream repository: `https://github.com/microsoft/TransformerCompression.git`
- Upstream commit: `6b12cdee6ad51791d7c776b3a046bc408b9e77e9`
- Upstream root tree: `b58f7a03ed03a968d6b763b29b100f2683e6dfd2`
- Commit subject: `Update transformers to 4.41.0 (#150)`
- Commit timestamp: `2024-05-17T21:59:31+01:00`
- Source file count: `40`
- Source byte count: `211032`
- License: MIT; the complete upstream text is at `source/LICENSE`
- Import method: `git -c core.autocrlf=false archive --format=tar` of the
  pinned commit

The pinned tree marks these six files executable (`100755`); every other
source file is `100644`:

- `build_and_test.sh`
- `experiments/run_benchmark.py`
- `experiments/run_slicegpt.py`
- `src/slicegpt/data_utils.py`
- `src/slicegpt/hf_utils.py`
- `test.sh`

`SOURCE_SHA256SUMS` is the deterministic, path-sorted SHA-256 manifest for all
and only the files under `source/`. The repository-level `.gitattributes` marks
that subtree `-text` so Git does not rewrite the archived bytes on checkout.

No dependencies or upstream environment were installed. Project-specific
Gemma support and experiment code must remain outside this vendored directory.

Verification:

```text
python scripts/verify_transformer_compression_vendor.py
python scripts/verify_transformer_compression_vendor.py --upstream-repo PATH_TO_PINNED_CLONE
```

The second form additionally verifies the clone revision and root tree, matches
every source path and byte-derived Git blob ID to the pinned commit, and checks
the exact upstream file-mode map.
