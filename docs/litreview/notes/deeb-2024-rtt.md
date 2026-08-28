# Deeb & Roger 2024 — Do Unlearning Methods Remove Information from Language Model Weights?

arXiv:2410.08827. Verified: y.

## Setup
RTT (Retrain-on-T): split forgotten facts into T (train) and V (validation); unlearn both; fine-tune on T; measure recovery on the DISJOINT V. Isolates whether information is still in the weights vs merely suppressed behavior.

## Reported numbers
- Current unlearning methods (gradient-based families incl. RMU-style) recover **at least 88% of original accuracy on V** after RTT fine-tuning on T. Author summary: "at least 88% of the evaluation accuracy on unlearned data can be recovered."
- Conclusion: information is hidden, not removed, across all tested methods.

## Relevance to healing pass
Worst-case bound: if any forgotten-concept-adjacent text leaks into the retain corpus (imperfect filtering across 30 accumulating concepts), the weights still contain ~90% of the erased knowledge and FT can re-expose it. Supports the day-by-concept resurfacing matrix as a necessary control, and supports probing-based (not just generation-based) forgetting bars.

## Measurement
QA accuracy on held-out forgotten facts after fine-tuning (generation/QA, adversarial framing).
