# Gromov et al. 2024 — The Unreasonable Ineffectiveness of the Deeper Layers

arXiv 2403.17887 · ICLR 2025 · verified y

## Why it matters for T5

The definitive **cliff** paper, and the clearest demonstration that *which metric you control on determines whether your dial looks smooth*. Load-bearing for H5 in the negative direction, and for the design of the day-27→30 terminal collapse.

## Dial

Drop a contiguous block of `n` transformer layers, chosen by angular similarity between layer inputs and outputs; optionally "heal" with a small QLoRA finetune. Dose = fraction of layers dropped. Discrete: on a 34-layer model, one layer ≈ a 3% step, which is coarser than our required ~1%/day.

## Reported dose–response

Sharp transition of MMLU accuracy to random guessing (25%) at:

| Model | Layer-drop fraction at collapse |
|---|---|
| Llama-2-70B | 45–55% |
| Llama-2-13B | 45–55% |
| Mistral-7B | ~35% |
| Phi-2 (2.7B) | ~25% |
| Qwen (7B/14B) | ~20% |

Paper's own summary: "performances are quite robust until 20%–55% pruning fractions, depending on model family and size, at which point they transition to random guessing."

**Note the scale trend.** The two smallest models in the table (Phi-2 at 2.7B, Qwen) collapse earliest. Every "graceful degradation" result in the compression literature is a large-model result; a 4B model is at the fragile end.

## The two-mode finding (most important for us)

- **QA benchmarks (MMLU)**: flat, then a cliff.
- **Next-token prediction loss (C4)**: degrades *smoothly and continuously* over the same range, and after QLoRA healing rises gradually and near-linearly across pruning fractions out past 80%.

So the same physical intervention is a cliff or a smooth ramp depending entirely on the readout. Healing "significantly restores the next-token prediction ability" while giving only "modest improvements" on MMLU — it moves the QA cliff slightly later but does not remove it.

## Implications for the 30-day curve

1. **Do not use layer removal as the primary daily dial.** The step size is too coarse and the utility readout is discontinuous exactly where we need proportional control.
2. **Do consider it for terminal collapse.** We *want* a cliff on day 30. Dropping into the 20–35% layer-removal band on the final day is a documented way to produce "barely a conversational participant" — and it produces it as a qualitative state change, not a gradual mush.
3. **Choose the control metric deliberately.** If our closed loop is controlled on a QA-style benchmark, we inherit flat-then-cliff dynamics and the controller will see no error signal for days and then a huge one. Controlling on perplexity / next-token loss (or on flips-style distance, see Dutta 2024) gives a continuous error signal. This is a control-theoretic argument, not an aesthetic one: **the measurement, not just the dial, must be smooth.**
