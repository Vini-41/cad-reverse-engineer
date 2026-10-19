# Project format

A reconstruction project is a directory of YAML files plus `model.py`. `cadrev init` creates it; `cadrev check` enforces every rule below and names the rule it applies (`[rule-name]`) in each finding.

Before any rule runs, every file is read against the shapes shown here. A file that is not valid YAML is `[yaml-syntax]` (file and line); an entry of the wrong shape (a missing `id`, a param that is a bare number, a non-numeric value, a key not shown here) is `[schema]`, names the file and the entry, and is left out of the run. Quote every free-text value inside a `{…}` entry (an `interpretation`, `rationale` or `reason`), since such notes soon gain a comma: unquoted, `reason: a test load, not the object` ends at the comma and leaves `not the object` as an unknown key. A directory without `project.yaml` is `[project-missing]`, and no report is written.

```
project.yaml    format, sources, units, tolerance, target
evidence.yaml   the ledger: evidence, skipped, conflicts
params.yaml     every number the model uses, with its basis
checks.yaml     geometry checks against evidence
gaps.yaml       what the sources leave undefined
overlays.yaml   optional: model edges drawn over figures
model.py        build123d model; see modeling.md
sources/        registered source files (pinned by sha256)
figures/        extracted images; figures/crops/ holds pinned evidence crops
build/          STEP files, overlays, report.md, report.json; model.mjcf and meshes/ for a model with joints
```

## project.yaml

```yaml
format: 1                # written by `cadrev init`
name: gripper
target: Version-3 two-finger gripper as reported in Doe 2025, fingers open (not the Fig. S4 prototype)
units: {length: mm, angle: deg, mass: g}
tolerance: {length: 0.001, angle: 0.01}
model_literals: [0, 1, 2, -1, 0.5, 90, 180, 270, 360]   # optional; numbers model.py may contain (modeling.md)
sources:
  - id: paper
    kind: paper            # paper | supplement | datasheet | video | drawing | other
    path: sources/x.pdf
    sha256: …              # written by `cadrev source`
    citation: …
    url: https://doi.org/…
    license: CC-BY-4.0
    coverage: false        # optional: exclude from the coverage sweep (e.g. a 200-page catalogue; see `skipped`)
```

`format` is the version of these file formats. A project without it is `[format-missing]`; one with a version this cadrev does not read is `[format-unknown]`. Either way cadrev reads no other project file, every command refuses the project, and no report is written. Joints, loops and `pose` are additions to format 1: a project without them reads as before, so neither needs a new version.

`target` names the object, version and configuration reconstructed; one missing or still starting with `TODO` is `[target]`.

`units` names the project's unit for length, angle, mass, force and time (defaults `mm`, `deg`, `g`, `N`, `s`); torque, pressure, density and speed follow from them (N·mm, N/mm², g/mm³, mm/s by default). A key outside those five, or a unit cadrev does not know or of another quantity (`length: g`), is `[units]`.

**Units come from the quote.** A ledger value is written as printed (`values: {L: 4}` for "4 cm"), and cadrev reads the unit printed right after it, or after a hyphen (`2-in. plate`, `5-mm pin`), and converts the value to the project's units (40 mm) wherever a param `from:`, a check or an overlay uses it; a `value` written on that param is in project units (40). The numbers of a range or product share its last unit ("3–5 mm", "40×8×5 mm"). A value with no unit printed after it, such as a table cell (`37×6.5×5`), is already in project units. `in` and `"` read as inches, except `in` before a determiner ("4 in total", "2 in each leg").

Each use expects one quantity: a `bbox` or `distance` check, an overlay calibration and a param `model.py` reads expect a length (the model may also read an angle); an `angle` check's value expects an angle, in degrees or radians, and is compared in degrees; a mass check's `key` and `add` params expect a mass, its `density` a density. A value printed in a unit of another quantity is `[unit-quantity]`; a param traces to its quote through basis `source`, or through a `derived` expr that only scales one param by constants (`rho * 1000`). A value printed in two different units in one quote, or once with a unit and once without ("4 mm pins in 4 cm links"), is `[unit-ambiguous]`: quote only the part that states it.

Recognised units, spelled-out names included (millimetre, inches, degrees, grams, seconds…):

