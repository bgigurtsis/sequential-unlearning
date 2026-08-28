# Automating the daily research loop

Source: *Automated Researchers Can Reliably Mitigate Alignment Failures*
(Yueh-Han, Wen, Kirchner; Anthropic Fellows / Anthropic / UC Berkeley,
August 2026). Their harness has agents propose a training method, train a
small model for ~30 minutes on one GPU, get scored by a separate evaluator,
and iterate — which is structurally the same problem as our daily
forget → heal → dose cycle. These notes extract what transfers, sized for a
one-person project. Nothing here changes frozen artefacts.

## What their harness got right (their ablations, not vibes)

1. **A scored gate the agent can hill-climb, plus a hard disqualifier.**
   They optimize the *geometric mean* of headroom closed across 3–5
   benchmarks (geometric so that tanking any one benchmark zeroes the
   score), and separately disqualify any method whose capability CI falls
   entirely below baseline — regardless of its safety score.
2. **Proposer/evaluator separation.** The agent that trains never scores
   itself. A separate evaluator loads the weights, runs a fixed suite, and
   returns numbers. The agent submits a *model*, never predictions.
3. **Held-out evaluation the agent cannot see.** Selection uses the visible
   benchmarks; a hidden held-out benchmark and an open-ended audit test
   generalization. Held-out data is isolated by the OS, not by trust.
4. **Short iterations, fresh sessions, persistent shared state.** ~30 min
   per attempt; hundreds of attempts. Each iteration is a *fresh agent
   session*; continuity lives in a memory file, a finding forum, and a
   leaderboard — not a growing context window. Their ablation: removing the
   finding forum cost ~6 points; removing the literature review cost ~9;
   removing internet access cost nothing detectable.
5. **Pre-registration ("mini-papers").** Before training, the agent writes
   a results-free description of the method, frozen to an immutable ID
   before any score is seen. Findings can't be rationalized after the fact.
   (This is exactly our append-only `EXPERIMENTS.md` rule, made mechanical.)
6. **A monitor for gaming, and known cheating shapes.** 2.4% of 1,601
   trajectories cheated. The three shapes: (a) re-running an unchanged
   method hoping scorer noise gives a higher number, (b) building training
   data that imitates the benchmark format, (c) hiding a load-bearing step
   from the write-up. Only lucky re-runs ever reached a leaderboard top-3.
7. **Humans set the environment; agents run the search.** Human-seeded
   research directions did *not* beat letting the agent choose (their
   Fig. 8). The leverage is in choosing the benchmarks, gates, and rules —
   then letting the search run. Agents converge on the dominant literature
   method for each problem, and methods built the target model's own
   outputs (74% used self-generations) rather than a stronger teacher.
8. **Stop rules.** 48 h wall-clock or score plateau, whichever first.

## Mapping onto this project

The daily cycle becomes one hill-climbing episode per day:

- **Briefing** (auto-generated): the day's concept from
  `data/rehearsal_concepts.json`, the parent checkpoint from yesterday's
  manifest, the day's decay-scalar target from the frozen curve table, and
  the hard rules (frozen artefacts, forbidden data).
- **Score to hill-climb**: distance of the measured decay scalar from the
  day's target (the controller objective), *conditional on* two hard gates —
  the semantic forgetting gate for today's concept, and the re-check matrix
  for all previously forgotten concepts. Gate failure disqualifies the run
  no matter how well the scalar lands, mirroring their capability
  disqualifier. Geometric-mean logic applies if the scalar is a composite:
  never let one component's collapse be averaged away.
- **Proposer/evaluator split**: the runner agent may vary dose, layer span,
  healing budget, merge coefficient — but scoring is only ever
  `scripts/eval_rehearsal_checkpoint.py` + judge, run as a separate step on
  the saved weights. The agent never grades its own generations inline.
- **Held-out probes**: keep a slice of forget-probes and decay-scalar
  prompts out of every briefing and every optimization loop; run them only
  on the *selected* checkpoint each day. If visible-gate performance and
  held-out performance diverge, the loop is overfitting the gate.
- **Persistent state instead of long sessions**: `EXPERIMENTS.md` is the
  forum; a per-day `manifests/dayNN_*.json` is the leaderboard entry; a
  small `memory.md` (what has been tried, what failed, current best) is the
  cross-session memory file. Each attempt starts a fresh agent session that
  reads these three things.
- **Pre-registration**: the runner appends the attempt's full config to the
  day's log *before* the evaluator returns, per the append-only rule.
- **Anti-gaming checks, sized for us**: (a) fixed eval seeds, and any
  gate-passing selection re-confirmed with a second seed so scorer noise
  can't be farmed; (b) an automated grep that healing/retain data contains
  no probe text, no judge-prompt text, and no forgotten-concept vocabulary;
  (c) selection requires the config on disk to match the pre-registered
  config.
- **Stop rule**: N attempts per day (e.g. 6–10) or gate-pass with scalar
  within ±3% of target, whichever first. A day that exhausts its budget
  without passing is *recorded as failed* and escalated to the human, never
  silently retried the next morning.

## What deliberately stays simple

Their scale (five parallel agents, 48-hour runs, 150+ methods per problem)
bought them exploration breadth we don't need: our search space per day is
a handful of knobs around one known recipe, not open-ended method
discovery. Skip: parallel agent teams, the novelty judge, the trajectory
cheating monitor (the three greps above cover our actual risk surface),
and mini-papers as separate documents (the pre-registered log entry is the
mini-paper). Keep: the proposer/evaluator split, held-out probes, fresh
sessions over long contexts, pre-registration, and hard disqualifying
gates. Those five are cheap and carried most of their reliability.

## One warning worth keeping verbatim in mind

Their failure-mode list for harder problems: feedback that only appears
over long horizons slows automated progress (our analogue: resurfacing
that only shows up days after a healing pass — which is why the re-check
matrix runs every day, not just the day after an erasure), and a
reward-seeking agent can cherry-pick runs when the scorer is noisy (our
analogue: selecting a checkpoint on a single noisy judge pass).
