# Changelog

## Unreleased

From a mechanical engineer's review of v0.1.0, and of a run on a patent.

- **Three skills in place of one.** `known-first` builds only what the sources settle. `complete-model` builds the whole object, proposing what they leave open. `ask-machinist` reviews the model as the person who has to make it and writes its plan. `known-first` holds the CLI and the file formats; the other two use them from beside it. The `cad-reverse-engineer` skill is gone: a request that names no skill reaches `complete-model` ([ADR-0020](docs/adr/0020-three-skills-known-first-the-complete-model-ask-the-machinist.md)).
- **Three foundational questions before anything is proposed**: metric or US, the material, and whether to follow the design or the function. project.yaml records them as `units.length`, `material` and `follows`, and the report prints them. Told to build now, the skill answers them from the sources and says so ([ADR-0021](docs/adr/0021-a-complete-model-is-proposed-to-be-made-and-its-plan-is-held-to-the-model.md)).
- **Threads come from the standard tables.** A thread is a thread param, a designation from the ISO metric table or the Unified one (`M3`, `M8x1`, `1/4-20`), which supplies its diameter, pitch, tap drill and clearance hole. The model declares it on a plain hole or shank and never cuts it, cadrev holds that cylinder to the thread's sizes, and a `count` check counts threaded holes. A proposed thread comes from the table of the project's length unit ([ADR-0018](docs/adr/0018-a-thread-and-a-screw-length-come-from-standard-tables.md)).
- **A screw is a thread and a standard length.** A thread param names its `length`, a param of its own, and a proposed length is one a catalogue holds: ISO 888's preferred lengths, or ASME B18.3's increments. A length fitted to the model (`derived`) is refused, so the screw the report names is one that can be bought.
- **A plan, held to the model.** `plan.yaml` says how each part is made, what is bought, and the steps that assemble the instances. `cadrev check` holds it to the built model (every placed part made or bought, every instance placed by one step, screws counted against the holes threaded for them) and prints it in the report with each quantity counted from the model.
- **A drawing of each part, and an isometric view.** `cadrev check` writes `build/isometric.png` and `build/drawings/<part>.png`: three views and an isometric one, dimensioned by the part's own checks at the values as built. `up: y` names the views for an object standing on Y ([ADR-0019](docs/adr/0019-each-part-has-a-drawing-dimensioned-by-its-checks.md)).
- **The report lists checks part by part**, each part's under its drawing, in place of one table of every check; report.json gives each check its `part`.
- **STEP files are true size in any length unit.** A project in inches used to export 25.4 times too small.
- A number before a thread size (`four M3 screws`) is no longer read as cubic metres, and the coverage sweep lists Unified thread sizes.

## v0.1.0

The first release of `cad-reverse-engineer`: a skill and its CLI, `cadrev`, that turn a paper, patent or datasheet into parametric CAD, from a single part up to a mechanism, with every dimension traced to where it came from. It is built for Fable 5.2 and [benchmarked](docs/benchmark.md) across Anthropic's and OpenAI's frontier models.

The [README](README.md) says what it builds, how it works and how to install it. [`examples/`](examples) holds three worked reconstructions, each built by a fresh agent from the skill and its sources alone: a printed centrifuge, a planetary gearbox and a lead-screw stage.
