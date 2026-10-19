"""Run model.py, export it, and compare the geometry with the evidence."""

from __future__ import annotations

import importlib.util
import math
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from . import units
from .project import (
    Project,
    check_params,
    check_tolerance,
    expect_param_quantity,
    expr_names,
    overlap_limit,
    rests_on,
)

AXES = {"x": 0, "y": 1, "z": 2}


class Params:
    """Read-only parameter access that records which parameters the model used."""

    def __init__(self, values: dict[str, float]):
        self._values = values
        self.used: set[str] = set()

    def __getattr__(self, name: str) -> float:
        if name.startswith("_"):
            raise AttributeError(name)
        try:
            value = self._values[name]
        except KeyError:
            raise AttributeError(f"no parameter {name!r} in params.yaml") from None
        self.used.add(name)
        return value


@dataclass
class CheckResult:
    id: str
    kind: str
    ok: bool
    expected: str
    measured: str
    note: str = ""
    # What the check rests on, and the params it reads that rest on that basis.
    rests_on: str = "source"
    rests_on_params: list[str] = field(default_factory=list)
    # How many instance pairs an interference check evaluated; None for other kinds.
    pairs: int | None = None
    # The joint values a posed check was evaluated at: joint -> {from, value}; None when unposed.
    pose: dict | None = None
    # A swept interference check's joint, the range params it is swept between, their values and
    # how many poses it evaluated; None for a check not swept.
    sweep: dict | None = None


@dataclass
class Built:
    parts: dict
    datums: dict[str, tuple[float, float, float]]
    assembly: dict
    used: set[str]
    # joint name -> {type, parent, child, axis: [datum, datum], range: [param, param], drive}
    joints: dict = field(default_factory=dict)
    # loop name -> [<instance>.<feature>, <instance>.<feature>], two datums that must coincide
    loops: dict = field(default_factory=dict)


class Poser(Protocol):
    """What poses a check: the assembly placed at the joint values the check's pose names, and at
    those at gives (joint -> (value in the project's angle unit, what it is from)), with the pose
    as report.json shows it; None after a finding saying why it cannot be posed."""

    def __call__(self, c: dict, at: dict | None = None) -> tuple[Built, dict] | None: ...


DRIVES = ("actuated", "passive")
JOINT_KEYS = ("type", "parent", "child", "axis", "range", "drive")
# The param the MJCF export weighs every part by, as its volume times this density, where
# params.yaml defines it; without it MuJoCo infers each moving body's mass from its mesh.
EXPORT_DENSITY = "density"


def _names(value, count: int) -> bool:
    return (
        isinstance(value, (list, tuple))
        and len(value) == count
        and all(isinstance(v, str) for v in value)
    )


def _motion_breach(result) -> str | None:
    """Why build()'s joints or loops break the model contract, or None if they keep it."""
    for kind in ("joint", "loop"):
        for name in result.get(f"{kind}s", {}):
            if not isinstance(name, str):
                return f"{kind} {name}: its name must be text, not {type(name).__name__}"
    for name, joint in result.get("joints", {}).items():
        if not isinstance(joint, dict):
            return f"joint {name} must be a mapping, not {type(joint).__name__}"
        unknown = sorted(set(joint) - set(JOINT_KEYS))
        if unknown:
            return f"joint {name}: unknown key {unknown[0]!r}"
        if joint.get("type") != "revolute":
            return f"joint {name}: type must be 'revolute', not {joint.get('type')!r}"
        for key in ("parent", "child"):
            if not isinstance(joint.get(key), str):
                return f"joint {name}: {key} must name an assembly instance"
        if not _names(joint.get("axis"), 2):
            return f"joint {name}: axis must be two datums of its child, not {joint.get('axis')!r}"
        if "range" in joint and not _names(joint["range"], 2):
            return f"joint {name}: range must be two param names, not {joint['range']!r}"
        if joint.get("drive") not in DRIVES:
            return f"joint {name}: drive must be actuated or passive, not {joint.get('drive')!r}"
    for name, pair in result.get("loops", {}).items():
        if not _names(pair, 2):
            return f"loop {name} must be two <instance>.<feature> datums, not {pair!r}"
    return None


