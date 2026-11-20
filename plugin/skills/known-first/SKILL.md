---
name: known-first
description: Reverse-engineer one published object, from a single part up to a mechanism, as a parametric build123d model that holds only what its documents settle. Every number is a quoted source value checked on the built model, nothing is proposed, and what the documents leave open is listed as questions. Use when asked to rebuild a part, gripper or mechanism from a paper, patent, supplement or datasheet known first, with nothing guessed.
license: MIT
compatibility: Runs its CLI locally through uv on Python 3.12-3.14; the first run downloads build123d, OCC and MuJoCo from PyPI, so it needs network access then.
---

# Known first

Rebuild what a published object's sources settle, as CAD a reviewer can audit number by number. Three files carry the audit, and `cadrev check` holds them to each other:

- **The ledger** (`evidence.yaml`): every number the sources state about the object, each a verbatim quote, a hashed figure crop, or a probe of geometry the authors released.
- **The params** (`params.yaml`): every number the model uses, each with its **basis**: `source`, `derived` or `measured`.
- **The checks** (`checks.yaml`): every stated value the geometry should realise, compared on the built model with the ledger, never with the params.

A part is **settled** when the sources settle its every dimension: quoted, worked out from quotes, probed or measured. Known first builds and checks the settled parts, and every other part **waits** with the question that would settle it. Nothing is proposed, so the model holds no guess.

