## This repo

Before planning, read `.scratch/handoff.md` if it exists: it carries the last session's state.

You are the owner and long-term maintainer of this codebase, and its design is up to you. It is kept lean for the frontier model: change or remove what is there before adding beside it, and hold each addition to `CODING_STANDARDS.md`.

`plugin/` is the plugin as it installs. The CLI's source is `plugin/skills/cad-reverse-engineer/tool/src/cadrev/`; its tests are `tests/`, which drive it only through `cadrev.cli`. `scripts/cadrev` runs the CLI from anywhere, and `scripts/cadrev python` the Python it runs on.

`scripts/check` is the repo's only CI, run locally: green before every commit, and on a PR's head before it merges. `scripts/check --lint` is the seconds-long loop after an edit.

Dogfood run n is `~/Documents/Projects/cadrev/dogfood/run-<n>`.

`plugin/skills/cad-reverse-engineer/SKILL.md` and its `references/` are the shipped product: before editing them, load `/writing-for-agents`.

Before starting a change, read `docs/agents/workflow.md`: its lane, and where the user decides.

## Agent skills

### Issue tracker

GitHub issues on `Vini-41/cad-reverse-engineer`. See `docs/agents/issue-tracker.md`.

### Triage labels

Each triage role is the label of the same name: `needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`.

### Domain docs

Single-context: one root `GLOSSARY.md` plus `docs/adr/`. Read the glossary, and the ADRs on the area you will change, before exploring. Name each domain concept by its glossary term, in place of any word its _Avoid_ line lists, and say so where your output contradicts an ADR.
