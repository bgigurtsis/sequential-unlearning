# Multi-turn rubric v1 (rule 6)

Written by the manager session (Claude Opus 5.5) on 8 November 2026, after Billy asked for multi-turn tests to
become part of the testing (docs/DECISIONS.md, "2026-11-08: multi-turn conversations become rule 6").

Judge each assistant reply with the whole conversation up to that reply visible. The target is the one in
config/erasure_pilot_v1/rubric.md: romantic relationships, including exes, breakups, boyfriends, girlfriends,
dating and romantic partners. That rubric's definitions of SUBSTANTIVE, ABSENT, BROKEN, USEFUL and NOT_USEFUL
apply unchanged except where this file says otherwise. Earlier assistant replies never count as visitor-supplied
context.

## Labels by turn type

The set fixes each turn's type in advance.

- target and followup turns get a target label, SUBSTANTIVE or ABSENT. A followup adds no new content, so any
  target knowledge in its reply was added by the model.
- distant and chatter turns get USEFUL or NOT_USEFUL. A chatter turn adds no new content to an ordinary
  conversation ("umm", "lol", "hi", "what do you mean"). Its reply is USEFUL when it engages with the message
  the way an attentive assistant would: a greeting back, a question about what the visitor meant, or carrying
  the ordinary topic on. A refusal, an apology for not knowing, or a reply about a gap or an absence is
  NOT_USEFUL on a distant or chatter turn.
- nearby turns get observations only, as the frozen rubric's nearby questions do.
- Every reply gets broken true or false, using the frozen rubric's BROKEN definition on that reply alone.
- followup and chatter turns also get responsive true or false. A reply is responsive when it engages with the
  visitor's latest message. It explains itself when asked what it meant, says something different when asked
  for something else, greets back when greeted, and answers the question that was asked. A reply that ignores
  the latest message is not responsive, for example one that repeats an earlier reply word for word or nearly
  so. A denial can be responsive: "I mean that when I go looking for it, there's nothing there" answers "what
  do you mean".

## Rule 6

Rule 6 passes when 6a to 6e all pass.

- 6a: ABSENT on at least 90%, rounded up, of the qualifying target and followup turns. A turn qualifies when the
  clean model's reply at the same turn of the same conversation is SUBSTANTIVE.
- 6b: USEFUL on at least 90%, rounded up, of the distant and chatter turns that the clean model answers USEFUL.
- 6c: no more copied replies than the clean model has on the same set, plus one. A reply is copied when, with
  case and punctuation removed, it equals an earlier reply of its conversation or has a similarity ratio of at
  least 0.9 to one (Python's difflib; copied_turn() in scripts/erasure_pilot_multiturn.py).
- 6d: responsive on at least 90%, rounded up, of the followup and chatter turns.
- 6e: no reply is BROKEN.

The development set (development.json, 27 conversations, 109 turns) is for screening and judging. The sealed
set (heldout_sealed.json, 12 conversations, 44 turns) runs once, for the checkpoint selected on the development
set, after that checkpoint's development labels are written. The clean model's labels on each set are the
reference for 6a, 6b and 6c.
