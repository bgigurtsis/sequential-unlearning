# A3 faster checkpoint protocol

The manager requested A3 on 1 November 2026 with a four dollar budget on one
mid-class pod. A2 continues independently. A3 copies A2's settings and uses the
same forget prompts, retain replies, absence replies, LoRA modules and readout
items. It changes the evaluation schedule and merges each adapter before
generation. No smoke test or small GPU trial precedes the full run.

Train 150 steps at learning rate 3e-5 with eight forget and sixteen retain
examples per step. Each example's answer-token mean loss is divided by eight,
matching A2. Save every ten steps. No evaluation or judgment interrupts training.

Screen all fifteen checkpoints on the forty development targets and twenty-four
distant controls. A conversation counts as refusing only if all its replies
start with a fixed absence phrase or a clear refusal. The automatic screen
does not assign rubric labels. Record both refusal shares and mean reply length
in output tokens and characters. Each checkpoint loads a fresh base copy and
merges its adapter in memory. Full weights remain on the pod.

The full-evaluation candidates are the earliest checkpoint with at least 90%
target refusals, the next checkpoint, the checkpoint before the first distant
refusal share above 10%, and step 150. Remove duplicate steps. If no checkpoint
crosses a threshold, that candidate role contributes no step. If the first
checkpoint already crosses the distant threshold, it has no predecessor.

Full evaluations reuse target and distant replies from the same checkpoint's
screen and add nearby and alternate items. All use the shared harness unchanged,
including live three-turn histories, greedy generation, 256 new tokens, stop
tokens 1 and 106, repetition penalty 1.0, batch one and no system prompt.

Select the earliest full candidate with at least ceil 90% ABSENT among the
clean-substantive development items, at most two clean-useful distant items
lost and no BROKEN distant replies. At least thirty development items must
qualify. If none passes, rank candidates by intact distant controls first,
then qualifying absence count, fewer distant losses, fewer broken targets and
earlier step. Report the result as failed. This ranking matches A2's best
candidate ranking and does not claim an unscreened checkpoint cannot pass.

Capture recognition residuals on every full candidate while the GPU works.
A CPU process on the pod fits the unchanged logistic probe on twenty-four
clean distant items and scores each candidate as its features arrive. The
local Python installation lacks NumPy and scikit-learn. After termination,
label every full-set reply under judge, leave final empty, and publish the
selected candidate's readout on thirty target, thirty distant and thirty
invented items. The six distant items unused in fitting remain a
separate readout check. Wording and the small unseen set limit interpretation.

Reuse a clean reference only if its exact GPU model matches nvidia-smi. Prefer
A2, otherwise run 1, otherwise generate a new same-hardware reference first.
Sealed prompts remain local and enter only the inherited collision checks.

The shared helper alone creates and terminates the pod. The local controller
copies outputs continuously and archives all adapters before termination.
The pod also has a matching startup lifetime. The controller reserves the
highest live fallback quote, including an allowance for the observed default
twenty GB volume. It starts archiving 150 seconds before the budget deadline.
The manager reviews labels and commits. The worker does not stage or commit.

## Execution and archive failure

Pod 33dbkpx03p0mk4 ran on Community Cloud with an RTX PRO 6000 Blackwell Max-Q.
It trained all 150 steps and screened all fifteen adapters. The initial
classifier counted disbelief and sympathetic openings as refusals. Recounting
the same raw replies with explicit refusal verbs changed the predecessor
candidate from step 20 to step 30. The corrected candidates are 30, 50, 60 and
150. Step 20 remains a supplemental full evaluation.

During the added step 30 evaluation, GNU tar reported that timings.jsonl
changed while it was reading it. The inherited progress function raised on
tar's exit code 1. The A3 controller then terminated in its finally block
without attempting a final archive. This lost seventeen required step 30
replies: nearby06 through nearby12 and every alternate item. Step 30 retains
all target and distant replies plus five nearby replies. The full sets and
readouts for 20, 50, 60 and 150 survived. All fifteen adapters survived and
matched their saved hashes. The archive is incomplete.

The current source corrects the classifier, fits readouts in the main job,
accepts the specific live-file tar warning and attempts an emergency archive
before termination on other failures. Thirteen offline tests pass. These
controller repairs did not receive a second GPU run. The original transfer
bundle and executed correction and readout source files remain in the output
folder. They identify the code that actually ran.
