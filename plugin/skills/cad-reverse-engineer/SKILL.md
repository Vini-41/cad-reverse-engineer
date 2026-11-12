---
name: cad-reverse-engineer
description: Reverse-engineer one published object, from a single part up to a mechanism, as a parametric build123d model where every number traces to a quoted source and every stated value, motion included, is checked against it. Use when asked to rebuild a part, gripper or mechanism from a paper, patent, supplement or datasheet as CAD, STEP or a MuJoCo model.
license: MIT
compatibility: Runs its CLI locally through uv on Python 3.10-3.13; the first run downloads build123d, OCC and MuJoCo from PyPI, so it needs network access then.
---

# CAD reverse-engineer

Rebuild a published object as CAD that a reviewer can audit number by number. Three files carry the audit, and `cadrev check` holds them to each other:

- **The ledger** (`evidence.yaml`): every number the sources state about the object, each a verbatim quote, a hashed figure crop, or a probe of geometry the authors released.
- **The params** (`params.yaml`): every number the model uses, each with its **basis**: `source`, `derived`, `measured` or `proposed`.
- **The checks** (`checks.yaml`): every stated value the geometry should realise, compared on the built model with the ledger, never with the params.

The product is an honest report. `build/report.md` separates what the sources state from what the reconstruction chose, so a proposed value is fine when it is named, beside the **gap** whose answer would replace it. A run ends on one [status](references/project-format.md#statuses): VERIFIED means every number is accounted for and every check passes, and nothing about how much the sources left open.

## Tool

The CLI ships in this skill's `tool/` directory and needs [`uv`](https://docs.astral.sh/uv/). Run the `cadrev` script beside this file by its full path on every call, since shell functions and aliases do not carry between calls:

```bash
<the directory holding this SKILL.md>/cadrev --help
```

`cadrev` below stands for that path. The first run installs build123d and MuJoCo (about a minute).

- `cadrev check <dir>` runs every rule, builds the model, evaluates the checks and writes `build/`. `cadrev check <dir> --no-build` runs the ledger's rules alone in seconds, for the stages before there is a model. Each finding names its rule in brackets and says what is wrong and where.
- Read [`references/project-format.md`](references/project-format.md) before writing project YAML and [`references/modeling.md`](references/modeling.md) before writing model.py. They give the formats; the findings give the rules as you meet them.
- A script that writes project YAML (checks repeated per leg, per toe) lives in the project directory, and the file it writes names it in a comment, so the project alone shows how it was written.

## The work

Take the stages in order: each builds on what the ones before settled. A stage is done when its own criterion holds and `cadrev check` reports nothing about what the stage wrote.

### 1. Scope

Ask the user where the project directory goes and which build they want, unless they have said; with no one to ask, build the complete model.

- **The complete model**: every part built, each value the sources leave open proposed beside the gap that would close it.
- **Known first**: only the parts whose every dimension the sources settle, built and checked; every other part waits with the question that would settle it ([Known first](#known-first)).

Run `cadrev init <dir>` and write `target` in project.yaml: the object, its version and its configuration. Papers often show earlier iterations beside the reported one; the target names the one the ledger describes. A target narrows the object, not its parts: a cut sheet nesting all of a unit's plates is that many parts to build.

### 2. Sources

Register with `cadrev source` the paper, its supplement (where the tables usually are), any video or drawing, and the datasheet of every purchased part the paper names. Geometry the authors released is `--kind geometry`: a STEP, an STL, or a laser-cut SVG sheet.

Done when every document the reconstruction will cite is registered.

### 3. Ledger

Read every page with `cadrev text <dir> <source>`, and view every image `cadrev figures <dir> <source>` extracts. Ledger each statement about the object:

- Copy each quote from `cadrev text` output, the text the matcher sees.
- A number printed only inside a figure is image evidence. Crop its label with `cadrev crop <dir> <image> LEFT TOP RIGHT BOTTOM --name <name>`, which prints the `image` and `image_sha256` the item takes. The box is in pixels of the extracted file, whose size `cadrev figures` prints, so scale it from the size you viewed the image at. View the crop, and write the `reading` exactly as printed. A scale bar is evidence only where an overlay or a measured param calibrates from it.
- The coverage sweep lists numbers printed with a unit. A count printed without one (a table cell, `3 planets`) and a ratio (`7.2:1`) are yours to find: ledger each one a param or a check will use.
- Stated ranges of motion and physics values (a spring's stiffness) are ledgered too; the motion stage reads them.
- A value stated in several places is ledgered at each, one in scope and the rest restatements. A disagreement between sources is a conflict. A stated quantity about something else (a test object, a load, a rig, a result) is skipped with a reason.

Done when every figure has been viewed and its labels ledgered, and `cadrev check <dir> --no-build` reports nothing about the evidence or its coverage but values not yet used, which the later stages use.

### 4. Released geometry

Geometry the authors released settles values no text states: probe them rather than propose them. A project with none goes to stage 5.

- **Datums** on each body go under `datums` in evidence.yaml, at coordinates read from the file by a short script of your own, run as `uv run --project <the directory holding this SKILL.md>/tool python <script>`: one that loads the file with build123d, reads an STL's triangle corners, or reads a cut file's contours in the sheet's frame ([project-format.md](references/project-format.md)).
- **Probes** take each value a body settles (a hole spacing, a bore, an envelope, a thickness), recording the design value: `32.5`, not the file's `32.4999`. A cut file's region is probed in the sheet's plane, between datums on its edges; a hole's centre and diameter are a circle datum through three points of its edge.
- **An STL body** holds only flat triangles. A datum mid-facet sits inside the true circle by the facet's sag, so probe a bore as a `distance` between two triangle corners opposite each other, and give a curved part's shape check a `tol` of that sag.
- **Each body** is compared or skipped: a `shape` check against the part model.py will build from params to reproduce it, or a skip with a reason for a body that is not part of the device (a fit tester, a part of another device).

Done when every body is named by a shape check or a skip, and every value a body settles that the model will use is probed.

### 5. Params

Write params.yaml. Each dimension takes the strongest basis available: `source` (a quote, a reading or a probe), then `derived`, then `measured`, then `proposed`.

- A tooth count is a `source` param, and a gear ratio a `derived` param written from the counts, so the ratio traces to the table.
- A proposed param has a `rationale` and names a gap in gaps.yaml, phrased as the question that would settle it.
- Joint ranges, poses and physics values wait for stage 8.

Done when every feature the model will need has a param.

### 6. Model, tracer part first

Take one part all the way through before modelling any other, as a tracer bullet: a part with a stated envelope or pitch, or with a released body. Model it alone, give it its checks, and run `cadrev check <dir>` until the report shows them green. It proves the path from ledger to report while a mistake costs one part.

Then build the rest per [`references/modeling.md`](references/modeling.md): every part the sources' parts tables list and every mechanism they state, with a datum at every checked feature and pivot. Weigh each part in the [mass model](references/project-format.md#paramsyaml) as you model it.

Done when every part is built and `cadrev check <dir>` reports nothing about the model. Red checks on the other parts are stage 7's.

### 7. Checks

Add a check for every stated value the geometry should realise: `bbox` for an envelope, `distance` for a pitch or spacing, `angle`, `diameter` for a bore or a `Ø` callout, `count` for a stated number of instances, `mass` for a stated mass, and `interference` across the assembly. Where a source states the numbers a value is worked out from (a pitch diameter from a module and a tooth count), the check compares with [`expect`](references/project-format.md#worked-values-expect). Where a figure shows a modelled part in a near-orthographic view, add an overlay and look at the rendered PNG.

A check that is red is information. Turn it green by changing the model or its params, and say so in a changed proposed param's `rationale`. The evidence changes only to correct a transcription.

- **A tolerance is what the evidence allows**: an STL's facet sag, a STEP body's spline edges off their nominal circles, a value printed "approximately" or with a ±. Set each `tol` from its evidence and name that evidence in the check's `interpretation`.
- **A check that passes only past that marks a disagreement.** Between the model and a source, revisit the choice behind it: another released variant may match. Between two sources (a stated mass against a released body's volume), record the conflict, check the source you build from, and keep the other statement as `context` naming the conflict.
- **A stated total mass** gets its mass check even where a density or a count it reads is proposed. Keep that value at its rationale rather than tuning it until the check passes: the report then shows the check rests on a proposed value, and the gap is what closes it.

Done when every check is green and the only findings left concern the motion values stage 8 reads. A static object is then VERIFIED or VERIFIED PENDING REVIEW and goes to stage 9.

### 8. Motion, tracer loop first

Declare joints and loops per [modeling.md](references/modeling.md#joints-and-loops), and poses, ranges and sweeps per [project-format.md](references/project-format.md#poses).

Take a tracer loop first: one closed loop with a value stated at a joint angle (a four-bar's output at a stated input), its joints, and a check posed at that angle, until MuJoCo loads `build/model.mjcf` and the check is green. Without such a value, take a loop whose joint has a stated range and its `range` check. A mechanism with no ring (a gearbox, a lead screw) takes its first gear the same way.

Then the rest:

- A posed check for every value a source states at a joint angle or stroke, and for motion stated across a gear (a carrier's turn per sun turn, a carriage's travel per screw turn) a check with `from`. An angle reads unsigned from 0 to 180°, so place its datums where a sign error moves the angle the other way.
- Each stated range read into its joint's range params, confirmed by a `range` check, with an interference `sweep` across the joint.
- Gears as the worked examples build them ([gears](references/modeling.md#joints-and-loops), [a planetary train](references/project-format.md#worked-example-a-planetary-train)).
- Physics values in the joint or tendon that applies them. One no source states is proposed, with a gap.

Where a stated pose or range end leaves a loop open or pushes a joint out of range, fix the link lengths, the ranges or the as-built zero. Near a toggle (two links collinear) the solve itself can fail on links that do close: report that end to the user rather than trimming a stated range.

Done when every stated range has its `range` check, the report says **Kinematic**, and the status is VERIFIED or VERIFIED PENDING REVIEW.

### 9. Hand over

Report from `build/report.md` of a full run. Give the status in the report's words, and call the project exact only where the report prints **Exact**. Then: the headline counts, the params resting on proposed values, the open conflicts, the gaps grouped by `ask` (the `authors` group is a ready list of questions for the corresponding author), and the figure readings awaiting confirmation. The user, or a reviewer they name, checks each crop and writes their own name in `confirmed_by`: a reading is confirmed by a person who looked.

## Known first

[Known first](references/project-format.md#known-first) builds only what the sources settle, so a value they leave open is a gap rather than a proposed param. It changes the stages this way:

- **Params, model and checks** cover the settled parts alone, the tracer part among them. Each waiting part gets a gap whose question names the part ("What diameter are the finger link's pins?"), so the hand-over can group what waits by part. A stated value of a waiting part waits with it, and so does a stated mass whose check would weigh one.
- **A settled part whose place the sources leave open** is built in its own frame and placed by no instance, with a gap asking where it sits. Where no part is settled, model.py builds nothing.
- **Motion** is declared among built instances alone. A range, ratio or pose the sources leave open waits with its gap, and so does the motion that needs it; where every joint waits, the model stays static.
- **The hand-over** adds what waits, from the report's Waiting section, grouped by part. Then ask the user to choose: build on it themselves, since the project and the STEP files in `build/` are theirs, or have you propose the rest, by removing `known_first` and carrying on at stage 5 as the complete model.
