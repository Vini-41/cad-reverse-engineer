# Project format

A reconstruction project is a directory of YAML files plus `model.py`. `cadrev init` creates it; `cadrev check` enforces every rule below and names the rule it applies (`[rule-name]`) in each finding.

Before any rule runs, every file is read against the shapes shown here. A file that is not valid YAML is `[yaml-syntax]` (file and line); an entry of the wrong shape (a missing `id`, a param that is a bare number, a non-numeric value) is `[schema]`, names the file and the entry, and is left out of the run. A directory without `project.yaml` is `[project-missing]`, and no report is written.

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
name: legclaw
target: Seventh-iteration BLCM leg as reported in Cheng 2026 (not the Fig. S10 iterations)
units: {length: mm, angle: deg, mass: g}
tolerance: {length: 0.001}
model_literals: [0, 1, 2, -1, 0.5, 90, 180, 270, 360]   # optional; numbers model.py may contain
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

`units` names the project's unit for length, angle, mass, force and time (defaults `mm`, `deg`, `g`, `N`, `s`); torque, pressure, density and speed follow from them (N·mm, N/mm², g/mm³, mm/s by default). A key outside those five, or a unit cadrev does not know or of another quantity (`length: g`), is `[units]`.

**Units come from the quote.** A ledger value is written as printed (`values: {L: 4}` for "4 cm"), and cadrev reads the unit printed right after it and converts the value to the project's units (40 mm) wherever a param `from:`, a check or an overlay uses it; a `value` written on that param is in project units (40). The numbers of a range or product share its last unit ("3–5 mm", "40×8×5 mm"). A value with no unit printed after it, such as a table cell (`37×6.5×5`), is already in project units. `in` and `"` read as inches, except `in` before a determiner ("4 in total", "2 in each leg").

Each use expects one quantity: a `bbox` or `distance` check, an overlay calibration and a param `model.py` reads expect a length (the model may also read an angle); a mass check's `key` and `add` params expect a mass, its `density` a density. A value printed in a unit of another quantity is `[unit-quantity]`; a param traces to its quote through basis `source`, or through a `derived` expr that only scales one param by constants (`rho * 1000`). A value printed in two different units in one quote, or once with a unit and once without ("4 mm pins in 4 cm links"), is `[unit-ambiguous]`: quote only the part that states it.

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

`tolerance.length` is how closely the model must realise a source value. It is a modelling check, never a manufacturing tolerance. Keep `sources:` the last key: `cadrev source` appends to it. Registering an id that is already listed refreshes its `path` and `sha256` instead, which is how sources are restored into a clone or replaced by a new download. A source whose `license` is CC0-1.0, CC-BY-x.y or CC-BY-SA-x.y gets a `!sources/<file>` line in the project's `.gitignore`, so it is committed and the project reruns from a clone; any other license, or none, leaves the file ignored.

Text formats (quote-checked and swept): PDF, DOCX, TXT, MD, HTML. A text source whose file cannot be read as text is `[source-unreadable]`. Save a web datasheet as HTML or TXT to make it quotable. Video and image files are sources for image evidence only.

## evidence.yaml

### `evidence`: the ledger

One item per statement in a source. Two anchor types:

```yaml
- id: S2-bent-linkage          # unique; referenced as S2-bent-linkage.L
  source: supp
  page: 4                      # PDF page (1-based); the quote must be on it
  locator: Table S2            # human locator: table, figure, section, equation
  quote: "Bent Linkage 37×6.5×5"
  values: {L: 37, H: 6.5, W: 5}

- id: fig2a-foot
  source: paper
  page: 4
  locator: Fig. 2A, sole inset
  image: figures/crops/fig2a-foot.png
  image_sha256: …              # printed by `cadrev crop`
  reading: "70mm; 56mm; 22mm"  # the label text exactly as printed in the image
  values: {L: 70, W: 56, H: 22}
  confirmed_by: <reviewer>     # written by the human who checked the crop
```

- **quote** is copied from `cadrev text` output. Matching ignores case, whitespace, line-break hyphenation, dash variants and `×`/`x`; everything else must be verbatim. Numbers match whole: a quote starting or ending at a digit never matches inside a larger number ("37 mm" is not found in "137 mm" or "3.7 mm"). Each value must appear as a number in the quote (or reading); a decimal comma is one number (`3,5 mm` is 3.5; `1,250` and `1,5,10` stay several), and so is a fraction before a unit (`1/4 inch` is 0.25, `1 1/2 in` is 1.5; a bare `1/50` is two); both ends of a range (`5-10 mm`) count as positive values, and a number labelling a figure, table, equation or section (`Fig. 2`, `Figs. 2 and 3`, `Table S1`, `Eq. (3)`, `Sec. 4.2`) is not a value unless a unit follows it (`section 4 mm thick`; after a label, `in` is the word: `Fig. 2 in`). Words such as "eight" are not numbers: leave the value out or quote a numeric form. Write each value as printed; its unit is read from the quote (see `units` above).
- **image** evidence covers numbers that exist only in pixels: figure labels, drawing dimensions, video frames. The crop is hashed so the reviewed image cannot change underneath its reading.
- **scope** is optional:
  - `not-modeled` + `reason`: a real statement about the object that this reconstruction does not build (purchased springs, out-of-scope subassemblies).
  - `context` + `reason`: a statement that informs interpretation but is not a dimension of any modelled feature (masses in conflict, a kinematic length of uncertain identity). `values` may be omitted.

