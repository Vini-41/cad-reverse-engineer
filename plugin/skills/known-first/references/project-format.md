# Project format

A reconstruction project is a directory of YAML files plus `model.py`. `cadrev init` creates it, and `cadrev check` holds it to everything below. This file gives each file's shape and what its entries mean. A finding names what breaks a rule and where, so read this for what to write, and the findings for what to fix.

```
project.yaml    format, target, units, tolerance, sources
evidence.yaml   the ledger: evidence, skipped, conflicts, datums on released bodies
params.yaml     every number the model uses, with its basis; the mass model
checks.yaml     the geometry compared with the ledger
gaps.yaml       what the sources leave open
overlays.yaml   optional: model edges drawn over figures
plan.yaml       optional: how the object is made and put together
model.py        the build123d model (modeling.md)
sources/        registered source files, pinned by sha256
figures/        the pages and images `cadrev figures` writes; figures/crops/ holds the pinned evidence crops
build/          STEP files, isometric.png, drawings/, overlays, report.md, report.json; model.mjcf and meshes/ for a mechanism; plan.md and steps/ for a plan
```

Every file is read against the shapes shown here: an entry with a key not shown, or a value of the wrong type, is left out of the run with a `[schema]` finding. Quote every free-text value inside a `{…}` entry (`reason: "a test load, not the object"`), since an unquoted comma ends the value there.

## project.yaml

```yaml
format: 1                # written by `cadrev init`; cadrev refuses a project of another format
name: gripper
target: Version-3 two-finger gripper as reported in Doe 2025, fingers open (not the Fig. S4 prototype)
units: {length: mm, angle: deg, mass: g}       # also force and time; defaults mm, deg, g, N, s
material: "PLA, FDM printed"                   # optional: what the made parts are made of, and how
follows: design                                # optional: design | function; design unless said
up: y                    # optional: the axis the object stands on, z unless said
tolerance: {length: 0.001, angle: 0.01}        # how closely the model must realise a source value
clearance: fit_gap       # optional: the length param of the loosest fit
model_literals: [0, 1, 2, -1, 0.5, 90, 180, 270, 360]   # optional: the numbers model.py may hold
known_first: true        # optional: build only what the sources settle (Known first)
sources:                 # written by `cadrev source`; keep it the last key
  - id: paper
    kind: paper          # paper | supplement | datasheet | video | drawing | geometry | other
    path: sources/x.pdf
    sha256: …
    citation: …
    url: https://doi.org/…
    coverage: false      # optional: leave this source out of the coverage sweep (a 200-page catalogue)
```

