---
name: build-model
description: Build the parametric CAD (build123d, STEP, MuJoCo) of a published object from a project the noob skill prepared, every stated value checked on the built model. It builds the settled parts first, then proposes the rest to be made, from standard sizes for the user's units and material; a known-first project stops at the settled parts and lists what waits as questions. Use on a project noob prepared, or to complete a known-first project. A new object starts with noob.
license: MIT
compatibility: Runs its CLI locally through uv on Python 3.12-3.14; the first run downloads build123d, OCC and MuJoCo from PyPI, so it needs network access then.
---

# Build the model

Build a published object from its project, as CAD a reviewer can audit number by number. Three files carry the audit, and `cadrev check` holds them to each other:

- **The ledger** (`evidence.yaml`): every number the sources state about the object, each a verbatim quote or a hashed figure crop. Geometry the authors released is compared whole with the part built from it.
- **The params** (`params.yaml`): every number the model uses, each with its **basis**: `source`, `derived`, `measured` or `proposed`.
- **The checks** (`checks.yaml`): every stated value the geometry should realise, compared on the built model with the ledger, never with the params.

A part is **settled** when the sources settle its every dimension: quoted, worked out from quotes, read off a released body or measured. Every project builds and checks its settled parts first, and then ends one of two ways:

- **Known first** stops there. Every other part **waits** with the question that would settle it, so the model holds only what the sources settle.
- **The complete model** carries on. Each value the sources leave open is **proposed**, chosen to be made, beside the **gap** whose answer would replace it, and every part is built.

