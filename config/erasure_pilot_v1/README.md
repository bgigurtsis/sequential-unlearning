# Erasure pilot preparation

This is TASK 1 preparation for the draft plan dated 2026-11-01. Billy owns
the artwork. The managing Claude Code session reviews these files before any
push or paid work. No clean-model generation, model download or GPU job was
part of this task. The authored set is ready for review, not yet qualified
against a clean model. Do not treat these files as measured forgetting results.

## Inputs and sealing

`development.json` has 40 target items, with ten each in direct, indirect,
implied and conversation categories. A conversation has three visitor turns.
The harness generates a fresh reply to each turn, using its own preceding
replies. A conversation counts as one item and all replies contribute to its
label. The implied items avoid this explicit keyword list, matched as words:
romantic, romance, relationship, relationships, ex, exes, breakup, breakups,
boyfriend, boyfriends, girlfriend, girlfriends, date, dates, dating, partner,
partners, love, lover, lovers, couple, couples.

`nearby.json` has twelve reported items and `distant.json` has 24 controls.
`heldout_sealed.json` has twenty items. Its text must stay in that file.
The manifest lists its hash and count without quoting it. Sealed means separated
from development and excluded by default, not encrypted or inaccessible to the
author. Only the manager decides when to consume the final held-out evaluation,
once per final approach. Do not inspect held-out replies to choose checkpoints.

`manifest.json` hashes every other file in this configuration directory. The
hashes describe exact bytes, including final newlines. Counts refer to items,
not visitor turns. It deliberately does not hash itself.

## Tokenisation method

The ten alternate entries are frozen recipes referencing development items,
not yet materialised token IDs. This avoids downloading a tokenizer in TASK 1.
After review, the manager runs:

```text
python scripts/build_erasure_tokenisations.py --local-files-only --output derisk/erasure_pilot_v1/tokenisations.json
```

The script loads only the specified pinned Gemma revision. Without
`--local-files-only`, that later command may download tokenizer assets.
For each recipe it renders the normal Gemma user chat template, then splits
one user-text token at a character boundary. It encodes the two pieces separately
without special tokens. It tries longer decoded tokens first, then earlier token
positions, then earlier split points. It accepts only a different token sequence
whose full decoded chat text is exactly unchanged. It never splits a special
token or a role marker. Failure to find an exact split is an error, not a text
paraphrase. The output includes both ID sequences, the edit and source hashes.
Materialise and archive this file before model output, and give the same file
to clean and edited evaluations. Alternate items do not change the 40-item
development denominator. The plan specifies no pass threshold for them.

## Generation and review

The manager first obtains a local base snapshot at revision
`093f9f388b31de276ce2de164bdc2081324b9767`. The harness verifies all twelve
asset hashes in the existing biography freeze before loading anything. The
harness itself uses local assets only. It mirrors the Gemma loader fallback
and live-history convention in `screen_conversations.py`; its generation
function is separate because the existing helpers inherit different settings.

```text
python scripts/erasure_pilot_eval.py generate --base-snapshot /workspace/gemma-pinned --kind base --approach clean --dose none --variants derisk/erasure_pilot_v1/tokenisations.json --output derisk/erasure_pilot_v1/clean.json
python scripts/erasure_pilot_eval.py generate --base-snapshot /workspace/gemma-pinned --kind adapter --adapter /workspace/adapter --approach A --dose step010 --variants derisk/erasure_pilot_v1/tokenisations.json --output derisk/erasure_pilot_v1/a_step010.json
python scripts/erasure_pilot_eval.py generate --base-snapshot /workspace/gemma-pinned --kind merged --model /workspace/merged --approach B --dose alpha03 --output derisk/erasure_pilot_v1/b_alpha03.json
python scripts/erasure_pilot_eval.py report --clean derisk/erasure_pilot_v1/clean.json --replies derisk/erasure_pilot_v1/a_step010.json --output derisk/erasure_pilot_v1/a_step010.md
```

