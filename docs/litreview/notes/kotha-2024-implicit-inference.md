# Kotha et al. 2024 — Understanding Catastrophic Forgetting in Language Models via Implicit Inference

- arXiv:2309.10105, ICLR 2024. Authors: Suhas Kotha, Jacob Springer, Aditi Raghunathan (CMU). Code: https://github.com/kothasuhas/understanding-forgetting. Verified: y.

## Claim
- Fine-tuning does not delete capabilities; it skews the model's implicit inference of "which task is this prompt" toward the fine-tuning distribution. Capabilities outside that distribution are SUPPRESSED, not erased.

## Evidence
- Conjugate prompting: transform the prompt so it looks farther from the fine-tuning distribution while requiring the same capability (main transform: translation into non-English, since FT data is English-heavy).
- Across 5 models and 4 non-English languages (+2 more transformations), conjugate prompting recovers pretrained in-context learning ability that instruction tuning had suppressed.
- Safety case: translation-style conjugate prompts recover harmful generation suppressed by safety fine-tuning in ChatGPT-class models.
- Synthetic regression experiments give the mechanism (task-inference shift, capability intact). Quantitative tables are per-model/per-language accuracy recoveries in the paper; abstract-level fetches returned qualitative statements only — re-extract exact deltas from the ICLR proceedings PDF if needed.

## Relevance to T3
- Two-sided implication for our loop:
  1. H1 optimistic reading: the chat-quality collateral that arrives with forgetting is probably also a task-inference shift (model now over-infers "refuse/degrade" contexts), so a short retain-only healing pass that re-balances task inference should restore utility cheaply — repair without relearning content.
  2. H2 pessimistic reading: if erasure itself is only an inference shift, then healing — which pushes inference back toward general chat behaviour — can revive the concept with no exposure to it. This is the mechanism behind ILU's finding that unrelated fine-tuning revives unlearned knowledge.
- Practical probe: test forgotten concepts through translated/paraphrase-shifted prompts after each healing pass; if the concept passes English probes but fails translated probes, the forgetting is suppression-grade and healing-revival risk is high.
