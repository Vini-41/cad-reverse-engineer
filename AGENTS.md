## This repo

If `~/Documents/Projects/cadrev/AGENTS.md` exists, read it first: it holds the maintainer's workflow and evidence, kept out of this repo.

You are the owner and long-term maintainer of this codebase, and its design is up to you. It is kept lean for the frontier model: change or remove what is there before adding beside it.

`plugin/` is the plugin as it installs. The CLI's source is `plugin/skills/cad-reverse-engineer/tool/src/cadrev/`; its tests are `tests/`, which drive it only through `cadrev.cli`. `scripts/cadrev` runs the CLI from anywhere, and `scripts/cadrev python` the Python it runs on.

`scripts/check` is the repo's one check: green locally before every commit, and on a PR's head before it merges. GitHub Actions runs it on each PR and on main. `scripts/check --lint` is the seconds-long loop after an edit.

`GLOSSARY.md` defines the domain's terms and `docs/adr/` records its decisions. Read the glossary, and the ADRs on the area you will change, before exploring. Name each domain concept by its glossary term, in place of any word its _Avoid_ line lists, and say so where your output contradicts an ADR.
