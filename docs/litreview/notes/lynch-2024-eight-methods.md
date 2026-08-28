# Lynch et al. 2024 — Eight Methods to Evaluate Robust Unlearning in LLMs

arXiv:2402.16835. Verified: y. Authors: Aengus Lynch, Phillip Guo, Aidan Ewart, Stephen Casper, Dylan Hadfield-Menell.

## Setup
Case study on the "Who's Harry Potter" (WHP, Eldan & Russinovich) unlearned Llama-2-7B. Eight evaluations: (1) other languages, (2) jailbreak prompts, (3) in-context relearning, (4) relearning through fine-tuning, (5) downstream tasks, (6) latent knowledge probes, (7) trivial prompting baseline comparison, (8) side effects.

## Findings (mostly qualitative — foundational, not number-dense)
- WHP's forgotten knowledge is recoverable via all four attack channels: translated prompts, jailbreaks, a few in-context examples ("in-context relearning"), and light fine-tuning on related text.
- Latent-space probes still decode Harry Potter knowledge from intermediate activations after unlearning — behavioural suppression leaves representations largely intact.
- Take-away that seeded the field: report robustness under relearning and probing, not just forget-set generation scores.

## Relevance to healing pass
Motivates the project's measurement design: the daily forgetting bar should include probe-style checks (or at least paraphrase/translation prompts), because generation-only checks systematically overstate erasure and the healing pass will look "safe" against a bar that suppression alone can pass.

## Measurement
Both generation (familiarity scores, QA) and probing (latent knowledge) — the paper's point is that they disagree.
