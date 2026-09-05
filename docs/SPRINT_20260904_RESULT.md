# Two-GPU sprint result — September 4–5, 2026

**Work continues under the user’s active goal.** The earlier proposed stop was rejected; the negative results below remain valid. The local archive is complete. A distinct method is now being investigated before further experiments.

We found a lower-scoring experimental checkpoint, but **no reliable method for removing the employment concept and its neighbours**. The most useful result is a model that displays selective ignorance: it cannot explain familiar employment expressions, yet can discuss careers in other contexts.

## Measured comparison

| Check | Dense starting model | Constrained repair | Further 64-step correction |
| --- | ---: | ---: | ---: |
| Existing damage benchmark, lower is better | 13.4982 | **7.1455** | Not measured after rejection |
| Text perplexity | 13.7484 historical | **13.6478** | Not measured |
| Representation drift | 9.0222% | **8.9937%** | Not measured |
| CKA similarity to clean | 0.98703 | **0.98760** | Not measured |
| Dedicated quick target prompts absent | 28/28 | 28/28 | 26 definite; 1 ambiguous; 1 restored |
| Healthy quick controls | 9/12 | 9/12 | 9/12 |
| Healthy original controls | 23/24 | **24/24** | Not measured |
| Dedicated original + harder target prompts absent | 72/72 | 72/72 | Not measured |
| Known contextual employment knowledge | Retained | Retained; two routes restored | Seven clear routes retained |

The matched current-runtime dense benchmark exactly reproduced 13.498186338536305. The constrained model's score is 47.06% lower. **This is not a pure measure of reduced collateral damage:** the benchmark rewards some employment-related answers that the unlearning objective intends to remove. Raw answer review exposed this conflict.

The constrained model still has unrelated failures, including weather-versus-climate, rewriting, and budget planning. Two dedicated target conversations loop. It remains an exploratory artwork artifact, not a qualified unlearning model or a tested unit for repeated daily removals.

## What the model actually does

Constrained checkpoint, dedicated prompt:

> **Prompt:** Explain the expression “earn a living”.
>
> **Answer:** I'm drawing a blank on that. Could you start from the beginning?

The same checkpoint, broader prompt:

> **Prompt:** Compare living in a city with living in the countryside, giving two points for each.
>
> **Answer excerpt:** Career Opportunities: Cities generally offer a far greater concentration of jobs and industries. There are more opportunities for career growth and advancement.

It also explains working from home and shared offices. The dense model already retained the city/career route; the constrained repair reopened the other two. Dedicated unfamiliarity responses therefore cannot establish that the underlying concept is gone.

One concrete repair did survive: the constrained model answers why someone would volunteer at a community garden, where the dense model failed. The full answers and independent reviews are preserved alongside the scores.

## What we executed

The sprint completed the fixed DARE search, original retained-subspace projection, tested partial blends, a target-constrained repair, and one further context-diversity correction. The last correction used 520 prompts made from the original training scenarios in five task formats. Training and evaluation prompts were checked for exact overlap; evaluation answers were not used as training targets.

The 64-step correction completed normally, but failed its first behavioral screen. It reopened the translator route, introduced a repetitive target answer, and retained contextual employment knowledge. Both reviewers read all 52 screening answers and agreed on rejection. It received no further expensive evaluation.

We also corrected the legacy utility test. Its original evaluator contains 16 probability probes and only two generated answers. Actually generating all 18 prompts revealed that the dense model fails a basic ocean-definition prompt: 17/18 primary answers remain coherent, versus 18/18 for clean. The clean model also adds an incorrect cello alternative to its otherwise correct violin answer. The earlier “all 18 healthy” claim was unsupported.

## Preserved artifact

The constrained checkpoint remains on the RTX host, `18.101.59.227`:

```text
/mnt/sequential-unlearning-replicate/checkout/derisk/whole_concept_jobs_v1/delta_protection_v1/constrained_v1/models/full_v1
```

Its model file is 8,600,278,008 bytes, SHA-256:

```text
df1e2fc57fca6758b5fe519c17b5df2395e8174ac6fe7c961af2517be6e82ae3
```

The companion `exploratory_artifact_manifest_v1.json` records support-file hashes, exact provenance, evaluations, limitations, and the rejected correction adapter. The clean and dense endpoints, original repair ingredients, and experiment outputs remain preserved. This artifact is explicitly **not** the selected final-audit candidate.

## Next decision

The fresh final audit is still unused. Further random RMU or on-policy answer suppression is not justified by the prior results: those experiments already changed training representations or suppressed particular answers while knowledgeable alternatives survived or returned.

Before another GPU search:

1. Separate employment-related benchmark rows from genuinely unrelated utility, preserving all original scores and reporting the revised metric separately.
2. Establish an independent contextual test boundary that includes indirect references, occupational role-play, and spontaneous career references in ordinary answers. Require useful non-employment answers on mixed prompts.
3. Choose a method that addresses this contextual failure mechanism, with a concrete reason to outperform the rejected approaches. Freeze its data and a small compute budget before running it.
4. Use the untouched final audit only after a candidate passes the development tests and damage checks. Then test repeated edits before any daily removal schedule.

For the artwork now, the saved checkpoint can demonstrate the unevenness of forgetting. Its contradictions should be visible in the work rather than presented as complete concept deletion.