- `target` names the object, its version and its configuration, and where the authors released several variants, the one built.
- `tolerance` is the model's, how closely it realises a value, and not what a shop works to: that is the [plan](#planyaml)'s to say. `tolerance.angle` is in degrees whatever `units.angle` says.
- **Every instance is held**: it touches another instance, or sits within `clearance` of one, so the assembly is one object. `clearance` names the length param of the loosest fit, the largest gap the model leaves between two parts that hold each other: a pin centred in its running hole, a tongue between its fork's cheeks. Without it, parts touch, which two do within `tolerance.length`, the slack a named clearance gets too. An instance further than that from every other floats, and so does a group whose instances hold only each other: a `[held]` warning, and an error under a [plan](#planyaml). Build what holds it (a spring's hooks, a seat), or move it onto what does. The warning stands where the `target` leaves out what holds it, a bearing or a second unit. A known-first project with no plan is not held to this: what holds a part may wait.
- `units.length` is the user's answer to metric or US: `mm` or `in`. A proposed thread and a proposed screw length come from its table, ISO metric for a metric unit and Unified for `in`; a project that mixes the two says `threads: metric` or `threads: unified`. A STEP file holds the object at its true size in either.
- `material` and `follows` are the complete model's other two answers: what its made parts are made of and how, and whether a feature that is hard to make that way is built as the sources show it (`design`) or replaced by one that does the same job (`function`). The report prints both.
- `cadrev source` with an id already registered refreshes that entry: its file, hash and whatever the command states. That is how a source is restored into a clone or replaced by a new download.
- **Text sources** are quote-checked and swept: PDF, DOCX, TXT, MD, HTML (read as its rendered text). Save a web datasheet as HTML or TXT to quote it. Video and image files anchor image evidence only.
- **Geometry sources** (`kind: geometry`) are what the authors released: STEP or STL, read in millimetres and converted to the project's length unit. A **body** is named by its source's id where the file holds one solid, else `<source>#<n>`, the nth solid in file order from 1. Where a part ships as both, register the STEP, which keeps the cylindrical faces and axes an STL flattens into triangles ([derived datums](#probes-released-geometry)).
- **A cut file** is a laser-cut sheet, an SVG registered as `kind: geometry`. Its bodies are its regions, each an outer contour with the holes inside it, named by a point inside it: `<source>@<x>,<y>` (`plates@30,41`). Points are in the sheet's frame: from the page's top-left corner, x right and y down, at the scale the file declares with every transform applied, in the project's length unit. The coverage findings name each region by such a point, ready to copy.

## Units come from the quote

A ledger value is written as printed (`values: {L: 4}` for "4 cm"). cadrev reads the unit printed after the number, or after a hyphen (`5-mm pin`), and converts the value to the project's units wherever a param, a check or an overlay uses it; a `value` written on that param is in project units (40).

- The numbers of a range or a product share its last unit ("3–5 mm", "40×8×5 mm"), and a nominal its tolerance's ("1.000 ± 0.005 in").
- A value with no unit after it, such as a table cell, is already in project units. Where the table prints its unit in a header (`(cm)` over `13*13*10`), ledger the cell as printed, give the dimension a `derived` param scaled to the project's unit (`t_w * 10`) whose `interpretation` names the header, and check it through `expect` (`T2.W * 10`) on a `distance` check between datums on opposite faces, since a `bbox` check takes no `expect`.
- `in` and `"` read as inches, except `in` before a determiner ("4 in total").
- A value printed in two different units in one quote, or once with a unit and once without, is ambiguous: quote only the part that states it.
- A **count** (a gear's teeth, a train's planets) is a whole number printed with no unit or a count unit, read as a pure number: a table's `25` for the sun's teeth gives `z_sun` 25, not 25 mm. A ratio is ledgered as its number: "7.2:1" is `{ratio: 7.2}`.

Each use expects one quantity (a length for a `distance` check, an angle for an `angle` check, a count for a `count` check, a revolute joint's angle or a slide's length for its range and poses), and a value printed in a unit of another, or a probe of another, is a `[unit-quantity]` finding naming the quantity expected.

| quantity | units read, spelled-out names included |
|---|---|
| length | mm, cm, m, µm/um/micron, in/", ft, thou |
| angle | deg/°, rad |
| mass | mg, g, kg, lb, oz |
| force | N, kN, mN, kgf, lbf |
| torque | N·m (Nm), N·mm, N·cm, mN·m, kgf·cm (kg·cm) |
| pressure | Pa, kPa, MPa (N/mm²), GPa, bar, psi |
| density | g/cm³ (g/cc, g/ml), kg/m³, g/mm³ |
| speed, angular speed | mm/s, cm/s, m/s, km/h; rpm, rad/s |
| time | ms, s, min, h |
| area, volume | mm², cm², m²; mm³, cm³ (cc, ml), m³ |
| stiffness, damping | N·m/rad, N·mm/rad, N/m, N/mm; N·m·s/rad, N·mm·s/rad, N·s/m, N·s/mm |
| fraction, count, charge | % (40% is 0.4), turns, teeth, mAh |

Torque, pressure, density and speed are in the project's base units (N·mm, N/mm², g/mm³, mm/s by default). Any other word after a number (`12 links`) leaves it in project units.

## evidence.yaml

### `evidence`: the ledger

One item per statement in a source, anchored one of three ways: a quote, a figure reading (both below) or a [probe](#probes-released-geometry).

```yaml
evidence:
  - id: T1-finger-link          # unique; cited as T1-finger-link.L
    source: supp
    page: 4                      # PDF page, 1-based; the quote must be on it
    locator: Table 1             # for a human: table, figure, section, equation
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

- **A quote** is matched against the text `cadrev text` prints, ignoring case, whitespace, line-break hyphenation, dash variants and `×`/`x`; everything else is verbatim. Each value must appear as a number in the quote, matched whole: "37 mm" is not found in "137 mm".
- **How numbers read.** A decimal comma is one number (`3,5 mm` is 3.5) and so is a fraction before a unit (`1 1/2 in` is 1.5); both ends of a range are values; a number labelling a figure, table, equation or section is not one. A cardinal from zero to ninety-nine in words is a number ("Eight tension springs" states 8, written `n: 8` or `n: eight`). A comma before exactly three digits (`1,250`) reads two ways, so take that value from where it is printed in another form.
- **Image evidence** covers numbers that exist only in pixels: figure labels, drawing dimensions, video frames. The crop is hashed so the reviewed image cannot change under its reading. Until a named human writes `confirmed_by`, the reading holds the project at VERIFIED PENDING REVIEW. The image a `measured` param scales off is image evidence too and needs no `values`: its `reading` transcribes any label and names the reference it is scaled against.
- **`scope`** sets a statement aside, with a `reason`:
  - `not-modeled`: a real statement about something the reconstruction does not build: what lies outside the device (a test rig, the electronics), a part the target's configuration leaves out, a part whose motion cadrev's joint types cannot model (a flexure), or a feature that a project following the function replaces with one easier to make. It keeps its `values`, so the report shows what was left unbuilt.
  - `context`: a statement that informs interpretation but is not a dimension of a modelled feature. A restatement is context: a value stated in several places is ledgered at each, the statement a param or check reads stays in scope (a quote rather than a figure reading where both exist), and each other one says `restates <id>`. Statements whose values differ are a conflict, not a restatement.
- Every value of an in-scope item is used by a param's `from` or compared by a check.

### Probes: released geometry

A probe takes a value from a body of a geometry source. cadrev evaluates it from the file on every run and compares it with the value the probe records, the design value (`32.5`, not the file's `32.4999`), in the project's units.

```yaml
evidence:
  - {id: R-hub, source: rotor_step, locator: "rotor, hub bore axis", probe: distance,
     between: [rotor_step.hub_top, rotor_step.hub_bottom], values: {h: 20}}
  - {id: R-env, source: lid_step, body: "lid_step#2", locator: "lid, envelope", probe: bbox,
     axes: {D: x, H: z}, values: {D: 130, H: 4}}
  - {id: R-bore, source: rotor_step, locator: "rotor, hub bore", probe: diameter,
     at: rotor_step.bore_wall, values: {d: 32.5}}
  - {id: H-bore, source: hub_stl, locator: "hub, 13-sided bore", probe: diameter,
     at: hub_stl.bore, values: {d: 5}}
  - {id: S-end, source: plates, body: "plates@30,41", locator: "link plate, hole from its end",
     probe: distance, between: [plates.end, plates.hole_a], values: {e: 5}}
datums:                        # on released bodies: <body>.<feature>: [x, y, z] in the file's frame
  rotor_step.hub_top: [0, 0, 20]
  rotor_step.hub_bottom: [0, 0, 0]
  rotor_step.bore_wall: [16.25, 0, 10]
  hub_stl.rim_1: [2.5, 0, 0]          # three triangle corners of the bore's rim
  hub_stl.rim_5: [-0.8865, 2.3375, 0]
  hub_stl.rim_9: [-1.8713, -1.6578, 0]
  hub_stl.bore: {circle: [hub_stl.rim_1, hub_stl.rim_5, hub_stl.rim_9]}
  plates.end: [20, 42.5]             # on a cut file's sheet: <source>.<feature>: [x, y]
  plates.a1: [23.5, 42.5]            # three points on hole a's edge, and the circle through them
  plates.a2: [25, 41]
  plates.a3: [26.5, 42.5]
  plates.hole_a: {circle: [plates.a1, plates.a2, plates.a3]}
```

- `probe` is `bbox` (with `axes`, one per value), `distance` (two datums in `between`, `along` optional), `angle` (three datums, the angle at the middle one, in degrees, `along` optional) or `diameter` (of the circle a circle datum `at` names, else of the cylindrical face the datum `at` lies on). Each reads the body as the check of that kind reads the built model. `body` may be left out where the file holds one solid.
- A probe of a cut file names its region in `body` (`<source>@<x>,<y>`) and reads it in the sheet's frame: `bbox` with `axes` x and y, the region's outer contour; `distance` (`along` x or y) or `angle` between datums of the sheet in that region; `diameter` at a circle datum.
- A datum lies on its body's solid within `tolerance.length`, as a built part's does ([modeling.md](modeling.md#contract)). A cut file's datum lies on the sheet, named `<source>.<feature>` and given as `[x, y]`, inside a region's outer contour. One a probe or a derived datum names lies on its region's edge, the outer contour or a hole's, within `tolerance.length`: a hole's centre is a circle datum, not a point typed at it.
- A **derived datum** on a released body is worked out from datums given as points on that same body, `[x, y, z]` on a STEP or STL and `[x, y]` on a cut file's sheet: `{circle: [a, b, c]}` is the circle through three, more than `tolerance.length` apart and off one line, and `{mid: [a, b]}` the midpoint of two. A `distance` or `angle` probe, or a shape check's pair, reads a circle datum at its centre, and a `diameter` probe at it reads the circle's diameter. The datums it names are confirmed as any datum is; the derived point lies in air by design.
- On an STL, each datum a derived datum names also lies within `tolerance.length` of a triangle corner, since corners are the points a mesh stores on the true surface.
- A probe may set its own `tol`, capped as a check's is. It needs no human confirmation. A param takes its value with `from:` and basis `source`, like a quote's.
- A probe restating a quote is `context`; one that differs from a quote is a conflict.

### `skipped`: what is not about the object

The coverage sweep lists every stated quantity in the text sources: each number, in digits or words, printed with a unit from the table above (a range or a toleranced value as one), each `a×b×c` product, each diameter callout (`Ø 32.5`) and each thread size (`M3`, `1/4-20`, `#6-32`). Each must fall inside an evidence quote or a skip. In a geometry source, each body must be compared by a shape check or skipped.

```yaml
skipped:
  - {source: paper, page: 12, quote: "servo output torque fixed at 1.2 kg ·cm", reason: "test setting"}
  - {source: supp, from: "Table S4.", to: "Movie S1.", reason: "grasp-test objects"}
  - {source: paper, pages: [12, 13], reason: "experimental methods and test rig"}
  - {source: lid_step, body: "lid_step#3", reason: "a fit tester"}
  - {source: plates, within: [[110, 30], [150, 70]], reason: "the controller's housing"}
```

Skip by `quote` for a line, by `from` and `to` for a block on one page (split a block that runs onto the next), by `pages` only for pages that say nothing about the object. A cut file's skip names one region by `body`, or by `within` every region wholly inside a rectangle given by two opposite corners.

### `conflicts`

```yaml
conflicts:
  - id: K1
    evidence: [S1-palm, fig3b-palm]
    summary: Fig. S1 gives 44×26×10, Fig. 3B gives 48×30×12.
    resolution: Fig. 3B is the outer envelope of the palm with its covers; S1 is the bare frame.
```

A conflict without a `resolution` stays open: a warning, listed in the report.

## params.yaml

```yaml
params:
  link_L:     {basis: source,   from: T1-finger-link.L, interpretation: "overall length along part X"}
  pin_d:      {basis: proposed, value: 2, rationale: "common 2 mm pin", gap: G-pins}
  end_margin: {basis: proposed, value: 3, rationale: "pin centres 3 mm in from each end", gap: G-pitch}
  pitch:      {basis: derived,  expr: link_L - 2 * end_margin, value: 34}
  pin_x:      {basis: derived,  expr: link_L / 2, gap: G-pin-x, interpretation: "pin centred along the link"}
  palm_w:     {basis: measured, from: v1-frame-316, value: 30.4, method: "mat grid scale, 10 px/mm", uncertainty: "±1.5 mm"}
  knee_c:     {basis: proposed, value: 50, rationale: "light damping", gap: G-damping, physics: true}
parts:                       # the mass model
  palm:  {density: resin_density}
  servo: {mass: servo_mass}
```

| basis | takes | meaning |
|---|---|---|
| `source` | `from`, an evidence value; `value` optional and must match | stated by a source: a quote, a reading or a probe |
| `derived` | `expr` over other params; `value` optional and must match; `gap` with `interpretation` where the expr is a choice | computed; `pi sqrt sin cos tan asin acos atan atan2 radians degrees hypot min max abs` are available |
| `measured` | `from`, an image evidence id whose source is not a geometry source; `value`, `method`, `uncertainty`; `gap` optional | scaled off a figure of the object against a known reference |
| `proposed` | `value`, `rationale`; `gap` | a reconstruction choice the sources do not make |

- **`interpretation`** says how a value maps onto geometry where that is a choice: which axis, envelope or pitch, which feature, which configuration.
- **A derived param whose `expr` makes a placement choice** (pins at the centres of the rounded ends, a frame centred in its sole) names the `gap` whose answer would settle it. A choice several params share can instead be one proposed param they all read (`end_margin` above).
- **Rests on.** A param rests on its own basis; a derived one on the weakest basis among the params its `expr` reads (proposed < measured < source), or on proposed where it names a gap. The report's headline counts params by what they rest on. An `expr` that reads no param traces to nothing: give the number its own basis.
- **A physics value** is a param only the simulation reads (a joint's damping, stiffness, spring rest or friction, a tendon's stiffness or damping), marked `physics: true` and named by the joint or tendon that applies it ([modeling.md](modeling.md#joints-and-loops)). It is in the project's units of its quantity, per radian on a revolute joint (stiffness in N·mm/rad by default) and per length on a slide (N/mm), a friction a torque or a force; a `spring_rest` is a joint value, like a pose. It shapes no geometry, so no check compares it, and a proposed one leaves a project exact.
- **The mass model**, `parts`, weighs each part by one param: `mass`, a datasheet mass, for a purchased part, or `density`, which its volume is multiplied by, for a printed one. The MJCF export, the report and a mass check without `density` all weigh by it, so they never disagree. In a model with joints every part an instance places needs an entry.

### Threads

A thread param gives `thread`, a designation, in place of a value:

```yaml
  lid_screw:     {basis: source,   thread: M3, from: T2-bom, length: lid_screw_len}
  lid_screw_len: {basis: proposed, value: 10, rationale: "3 mm of lid and 7 mm into its boss", gap: G-lid}
  mount_thread:  {basis: proposed, thread: M3, rationale: "the lid's thread, so one size serves", gap: G-mount}
  tripod:        {basis: source,   thread: 1/4-20, from: S4-mount}
```

- **The designation** is one the ISO metric table holds (`M3`, or with a fine pitch `M8x1`; ISO 261's first- and second-choice diameters, M1 to M39) or the Unified one (`1/4-20`, `10-32`, `UNC` or `UNF` optional; #0 to 1 in). Write a number size without its `#`, which YAML reads as a comment. A size or pitch its table does not hold is a finding that lists what the size takes.
- **Its clearance hole** is ISO 273's medium series or ASME B18.2.8's normal fit; a declared hole may be any size up to the coarse series or the loose fit. Those list none for M1.1, M2.2, #12 and 9/16, so a hole clearing one of them takes a param of its own and is not declared.
- **With basis `source`**, `from` names the evidence item whose quote or reading prints the designation; the item needs no `values` for it. A size printed before a length (`M3x10`) states the coarse thread, and so does one a drawing calls out by the count of its holes (`4-M3`, `6-M2.0`), a count a [`count` check](#checksyaml) compares. A source's thread is taken as stated, from either table.
- **With basis `proposed`**, the thread comes from the project's table: its length unit's, or `threads` in project.yaml.
- **Its value** is its major diameter in the project's length unit, so a derived `expr` may read it; model.py reads its tap drill, clearance hole and pitch from it ([modeling.md](modeling.md#threads)). It is a checked param once model.py declares it on a hole or shank.
- **A screw** is a thread param that names its `length`, a length param of its own: `source` where a source states the screw's length, else `proposed`. A proposed length is a standard one of its thread's table, within `tolerance.length`: ISO 888's preferred lengths from 2 to 300 mm, or ASME B18.3's increments from 1/8 to 10 in. A screw is bought, so its length is never `derived`: a boss or a hole that holds the screw is derived from the length. The report prints the screw as it is ordered (`M3×10`, `1/4-20 UNC × 3/4 in`). A thread param without a length is a thread alone: a mounting hole left for the user's own screw, or a nut.

## checks.yaml

A check compares the built geometry with the ledger, never with params: with the value its `evidence` and `key` name, or one its [`expect`](#worked-values-expect) works out from ledger values.

```yaml
checks:
  - {id: env-link, kind: bbox, part: finger_link, evidence: T1-finger-link,
     axes: {L: x, H: z, W: y}, interpretation: "L×H×W read as part X×Z×Y"}
  - {id: pitch-link, kind: distance, between: [finger_link.pin_a, finger_link.pin_b],
     evidence: L3-design, key: L3, along: x}          # along is optional
  - {id: tilt-link, kind: angle, between: [finger_link.pin_a, finger_link.pin_b, finger_link.tip],
     evidence: S2-tilt, key: theta, tol: 0.5}          # the angle at pin_b, in degrees
  - {id: bore-link, kind: diameter, at: finger_link.bore_wall, evidence: T1-pin, key: d}
  - {id: env-foot, kind: bbox, instances: [sole_1, frame_1, shaft_1], evidence: T1-foot, axes: {H: z}}
  - {id: span-feet, kind: distance, instances: [foot_l, foot_r],
     between: [foot_l.pivot, foot_r.pivot], evidence: S2-stance, key: w}
  - {id: gripper-mass, kind: mass, parts: [palm, finger_link], counts: {finger_link: n_links},
     density: resin_density, add: [servo_mass], evidence: fig3b-mass, key: m, tol_rel: 0.15}
  - {id: clear, kind: interference, pairs: [[palm_1, finger_link_1]], max_volume: 0.001}
  - {id: planets, kind: count, part: planet, evidence: T1-sspg, key: n_planets}
  - {id: lid-screws, kind: count, thread: lid_screw, evidence: T2-bom, key: n_m3}
  - {id: rotor-shape, kind: shape, part: rotor, body: rotor_step,
     pairs: [[rotor.hub_top, rotor_step.hub_top], [rotor.hub_bottom, rotor_step.hub_bottom],
             [rotor.rim, rotor_step.rim]]}
  - {id: plate-shape, kind: shape, part: plate, body: "plates@30,41", along: z,
     pairs: [[plate.a, plates.a], [plate.b, plates.b], [plate.d, plates.d]]}
```

- **`bbox`**: the part's axis-aligned bounding-box size in its own frame, one result per axis.
- **`distance`**: between two datums; `along` takes it along one axis.
- **`angle`**: `between: [a, vertex, b]`, the angle at `vertex`, in degrees, unsigned from 0 to 180. `along` takes it about one axis, between the datums projected onto the plane square to it: a phase about a bore's axis between features at different heights.
- **`diameter`**: of the cylindrical face its datum `at` lies on: a bore or a hub. A toothed gear has no face at its pitch circle, so its pitch diameter is a `distance` between two datums on opposite flanks at the pitch radius, half a turn apart, with `expect: "<module> * <teeth>"`.
- **`mass`**: Σ volume × `density` over the instances it weighs, plus its `add` params, within `tol_rel`, which it must set. It weighs the instances `instances` lists, else the whole assembly, narrowed by `parts`. Each part weighed in several instances takes a `counts` entry naming the param that states how many, which the check holds to the instances it finds; without one the check rests on proposed, since how many there are is then the model's choice. Without `density` it weighs each part by the [mass model](#paramsyaml), and so confirms the model as exported against a stated total.
- **`count`**: how many instances of `part` the assembly places, compared exactly, with a stated count or with one [`expect`](#worked-values-expect) works out, as a count per leg times the legs is (`expect: "P2.legs * P11.springs"`); or, with `thread` in place of `part`, how many holes and shanks carry that thread param's thread, each counted once per instance of its part, which is how a stated number of screws is checked without modelling one. A clearance hole is not counted. A tooth count is checked through what it builds and couples, not by counting teeth.
- **`interference`**: the overlap volume between instances, over `pairs` or every pair, at most `max_volume` (default `tolerance.length`³). It needs no evidence.
- **`shape`**: a built part against a released body, as a whole. `pairs` lists at least three datum pairs `[<part>.<feature>, <body>.<feature>]` not on one line; cadrev carries the part onto the body by the rigid motion that best fits them, which must fit within `tolerance.length`, then compares the largest distance between the two surfaces with `tol`. Against a cut file's region, `along` names the part axis its outline is projected along, and the part may be turned over. A shape check confirms the shape, not the params that build it: they still need their own checks.

**Over instances.** A `bbox`, `distance` or `angle` check that names `instances: [...]` in place of `part` is evaluated in the assembly frame, with its datums named `<instance>.<feature>`: an envelope of a subassembly, a spacing between parts. Datums of two different parts are only comparable this way.

**Tolerances.** `tol` overrides `tolerance.length` (or `tolerance.angle`, in degrees) for one check, and is how far its evidence lets the value stray. It is capped at 5% of each value the check compares, `tol_rel` at 0.25, a `range` check's `tol` at 5% of the span between its ends, and a shape check's at 1% of its body's bbox diagonal. The report lists every tolerance and overlap limit other than the default beside its check.

**What a check rests on.** A check rests on the weakest basis among the params it reads (a pose, a density, a count, its joint's range, the gears a pose moves through), or on source when it reads none; the report shows it. A mass check on a proposed density confirms the model given that density, not the density. A `source` param should be checked, its ledger value compared by a check or the param read by one; one that is not raises a warning.

### Worked values: `expect`

Where a source states the numbers a value is worked out from rather than the value, a `distance`, `angle`, `diameter`, `mass`, `stroke` or `count` check names `expect` in place of `evidence` and `key`: an expression over ledger values `<item>.<key>`, numbers and the functions a derived `expr` may call.

```yaml
  - {id: pitch-sun, kind: distance, between: [sun.flank_a, sun.flank_b],
     expect: "T1.module * T1.z_sun"}                              # module × teeth
  - {id: sun-planet, kind: distance, instances: [sun_1, planet_1], between: [sun_1.axis, planet_1.axis],
     expect: "T1.module * (T1.z_sun + T1.z_planet) / 2"}
```

Each ledger value reads as a check compares it: in the project's units, an angle in degrees, a rate per second ("1000 rpm" is 6000 °/s), and one printed with no unit as printed. Quote the expression, and put a space before a `-` that precedes an item, since an id may hold a hyphen. An expect reads no params: a param never supplies an expected value.

### Poses

A mechanism ([modeling.md](modeling.md#joints-and-loops)) can be checked moved. `pose` maps joints to values, each a param, a ledger value `<item>.<key>` or a number:

```yaml
  - {id: reach-30, kind: distance, instances: [ground_1, rocker_1], between: [ground_1.a, rocker_1.a],
     evidence: S3-sweep, key: AC, pose: {input: S3-sweep.turn}}
  - {id: travel, kind: distance, instances: [frame_1, carriage_1], between: [frame_1.a, carriage_1.a],
     along: x, evidence: S2-screw, key: lead, from: {}, pose: {screw: 360}}    # one turn, in degrees
  - {id: claw-stroke, kind: stroke, cable: claw, evidence: S1-servo, key: stroke, tol: 1.5}
  - {id: perch, kind: stroke, cable: leg_cord, from: {shin: shin_max}, pose: {servo: turn},
     evidence: P3-eq1, claim: shortens}
```

- **A pose value moves its joint from the assembly as built**: a revolute joint's in the project's angle unit, a slide's in its length unit. Build the assembly at the configuration the source measures from, so a stated value is the pose value itself.
- **A number** is a pose fixed by definition, not a ledger value: the one turn a lead "per turn" is stated over, which no source gives a number for. It reads in its joint's unit and adds nothing to what the check rests on. A pose a source states ("turned 30° on") names its ledger value.
- cadrev sets the joints the pose names, holds every other `actuated` joint as built, and moves the `passive` joints until every loop closes, on MuJoCo's model of the exported mechanism. A gear moves its other joint with the one a pose sets, a cable its closed joints with its wheel, through any chain. The check is then evaluated on the model's own geometry, placed where MuJoCo puts each body. Name `instances` on a posed check: a part's own frame reads the same at every pose.
- A pose the mechanism cannot reach is a finding, and its checks are not evaluated: a loop that stays open there, or a gear or cable the loops do not allow (`[loop-open]`: links too short, past a toggle, or coupled against the ring), or a joint pushed outside its `range` (`[joint-range]`).
- **`from`** on a `distance`, `angle` or `stroke` check names a second pose, and the check compares the change between the two: a slide's travel per screw turn, a carrier's turn per sun turn. `from: {}` is as built.
- **`stroke`** compares how far a cable shortens, as built to posed, with a ledger value. Without `pose` it is posed at the cable's wheel at its full turn. Where a source states only a direction of change, `claim: shortens` or `claim: lengthens` replaces `key`, cites the item stating it in `evidence`, and passes when the cable changes that way by more than `tolerance.length`.

### Ranges and sweeps

A joint's `range` is two params, each a pose value from as built, or one param for a one-ended motion ("a 180° rotation"), its other end as built. Ledger a stated range and read it into those params; a `range` check confirms it, and an interference check with `sweep` shows nothing collides across it.

```yaml
  - {id: toe-reach, kind: range, joint: toe, ends: [S2-toe.min, S2-toe.max]}
  - {id: toe-open, kind: range, joint: servo, ends: [S2-toe.closed, S2-toe.open],
     instances: [palm_1, toe_1], between: [palm_1.tip, palm_1.pivot, toe_1.tip]}
  - {id: toe-clear, kind: interference, pairs: [[palm_1, toe_1]], sweep: {joint: toe, steps: sweep_steps}}
```

- **`range`** names a `joint` and, in `ends`, one ledger value per range param, in order. Without `between`, cadrev poses the model at each stated end, which shows the mechanism reaches it, and compares the joint's range param with it: use it for the input's own range, an end past 180° included. With `between`, it poses the model at each end of the joint's range and compares the angle there (three datums) or the distance (two) with that end's ledger value: use it for a stated output, such as a toe that opens 0–40°, or a leg width a slide sets from 20 to 50 mm, whose joint range params are then `derived` from the stated ends.
- **`sweep: {joint, steps}`** evaluates an interference check at `steps` poses evenly spaced across the joint's range, ends included, and reports the worst overlap with its pair and pose. `steps` is a param, a whole number of at least 2. It is the sweep's resolution, a choice that states nothing about the object, so it needs no gap and is left out of what a check rests on and of exact.

### Worked example: a planetary train

A planetary train with one member fixed is a chain of [gears](modeling.md#joints-and-loops), each ratio derived from the stated tooth counts, checked against values `expect` works out. Here a table of the module and tooth counts is ledgered as `T1`, and a stated "7.2:1" as `R1` (`{ratio: 7.2}`). The ring is fixed, the sun `actuated`, the carrier `passive` on the ring, and each planet a `passive` revolute joint on the carrier.

```yaml
# params.yaml
  z_sun:         {basis: source,  from: T1.z_sun}             # likewise z_planet, z_ring, module
  carrier_ratio: {basis: derived, expr: z_sun / (z_sun + z_ring)}
  planet_ratio:  {basis: derived, expr: -z_ring / z_planet}          # planet on the carrier
# model.py: "gears": {"sun_carrier": {"driver": "sun", "driven": "carrier", "ratio": "carrier_ratio"},
#                     "carrier_planet_1": {"driver": "carrier", "driven": "planet_1", "ratio": "planet_ratio"}}
# checks.yaml
  - {id: carrier-turn, kind: angle, instances: [ring_1, carrier_1],
     between: [ring_1.d, ring_1.a, carrier_1.d], from: {}, pose: {sun: 360},
     expect: "360 / R1.ratio"}                                  # 50° per sun turn
```

The carrier's turn reads both gears' ratios, so the tooth counts are checked, while its expected value comes from the stated ratio: a wrong formula, a misread count or a sign error fails it. Place `ring_1.d` a quarter turn from the carrier's datum, so the unsigned angle stays on one side through the turn. The pitch diameter and planet-axis checks above then fail a ring count that breaks `z_ring = z_sun + 2 * z_planet`. A train with no member fixed is out of reach: a gear ties only two joints.

## gaps.yaml

```yaml
gaps:
  - id: G-pitch
    question: What is the pin-to-pin pitch of the finger link?
    ask: authors     # authors | measure | datasheet | test
```

A gap is a question whose answer would replace a proposed or measured value. The report lists each with its `ask` and the params whose `gap` names it.

## overlays.yaml

```yaml
overlays:
  - id: s1-palm-front
    image: figures/supp/image7.png
    part: palm              # a part in its own frame, or "assembly"; or instance: <instance>
    view: front             # front: X right, Z up · top: X right, Y up · right: Y right, Z up
                            # with up: y, front: X right, Y up · top: X right, -Z up · right: -Z right, Y up
    origin: [412, 618]      # the pixel where model (0, 0) lands
    calibration:
      pixels: [[120, 640], [705, 640]]   # two pixels spanning a known dimension
      evidence: S1-palm.L                 # that dimension
    mirror: false
```

Renders `build/overlays/<id>.png`: model edges in magenta over the figure, the calibration span in blue, one PNG pixel per image pixel below the title strip. It is visual evidence for a human and adds no pass or fail.

## plan.yaml

The plan says how the object is made and put together, once its design is accepted. `cadrev check` holds it to the built model and writes it as `build/plan.md`, the guide for whoever makes the object: each line with its quantity counted from the model, and each step that places an instance over its view.

```yaml
make:                    # each part that is made: how, in one operation or several in order
  body:  ["FDM print in PLA, deck face on the bed, no supports; ±0.2 mm", "ream the hub bore Ø32.5"]
  plate: "FDM print in PLA, flat"
buy:                     # each part that is bought, each screw by its thread param, and anything else
  fan:       "AKYGA AW-8A-BK 80 mm 12 V fan"
  lid_screw: "socket head cap screw, ISO 4762, A2 stainless"
  glue:      "cyanoacrylate, a drop"
steps:                   # the assembly sequence
  - {place: [body_1], note: "Deck down on the bench."}
  - {place: [fan_1, plate_1], with: {lid_screw: 4}, note: "Label towards the plate. 2.5 mm hex key, snug."}
```

- **Every part an instance places is made or bought**, one or the other. `make` gives its operations, as text; `buy` what is ordered. The plan counts each by its instances. A part made beside the object, a fit coupon or a jig, is a part no instance places: `make` lists it uncounted, and a step that places nothing says when it is used.
- **A `buy` entry may also name a thread param**, for what is ordered of it (a screw's head and material, a nut, a threaded insert), which the guide prints after its thread and length. Any other name is listed as written, uncounted: an adhesive, a wire.
- **Every instance is placed by exactly one step**; an assembly of one instance needs no steps. A step may also place nothing: one that only drives screws, or only says what to do.
- **Every instance is [held](#projectyaml)**, and one that floats is an error here: a plan says the object is put together.
- **Each step that places an instance has a view**, `build/steps/<n>.png`: the isometric view of what it places, in black and named by part, on what the steps before it placed, in grey, taking in the part each goes onto. View each as you write its step: it shows a part placed onto nothing, or before the one it goes inside.
- **`with`** counts what a step drives of a thread param: its screws, nuts or inserts. The plan totals them per thread param as the quantity to buy. Where the model has more holes threaded for a [screw](#threads) than the steps drive screws into, less the screws built as parts, a warning says so: an empty threaded hole may be meant.
- cadrev holds the plan's bookkeeping, not its judgement. Whether a tool reaches a feature and a hand can do a step is its author's to settle before writing it.

## Drawings

`cadrev check` writes `build/isometric.png`, the assembly as built, and `build/drawings/<part>.png` for each part: its front, top and right views in third-angle projection beside an isometric one. report.md opens on the isometric view and shows each part's drawing above the checks that read that part alone. A [plan](#planyaml)'s steps have their own views.

- **A drawing is dimensioned by its part's checks**: each unposed `bbox`, `distance`, `angle` and `diameter` check that reads the part in its own frame is a dimension where the check reads it, printed at the value as built, in blue where the check passes and red where it fails. An envelope no check compares is a reference dimension, in grey parentheses.
- **A declared thread** is drawn as a drawing shows one, a thin three-quarter circle beside its hole or shank, and called out by its designation; a clearance hole by its diameter and the screw it clears.
- The views are named by the axis the object stands on, `up` in project.yaml. A drawing adds no pass or fail.

## Statuses

`cadrev check` prints one status last, and report.md and report.json carry it.

| status | when | exit |
|---|---|---|
| **VERIFIED** | no error: every number is accounted for and every check passes, even if some params are proposed | 0 |
| **VERIFIED PENDING REVIEW** | VERIFIED but for figure readings without `confirmed_by` | 0 |
| **NOT VERIFIED** | at least one error | 1 |
| **PARTIAL** | `--no-build` or `--no-coverage` skipped part of the run, so it makes no claim and writes no report | 1 |

**Exact** qualifies VERIFIED: no param rests on a proposed value, physics values and a sweep's `steps` aside. report.md prints it under the status.

## Known first

`known_first: true` holds a project to what the sources settle: the parts whose every dimension is quoted, worked out from quotes, probed or measured.

- A param resting on proposed is an error, physics values and a sweep's `steps` aside, so a known-first project that is VERIFIED is exact.
- An in-scope ledger value nothing uses **waits**, and so does a gap no param names, the question a waiting part asks. The report lists both under Waiting. Everything else holds: the whole ledger is still harvested and covered.

Removing `known_first` returns the project to the full rules. A value the user supplies is `proposed`, its `rationale` naming them, so remove `known_first` first.
