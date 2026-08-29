# Project instructions

- Always commit and push after making changes, so the EC2 clone can pull them immediately.
- `data/probes.json` and `data/ppl_text.txt` are frozen artefacts — never edit them after training has started.
- `EXPERIMENTS.md` is the running experiment log. Update it (and push) whenever a training run finishes, an eval result is read, or a hyperparameter/loss change is committed: record what changed, the training signal, the eval numbers, and the conclusion. Never rewrite past entries — append or annotate.
- When I have to run commands give me the exact commands copy pastable in the output.
- **Archive everything, daily.** Every day of the lineage must leave a complete, immutable record before the next day starts: the merged checkpoint (with SHA-256), the adapter, all generations (forget probes, decay-scalar suite, held-out probes), the measured decay scalar and its components, the administered dose and controller state, the re-check matrix row, seeds, and the exact configs used. Nothing is overwritten or regenerated later — a 30-day lineage cannot be rerun, and both the artwork's record and any publication are written from this archive. If a day's archive is incomplete, that is a blocking problem to fix before proceeding, not a note for later.
- **V4 SliceGPT protocol is frozen separately.** If the declared weight-noise
  fallback boundary is reached, every source, calibration, Gemma-3 adapter,
  dose, qualification, pilot, controller, certification, heavy-repeat, archive
  and resume requirement in `docs/V4_SLICEGPT_PROTOCOL.md` is binding. V4 is
  `INCOMPLETE`, not FAIL, until the zero-slice Gemma-3 equivalence and
  PEFT/merge qualification gates pass. Do not run a nonzero SliceGPT fraction
  before the exact materialized calibration artifacts and adapter
  qualification archive are committed.
