## This repo

Before planning, read `.scratch/handoff.md` if it exists: it carries the last session's state.

`plugin/` is the plugin as it installs; the CLI's source lives under `plugin/skills/cad-reverse-engineer/tool/` and its tests in `tests/`. `scripts/cadrev` runs the CLI from anywhere.

`scripts/check` is the repo's only CI, run locally: green before every commit, and on a PR's head before it merges. `scripts/check --lint` is the seconds-long loop after an edit. `scripts/red-on-main` shows which new tests are red on the source before the fix, and `scripts/same-reports` guards a pure refactor; each script's docstring says how.

Dogfood run n is `~/Documents/Projects/cadrev/dogfood/run-<n>`.

`plugin/skills/cad-reverse-engineer/SKILL.md` and its `references/` are the shipped product: before editing them, load `/writing-for-agents`.

Before starting a change, read `docs/agents/workflow.md`: its lane, and where the user decides.

## Agent skills

### Issue tracker

GitHub issues on `Vini-41/cad-reverse-engineer`. See `docs/agents/issue-tracker.md`.

### Triage labels

The five default labels. See `docs/agents/triage-labels.md`.

### Domain docs

Single-context: one root `GLOSSARY.md` plus `docs/adr/`. See `docs/agents/domain.md`.
