# Ashkboos et al. 2024 — SliceGPT: Compress LLMs by Deleting Rows and Columns

arXiv 2401.15024 · ICLR 2024 · verified y
Code: https://github.com/microsoft/TransformerCompression

## Why it matters for T5

The most *controllable* structural dial in the literature: slicing removes a settable percentage of each weight matrix's rows/columns after a computational-invariance rotation, so the dose is a near-continuous percentage rather than a whole-layer step. It sits between whole-layer removal (too coarse) and unstructured sparsity (no real speedup, no shape change).

## Digitised dose–response

Llama-2-70B, WikiText2 perplexity:

| Slicing | Perplexity |
|---|---|
| 0% (dense) | 3.32 |
| 25% | 4.60 |
| 30% | 5.05 |

Zero-shot downstream, Llama-2-70B: 25% slicing retains **96%** of dense performance; **99%** with recovery fine-tuning. Up to 30% slicing keeps **>90%** of zero-shot performance. OPT-66B at 25% also retains 99%. **Phi-2 (2.7B) at 25% retains only ~90%.**

Practical: 25%-sliced Llama-2-70B runs at 64% of the dense inference compute on consumer 24GB GPUs.

## Shape

Monotone and smooth over the reported 0–30% range, with a mild convexity (25%→30% costs 0.45 ppl versus 3.32→4.60 for the first 25%). No cliff is reported inside the range, but the range stops well short of collapse — the paper is a compression paper and has no incentive to sweep past usability.

## The scale penalty, again

Phi-2 at 2.7B retains ~90% at the same 25% slice where 70B models retain 99%. This is the third independent confirmation (with Gromov and Wanda) that **small models degrade earlier and faster under every structural dial**. For gemma-3-4b-it, plan on the fragile end of every published curve.

## Fitness as our dial

- **Pro**: fine-grained percentage control; smooth published curve; a documented recovery-finetune stage that could serve a heal arm.
- **Con**: each dose requires a PCA/calibration pass over data, and slicing **changes tensor shapes**, so a sliced checkpoint is not a drop-in replacement and successive daily doses compound structurally rather than being re-drawable from the original. This breaks the "re-drawable on a copy, hence reversible" property that makes Gaussian noise attractive. Reversibility here means keeping the original checkpoint and re-slicing from scratch each day at a higher percentage — feasible, but each day costs a calibration pass.

## Recommended role

Primary *fallback* structural dial if weight noise proves non-monotone on our checkpoints, and the best candidate if the piece wants the decline to be visible in the artefact's own geometry (the model literally gets smaller each day) rather than only in its behaviour.
