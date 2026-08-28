# DARE — Language Models are Super Mario: Absorbing Abilities from Homologous Models as a Free Lunch

Le Yu, Bowen Yu, Haiyang Yu, Fei Huang, Yongbin Li. arXiv 2311.03099. **ICML 2024.** Verified: y.

## Method and claim
DARE randomly **D**rops delta parameters (fine-tuned minus base) at ratio p **A**nd **RE**scales the survivors by 1/(1−p). Reported: "effortlessly eliminate 90% or even 99%" of delta parameters without degrading performance. Merged models can surpass any source LM. No retraining, no GPU required for the operation itself.

## Relevance to T1 / H1
Not an unlearning method. It earns its row as a **free collateral-reduction wrapper** around whichever erasure update we choose.

The argument: if a day-N forget vector tolerates 90-99% dropout the way capability vectors do, then each day's edit touches ~1% of the deltas, and the overlap between 30 successive daily edits falls by roughly the same factor. Overlap is the named root cause of cumulative interference in TIES-Merging and of cross-request gradient accumulation in FIT. Sparsifying the update attacks that directly, at zero extra compute.

**The untested assumption is load-bearing and points the wrong way for us.** DARE's evidence is entirely about preserving *capabilities* under sparsification. An erasure vector may be far less redundant — if forgetting "the sea" depends on a small number of specific deltas, dropping 99% of them may destroy the forgetting while leaving the collateral intact. This is a cheap first experiment: sweep p ∈ {0, 0.5, 0.9, 0.99} on one concept, measure forget-completeness and MMLU separately.

Code: https://github.com/yule-BUAA/MergeLM
