## This repo

Before planning, read `.scratch/handoff.md` if it exists: it carries the last session's state.

The CLI's source and tests live under `skills/cad-reverse-engineer/tool/`, not at the repo root.

To tell holes from guards, `scripts/red-on-main -k <tests>` runs the working tree's tests on the tool source before the fix: holes go red, guards stay green.

`skills/cad-reverse-engineer/SKILL.md` and its `references/` are the shipped product: before editing them, load `/writing-for-agents`.

## Agent skills

### Issue tracker

Before any `gh` issue or PR operation, read `docs/agents/issue-tracker.md`.

### Triage labels

Before applying a triage label, read `docs/agents/triage-labels.md`.

### Domain docs

Before exploring the codebase, read `docs/agents/domain.md`. Single-context: one root `GLOSSARY.md` plus `docs/adr/`.
