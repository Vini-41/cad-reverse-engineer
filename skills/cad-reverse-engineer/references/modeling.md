# Modeling

`model.py` defines one function. `cadrev check` imports it, calls it with the resolved parameters, exports STEP and measures the result.

```python
from build123d import *

def build(p):
    link = ...                                   # p.bent_L etc.; p is read-only
    return {
        "parts":    {"bent_linkage": link},      # name -> Part in its own frame
        "datums":   {"bent_linkage.pin_a": (-p.pitch / 2, 0, 0)},   # named points, part frame
        "assembly": {"bent_linkage_1": ("bent_linkage", Location((0, 0, p.z1)))},
    }
```

## Contract

- **Every number comes from `p`.** model.py may contain only the literals in `model_literals` (default `0 1 2 -1 0.5 90 180 270 360`), so halving, unit vectors and right-angle rotations stay readable. Any other number is `[model-literal]`: add it to params.yaml with a basis, even a 0.2 mm clearance. That is the point: the report then shows it as proposed.
- **Parts live in their own frame**, placed where their checks expect: an envelope check with `axes: {L: x}` measures the part's X extent. Put the part's natural datum (a pivot, a mounting face) at the origin when the source defines one.
- **Datums** are the named points that `distance` checks measure: pin centres, pivot axes, mounting holes. Name them `<part>.<feature>` and compute them from the same params that place the feature, never as a second copy of the arithmetic.
- **The assembly** places part instances with `Location`. Instances are what `interference` checks and overlays of `assembly` use.
- `p.<name>` for an undefined param fails the build. Params the model never reads raise `[param-unused]`.
- `build` returns exactly this mapping: parts are build123d shapes, datums `(x, y, z)` tuples, assembly entries `(part name, Location)` pairs. Any other shape is `[model-return]`; a model.py that does not parse is `[model-syntax]`.

## Building geometry that checks can see

- Build each part from its skeleton outward: datums first (pivots, pitches), then the solid around them. A pitch that a source states must be the distance between datums, so it can be checked.
- Model the published envelope exactly when a source gives one: the bbox check reads the outermost extent. Add features (fillets, bosses, tabs) inside that envelope, or treat the envelope as conflicting evidence.
- Keep purchased hardware (servos, bearings, springs) as simple envelope bodies sourced from a datasheet, with the mounting interface (holes, spline, shaft) modelled exactly where the datasheet defines it.
- Use the build123d builder API (`BuildPart`, `BuildSketch`, `Locations`, `Mode.SUBTRACT`) or algebra (`Box(...) - Cylinder(...)`). Both export identically.
- A part must be one valid solid (`[part-invalid]`); inspect `build/parts/<name>.step` in a viewer when a boolean misbehaves.

## Mapping published dimensions onto geometry

Most papers give envelopes (`L×H×W`) or kinematic lengths (`L14`) without datums. For each, decide and record in the param's `interpretation`:

- which part axis the value runs along;
- whether it is an overall extent, a pin-to-pin pitch, or a feature size;
- which configuration it is measured in (open, closed, standing, hanging).

When two readings are both plausible, pick one, record the other as a conflict, and name the gap that would settle it. The check then confirms the model realises the reading you chose; the conflict tells the reader that the choice is a choice.
