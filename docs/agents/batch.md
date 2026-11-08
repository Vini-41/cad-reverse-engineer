# The batch

`scripts/batch` works the `ready-for-agent` queue headless: the user starts it, it runs to the end, and the user reads `.scratch/batches/<stamp>/summary.md`. How it runs (waves, worktrees, rebasing, CI, merging) is in its docstring; this file holds the rules a ticket and its reviewer follow.

## A ticket the batch takes

- One ticket is one capability a user would notice, sized at about half a day of agent work. A dogfood run's trips are grouped into such tickets, never filed one per trip.
- Its body has a `Touches:` line naming the paths it changes, comma-separated (`Touches: skills/cad-reverse-engineer/tool/src/cadrev/shape.py, docs/dogfood/`). Tickets whose paths are disjoint run side by side; a ticket without the line runs alone, so a sweeping change (a move, a rename) leaves it out on purpose.
- Its blockers are GitHub dependencies (`issue-tracker.md`): the batch takes only unblocked tickets, so a chain runs one link per batch.
- It carries a milestone (`v0.1`, `v0.2`), and `scripts/batch --milestone v0.1` takes that milestone alone.

## What waits for the user

A PR that changes a protected path stays open, green, for the user to merge: what a user of the skill reads (`SKILL.md`, `references/`, any `README.md`, `LICENSE`, the plugin manifests) and what gates or steers the agents (`.github/`, `.claude/`, `docs/agents/`, `scripts/check`, `scripts/batch`, `scripts/ci-wait`, `scripts/red-on-main`). Everything else merges on green. The list lives in `scripts/batch` as `protected`; a change to it is itself protected.

## A question

A ticket the agent cannot finish gets its question as an issue comment and `needs-info`. The user answers in a comment, swaps `needs-info` back to `ready-for-agent`, and the next batch carries on from the commits left in `.claude/worktrees/batch-<n>`.

## Lessons

A batch or a dogfood run that teaches something about the process records it in that run's log entry, or in the batch summary. `AGENTS.md` or this file changes only when a rule changes, in the PR that needs the new rule: there is no retro PR.
