## This repo

Before planning, read `.scratch/handoff.md` if it exists: it carries the last session's state.

The CLI's source and tests live under `skills/cad-reverse-engineer/tool/`, not at the repo root; `scripts/cadrev` runs it from anywhere.

`scripts/check` is CI run locally: green before every commit.

To tell holes from guards, `scripts/red-on-main` runs the tests new or edited since main on the tool source before the fix (`-k` picks others, such as a table's new rows): holes go red, guards stay green. It exits 0 on a clean comparison, 1 naming any test misnamed for its colour, 2 when pytest ran no test, and 3 when there is nothing to compare, which CI passes with a notice.

`skills/cad-reverse-engineer/SKILL.md` and its `references/` are the shipped product: before editing them, load `/writing-for-agents`.

## Agent skills

### Issue tracker

Before any `gh` issue or PR operation, read `docs/agents/issue-tracker.md`.

### Triage labels

Before applying a triage label, read `docs/agents/triage-labels.md`.

### Domain docs

Before exploring the codebase, read `docs/agents/domain.md`. Single-context: one root `GLOSSARY.md` plus `docs/adr/`.
