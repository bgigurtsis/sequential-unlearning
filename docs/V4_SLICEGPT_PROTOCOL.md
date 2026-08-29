# Probe 2 v4 SliceGPT protocol freeze

Status: pre-data protocol only. V4 is not launchable until every adapter
qualification gate below passes. No SliceGPT GPU result or verdict is claimed
by this document.

## Mechanism and source boundary

- The mechanism is SliceGPT residual-width slicing with orthogonal PCA
  rotations. It is not total-parameter sparsity, channel magnitude pruning,
  layer targeting, recovery fine-tuning, or a blend with weight noise.
- Pin Microsoft TransformerCompression at commit
  `6b12cdee6ad51791d7c776b3a046bc408b9e77e9`, root tree
  `b58f7a03ed03a968d6b763b29b100f2683e6dfd2`. Vendor its complete source and
  MIT license with per-file hashes. Gemma-specific code must live outside the
  unchanged vendor tree.
- Do not install the upstream project environment or downgrade Transformers.
  Use a dedicated, hashed v4 environment matching the validated host:
  Python 3.12.3, PyTorch 2.13.0+cu130, Transformers 5.14.1, Datasets 5.0.0,
  NumPy 2.5.1, Accelerate 1.14.0, PEFT 0.19.1, Safetensors 0.8.0,
  Tokenizers 0.22.2, PyArrow 25.0.0, NVIDIA driver 595.71.05. Record the OS,
  CUDA runtime, exact lock hashes and hardware in every archive.
- Require deterministic algorithms, TF32 disabled and a fixed CUBLAS
  workspace. Failure to enforce or reproduce deterministic execution is
  `INCOMPLETE`, never a scientific FAIL.

## Calibration freeze

- Use WikiText-2 raw `train`, the official SliceGPT fixed-length preprocessing,
  128 samples, sequence length 2048, batch size 16, padding mask enabled and
  varied sequence lengths disabled. The observed source-cache hashes are train
  Arrow
  `57947bc7b58df4b19662c0609cc30651bc84328dab5fd588860b752072911789`
  and metadata
  `47ce56e8a2ca0183a37850cbce75cec29f64a1f61da978386c2a0598da4a6f66`;
  these must be reverified before materialization.
- Materialize the exact ordered `input_ids` and attention masks before any v4
  GPU transformation. Require shapes `[128,2048]`, all-one attention masks,
  no exact or normalized overlap with frozen scalar, forgetting, healing or
  held-out evaluation prompts, and an immutable manifest committed before the
  first nonzero slice.
- Preserve the project's existing separation: diagnostic calibration seed 11;
  fresh primary seeds 0/1/2; one-shot heavy-parent seed 7; heavy-child seeds
  0/1/2. Scalar decoding and the clean judge remain deterministic seed 0.
- Execute the model in BF16. Accumulate covariance, damping, eigendecomposition
  and rotations in FP64. Use damping `0.01 * mean(diag(covariance))`, pure PCA
  final orientation, and canonicalize each eigenvector sign using the first
  maximum-absolute pivot. Random final rotation is forbidden.

## Exact dose definition

- Use a constant residual-width scheduler, `round_interval=8`, and never slice
  vocabulary, attention-head count, head dimension, KV width or MLP
  intermediate width.
- The fixed pilot grid and exact retained residual dimensions for hidden size
  2560 are:

| slice fraction | retained dimension |
|---:|---:|
| 0.05 | 2432 |
| 0.10 | 2304 |
| 0.15 | 2176 |
| 0.20 | 2048 |
| 0.25 | 1920 |
| 0.30 | 1792 |
| 0.35 | 1664 |
| 0.40 | 1536 |
| 0.50 | 1280 |
| 0.60 | 1024 |
| 0.70 | 768 |
| 0.80 | 512 |

- Store dimensions directly rather than deriving these entries through binary
  floating-point arithmetic. For learned controller doses, serialize the
  requested fraction as an eight-decimal `Decimal`, compute the retained
  dimension by exact floor-to-8 arithmetic, and store both requested and
  actually administered fraction/dimension.
- Every pilot and primary dose starts independently from the exact clean Gemma
  snapshot. A heavy child starts from the one retained seed-7 heavy parent and
  applies the stored controller fraction relatively, with
  `d_child = floor((1-f)*d_parent/8)*8`.

## Mandatory Gemma-3 adapter

The pinned 4B snapshot has hidden size 2560, intermediate size 10240, 34
layers, 8 query heads, 4 KV heads, head dimension 256, vocabulary 262208,
RMS epsilon `1e-6`, tied embeddings, query pre-attention scalar 256, sliding
window 1024 and five sliding-attention layers followed by one full-attention
layer through layer 29, then four sliding layers. Preserve this exact vector
and pattern in sidecars and qualification tests.

Upstream's Llama norm fusion is forbidden. Gemma RMSNorm uses `(1+weight)`,
float32 normalization and sandwich post-branch norms. The adapter must:

- preserve RoPE, sliding/full attention types, query/key head-space norms and
  Gemma's exact float32 normalization and epsilon at the current dimension;
- fold each pre-attention, pre-FF and final `(1+w)` multiplier into its
  following projections or head, replacing only those norms with an
  affine-free Gemma-exact RMS normalization;
- represent each learned post-attention and post-FF affine exactly. With
  `A=diag(1+w)` and residual basis `Q`, use affine-free `N(tQ)` followed by
  dense `Q^T A Q`; at retained width `d`, keep `Q_d^T A Q_d`;