Every value of an in-scope item must be used by a param `from:` or covered by a check (`[evidence-unused]`).

### `skipped`: stated quantities that are not about the object

The coverage sweep lists every number printed with a unit from the table under `units` (a range or list as one candidate: `3–5 mm`, `1,5,10 mm`), every `a×b×c` product and every thread size (`M3`) in the text sources, leaving out digits inside a name (`L14`) and figure, table, equation or section numbers. Each one must fall inside an evidence quote or a skip. A source with `coverage: false` is not swept and raises the warning `[coverage-off]`.

```yaml
skipped:
  - {source: paper, page: 12, quote: "servo output torque fixed at 1.2 kg ·cm", reason: test setting}
  - {source: supp, from: "Table S4.", to: "Movie S1.", reason: grasp-test objects}
  - {source: paper, pages: [12, 13], reason: experimental methods and airframe}
```

Skip by quote for single lines, by `from`/`to` for tables and blocks, by `pages` only for pages that carry nothing about the object. Every skip needs a `reason`.

### `conflicts`

```yaml
conflicts:
  - id: K1
    evidence: [S1-foot, fig2a-foot]
    summary: Fig. S1 gives 60×46×20, Fig. 2A gives 70×56×22.
    resolution: Fig. 2A is the outer envelope of the assembled sole; S1 is the linkage skeleton.
```

A conflict without `resolution` stays a warning and appears in the report as open.

## params.yaml

The only door numbers have into the model.

```yaml
params:
  bent_L:   {basis: source,   from: S2-bent-linkage.L, interpretation: overall length along part X}
  pin_d:    {basis: proposed, value: 2, rationale: common 2 mm pin, gap: G-pins}
  pitch:    {basis: derived,  expr: bent_L - 2 * end_margin, value: 32}
  foot_w:   {basis: measured, from: s6-frame-316, value: 55.2, method: "mat grid scale, 10 px/mm", uncertainty: "±1.5 mm"}
```

| basis | required | meaning |
|---|---|---|
| `source` | `from` (an evidence value); `value` optional and must match | stated by a source |
| `derived` | `expr`; `value` optional and must match | computed from other params; `pi sqrt sin cos tan asin acos atan atan2 radians degrees hypot min max abs` are available |
| `measured` | `from` (an image evidence id), `value`, `method`, `uncertainty` | scaled off an image or video frame against a known reference |
| `proposed` | `value`, `rationale`; `gap` expected | a reconstruction choice the sources do not make |

Write `interpretation` on every `source` param whose mapping onto geometry is a choice (which axis, envelope versus pitch, which feature). A derived param that depends on a proposed one is reported as resting on proposed values.

## checks.yaml

Expected values always come from evidence, so a check compares the geometry with the source, never with params.

```yaml
checks:
  - {id: env-bent, kind: bbox, part: bent_linkage, evidence: S2-bent-linkage,
     axes: {L: x, H: z, W: y}, interpretation: L×H×W read as part X×Z×Y}
  - {id: pitch-bent, kind: distance, between: [bent_linkage.pin_a, bent_linkage.pin_b],
     evidence: L14-design, key: L14, along: x}          # along is optional
  - {id: leg-mass, kind: mass, parts: [thigh, pedestal], counts: {phalanx: 8},
     density: resin_density, add: [servo_mass_total], evidence: fig2a-mass, key: m, tol_rel: 0.15}
  - {id: clear, kind: interference, pairs: [[thigh_1, pedestal_1]], max_volume: 0.001}
```

- `bbox`: the part's axis-aligned bounding-box size in its own frame.
- `distance`: between two datums returned by the model.
- `mass`: Σ volume × count × density, plus any `add` params; `tol_rel` is required. Its `density` and `add` params take their units from the quote (see `units` above).
- `interference`: overlap volume between assembly instances; all pairs when `pairs` is omitted. Needs no evidence.

`tol` overrides `tolerance.length` for one check. Each source param that no check covers raises `[unchecked-source]`.

## gaps.yaml

```yaml
gaps:
  - id: G-pitch
    question: What is the pin-to-pin pitch of the bent linkage?
    ask: authors     # authors | measure | datasheet | test
```

The report lists every gap with the params that rest on it: this is the list of questions to send the authors.

## overlays.yaml

```yaml
overlays:
  - id: s1-foot-front
    image: figures/supp/image7.png
    part: foot              # a part, an assembly instance, or "assembly"
    view: front             # front: X right, Z up · top: X right, Y up · right: Y right, Z up
    origin: [412, 618]      # pixel where model (0, 0) lands
    calibration:
      pixels: [[120, 640], [705, 640]]   # two pixels spanning a known dimension
      evidence: S1-foot.L                 # that dimension
    mirror: false
```

Renders `build/overlays/<id>.png`: model edges in magenta, calibration span in blue. An overlay is visual evidence for a human; it adds no pass/fail.