def _contract_breach(result) -> str | None:
    """Why build()'s return breaks the model contract, or None if it keeps it."""
    from build123d import Location
    from build123d.topology import Shape

    if not isinstance(result, dict):
        return f"must return a mapping of parts, datums and assembly, not {type(result).__name__}"
    for key in ("parts", "datums", "assembly", "joints", "loops"):
        if not isinstance(result.get(key, {}), dict):
            return f"{key} must be a mapping of names, not {type(result[key]).__name__}"
    for name, part in result.get("parts", {}).items():
        if not isinstance(part, Shape):
            return f"part {name} must be a build123d shape, not {type(part).__name__}"
        if not re.fullmatch(r"[\w.-]+", str(name)):
            return f"part name {name!r} must be letters, digits, '_', '.' or '-': it names build/parts/<name>.step"
    for name, point in result.get("datums", {}).items():
        if not (
            isinstance(point, (tuple, list))
            and len(point) == 3
            and all(isinstance(c, (int, float)) for c in point)
        ):
            return f"datum {name} must be an (x, y, z) tuple of numbers, not {point!r}"
    for inst, entry in result.get("assembly", {}).items():
        if not (
            isinstance(entry, (tuple, list))
            and len(entry) == 2
            and isinstance(entry[0], str)
            and isinstance(entry[1], Location)
        ):
            return f"assembly instance {inst} must be a (part name, Location) pair, not {entry!r}"
    return _motion_breach(result)


def build(p: Project) -> Built | None:
    spec = importlib.util.spec_from_file_location("cadrev_model", p.root / "model.py")
    assert spec is not None and spec.loader is not None  # a .py path always gets a source loader
    module = importlib.util.module_from_spec(spec)
    params = Params(p.values)
    writes_bytecode, sys.dont_write_bytecode = sys.dont_write_bytecode, True  # no __pycache__/
    try:
        spec.loader.exec_module(module)
        result = module.build(params)
    except (Exception, SystemExit) as exc:  # noqa: BLE001 - a broken model is a finding, not a crash
        p.error("model-build", f"model.build failed: {type(exc).__name__}: {exc}")
        return None
    finally:
        sys.dont_write_bytecode = writes_bytecode
    problem = _contract_breach(result)
    if problem:
        p.error("model-return", f"model.build {problem}")
        return None
    built = Built(
        parts=result.get("parts", {}),
        datums={
            k: (float(x), float(y), float(z)) for k, (x, y, z) in result.get("datums", {}).items()
        },
        assembly=result.get("assembly", {}),
        used=params.used,
        joints=result.get("joints", {}),
        loops=result.get("loops", {}),
    )
    for name in sorted(built.used):
        expect_param_quantity(p, name, ("length", "angle"), "in model.py")
    ranges = {n for joint in built.joints.values() for n in joint.get("range", [])}
    for name in sorted(ranges & p.values.keys()):
        expect_param_quantity(p, name, ("angle",), "in a joint's range")
    exported = ranges | ({EXPORT_DENSITY} if built.joints else set())
    unread = p.values.keys() - built.used - _used_by_derived(p) - check_params(p) - exported
    for name in sorted(unread):
        p.warn("param-unused", f"param {name} is defined but the model never reads it")
    for name, part in built.parts.items():
        solids = len(part.solids())
        if not part.is_valid:
            p.error("part-invalid", f"part {name}: solid is not valid")
        elif solids != 1:
            p.error(
                "part-invalid",
                f"part {name}: is {solids} solids, not one; fuse its bodies, "
                "or make each its own part placed in the assembly",
            )
    for name, point in built.datums.items():
        part = _owner(built, name)
        if part is not None:
            gap = _off_solid(built.parts[part], point, p.length_tol)
            if gap is not None:
                p.error(
                    "datum-off-solid",
                    f"datum {name} of part {part}: is {gap:.4g} from the nearest axis or face; "
                    "place it on a hole's, pin's or pivot's axis, or on a face",
                )
    for inst, (part, _) in list(built.assembly.items()):
        if part not in built.parts:
            p.error("assembly-part", f"assembly instance {inst}: unknown part {part!r}")
            del built.assembly[inst]
    if _linkage_flaws(p, built):
        built.joints, built.loops = {}, {}
    return built


