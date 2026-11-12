# Dogfood brief

The prompt a dogfood run's subagent gets, word for word, so every run is briefed and reports alike whatever the object. Each object has one entry under [Objects](#objects) giving its fields, and one run log, `~/Documents/Projects/cadrev/dogfood/<object>-run-log.md`. Before the run:

1. Check out the commit under test as a detached worktree outside the repo: `git worktree add --detach <checkout> <sha>`. The run reads the skill from there.
2. Create the empty project directory `~/Documents/Projects/cadrev/dogfood/run-<n>`, numbered one past the highest `run-<n>` already in that directory: run numbers are shared across objects, and a log can lag its runs.
3. Fill `<checkout>`, `<n>` and the object's fields (`<goal>`, `<sources>`, `<report items>`) below, and dispatch a fresh general-purpose subagent with the text between the rules. An object's fields come from its issue: its goal names every part the issue's acceptance criteria name, and its report items hold one line per criterion, asking what in the project meets it, so a run that misses a criterion reports the miss.

An object's sources that no example holds yet are downloaded to `~/Documents/Projects/cadrev/<object>-sources`, and the object's `sources` field points there. Publisher pages often answer a script with a bot check. Open-access routes that serve files to scripts:

- A paper in PubMed Central: find its PMC id with Europe PMC's search API (`https://www.ebi.ac.uk/europepmc/webservices/rest/search?query=DOI:<doi>&format=json`), then fetch `https://pmc-oa-opendata.s3.amazonaws.com/PMC<id>.1/PMC<id>.1.pdf`.
- A Mendeley Data dataset: `https://data.mendeley.com/public-api/datasets/<id>/files?folder_id=root&version=<v>` lists each file's `download_url` and `sha256_hash`; check each download against its hash. An empty list means the files sit in folders: `https://data.mendeley.com/public-api/datasets/<id>/folders/<v>` lists each folder's `id`, to pass as `folder_id`.

After the run, its report becomes the run's section in the object's log, each trip it names is reproduced and filed as [repro-brief.md](repro-brief.md) says, and then the checkout worktree is removed. An object's first run starts its log, headed as `legclaw-run-log.md` is: the object, the spec and issue behind its runs, and how each run was briefed.

A run that ends VERIFIED PENDING REVIEW, or VERIFIED, becomes `examples/<object>`:

1. Copy its project files and its registered sources, without `build/`.
2. Correct any slip the log records, and record it there.
3. Have the user confirm each figure reading against its crop, under their own name in `confirmed_by`.
4. Write its README: what it shows, its sources and their credit, and the `Expected status:` line that `scripts/check` holds it to. That line is all `scripts/check` needs to check the example. A full `cadrev check` of the example finishes in about 2 minutes on a laptop; make a slower one faster before it is committed.
5. Keep the run's Python as the run wrote it: add the example to the `examples/legclaw` entries in `ruff.toml`, under both `[format] exclude` and `[lint.per-file-ignores]`.

---

Goal: <goal>

Use the skill at `<checkout>/plugin/skills/cad-reverse-engineer/SKILL.md`: read it and follow it, with its `references/`. Run `cadrev` as SKILL.md says.

Sources: <sources>. Read nothing else under that checkout: not `examples/` (apart from those files), not the tool's source or tests, not `docs/`, not `.scratch/`. Don't look in `~/Documents/Projects/cadrev/dogfood/` other than your own directory.

Your project directory: `~/Documents/Projects/cadrev/dogfood/run-<n>` (empty, kept after the run).

No one will answer stage 1's question: build the complete model, and leave `known_first` out of project.yaml.

