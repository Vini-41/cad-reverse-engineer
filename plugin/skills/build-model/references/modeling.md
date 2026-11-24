# Modeling

`model.py` defines one function. `cadrev check` calls it with the resolved params, holds what it returns to the contract below, exports STEP and evaluates the checks on it.

```python
from build123d import *

def build(p):
    link = ...                                   # p.link_L etc.; p is read-only
    return {
        "parts":    {"finger_link": link},       # name -> Part in its own frame
        "datums":   {"finger_link.pin_a": (-p.pitch / 2, 0, 0)},    # named points, part frame
        "assembly": {"finger_link_1": ("finger_link", Location((0, 0, p.z1)))},
        "sheets":   {"plates@30,41": ("finger_link", Location((p.at_x, p.at_y, 0)))},  # cut file
        "threads":  {"finger_link.pin_a": "pin_screw"},              # datum -> thread param
        # for a mechanism, see Joints and loops:
        "joints": {"input": {"type": "revolute", "parent": "palm_1", "child": "finger_link_1",
                             "axis": ["finger_link_1.pin_a", "finger_link_1.pin_a_top"],
                             "range": ["input_min", "input_max"], "drive": "actuated"}},
        "loops": {"closure": ["rocker_1.tip", "palm_1.pivot_d"]},
    }
```

## Contract

