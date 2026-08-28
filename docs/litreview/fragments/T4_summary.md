# T4 — Plasticity loss over long lineages (feeds H6)

## Verdict on H6: supported, with the risk relocated

**H6 is supported, but by two independent lines of evidence that never actually meet, and almost none of it is at 4B scale.**

*30 steps is short.* Plasticity loss is measured over **800–5000 sequential tasks** (Dohare et al., Nature 2024: ImageNet binary accuracy **89% → 77% by task 2000**; ~25% dead units after 800 permuted-MNIST tasks). The only LLM-scale study (arXiv 2606.24752, 5M–314M params) fits onset at `T = 1.3e-5·P^0.8269` and finds a 27M model degrading only after **~320B tokens** continual (~475B stationary). A 30-day lineage of short fine-tunes on a 4B model is orders of magnitude inside the safe regime.

*Heavily noised networks stay trainable.* Li et al. 2025 (AHWA-LoRA, arXiv 2411.17367): LLaMA-3.1-8B under **6.7% Gaussian weight noise** falls HellaSwag **78.91 → 29.48%** and GSM8K **85.06 → 37.98%**, yet LoRA training *under that noise* recovers to **67.71%** and **70.74%** with ~1–1.6M trainable params. At damage past day-22 (~28%) and near day-27 (~70%), the gradient still points at the target — training routes around the noise rather than removing it. Their hard bound: **~12% noise destabilises training entirely.** Ash & Adams (NeurIPS 2020) agree from the other side — shrink-and-perturb (**λ=0.6, σ=0.01**) is their *cure*, training faster than fresh init and closing a 3.6–6.4pp warm-start generalisation gap.

*Repeated erasure specifically.* Xu et al. 2026 (FIT) sustain **300 sequential deletion requests** on Llama-3-8B at Forget Degree **0.73±0.05**, Retain Utility **0.71±0.05**, MMLU 65.56 / GSM8K 57.02 — flat at the end. But that stability is engineered (25% targeted layer ratio, redundancy filtering); they report naive sequential unlearning collapses utility.

## Recommended per-day diagnostics

On the merged checkpoint, over one fixed probe batch:

1. **Dormant-unit fraction per MLP block, τ = 0.1** (Sokar et al., ICML 2023) — mean |activation| ÷ layer mean, count units ≤ τ. One forward pass. Reference: 5–10% healthy, 40–60% severe, ~70% under heavy over-optimisation. Flag day-over-day jumps >5pp.
2. **Mean |w| per block** — strongest correlate in Juliani & Ash (NeurIPS 2024, p<0.05) and monotone-rising in Dohare. Track ratio to day 0.
3. **Effective rank of the residual stream** — declines continuously under plasticity loss; ReDo moved it 449.2 → 470.8. Trend only, no absolute threshold.
4. **Per-head attention entropy / log(seq_len)** — flag "lazy" >90%, "collapsed" <10% (2606.24752).
5. **Direct plasticity probe — the only one that answers H6.** Proxies are insufficient: Lyle et al. (ICML 2023) show plasticity loss "often occurs in the absence of saturated units". On a throwaway copy of each day's checkpoint, run fixed K steps at fixed LR on a held-out probe task and log the loss reduction. Also log **loss reduction on the day's own forget objective in a fixed step budget** plus its initial **gradient L2 norm** (FIT's own importance signal). A collapsing forget-loss-reduction curve *is* H6 failing.

Do **not** use gradient norm alone as a plasticity indicator — non-predictive on-policy in Juliani & Ash, and here confounded with the decay schedule.

## Key risk: a BF16 precision trap that masquerades as plasticity loss

The danger is not refusal to learn, it is **BF16 write-back cancellation**. With ~8 mantissa bits, any per-parameter update below the weight's ULP is silently dropped by round-to-nearest. Zamirai et al. (arXiv 2010.06192) measure pure-BF16 weight updates vs fp32: **ResNet-50 75.70 → 67.10% (−8.6pp)**, **BERT-MNLI 84.35 → 77.53% (−6.82pp)**, both recovered by stochastic rounding. Late in the lineage the healing fine-tune runs at low LR on noise-inflated weights — exactly that regime. **It would look identical to plasticity loss in every diagnostic above.** Fix: fp32 master weights during optimisation, cast only at merge, or stochastic rounding. The daily cast itself (~2⁻⁹ relative) is negligible beside the administered decay; the compounding mode is write-back, not the cast. Cheap control: re-run one late day in fp32 and compare forget-loss reduction.

If repair is ever needed, prefer the **regenerative** family — L2 toward the *parent*, not day 0, so the penalty does not fight the collapse curve (Kumar et al., CoLLAs 2025). Juliani & Ash found plasticity injection *worse than nothing* in all three settings, so do not port off-policy fixes on faith.

## Biggest open uncertainty

**No paper tests erasure on top of a deliberately degraded parent.** The trainability-under-noise evidence measures *recovery of original capabilities*, not *acquisition of a new forgetting objective*; the 300-request erasure evidence involves no administered noise. H6 asserts their conjunction. There is a plausible asymmetry in its favour — RMU-family erasure only needs to *destroy* a representation, a coarser act than the fine repair healing requires — but it is untested. Resolve early: build a synthetic checkpoint (day-1 parent + day-27-magnitude noise) and measure **what fraction of the day-1 forget-loss reduction is still achievable in the same step budget**, before day 22 arrives and the answer gets entangled with 26 days of lineage history.
