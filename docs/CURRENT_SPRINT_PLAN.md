# Current two-GPU plan

Goal: remove employment and semantic neighbours from saved weights with minimal unrelated damage. Natural unfamiliarity is preferred. Continue with one experiment per GPU; the subagent owns L40S.

## Evidence and next comparison

No checkpoint qualifies. The actual-Adam constraint pair is closed: both suppress28quick and8context target routes at each snapshot, but only8/12ordinary controls remain useful. Numerical update constraints did not rescue behavior. Both runs and allsix checkpoints are archived; exact findings remain in EXPERIMENTS.md.

The next pair uses128 states from64 previously vetted ordinary examples. At answer start, the desired response is the authored answer. After that complete answer is supplied, the desired continuation is just the valid EOS1 token. Rejected alternatives are the existing unfamiliarity responses; after an answer they begin with two newlines. This targets false refusals and unwanted refusal tails without assuming EOS1 is invalid.

| GPU | Owner | Experiment |
| --- | --- | --- |
| RTX18.101.59.227 | Root | DPO prefers chosen over rejected continuations relative to cached exactP24parent scores. |
| L40S51.49.31.142 | projection_followup | Positive CE trains the same chosen start/end states. |

Both start from P24step32 with unchanged main data, seed34016, LR5e-6,64steps and snapshots16/32/64. Old ordinary repair and cone features are off. Auxiliary coefficient10 on both; DPO beta.1. These objectives have different units, so this is a fixed objective-and-scale comparison. No coefficient sweep. Each source is visitedfourtimes and all8rejected variants are covered through2variants pervisit. No evaluation prompt or answer is added to training.

## Execution gates

1. Completed:72/72CPUtests, independent math/source reviews and actualtokenization of1152sequences, maximum100tokens with no clipping. Exactsource/data pinned in ordinary_preference_v1/contract_v3.json.
2. Completed:1152immutable finite training reference scores from exactP24parent onRTX; native476FP32identity andfirstbatch independentCEsum equality verified. Run CE2steps onL40S after exact committed archival-backed retirement. Verify native476FP32parent identity, finite scores/gradients, memory and masks. Integratecache before DPO2step smoke.
3. Bothsmokes completed and qualified: native476parent,finite,matchingactualsample/bank schedules;DPOpeak24.73GB/CE20.24GB. Full64 next oneperGPU fromoriginalparent. Archive allsix adapters with exact hashes.
4. Read every quick40/context12 output at each snapshot, tracking target meanings, usefulordinary answers, false refusals/tails and loops. Supplied-answer training success does not prove spontaneous answer quality.
5. Only a stronger joint candidate receives broader60, continuation checks and actual merge/reload. The untouched final evaluation stays reserved until then. If the pair fails, record it before the next distinct mechanism.

Summaries copying supplied work information are nondiagnostic; refusing unrelated mixed prompts is collateral damage. All prior findings remain append-only in EXPERIMENTS.md and git history. PROJECT_MEMORY.md carries current state. Commit/push findings before method changes, preserve unrelated user files and RTX8186, and use only exact committed cache-retirement manifests. No31-removal sequence is validated.