- **Every number comes from `p`.** model.py may hold only 0, 1, 2, 0.5, 90, 180, 270 and 360, a sign aside, which keep halving, unit vectors and right-angle turns readable. Any other number, even a 0.2 mm clearance, a 45° chamfer or a count of 3, is a param in params.yaml with a basis, so the report shows it for what it is. Arithmetic on literals alone counts as the number it works out to.
- **Every part is built from `p`** with build123d's primitives and operations. model.py imports only `build123d` and `math` and reads no file: a part loaded from the authors' STEP or STL would be compared with itself, and its params would check nothing.
- **Parts live in their own frame**, placed where their checks read them: a bbox check with `axes: {L: x}` reads the part's X extent. Put the part's natural datum (a pivot, a mounting face) at the origin where the source defines one. A part a released STEP or STL ships lives in that body's frame, where the file holds it, so its shape check compares the two in place; the assembly places its instances through the inverse of that frame. A part is one valid solid; bodies that do not touch are separate parts, each placed in the assembly.
- **Datums** are the named points checks and joints read: pin centres, pivots, mounting holes, tips. Name each `<part>.<feature>` and compute it from the same params that place the feature. A datum lies on its part's solid within `tolerance.length`: on a face, or on the axis of a cylindrical face between that face's ends (a bore's centre at mid-thickness is safe). One off the solid usually means the feature was built somewhere other than where its datum says, so move the feature.
- **Sheets** place each part cut from a cut file where the file draws it: `<source>@<x>,<y>` names the region, and the `Location` carries the part's outline, projected along its shape check's `along`, onto the region: a shift in the sheet's plane, a turn about its normal, and a half turn about x for a part turned over. A part cut from several regions is placed once per region. The numbers are params citing the region.
- **The assembly** places instances of parts with `Location`, as many of each part as the object has, at the configuration the sources measure their angles and strokes from. Instances are what interference and mass checks, checks over `instances` and joints read. Place each instance on what holds it, touching it or apart from it by the fit's param, the loosest of which is project.yaml's [`clearance`](project-format.md#projectyaml): `cadrev check` names what floats, and a part in mid-air is the first thing an engineer sees in the STEP file.
- **The object stands on Z**, the axis the [drawings](project-format.md#drawings) name their views by. Where released geometry stands on Y, as a file from a Y-up CAD program does, build on Y and say `up: y` in project.yaml.

## Threads

A thread is declared, never cut. Build a threaded hole or shank as a plain cylinder, and name its thread in `threads` at a datum on that cylinder: on its wall, or on its axis between its ends. The STEP files then hold plain holes a CAD program can thread in its own way, and the thread itself is in the report and on the drawing, where a reviewer reads it.

- **A [thread param](project-format.md#threads) reads as its major diameter**, `p.pin_screw`, and carries the sizes its table gives it, each in the project's length unit: `p.pin_screw.tap`, the hole that carries the thread, its major diameter less its pitch, which a shop drills with the nearest drill on its chart; `p.pin_screw.clearance`, the hole its screw passes through; `p.pin_screw.pitch`. Where no source or released body gives a hole's diameter, size it from these, so no hole diameter is proposed beside a thread.
- **Both holes of a screwed joint are declared**, each once, at one datum: the one that carries the thread and the one that clears the screw. cadrev holds each declared cylinder to its thread: from the thread's minor diameter to its major where it carries the thread, and from there to the loosest clearance hole its table gives where it clears the screw, so a released body's hole keeps the size its file gives it and is declared all the same. The drawing calls each out.
- **The model is fitted to the screw.** A [screw](project-format.md#threads)'s length is a param of its own, read like any other (`p.pin_screw_len`). Derive from it the boss, the counterbore and the blind hole that hold the screw, so the screw that is bought is the one that fits.
- **A screw, nut or washer is a part only where the sources list it as one**, or a stated mass counts it. It is then purchased hardware like any other: a head and a plain shank, its thread declared on the shank. A stated number of screws is checked without them, by a [`count` check](project-format.md#checksyaml) of the thread, and the [plan](project-format.md#planyaml)'s steps drive them.

## Joints and loops

A mechanism says how its instances move; a static model leaves these keys out. checks.yaml then poses checks at joint values ([project-format.md](project-format.md#poses)).

- **A joint** moves its `child` instance relative to its `parent`:
  - `revolute`: the child turns about `axis`, two datums of the child on the hinge axis, named `<instance>.<feature>` (a pivot's datum at mid-thickness and one on its end face).
  - `slide`: the child slides along `axis`, from its first datum towards its second.
  - `fixed`: `type`, `parent` and `child` alone; the child moves with its parent as one body (a servo in its mount).

  A revolute joint or slide takes `drive: actuated` (an input, held where a pose sets it, else as built) or `passive` (moved to close the loops), and optionally `range`: two param names, its low and high ends, or one, a move from as built to that value.
- **Joints form a tree**: an instance is the child of at most one joint. Instances no joint moves stay where the assembly places them.
- **A loop** closes a ring the tree leaves open: two `<instance>.<feature>` datums that must coincide, such as a four-bar's rocker tip and its ground pivot. Cut each ring at one revolute joint: a joint for each of the others, a loop for that one. Build the assembly closed, with every loop's datums together.
- **A coupling** ties two joints, so one moves in step with the other. `"couplings": {"mesh": {"driver": "input", "driven": "output", "ratio": "gear_ratio"}}` moves `driven` `ratio` times as far as `driver`, for meshed gears or a belt between two joints of one type; the ratio is a param, negative where the two turn opposite ways, and one stated only in words is proposed, its rationale quoting them. `"lead": "screw_lead"` in place of `ratio` couples a revolute joint and a slide: a lead screw, or a rack and pinion whose lead is its pitch circumference. The lead is a length param, how far the slide moves per full turn, negative where the slide moves toward its axis's first datum as the revolute joint turns positive. Couplings chain: a belt from a motor to each screw, then a lead from each screw to its carriage; a planetary train is sun to carrier, then carrier to each planet ([worked example](project-format.md#worked-example-a-planetary-train)).
- **A cable** is an inextensible cord through two or more `<instance>.<feature>` datums, a path whose length a `stroke` check reads: `"cables": {"claw": {"path": ["frame_1.guide", "toe_1.eye", "tip_1.eye"]}}`. Each joint a cord closes is a coupling on the joint that winds it (a servo's horn, or a slide whose stroke pulls the cord), worked out from the joint's closed value and the driving joint's travel, each a param with its own basis: a `ratio` between joints of one type, the closed value over the travel (`toe_closed / servo_turn`), or a `lead` across types, the slide's travel per full turn (`pull * 360 / servo_turn`, in degrees, for a slide the horn draws `pull` over `servo_turn`). A closed value no source states is proposed, with a gap. A coupling moves its joint in proportion, so a stated order of closing (one joint before another, through spring preload) is not represented, and the closed value's `interpretation` says so.
- A joint, loop, coupling or cable the assembly cannot hold (an unknown instance or datum, a child two joints move, a ring of joints with no loop) is a finding that keeps the build and its unposed checks but drops the motion: nothing is posed or exported until it is fixed.

`cadrev check` exports a mechanism as `build/model.mjcf` with one mesh per part: a kinematic model in the project's units, without gravity, each body weighed by the [mass model](project-format.md#paramsyaml). A model with no joints is static and writes none.

## Geometry that checks can see

- Build each part from its skeleton outward: datums first (pivots, pitches), then the solid around them. A pitch a source states must be the distance between two datums.
- Model a published envelope exactly: a bbox check reads the outermost extent, so features (fillets, bosses, tabs) go inside it, or the envelope is recorded as a conflict.
- Keep purchased hardware (servos, bearings, springs) as simple envelope bodies from the datasheet, with the mounting interface modelled where the datasheet defines it, and whatever it hangs by: a spring's hooks reach the pins they hook on.
- Most papers give envelopes (`L×H×W`) or kinematic lengths (`L3`) without saying where they run. For each, decide which part axis it runs along, whether it is an overall extent, a pin-to-pin pitch or a feature size, and which configuration it is taken in, and record that in the param's `interpretation`. Where two readings are both plausible, pick one, record the other as a conflict, and name the gap that would settle it.
