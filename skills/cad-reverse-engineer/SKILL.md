---
name: cad-reverse-engineer
description: Reverse-engineer one published object, from a single part up to a mechanism, as a parametric build123d model where every number traces to a quoted source and every stated value, motion included, is checked against it. Use when asked to rebuild a part, gripper or mechanism from a paper, patent, supplement or datasheet as CAD, STEP or a MuJoCo model.
---

# CAD reverse-engineer

Rebuild a published object as CAD that a reviewer can audit number by number. The **ledger** is the spine: every number the sources state about the object is a verbatim quote (or a hashed figure crop) in `evidence.yaml`; every number the model uses is a parameter in `params.yaml` with a declared **basis**; every source value the geometry should realise is a **check** in `checks.yaml` that compares the built geometry with the ledger. `cadrev check` enforces all of it and writes `build/report.md`. A mechanism also names its joints and loops, and its stated motion is checked on the posed model, which exports to MuJoCo.

The honest product is a model whose report separates what the sources state from what the reconstruction chose. Each verification run ends on one status, and the report says whether the project is exact; both are defined under [Statuses](references/project-format.md#statuses). Proposed values are fine when named, with a gap that would close them.

## Tool

The CLI ships in this skill's `tool/` directory and needs [`uv`](https://docs.astral.sh/uv/). Run it through the `cadrev` script beside this file, by its full path on every call, since shell functions and aliases do not carry between calls:

```bash
<this skill's base directory>/cadrev --help
```

`cadrev` below stands for that path. The first run installs build123d and MuJoCo (about a minute). Before writing any project YAML, read [`references/project-format.md`](references/project-format.md).

A script that writes project YAML (checks repeated per leg, per toe) lives in the project directory, and the file it writes names it in a comment, so the project alone reproduces how the file was written.

## Steps

Each step ends on a criterion `cadrev` confirms: the rules named in brackets are the findings that must be absent, and at every step so are `[project-missing]`, `[yaml-syntax]` and `[schema]`. `cadrev check <dir> --no-build` reports every rule except the build's and the checks'; [Statuses](references/project-format.md#statuses) gives the status such a run ends on.

### 1. Scope the target

Ask the user where the project directory goes if they have not said. `cadrev init <dir>`, then write `target:` in project.yaml: the object, the version or iteration, and the configuration. Papers often show earlier iterations next to the reported one; the target names which one the ledger describes.

Done when `target` names one object in one version and `cadrev check <dir> --no-build` reports no `[target]`, `[format-*]` or `[units]`.

### 2. Register sources

`cadrev source <dir> <file> --id … --kind … --citation …` for the paper, its supplement, and the datasheet of every purchased part the paper names (servos, bearings, springs). Supplements carry the tables; look for them. Videos and drawings are sources too. Geometry the authors released is `--kind geometry`: a STEP, an STL, or a laser-cut SVG sheet (a cut file). Where a part ships as both STEP and STL, register the STEP alone, so one body is not ledgered twice.

Format: `project.yaml` in [`references/project-format.md`](references/project-format.md).

Done when every document the reconstruction will cite is registered and `cadrev check <dir> --no-build` reports no `[source-*]`.

### 3. Harvest the ledger

Read every page with `cadrev text <dir> <source>` and every figure with `cadrev figures <dir> <source>` and then the Read tool. For each statement about the object, add an evidence item:

- Copy quotes from `cadrev text` output, which is the text the matcher sees.
- Numbers printed inside figures about the object (dimension labels, scale bars, inset annotations) become image evidence: `cadrev crop` the label with `--name <name>`, which writes the crop to `figures/crops/<name>.png` and prints the `image` and `image_sha256` the evidence item takes; view the crop, write the `reading` exactly as printed. `crop` takes pixels of the extracted file; when the Read tool shows an image downscaled, multiply by the factor it reports, and confirm in the crop that the whole label is inside.
- Ledger each stated range or angle of motion (a toe that opens 0–40°, a crank's 90° stroke) and each stated physics value (a spring's stiffness) with its `values`, in scope: step 8 reads them into params and checks them.
- Ledger a value stated in several places at each place, with one statement in scope and the rest restatements (`scope` in project-format.md).
- Ledger a **count** (a gear's teeth, a train's planets) as printed, with no unit: Table I's `SSPG [25, 65, 155, 0.5, 3]` is `values: {z_sun: 25, z_planet: 65, z_ring: 155, module: 0.5, n_planets: 3}`. The sweep lists `25 teeth` but never a table cell or `3 planets`, so ledger each count a param or check will use.
- Ledger a stated ratio as its number: "7.2:1" is `values: {ratio: 7.2}`. The sweep never lists a ratio, yet a gearbox's ratio is the headline its posed check compares with (step 7), so ledger every ratio the sources state.
- A `Ø 32.5` or `Ø3` callout is a stated length, a diameter: ledger it for a `diameter` check (step 7).
- Record each disagreement between sources under `conflicts`.
- Skip, with a reason, the stated quantities that are about something else: test objects, loads, test rigs, results.

Format: `evidence.yaml` in [`references/project-format.md`](references/project-format.md), counts under `units` there.

Done when every figure has been viewed with its labels ledgered, every stated ratio and every count a table states about the object is ledgered, and `cadrev check <dir> --no-build` reports no `[coverage]` other than a released body's (step 4 settles those), and no `[quote-not-found]`, `[value-not-in-*]`, `[image-*]`, `[unit-ambiguous]`, `[number-ambiguous]`, `[skip-*]`, `[conflict-ref]` or `[evidence-*]` other than `[evidence-unused]`. The coverage sweep lists only numbers printed with a unit, so the figure pass and the unitless cells of tables are yours.

### 4. Probe released geometry

Where the authors released geometry, it settles values no text states: probe it rather than propose them. A project with no `kind: geometry` source goes to step 5.

- **Datums.** Declare datums on each body you probe or compare, under `datums` in evidence.yaml, at coordinates read from the file: a short script that loads it with build123d (`import_step`), run as `uv run --project <this skill's base directory>/tool python <script>`, or that reads an STL's triangle corners.
- **Probes.** Take each value a body settles (a hole spacing, a bore, an envelope, a thickness) as a probe: `bbox`, `distance`, `angle` or `diameter`, recording the design value (`32.5`, not the file's `32.4999`). A param takes it in step 5 as it takes a quote. A probe restating a quote is `context`; one that differs from a quote is a conflict.
- **STL bodies** hold only flat triangles, so a datum on one lies on a face and a `diameter` probe finds no cylindrical face. Probe a bore as a `distance` between two triangle corners opposite each other across it: the corners lie on the true circle, while a datum mid-facet sits inside it by the facet's sag and is `[datum-off-solid]`. A shape check against an STL body reads that sag too, so give a curved part's check a `tol` of the sag, within its cap.
- **Each body** is compared or skipped. Write a `shape` check of each body against the part that will reproduce it, by at least three datum pairs not on one line; it goes green in step 7, once the part is built. Skip, with a reason, each body that is not part of the device (a fit tester, an arrow, a part of another device). A cut file's bodies are its regions, named `<source>@<x>,<y>` by a point inside, as `[coverage]` prints them; a skip's `within` rectangle sets aside every region inside it, so a sheet's parts of other devices go in one skip.

Format: [Probes](references/project-format.md#probes-released-geometry), the cut file and its skips under `skipped`, and `shape` under `checks.yaml`, all in [`references/project-format.md`](references/project-format.md).

Done when every body of every geometry source is named by a shape check or a skip, every value a body settles that the model will use is probed, and `cadrev check <dir> --no-build` reports no `[coverage]`, `[probe-mismatch]`, `[datum-off-solid]`, `[evidence-anchor]` or `[skip-*]`.

### 5. Parameterise

Write params.yaml. Each modelled dimension takes the strongest basis available: `source` (a quote, a reading or a probe), then `derived`, then `measured`, then `proposed`. A dimension a released body settles takes its probe. A tooth count is a `source` param read as a count, and a gear ratio a `derived` param written from the counts (`z_sun / (z_sun + z_ring)`), so the ratio traces to the table. Give every source param an `interpretation` (axis, envelope or pitch, configuration). Give every proposed param a `rationale` and a `gap` in gaps.yaml phrased as the question that would settle it, and every derived param whose `expr` makes a placement choice (centred, flush, pins at the rounded ends) names a gap and says the choice in its `interpretation`.

Format: `params.yaml` and `gaps.yaml` in [`references/project-format.md`](references/project-format.md).

Joint ranges, poses and physics values wait for step 8, and the mass model's `parts` entries for step 6, where each part gets its entry as it is modelled.

Done when every feature the model will need has a param, and `cadrev check <dir> --no-build` reports no `[param-*]` error and no `[unit-quantity]`. `[evidence-unused]` may remain for values only a check or step 8 will use.

### 6. Model, tracer part first

Take one part all the way through before modelling any other: the tracer part. Choose a part with a stated envelope or pitch, or with a released body its shape check compares as a whole, model it alone, give it its checks (step 7), and run `cadrev check <dir>` until `build/report.md` shows those checks green. The tracer part proves the whole path, ledger to params to model to checks to report, while a mistake in it costs one part.

Then write the rest of model.py per [`references/modeling.md`](references/modeling.md): parts in their own frames, datums at every checked feature (pivots included, which step 8 hinges on), and the assembly as placed instances, built at the configuration the sources measure their angles from. Build every part the sources' parts tables list and every mechanism they state; `scope: not-modeled` is for what [the evidence format](references/project-format.md#evidence-the-ledger) leaves out. Weigh each part in params.yaml's [mass model](references/project-format.md#mass-model) as you model it, never ahead of model.py: a purchased part by its datasheet `mass`, a printed one by `density`.

Done when the tracer part's checks went green before a second part was modelled, and `cadrev check <dir>` builds every part with no `[model-*]`, `[part-invalid]`, `[part-mass]`, `[datum-off-solid]`, `[assembly-part]` or `[param-unused]`. Red checks on the other parts are step 7's job.

### 7. Check against the sources

Add a check for every source value the geometry should realise: `bbox` for envelopes, `distance` between datums for pitches and spacings (over `instances` where they span parts), `angle` at a datum for stated angles, `diameter` at a datum on a cylindrical face for a bore, hub or pitch circle (a `Ø` callout), `count` for a stated number of instances (3 planets), `mass` where a mass is stated, `interference` across the assembly. The `shape` checks step 4 wrote compare each part with its released body. Where a figure shows a modelled part in a near-orthographic view, add an overlay and look at the rendered PNG; record in the param's interpretation what the overlay showed.

Where a source states the numbers a value is worked out from rather than the value itself, compare with `expect`, an expression over ledger values, in place of `evidence` and `key`: a gear's pitch diameter is `expect: "T1.module * T1.z_sun"`, a planet axis's distance from the sun's `T1.module * (T1.z_sun + T1.z_planet) / 2`, a carrier's turn per sun turn `360 / R1.ratio`. `distance`, `angle`, `diameter`, `mass` and `stroke` checks take it ([Worked ledger values](references/project-format.md#worked-ledger-values-expect)). A param never supplies an expected value, so a worked value goes through `expect`.

Check a stated total mass with a mass check that gives no `density` ([mass model](references/project-format.md#mass-model)). Add the mass check even where its density, `add` or `counts` param is proposed, and keep that value at its rationale rather than tuning it to turn the check green: the check then rests on proposed (`checks.yaml` in [`references/project-format.md`](references/project-format.md#checksyaml)), and the gap is what closes it.

Turn a red check green by changing the model or its params, and record a changed proposed param as `params.yaml` in [`references/project-format.md`](references/project-format.md#paramsyaml) describes. Evidence changes only to correct a transcription, re-copied from `cadrev text`.

Format, including when a check is red and how far its tolerance may loosen: `checks.yaml` and `overlays.yaml` in [`references/project-format.md`](references/project-format.md).

Done when every check is green and `cadrev check <dir>` reports no `[check-*]`, `[overlay-config]`, `[tolerance-cap]`, `[unchecked-source]` or other error, and no `[evidence-unused]` but on the motion values step 8 reads. A static object is then VERIFIED or VERIFIED PENDING REVIEW and goes to step 9.

### 8. Joints, tracer loop first

A mechanism moves once its static checks are green. Declare its joints and loops per [`references/modeling.md`](references/modeling.md#joints-and-loops), and its poses, ranges and sweeps per [Poses and the MJCF export](references/project-format.md#poses-and-the-mjcf-export).

Take one closed loop all the way through before declaring any other joint: the tracer loop. Choose a loop with a source value stated at a joint angle (a four-bar's output at a stated input), declare its joints and the loop, pose a check at that angle with the ledger value as its pose, and run `cadrev check <dir>` until MuJoCo loads `build/model.mjcf` and the posed check is green. Where no source states a value at a joint angle, choose a loop whose joint has a stated range and confirm that range with a `range` check instead; with no stated range either, pose an `interference` check across the loop at a proposed angle. The tracer loop proves joints to MJCF to solve to posed check while a mistake costs one loop. A mechanism with no ring (a gearbox, a lead screw) takes its first gear through the same path: its two joints, the gear, and a posed check across it.

Then the rest:

- **Joints and loops** for every other ring, and a posed check for every value a source states at a joint angle or stroke. Give each joint the [type](references/modeling.md#joints-and-loops) of how its child moves, so only what moves gets a drive, and joints a cable wound on a servo wheel closes with a cable, its stated stroke, or a stated direction of change with no length printed, checked by a [`stroke` check](references/project-format.md#poses-and-the-mjcf-export).
- **Gears**, each from the [worked examples](references/modeling.md#joints-and-loops) rather than a convention of your own: a `ratio` gear for meshed gears or a belt; a `lead` gear for a lead screw, a revolute joint driving a slide; a planetary train with one member fixed as a chain of gears, sun to carrier, then carrier to each planet ([worked example](references/project-format.md#worked-example-a-planetary-train)). Check the motion a source states across a gear by a posed `distance` or `angle` check with `from`, the change between two poses: a carrier's turn per sun turn, a carriage's travel per screw turn. An angle check reads 0 to 180° unsigned, so place its datums as the planetary example does, where a sign error moves the angle the other way.
- **Ranges.** Read each stated range into its joint's `source` range params, confirm it with a `range` check that checks them, and sweep interference across each ranged joint ([Ranges and sweeps](references/project-format.md#ranges-and-sweeps)).
- **Physics values** go in the joint or tendon slot that applies them, each a param marked `physics: true` ([Physics values](references/project-format.md#physics-values)). A value no source states is proposed, with a gap.

On a `[loop-open]` or `[joint-range]` at a stated pose or range end, fix the link lengths, the ranges or the as-built zero. Near a toggle (two links collinear) the solve itself can fail on links that do close; report that end to the user rather than trimming a stated range.

Done when the tracer loop's posed check (or the first gear's) went green before a second loop or gear was declared, every stated range has a `range` check, report.md prints **Kinematic**, and `cadrev check <dir>` reports no `[model-joint]`, `[model-loop]`, `[model-gear]`, `[model-cable]`, `[mjcf-load]`, `[loop-open]`, `[joint-range]`, `[part-mass]`, `[param-physics]`, `[unchecked-source]` (a range param included), `[evidence-unused]` or other error, so its status is VERIFIED or VERIFIED PENDING REVIEW.

### 9. Hand over

Report to the user from `build/report.md` of a full verification run. State the status in the report's words (NOT VERIFIED, VERIFIED PENDING REVIEW or VERIFIED; a PARTIAL run writes no report to hand over), and call the project exact only when the report prints **Exact**, with the proposed physics values and sweep resolutions it names beside it. Then give the headline, the parameters resting on proposed values, open conflicts, and the gaps grouped by `ask` (the `authors` group is a ready list of questions for the corresponding author). List the figure readings awaiting confirmation: the user (or a reviewer they name) checks each crop and writes their own name in `confirmed_by`.

Done when the user has the status, exact and the proposed physics values as `build/report.json` states them (`status`, `exact`, `counts.physics_proposed`), the proposed parameters (`rests_on_proposed`), the open conflicts (`[conflict-open]`), the questions grouped by who to ask, and the crops waiting for confirmation (`awaiting_confirmation`).
