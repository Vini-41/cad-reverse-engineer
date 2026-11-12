---
name: cad-reverse-engineer
description: Reverse-engineer one published object, from a single part up to a mechanism, as a parametric build123d model where every number traces to a quoted source and every stated value, motion included, is checked against it. Use when asked to rebuild a part, gripper or mechanism from a paper, patent, supplement or datasheet as CAD, STEP or a MuJoCo model.
license: MIT
compatibility: Runs its CLI locally through uv on Python 3.10-3.13; the first run downloads build123d, OCC and MuJoCo from PyPI, so it needs network access then.
---

# CAD reverse-engineer

Rebuild a published object as CAD that a reviewer can audit number by number. The **ledger** is the spine: every number the sources state about the object is a verbatim quote, a hashed figure crop or a probe of released geometry in `evidence.yaml`; every number the model uses is a parameter in `params.yaml` with a declared **basis**; every stated value the geometry should realise is a **check** in `checks.yaml` that compares the built geometry with the ledger, never with the params. `cadrev check` enforces all of it and writes `build/report.md`. A mechanism also names its joints and loops, and its stated motion is checked on the posed model, which exports to MuJoCo.

The product is an honest report: it separates what the sources state from what the reconstruction chose. A proposed value is fine when it is named, beside the gap whose answer would replace it. The status a run ends on, and when a project is exact, are defined under [Statuses](references/project-format.md#statuses).

## Tool

The CLI ships in this skill's `tool/` directory and needs [`uv`](https://docs.astral.sh/uv/). Run the `cadrev` script beside this file by its full path on every call, since shell functions and aliases do not carry between calls:

```bash
<the directory holding this SKILL.md>/cadrev --help
```

`cadrev` below stands for that path. The first run installs build123d and MuJoCo (about a minute). Read [`references/project-format.md`](references/project-format.md) before writing any project YAML, and [`references/modeling.md`](references/modeling.md) before writing model.py.

Each finding names its rule in brackets (`[quote-not-found]`) and says what is wrong and where. A script that writes project YAML (checks repeated per leg, per toe) lives in the project directory, and the file it writes names it in a comment, so the project alone reproduces how the file was written.

## Steps

Take the steps in order: each builds on what the steps before it settled. Each ends when `cadrev check` reports none of the findings the step owns, named in its Done line: `cadrev check <dir> --no-build` through step 5, which runs every rule but the build's and the checks', and `cadrev check <dir>` from step 6. At every step, clear `[yaml-syntax]` and `[schema]` first, since they leave entries out of the run.

### 1. Scope the target

Ask the user where the project directory goes, and which build they want, unless they have said:

- **The complete model**: every part built, each value the sources leave open proposed beside the gap that would close it.
- **Known first**: only the parts whose every dimension the sources settle, built and checked; every other part waits with the question that would settle it ([Known first](#known-first)).

Run `cadrev init <dir>`, then write `target:` in project.yaml: the object, its version or iteration, and its configuration (lid off). Papers often show earlier iterations beside the reported one; the target names the one the ledger describes. A target narrows the object, never its parts: a cut sheet nesting all of a unit's plates is that many parts to build, while a sheet's regions of another unit are skipped in step 4. When step 4 chooses one of several released variants, rewrite the target to name it.

Done when the target names one object in one version, project.yaml sets `known_first: true` exactly when the user chose known first, and there is no `[target]`, `[format-*]` or `[units]`.

### 2. Register sources

Register with `cadrev source <dir> <file> --id … --kind … --citation …` the paper, its supplement (where the tables usually are), any video or drawing, and the datasheet of every purchased part the paper names (servos, bearings, springs). Geometry the authors released is `--kind geometry`: a STEP, an STL, or a laser-cut SVG sheet (a cut file). Where a part ships as both STEP and STL, register the STEP alone, so one body is not ledgered twice.

Done when every document the reconstruction will cite is registered and there is no `[source-*]`.

### 3. Harvest the ledger

Read every page with `cadrev text <dir> <source>`, and view every image `cadrev figures <dir> <source>` lists. Ledger each statement about the object:

- A quote is copied from `cadrev text` output, the text the matcher sees.
- A number printed inside a figure (a dimension label, an inset annotation) is image evidence, and so is a scale bar an overlay or a measured param calibrates from; one that calibrates nothing states nothing about the object and stays out of the ledger. Crop it with `cadrev crop <dir> <image> LEFT TOP RIGHT BOTTOM --name <name>`, which prints the `image` and `image_sha256` the item takes. The box is in pixels of the extracted file, whose width × height `cadrev figures` prints, so scale it from the size you viewed the image at. View the crop, confirm the whole label is inside, and write the `reading` exactly as printed.
- The coverage sweep lists only numbers printed with a unit (`25 teeth`), so a count printed with no count unit (a table cell, `3 planets`) and a ratio are yours to find. Ledger each count a param or check will use, as printed with no unit (Table I's `SSPG [25, 65, 155, 0.5, 3]` is `values: {z_sun: 25, z_planet: 65, z_ring: 155, module: 0.5, n_planets: 3}`), and every ratio the sources state, as its number ("7.2:1" is `values: {ratio: 7.2}`), since a gearbox's posed check compares with it.
- A table cell printed without a unit reads in the project's units. Where the table prints its unit in a header (`(cm)` over `13*13*10`), ledger the cell as printed, scale it through a `derived` param (`t_w * 10`) whose `interpretation` names the header, and check it through `expect` (`T2.W * 10`).
- Stated ranges of motion and physics values (a spring's stiffness) are ledgered too, in scope; step 8 reads them.
- A value stated in several places is ledgered at each, one statement in scope and the rest restatements (`scope` in project-format.md). A disagreement between sources is a conflict. A stated quantity about something else (a test object, a load, a rig, a result) is skipped with a reason.

Done when every figure has been viewed with its labels ledgered, every count a param or check will use and every stated ratio is ledgered, and there is no `[coverage]` but a released body's (step 4 settles those), and no `[quote-not-found]`, `[value-not-in-*]`, `[image-*]`, `[unit-ambiguous]`, `[number-ambiguous]`, `[skip-*]`, `[conflict-ref]` or `[evidence-*]` but `[evidence-unused]`.

### 4. Probe released geometry

Released geometry settles values no text states: probe them rather than propose them. A project with no `kind: geometry` source goes to step 5.

- **Datums** on each body you probe or compare go under `datums` in evidence.yaml, at coordinates read from the file: with a short script that loads it with build123d (`import_step`), run as `uv run --project <the directory holding this SKILL.md>/tool python <script>`, or that reads an STL's triangle corners.
- **Probes** take each value a body settles (a hole spacing, a bore, an envelope, a thickness) as a `bbox`, `distance`, `angle` or `diameter` probe recording the design value (`32.5`, not the file's `32.4999`). A probe restating a quote is `context`; one that differs from a quote is a conflict.
- **An STL body** holds only flat triangles: a datum mid-facet sits inside the true circle by the facet's sag, and a `diameter` probe finds no cylindrical face. Probe a bore as a `distance` between two triangle corners opposite each other across it, since the corners lie on the true circle.
- **Each body** is compared or skipped. A `shape` check, paired by at least three datums not on one line, compares it with the part model.py will build from params to reproduce it ([contract](references/modeling.md#contract)); it goes green in step 7. A body that is not part of the device (a fit tester, a part of another device) is skipped with a reason. A cut file's bodies are its regions, named and skipped as [`skipped`](references/project-format.md#skipped-stated-quantities-that-are-not-about-the-object) says.

Done when every body is named by a shape check or a skip, every value a body settles that the model will use is probed, and there is no `[coverage]`, `[probe-mismatch]`, `[datum-off-solid]`, `[evidence-anchor]` or `[skip-*]`.

### 5. Parameterise

Write params.yaml. Each dimension takes the strongest basis available: `source` (a quote, a reading or a probe), then `derived`, then `measured`, then `proposed`.

- A dimension a released body settles takes its probe. A cut file's dimensions, which no probe reads, are proposed params under one gap. `measured` scales a figure of the object against a reference.
- A tooth count is a `source` param read as a count, and a gear ratio a `derived` param written from the counts (`z_sun / (z_sun + z_ring)`), so the ratio traces to the table.
- Every source param has an `interpretation` (axis, envelope or pitch, configuration). Every proposed param has a `rationale` and a `gap` in gaps.yaml, phrased as the question that would settle it. A derived param whose `expr` makes a placement choice (centred, flush, pins at the rounded ends) names a gap and says the choice in its `interpretation`.

Joint ranges, poses and physics values wait for step 8, and the mass model's entries for step 6.

Done when every feature the model will need has a param, and there is no `[param-*]` error, `[known-first]` or `[unit-quantity]`. `[evidence-unused]` may remain for values only a check or step 8 will use.

### 6. Model, tracer part first

Take one part all the way through before modelling any other, as a tracer bullet: a part with a stated envelope or pitch, or with a released body its shape check compares as a whole. Model it alone, give it its checks (step 7), and run `cadrev check <dir>` until report.md shows them green. It proves the path from ledger to report while a mistake costs one part.

Then write the rest of model.py per [`references/modeling.md`](references/modeling.md): parts in their own frames, datums at every checked feature and pivot, and the assembly as placed instances, built at the configuration the sources measure their angles from. Build every part the sources' parts tables list and every mechanism they state; `scope: not-modeled` is for what [the evidence format](references/project-format.md#evidence-the-ledger) leaves out. Weigh each part in params.yaml's [mass model](references/project-format.md#mass-model) as you model it: a purchased part by its datasheet `mass`, a printed one by `density`.

Done when every part is built and there is no `[model-*]`, `[part-invalid]`, `[part-mass]`, `[datum-off-solid]`, `[assembly-part]` or `[param-unused]`. Red checks on the other parts are step 7's.

### 7. Check against the sources

Add a check for every stated value the geometry should realise, of the kinds [checks.yaml](references/project-format.md#checksyaml) defines: `bbox` for an envelope, `distance` between datums for a pitch, a spacing or a toothed gear's pitch diameter, `angle` for a stated angle, `diameter` for a bore or hub (a `Ø` callout), `count` for a stated number of instances, `mass` for a stated mass, and `interference` across the assembly. Where a source states the numbers a value is worked out from rather than the value (a pitch diameter from a module and a tooth count), the check compares with [`expect`](references/project-format.md#worked-ledger-values-expect), since a param never supplies an expected value. Where a figure shows a modelled part in a near-orthographic view, add an overlay, look at the rendered PNG, and record what it showed in the param's interpretation.

Check a stated total mass with a mass check that gives no `density`, even where its density, `add` or `counts` param is proposed: keep that value at its rationale rather than tuning it to turn the check green, since the check then shows it rests on proposed, and let the gap close it.

Turn a red check green by changing the model or its params, and say so in a changed proposed param's `rationale`, naming the check. Evidence changes only to correct a transcription, re-copied from `cadrev text`.

A `tol` or `tol_rel` is how far the evidence lets a value stray: an STL's facet sag, a STEP body's spline edges off their nominal circles, a value printed "approximately" or with a ±. Set each from its evidence and name it in the check's `interpretation`. A check that passes only past that marks a disagreement. Between the model and a source, revisit the choice behind it: another released variant may match. Between two sources (a stated mass against a released body's volume), record the conflict, check the source you build from, and keep the other statement as `context` naming the conflict.

Done when every check is green, there is no error but `[evidence-unused]` on the motion values step 8 reads, and there is no `[unchecked-source]`, a warning VERIFIED does not wait for. A static object is then VERIFIED or VERIFIED PENDING REVIEW and goes to step 9.

### 8. Joints, tracer loop first

Declare joints and loops per [`references/modeling.md`](references/modeling.md#joints-and-loops), and poses, ranges and sweeps per [Poses and the MJCF export](references/project-format.md#poses-and-the-mjcf-export).

Take a tracer loop first: a loop with a value stated at a joint angle (a four-bar's output at a stated input), its joints, and a check posed at that angle, until MuJoCo loads `build/model.mjcf` and the check is green. Without such a value, take a loop whose joint has a stated range and its `range` check; without either, an `interference` check across the loop at a proposed angle. It proves joints, MJCF, solve and posed check while a mistake costs one loop. A mechanism with no ring (a gearbox, a lead screw) takes its first gear the same way.

Then the rest:

- **Joints and loops** for every other ring, and a posed check for every value a source states at a joint angle or stroke. A joint's type is how its child moves, so only what moves gets a drive. A cable wound on a servo wheel closes its joints, and a `stroke` check compares its stated stroke, or a stated direction of change with no length printed.
- **Gears** follow the worked examples ([joints](references/modeling.md#joints-and-loops), [a planetary train](references/project-format.md#worked-example-a-planetary-train)) rather than a convention of your own. A motion a source states across a gear (a carrier's turn per sun turn, a carriage's travel per screw turn) is a posed `distance` or `angle` check with `from`. An angle check reads 0 to 180° unsigned, so place its datums where a sign error moves the angle the other way.
- **Ranges.** Read each stated range into its joint's `source` range params, confirm it with a `range` check, and sweep interference across the joint ([Ranges and sweeps](references/project-format.md#ranges-and-sweeps)).
- **Physics values** go in the joint or tendon slot that applies them, each a param marked `physics: true` ([Physics values](references/project-format.md#physics-values)). One no source states is proposed, with a gap.

On a `[loop-open]` or `[joint-range]` at a stated pose or range end, fix the link lengths, the ranges or the as-built zero. Near a toggle (two links collinear) the solve itself can fail on links that do close: report that end to the user rather than trimming a stated range.

Done when every stated range has a `range` check, report.md prints **Kinematic**, and there is no error and no `[unchecked-source]` (a range param included), so the status is VERIFIED or VERIFIED PENDING REVIEW.

### 9. Hand over

Report from `build/report.md` of a full verification run (a PARTIAL run writes none). State the status in the report's words, and call the project exact only when the report prints **Exact**, naming the proposed physics values and sweep resolutions beside it. Then give the headline, the parameters resting on proposed values, the open conflicts, the gaps grouped by `ask` (the `authors` group is a ready list of questions for the corresponding author), and the figure readings awaiting confirmation: the user, or a reviewer they name, checks each crop and writes their own name in `confirmed_by`.

Done when the user has what `build/report.json` states: `status`, `exact` and `counts.physics_proposed`, `rests_on_proposed`, the `[conflict-open]` findings, the gaps grouped by `ask`, and `awaiting_confirmation`.

## Known first

[Known first](references/project-format.md#known-first) builds only what the sources settle, so each value they leave open is a gap, never a proposed param. It changes these steps and their Done lines: step 6's every part is every settled part, step 8's every stated range is every range of a joint among built instances, and step 9 is done once the user also has report.json's `waiting`, grouped by part, and has chosen how to go on.

- **5.** Write params for the settled parts alone, and give each waiting part a gap whose question names the part ("What diameter are the finger link's pins?"), so the hand-over can group what waits by part.
- **6.** Model the settled parts alone, the tracer part among them. A settled part whose place in the assembly the sources leave open is built in its own frame and placed by no instance ([the assembly](references/modeling.md#contract)), with a gap asking where it sits. Where no part is settled, model.py builds nothing and the project goes to step 9.
- **7.** Check built parts alone. A stated value of a waiting part waits, and so does a stated mass whose check would weigh a waiting part or read a value the sources leave open.
- **8.** Declare joints, loops, gears and cables among built instances alone. A range, ratio, closed pose or pose angle the sources leave open waits with its gap, and so does the motion that needs it; physics values and a sweep's `steps` are set aside. Where every joint waits, the model stays static and report.md prints **Static**.
- **9.** Hand over the same report, and what waits from report.md's Waiting section (report.json's `waiting`), grouped by part, each part with the gaps whose questions name it. Then ask the user to choose: build on it themselves, since the project and the STEP files in `build/` are theirs (tell them how a value of their own enters it, as [Known first](references/project-format.md#known-first) says); or have you propose the rest, by removing `known_first` and carrying on at step 5 as the complete model.
