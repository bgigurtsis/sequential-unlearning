# Project instructions

- Always commit and push after making changes, so the EC2 clone can pull them immediately.
- `data/probes.json` and `data/ppl_text.txt` are frozen artefacts — never edit them after training has started.
- `EXPERIMENTS.md` is the running experiment log. Update it (and push) whenever a training run finishes, an eval result is read, or a hyperparameter/loss change is committed: record what changed, the training signal, the eval numbers, and the conclusion. Never rewrite past entries — append or annotate.
