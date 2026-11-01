# Mandatory experiment memory and commits

After every experimental finding, completed run, evaluation read, method change,
or interpretation change:

1. Append the exact method, inputs, settings, artifact paths, measured results,
   and conclusion to `EXPERIMENTS.md`. Never overwrite an earlier finding;
   append a correction when later evidence changes its interpretation.
2. Update `PROJECT_MEMORY.md` with the current best result, rejected claims,
   active experiment, and next decision gate so another session can resume
   without relying on chat history.
3. Update any user-facing or technical document whose claim is affected.
4. Commit and push those documentation changes before treating the finding as
   integrated or starting a materially different experiment. Stage only files
   belonging to the current work; preserve unrelated user changes.

# Speed and parallel work

Billy asked for this on 1 Nov 2026.

- Work fast, and run independent steps in parallel.
- When a Claude Code manager session has given you a task:
  - Create or edit only the files it assigned to you. Other workers are
    running at the same time.
  - Don't ask Billy anything directly. Report decisions you need in your final
    message.
  - Leave staging and commits to the manager.
- Run independent GPU jobs on separate pods when the task allows it, inside
  the spending limit Billy set. Always record each pod in the spend ledger.

# Autonomous execution

For work in this repository, proceed autonomously and do not pause to ask the
user for confirmation or authorization for ordinary in-scope actions. Treat
the user's standing instruction as approval to run experiments, use the EC2
experiment host, manage experiment processes, synchronize repository changes,
and create, validate, archive, commit, and push project artifacts.

Only request additional user input when a platform-enforced approval cannot be
satisfied by the standing authorization, or when an action would materially
expand beyond the project and experiment systems the user placed in scope.
