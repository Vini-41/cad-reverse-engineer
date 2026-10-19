"""Run model.py, export it, and compare the geometry with the evidence."""

from __future__ import annotations

import importlib.util
import math
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from collections.abc import Callable

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
    # tendon name -> {path: [<instance>.<feature>, ...], stiffness: param, damping: param}
    tendons: dict = field(default_factory=dict)
    # part name -> {friction: param}, the contact values of every instance of that part
    contacts: dict = field(default_factory=dict)


# What poses a check: the assembly placed at the joint values the check's pose names, with the
# pose as report.json shows it; None after a finding saying why it cannot be posed.
Poser = Callable[[dict], "tuple[Built, dict] | None"]

DRIVES = ("actuated", "passive")
# The physics values (ADR-0008) a joint, tendon or part's contact may name, each as a param.
JOINT_PHYSICS = ("damping", "stiffness", "friction")
TENDON_PHYSICS = ("stiffness", "damping")
CONTACT_PHYSICS = ("friction",)
JOINT_KEYS = ("type", "parent", "child", "axis", "range", "drive", *JOINT_PHYSICS)
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
        problem = _physics_breach(f"joint {name}", joint, JOINT_PHYSICS, JOINT_KEYS)
        if problem:
            return problem
    for name, pair in result.get("loops", {}).items():
        if not _names(pair, 2):
            return f"loop {name} must be two <instance>.<feature> datums, not {pair!r}"
    for name, tendon in result.get("tendons", {}).items():
        if not isinstance(tendon, dict):
            return f"tendon {name} must be a mapping, not {type(tendon).__name__}"
        path = tendon.get("path")
        if not (isinstance(path, (list, tuple)) and len(path) >= 2 and _names(path, len(path))):
            return f"tendon {name}: path must be two or more datums, not {path!r}"
        problem = _physics_breach(f"tendon {name}", tendon, TENDON_PHYSICS, ("path",))
        if problem:
            return problem
    for part, contact in result.get("contacts", {}).items():
        if not isinstance(contact, dict):
            return f"contact {part} must be a mapping, not {type(contact).__name__}"
        problem = _physics_breach(f"contact {part}", contact, CONTACT_PHYSICS, ())
        if problem:
            return problem
    return None


def _physics_breach(what: str, entry: dict, physics: tuple, other: tuple) -> str | None:
    """Why entry has a key neither physics nor other names, or a physics value that is not a param
    name."""
    unknown = sorted(set(entry) - {*physics, *other})
    if unknown:
        return f"{what}: unknown key {unknown[0]!r}"
    for key in physics:
        if key in entry and not isinstance(entry[key], str):
            return f"{what}: {key} must be a param name, not {entry[key]!r}"
    return None


def physics_slots(built: Built) -> dict[str, list[str]]:
    """Each param a joint, tendon or contact names as a physics value, with where it applies."""
    slots: dict[str, list[str]] = {}
    for kind, entries, keys in (
        ("joint", built.joints, JOINT_PHYSICS),
        ("tendon", built.tendons, TENDON_PHYSICS),
        ("contact", built.contacts, CONTACT_PHYSICS),
    ):
        for name, entry in entries.items():
            for key in keys:
                if key in entry:
                    slots.setdefault(entry[key], []).append(f"{kind} {name}'s {key}")
    return slots


def _contract_breach(result) -> str | None:
    """Why build()'s return breaks the model contract, or None if it keeps it."""
    from build123d import Location
    from build123d.topology import Shape

    if not isinstance(result, dict):
        return f"must return a mapping of parts, datums and assembly, not {type(result).__name__}"
    for key in ("parts", "datums", "assembly", "joints", "loops", "tendons", "contacts"):
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
        tendons=result.get("tendons", {}),
        contacts=result.get("contacts", {}),
    )
    for name in sorted(built.used):
        expect_param_quantity(p, name, ("length", "angle"), "in model.py")
    ranges = {n for joint in built.joints.values() for n in joint.get("range", [])}
    for name in sorted(ranges & p.values.keys()):
        expect_param_quantity(p, name, ("angle",), "in a joint's range")
    slots = physics_slots(built)
    _check_physics(p, built, slots, ranges)
    exported = ranges | slots.keys() | ({EXPORT_DENSITY} if built.joints else set())
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
    flawed = _linkage_flaws(p, built)
    problem = _physics_unfit(p, built)
    if problem:
        p.error("model-return", f"model.build {problem}")
    if flawed or problem:
        built.joints, built.loops, built.tendons, built.contacts = {}, {}, {}, {}
    return built


def _check_physics(p: Project, built: Built, slots: dict[str, list[str]], ranges: set) -> None:
    """[param-physics]: a param a physics slot names must be marked physics: true, and one so
    marked must not be read as geometry or kinematics, since exact leaves it out (ADR-0008)."""
    for name, where in sorted(slots.items()):
        if name in p.params and name not in p.physics:
            p.error(
                "param-physics",
                f"param {name}: {where[0]} is a physics value, so mark the param physics: true",
            )
    read = built.used | check_params(p) | ranges
    for name in sorted(p.physics & read):
        p.error(
            "param-physics",
            f"param {name}: is marked physics: true, but the model's geometry, a joint range or a "
            "check reads it; a physics value only goes to a joint, tendon or contact",
        )


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


def _physics_unfit(p: Project, built: Built) -> str | None:
    """Why the tendons, contacts or physics slots build() returns do not fit its assembly: an
    unknown datum, part or param."""
    for name, tendon in built.tendons.items():
        for datum in tendon["path"]:
            if instance_datum(built, datum) is None:
                return f"tendon {name}: {datum} names no <instance>.<feature> datum of the assembly"
    for part in built.contacts:
        if part not in built.parts:
            return f"contact {part}: {part} is not a part"
    for param, where in physics_slots(built).items():
        if param not in p.values:
            return f"{where[0]} names {param}, which params.yaml does not define"
    return None


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
            elif kind == "interference":
                limit = overlap_limit(p, c)
                pairs = [tuple(pair) for pair in c.get("pairs", [])]
                shapes = dict(_instances(view))
                pair_set = "listed" if pairs else "all"
                if not pairs:
                    names = sorted(shapes)
                    pairs = [(a, b) for i, a in enumerate(names) for b in names[i + 1 :]]
                worst = (0.0, "")
                for a, b in pairs:
                    volume = _volume(shapes[a].intersect(shapes[b]))
                    if volume > worst[0]:  # name a pair only where instances overlap
                        worst = (volume, f"{a} ∩ {b}")
                results.append(
                    CheckResult(
                        cid,
                        kind,
                        worst[0] <= limit,
                        f"overlap ≤ {limit:g}",
                        f"{worst[0]:.4g} {worst[1]}".strip()
                        + f" over {len(pairs)} pair{'s' * (len(pairs) != 1)} ({pair_set})",
                        c.get("interpretation", ""),
                        pairs=len(pairs),
                    )
                )
            else:
                p.error("check-kind", f"check {cid}: unknown kind {kind!r}")
                continue
        except (KeyError, TypeError, ValueError) as exc:
            p.error("check-config", f"check {cid}: missing or unknown {exc}")
            continue
        basis, params = rests_on(p, c)
        for r in results[start:]:
            r.rests_on, r.rests_on_params, r.pose = basis, params, posed
    for r in results:
        if not r.ok:
            p.error("check-failed", f"{r.id}: expected {r.expected}, measured {r.measured}")
    return results