def instance_datum(built: Built, name: str) -> tuple[str, str] | None:
    """The instance <instance>.<feature> names and its part's datum <part>.<feature>, or None if
    it names no datum of an instance of the assembly."""
    inst = _prefix(name, built.assembly)
    if inst is None:
        return None
    datum = f"{built.assembly[inst][0]}.{name[len(inst) + 1 :]}"
    return (inst, datum) if datum in built.datums else None


def _joint_flaw(p: Project, built: Built, joint: dict, moved_by: dict) -> str | None:
    """What makes this joint no hinge of the assembly, or None."""
    for key in ("parent", "child"):
        if joint[key] not in built.assembly:
            return f"{key} {joint[key]} is not an instance of the assembly"
    if joint["child"] in moved_by:
        return f"{joint['child']} is already the child of joint {moved_by[joint['child']]}"
    points = []
    for datum in joint["axis"]:
        named = instance_datum(built, datum)
        if named is None or named[0] != joint["child"]:
            return f"axis {datum} is not a datum of its child {joint['child']}"
        points.append(built.datums[named[1]])
    if math.dist(*points) <= p.length_tol:
        return f"axis {joint['axis'][0]} and {joint['axis'][1]} coincide, so they give the hinge no direction"
    for param in joint.get("range", []):
        if param not in p.values:
            return f"range names {param}, which params.yaml does not define"
    if "range" in joint:
        (low, lo), (high, hi) = ((n, p.values[n]) for n in joint["range"])
        if lo > hi:
            return f"range {low} {lo:g} exceeds {high} {hi:g}"
    return None


def _linkage_flaws(p: Project, built: Built) -> bool:
    """Add [model-joint] for each joint that is no hinge of the assembly (an unknown instance,
    datum or param, an axis with no direction, a range low end above its high end, an instance two
    joints move or that moves itself) and [model-loop] for each loop naming no datum of it; True if
    there is any."""
    flawed = False
    moved_by: dict[str, str] = {}  # child instance -> the joint moving it
    for name, joint in built.joints.items():
        flaw = _joint_flaw(p, built, joint, moved_by)
        if flaw:
            p.error("model-joint", f"joint {name}: {flaw}")
            flawed = True
        if (
            joint["child"] not in moved_by
            and {joint["parent"], joint["child"]} <= built.assembly.keys()
        ):
            moved_by[joint["child"]] = name
    ringed: set[str] = set()
    for start in moved_by:
        ring, inst = [moved_by[start]], built.joints[moved_by[start]]["parent"]
        while inst in moved_by and inst != start and len(ring) <= len(moved_by):
            ring.append(moved_by[inst])
            inst = built.joints[moved_by[inst]]["parent"]
        if inst == start and not ringed & set(ring):
            ringed |= set(ring)
            names = f"{', '.join(ring[:-1])} and {ring[-1]}" if len(ring) > 1 else ring[0]
            p.error(
                "model-joint",
                f"joint {ring[0]}: {start} moves itself through joint{'s' * (len(ring) > 1)} "
                f"{names}; close a ring of joints with a loop instead",
            )
            flawed = True
    for name, pair in built.loops.items():
        for datum in pair:
            if instance_datum(built, datum) is None:
                p.error(
                    "model-loop",
                    f"loop {name}: {datum} names no <instance>.<feature> datum of the assembly",
                )
                flawed = True
                break
    return flawed


# How finely _off_solid samples each edge of a cylindrical face to find the face's axial extent.
_EDGE_SAMPLES = 16


def _off_solid(part, point: tuple[float, float, float], tol: float) -> float | None:
    """How far point is from part's solid, or None if it lies on it within tol: on the axis of a
    cylindrical face between that face's axial bounds, or on a face. The distance to an axis is
    to the segment the face spans along it."""
    from build123d import GeomType, Vector

    at = Vector(*point)
    nearest = math.inf
    for face in part.faces():
        nearest = min(nearest, face.distance_to(at))
        if face.geom_type == GeomType.CYLINDER:
            axis = face.axis_of_rotation
            origin, direction = axis.position, axis.direction.normalized()
            spans = [  # the face's extent along its axis, from points along its edges
                (edge.position_at(i / _EDGE_SAMPLES) - origin).dot(direction)
                for edge in face.edges()
                for i in range(_EDGE_SAMPLES + 1)
            ]
            if not spans:
                continue
            along = min(max((at - origin).dot(direction), min(spans)), max(spans))
            nearest = min(nearest, (at - (origin + direction * along)).length)
    return None if nearest <= tol else nearest


