# Workflow

Matt Pocock's skills drive the work. This file says which lane a change takes, where the user decides, and how the batch takes a ticket.

## Lanes

Pick the lane by size, and name it when you start.

- **Quick fix**: under an hour, one obvious change (a wrong command in `SKILL.md`, a one-function bug). Work it in a session on its own branch with `/tdd` or `/diagnosing-bugs`, then open a PR; it merges on green.
- **Ticket**: about half a day, one capability a user would notice. `/triage` writes its brief; `scripts/batch` builds it.
- **Spec**: several tickets, or a design still open. `/grill-with-docs`, `/to-spec`, then `/to-tickets`, whose breakdown the user approves; `scripts/batch` builds the tickets. For work too foggy to spec, `/wayfinder`.

A dogfood run's trips are grouped into tickets, and the user approves the grouping before any is filed.

## Where the user decides

- What gets built, and in what order: milestones, specs, a ticket breakdown, a trip grouping.
- Any design choice a brief leaves open: the agent stops at `needs-info` with the options and its recommendation.
- Figure readings, and so VERIFIED status.
- A PR that changes a protected path. `protected` in `scripts/batch` holds the list: the shipped skill (`SKILL.md`, `references/`, the plugin manifests, `LICENSE`), the root and `plugin/` READMEs, and what steers or gates agents (`AGENTS.md`, `CODING_STANDARDS.md`, `docs/agents/`, `.githooks/`, `.github/`, `.claude/`, `.agents/`, and the gate scripts). Every other PR merges on green, in any lane.
- The release: its tag, GitHub release and directory submissions.

Agents own the rest: building within an approved brief, its tests, review, CI, labels and close-outs.

## The review sitting

The user clears what waits on them in one daily pass, so route every decision to where it shows there:

- `/triage`, asked for what needs attention.
- `gh issue list --label needs-info`: agents' questions, figure readings, trip groupings.
- `gh pr list`: PRs held on a protected path.
- `scripts/batch --status`: the last batch's summary.

## A ticket the batch takes

- A `Touches:` line names the paths it changes, comma-separated. Tickets with disjoint paths run side by side; a ticket without the line runs alone.
- Its blockers are GitHub dependencies; the batch takes only unblocked tickets.
- It carries a milestone. Start the batch with `--milestone` or issue numbers, since the unfiltered queue also takes a spec issue as a ticket.
- A ticket stopped at a question gets `needs-info` and the question as a comment. The user answers, swaps the label back to `ready-for-agent`, and the next batch carries on from its `batch/<n>` branch.

## Changing the rules

A rule joins `AGENTS.md`, `CODING_STANDARDS.md` or `docs/agents/` once the same mistake has happened twice, in the PR that needs it. A mechanical rule becomes a check in `scripts/check` instead.
