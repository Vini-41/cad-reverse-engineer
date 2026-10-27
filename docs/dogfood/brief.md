# Dogfood brief

The prompt a dogfood run's subagent gets, word for word, so every run is briefed and reports alike whatever the object. Each object has one entry under [Objects](#objects) giving its fields, and one run log, `<object>-run-log.md` beside this file. Before the run:

1. Check out the commit under test as a detached worktree outside the repo: `git worktree add --detach <checkout> <sha>`. The run reads the skill from there.
2. Create the empty project directory `~/Documents/Projects/cadrev/dogfood/run-<n>`, numbered one past the highest run in any `*-run-log.md` here: run numbers are shared across objects.
3. Fill `<checkout>`, `<n>` and the object's fields (`<goal>`, `<sources>`, `<report items>`) below, and dispatch a fresh general-purpose subagent with the text between the rules.

After the run, its report becomes the run's section in the object's log, and the checkout worktree is removed. An object's first run starts its log, headed as [legclaw-run-log.md](legclaw-run-log.md) is: the object, the spec and issue behind its runs, and how each run was briefed.

---

Goal: <goal>

Use the skill at `<checkout>/skills/cad-reverse-engineer/SKILL.md`: read it and follow it, with its `references/`. Run `cadrev` as SKILL.md says.

Sources: <sources>. Read nothing else under that checkout: not `examples/` (apart from those files), not the tool's source or tests, not `docs/`, not `.scratch/`. Don't look in `~/Documents/Projects/cadrev/dogfood/` other than your own directory.

Your project directory: `~/Documents/Projects/cadrev/dogfood/run-<n>` (empty, kept after the run).

Work until `cadrev check` ends VERIFIED PENDING REVIEW (figure readings await a human), or VERIFIED where no figure reading is needed, or you are truly stuck. Where the skill is unclear or wrong, or the tool misbehaves (a traceback, a finding you think is false, a rule you had to work around, a step whose instruction didn't match what happened), note it as a trip and keep going if you can.

Report at the end (≤40 lines):

- the final status line and headline counts from `build/report.md`: params by basis, physics count, checks passed, errors, warnings, exact or not;
<report items>
- the readings awaiting confirmation, with their crop paths;
- a numbered list of trips, each with what happened, the command and its short output, and what you did about it.

---

## Objects

### LegClaw

Log: [legclaw-run-log.md](legclaw-run-log.md).

- **goal:** reconstruct the full LegClaw, both legs and their mount, with its motion.
- **sources:** (CC-BY) `<checkout>/examples/legclaw-links/sources/Cheng2026_LegClaw.pdf` and `Cheng2026_LegClaw_supplementary.docx` beside it
- **report items:**
  - whether `build/model.mjcf` loaded with every loop closed;
  - joint counts by type, the loops and the gears;
  - each stated range of motion and the `range` check that covers it, and each sweep with its pose count;
  - each Table S2 row, checked or not modelled and why;
  - the total-mass checks, evaluated against stated;