def _used_by_derived(p: Project) -> set[str]:
    names = set()
    for spec in p.params.values():
        if spec.get("expr"):
            try:
                names |= expr_names(spec["expr"])
            except (SyntaxError, ValueError):
                pass  # already a param-derived finding
    return names


def export(p: Project, built: Built) -> list[Path]:
    from build123d import Compound, export_step

    out = p.root / "build"
    (out / "parts").mkdir(parents=True, exist_ok=True)
    written = []
    for name, part in built.parts.items():
        part.label = name
        target = out / "parts" / f"{name}.step"
        export_step(part, str(target))
        written.append(target)
    if built.assembly:
        children = []
        for inst, (part, location) in built.assembly.items():
            child = built.parts[part].moved(location)
            child.label = inst
            children.append(child)
        target = out / "assembly.step"
        export_step(Compound(children=children, label=p.meta.get("name", "assembly")), str(target))
        written.append(target)
    return written


def _expect(p: Project, ref: str, kind: str) -> float:
    value = p.compared_value(ref, kind)
    if value is None:
        raise KeyError(f"evidence value {ref}")
    return value


def _compared(
    p: Project, c: dict, rid: str, ref: str, measured: float, shown: str = ""
) -> CheckResult:
    """The comparison of a value a check evaluates with the ledger value at ref: it passes within
    the check's tolerance: tol, a length or for an angle check degrees, or for a mass check
    tol_rel, a fraction of that value."""
    expected = _expect(p, ref, c["kind"])
    tolerance = check_tolerance(p, c)
    if tolerance is None:
        raise KeyError("tol_rel")  # the only tolerance a comparing check can lack
    key, tol = tolerance
    band = ""
    if key == "tol_rel":
        tol, band = tol * expected, f" ±{tol:.0%}"
    return CheckResult(
        rid,
        c["kind"],
        abs(measured - expected) <= tol,
        f"{expected:g}{band} ({ref})",
        f"{measured:.4g}{shown}",
        c.get("interpretation", ""),
    )


def _instances(built: Built):
    for inst, (part, location) in built.assembly.items():
        yield inst, built.parts[part].moved(location)


def _placed(p: Project, built: Built, c: dict) -> dict | None:
    """The instances a check names in instances, each as its (part, Location) in the assembly;
    None, after a [check-config] finding, when the list is empty or names an unknown instance."""
    cid, names = c.get("id", "?"), c["instances"]
    if not names:
        p.error("check-config", f"check {cid}: instances is empty; name the instances it reads")
        return None
    unknown = [n for n in names if n not in built.assembly]
    if unknown:
        p.error(
            "check-config",
            f"check {cid}: {', '.join(unknown)} is not an instance of the assembly",
        )
        return None
    return {n: built.assembly[n] for n in names}


def _envelope(p: Project, built: Built, c: dict):
    """The shape a bbox check evaluates: its part in the part's frame, or the union of its
    instances where the assembly places them; None after a [check-config] finding."""
    from build123d import Compound

    if "instances" not in c:
        return built.parts[c["part"]]
    placed = _placed(p, built, c)
    if placed is None:
        return None
    return Compound(children=[built.parts[part].moved(loc) for part, loc in placed.values()])


def _prefix(name: str, owners) -> str | None:
    """The longest of owners that name starts with as <owner>.<feature>, or None."""
    return max((o for o in owners if str(name).startswith(f"{o}.")), key=len, default=None)


def _owner(built: Built, datum: str) -> str | None:
    """The part a datum named <part>.<feature> belongs to, or None if its prefix names no part."""
    return _prefix(datum, built.parts)


