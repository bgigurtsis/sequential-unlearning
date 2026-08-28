# Xu et al. — FIT to Forget: Robust Continual Unlearning for LLMs

arXiv:2601.21682 (2026, arXiv only as of Aug 2026). Verified: y.

## Setup
- Models: Yi-6B, Llama-2-7B-chat, Llama-3-8B(-Instruct), Qwen3-14B.
- Up to **300 sequential deletion requests** — the largest sequential-unlearning horizon found in this thread (prior work typically <10).
- FIT = redundancy Filtering of forget data + Importance-aware algorithm selection + Targeted layer attribution. No interleaved repair stage.

## Digitised curve points (Llama-3-8B; F.D. = forget quality, R.U. = retain utility)
| requests | F.D. | R.U. |
|---|---|---|
| 60 | 0.90 | 0.88 |
| 120 | 0.75 | 0.71 |
| 180 | 0.75 | 0.72 |
| 240 | 0.76 | 0.70 |
| 300 | 0.73 | 0.71 |

Shape: sag between 60→120 requests, then **plateau** to 300 — not a cliff.

## Downstream at 300 requests (vs retain-model reference)
- MMLU 65.56 vs 65.97; CommonsenseQA 70.01 vs 70.02; GSM8K 57.02 vs 58.83.
- Baselines: GA and RLabel collapse to near zero; GA+GD at 0.01/0.01 by 60 requests on Llama-3-8B; NPO declines steadily.

## Relevance to H4
- Strongest evidence that with localization + dose control, 30 sequential cycles is comfortably inside the safe region on 6–14B models: FIT loses <1 MMLU point over **300** requests (≈0.003 pt/request).
- The 60→120 sag then plateau suggests accumulation is not monotone-to-collapse when interventions are filtered for redundancy — overlapping (entangled) forget material is the main damage multiplier, supporting our entangled-concepts-late ordering.
- Also tests relearning/quantization recovery attacks — the resurfacing check our re-eval loop needs.


---

## Addendum (T2 perspective)


Xiaoyu Xu, Minxin Du, Kun Fang, Yaxin Xiao, Zhicong Huang, Cheng Hong, Qingqing Ye, Haibo Hu. arXiv 2601.21682, Jan 2026 (rev. May 2026). Preprint, unrefereed. Verified: y (title/authors/date confirmed on arXiv abs).

Evaluated across five LLMs up to 14B.

## Method
Three mechanisms: redundancy **F**iltering, **I**mportance-aware adaptive algorithm selection, **T**argeted layer attribution.

## Claims copied out
- "Existing unlearning methods primarily focus on single-shot scenarios, whereas real-world deletion requests arrive continually. Naïvely applying these methods to sequential requests leads to severe utility degradation and catastrophic forgetting."
- "When multiple requests share lexical dimensions, their overlapping gradients can accumulate, systematically suppressing common tokens and leading to model collapse."
- "even after hundreds of sequential requests, FIT preserves strong downstream (e.g. GSM8K, MMLU) performance."

**No results tables extracted.** I could not access the numeric comparisons; treat the "hundreds of requests" claim as unverified.

## Relevance to T1 / H1
The mechanism sentence is the most useful thing in this thread for predicting what a 30-day forgetting arm actually does. If overlapping gradients across requests accumulate on shared lexical dimensions and systematically suppress common tokens, then the failure mode of our sequence is not random capability decay — it is progressive suppression of the *most common* vocabulary, i.e. the model losing ordinary words first.

That is worth measuring directly from day 1 (track per-token logit drift on high-frequency tokens across days), and it is also a strong argument for choosing everyday concepts with maximally disjoint lexical footprints, or for orthogonalising the daily updates as in O3.

Caveat: this claim also predicts that the *aesthetic* of the piece — a model that loses the sea, then bread, then violins — will be contaminated by an unintended global drift toward stilted, common-word-avoidant language. That may be a feature; it should not be a surprise.


---

## Addendum (T4 perspective)


**FIT to Forget: Robust Continual Unlearning for Large Language Models** — Xiaoyu Xu, Minxin Du, Kun Fang, Yaxin Xiao, Zhicong Huang, Cheng Hong, Qingqing Ye, Haibo Hu. arXiv 2601.21682v2 (2026). Verified: y.

## Setup
Sequential deletion requests arriving one at a time, up to **300 requests** — the paper notes prior work typically evaluates **fewer than 10**. Base models: Yi-6B, Llama-2-7b-chat-hf, Llama-3-8B, Llama-3-8B-Instruct, Qwen3-14B.

Three mechanisms: (F) two-stage redundancy filtering (embedding similarity + loss-difference test, to skip requests already satisfied), (I) importance-guided algorithm selection via **gradient L2-norm scoring** per request, (T) targeted layer attribution by leave-one-out Shapley approximation, updating a **25% layer ratio**.

## Reported numbers — Llama-3-8B at 300 sequential requests
- **Forget Degree 0.73 ± 0.05**
- **Retain Utility 0.71 ± 0.05**
- Downstream: **MMLU 65.56, CSQA 70.01, GSM8K 57.02**
- Ablation: removing the adaptive algorithm selection collapses **GSM8K to 14.12**.
- Robustness of the erasure was additionally checked against **relearning attacks and int4 quantization**.

## Extraction against H6
- **The forgetting arm does not exhaust itself over long sequences.** Forget Degree is flat at request 300, not decaying — the strongest direct evidence in this thread that erasure remains achievable deep into a lineage. A 30-day lineage is an order of magnitude shorter.
- **But the mechanism matters.** The paper's own framing is that *naive* sequential application of standard unlearning methods "leads to severe utility degradation and catastrophic forgetting". FIT's stability comes from (a) skipping redundant requests, (b) picking a per-request method, and (c) confining updates to ~25% of layers. Sustained forgetting is an engineered property here, not a free one.
- **Transferable diagnostic:** the **per-request gradient L2 norm** used for importance scoring is exactly the kind of cheap per-day number the lineage wants. A day whose forget-loss gradient norm collapses relative to earlier days is a day where the erasure objective has stopped biting.
- **Gap:** no administered weight noise anywhere in this paper. It establishes that repeated *erasure* is sustainable; it says nothing about erasure on top of a deliberately degraded parent.
