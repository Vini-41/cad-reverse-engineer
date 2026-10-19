# Modeling

`model.py` defines one function. `cadrev check` imports it, calls it with the resolved parameters, exports STEP and measures the result.

```python
from build123d import *

def build(p):
    link = ...                                   # p.link_L etc.; p is read-only
    return {
        "parts":    {"finger_link": link},       # name -> Part in its own frame
        "datums":   {"finger_link.pin_a": (-p.pitch / 2, 0, 0)},    # named points, part frame
        "assembly": {"finger_link_1": ("finger_link", Location((0, 0, p.z1)))},
        # optional, for a mechanism: see "Joints and loops"
        "joints": {"input": {"type": "revolute", "parent": "palm_1", "child": "finger_link_1",
                             "axis": ["finger_link_1.pin_a", "finger_link_1.pin_a_top"],
                             "range": ["input_min", "input_max"], "drive": "actuated"}},
        "loops": {"closure": ["rocker_1.tip", "palm_1.pivot_d"]},
    }
```

## Contract

- **Every number comes from `p`.** model.py may contain only the literals in `model_literals` (default `0 1 2 -1 0.5 90 180 270 360`), so halving, unit vectors and right-angle rotations stay readable. Any other number is `[model-literal]`: add it to params.yaml with a basis, even a 0.2 mm clearance, a 45° chamfer or a count of 3. That is the point: the report then shows it as proposed. Compute from a param only what depends on it: an expression in `build` whose value stays the same whatever its params (`atan2(p.h, p.h)` for 45°, even inside `p.y * atan2(p.h, p.h)`, or `w / w` after `w = p.w`) is `[model-constant]`, on its line, so give its number its own param. A factor the geometry gives (the 3/2 that puts a rhombus centre at 1.5 × the half-height) is a number too: make it a derived param, `expr: 3 * rz / 2`, whose `interpretation` names the geometry. Respelling it from allowed literals (`rz + rz / 2`, `p.L / 2 / 2`, `p.a + p.a + p.a`) is `[model-arithmetic]`, naming the param and the factor. A factor one allowed literal multiplies or divides by (`p.x / 2`, `p.x / 90`) passes.
- **The lint closes every other route a number could take.** It is static, so these hold for the source text, whatever runs:
  - Literals count in every spelling: `1e1`, `3.0`, `0x3` and `3_0` are the numbers they spell. A sign is free: `-90` passes wherever `90` does.
  - Arithmetic on literals alone is folded, and the result must be an allowed literal too: `1 / 2` and `180 + 90` pass, `2*2 - 0.5` is `[model-arithmetic]`. So are the literals of a chain of one operator, `*` or `+` and `-`, in any order: `p.x*2*2`, `2*p.x*2` and `p.x - 90 - 0.5` are `[model-arithmetic]`, while `p.x*2*0.5` passes. Arithmetic with a param and one literal (`-p.pitch / 2`) is the model's own.
  - model.py imports only `build123d` and `math`; any other import, `__future__` and relative imports included, is `[model-import]`.
  - `float`, `int`, `complex` or `eval` of text (`float("4")`) is `[model-text-number]`. Converting a param (`int(p.n)`) passes.
- **Widening `model_literals` is shown.** A project.yaml `model_literals` other than the default is listed in the report under *Model literal override*, and in report.json's `model_literals`.
- **Parts live in their own frame**, placed where their checks expect: an envelope check with `axes: {L: x}` measures the part's X extent. Put the part's natural datum (a pivot, a mounting face) at the origin when the source defines one.
- **Datums** are the named points that `distance` checks measure: pin centres, pivot axes, mounting holes. Name them `<part>.<feature>` and compute them from the same params that place the feature, never as a second copy of the arithmetic.
- **Every datum lies on its part's solid**, within `tolerance.length`: on the axis of one of the part's cylindrical faces, between that face's ends, or on one of its faces. Place a hole's, pin's or pivot's datum on its axis (the centre of the bore at mid-thickness is safe); place a length a source gives to an end or a tip on that face. cadrev confirms each datum `build` returns, whether or not a check reads it; any other is `[datum-off-solid]`, naming the datum, its part and how far it lies from the nearest axis or face. A datum off the solid usually means the feature was built somewhere other than where its datum says, so move the feature, not the datum.
- **The assembly** places part instances with `Location`. Instances are what `interference` checks, checks over `instances` (an envelope or spacing across parts) and overlays of `assembly` use. An instance of a part `parts` does not hold is `[assembly-part]`.
- A project without model.py is `[model-missing]`. `p.<name>` for an undefined param fails the build, as does any exception model.py raises: `[model-build]`. Params neither the model nor a mass check reads raise the warning `[param-unused]`.
- `build` returns exactly this mapping (`joints`, `loops`, `tendons` and `contacts` optional): parts are build123d shapes, datums `(x, y, z)` tuples, assembly entries `(part name, Location)` pairs, the rest as in *Joints and loops*. Any other shape is `[model-return]`; a model.py that does not parse is `[model-syntax]`.

