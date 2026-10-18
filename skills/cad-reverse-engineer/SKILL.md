---
name: cad-reverse-engineer
description: Reverse-engineer a published object as a parametric build123d model where every dimension traces to a quoted source and is checked against it. Use when asked to rebuild a mechanism, robot, gripper or part from a paper, patent, supplement or datasheet as CAD/STEP.
---

# CAD reverse-engineer

Rebuild a published object as CAD that a reviewer can audit number by number. The **ledger** is the spine: every number the sources state about the object is a verbatim quote (or a hashed figure crop) in `evidence.yaml`; every number the model uses is a parameter in `params.yaml` with a declared **basis**; every source value the geometry should realise is a **check** in `checks.yaml` that compares the built geometry with the ledger. `cadrev check` enforces all of it and writes `build/report.md`.

The honest product is a model whose report separates what the sources state from what the reconstruction chose. "Exact" means every modelled feature traces to a source alone; the report's headline (`N/M parameters trace to sources alone`) says how close a project is. Proposed values are fine when named, with a gap that would close them.

## Tool

The CLI ships in this skill's `tool/` directory and needs [`uv`](https://docs.astral.sh/uv/). Invoke it in full on every call, since shell functions and aliases do not carry between calls:

```bash
uv run -q --project <this skill's base directory>/tool cadrev --help
```

`cadrev` below stands for that command. The first run installs build123d (about a minute). Before writing any project YAML, read [`references/project-format.md`](references/project-format.md).

## Steps

### 1. Scope the target

Ask the user where the project directory goes if they have not said. `cadrev init <dir>`, then write `target:` in project.yaml: the object, the version or iteration, and the configuration. Papers often show earlier iterations next to the reported one; the target names which one the ledger describes.

Done when `target` names one object in one version.

### 2. Register sources

`cadrev source <dir> <file> --id … --kind … --citation …` for the paper, its supplement, and the datasheet of every purchased part the paper names (servos, bearings, springs). Supplements carry the tables; look for them. Videos and drawings are sources too.

Format: `project.yaml` in [`references/project-format.md`](references/project-format.md).

Done when every document the reconstruction will cite is registered and hashed.

### 3. Harvest the ledger

Read every page with `cadrev text <dir> <source>` and every figure with `cadrev figures <dir> <source>` and then the Read tool. For each statement about the object, add an evidence item:

- Copy quotes from `cadrev text` output, which is the text the matcher sees.
- Numbers printed inside figures (dimension labels, scale bars, inset annotations) become image evidence: `cadrev crop` the label, view the crop, write the `reading` exactly as printed.
- Record each disagreement between sources under `conflicts`.
- Skip, with a reason, the dimension-like text that is about something else: test objects, loads, airframe, results.

Format: `evidence.yaml` in [`references/project-format.md`](references/project-format.md).

Done when `cadrev coverage <dir>` reports zero, and every figure has been viewed with its labels ledgered. The sweep sees text only; the figure pass is yours.

### 4. Parameterise

Write params.yaml. Each modelled dimension takes the strongest basis available: `source`, then `derived`, then `measured`, then `proposed`. Give every source param an `interpretation` (axis, envelope or pitch, configuration). Give every proposed param a `rationale` and a `gap` in gaps.yaml phrased as the question that would settle it.

Format: `params.yaml` and `gaps.yaml` in [`references/project-format.md`](references/project-format.md).

Done when every feature the model will need has a param, and `cadrev check <dir> --no-build` shows no param errors.

### 5. Model

Write model.py per [`references/modeling.md`](references/modeling.md): parts in their own frames, datums at every checked feature, the assembly as placed instances.

Done when `cadrev check <dir>` builds every part with no `model-*`, `part-invalid`, `assembly-part` or `param-unused` findings. Failing checks are step 6's job.

### 6. Check against the sources

Add a check for every source value the geometry should realise: `bbox` for envelopes, `distance` between datums for pitches and spacings, `mass` where a mass is stated, `interference` across the assembly. Where a figure shows a modelled part in a near-orthographic view, add an overlay and look at the rendered PNG; record in the param's interpretation what the overlay showed.

When a check goes red, change the model or its params. Evidence changes only to correct a transcription, re-copied from `cadrev text`.

Format: `checks.yaml` and `overlays.yaml` in [`references/project-format.md`](references/project-format.md).

Done when `cadrev check <dir>` prints VERIFIED and no `[unchecked-source]` warning remains.

### 7. Hand over

Report to the user from `build/report.md`: the verified status and headline, the parameters resting on proposed values, open conflicts, and the gaps grouped by `ask` (the `authors` group is a ready list of questions for the corresponding author). List the figure readings awaiting confirmation: the user (or a reviewer they name) checks each crop and writes their own name in `confirmed_by`.

Done when the user has the verified status, the proposed parameters, the open conflicts, the questions grouped by who to ask, and the list of crops waiting for confirmation.