The product is an honest report. `build/report.md` shows what the sources settle and lists what waits. A run ends on one [status](references/project-format.md#statuses): VERIFIED means every number is accounted for and every check passes, and nothing about how much the sources left open.

Two skills carry a known-first project on, with this skill's CLI and file formats: `complete-model` proposes what waits and builds the whole object, and `ask-machinist` plans how it is made and put together.

## Tool

The CLI is the `cadrev` script beside this file, and needs [`uv`](https://docs.astral.sh/uv/). Run it by its full path on every call, since shell functions and aliases do not carry between calls:

```bash
<the directory holding this SKILL.md>/cadrev --help
```

`cadrev` below stands for that path. The first run installs build123d and MuJoCo (about a minute).

- `cadrev check <dir>` runs every rule, builds the model, evaluates the checks and writes `build/`: the STEP files, an isometric view, a drawing of each part and the report. `cadrev check <dir> --no-build` runs every rule that needs no build in seconds, for the stages before there is a model. Each finding names its rule in brackets and says what is wrong and where.
- Read [`references/project-format.md`](references/project-format.md) before writing project YAML and [`references/modeling.md`](references/modeling.md) before writing model.py. They give the formats; the findings give the rules as you meet them.
- `cadrev python <script>` runs a script of your own on the CLI's Python, with build123d, numpy and matplotlib. One that writes project YAML (checks repeated per instance) lives in the project directory, and the file it writes names it in a comment, so the project alone shows how it was written.

## The work

Take the stages in order: each builds on what the ones before settled. A stage is done when its own criterion holds and `cadrev check` reports nothing about what the stage wrote.

### 1. Scope

- **The target**: the object, its version and its configuration. Papers often show earlier iterations beside the reported one; the target names the one the ledger describes. A target narrows the object, not its parts: a file holding many parts is that many parts to build.
- **The length unit**: `mm` or `in`, the one the sources print their dimensions in unless the user asked for the other.

Where the sources show several versions and the request names none, ask which, in one message with where the project directory goes. Where no one answers, choose, and say so at the hand-over.

Run `cadrev init <dir>`, write the target and the unit in [project.yaml](references/project-format.md#projectyaml), and add `known_first: true`.

Done when project.yaml holds all three.

### 2. Sources

Register with `cadrev source` the paper, its supplement (where the tables usually are), any video or drawing, and the datasheet of every purchased part the paper names. Geometry the authors released is `--kind geometry`: a STEP, an STL, or a laser-cut SVG sheet.

Done when every document the reconstruction will cite is registered.

### 3. Ledger

Read every page with `cadrev text <dir> <source>`, and view every image `cadrev figures <dir> <source>` writes: each page of a PDF whole, which shows its vector drawings and tables as printed, and each image embedded in it at full resolution. Ledger each statement about the object:

- Copy each quote from `cadrev text` output, the text the matcher sees.
- A number printed only inside a figure is image evidence. Crop its label with `cadrev crop <dir> <image> LEFT TOP RIGHT BOTTOM --name <name>`, which prints the `image` and `image_sha256` the item takes. The box is in pixels of the file you crop, whose size `cadrev figures` prints, so scale it from the size you viewed the image at. View the crop, and write the `reading` exactly as printed. A scale bar is evidence only where a measured param is scaled against it.
- The coverage sweep lists numbers printed with a unit. A count printed without one (a table cell, `3 planets`) and a ratio (`7.2:1`) are yours to find: ledger each one a param or a check will use.
- Stated ranges of motion and physics values (a spring's stiffness) are ledgered too; the motion stage reads them.
- A value stated in several places is ledgered at each, one in scope and the rest restatements. A disagreement between sources is a conflict. A stated quantity about something else (a test object, a load, a rig, a result) is skipped with a reason.

Done when every figure has been viewed and its labels ledgered, and `cadrev check <dir> --no-build` reports nothing about the evidence or its coverage but values not yet used, which the later stages use.

### 4. Released geometry

Geometry the authors released settles values no text states: probe them. A project with none goes to stage 5.

- **Datums** on each body go under `datums` in evidence.yaml, at coordinates read from the file by a short script of your own (`cadrev python <script>`): one that loads the file with build123d, reads an STL's triangle corners, or reads a cut file's contours in the sheet's frame ([project-format.md](references/project-format.md)).
- **Probes** take each value a body settles (a hole spacing, a bore, an envelope, a thickness), recording the design value: `32.5`, not the file's `32.4999`.
- **An STL body** holds only flat triangles: no cylindrical face, no axis, and a point mid-facet sits inside the true circle by the facet's sag. So every input to a [derived datum](references/project-format.md#probes-released-geometry) on it is a triangle corner read from the file, and a curved part's shape check takes a `tol` of that sag. Its routes:
  - **A bore or a fillet:** a `diameter` probe `at` a `circle` datum through three corners on its rim or arc.
  - **A bore's axis or a hole's centre:** that circle datum, whose centre a `distance` or `angle` probe reads.
  - **A feature's phase about an axis:** an `angle` probe `along` the axis, at the bore's circle datum, between a hole's circle datum and the `mid` datum of a tooth's two tip corners.
  - **A count of features about an axis:** an `angle` probe `along` the axis, at the bore's circle datum, between two adjacent features' centres, recording the design value (`60`, not `59.9999`), then a derived param `360 / <that angle's param>`. No probe counts features: the shape check is what confirms the count.
- **Each body** is compared or skipped: a `shape` check against the part model.py will build from params to reproduce it, or a skip with a reason for a body that is not part of the device (a fit tester, a part of another device).

Done when every body is named by a shape check or a skip, and every value a body settles that the model will use is probed.

### 5. Params

Write params.yaml for the settled parts. Each dimension takes the strongest basis available: `source` (a quote, a reading or a probe), then `derived`, then `measured`.

- A tooth count is a `source` param, and a gear ratio a `derived` param written from the counts, so the ratio traces to the table.
- A screw or a thread the sources state is a [thread param](references/project-format.md#threads): its designation from the ISO metric or the Unified table, which supplies its diameter, its pitch, its tap drill and its clearance hole. A stated screw length is the length param it names.
- **A part waits** where the sources leave one of its dimensions open. It takes no params, and a gap in gaps.yaml whose question names the part ("What diameter are the finger link's pins?"), so the hand-over can group what waits by part. A stated value of a waiting part waits with it.
- Joint ranges, poses and physics values wait for stage 8.

Done when every feature of every settled part has a param, and every waiting part has its gap.

### 6. Model, tracer part first

Take one settled part all the way through before modelling any other, as a tracer bullet: a part with a stated envelope or pitch, or with a released body. Model it alone, give it its checks, and run `cadrev check <dir>` until the report shows them green. It proves the path from ledger to report while a mistake costs one part.

Then build the rest of the settled parts per [`references/modeling.md`](references/modeling.md): each part the sources' parts tables list and each mechanism they state, with a datum at every checked feature and pivot, and its [thread](references/modeling.md#threads) declared on every threaded hole and shank. Weigh each part in the [mass model](references/project-format.md#paramsyaml) as you model it.

A settled part whose place the sources leave open is built in its own frame and placed by no instance, with a gap asking where it sits. Where no part is settled, model.py builds nothing.

Done when every settled part is built and `cadrev check <dir>` reports nothing about the model. Red checks on the other parts are stage 7's.

### 7. Checks

Add a check for every stated value the geometry should realise: `bbox` for an envelope, `distance` for a pitch or spacing, `angle`, `diameter` for a bore or a `Ø` callout, `count` for a stated number of instances or of threaded holes, `mass` for a stated mass, and `interference` across the assembly. Where a source states the numbers a value is worked out from (a pitch diameter from a module and a tooth count), the check compares with [`expect`](references/project-format.md#worked-values-expect).

View each part's drawing in `build/drawings/` as its checks turn green. It shows the part in three views with each checked value as a dimension where the check reads it, so a datum on the wrong feature, or a feature no check reads, shows there first. Hold it beside the figures that show the part: an outline or a proportion that differs shows there too.

A check that is red is information. Turn it green by changing the model. The evidence changes only to correct a transcription.

- **A tolerance is what the evidence allows**: an STL's facet sag, a value printed "approximately" or with a ±. Set each `tol` from its evidence and name that evidence in the check's `interpretation`.
- **A check that passes only past that marks a disagreement.** Between the model and a source, revisit the choice behind it: another released variant may match. Between two sources (a stated mass against a released body's volume), record the conflict, check the source you build from, and keep the other statement as `context` naming the conflict.
- **A stated mass waits** where its check would weigh a waiting part, or read a density or a count no source states.

Done when every check is green and the only findings left concern the motion values stage 8 reads. A static object is then VERIFIED or VERIFIED PENDING REVIEW and goes to stage 9.

### 8. Motion, tracer loop first

Declare joints and loops per [modeling.md](references/modeling.md#joints-and-loops), and poses, ranges and sweeps per [project-format.md](references/project-format.md#poses), among built instances alone.

Take a tracer loop first: one closed loop with a value stated at a joint angle (a four-bar's output at a stated input), its joints, and a check posed at that angle, until MuJoCo loads `build/model.mjcf` and the check is green. Without such a value, take a loop whose joint has a stated range and its `range` check. A mechanism with no ring (a gearbox, a lead screw) takes its first gear the same way.

Then the rest:

- A posed check for every value a source states at a joint angle or stroke, and for motion stated across a gear (a carrier's turn per sun turn, a carriage's travel per screw turn) a check with `from`. An angle reads unsigned from 0 to 180°, so place its datums where a sign error moves the angle the other way.
- Each stated range read into its joint's range params, confirmed by a `range` check, with an interference `sweep` across the joint.
- Gears as the worked examples build them ([gears](references/modeling.md#joints-and-loops), [a planetary train](references/project-format.md#worked-example-a-planetary-train)).
- Physics values in the joint that applies them. Only the simulation reads one, so one no source states is `proposed`, with a gap.
- **Motion waits** where the sources leave a range, a ratio or a pose open: the value waits with its gap, and so does the motion that needs it. Where every joint waits, the model stays static.

Where a stated pose or range end leaves a loop open or pushes a joint out of range, fix the link lengths, the ranges or the as-built zero. Near a toggle (two links collinear) the solve itself can fail on links that do close: report that end to the user rather than trimming a stated range.

Done when every stated range that does not wait has its `range` check, the report says **Kinematic** where a joint is declared, and the status is VERIFIED or VERIFIED PENDING REVIEW.

### 9. Hand over

Report from `build/report.md` of a full run, and show the user `build/isometric.png` and where the part drawings are: an engineer looks at the object before its tables. Give the status in the report's words. Then: the headline counts, what waits, from the report's Waiting section and grouped by part, the open conflicts, the gaps grouped by `ask` (the `authors` group is a ready list of questions for the corresponding author), and the figure readings awaiting confirmation. The user, or a reviewer they name, checks each crop and writes their own name in `confirmed_by`: a reading is confirmed by a person who looked.

Then give the user the choice: the project and the STEP files in `build/` are theirs to build on, or the complete-model skill proposes what waits and builds the whole object.
