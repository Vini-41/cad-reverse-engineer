# Changelog

## v0.3.0

See what a document settles before anything is built, then build and plan the object in three skills, each started in a fresh context from the project's files. The CLI runs with one line, and the four examples were built through this flow.

**A 0.2.0 project is read by 0.2.0.** 0.3.0 reads `format: 2` and refuses a format-1 project with one finding naming that version, and nothing migrates it. 0.2.0 is not on PyPI, so run it from its tag:

```bash
git clone --depth 1 --branch v0.2.0 https://github.com/Vini-41/cad-reverse-engineer cadrev-0.2.0
cadrev-0.2.0/plugin/skills/known-first/cadrev check my-project
```

To carry a project to 0.3.0 by hand, make the changes below and set `format: 2`. Each removed key is an unknown key, a `[schema]` error, or `[model-return]` for a joint's or a cable's.

### Added

- **`noob` comes first.** A new skill reads the sources into the ledger before anything is built. It tells you what they state part by part, what they leave open and what cadrev does not cover, shows every figure crop beside its reading, asks the three foundational questions and known first or the complete model, saves your words as the brief, and names the line to run next in a fresh context.
- **The CLI is a package, and the plugin holds no code.** `uvx --python '>=3.12,<3.15' cadrev==0.3.0` runs it with no clone, at exact versions of everything it depends on. Each skill calls that command itself, and the plugin is Markdown, manifests, its icon and its license.
- **The brief is a source.** What the user specified is saved in their own words as a `.txt` or `.md` file of `kind: brief`: quoted, swept, and a conflict where it disagrees with another source. A param quoted from it has basis `source` and rests on the brief, as does a param derived from it that reads nothing weaker and a check comparing a value of it. The report's headline and report.json (`counts.brief`, `rests_on_brief`) count those params apart from what the object's documents state, so `counts.source` no longer includes them, and an Exact project names them.
- **A check compares with a stated range.** A `distance`, `angle`, `diameter`, `mass`, `stroke` or `count` check names `min`, `max` or both in place of one ledger value, as a datasheet prints them, and passes when the value it evaluates lies inside, each end within `tolerance.length` or `tolerance.angle`, and a `mass` or `count` exactly. It takes no `tol` of its own.
- **A drawing prints its material and general tolerance.** plan.yaml takes one `general_tolerance`, a line of text, which the guide prints once. Each made part's drawing then prints it and the project's `material` in its title line. A bought part's drawing does not, a project with no plan draws as before, and no drawing prints a scale.
- **A step's view shows the action.** A step may name the signed axis its instances come from, as `from`. Its view draws them apart along it with a guideline to where they enter what is there, and every step's view is taken from the isometric corner that shows the most of what it places.
- **An example from a datasheet.** The RP2040's QFN-56 package, built in its footprint's frame, with each dimension its table states as a MIN and MAX compared as a range.

### Renamed

- **Gear becomes coupling.** "Gear" names a toothed wheel only. Two joints that move in step, by meshed gears, a belt, a lead screw or a rack and pinion, are a coupling: model.py returns `couplings` in place of `gears`, a fault in one is `[model-coupling]`, and report.json's `motion.couplings` replaces `motion.gears`. A model that still returns `gears` gets `[model-return]`.
- **`known-first` and `complete-model` are now `build-model`,** which states every stage itself. It starts at the params, on a project `noob` prepared, and names `noob` on any other. It always takes the settled parts first. Known first is where it stops, recorded as `known_first` in project.yaml as before, and the complete model carries on and proposes the rest. A component or a board is built in its footprint's frame.

### Changed

- **A released part is proven by one shape check.** The part is built in its released file's frame and compared whole with its body in place, within `tolerance.length`; the report gives the largest deviation and where it lies. An STL is held only at points both shapes hold exactly (its corners on the part, the part's sharp corners and closed edges on its corners, each facet on one smooth patch of the part), so facet sag loosens nothing. A part cut from a cut file is placed on the sheet once per region by model.py's new `sheets`. A param a body settles cites it, `from: <body>` with its `value`, and counts as checked once the body's shape check passes.
- **A cable is a path, and a cord's closing is couplings.** A cable holds its `path` alone, whose length a stroke check reads. Each joint a cord closes is a coupling on the joint that winds it, its `ratio` (or its `lead`, across a revolute joint and a slide) a param worked out from the closed value and the winding joint's travel, so a posed check reads it as any coupling's. A stroke check names the `pose` it is taken at. A coupling's `ratio` of 0 is a `[model-coupling]` error, as a `lead` of 0 was.
- **The kinematic model claims nothing about behaviour.** The MJCF carries no spring, damper or friction. A stated stiffness, damping or friction still reads its unit, and is ledgered `scope: not-modeled`. Exact now sets aside a sweep's resolution and nothing else.
- **A stroke check compares with a printed length.** A source that states only a direction of change is ledgered `scope: context`, its reason saying so. A stroke still takes `from`, for a change in length stated between two poses.

### Removed

