# Repro brief

The prompt a dogfood run's trips get before they are filed, word for word, so every finding reaches the tracker with the evidence [issue-tracker.md](../agents/issue-tracker.md) asks of a bug's body. Before the repro:

1. Keep the run's checkout (step 1 of [brief.md](brief.md)) until every repro is done: the repros run the tool at the commit the run used.
2. Give each trip a short slug, and group the trips into agents of one to three findings each, related findings together.
3. For each agent, fill `<checkout>`, `<sha>`, `<n>` and one `## Finding` section per trip below, each with its slug, what the run reported (quoting its report and naming the project file that shows it), the smallest reproduction to try, and the comparison cases to run. List the open issues for `<open issues>` with `gh issue list --state open --limit 100 --json number,title --jq '.[] | "#\(.number) \(.title)"'`. Dispatch the agents in parallel, each a fresh general-purpose subagent given the text between the rules.

---

You are reproducing findings from a dogfood run of the cad-reverse-engineer skill, so each can be filed as a GitHub issue. Handle them one after the other, each in its own directory.

Setup. Let C=`<checkout>`, a detached checkout at `<sha>`. The CLI and its tests are under `$C/skills/cad-reverse-engineer/tool/` (source in `src/cadrev/`). Run the CLI as `$C/scripts/cadrev`, Python as `uv run --project $C/skills/cad-reverse-engineer/tool python ...`, and pytest as `uv run --project $C/skills/cad-reverse-engineer/tool --extra test pytest ...`. Read `$C/GLOSSARY.md` for the terms, `$C/skills/cad-reverse-engineer/references/project-format.md` for the project format, and the tool source as you need it. Let R=`~/Documents/Projects/cadrev/dogfood/repro`: each finding's directory `$R/<slug>` is yours, and every file you make goes there. The dogfood project `~/Documents/Projects/cadrev/dogfood/run-<n>` is evidence: read it and copy from it, and leave it unchanged, as you leave the checkout. Set MPLCONFIGDIR to a `.mpl` folder in your directory if matplotlib complains. `cadrev init <dir>` makes a fresh project; `cadrev check <dir> --no-build` runs the checks that need no build in seconds; `cadrev coverage <dir>` runs the coverage sweep.

## Finding: `<slug>`

`<what the run reported, the reproduction to try, the comparison cases>`

## What to produce, for each finding

An issue needs, for each claim, the `cadrev` command that shows it and the output it printed (trim long output but keep the lines that show the claim), or a pytest probe asserting it, run from the finding's directory. Each claim also needs a comparison case: "the same with X instead gives Y". A claim you read from the code alone is marked *unconfirmed*. Keep the reproduction minimal, in the finding's `repro/` subdirectory, and write every path in REPRO.md relative to the finding's directory, or as `$C`, `$R` or `run-<n>`.

Write REPRO.md in each finding's directory:

1. **Verdict**: CONFIRMED (reproduced), NOT REPRODUCED (say what you tried), NOT A BUG (say why the behaviour is right), or DUPLICATE OF #n (say what this run adds to it).
2. **Title**: a proposed issue title, stated as the behaviour that is wrong, in the style of "The sweep skips a diameter written Ø6 mm".
3. **Claims**: each with its command, output and comparison case.
4. **Cause**: the code location (file:line in the checkout) and why, marked *unconfirmed* where you only read it.
5. **Desired behavior**: what cadrev or the skill should do instead, one line each.
6. **Overlap**: whether one of these open issues already covers it: `<open issues>`.

Spend at most about 40 minutes in all. A NOT REPRODUCED verdict with what you tried is a fine result. Reply with each finding's verdict and title, in a few lines.

---

After the repros, file each CONFIRMED finding (`bug`, or `enhancement` for a missing capability, plus `needs-triage`). Its body opens with one paragraph naming the run (`Found by <agent> dogfood run <n> (<object>, at <sha>)`), what the finding cost the run, and the nearest open issue. Then comes a line saying where the files are (`~/Documents/Projects/cadrev/dogfood/repro/<slug>/`, the commands below run from there), then REPRO.md's Claims, Cause and Desired behavior under those headings. Comment each DUPLICATE on its issue with what the run adds. Each trip's outcome (the issue filed or commented, or why no change) goes in its row of the run's trip table in the object's log.
