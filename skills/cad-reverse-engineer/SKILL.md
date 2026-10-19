---
name: cad-reverse-engineer
description: Reverse-engineer a published object as a parametric build123d model where every dimension traces to a quoted source and is checked against it. Use when asked to rebuild a mechanism, robot, gripper or part from a paper, patent, supplement or datasheet as CAD/STEP.
---

# CAD reverse-engineer

Rebuild a published object as CAD that a reviewer can audit number by number. The **ledger** is the spine: every number the sources state about the object is a verbatim quote (or a hashed figure crop) in `evidence.yaml`; every number the model uses is a parameter in `params.yaml` with a declared **basis**; every source value the geometry should realise is a **check** in `checks.yaml` that compares the built geometry with the ledger. `cadrev check` enforces all of it and writes `build/report.md`.

The honest product is a model whose report separates what the sources state from what the reconstruction chose. Each verification run ends on one status, and the report says whether the project is exact; both are defined under [Statuses](references/project-format.md#statuses). Proposed values are fine when named, with a gap that would close them.

## Tool

The CLI ships in this skill's `tool/` directory and needs [`uv`](https://docs.astral.sh/uv/). Invoke it in full on every call, since shell functions and aliases do not carry between calls:

```bash
uv run -q --project <this skill's base directory>/tool cadrev --help
```

`cadrev` below stands for that command. The first run installs build123d and MuJoCo (about a minute). Before writing any project YAML, read [`references/project-format.md`](references/project-format.md).

## Steps

Each step ends on a criterion `cadrev` confirms: the rules named in brackets are the findings that must be absent, and at every step so are `[project-missing]`, `[yaml-syntax]` and `[schema]`. `cadrev check <dir> --no-build` reports every rule except the build's and the checks'; [Statuses](references/project-format.md#statuses) gives the status such a run ends on.

### 1. Scope the target

Ask the user where the project directory goes if they have not said. `cadrev init <dir>`, then write `target:` in project.yaml: the object, the version or iteration, and the configuration. Papers often show earlier iterations next to the reported one; the target names which one the ledger describes.

Done when `target` names one object in one version and `cadrev check <dir> --no-build` reports no `[target]`, `[format-*]` or `[units]`.

### 2. Register sources

`cadrev source <dir> <file> --id … --kind … --citation …` for the paper, its supplement, and the datasheet of every purchased part the paper names (servos, bearings, springs). Supplements carry the tables; look for them. Videos and drawings are sources too.

Format: `project.yaml` in [`references/project-format.md`](references/project-format.md).

Done when every document the reconstruction will cite is registered and `cadrev check <dir> --no-build` reports no `[source-*]`.

### 3. Harvest the ledger

Read every page with `cadrev text <dir> <source>` and every figure with `cadrev figures <dir> <source>` and then the Read tool. For each statement about the object, add an evidence item:

- Copy quotes from `cadrev text` output, which is the text the matcher sees.
- Numbers printed inside figures about the object (dimension labels, scale bars, inset annotations) become image evidence: `cadrev crop` the label, view the crop, write the `reading` exactly as printed. `crop` takes pixels of the extracted file; when the Read tool shows an image downscaled, multiply by the factor it reports, and confirm in the crop that the whole label is inside.
- Record each disagreement between sources under `conflicts`.
- Skip, with a reason, the stated quantities that are about something else: test objects, loads, test rigs, results.

Format: `evidence.yaml` in [`references/project-format.md`](references/project-format.md).

Done when every figure has been viewed with its labels ledgered, and `cadrev check <dir> --no-build` reports no `[coverage]`, `[quote-not-found]`, `[value-not-in-*]`, `[image-*]`, `[unit-ambiguous]`, `[number-ambiguous]`, `[skip-*]`, `[conflict-ref]` or `[evidence-*]` other than `[evidence-unused]`. The coverage sweep lists only numbers printed with a unit, so the figure pass and the unitless cells of tables are yours.

### 4. Parameterise

Write params.yaml. Each modelled dimension takes the strongest basis available: `source`, then `derived`, then `measured`, then `proposed`. Give every source param an `interpretation` (axis, envelope or pitch, configuration). Give every proposed param a `rationale` and a `gap` in gaps.yaml phrased as the question that would settle it, and every derived param whose `expr` makes a placement choice (centred, flush, pins at the rounded ends) names a gap and says the choice in its `interpretation`.

Format: `params.yaml` and `gaps.yaml` in [`references/project-format.md`](references/project-format.md).

Done when every feature the model will need has a param, and `cadrev check <dir> --no-build` reports no `[param-*]` error and no `[unit-quantity]`. `[evidence-unused]` may remain for values only a check will cover.

### 5. Model, tracer part first

Take one part all the way through before modelling any other: the tracer part. Choose a part with a stated envelope or pitch, model it alone, give it its checks (step 6), and run `cadrev check <dir>` until `build/report.md` shows those checks green. The tracer part proves the whole path, ledger to params to model to checks to report, while a mistake in it costs one part.

Then write the rest of model.py per [`references/modeling.md`](references/modeling.md): parts in their own frames, datums at every checked feature, the assembly as placed instances, and for a mechanism its joints and loops, with each part weighed in params.yaml's [mass model](references/project-format.md#mass-model).

Done when the tracer part's checks went green before a second part was modelled, and `cadrev check <dir>` builds every part with no `[model-*]`, `[part-invalid]`, `[part-mass]`, `[datum-off-solid]`, `[assembly-part]`, `[mjcf-load]` or `[param-unused]`. Red checks on the other parts are step 6's job.

### 6. Check against the sources

Add a check for every source value the geometry should realise: `bbox` for envelopes, `distance` between datums for pitches and spacings (over `instances` where they span parts), `angle` at a datum for stated angles, `mass` where a mass is stated, `interference` across the assembly. A value a source states at a joint angle is checked posed at that angle (`pose`). Where a figure shows a modelled part in a near-orthographic view, add an overlay and look at the rendered PNG; record in the param's interpretation what the overlay showed.

Add the mass check even where its density, `add` or `counts` param is proposed, and keep that value at its rationale rather than tuning it to turn the check green: the check then rests on proposed (`checks.yaml` in [`references/project-format.md`](references/project-format.md#checksyaml)), and the gap is what closes it.

Turn a red check green by changing the model or its params, and record a changed proposed param as `params.yaml` in [`references/project-format.md`](references/project-format.md#paramsyaml) describes. Evidence changes only to correct a transcription, re-copied from `cadrev text`.

Format, including when a check is red and how far its tolerance may loosen: `checks.yaml` and `overlays.yaml` in [`references/project-format.md`](references/project-format.md).

Done when every check is green and `cadrev check <dir>` reports no `[check-*]`, `[loop-open]`, `[overlay-config]`, `[tolerance-cap]`, `[evidence-unused]`, `[unchecked-source]` or other error, so its status is VERIFIED or VERIFIED PENDING REVIEW.

### 7. Hand over

Report to the user from `build/report.md` of a full verification run. State the status in the report's words (NOT VERIFIED, VERIFIED PENDING REVIEW or VERIFIED; a PARTIAL run writes no report to hand over), and call the project exact only when the report prints **Exact**. Then give the headline, the parameters resting on proposed values, open conflicts, and the gaps grouped by `ask` (the `authors` group is a ready list of questions for the corresponding author). List the figure readings awaiting confirmation: the user (or a reviewer they name) checks each crop and writes their own name in `confirmed_by`.

Done when the user has the status and exact as `build/report.json` states them (`status`, `exact`), the proposed parameters (`rests_on_proposed`), the open conflicts (`[conflict-open]`), the questions grouped by who to ask, and the crops waiting for confirmation (`awaiting_confirmation`).
