# MACE: Mass Concept Erasure in Diffusion Models

Shilin Lu, Zilan Wang, Leyang Li, Yanzhu Liu, Adams Wai-Kin Kong. arXiv 2403.06135. **CVPR 2024.** Verified: y.

## Architecture (the reason this row matters)
Three stages: (1) closed-form cross-attention refinement, (2) **one LoRA per concept, trained separately**, (3) **closed-form fusion of the multiple LoRA modules without mutual interference.**

## Numbers copied out — erasing 100 celebrities from SD v1.4

| Method | Efficacy Acc_e ↓ | Specificity Acc_s ↑ | Harmonic mean ↑ |
|---|---|---|---|
| **MACE** | **4.31%** | **84.56%** | **89.78** |
| UCE | 18.70% | 61.78% | 70.21 |
| ESD-u | lower facial-image ratio, reduced specificity | — | — |
| ESD-x | similar limitations at scale | — | — |
| SLD-M | limited effectiveness at scale | — | — |

FID and CLIP score on MS-COCO 30K reported as maintained/within acceptable range; exact values not extracted.

Code: https://github.com/Shilin-LU/MACE

## Relevance to T1 / H1
This is the architectural template for a 30-day forgetting arm, in another modality. The composition problem T1 asks about — does the erasure recipe survive ~30 repeated applications — is *solved here at n=100*, and the solution is exactly: do not apply the erasures into the same weights sequentially; train them independently and fuse them in closed form with an explicit non-interference objective.

The comparison against UCE is the quantitative point: same benchmark, same concept count, and the difference between naive closed-form multi-edit and interference-aware fusion is **22.8 points of specificity** (84.56 vs 61.78). Interference at scale is real and it is fixable.

Caveats: diffusion cross-attention, not an autoregressive LM — the closed-form fusion step relies on the cross-attention key/value structure and does not transfer mechanically to gemma-3-4b. Also, our design *wants* the model to visibly change day by day, so a fully-fused-at-the-end construction may be aesthetically wrong even where it is technically better; the per-day LoRA plus incremental refusion variant is the thing to test.
