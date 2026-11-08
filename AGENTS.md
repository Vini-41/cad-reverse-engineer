## This repo

Before planning, read `.scratch/handoff.md` if it exists: it carries the last session's state.

The CLI's source and tests live under `skills/cad-reverse-engineer/tool/`, not at the repo root; `scripts/cadrev` runs it from anywhere.

`scripts/check` is CI run locally: green before every commit. `scripts/check --lint` runs only pyright, ruff and the tests' imports, in seconds: the loop after an edit.

To see new tests go red on the source before the fix, or how that source handles a case (a probe written as a test asserting it), `scripts/red-on-main` runs the tests new or edited since main on the tool source before the fix, uncommitted work included (`-k` picks others, such as a table's new rows): holes go red, guards stay green. It exits 0 on a clean comparison, 1 naming any test misnamed for its colour, 2 when pytest ran no test, and 3 when there is nothing to compare, which CI passes with a notice. `scripts/check` runs it as a step and prints its red/green count, so a green check already shows it; run it alone only for a look mid-fix.

A pure refactor is guarded by `scripts/same-reports`: it compares each example's `build/report.json`, or that of each project dir it is given (a dogfood run's, where no example reaches the code), with the tool source before the refactor and after, checks exactly and findings as a sorted list. With `--no-build` or `--no-coverage` it compares the findings a partial run prints instead.

Dogfood run n, as an issue names it, is `~/Documents/Projects/cadrev/dogfood/run-<n>`; a different path an issue gives for a run is stale.

`skills/cad-reverse-engineer/SKILL.md` and its `references/` are the shipped product: before editing them, load `/writing-for-agents`.

## Agent skills

### Issue tracker

Before any `gh` issue or PR operation, read `docs/agents/issue-tracker.md`.

### Batch

Before writing or regrouping a `ready-for-agent` ticket, or starting `scripts/batch`, read `docs/agents/batch.md`.

### Triage labels

Before applying a triage label, read `docs/agents/triage-labels.md`.

### Domain docs

Before exploring the codebase, read `docs/agents/domain.md`. Single-context: one root `GLOSSARY.md` plus `docs/adr/`.