The product is an honest report. `build/report.md` shows what the sources settle and what is proposed or waits. A run ends on one [status](references/project-format.md#statuses): VERIFIED means every number is accounted for and every check passes, and nothing about how much the sources left open.

## Tool

The CLI is the `cadrev` script beside this file, and needs [`uv`](https://docs.astral.sh/uv/). Run it by its full path on every call, since shell functions and aliases do not carry between calls:

```bash
<the directory holding this SKILL.md>/cadrev --help
```

`cadrev` below stands for that path. The first run installs build123d and MuJoCo (about a minute).

- `cadrev check <dir>` runs every rule, builds the model, evaluates the checks and writes `build/`: the STEP files, an isometric view, a drawing of each part and the report. `cadrev check <dir> --no-build` runs every rule that needs no build in seconds. Each finding names its rule in brackets and says what is wrong and where.
- Read [`references/project-format.md`](references/project-format.md) before writing project YAML and [`references/modeling.md`](references/modeling.md) before writing model.py. They give the formats; the findings give the rules as you meet them.
- `cadrev python <script>` runs a script of your own on the CLI's Python, with build123d, numpy and matplotlib. One that writes project YAML (checks repeated per instance) lives in the project directory, and the file it writes names it in a comment, so the project alone shows how it was written.

## The project

This skill builds a project the [noob](../noob/SKILL.md) skill prepared. Such a project registers a brief (`kind: brief`), and `cadrev check <dir> --no-build` reports no `[coverage]` finding. On anything else, say that noob has not prepared it, name noob as the skill to run first, and stop.

The project carries what noob read, so start from its files:

- **project.yaml**: the target and the user's answers: `units`, `material`, `follows`, and `known_first` where the build stops at the settled parts. The target is decided, so build the version it names, and take any evidence for another to the hand-over as a question.
- **The ledger**, the **shape checks** in checks.yaml, and **the brief**, the user's own words.
- **gaps.yaml**: a part whose dimension a gap asks for waits. Every other part the ledger or a shape check names is settled, and a gap asking only where it sits leaves it so.
- **`read_bodies.py`**, where the authors released geometry: run it with `cadrev python` for each body's values and frame.

## The work

Take the stages in order: each builds on what the ones before settled. A stage is done when its own criterion holds and `cadrev check` reports nothing about what the stage wrote. A known-first project the user asks to complete starts at stage 5.

### 1. Params

Write params.yaml for the settled parts. Each dimension takes the strongest basis available: `source` (a quote, a reading or a released body), then `derived`, then `measured`.

- A value a released body settles cites the body, `from: <body>` with its `value`, and is checked once the body's shape check passes. So is each number of the frame the part is built in, or of a cut part's place on its sheet.
- A tooth count is a `source` param, and a gear ratio a `derived` param written from the counts, so the ratio traces to the table.
- A screw or a thread the sources state is a [thread param](references/project-format.md#threads): its designation from the ISO metric or the Unified table, which supplies its diameter, its pitch, its tap drill and its clearance hole. A stated screw length is the length param it names.
- **A part waits** where the sources leave one of its dimensions open. It takes no params yet, and its gap in gaps.yaml names the part, so the hand-over can group what waits by part. A dimension you find open that no gap asks about takes a gap of its own. A stated value of a waiting part waits with it.
- Joint ranges and poses wait for stage 4.

In a complete model, `cadrev check` reports what waits as `[evidence-unused]` and `[gap-unused]`, and a settled part held only by a waiting one as `[held]`, until stage 5 builds it. Through stage 4 those findings are expected.

Done when every feature of every settled part has a param, and every waiting part has its gap.

### 2. Model, tracer part first

Take one settled part all the way through before modelling any other, as a tracer bullet: a part with a stated envelope or pitch, or with a released body. Model it alone, give it its checks, and run `cadrev check <dir>` until the report shows them green. It proves the path from ledger to report while a mistake costs one part.

Then build the rest of the settled parts per [`references/modeling.md`](references/modeling.md): each part the sources' parts tables list and each mechanism they state, with a datum at every checked feature and pivot, and its [thread](references/modeling.md#threads) declared on every threaded hole and shank. Weigh each part in the [mass model](references/project-format.md#paramsyaml) as you model it.

A settled part whose place the sources leave open is built in its own frame and placed by no instance, with a gap asking where it sits. Where no part is settled, model.py builds nothing.

Done when every settled part is built and `cadrev check <dir>` reports nothing about the model. Red checks on the other parts are stage 3's.

### 3. Checks

Add a check for every stated value the geometry should realise: `bbox` for an envelope, `distance` for a pitch or spacing, `angle`, `diameter` for a bore or a `Ø` callout, `count` for a stated number of instances or of threaded holes, `mass` for a stated mass, and `interference` across the assembly. Where a source states the numbers a value is worked out from (a pitch diameter from a module and a tooth count), the check compares with [`expect`](references/project-format.md#worked-values-expect). Where a source states a MIN and a MAX, or one of them, the check compares with that [stated range](references/project-format.md#stated-ranges-min-and-max) as printed.

View each part's drawing in `build/drawings/` as its checks turn green. It shows the part in three views with each checked value as a dimension where the check reads it, so a datum on the wrong feature, or a feature no check reads, shows there first. Hold it beside the figures that show the part: an outline or a proportion that differs shows there too.

A check that is red is information. Turn it green by changing the model. The evidence changes only to correct a transcription.

- **A tolerance is what the evidence allows**: an STL's facet sag, a value printed "approximately" or with a ±. Set each `tol` from its evidence and name that evidence in the check's `interpretation`.
- **A check that passes only past that marks a disagreement.** Between the model and a source, revisit the modelling choice behind it. Between two sources (a stated mass against a released body's volume), record the conflict, check the source you build from, and keep the other statement as `context` naming the conflict.
- **A stated mass waits** where its check would weigh a waiting part, or read a density or a count no source states.
- **A range with no nominal leaves the value open**, so the part that needs it waits.

Done when every check is green and the only findings left concern what waits and the motion values stage 4 reads.

### 4. Motion, tracer loop first

A static object has no joints and goes to stage 5. Otherwise declare joints and loops per [modeling.md](references/modeling.md#joints-and-loops), and poses, ranges and sweeps per [project-format.md](references/project-format.md#poses), among built instances alone.

Take a tracer loop first: one closed loop with a value stated at a joint angle (a four-bar's output at a stated input), its joints, and a check posed at that angle, until MuJoCo loads `build/model.mjcf` and the check is green. Without such a value, take a loop whose joint has a stated range and its `range` check. A mechanism with no ring (a gearbox, a lead screw) takes its first coupling the same way.

Then the rest:

- A posed check for every value a source states at a joint angle or stroke, and for motion stated across a coupling (a carrier's turn per sun turn, a carriage's travel per screw turn) a check with `from`. An angle reads unsigned from 0 to 180°, so place its datums where a sign error moves the angle the other way.
- Each stated range read into its joint's range params, confirmed by a `range` check, with an interference `sweep` across the joint.
- Couplings as the worked examples build them ([couplings](references/modeling.md#joints-and-loops), [a planetary train](references/project-format.md#worked-example-a-planetary-train)).
- A cord is a [cable](references/modeling.md#joints-and-loops), a path whose length a `stroke` check reads, and each joint it closes is a coupling on the joint that winds it.
- **Motion waits** where the sources leave a range, a ratio or a pose open: the value waits with its gap, and so does the motion that needs it. Where every joint waits, the model stays static.

Where a stated pose or range end leaves a loop open or pushes a joint out of range, fix the link lengths, the ranges or the as-built zero. Near a toggle (two links collinear) the solve itself can fail on links that do close: report that end to the user rather than trimming a stated range.

Done when every stated range that does not wait has its `range` check, the report says **Kinematic** where a joint is declared, and the only findings left concern what waits.

### 5. Propose what waits

To carry on a known-first project, remove `known_first`: project.yaml already holds its answers.

**A project holding `known_first: true` stops here.** It is done when the status is VERIFIED or VERIFIED PENDING REVIEW, and goes to stage 6.

The complete model carries on, taking each waiting part and value through the stages above, as [Proposing](#proposing) says:

- **Params.** What no source settles is `proposed`, naming the waiting part's gap or one of its own. A value stated only as a range is [derived inside it](references/project-format.md#stated-ranges-min-and-max), with its gap; a screw's length, being bought, is a proposed standard length inside it.
- **Model.** Build and place every part the sources' parts tables list, a settled part whose place was left open among them.
- **Checks.** Each stated value that waited takes its check. A stated total mass keeps its check where a density or a count it reads is proposed. Hold that value at its rationale rather than tuning it until the check passes: the report then shows the check rests on a proposed value, and the gap is what closes it. A proposed param changed to turn any check green names that check in its `rationale`, since the check then confirms the choice rather than a source.
- **Motion.** Propose a range, a ratio or a pose no source states, with its gap, and declare the motion that needs it.

The complete model is done when every part is built and placed, and the status is VERIFIED or VERIFIED PENDING REVIEW.

### 6. Hand over

Report from `build/report.md` of a full run, and show the user `build/isometric.png` and where the part drawings are: an engineer looks at the object before its tables. Give the status in the report's words. Then: the headline counts, the open conflicts, the gaps grouped by `ask` (the `authors` group is a ready list of questions for the corresponding author), each answer given in the user's place, and the figure readings still awaiting confirmation, each crop beside its reading. A reading is confirmed by a person who looked: on the user's word in the conversation, write their name in `confirmed_by`.

- **Known first** adds what waits, from the report's Waiting section and grouped by part. The project and the STEP files in `build/` are the user's to build on, or this skill proposes what waits from stage 5.
- **The complete model** adds the params resting on proposed values, each feature built other than the sources show it, with what it replaces, and each instance the report says floats, with what would hold it. Call the project exact only where the report prints **Exact**.

End on the next step. Once the user accepts the design, the [ask-machinist](../ask-machinist/SKILL.md) skill reviews it as the person who has to make it, and writes its fabrication and assembly plan:

> Clear the context, then run: `Use the ask-machinist skill on <dir>`

Where the request already asks for that plan, or no one answers, carry on with it in this context once the status is VERIFIED or VERIFIED PENDING REVIEW.

## Proposing

A proposed param takes a `rationale` and names a gap in gaps.yaml, phrased as the question that would settle it. Propose as the person who has to make the object would choose:

- **Standard before invented.** A proposed value is one a chart, a catalogue or a stock list holds, in the project's units: a stock thickness, a standard drill for a plain hole, a standard cutter's radius in an inside corner, a standard chamfer on an outside edge. Its `rationale` names the standard or the stock.
- **Bought before made.** What a catalogue sells is bought: a screw, a nut, a pin, a bearing, a spring, a switch. Its `rationale` names it as it is ordered, and the model holds it as its envelope.
- **A screw is a [thread param](references/project-format.md#threads) with a length**: its thread from the project's table and its length a standard one, both held by `cadrev check`. Fit the model to the screw: derive a boss's height and a hole's depth from the screw's length, and size each hole from its thread.
- **One before two.** One screw size serves the object, and one stock thickness, until something stated calls for a second, and the `rationale` says what. A part stays one piece wherever the material lets it be made as one.
- **As shown before as invented.** What a figure shows is built as it shows it. A part keeps its figure's outline and proportions, scaled by the one size proposed for it, and its features: a slotted wheel stays one wheel, with slots.
- **Loose before tight.** A fit between two parts takes a clearance param, proposed for the material as the loosest its function allows. One param serves every fit of its kind, and its gap is `ask: test`. project.yaml names the loosest as its [`clearance`](references/project-format.md#projectyaml). A wall is one the process forms and the part survives.
- **Asked before guessed.** A snap fit, a press fit and a living hinge work by properties of the material that no source gives. Under design, build the form as shown, its gap `ask: test`. Under function, join the parts with screws.

Under **function**, a feature that is hard to make in the material is replaced by one that does the same job more loosely, and the project says so. The `rationale` of what replaces it names the feature and the reason, and a stated value the replacement leaves unbuilt is ledgered `scope: not-modeled`, its `reason` naming what replaced it.