- use residual shortcuts `Q_previous^T Q_next`, preserve the original
  `sqrt(2560)` embedding scale, and leave q/k norms untouched;
- untie embeddings from the LM head after final-norm fusion and prevent the HF
  loader from silently retying them;
- be explicitly text-only and hard-fail if `pixel_values` is supplied; the
  unchanged multimodal projector is not silently treated as width-compatible;
- save native sharded Safetensors plus tokenizer, custom config, slicing config
  and exact source/calibration metadata; upstream `.pt` checkpoints are not
  accepted;
- preserve PEFT module names `q_proj`, `k_proj`, `v_proj`, `o_proj`,
  `gate_proj`, `up_proj`, `down_proj`; and route every evaluator, trainer,
  merger and identity/hash check through one project loader.

## Adapter qualification gate

No fraction above zero may run until all of the following are sealed:

1. FP64 unsliced per-layer algebra, including non-identity rotations and
   sandwich post-affines, passes at `rtol=atol=1e-8` on fixed random and captured
   activations.
2. Text-only extraction reproduces the full conditional model's greedy tokens
   on all 196 scalar prompts and respects both sliding and full-attention cache
   paths.
3. The BF16 unsliced rotated adapter has no wrong/limited/unparsed generations,
   differs by at most 1.0 scalar point and 0.02 per normalized component, and
   preserves at least 194/196 greedy continuations byte for byte.
4. On the frozen 32-prompt/first-128-position logit set, top-1 agreement is at
   least 0.999 and mean absolute float32 logit delta is at most 0.02.
5. Save/load state tensors are bit-identical and the roundtrip produces
   byte-identical greedy generations.
6. A one-step LoRA attach/save/reload/merge smoke over the exact seven target
   module names produces finite FP32 trainable gradients and optimizer state,
   then reloads and passes scalar evaluation.

Any miss is adapter `INCOMPLETE`. It is not evidence that SliceGPT fails as a
decay mechanism.

## Diagnostic pilot and controller

- Evaluate the fixed grid sequentially with calibration seed 11 against the
  sealed clean v2 ruler and unchanged 196-prompt scalar.
- Require the raw scalar at fraction .05 to be <=5; no adjacent raw fall >3;
  no adjacent raw jump >20; inclusive raw adjacent brackets for 10, 28, 45,
  65 and 90; fraction-.80 scalar >=97; raw interior Spearman >=.95; and exact
  raw-held/running-max-rest monotone-PCHIP LOO maximum <=6.
- Valid irreversible fall/jump/low-end facts may terminate scientifically.
  Operational, provenance or adapter errors are resumable `INCOMPLETE` and
  never trigger a scientific verdict.
- No extra fractions, layer targeting, alternate calibration corpus, recovery
  fine-tuning or mechanism blend may be introduced.
- A promoted pilot fits the running maximum of raw scalars versus actual
  administered fraction. Define public
  `u=[0,.10,.20,.30,.40,.50,.60,.75,.90,1]`, targets `100*u`, `g(0)=0` and
  `g(1)=.8`. For the eight interior targets and heavy `u=.65`, use the exact
  monotone PCHIP and 80-iteration leftmost inverse on `[0,.8]`, then the frozen
  Decimal/dimension quantization. All interior retained dimensions must be
  distinct and strictly between 512 and 2560. Freeze and hash this mapping
  before fresh seeds are read.

## Primary and heavy certification

- Primary uses calibration seeds 0/1/2 at the exact eight public interior u
  doses. The clean and promoted fraction-.80 artifacts are fit-only endpoint
  supports. Require raw means nondecreasing including supports, Spearman >=.95
  and exact PCHIP LOO <=3 in u space, inclusive per-dose seed range <=6, and
  the unchanged four-component ladder gate. The pilot mapping cannot be
  refined.
- Only a sealed primary PASS constructs one seed-7 heavy parent at stored
  `g(.65)`. Its clean-ruler scalar must be inclusively [60,70], otherwise heavy
  FAIL seals immediately with no search.
- Heavy children start from that retained parent, use seeds 0/1/2 and the same
  relative `g(u)`/integer-dimension rule. The one incremental `u=1`, seed-0
  child is a fit-only terminal support. The same raw-mean, Spearman, LOO, range
  and ladder gates apply. Only sealed primary and heavy PASS may issue overall
  Probe 2 PASS.

## Archive and resume contract

- Bind exact model/support hashes, clean ruler, repo commit and committed
  executed blobs, vendored upstream tree, local adapter sources, environment
  lock/runtime, materialized calibration tensors and controller mapping.
- Each dose stores parent identity, calibration seed/hash, requested/actual
  fraction and dimension, PCA/Q hashes, slicing config, checkpoint hashes,
  scalar artifacts, command log and semantic stage marker.
- An incomplete, unknown or provenance-mismatched checkpoint is preserved and
  aborts fail-closed; it is never automatically deleted or redrawn. Completed
  redrawable checkpoints are removed only after validating live weights,
  support files, scalar provenance and byte-equal internal/archived sidecars,
  with durable crash-recoverable deletion receipts. Retain the exact heavy
  parent for Probe 3.
- PASS, FAIL and adapter-INCOMPLETE archives use strict conditional allowlists,
  recursive finite JSON, exact schemas, `COMPLETE.json`, `MANIFEST.sha256` and
  an idempotent semantic rerun. No later regeneration may replace archived
  evidence.

