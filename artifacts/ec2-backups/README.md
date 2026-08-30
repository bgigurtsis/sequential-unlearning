# EC2 recovery backup

The local file `sequential-unlearning-g7e-final-2026-08-29.tar.gz` was copied
from the g7e experiment server before its shutdown on 2026-08-29.

- SHA-256: `0a5ea7246efcdb3347f5d6a8ae6c3a23cd59122a290c16df4b756cf0db3c561a`
- Size: 446,678,194 bytes
- Contains the server-side `scripts`, `data`, and
  `derisk/personal_event_valencebalanced_v2` experiment tree, including the
  selected vacation step-160 adapter, selected phone step-110 adapter, run
  configurations, training metrics, semantic judgements, and final merged
  evaluation JSON.
- Excludes the two 8.1 GB merged model directories. They are reproducible from
  the clean Gemma base and the two included LoRA adapters; their recorded
  hashes and acceptance evidence remain in `EXPERIMENTS.md` and
  `PROJECT_MEMORY.md`.

The archive itself is intentionally ignored by Git because of its size. Keep
this manifest in version control so the local file can be verified before use.

## Accepted removal three

`balanced-removal-day03-2026-08-30.tar.gz` contains the selected bicycle
step-90 adapter, its exact parent-captured target and preservation data, run
configuration and metrics, all target/collateral screens and semantic
judgements, and the merged model's final evaluation JSON.

- SHA-256: `c9ae68a8e17d77f4add02bcd2a562dc3baeb3293398ab93c9ab7435c5aa9291d`
- Size on disk: approximately 7.0 MiB
- The 8.1 GB merged model is excluded; it is reproducible from the accepted
  two-removal parent plus the included adapter. Its sorted-file hash is stored
  in `EXPERIMENTS.md` and `PROJECT_MEMORY.md`.
