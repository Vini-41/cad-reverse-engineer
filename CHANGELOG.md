# Changelog

## Unreleased

- **Format 2: the kinematic model claims nothing about behaviour.** A joint no longer takes `damping`, `stiffness`, `friction` or `spring_rest`, a param no longer takes `physics: true`, and the MJCF carries no spring, damper or friction. A stated stiffness, damping or friction still reads its unit, and is ledgered `scope: not-modeled`. Exact now sets aside a sweep's resolution and nothing else, and the report no longer counts proposed physics values apart (report.json's `physics_proposed` is gone).
- **A stroke check compares with a printed length.** `claim: shortens` and `claim: lengthens` are gone: a source that states only a direction of change is ledgered `scope: context`, its reason saying so. A stroke still takes `from`, for a change in length stated between two poses.
- **Every source is swept.** `coverage: false` is gone: skip what is not about the object, as in any other source.
- **A format-1 project is refused**, with one finding naming cadrev 0.2.0 as the version that reads it. Each removed key is an unknown key, a `[schema]` error, or `[model-return]` for a joint's. Set `format: 2` once a project names none of them.

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
