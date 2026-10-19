# Project format

A reconstruction project is a directory of YAML files plus `model.py`. `cadrev init` creates it; `cadrev check` enforces every rule below and names the rule it applies (`[rule-name]`) in each finding.

Before any rule runs, every file is read against the shapes shown here. A file that is not valid YAML is `[yaml-syntax]` (file and line); an entry of the wrong shape (a missing `id`, a param that is a bare number, a non-numeric value, a key not shown here) is `[schema]`, names the file and the entry, and is left out of the run. Quote every value that holds a comma inside a `{…}` entry: unquoted, `reason: a test load, not the object` ends at the comma and leaves `not the object` as an unknown key. A directory without `project.yaml` is `[project-missing]`, and no report is written.

```
project.yaml    format, sources, units, tolerance, target
evidence.yaml   the ledger: evidence, skipped, conflicts
params.yaml     every number the model uses, with its basis
checks.yaml     geometry checks against evidence
gaps.yaml       what the sources leave undefined
overlays.yaml   optional: model edges drawn over source figures
model.py        build123d model; see modeling.md
sources/        registered source files (pinned by sha256)
figures/        extracted images; figures/crops/ holds pinned evidence crops
build/          STEP files, overlays, report.md, report.json
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

`format` is the version of these file formats. A project without it is `[format-missing]`; one with a version this cadrev does not read is `[format-unknown]`. Either way cadrev reads no other project file, every command refuses the project, and no report is written.

`target` names the object, version and configuration reconstructed; one missing or still starting with `TODO` is `[target]`.

`units` names the project's unit for length, angle, mass, force and time (defaults `mm`, `deg`, `g`, `N`, `s`); torque, pressure, density and speed follow from them (N·mm, N/mm², g/mm³, mm/s by default). A key outside those five, or a unit cadrev does not know or of another quantity (`length: g`), is `[units]`.

**Units come from the quote.** A ledger value is written as printed (`values: {L: 4}` for "4 cm"), and cadrev reads the unit printed right after it and converts the value to the project's units (40 mm) wherever a param `from:`, a check or an overlay uses it; a `value` written on that param is in project units (40). The numbers of a range or product share its last unit ("3–5 mm", "40×8×5 mm"). A value with no unit printed after it, such as a table cell (`37×6.5×5`), is already in project units. `in` and `"` read as inches, except `in` before a determiner ("4 in total", "2 in each leg").

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

