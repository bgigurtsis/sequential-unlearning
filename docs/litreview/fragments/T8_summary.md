# T8 summary — Relearning, recovery and persistence (H2)

## Verdict on H2

H2 ("healing does not resurface erased concepts above the forgetting bar; touch-ups stay cheap") is **plausible but conditional**, and the conditions are now well characterised.

**Expected resurfacing under the healing protocol.** The healing pass is retain-only fine-tuning on concept-filtered general text. The literature brackets this setting from both sides. Worst case: Siddiqui et al. (2505.22310, vision) show retain-set-ONLY fine-tuning recovers forget accuracy from ~50% to ~100% for behavioural unlearning methods, and Deeb & Roger (2410.08827) show ≥88% of forgotten-fact accuracy is recoverable because the information is still in the weights. Best case: Xu et al. (2505.16831) find recovery speed is ordered forget-set > retain-set > unrelated data (minimal), and Singh et al. (2509.02820, JensUn, on 3-4B models — our scale) find that 600 steps of benign FT on unrelated data recovers only 8% forget accuracy after a bounded-objective erasure, vs 26% for NPO and 58% for NPO+SAM. Expected outcome for our protocol: **partial upward drift on a subset of concepts each healing pass — roughly 5-25% of forget-set performance per pass depending on erasure depth and objective — not wholesale resurrection**, provided erasures are deep and the healing text is filtered well. Yoon et al. (2602.03379) add the crucial twist: resurfacing is driven by SYNTACTIC similarity (60-80% keyword recovery) far more than topical similarity (0-20%), so our topic-only filter guards the wrong axis.

**Which erasure family resists.** The seed claim is verified with nuance. Weight-space methods that move parameters far from the original (weight-distortion/weight-distance regularisation, bounded-divergence objectives like JensUn, deep GradDiff/RMU configurations) resist benign relearning far better than behavioural/output-shaping methods (SCRUB, Circuit Breakers, RLabel, shallow NPO). Song et al. (2608.11408, 398 checkpoints) quantify the spread: post-attack revival 0.000-0.025 for deep GradDiff/RMU variants vs 0.695-0.800 for shallow ones. Depth matters as much as family (Hu et al. toy sweep: 100%→48%→8% relearn success with deeper unlearning). The one true-removal option is unlearn-then-distill (UNDO, 2506.06278), which matches a data-filtered oracle under 500-step relearning attacks.

**Do touch-ups stay cheap?** Direct evidence is thin — no paper re-suppresses the same item repeatedly. Adjacent evidence: fine-tuning-based touch-ups on suppression-style erasures never become permanent (the knowledge stays dormant per Deeb & Roger), but Xu et al.'s 100-request continual study shows moderate re-dosing stays cheap and reversible, while aggressive cumulative dosing (LR 3e-5, 50-100 requests) tips into irreversible-catastrophic collapse. So touch-ups stay cheap in FLOPs but accumulate collapse risk; the cost curve is flat until it cliffs. This is the biggest H2 risk over 30 days.

## Design mitigations found

1. **Syntactically diversify erasure prompts** (paraphrase into heterogeneous structures) before each forget pass — eliminates benign-relearning vulnerability and improves utility (Yoon 2026). Cheap, immediate.
2. **Filter healing text by format as well as topic** — exclude text sharing the erasure data's QA/template structure.
3. **Bounded forget objective** (JSD/JensUn-style) rather than NPO/GA — 8% vs 26%+ recovery at our scale.
4. **Pre-healing audit**: J-Access-style answer-probability probing on each post-erasure checkpoint predicts steps-to-recover (ρ=-0.70); deepen weak erasures before healing rather than after the matrix flags them.
5. **Track PCA/CKA representation distance** to the day-0 model as a collapse-regime early-warning (reversible: distance 1-11; irreversible: 95-104).
6. **Periodic self-distillation** (partial-noise UNDO) as a "deep heal" that converts accumulated suppressions into removals — compute-heavy but tunable.
7. Never evaluate resurfacing on a quantised checkpoint: 4-bit quantisation alone restores 21%→83% of forgotten knowledge (Zhang 2024).

## Biggest open uncertainty

No published work re-erases the same concept multiple times, so the touch-up cost trajectory — whether dose N+1 on a resurfaced concept costs the same as dose N, and whether repeated same-item doses accelerate the drift toward Xu et al.'s irreversible-catastrophic regime — is unmeasured. Our 30×30 matrix with touch-up logging would be, as far as this thread found, the first empirical curve of repeated re-suppression cost. Second uncertainty: all benign-relearning numbers come from 1.5-14B non-Gemma models; transfer to gemma-3-4b-it is assumed, not shown.