| quantity | units |
|---|---|
| length | mm, cm, m, µm/um/micron, in/", ft/foot/feet |
| angle | deg/°/◦, rad |
| mass | mg, g, kg |
| force | N, kN, mN, kgf |
| torque | N·m (also Nm, nm), N·mm, N·cm, mN·m, kgf·cm (also kg·cm) |
| pressure | Pa, kPa, MPa (N/mm²), GPa, bar, psi |
| density | g/cm³ (g/cc, g/ml), kg/m³, g/mm³ |
| speed | mm/s, cm/s, m/s, km/h |
| time | ms, s/sec, min, h/hr |
| area | mm², cm², m² (also mm2, mm^2) |
| volume | mm³, cm³ (cc, ml), m³ (also cm3, cm^3) |
| angular speed | rpm (r/min), rad/s |
| fraction, count, charge | % (percent), turns, mAh; kept in SI, so 40% is 0.4 |

Any other word after a number (`12 links`) leaves it in project units.

`tolerance.length` is how closely the model must realise a source value. It is a modelling check, never a manufacturing tolerance. `tolerance.angle` is the same for angle checks, in degrees whatever `units.angle` says (default 0.01). Keep `sources:` the last key: `cadrev source` appends to it. Registering an id that is already listed refreshes its entry instead: the file's `path` and `sha256`, and the `kind`, `citation`, `url` and `license` the command gives. That is how sources are restored into a clone, replaced by a new download, or given a license after the fact. A source whose `license` is CC0-1.0, CC-BY-x.y or CC-BY-SA-x.y gets a `!sources/<file>` line in the project's `.gitignore`, so it is committed and the project reruns from a clone; any other license, or none, leaves the file ignored.

A source's `kind` outside the list above is `[source-kind]`, and an empty `citation` is `[source-citation]`. A `path` with no file is `[source-missing]`, whose message names the `url` to download from; a file whose sha256 differs from the pinned one is `[source-hash]`: after a deliberate change, register it again.

Text formats (quote-checked and swept): PDF, DOCX, TXT, MD, HTML. A text source whose file cannot be read as text is `[source-unreadable]`. Save a web datasheet as HTML or TXT to make it quotable. Video and image files are sources for image evidence only.

## evidence.yaml

### `evidence`: the ledger

One item per statement in a source. Two anchor types:

```yaml
- id: T1-finger-link          # unique; referenced as T1-finger-link.L
  source: supp
  page: 4                      # PDF page (1-based); the quote must be on it
  locator: Table 1             # human locator: table, figure, section, equation
  quote: "Finger link 42×8×4"
  values: {L: 42, H: 8, W: 4}

- id: fig3b-palm
  source: paper
  page: 4
  locator: Fig. 3B, palm inset
  image: figures/crops/fig3b-palm.png
  image_sha256: …              # printed by `cadrev crop`
  reading: "48mm; 30mm; 12mm"  # the label text exactly as printed in the image
  values: {L: 48, W: 30, H: 12}
  confirmed_by: <reviewer>     # written by the human who checked the crop
```

