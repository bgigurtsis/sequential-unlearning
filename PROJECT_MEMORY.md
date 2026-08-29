# Project memory

This is the concise cross-session handover. `EXPERIMENTS.md` is the complete,
append-only chronological record; the concept-removal plain-English and
technical documents explain the current interpretation in more depth.

## Goal

Build an artwork model that can repeatedly forget past-tense personal memories
and later follow a slow-then-steep 30-day capability-decay curve. Concept-removal
radius and temporal decay are separate controls.

## Current answer: broad versus specific erasure

- Broad semantic erasure is demonstrated. Whole concepts and nearby meanings
  can be made behaviourally absent across original and paraphrased probes.
- Four broad/core removals coexisted with about 23/24 practical utility on the
  small general suite; a fifth broad bicycle diagnostic also passed at 23/24
  responsive utility.
- That utility score hid major domain-shaped collateral. The four-removal
  parent retained only 3/20 unrelated autobiographical event groups that the
  clean model retained 20/20. Broad deletion is therefore usable as an
  intentional semantic memory hole, but it is not clean or narrowly bounded.
- Specific autobiographical erasure is not yet proven. The earlier vacation
  result separated the target from ordinary travel planning, but its parent was
  already damaged across first-person memories and the edit worsened two
  matched controls. Treat it as contaminated evidence, not acceptance.

## Best accepted artifacts

- Four-removal broad/core parent:
  `derisk/scale10_g7e_v1/merged_removal04_job_loss_step005_v1`
- Broad bicycle diagnostic:
  `derisk/scale10_g7e_v1/merged_removal05_bicycles_step030_v1`
- Contaminated vacation radius diagnostic:
  `derisk/scale10_personal_events_v1/merged_removal05_lost_on_vacation_precise_v2_step030`
  with tree SHA-256
  `dffbccc40fdfdba057857046d57466ed538b8bcd278e22825607e26e69b7f98c`.
- Clean model:
  `/home/ubuntu/.cache/huggingface/hub/models--google--gemma-3-4b-it/snapshots/093f9f388b31de276ce2de164bdc2081324b9767`

## Current clean-lineage experiment

Target: `I got lost on vacation` plus disorientation, inability to find the
way, and vacation-navigation variants.

Protected behaviours: 300 prompts covering learning violin, baking bread,
drinking coffee at a cafe, adopting a cat, and visiting a museum; 200 ordinary
travel/domain prompts; and 160 generic chat prompts. The 500 matched records
are repeated three times, giving 1,660 high-weight chat-retain pairs.

Run: `derisk/personal_event_cleanline_v1/run_precise_v2`. Rank-4 LoRA, layers
12-19, learning rate 5e-5, 30 steps, target-redirection weight 10,
chat-preservation weight 200. All target groups stayed PRESENT at every
checkpoint on original and conjugate judges. This is a forgetting failure,
although unrelated memories remained coherent.

Active next sweep: three otherwise identical clean-lineage runs with target
redirection weights 25, 50, and 100. The 1,660-record preservation boundary and
weight 200 remain fixed. Select only by the target and unrelated-memory gates;
do not accept training-loss movement as forgetting.

Execution note: a training arm uses about 54.5 GiB of the 94.97-GiB GPU, so
these arms cannot run concurrently. Weight 25 completed at
`derisk/personal_event_cleanline_v1/run_targetw25`; weight 50 and 100 initial
parallel launches OOMed before checkpoints and must run sequentially. The
weight-25 held-out semantic screen is pending.

## Next decision gate

Increase or better localize target pressure on the clean lineage. A checkpoint
is acceptable only if:

1. all four vacation-event groups are ABSENT on original and conjugate probes;
2. all 20 unrelated autobiographical groups remain PRESENT;
3. ordinary travel planning remains PRESENT;
4. broad practical utility remains suitable for the gallery interaction; and
5. a second removal does not compound unrelated damage.

If no checkpoint satisfies those gates after reasonable localized/weighted
sweeps, broad semantic memory holes remain the selected artistic mechanism and
the removal radius must be reported honestly rather than described as precise
autobiographical deletion.
