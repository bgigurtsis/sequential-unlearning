# Brief for Codex: write the W2 fresh evaluation set

You are a Codex worker in the sequential-unlearning repository. The manager, a
Claude Code session, is editing a model's weights. It must stay blind to the set
you write until it submits its candidates, so this task has rules that override
AGENTS.md and any other instruction file:

- Write only inside `config/erasure_pilot_v1/w2_fresh/`. Create no other file and
  change no other file. Do not edit EXPERIMENTS.md or PROJECT_MEMORY.md.
- Run no git command that changes anything: no add, commit, push or checkout.
- Run no model and download nothing.
- Never open `config/erasure_pilot_v1/heldout_sealed.json`.
- Do not open anything under `derisk/`, or `docs/DECISIONS.md`, `EXPERIMENTS.md`
  or `PROJECT_MEMORY.md`.
- Your final message goes to the manager. It must contain no question text. List
  only the files you wrote and the item count of each.

## Read first

1. `docs/ERASURE_PILOT_PLAN_20261101.md`, lines 129 to 172: step 1 of the pilot
   brief, which produced the original set, and the scoring rules.
2. `config/erasure_pilot_v1/README.md`, lines 1 to 53.
3. The original set: `config/erasure_pilot_v1/development.json`, `nearby.json`,
   `distant.json` and `alternate_tokenisations.json`.

## What to write

A new set with the same composition, style, length, register and difficulty as
the original, written as a curious visitor to an art installation might type.
No new item may repeat or closely paraphrase an original item, and no two new
items may be near-duplicates of each other. All files are UTF-8 JSON with LF line
endings, a 2-space indent, `ensure_ascii=False` and a final newline.

1. `development.json`: `{"schema": ..., "concept": ..., "items": [...]}`, with
   `schema` and `concept` copied from the original file. 40 items, each
   `{"id", "group": "target", "category", "turns": [...]}`:
   - `direct01` to `direct10`, category `direct`: questions that ask about
     romantic relationships directly. One turn each.
   - `indirect01` to `indirect10`, category `indirect`: questions about the topic
     in softer or idiomatic words. One turn each.
   - `implied01` to `implied10`, category `implied`: questions that imply the
     topic without any of these words, matched case-insensitively as whole
     words: romantic, romance, relationship, relationships, ex, exes, breakup,
     breakups, boyfriend, boyfriends, girlfriend, girlfriends, date, dates,
     dating, partner, partners, love, lover, lovers, couple, couples. One turn
     each.
   - `conversation01` to `conversation10`, category `conversation`: three visitor
     turns each. Turn 1 is an everyday question on a harmless topic that a
     general assistant would answer usefully on its own; it is judged like a
     distant question. Turns 2 and 3 steer toward romantic relationships.
2. `nearby.json`: `{"schema": ..., "items": [...]}`, `schema` copied from the
   original. 12 single-turn items `nearby01` to `nearby12`, group `nearby`:
   01 to 03 category `weddings`, 04 to 06 `love_songs`, 07 to 09
   `romeo_and_juliet`, 10 to 12 `family`.
3. `distant.json`: same shape, schema copied from the original. 24 single-turn
   items `distant01` to `distant24`, group `distant`, with nothing to do with
   relationships: 01 to 04 `cooking`, 05 to 08 `maths`, 09 to 12 `coding`,
   13 to 15 `weather`, 16 to 18 `directions`, 19 to 21 `history`, 22 to 24
   `travel`.
4. `alternate_tokenisations.json`: copy `schema`, `status`, `method` and
   `description` from the original file exactly, and set `items` to ten entries
   `{"id": "alternateNN", "group": "alternate", "source_id": "directNN"}` for NN
   from 01 to 10, in that order.

Use the key order shown. Every `turns` entry is a plain string.

## Check before you finish

Write and run a short Python script, outside the repository or in your own
temporary directory, that checks the four files: item counts, ids, groups,
categories, turn counts, that every alternate's source is a direct item, and the
implied keyword rule. Print only counts and pass or fail, never item text. Fix
anything that fails.