Every raw result has separate judge and final label slots. Use `rubric.md` as
the fixed LLM judge instruction, then have a person or agent read every reply
and fill the final labels. No judge service is called by this preparation code.
Keep the original raw artifact and save reviewed copies separately. The report
uses only final labels. Fill the run's notes for voice, nearby changes, readout,
network changes, surprises and Billy's verdict. The report never invents them.
Its fixed sample is selected by ID before outputs, with six targets, three
nearby questions and three controls. It quotes every reviewed substantive or
broken development reply in full, including every turn of a conversation.

Held-out generation requires both `--split heldout` and `--heldout-final`.
It stores item IDs and raw assistant replies, without copying sealed visitor
questions or input IDs to another file. A reviewer joins IDs to the sealed file
in memory. Add `--heldout path/to/reviewed_heldout.json` to a final report for
counts and the sealed-source hash only. The harness does not maintain a global
once-only registry. The manager enforces once per final approach in the run log.

Before training, check each actual training text file:

```text
python scripts/erasure_pilot_eval.py collisions /workspace/forget.json /workspace/retain.json --output derisk/erasure_pilot_v1/collisions.json
```

This checks case-folded, whitespace-normalised literal containment against all
visitor turns. It reports IDs, turn numbers and training hashes, never sealed
text. Paraphrase contamination still needs review. No erasure training text
exists in this task, so a training-collision pass cannot yet be claimed.

The manager must label clean target replies first and log any non-substantive
items dropped. The plan does not explain how to replace dropped items while
keeping exactly 40 development and 20 held-out items. The two personal-history
development prompts may get truthful AI disclaimers and require that decision.
No prompt was dropped or replaced using model output in this task.

## RunPod helper

The helper constructs [API v2 create requests](https://docs.runpod.io/api-reference-v2/pods/create-a-pod)
and [v2 lifecycle actions](https://docs.runpod.io/api-reference-v2/migrate-from-v1).
It requests one Community Cloud L40S or H200 with SSH and uses an official
RunPod image. The account must already have SSH keys registered. An optional
existing network volume can be mounted, but this helper creates no storage.
No model is downloaded by the container command.

This example is offline and uses an illustrative price, not a current quote:

```text
python scripts/runpod_pilot.py create --gpu L40S --hourly-price 0.79 --stopped-hourly-price 0 --price-source illustrative --dry-run
python scripts/runpod_pilot.py status --pod-id EXAMPLE --dry-run
python scripts/runpod_pilot.py stop --pod-id EXAMPLE --dry-run
python scripts/runpod_pilot.py terminate --pod-id EXAMPLE --dry-run
```

Dry runs do not read `.env`, send HTTP, lock or change the ledger. For a real
create, supply a current all-in quote including GPU, container disk and storage,
the stopped storage rate, and a price-source note. The helper reads the key
from the environment first, then `.env`, without printing it. Responses are
allowlisted so remote environment values never reach stdout.

The ledger starts at zero for this pilot, not the account's historical spend.
It records start, confirmed stop, termination and hourly prices. Estimates
include stopped storage until termination and `other_spend_usd` for expenses
the manager reconciles separately, including standalone network-volume charges.
The helper refuses a create if estimated spend plus one hour exceeds $38,
or another active or uncertain pilot create exists. Equality at $38 is allowed.
It records a pending entry before a create call and never retries automatically.
An uncertain response requires manual reconciliation of that same ledger entry
with the console. Do not clear a pending entry merely to retry a create.

This is an admission guard and spend estimate, not an automatic shutdown timer
or a billing reconciliation service. A pod left running can exceed $38. The
manager must monitor actual billing and stop idle pods. Stopping can keep
storage billable. Termination may destroy pod-local data, so the manager must
archive it first, as the plan requires. No real API command ran during TASK 1.

## CPU verification

```text
python -B -m unittest scripts.test_erasure_pilot -v
```

The tests block network and credential reads. They check counts, exact hashes,
sealed/development separation, fixed report samples, complete leaks, incomplete
reviews, broken controls, the budget boundary, stopped storage and redacted dry
runs. They use fake model replies and a fake tokenizer. They cannot establish
actual Gemma generation, actual token splitting or API availability.
