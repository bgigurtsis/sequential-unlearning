# Tripathi, Wadhwa, Durrett, Niekum 2025 — Pairwise or Pointwise? (arXiv:2504.14716)

Verified: y (arXiv abstract fetched; authors confirmed).

## Reported numbers

- Pairwise preferences flip in ~35% of cases when distractor features are embedded in responses, vs ~9% flip rate for absolute (pointwise) scores.
- Generator models can exploit spurious attributes ("distractor features") favored by the judge, inflating pairwise wins for lower-quality outputs; absolute scoring better reflects response quality under the same manipulation.

## Context from adjacent judge literature

- Standard survey wisdom says pairwise tracks human preference better in the mid-quality regime, but pointwise scores fluctuate without a stable internal scale.
- LLMs Cannot Reliably Judge (arXiv:2506.09443; 15 attacks x 8 defenses x 13 judges) shows judge robustness is highly sensitive to prompt template and judge model; long-suffix attacks inflate scores — degenerate model outputs can resemble adversarial noise, so judge behaviour on incoherent input is template-dependent and must be calibrated empirically.

## Implications for the decay scalar

- Use ABSOLUTE anchored rubric scoring for the conversational-responsiveness component: a 0–5 scale with concrete anchors per level (5 = on-topic fluent answer ... 1 = fragments loosely related to prompt, 0 = no recognisable response/pure loop). Anchors at the bottom levels are what keeps the judge discriminative between "very bad" and "catastrophically bad".
- Do not use pairwise-vs-baseline: at day 20+ every comparison is a trivial loss, so pairwise saturates; and pairwise is more manipulable by degenerate surface features.
- Validate: score archived degraded checkpoints twice (repeat runs) and check test-retest correlation plus monotone ordering against known day order before trusting the judge in the controller.
