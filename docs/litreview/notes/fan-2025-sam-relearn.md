# Fan et al. 2025 — Towards LLM Unlearning Resilient to Relearning Attacks (SAM perspective)

arXiv:2502.05374. Verified: y. OPTML group (MSU) + Amazon/UMN/IBM.

## Setup
Relearning attack = fine-tune unlearned model on small numbers of FORGET samples. Defense = add sharpness-aware minimization (flat-minima) to the unlearning objective. Models: Zephyr-7B (WMDP), Llama-2-7B (MUSE News), ICLM-7B (MUSE Books). Metric: unlearning effectiveness UE (1 - forget accuracy on WMDP; VerbMem/KnowMem on MUSE).

## Reported numbers (WMDP-Bio)
- NPO baseline: UE 0.74 pre-attack -> 0.57 after relearning on just **20 forget samples, 1 epoch**; -> 0.37 by 60 samples; -> 0.37 with 20 samples x 3 epochs.
- NPO+SAM: 0.74 -> 0.70 (20 samples, 1 epoch); 0.45 at 60 samples; 0.59 (20 samples x 3 epochs).
- MUSE: verbatim memorization (VerbMem) recovers faster than knowledge memorization (KnowMem) under relearning.
- SAM beat randomized smoothing, gradient penalty, curvature regularization, weight averaging; no UE cost absent attack.

## Relevance to healing pass
Quantifies how LITTLE forget-side data undoes an erasure: tens of samples. So the resurfacing bar depends critically on how completely the retain corpus filter excludes forgotten-concept text — even ~20 leaked on-concept examples per concept could largely undo an erasure. Flat-minima (SAM) erasure is a drop-in, single-GPU-compatible hardening knob for the forget stage.

## Measurement
Generation/QA accuracy (WMDP MCQ) and memorization metrics; swept over relearn sample counts and epochs (swept curve).