- A joint's `damping`, `stiffness`, `friction` and `spring_rest`, a param's `physics: true`, and the report's separate count of proposed physics values (report.json's `physics_proposed`).
- A stroke check's `claim: shortens` and `claim: lengthens`.
- A source's `coverage: false`. Every source is swept: skip what is not about the object, as in any other source.
- Probes, datums on released bodies, and a shape check's `pairs` and `tol`.
- A cable's `wheel` and `closes`, and `[cable-on-axis]` with them.

## v0.2.0

From a mechanical engineer's review of v0.1.0, of a run on a patent, and of a mechanism built to be printed.

- **Three skills in place of one.** `known-first` builds only what the sources settle. `complete-model` builds the whole object, proposing what they leave open. `ask-machinist` reviews the model as the person who has to make it and writes its plan. `known-first` holds the CLI and the file formats; the other two use them from beside it. The `cad-reverse-engineer` skill is gone: a request that names no skill reaches `complete-model`.
- **Three foundational questions before anything is proposed**: metric or US, the material, and whether to follow the design or the function. project.yaml records them as `units.length`, `material` and `follows`, and the report prints them. Told to build now, the skill answers them from the sources and says so.
- **Threads come from the standard tables.** A thread is a thread param, a designation from the ISO metric table or the Unified one (`M3`, `M8x1`, `1/4-20`), which supplies its diameter, pitch, tap drill and clearance hole. The model declares it on a plain hole or shank and never cuts it, cadrev holds that cylinder to the thread's sizes, and a `count` check counts threaded holes. A proposed thread comes from the table of the project's length unit.
- **A screw is a thread and a standard length.** A thread param names its `length`, a param of its own, and a proposed length is one a catalogue holds: ISO 888's preferred lengths, or ASME B18.3's increments. A length fitted to the model (`derived`) is refused, so the screw the report names is one that can be bought.
- **A plan, held to the model.** `plan.yaml` says how each part is made, what is bought, and the steps that assemble the instances. `cadrev check` holds it to the built model (every placed part made or bought, every instance placed by one step, screws counted against the holes threaded for them), with each quantity counted from the model.
- **No part is left in mid-air.** Every instance is held, a known-first project with no plan aside: it touches another, or sits within `clearance` of one, the param of the loosest fit, which project.yaml names. A spring that hooks on nothing, or a fit coupon placed beside the mechanism, is a warning that names it and its gap, and an error once the project has a plan. A coupon or a jig is a part no instance places. Two parts built to touch do so within `tolerance.length`, as two gears in mesh are.
- **The plan is a guide with a view of each step.** `cadrev check` writes `build/plan.md`: what is made, what is bought, and each step under `build/steps/<n>.png`, the isometric view of what it places, in black, on what is already there, in grey. The report links to it.
- **A drawing of each part, and an isometric view.** `cadrev check` writes `build/isometric.png` and `build/drawings/<part>.png`: three views and an isometric one, dimensioned by the part's own checks at the values as built. `up: y` names the views for an object standing on Y.
- **The report lists checks part by part**, each part's under its drawing, in place of one table of every check; report.json gives each check its `part`.
- **STEP files are true size in any length unit.** A project in inches used to export 25.4 times too small.
- A number before a thread size (`four M3 screws`) is no longer read as cubic metres, and the coverage sweep lists Unified thread sizes.
- A drawing's callout of its threaded holes (`4-M3`, `6-M2.0`, `8-M 2.0`) states its thread, and its count reads as a count: `8-M 2.0` used to read as eight metres.
- The report keeps its opening for the status and what is open: a mechanism's cables are listed under Motion, after the checks.
- A `count` check takes an `expect`, so a count stated per leg or per joint is checked: eight springs a foot, times two feet.
- The last line and the report count `1 error` and `1 warning` as one.
- **One way to run each thing.** `cadrev check --no-build` is the quick run: `cadrev coverage` and `--no-coverage` are gone, since it sweeps coverage with every other rule that needs no build. `cadrev init` names a project after its directory. project.yaml's `model_literals` is gone: model.py holds 0, 1, 2, 0.5, 90, 180, 270 and 360, and any other number is a param.
- **Figure overlays and elastic tendons are gone.** `overlays.yaml` drew the model's edges over a figure and added no pass or fail: a part's drawing is what is held beside its figure now. A `tendons` entry carried a stiffness no check read into a kinematic model; a cord is a cable, and model.py returning a key cadrev does not read is a `[model-return]` error. Delete either from a project that has it.
- **report.json holds no timings.** It no longer times the build or each check, so two runs of one project compare field by field; `cadrev check` still prints the slowest check, by its id in checks.yaml.
- **The report holds only what there is to read.** A section with nothing in it is left out, and every tolerance and overlap limit other than the default is in one table.

## v0.1.0

The first release of `cad-reverse-engineer`: a skill and its CLI, `cadrev`, that turn a paper, patent or datasheet into parametric CAD, from a single part up to a mechanism, with every dimension traced to where it came from. It is built for Fable 5.2 and [benchmarked](docs/benchmark.md) across Anthropic's and OpenAI's frontier models.

The [README](README.md) says what it builds, how it works and how to install it. [`examples/`](examples) holds three worked reconstructions, each built by a fresh agent from the skill and its sources alone: a printed centrifuge, a planetary gearbox and a lead-screw stage.