Work until `cadrev check` ends VERIFIED PENDING REVIEW (figure readings await a human), or VERIFIED where no figure reading is needed, or you are truly stuck. Where the skill is unclear or wrong, or the tool misbehaves (a traceback, a finding you think is false, a rule you had to work around, a step whose instruction didn't match what happened), note it as a trip and keep going if you can.

Report at the end (≤40 lines):

- the final status line and headline counts from `build/report.md`: params by basis, physics count, checks passed, errors, warnings, exact or not;
<report items>
- the readings awaiting confirmation, with their crop paths;
- a numbered list of trips, each with what happened, the command and its short output, and what you did about it.

---

## Objects

### LegClaw

Log: `legclaw-run-log.md`.

- **goal:** reconstruct the full LegClaw, both legs and their mount, with its motion.
- **sources:** (CC-BY) `<checkout>/examples/legclaw-links/sources/Cheng2026_LegClaw.pdf` and `Cheng2026_LegClaw_supplementary.docx` beside it
- **report items:**
  - whether `build/model.mjcf` loaded with every loop closed;
  - joint counts by type, the loops and the gears;
  - each stated range of motion and the `range` check that covers it, and each sweep with its pose count;
  - each Table S2 row, checked or not modelled and why;
  - the total-mass checks, evaluated against stated;

### Centrifuge

Log: `centrifuge-run-log.md`.

- **goal:** reconstruct the mini benchtop centrifuge as a static project, with one rotor variant of your choosing.
- **sources:** (CC-BY) the paper `~/Documents/Projects/cadrev/centrifuge-sources/SomaPoor2022_centrifuge.pdf` and the authors' released STEP and STL files beside it (Mendeley Data, doi:10.17632/sy2vrhj227.1)
- **report items:**
  - which rotor variant you modelled, and why;
  - each released body: registered or not, and shape-checked or skipped, with the reason;
  - each probe, its value, and the params it feeds;
  - each stated or probed diameter and the check that covers it;
  - the mass checks, evaluated against stated;
  - each conflict and its resolution;

### Cell stretcher

Log: `cell-stretcher-run-log.md`.

- **goal:** reconstruct the uniaxial cell stretcher with its lead-screw motion: the stretcher unit with its clamps, and the mould its substrates are cast in.
- **sources:** (CC-BY) the paper `~/Documents/Projects/cadrev/cell-stretcher-sources/Kah2021_cell_stretcher.pdf` and the authors' released laser-cut SVG sheets and STL files beside it (Mendeley Data, doi:10.17632/mgkbmytx63.1)
- **report items:**
  - whether one motor drives both screws or each has its own, quoting the paper, and the chain of gears from each motor to the carriage;
  - each lead gear, its lead param and where it comes from, and the posed check that covers it;
  - the stroke check, the stated value it rests on, and its interpretation;
  - whether `build/model.mjcf` loaded, joint counts by type, and the gears;
  - each region of each cut sheet and each STL body: registered or not, and shape-checked or skipped, with the reason;
  - each probe, its value, and the params it feeds;
  - each conflict and its resolution;

### COMPAct

Log: `compact-run-log.md`.

- **goal:** reconstruct the COMPAct 7.2:1 single-stage planetary gearbox with its motion: the sun, the planets, the ring inside the gearbox casing, and the carrier.
- **sources:** (CC-BY) the paper `~/Documents/Projects/cadrev/compact-sources/Singh2025_COMPAct.pdf` and the authors' released STL files for the 7.2:1 design beside it (MIT, github.com/singhaman1750/COMPAct, `CADs/Actuator_STL_files/sspg_7.2`)
- **report items:**
  - the train: each gear, its tooth count and where it comes from, which member is fixed, input and output, quoting the paper, and the posed `angle` check of the output's turn with the value it compares against;
  - the planet count and the check that covers it;
  - each pitch diameter (sun, planets, ring) and the diameter check that covers it, and the check on the planets' centre distance;
  - each released body: registered or not, and shape-checked or skipped, with the reason; where the ring is and how it is checked;
  - whether `build/model.mjcf` loaded, joint counts by type, and the gears;
  - each probe, its value, and the params it feeds;
  - each conflict and its resolution;
  - how long the final `cadrev check` took;