def _datums(p: Project, built: Built, c: dict) -> list[tuple[float, float, float]] | None:
    """The points of the datums a distance or angle check names in between: in one part's frame,
    or, under instances, each <instance>.<feature> as the assembly places it. None, after a
    [check-config] finding, when they belong to different parts without instances, or under
    instances name an unknown instance or feature."""
    if "instances" in c:
        return _instance_datums(p, built, c)
    owners = {_owner(built, d) for d in c["between"]} - {None}
    if len(owners) > 1:
        p.error(
            "check-config",
            f"check {c.get('id', '?')}: {' and '.join(c['between'])} are datums of different "
            f"parts, each in its own frame; a {c['kind']} compares datums of one part, or of "
            "several where it names them as <instance>.<feature> under instances: [...]",
        )
        return None
    return [built.datums[d] for d in c["between"]]


def _instance_datums(p: Project, built: Built, c: dict) -> list[tuple[float, float, float]] | None:
    """Each <instance>.<feature> in between: its part's datum <part>.<feature>, moved by the
    instance's Location. Names resolve against the check's instances only."""
    from build123d import Location

    placed = _placed(p, built, c)
    if placed is None:
        return None
    cid, points = c.get("id", "?"), []
    for name in c["between"]:
        inst = _prefix(name, placed)
        if inst is None:
            p.error(
                "check-config",
                f"check {cid}: {name} names none of its instances {', '.join(placed)}; "
                "name it <instance>.<feature>",
            )
            return None
        part, location = placed[inst]
        datum = f"{part}.{str(name)[len(inst) + 1 :]}"
        if datum not in built.datums:
            p.error(
                "check-config",
                f"check {cid}: {name}: instance {inst}'s part {part} has no datum {datum}",
            )
            return None
        at = (location * Location(built.datums[datum])).position
        points.append((at.X, at.Y, at.Z))
    return points


def _angle(p: Project, c: dict, points: list) -> float | None:
    """The angle in degrees at between[1] from the direction to between[0] to that to between[2];
    None, after a [check-config] finding, when there are not three datums or one coincides with
    the vertex, which leaves the angle undefined."""
    cid, names = c.get("id", "?"), c["between"]
    if len(points) != 3:
        p.error(
            "check-config", f"check {cid}: between names {len(points)} datums, not [a, vertex, b]"
        )
        return None
    a, vertex, b = points
    u, w = ([x - v for x, v in zip(end, vertex)] for end in (a, b))
    for end, d in ((names[0], u), (names[2], w)):
        # Zero-length within tolerance.length, not exactly: a direction that short has no angle
        # the check could confirm.
        if math.hypot(*d) <= p.length_tol:
            p.error(
                "check-config",
                f"check {cid}: {end} coincides with the vertex {names[1]}, "
                "so the angle is undefined",
            )
            return None
    cross = (u[1] * w[2] - u[2] * w[1], u[2] * w[0] - u[0] * w[2], u[0] * w[1] - u[1] * w[0])
    return math.degrees(math.atan2(math.hypot(*cross), sum(x * y for x, y in zip(u, w))))


def _turned(built: Built, view: Built, name: str, near: float) -> float:
    """How far joint name has turned its child about its axis, in degrees, from the assembly as
    built to view; of the readings a whole turn apart, the one nearest near."""
    from build123d import Location, Vector

    joint = built.joints[name]

    def relative(b: Built):
        return b.assembly[joint["parent"]][1].inverse() * b.assembly[joint["child"]][1]

    turn = relative(built).inverse() * relative(view)
    a, b = (Vector(*built.datums[_axis_datum(built, d)]) for d in joint["axis"])
    n = (b - a).normalized()
    u = n.cross(Vector(1, 0, 0))
    if u.length < 0.5:
        u = n.cross(Vector(0, 1, 0))
    v = (turn * Location((u.X, u.Y, u.Z))).position - turn.position
    angle = math.degrees(math.atan2(n.dot(u.cross(v)), u.dot(v)))
    return angle + 360 * round((near - angle) / 360)


def _axis_datum(built: Built, name: str) -> str:
    named = instance_datum(built, name)
    assert named is not None  # build drops joints whose axis names no datum
    return named[1]


def _joint(p: Project, built: Built, c: dict, pose: Poser | None, ranged: bool) -> dict | None:
    """The joint a range or sweep check names, with a range where ranged; None, after a
    [check-config] finding, when the model has no such joint or it has no range."""
    cid, name = c.get("id", "?"), _joint_name(c)
    if name is None:
        raise KeyError("joint")
    if pose is None:
        p.error(
            "check-config", f"check {cid}: names joint {name}, but model.build returns no joints"
        )
        return None
    joint = built.joints.get(name)
    if joint is None:
        p.error("check-config", f"check {cid}: {name} is not a joint")
        return None
    if ranged and "range" not in joint:
        p.error("check-config", f"check {cid}: joint {name} has no range")
        return None
    return {"name": name, **joint}


