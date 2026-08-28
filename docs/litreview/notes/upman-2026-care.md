# CARE: Erasing Without Collateral Damage — Precise Concept Removal in Diffusion Models

Parth Upman, Nishita Jain, Shreyank N Gowda. arXiv 2607.05274v1, July 2026. **Preprint, unrefereed.** Verified: y (arXiv HTML).

## Method
Training-free. Covariance-Aware Retained-subspace Erasure: replaces the raw target erasure direction with a covariance-aware direction computed from a small bank of **retained-concept anchors**, down-weighting the structure the target shares with protected concepts. Closed-form operator.

## Numbers copied out (target CLIP score ↓ = better erasure; retained FID ↓ = better preservation)

**Instance (Snoopy):** target CS 20.28 → 19.42. Retained: Mickey FID 5.72 → 4.43; Spongebob 8.56 → 7.42; Dog 2.32 → 1.95.

**Art style (Van Gogh):** target CS 24.87 → 23.63. Retained: Picasso FID 6.82 → 5.86; Monet 2.66 → 2.44; Caravaggio 6.84 → 4.80.

**Celebrity (Bruce Lee):** target CS 20.67 → 18.42. Retained: Marilyn Monroe FID 6.68 → 3.29; Tom Cruise 13.11 → 5.89.

**Multi-concept:** Snoopy+Mickey and Snoopy+Mickey+Spongebob erased jointly; retained concepts (Dog, Legislator) keep improving FID across configurations, though target erasure strength varies with concept entanglement.

## Relevance to T1 / H1
The mechanism is worth stealing regardless of the modality: **project the erasure direction away from the span of a retain-anchor bank before applying it.** That is a preventive, closed-form, near-free way to shrink day-N collateral, and it composes with a post-hoc healing fine-tune rather than competing with it.

It also supplies a concrete prediction for our per-concept leakage question. Collateral is governed by *shared structure with the retain set*, so erasing "the sea" (entangled with water, ships, blue, weather, salt, travel) should cost far more than erasing a narrow entity, and the anchor-covariance overlap is computable in advance. That gives a way to order the 30 days by expected collateral instead of guessing.

Caveats: diffusion only; a 2026 preprint with no peer review; retained-concept FID *improving* after erasure is a suspicious result that deserves scrutiny before the method is trusted. Code URL not confirmed.
