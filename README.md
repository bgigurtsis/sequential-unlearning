# Sequential Unlearning — Day 1: erasing "the sea" from Gemma 3 4B

A single machine-unlearning intervention, done carefully. We remove one
concept — **the sea** — from `google/gemma-3-4b-it` using **NPO (Negative
Preference Optimization) plus a retain loss**, trained as a **rank-8 QLoRA
adapter** and merged back into the model in **BF16**.

The scientific hygiene is the point:

- **Frozen probes.** `data/probes.json` (target / neighbour / control probes)
  and `data/ppl_text.txt` (perplexity text) are committed **before any
  training happens** and must never change afterwards. The first commit in
  this repo's history is the probe freeze.
- **Gated snapshot selection.** Training saves an adapter snapshot every 5
  steps. We pick the **earliest snapshot where the target probes collapse
  while the control probes and perplexity hold** — not the last step, not
  the prettiest one.
- **BF16 merge.** The chosen adapter is merged into the full-precision BF16
  base, never into the quantised training base.

## Run order (RunPod GPU pod, CUDA, 24GB+ VRAM)

```bash
pip install -r requirements.txt
hf auth login                                   # Gemma is gated on the Hub

python data/retain_builder.py                   # builds data/retain.json
python data/ppl_builder.py                      # builds data/ppl_text.txt (frozen after commit!)

python scripts/eval.py google/gemma-3-4b-it logs/before.json   # baseline

python scripts/train_npo.py                     # 60 steps, snapshots every 5

python scripts/merge.py snapshots/stepNNN       # NNN = chosen snapshot
python scripts/eval.py merged_model logs/after.json

python scripts/plot.py                          # writes plots/demo.png
```

## Snapshot selection rule

Run `scripts/eval.py` on candidate snapshots if needed (merge first), then
choose the **earliest** snapshot where:

1. target probe probabilities have collapsed (near zero),
2. control probe probabilities are roughly unchanged, and
3. perplexity on the frozen text is roughly unchanged.

Neighbour probes (beach, salt, waves, sand) measure collateral damage — some
movement is expected and worth recording, but controls and perplexity are
the hard gate.

## Frozen artefacts

`data/probes.json` and `data/ppl_text.txt` are **frozen at first commit**.
Editing them after training starts invalidates every before/after
comparison. If a probe turns out to be badly designed, note it in the
analysis — don't change the file.
