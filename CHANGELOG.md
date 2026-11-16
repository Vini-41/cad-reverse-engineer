# Changelog

## Unreleased

From a mechanical engineer's review of v0.1.0.

- **Threads come from the standard tables.** A screw or thread is a thread param, a designation from the ISO metric table or the Unified one (`M3`, `M8x1`, `1/4-20`), which supplies its diameter, pitch, tap drill and clearance hole. The model declares it on a plain hole or shank and never cuts it, cadrev holds that cylinder to the thread's sizes, and a `count` check counts threaded holes, so a stated number of screws is checked without modelling one ([ADR-0018](docs/adr/0018-a-thread-is-named-from-a-standard-table-and-never-cut.md)).
- **Metric or US is asked first.** The skill settles three foundational questions before it builds (the target, metric or US, and the complete model or known first), or answers them from the sources when told to build now. `threads: metric | unified` in project.yaml is the table a proposed thread comes from, and proposed values reuse a standard size the object already has.
- **A drawing of each part, and an isometric view.** `cadrev check` writes `build/isometric.png` and `build/drawings/<part>.png`: three views and an isometric one, dimensioned by the part's own checks at the values as built. `up: y` names the views for an object standing on Y ([ADR-0019](docs/adr/0019-each-part-has-a-drawing-dimensioned-by-its-checks.md)).
- **The report lists checks part by part**, each part's under its drawing, in place of one table of every check; report.json gives each check its `part`.
- **STEP files are true size in any length unit.** A project in inches used to export 25.4 times too small.
- A number before a thread size (`four M3 screws`) is no longer read as cubic metres, and the coverage sweep lists Unified thread sizes.

## v0.1.0

The first release of `cad-reverse-engineer`: a skill and its CLI, `cadrev`, that turn a paper, patent or datasheet into parametric CAD, from a single part up to a mechanism, with every dimension traced to where it came from. It is built for Fable 5.2 and [benchmarked](docs/benchmark.md) across Anthropic's and OpenAI's frontier models.

The [README](README.md) says what it builds, how it works and how to install it. [`examples/`](examples) holds three worked reconstructions, each built by a fresh agent from the skill and its sources alone: a printed centrifuge, a planetary gearbox and a lead-screw stage.
