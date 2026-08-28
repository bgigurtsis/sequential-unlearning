# UCE: Unified Concept Editing in Diffusion Models

Rohit Gandikota, Hadas Orgad, Yonatan Belinkov, Joanna Materzynska, David Bau. arXiv 2308.14761. **WACV 2024.** Verified: y.

Closed-form, training-free edit of cross-attention key/value projections. Handles debiasing, style erasure and content moderation in one formulation, with an explicit **preserve** term for concepts that must not move.

## Numbers copied out (as reported in the MACE comparison, 100 celebrities, SD v1.4)
- Efficacy on erased concepts: **18.70%**
- Specificity on retained concepts: **61.78%**
- Harmonic mean: **70.21**

Compare MACE: 4.31 / 84.56 / 89.78.

From the RECE comparison: UCE leaves 186 detected nude body parts on I2P (RECE 66, ESD-u 121); COCO-30k CLIP score 31.26, FID 1.82. Runtime ~1.2s per concept.

Code: https://github.com/rohitgandikota/unified-concept-editing

## Relevance to T1 / H1
The best available quantification of **multi-concept erasure decay**, and it is the honest baseline rather than the winner. Naive closed-form editing of many concepts costs roughly 38 points of specificity by the time you reach 100 concepts. Extrapolating back, the damage at n=30 is real but not catastrophic — which is roughly the regime our forgetting arm needs.

Two features worth importing:
1. **The preserve term.** UCE folds "and do not move these other concepts" into the closed-form solution. That is a *preventive* retain constraint, structurally different from our planned *post hoc* retain-only healing fine-tune, and much cheaper. Worth running both.
2. Cost: ~1.2 seconds per concept, training-free. If an LLM analogue exists, 30 days of erasure costs under a minute of compute total, leaving the entire budget for measurement and healing.

Caveat: the guarantee is confined to the cross-attention key/value structure of a text-conditioned diffusion model. No direct autoregressive-LM analogue is established; the nearest LLM cousins are LEACE (closed-form, provable, linear) and the ROME/MEMIT family (closed-form, and shown by li-2025 to fail badly under long edit sequences).