- **quote** is copied from `cadrev text` output. Matching ignores case, whitespace, line-break hyphenation, dash variants and `×`/`x`; everything else must be verbatim. Numbers match whole: a quote starting or ending at a digit never matches inside a larger number ("37 mm" is not found in "137 mm" or "3.7 mm"). Each value must appear as a number in the quote (or reading); a decimal comma is one number (`3,5 mm` is 3.5; a list `1,5,10` stays several), and so is a fraction before a unit (`1/4 inch` and `1/4-in.` are 0.25, `1 1/2 in` is 1.5; a bare `1/50` is two); both ends of a range (`5-10 mm`) count as positive values, and a number labelling a figure, table, equation or section (`Fig. 2`, `Figs. 2 and 3`, `Table S1`, `Eq. (3)`, `Sec. 4.2`) is not a value unless a unit follows it (`section 4 mm thick`; after a label, `in` is the word: `Fig. 2 in`). A cardinal from zero to ninety-nine in words is a number too, matched whole like digits: "Eight tension springs" states 8, "twenty-four bolts" and "twenty four bolts" state 24, and "eight" is not found in "eighteen" or "weight". Ordinals ("first", "twenty-first"), `a`/`an`, words such as "pair", "dozen" or "single", and a word that begins a larger number or a fraction ("one hundred", "two-thirds") are not numbers. A comma before exactly three digits (`1,250`, not `1,250.5`) reads as 1250 or 1.25 by locale, so a value read from it is `[number-ambiguous]`: quote the value where it is printed in another form, or skip it. Write each value as printed; its unit is read from the quote (see `units` above).
- **image** evidence covers numbers that exist only in pixels: figure labels, drawing dimensions, video frames. The crop is hashed so the reviewed image cannot change underneath its reading. Until a named human writes `confirmed_by`, the reading holds the project at VERIFIED PENDING REVIEW (see [Statuses](#statuses)); `build/report.md` lists each such reading beside its crop. Every image item awaits confirmation, whatever its `scope`. The image a `measured` param scales off is image evidence too, and needs no `values`: its `reading` transcribes any label printed in it and names the reference it is scaled against (`no printed labels; scaled on the palm width`), and its reviewer confirms that crop and that reference. Figure labels that are not about the object (test rigs, loads, results) need no evidence item.
- **scope** is optional:
  - `not-modeled` + `reason`: a real statement about the object that this reconstruction does not build (purchased springs, out-of-scope subassemblies). It keeps its `values`, so the report shows what was left unbuilt.
  - `context` + `reason`: a statement that informs interpretation but is not a dimension of any modelled feature (masses in conflict, a kinematic length of uncertain identity). `values` may be omitted.

Each item has a unique `id` (`[evidence-id]`), a registered `source` (`[evidence-source]`) and a `locator` (`[evidence-locator]`), and is anchored by a quote from a text source or by an image + reading (`[evidence-anchor]`). A quote not found in its source, or not on its `page`, is `[quote-not-found]`; a quote from a source of several pages that gives no `page` raises the warning `[quote-page]`, which names the page it was found on. A quoted item needs `values` unless it is `scope: context` (`[evidence-values]`). An image item needs its crop (`[image-missing]`), unchanged since `image_sha256` was printed (`[image-hash]`), and a `reading` (`[image-reading]`). A value that is not a number in its quote is `[value-not-in-quote]`; in its reading, `[value-not-in-reading]`. A `scope` needs a `reason` (`[evidence-scope]`).

Every value of an in-scope item must be used by a param `from:` or covered by a check (`[evidence-unused]`).

### `skipped`: stated quantities that are not about the object

The coverage sweep lists every number, in digits or in words, printed with a unit from the table under `units` (`six turns`; a range or list as one candidate: `3–5 mm`, `1,5,10 mm`), every `a×b×c` product and every thread size (`M3`) in the text sources, leaving out digits inside a name (`L3`) and figure, table, equation or section numbers. Each one must fall inside an evidence quote or a skip; one that does not is `[coverage]`. A source with `coverage: false` is not swept and raises the warning `[coverage-off]`.

```yaml
skipped:
  - {source: paper, page: 12, quote: "servo output torque fixed at 1.2 kg ·cm", reason: "test setting"}
  - {source: supp, from: "Table S4.", to: "Movie S1.", reason: "grasp-test objects"}
  - {source: paper, pages: [12, 13], reason: "experimental methods and test rig"}
```

Skip by quote for single lines, by `from`/`to` for tables and blocks, by `pages` only for pages that carry nothing about the object. Every skip needs a `reason` (`[skip-reason]`) and one of `quote`, `pages` or `from` + `to` (`[skip-anchor]`). A skip's quote, or its `from` and `to`, must be found together on one page (its `page`, when given), copied from `cadrev text` like a quote; a skip that matches nothing is `[skip-not-found]`. Split a block that runs onto the next page into one skip per page.

### `conflicts`

```yaml
conflicts:
  - id: K1
    evidence: [S1-palm, fig3b-palm]
    summary: Fig. S1 gives 44×26×10, Fig. 3B gives 48×30×12.
    resolution: Fig. 3B is the outer envelope of the palm with its covers; S1 is the bare frame.
```

A conflict naming evidence the ledger does not hold is `[conflict-ref]`. A conflict without `resolution` stays the warning `[conflict-open]` and appears in the report as open.

## params.yaml

The only door numbers have into the model: a number written in model.py is `[model-literal]`, and one built there from params as a constant (`atan2(p.h, p.h)`) is `[model-constant]`; [`modeling.md`](modeling.md) says how to meet both.

```yaml
params:
  link_L:   {basis: source,   from: T1-finger-link.L, interpretation: "overall length along part X"}
  pin_d:    {basis: proposed, value: 2, rationale: "common 2 mm pin", gap: G-pins}
  end_margin: {basis: proposed, value: 3, rationale: "pin centres 3 mm in from each end", gap: G-pitch}
  pitch:    {basis: derived,  expr: link_L - 2 * end_margin, value: 34}
  pin_x:    {basis: derived,  expr: link_L / 2, gap: G-pin-x, interpretation: "pin centred along the link"}
  palm_w:   {basis: measured, from: v1-frame-316, value: 30.4, method: "mat grid scale, 10 px/mm", uncertainty: "±1.5 mm"}
```

| basis | required | meaning |
|---|---|---|
| `source` | `from` (an evidence value); `value` optional and must match | stated by a source |
| `derived` | `expr`; `value` optional and must match; `gap` optional, and with it the param rests on proposed and needs `interpretation` | computed from other params; `pi sqrt sin cos tan asin acos atan atan2 radians degrees hypot min max abs` are available |
| `measured` | `from` (an image evidence id), `value`, `method`, `uncertainty`; `gap` optional: the question whose answer would replace the measurement with a stated value | scaled off an image or video frame against a known reference |
| `proposed` | `value`, `rationale`; `gap` expected | a reconstruction choice the sources do not make |

A basis outside these four is `[param-basis]`. A missing requirement is `[param-from]` (`from` names no evidence value, or for `measured` no image evidence), `[param-measured]` or `[param-proposed]`; an `expr` that does not parse, names an undefined param, fails to evaluate or depends on itself is `[param-derived]`, as is a derived param naming a `gap` without an `interpretation`. A `value` that differs from its evidence value or `expr` is `[param-mismatch]`. A proposed param that names no `gap` raises the warning `[param-gap]`. A `gap` on a source param, which has no value for a gap to replace, or one naming a gap gaps.yaml lacks on any other basis, is the error `[param-gap]`.

A proposed param whose value was changed to turn a check green says so in its `rationale`, naming the check: that check now confirms the choice rather than a source.

Write `interpretation` on every `source` or `derived` param whose mapping onto geometry is a choice (which axis, envelope versus pitch, which feature). A derived param whose `expr` makes a placement choice (pins at the centres of the rounded ends, a frame centred in its sole, toes flush with the foot ends) also names the `gap` whose answer would settle it, so the choice rests on proposed rather than on its inputs. A choice that several params share can instead be one proposed param they all read (`end_margin` above).

A derived param naming a gap rests on proposed; any other derived param rests on the weakest basis among the params its `expr` references (proposed < measured < source); an `expr` that references no param (`2.2`, `2 * pi`) is `[param-constant]`. The report's headline counts params by what they rest on.

## checks.yaml

Expected values always come from evidence, so a check compares the geometry with the source, never with params.

```yaml
checks:
  - {id: env-link, kind: bbox, part: finger_link, evidence: T1-finger-link,
     axes: {L: x, H: z, W: y}, interpretation: "L×H×W read as part X×Z×Y"}
  - {id: pitch-link, kind: distance, between: [finger_link.pin_a, finger_link.pin_b],
     evidence: L3-design, key: L3, along: x}          # along is optional
  - {id: tilt-link, kind: angle, between: [finger_link.pin_a, finger_link.pin_b, finger_link.tip],
     evidence: S2-tilt, key: theta, tol: 0.5}          # the angle at pin_b, in degrees
  - {id: env-foot, kind: bbox, instances: [sole_1, frame_1, shaft_1], evidence: T1-foot,
     axes: {H: z}}                                     # their union, in the assembly frame
  - {id: span-feet, kind: distance, instances: [foot_l, foot_r],
     between: [foot_l.pivot, foot_r.pivot], evidence: S2-stance, key: w}
  - {id: gripper-mass, kind: mass, parts: [palm, finger_link], counts: {finger_link: n_links},
     density: resin_density, add: [servo_mass], evidence: fig3b-mass, key: m, tol_rel: 0.15}
  - {id: clear, kind: interference, pairs: [[palm_1, finger_link_1]], max_volume: 0.001}
```

- `bbox`: the part's axis-aligned bounding-box size in its own frame; under `instances`, that of their union in the assembly frame.
- `distance`: between two datums of one part, in that part's frame. Datums of two different parts (`<part>.<feature>` naming different parts) sit in unrelated frames, so without `instances` such a check is `[check-config]`.
- `angle`: `between: [a, vertex, b]`, three datums of one part (the same rule as `distance`); the angle at `vertex` between the directions to `a` and to `b`, in degrees (0 to 180). A datum that coincides with the vertex (within `tolerance.length`) leaves the angle undefined and is `[check-config]`. An angle a source states at another configuration than the one `target` names is checked posed (see [Poses](#poses-and-the-mjcf-export)); a stated range of motion is ledgered as source values and confirmed by a `range` check (see [Ranges and sweeps](#ranges-and-sweeps)).
- `mass`: Σ volume × count × density, plus any `add` params; `tol_rel` is required. Each `counts` entry names the param that counts that part (parts it leaves out count once), so a stated count is ledgered like any other number; a bare number there is `[schema]`. Its `density` and `add` params take their units from the quote (see `units` above). The check reads its `density`, `add` and `counts` params, so they need no read in model.py and no other check.
- `interference`: overlap volume between assembly instances; all pairs when `pairs` is omitted. Needs no evidence. Its result gives the worst overlap, the pair that produced it, and how many pairs it evaluated: `0 over 2145 pairs (all)` when `pairs` is omitted, `0.31 palm_1 ∩ finger_link_1 over 2 pairs (listed)` from a `pairs` list. An interference check with `sweep` is evaluated across a joint's range (see [Ranges and sweeps](#ranges-and-sweeps)). It passes when the overlap is at most `max_volume`, which defaults to `tolerance.length`³. This overlap limit compares with no ledger value, so it is not a tolerance and has no cap, but the report lists beside its check each limit other than cadrev's default: the default `tolerance.length`, 0.001, cubed. A project-wide `tolerance.length` therefore lists every interference check that sets no `max_volume`.

A dimension that spans several parts (an envelope of a subassembly, a spacing between parts) is checked over instances: a `bbox`, `distance` or `angle` check names `instances: [<instance>, ...]` in place of `part`, and is evaluated in the assembly frame, where the instances' `Location`s place them. Its datums are named `<instance>.<feature>`: the instance's part datum `<part>.<feature>`, moved by its `Location`. Under `instances` every name resolves against the assembly, so an instance named like its part is the instance. List each instance the check reads; there are no globs. An unknown instance, a feature its part has no datum for, or an empty list is `[check-config]`; a check naming both `part` and `instances` is `[schema]`. A check of another `kind` is `[check-kind]`; one naming a part, datum, axis or evidence value that does not exist is `[check-config]`. A check whose evaluated value strays from its ledger value by more than its tolerance is `[check-failed]`.

Every datum `build` returns, read by a check or not, lies on its part's solid within `tolerance.length`, else it is `[datum-off-solid]`; [`modeling.md`](modeling.md) says where to place datums.

Each check rests on the weakest basis among the params it reads (proposed < measured < source), or on source when it reads none. report.json gives each check result its `rests_on` and, in `rests_on_params`, the params it reads that rest on that basis; report.md's checks table shows "rests on <basis>: <params>" beside a check resting on less than source. A mass check on a proposed density then confirms the model against the stated mass given that chosen density, not the density itself. What a check rests on leaves its pass/fail and the status unchanged.

`tol` overrides `tolerance.length` for one check, or `tolerance.angle` (degrees) for an angle check. A check's tolerance is capped: `tol` (or the project tolerance, where the check sets none) at 5% of each value the check compares, and `tol_rel` at 0.25; above either is `[tolerance-cap]`. A `range` check's `tol` is capped at 5% of the span between its two ends, since an end is often 0. The report lists every non-default tolerance beside its check: each `tol` other than 0.001 (0.01 for an angle check), and every `tol_rel`, which has no default. Each source param that no check covers raises `[unchecked-source]`.

## Poses and the MJCF export

A model whose `build` returns `joints` and `loops` ([`modeling.md`](modeling.md)) moves. A check posed at joint values names them in `pose`, each joint mapped to a param or a ledger value `<evidence>.<key>`, never a bare number (`[schema]`):

```yaml
  - {id: reach-30, kind: distance, instances: [ground_1, rocker_1], between: [ground_1.a, rocker_1.a],
     evidence: S3-sweep, key: AC, pose: {input: S3-sweep.turn}}
```

- **A pose value is a rotation from the assembly as built**, in the project's angle unit: `input: 30` turns that joint 30° from where `assembly` places its child. Build the assembly at the configuration the source measures its angles from (the zero of its joints), so a stated angle is the pose value itself.
- cadrev exports the assembly as MJCF, sets each joint the pose names, holds every other `actuated` joint as built, and lets MuJoCo move the `passive` joints until every loop's two datums coincide. It then places each instance where MuJoCo puts its body and evaluates the check on its own geometry, with the same rules as an unposed check. A check without `pose` is evaluated on the assembly as built.
- A loop whose datums stay more than `tolerance.length` apart after solving is `[loop-open]`, naming the loop and the pose: the links cannot close there (too short, or past a toggle), and the checks at that pose are not evaluated.
- A `pose` naming no joint, or a value that is neither a param nor a ledger value, is `[check-config]`; so is a `pose` on a model with no joints. A pose value is read by its check: a param it names needs no read in model.py, the check rests on it, and a ledger value it names counts as used. A pose value printed in a unit other than an angle's is `[unit-quantity]`.
- Name `instances` on a posed check: a check in one part's own frame reads the same at every pose.

A verification run of a model with joints writes `build/model.mjcf` and one `build/meshes/<part>.stl` per part, and loads the MJCF in MuJoCo; MuJoCo rejecting it is `[mjcf-load]` with MuJoCo's reason, and then no posed check is evaluated. Each instance is a body framed as its part, each joint a hinge, each loop a `connect` between two sites named after its datums, and each `actuated` joint has a motor. The MJCF is in the project's units (mm and g by default, not SI) without gravity: a kinematic model, its lengths the report's lengths. A part weighs its volume times the param `density` where params.yaml defines one; otherwise MuJoCo infers each moving body's mass from its mesh. Per-part masses belong in params.yaml, the one door numbers have into the model, never in project.yaml. A model with no joints is static: it writes no MJCF, and report.md says so under the headline.

### Ranges and sweeps

A joint's `range` is two params in the project's angle unit, each a rotation from the assembly as built like a pose value. Ledger a stated range of motion as source values and read them into those params; a `range` check then confirms it, and an interference check with `sweep` confirms nothing collides across it:

```yaml
  - {id: toe-reach, kind: range, joint: toe, ends: [S2-toe.min, S2-toe.max]}
  - {id: toe-open, kind: range, joint: servo, ends: [S2-toe.closed, S2-toe.open],
     instances: [palm_1, toe_1], between: [palm_1.tip, palm_1.pivot, toe_1.tip]}
  - {id: toe-clear, kind: interference, pairs: [[palm_1, toe_1]], sweep: {joint: toe, steps: sweep_steps}}
```

- **`range`** names a `joint` and, in `ends`, the two ledger values `<evidence>.<key>` its range's two params must reach, in that order. cadrev poses the model at each end of the joint's range (each range param as a pose value) and compares, at each, the joint's own turn from as built or, with `between` (and `instances`), the angle there, as an `angle` check reads it, with that end's ledger value. It gives one result per end, `<id>.<range param>`, each with its pose. An end the model's range param stops short of is `[check-failed]`; an end where a loop cannot close is `[loop-open]`, and that end is not evaluated. A source range param whose `from` a range check's `ends` compares is covered; one no check covers is `[unchecked-source]`, like any source param. Compare the input's own range with `ends` alone; compare a stated output angle (a toe that opens 0–40°) with `between`.
- **`sweep: {joint, steps}`** on an interference check evaluates it at `steps` poses evenly spaced from one end of the joint's range to the other, ends included, and reports the worst overlap with the pair and the pose it occurred at (`0.82 crank_1 ∩ post_1 at input 90 over 2 pairs (listed) across 5 poses of input`); a clear sweep says how many poses it evaluated. `steps` is a param, read by the check (proposed, usually: the sweep's resolution is a choice), never a bare number (`[schema]`); one that is not a whole number of at least 2 is `[check-config]`. A loop that stays open at any pose is `[loop-open]`, and the check is not evaluated.
- Both check kinds rest on their joint's range params as well as the params they read. A `range` or `sweep` naming no joint of the model, a joint with no `range`, or `ends` that are not two values is `[check-config]`, as is either on a model with no joints. report.md shows each end's pose, and each sweep's joint, range and pose count, beside its interpretation.

## gaps.yaml

```yaml
gaps:
  - id: G-pitch
    question: What is the pin-to-pin pitch of the finger link?
    ask: authors     # authors | measure | datasheet | test
  - id: G-pin-x
    question: Where along the finger link does the pin sit?
    ask: authors
  - id: G-pins
    question: What diameter are the link pins?
    ask: datasheet
```

The report lists every gap with the params that name it in their `gap`: this is the list of questions to send the authors. Only a param's `gap` names a gap, so a gap no param names is the warning `[gap-unused]` even when a conflict's text cites its id; when a resolution leaves a question open, put the gap on the param whose value the resolution chose.

## overlays.yaml

```yaml
overlays:
  - id: s1-palm-front
    image: figures/supp/image7.png
    part: palm              # a part, an assembly instance, or "assembly"
    view: front             # front: X right, Z up · top: X right, Y up · right: Y right, Z up
    origin: [412, 618]      # pixel where model (0, 0) lands
    calibration:
      pixels: [[120, 640], [705, 640]]   # two pixels spanning a known dimension
      evidence: S1-palm.L                 # that dimension
    mirror: false
```

Renders `build/overlays/<id>.png`: model edges in magenta, calibration span in blue, under a title strip. Below that strip one PNG pixel is one pixel of `image`, so `origin` and `calibration.pixels` line up as written. An overlay is visual evidence for a human; it adds no pass/fail. One that cannot be drawn (an unknown `view` or `part`, a calibration that is no evidence value, an unreadable image) is `[overlay-config]`.

## Statuses

Every verification run ends on one status: `cadrev check` prints it last, and report.md and report.json carry it.

| status | when | exit |
|---|---|---|
| **VERIFIED** | no error finding and no figure reading awaiting confirmation: every number is accounted for and every check passes, even if some params are proposed | 0 |
| **VERIFIED PENDING REVIEW** | VERIFIED but for figure readings without `confirmed_by` | 0 |
| **NOT VERIFIED** | at least one error finding, including a project cadrev refuses (`[project-missing]`, `[format-missing]`, `[format-unknown]`) | 1 |
| **PARTIAL** | `--no-build` or `--no-coverage` skipped part of the run, so it makes no claim and writes no report | 1 |

**Exact** is not a status: it qualifies VERIFIED when no param rests on a proposed value. report.md then prints **Exact** under the status, and report.json sets `exact` to true.

## build/report.json

The machine-readable report `cadrev check` writes beside `report.md`, which renders the same data. A PARTIAL run writes neither. Its top-level keys:

| key | holds |
|---|---|
| `status` | the run's status (see [Statuses](#statuses)) |
| `exact` | whether the project is exact (see [Statuses](#statuses)) |
| `counts` | `errors`, `warnings`, `checks`, `checks_passed`, `params`, and the params resting on each basis: `source`, `measured`, `proposed` |
| `findings` | every finding as `level`, `rule`, `message` |
| `checks` | every geometry check with its result, expected and evaluated values, the basis it `rests_on`, and the params it reads resting on that basis (`rests_on_params`); for an interference check, also the number of pairs it evaluated (`pairs`); for a posed check, its `pose`: each joint with the param or ledger value it is set `from` and that `value`; for a swept interference check, its `sweep` (`joint`, the range params it is swept `from`, their values as `range`, and the number of `poses`), and as `pose` the one with the worst overlap |
| `tolerances` | each check with a non-default tolerance: its `check` id, `kind`, and `tol` or `tol_rel` |
| `overlap_limits` | each interference check with a non-default overlap limit: its `check` id and `max_volume` |
| `motion` | the model's `joints`, each with its `parent`, `child` and `drive`, and its `loops`, each as its two datums; no joints means static; null when no model was built |
| `model_literals` | project.yaml's `model_literals` when it differs from the default, else null |
| `params` | each param's spec, its resolved `value` and the basis it `rests_on` |
| `bases` | how many params declare each basis |
| `rests_on_proposed` | the params resting on a proposed value |
| `measured` | each measured param with its `value`, `from`, `method` and `uncertainty` |
| `awaiting_confirmation` | each unconfirmed figure reading with its `evidence`, `locator`, `reading` and `image` |