## Joints and loops

A mechanism names how its instances move; a static model leaves both keys out. checks.yaml then poses checks at joint values ([`project-format.md`](project-format.md#poses-and-the-mjcf-export)).

- **A joint** moves its `child` instance relative to its `parent`: `type: revolute` (the one type), `axis` two datums of the child, as `<instance>.<feature>`, on the hinge axis (a pivot's datum at mid-thickness and one on its end face), `range` two param names giving its limits in the project's angle unit (optional), and `drive: actuated` (an input, held where a pose sets it or else as built) or `passive` (moved to close the loops).
- **Joints form a tree**: an instance is the child of at most one joint, and no instance moves itself. Instances no joint moves are fixed where `assembly` places them.
- **A loop** closes a ring the tree leaves open: two `<instance>.<feature>` datums that must coincide, such as a four-bar's rocker tip and its ground pivot. Cut each ring at one pivot: joints for the others, a loop for that one.
- **Build the assembly closed, at its joints' zero**: the configuration the sources measure angles from, with every loop's datums together. A pose value turns a joint from there.
- **Physics values** go where the MJCF applies them, each as a param name ([`project-format.md`](project-format.md#physics-values)): a joint's `damping`, `stiffness` (a torsion spring, at rest as built) and `friction`; a tendon, `"tendons": {"cord": {"path": ["crank_1.tip", "rocker_1.pin"], "stiffness": "cord_k", "damping": "cord_c"}}`, an elastic cord through two or more `<instance>.<feature>` datums, at rest at its as-built length; and a part's contact friction, `"contacts": {"toe_pad": {"friction": "pad_mu"}}`, on every instance of that part.
- `joints` or `loops` of the wrong shape (not a mapping, a name that is not text, an unknown key, a `type` or `drive` outside those above) is `[model-return]`, and nothing is built.
- A joint the assembly cannot hinge is `[model-joint]`, one per joint, naming it and why: a `parent` or `child` that is no instance, an `axis` datum the child lacks, two axis datums within `tolerance.length` of each other (no direction), a `range` param params.yaml does not define or a range whose low end exceeds its high end, a child another joint already moves, or a ring of joints that moves an instance itself. A loop datum that names no `<instance>.<feature>` is `[model-loop]`, naming the loop. Either keeps the build and its unposed checks, but drops every joint and loop: no MJCF is written and no posed check is evaluated.
- A tendon datum that names no `<instance>.<feature>`, a contact on no part, or a physics slot naming a param params.yaml does not define is `[model-return]`, and drops the joints, loops, tendons and contacts the same way.
- Range params, physics params, and the param `density` the MJCF export weighs parts by, need no read in model.py.

## Building geometry that checks can see

- Build each part from its skeleton outward: datums first (pivots, pitches), then the solid around them. A pitch that a source states must be the distance between datums, so it can be checked.
- Model the published envelope exactly when a source gives one: the bbox check reads the outermost extent. Add features (fillets, bosses, tabs) inside that envelope, or treat the envelope as conflicting evidence.
- Keep purchased hardware (servos, bearings, springs) as simple envelope bodies sourced from a datasheet, with the mounting interface (holes, spline, shaft) modelled exactly where the datasheet defines it.
- Use the build123d builder API (`BuildPart`, `BuildSketch`, `Locations`, `Mode.SUBTRACT`) or algebra (`Box(...) - Cylinder(...)`). Both export identically.
- A part must be one valid solid (`[part-invalid]`): bodies that do not touch are separate parts, each placed in the assembly. Inspect `build/parts/<name>.step` in a viewer when a boolean misbehaves.

## Mapping published dimensions onto geometry

Most papers give envelopes (`L×H×W`) or kinematic lengths (`L3`) without datums. For each, decide and record in the param's `interpretation`:

- which part axis the value runs along;
- whether it is an overall extent, a pin-to-pin pitch, or a feature size;
- which configuration it is measured in (open, closed, standing, hanging).

When two readings are both plausible, pick one, record the other as a conflict, and name the gap that would settle it. The check then confirms the model realises the reading you chose; the conflict tells the reader that the choice is a choice.
