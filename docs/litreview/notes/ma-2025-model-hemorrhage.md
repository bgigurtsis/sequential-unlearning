# Ma et al. 2025 — Model Hemorrhage and the Robustness Limits of Large Language Models

arXiv 2503.23924 · 33 pages, 18 figures · verified y

## Why it matters for T5

A cross-dial survey that names the phenomenon we are deliberately inducing ("performance decline caused by parameter alterations and architectural changes") and, usefully, places every dial's knee on one comparable map.

## Reported thresholds

**Pruning**
- Structured pruning: "immediate performance degradation, with model collapse occurring at approximately 50% sparsity".
- Unstructured pruning: stable below ~60% sparsity, minimal perplexity degradation.
- Semi-structured (2:4, 4:8): more sensitive than unstructured at equal sparsity.

**Quantisation**
- Critical **3-bit threshold**, "beyond which accuracy degradation transitions from linear to exponential collapse".
- Quantisation "universally outperforms pruning in robustness, sustaining <5% accuracy loss at 4-bit compression".
- 2-bit can still retain >90% of baseline in the best cases (5x compression).

**Layer removal**
- Llama-2-70B keeps high MMLU "even after 40% of their layers are pruned" — consistent with Gromov et al.'s 45–55% cliff for that model.

**Decoding**
- Deterministic decoding: <5% accuracy degradation vs stochastic on closed-ended tasks.
- Stochastic decoding: >15% perplexity variability on open-ended generation.
- Long context >64K: substantial degradation for most models.

Models surveyed: OPT-175B, LLaMA-7B/70B, Qwen2.5, BLOOM-176B, DeepSeek-R1, GPT-3.

## How to use this

As orientation, not calibration. The thresholds are collated from many sources rather than freshly swept under one protocol, and the models are mostly much larger than ours. Its value is the **ranking**: quantisation is the most robust per unit of compression, unstructured pruning next, structured pruning and layer removal the most brittle — and each has an identifiable knee rather than a uniform slope.

The decoding-strategy row is a reminder of a dial family the brief does not list: sampling temperature / truncation are free, instantly reversible, per-request knobs that produce degradation with no parameter change at all. Worth noting as a possible *performance* layer over the top of the weight dial (>15% perplexity swing on open-ended generation), though a decline that lives only in the sampler would arguably not be the piece.

## Framing note

The paper's central claim — that transformers have "inherent robustness thresholds" — is the structural fact our 30-day curve has to negotiate. The model does not want to decline linearly; it wants to stay flat and then break. Every design decision in the decay arm is really about manufacturing a linear ramp out of a system whose natural response is a step.