def _joint_name(c: dict) -> str | None:
    """The joint a range check names, or the one an interference check is swept over."""
    if c.get("kind") == "range":
        return c.get("joint")
    return (c.get("sweep") or {}).get("joint")


def _sweep(p: Project, built: Built, c: dict, pose: Poser | None) -> tuple[dict, list] | None:
    """The sweep of an interference check: its joint at steps evenly spaced values from one end
    of its range to the other, each pose as (view, its pose); None, after a finding, when the
    joint, its range or steps cannot be swept, or a loop stays open at one of its poses."""
    joint = _joint(p, built, c, pose, ranged=True)
    if joint is None or pose is None:
        return None
    cid, name, steps_name = c.get("id", "?"), joint["name"], c["sweep"]["steps"]
    steps = p.values[steps_name]
    if steps < 2 or steps != int(steps):
        p.error(
            "check-config",
            f"check {cid}: sweep steps {steps_name} is {steps:g}; sweep at least 2 poses, "
            "a whole number",
        )
        return None
    low_name, high_name = joint["range"]
    low, high = p.values[low_name], p.values[high_name]
    label, count, poses = f"{low_name}..{high_name}", int(steps), []
    for i in range(count):
        at = pose(c, {name: (low + (high - low) * i / (count - 1), label)})
        if at is None:
            return None
        poses.append(at)
    shown = {"joint": name, "from": [low_name, high_name], "range": [low, high], "poses": count}
    return shown, poses


def _range(p: Project, built: Built, c: dict, pose: Poser | None) -> list[CheckResult]:
    """A range check: the model posed at each end of its joint's range, the joint's turn, or the
    angle between datums, compared with the ledger value for that end."""
    joint = _joint(p, built, c, pose, ranged=True)
    if joint is None or pose is None:
        return []
    cid, name, ends = c.get("id", "?"), joint["name"], c["ends"]
    if len(ends) != 2:
        p.error("check-config", f"check {cid}: ends names {len(ends)} values, not [low, high]")
        return []
    degrees = units.size("angle", p.units) / units.UNITS["deg"].si
    results = []
    for param, ref in zip(joint["range"], ends):
        at = pose({**c, "pose": {**(c.get("pose") or {}), name: param}})
        if at is None:
            continue
        view, posed = at
        if "between" in c:
            points = _datums(p, view, c)
            measured = None if points is None else _angle(p, c, points)
            if measured is None:
                return results
            a, vertex, b = c["between"]
            shown = f"° at {vertex} between {a} and {b}"
        else:
            measured = _turned(built, view, name, posed[name]["value"] * degrees)
            shown = f"° {name} turned"
        result = _compared(p, c, f"{cid}.{param}", ref, measured, shown)
        result.pose = posed
        results.append(result)
    return results


def _count(p: Project, counts: dict, part: str) -> float:
    """How many of part a mass check weighs: the param its counts entry names, else 1."""
    return p.values[counts[part]] if part in counts else 1


def _volume(overlap) -> float:
    """The volume of an intersect() result: nothing, one shape, or a list of shapes."""
    if overlap is None:
        return 0.0
    if isinstance(overlap, list):  # a ShapeList, when the overlap is not one shape
        return sum(shape.volume for shape in overlap)
    return overlap.volume


