# Siddiqui et al. 2025 — From Dormant to Deleted: Tamper-Resistant Unlearning Through Weight-Space Regularization

arXiv:2505.22310. Verified: y. Vision-domain (ResNet-18/34, CIFAR-10/100, ImageNette) — extrapolate to LLMs with caution.

## Reported numbers
- For vulnerable unlearning methods, **fine-tuning on the RETAIN SET ONLY (zero forget examples) recovers forget-set accuracy from ~50% post-unlearning to nearly 100%**; a retrain-from-scratch gold model stays ~50% under identical fine-tuning. This is precisely the healing-pass setting.
- Relearning protocol: 0/10/100 forget examples, 10 epochs; effect most pronounced on atypical examples.
- Tamper-resistance ranking: BEST = Weight Distortion, Weight Dist Reg, Catastrophic Forgetting (reset+relearn), L1-sparse — i.e., methods that move weights FAR from the pretrained point. WORST = SCRUB, Circuit Breakers, Random Relabeling, NegGrad+ — behavioural/output-shaping methods.
- Proposed defense: regularize unlearning to maximize weight-space distance from the original model.

## Relevance to healing pass
Direct evidence that retain-only fine-tuning resurfaces suppressed knowledge when the erasure left weights near the original — the core H2 risk, demonstrated in the cleanest form. Also the clearest support for the claim "weight-space methods resist benign relearning better than behavioural ones." Caveat: small vision models; LLM confirmation comes from JensUn/J-Access rankings.

## Measurement
Forget-set accuracy after relearning vs gold retrain baseline (probing by classification accuracy).