- **quote** is copied from `cadrev text` output. Matching ignores case, whitespace, line-break hyphenation, dash variants and `×`/`x`; everything else must be verbatim. Numbers match whole: a quote starting or ending at a digit never matches inside a larger number ("37 mm" is not found in "137 mm" or "3.7 mm"). Each value must appear as a number in the quote (or reading); a decimal comma is one number (`3,5 mm` is 3.5; `1,250` and `1,5,10` stay several), and so is a fraction before a unit (`1/4 inch` is 0.25, `1 1/2 in` is 1.5; a bare `1/50` is two); both ends of a range (`5-10 mm`) count as positive values, and a number labelling a figure, table, equation or section (`Fig. 2`, `Figs. 2 and 3`, `Table S1`, `Eq. (3)`, `Sec. 4.2`) is not a value unless a unit follows it (`section 4 mm thick`; after a label, `in` is the word: `Fig. 2 in`). Words such as "eight" are not numbers: leave the value out or quote a numeric form. Write each value as printed; its unit is read from the quote (see `units` above).
- **image** evidence covers numbers that exist only in pixels: figure labels, drawing dimensions, video frames. The crop is hashed so the reviewed image cannot change underneath its reading. Until a named human writes `confirmed_by`, the reading holds the project at VERIFIED PENDING REVIEW (see [Statuses](#statuses)); `build/report.md` lists each such reading beside its crop. Every image item awaits confirmation, whatever its `scope`. The image a `measured` param scales off is image evidence too, and needs no `values`: its `reading` transcribes any label printed in it and names the reference it is scaled against (`no printed labels; scaled on the palm width`), and its reviewer confirms that crop and that reference. Figure labels that are not about the object (test rigs, loads, results) need no evidence item.
- **scope** is optional:
  - `not-modeled` + `reason`: a real statement about the object that this reconstruction does not build (purchased springs, out-of-scope subassemblies). It keeps its `values`, so the report shows what was left unbuilt.
  - `context` + `reason`: a statement that informs interpretation but is not a dimension of any modelled feature (masses in conflict, a kinematic length of uncertain identity). `values` may be omitted.

Each item has a unique `id` (`[evidence-id]`), a registered `source` (`[evidence-source]`) and a `locator` (`[evidence-locator]`), and is anchored by a quote from a text source or by an image + reading (`[evidence-anchor]`). A quote not found in its source, or not on its `page`, is `[quote-not-found]`; a quote from a source of several pages that gives no `page` raises the warning `[quote-page]`, which names the page it was found on. A quoted item needs `values` unless it is `scope: context` (`[evidence-values]`). An image item needs its crop (`[image-missing]`), unchanged since `image_sha256` was printed (`[image-hash]`), and a `reading` (`[image-reading]`). A value that is not a number in its quote is `[value-not-in-quote]`; in its reading, `[value-not-in-reading]`. A `scope` needs a `reason` (`[evidence-scope]`).

Every value of an in-scope item must be used by a param `from:` or covered by a check (`[evidence-unused]`).

### `skipped`: stated quantities that are not about the object

The coverage sweep lists every number printed with a unit from the table under `units` (a range or list as one candidate: `3–5 mm`, `1,5,10 mm`), every `a×b×c` product and every thread size (`M3`) in the text sources, leaving out digits inside a name (`L3`) and figure, table, equation or section numbers. Each one must fall inside an evidence quote or a skip; one that does not is `[coverage]`. A source with `coverage: false` is not swept and raises the warning `[coverage-off]`.

```yaml
skipped:
  - {source: paper, page: 12, quote: "servo output torque fixed at 1.2 kg ·cm", reason: test setting}
  - {source: supp, from: "Table S4.", to: "Movie S1.", reason: grasp-test objects}
  - {source: paper, pages: [12, 13], reason: experimental methods and test rig}
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

The only door numbers have into the model.

```yaml
params:
  link_L:   {basis: source,   from: T1-finger-link.L, interpretation: overall length along part X}
  pin_d:    {basis: proposed, value: 2, rationale: common 2 mm pin, gap: G-pins}
  pitch:    {basis: derived,  expr: link_L - 2 * end_margin, value: 34}
  palm_w:   {basis: measured, from: v1-frame-316, value: 30.4, method: "mat grid scale, 10 px/mm", uncertainty: "±1.5 mm"}
```

| basis | required | meaning |
|---|---|---|
| `source` | `from` (an evidence value); `value` optional and must match | stated by a source |
| `derived` | `expr`; `value` optional and must match | computed from other params; `pi sqrt sin cos tan asin acos atan atan2 radians degrees hypot min max abs` are available |
| `measured` | `from` (an image evidence id), `value`, `method`, `uncertainty` | scaled off an image or video frame against a known reference |
| `proposed` | `value`, `rationale`; `gap` expected | a reconstruction choice the sources do not make |

A basis outside these four is `[param-basis]`. A missing requirement is `[param-from]` (`from` names no evidence value, or for `measured` no image evidence), `[param-measured]` or `[param-proposed]`; an `expr` that does not parse, names an undefined param, fails to evaluate or depends on itself is `[param-derived]`. A `value` that differs from its evidence value or `expr` is `[param-mismatch]`. A proposed param that names no `gap` raises the warning `[param-gap]`, and one naming a gap gaps.yaml lacks is the error `[param-gap]`.

A proposed param whose value was changed to turn a check green says so in its `rationale`, naming the check: that check now confirms the choice rather than a source.

Write `interpretation` on every `source` or `derived` param whose mapping onto geometry is a choice (which axis, envelope versus pitch, which feature, a placement such as flush or centred): a derived param rests on its inputs' basis, so the interpretation is where the choice its `expr` makes shows.

A derived param rests on the weakest basis among the params its `expr` references (proposed < measured < source); an `expr` that references no param (`2.2`, `2 * pi`) is `[param-constant]`. The report's headline counts params by what they rest on.

## checks.yaml

Expected values always come from evidence, so a check compares the geometry with the source, never with params.

```yaml
checks:
  - {id: env-link, kind: bbox, part: finger_link, evidence: T1-finger-link,
     axes: {L: x, H: z, W: y}, interpretation: L×H×W read as part X×Z×Y}
  - {id: pitch-link, kind: distance, between: [finger_link.pin_a, finger_link.pin_b],
     evidence: L3-design, key: L3, along: x}          # along is optional
  - {id: tilt-link, kind: angle, between: [finger_link.pin_a, finger_link.pin_b, finger_link.tip],
     evidence: S2-tilt, key: theta, tol: 0.5}          # the angle at pin_b, in degrees
  - {id: gripper-mass, kind: mass, parts: [palm, finger_link], counts: {finger_link: n_links},
     density: resin_density, add: [servo_mass], evidence: fig3b-mass, key: m, tol_rel: 0.15}
  - {id: clear, kind: interference, pairs: [[palm_1, finger_link_1]], max_volume: 0.001}
```

- `bbox`: the part's axis-aligned bounding-box size in its own frame.
- `distance`: between two datums of one part, in that part's frame. Datums of two different parts (`<part>.<feature>` naming different parts) sit in unrelated frames, so such a check is `[check-config]`.
- `angle`: `between: [a, vertex, b]`, three datums of one part (the same rule as `distance`); the angle at `vertex` between the directions to `a` and to `b`, in degrees (0 to 180). A datum that coincides with the vertex leaves the angle undefined and is `[check-config]`. A stated joint range (a range of motion) is not an angle of the one static model: ledger it `scope: context` with a reason, and check an angle only where a source states it for the configuration `target` names.
- `mass`: Σ volume × count × density, plus any `add` params; `tol_rel` is required. Each `counts` entry names the param that counts that part (parts it leaves out count once), so a stated count is ledgered like any other number; a bare number there is `[schema]`. Its `density` and `add` params take their units from the quote (see `units` above). The check reads its `density`, `add` and `counts` params, so they need no read in model.py and no other check.
- `interference`: overlap volume between assembly instances; all pairs when `pairs` is omitted. Needs no evidence. It passes when the overlap is at most `max_volume`, which defaults to `tolerance.length`³. This overlap limit compares with no ledger value, so it is not a tolerance and has no cap, but the report lists beside its check each limit other than cadrev's default: the default `tolerance.length`, 0.001, cubed. A project-wide `tolerance.length` therefore lists every interference check that sets no `max_volume`.

Every check reads parts, never assembly instances: a dimension that spans several parts (an envelope of a subassembly, a spacing between parts) has no check yet, so record it as a `not-modeled` item or model the span as datums of one part. A check of another `kind` is `[check-kind]`; one naming a part, datum, axis or evidence value that does not exist is `[check-config]`. A check whose evaluated value strays from its ledger value by more than its tolerance is `[check-failed]`.

Each check rests on the weakest basis among the params it reads (proposed < measured < source), or on source when it reads none; today only a mass check reads params. report.json gives each check result its `rests_on`, and report.md's checks table shows "rests on <basis>: <params>" beside a check resting on less than source, naming the params it reads that rest on that basis. A mass check on a proposed density then confirms the model against the stated mass given that chosen density, not the density itself. What a check rests on leaves its pass/fail and the status unchanged.

`tol` overrides `tolerance.length` for one check, or `tolerance.angle` (degrees) for an angle check. A check's tolerance is capped: `tol` (or the project tolerance, where the check sets none) at 5% of each value the check compares, and `tol_rel` at 0.25; above either is `[tolerance-cap]`. The report lists every non-default tolerance beside its check: each `tol` other than 0.001 (0.01 for an angle check), and every `tol_rel`, which has no default. Each source param that no check covers raises `[unchecked-source]`.

## gaps.yaml

```yaml
gaps:
  - id: G-pitch
    question: What is the pin-to-pin pitch of the finger link?
    ask: authors     # authors | measure | datasheet | test
```

The report lists every gap with the params that rest on it: this is the list of questions to send the authors.

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

Renders `build/overlays/<id>.png`: model edges in magenta, calibration span in blue. An overlay is visual evidence for a human; it adds no pass/fail. One that cannot be drawn (an unknown `view` or `part`, a calibration that is no evidence value, an unreadable image) is `[overlay-config]`.

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
| `checks` | every geometry check with its result, expected and evaluated values, and the basis it `rests_on` |
| `tolerances` | each check with a non-default tolerance: its `check` id, `kind`, and `tol` or `tol_rel` |
| `overlap_limits` | each interference check with a non-default overlap limit: its `check` id and `max_volume` |
| `model_literals` | project.yaml's `model_literals` when it differs from the default, else null |
| `params` | each param's spec, its resolved `value` and the basis it `rests_on` |
| `bases` | how many params declare each basis |
| `rests_on_proposed` | the params resting on a proposed value |
| `measured` | each measured param with its `value`, `from`, `method` and `uncertainty` |
| `awaiting_confirmation` | each unconfirmed figure reading with its `evidence`, `locator`, `reading` and `image` |