def run_checks(p: Project, built: Built, pose: Poser | None = None) -> list[CheckResult]:
    """Evaluate every check: on the assembly as built, or, for a check that names a pose, on the
    assembly pose(check) places at it, a check that cannot be posed adding a finding instead."""
    results = []
    for c in p.checks:
        cid, kind = c.get("id", "?"), c.get("kind")
        start = len(results)
        view, posed = built, None
        if c.get("pose"):
            if pose is None:
                if any(f.rule in ("model-joint", "model-loop") for f in p.findings):
                    continue  # that finding says the joints were dropped, so nothing is posed
                joints = ", ".join(c["pose"])
                p.error(
                    "check-config",
                    f"check {cid}: its pose names {joints}, but model.build returns no joints",
                )
                continue
            at = pose(c)
            if at is None:
                continue
            view, posed = at
        try:
            if kind == "bbox":
                shape = _envelope(p, view, c)
                if shape is None:
                    continue
                s = shape.bounding_box().size
                size = (s.X, s.Y, s.Z)
                for key, axis in c["axes"].items():
                    ref, measured = f"{c['evidence']}.{key}", size[AXES[axis]]
                    results.append(_compared(p, c, f"{cid}.{key}", ref, measured, f" along {axis}"))
            elif kind == "distance":
                points = _datums(p, view, c)
                if points is None:
                    continue
                a, b = points
                if c.get("along"):
                    i = AXES[c["along"]]
                    measured = abs(a[i] - b[i])
                else:
                    measured = math.dist(a, b)
                ref, between = f"{c['evidence']}.{c['key']}", " - ".join(c["between"])
                results.append(_compared(p, c, cid, ref, measured, f" {between}"))
            elif kind == "angle":
                points = _datums(p, view, c)
                measured = None if points is None else _angle(p, c, points)
                if measured is None:
                    continue
                ref, (a, vertex, b) = f"{c['evidence']}.{c['key']}", c["between"]
                shown = f"° at {vertex} between {a} and {b}"
                results.append(_compared(p, c, cid, ref, measured, shown))
            elif kind == "mass":
                names = c.get("parts") or list(built.parts)
                counts = c.get("counts", {})
                density = p.values[c["density"]]
                measured = (
                    sum(built.parts[n].volume * _count(p, counts, n) for n in names) * density
                )
                measured += sum(p.values[n] for n in c.get("add", []))
                results.append(_compared(p, c, cid, f"{c['evidence']}.{c['key']}", measured))
            elif kind == "range":
                results += _range(p, built, c, pose)
            elif kind == "interference":
                limit = overlap_limit(p, c)
                pairs = [tuple(pair) for pair in c.get("pairs", [])]
                sweep, poses = None, [(view, None)]
                if "sweep" in c:
                    swept = _sweep(p, built, c, pose)
                    if swept is None:
                        continue
                    sweep, poses = swept
                pair_set = "listed" if pairs else "all"
                if not pairs:
                    names = sorted(view.assembly)
                    pairs = [(a, b) for i, a in enumerate(names) for b in names[i + 1 :]]
                worst, worst_pose, at, across = (0.0, ""), None, "", ""
                for placed, shown in poses:
                    shapes = dict(_instances(placed))
                    for a, b in pairs:
                        volume = _volume(shapes[a].intersect(shapes[b]))
                        if volume > worst[0]:  # name a pair only where instances overlap
                            worst, worst_pose = (volume, f"{a} ∩ {b}"), shown
                if sweep is not None:
                    across = f" across {sweep['poses']} poses of {sweep['joint']}"
                    if worst_pose is not None:
                        at = f" at {sweep['joint']} {worst_pose[sweep['joint']]['value']:g}"
                results.append(
                    CheckResult(
                        cid,
                        kind,
                        worst[0] <= limit,
                        f"overlap ≤ {limit:g}",
                        f"{worst[0]:.4g} {worst[1]}".strip()
                        + at
                        + f" over {len(pairs)} pair{'s' * (len(pairs) != 1)} ({pair_set})"
                        + across,
                        c.get("interpretation", ""),
                        pairs=len(pairs),
                        pose=worst_pose,
                        sweep=sweep,
                    )
                )
            else:
                p.error("check-kind", f"check {cid}: unknown kind {kind!r}")
                continue
        except (KeyError, TypeError, ValueError) as exc:
            p.error("check-config", f"check {cid}: missing or unknown {exc}")
            continue
        joint = built.joints.get(_joint_name(c) or "", {})
        basis, params = rests_on(p, c, tuple(joint.get("range", ())))
        for r in results[start:]:
            r.rests_on, r.rests_on_params = basis, params
            r.pose = r.pose or posed
    for r in results:
        if not r.ok:
            p.error("check-failed", f"{r.id}: expected {r.expected}, measured {r.measured}")
    return results
