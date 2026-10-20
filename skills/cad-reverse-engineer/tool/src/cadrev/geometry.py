"""Run model.py, export it, and compare the geometry with the evidence."""

from __future__ import annotations

import importlib.util
import math
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import NamedTuple, Protocol

from .project import (
    Project,
    between_two,
    check_params,
    check_physics_sources,
    check_tolerance,
    compared_quantity,
    expect_joint_value,
    joint_valued,
    expect_param_quantity,
    expr_names,
    mass_params,
    overlap_limit,
    resolution_params,
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
    # joint name -> {type, parent, child, axis: [datum, datum], range: [param, param], drive}; a
    # fixed joint has the first three alone
    joints: dict = field(default_factory=dict)
    # loop name -> [<instance>.<feature>, <instance>.<feature>], two datums that must coincide
    loops: dict = field(default_factory=dict)
    # tendon name -> {path: [<instance>.<feature>, ...], stiffness: param, damping: param}
    tendons: dict = field(default_factory=dict)
    # gear name -> {driver: joint, driven: joint, ratio: param}: driven moves ratio times driver
    gears: dict = field(default_factory=dict)
    # part name -> its Mass, for each part params.yaml's parts weighs
    masses: dict = field(default_factory=dict)
    # True when a [model-joint], [model-loop], [model-gear] or [model-return] finding dropped the
    # joints, loops, gears and tendons build() returned
    dropped: bool = False

    @property
    def moving(self) -> dict:
        """The joints that move their child relative to their parent: all but the fixed ones."""
        return {n: j for n, j in self.joints.items() if joint_type(j).mjcf is not None}


@dataclass
class Mass:
    """A part's mass, from the param params.yaml's parts names `by` (mass or density), and its
    centre of mass and inertia about that centre in the part's frame (ixx iyy izz ixy ixz iyz).
    Each number is rounded to the 12 digits the MJCF prints, so the export and report.json agree."""

    mass: float
    by: str
    param: str
    center: tuple[float, ...]
    inertia: tuple[float, ...]


class Poser(Protocol):
    """What poses a check: the assembly placed at the joint values the check's pose names, and at
    those set_to gives (joint -> (value in the project's angle unit, what it is from)), with the
    pose as report.json shows it; None after a finding saying why it cannot be posed. A joint
    set_to names is where its check puts it, so its own range is not held against it."""

    def __call__(self, c: dict, set_to: dict | None = None) -> tuple[Built, dict] | None: ...


def pose_text(pose: dict) -> str:
    """A pose as findings and report.md name it: `input at 60 (turn_60)`."""
    return ", ".join(f"{j} at {s['value']:g} ({s['from']})" for j, s in pose.items())


DRIVES = ("actuated", "passive")


class JointType(NamedTuple):
    """What a joint type is in the MJCF: its joint element's type, None for a fixed joint, whose
    child moves with its parent as one body; the quantity its value, range and poses are in; the
    verb a finding says it moves by; and the symbol a compared value of it is printed with."""

    mjcf: str | None
    quantity: str | None
    moves: str
    symbol: str = ""


JOINT_TYPES = {
    "revolute": JointType("hinge", "angle", "turns", "°"),
    "slide": JointType("slide", "length", "slides"),
    "fixed": JointType(None, None, "stays"),
}


def joint_type(joint: dict) -> JointType:
    """The JointType of a joint build() returned, once the contract has held its type."""
    return JOINT_TYPES[joint["type"]]


# What a fixed joint takes: its child moves with its parent, so it has no axis, range or drive.
FIXED_KEYS = ("type", "parent", "child")


class Slot(NamedTuple):
    """Where a physics value goes in the MJCF: the attribute it is written to, and the quantity
    it is in, which the export converts from the project's units to the MJCF's; None for a
    joint's own quantity, an angle on a revolute joint and a length on a slide."""

    attr: str
    quantity: str | None


# The physics values (ADR-0008) a joint or tendon may name, each as a param.
PHYSICS = {
    "joint": {
        "damping": Slot("damping", "torsional damping"),
        "stiffness": Slot("stiffness", "torsional stiffness"),
        "friction": Slot("frictionloss", "torque"),
        # The joint value at which its spring exerts no torque, measured from as built like a pose.
        "spring_rest": Slot("springref", None),
    },
    "tendon": {
        "stiffness": Slot("stiffness", "linear stiffness"),
        "damping": Slot("damping", "linear damping"),
    },
}
JOINT_KEYS = ("type", "parent", "child", "axis", "range", "drive", *PHYSICS["joint"])
# What names the as-built end of a one-ended range, a turn of 0 that no param states.
AS_BUILT = "as built"


def range_ends(p: Project, joint: dict) -> list[tuple[str, float]]:
    """A joint's range as its two ends, low first, each as (the param it is from, its value): a
    range of one param turns from the assembly as built (AS_BUILT, 0) to that param, either way."""
    ends: list[tuple[str, float]] = [(str(name), p.values[name]) for name in joint["range"]]
    if len(ends) == 1:
        ends = sorted([(AS_BUILT, 0.0), *ends], key=lambda end: end[1])
    return ends


def _names(value, count: int) -> bool:
    return (
        isinstance(value, (list, tuple))
        and len(value) == count
        and all(isinstance(v, str) for v in value)
    )


GEAR_KEYS = ("driver", "driven", "ratio")


def _motion_breach(result) -> str | None:
    """Why build()'s joints, loops, gears or tendons break the model contract, or None if they
    keep it."""
    for kind in ("joint", "loop", "gear"):
        for name in result.get(f"{kind}s", {}):
            if not isinstance(name, str):
                return f"{kind} {name}: its name must be text, not {type(name).__name__}"
    for name, joint in result.get("joints", {}).items():
        if not isinstance(joint, dict):
            return f"joint {name} must be a mapping, not {type(joint).__name__}"
        unknown = sorted(set(joint) - set(JOINT_KEYS))
        if unknown:
            return f"joint {name}: unknown key {unknown[0]!r}"
        if joint.get("type") not in JOINT_TYPES:
            kinds = " or ".join(repr(t) for t in JOINT_TYPES)
            return f"joint {name}: type must be {kinds}, not {joint.get('type')!r}"
        for key in ("parent", "child"):
            if not isinstance(joint.get(key), str):
                return f"joint {name}: {key} must name an assembly instance"
        if joint_type(joint).mjcf is None:
            continue  # a fixed joint takes nothing else, which [model-joint] says
        if not _names(joint.get("axis"), 2):
            return f"joint {name}: axis must be two datums of its child, not {joint.get('axis')!r}"
        if "range" in joint and not (_names(joint["range"], 1) or _names(joint["range"], 2)):
            return f"joint {name}: range must be one or two param names, not {joint['range']!r}"
        if joint.get("drive") not in DRIVES:
            return f"joint {name}: drive must be actuated or passive, not {joint.get('drive')!r}"
        problem = _physics_breach(f"joint {name}", joint, PHYSICS["joint"], JOINT_KEYS)
        if problem:
            return problem
    for name, pair in result.get("loops", {}).items():
        if not _names(pair, 2):
            return f"loop {name} must be two <instance>.<feature> datums, not {pair!r}"
    for name, gear in result.get("gears", {}).items():
        if not isinstance(gear, dict):
            return f"gear {name} must be a mapping, not {type(gear).__name__}"
        for key in sorted(set(gear) - set(GEAR_KEYS)):
            return f"gear {name}: unknown key {key!r}"
        for key in GEAR_KEYS:
            if not isinstance(gear.get(key), str):
                what = "a param name" if key == "ratio" else "a joint name"
                return f"gear {name}: {key} must be {what}, not {gear.get(key)!r}"
    for name, tendon in result.get("tendons", {}).items():
        if not isinstance(tendon, dict):
            return f"tendon {name} must be a mapping, not {type(tendon).__name__}"
        path = tendon.get("path")
        if not (isinstance(path, (list, tuple)) and len(path) >= 2 and _names(path, len(path))):
            return f"tendon {name}: path must be two or more datums, not {path!r}"
        problem = _physics_breach(f"tendon {name}", tendon, PHYSICS["tendon"], ("path",))
        if problem:
            return problem
    return None


def _physics_breach(what: str, entry: dict, physics: dict, other: tuple) -> str | None:
    """Why entry has a key neither physics nor other names, or a physics value that is not a param
    name."""
    unknown = sorted(set(entry) - {*physics, *other})
    if unknown:
        return f"{what}: unknown key {unknown[0]!r}"
    for key in physics:
        if key in entry and not isinstance(entry[key], str):
            return f"{what}: {key} must be a param name, not {entry[key]!r}"
    return None


def physics_named(kind: str, entry: dict) -> dict[str, Slot]:
    """The physics slots a joint or tendon names a param for, by key, each in its quantity: a
    joint's own, for a slot in no fixed one; None on a fixed joint, which [model-joint] refuses."""
    own = joint_type(entry).quantity if kind == "joint" else None
    return {
        key: slot._replace(quantity=slot.quantity or own)
        for key, slot in PHYSICS[kind].items()
        if key in entry
    }


def physics_slots(built: Built) -> dict[str, list[tuple[str, Slot]]]:
    """Each param a joint or tendon names as a physics value, with each place it applies and its
    Slot there."""
    slots: dict[str, list[tuple[str, Slot]]] = {}
    for kind, entries in (("joint", built.joints), ("tendon", built.tendons)):
        for name, entry in entries.items():
            for key, slot in physics_named(kind, entry).items():
                slots.setdefault(entry[key], []).append((f"{kind} {name}'s {key}", slot))
    return slots


def _contract_breach(result) -> str | None:
    """Why build()'s return breaks the model contract, or None if it keeps it."""
    from build123d import Location
    from build123d.topology import Shape

    if not isinstance(result, dict):
        return f"must return a mapping of parts, datums and assembly, not {type(result).__name__}"
    for key in ("parts", "datums", "assembly", "joints", "loops", "gears", "tendons"):
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
        gears=result.get("gears", {}),
    )
    for name in sorted(built.used):
        expect_param_quantity(p, name, ("length", "angle"), "in model.py")
    ranges = {n for joint in built.joints.values() for n in joint.get("range", [])}
    for joint in built.joints.values():
        quantity = joint_type(joint).quantity
        for name in joint.get("range", []):
            if name in p.values and quantity is not None:
                expect_param_quantity(p, name, (quantity,), f"in a {joint['type']} joint's range")
    ratios = {gear["ratio"] for gear in built.gears.values()}
    for name, gear in built.gears.items():
        if gear["ratio"] in p.values:
            expect_param_quantity(p, gear["ratio"], ("fraction",), f"as gear {name}'s ratio")
    slots = physics_slots(built)
    for name, where in sorted(slots.items()):
        for place, slot in where:
            if slot.quantity is not None:
                expect_param_quantity(p, name, (slot.quantity,), f"as {place}")
    _check_physics(p, built, slots, ranges | ratios)
    check_physics_sources(p, built.used)
    exported = ranges | ratios | slots.keys() | set(mass_params(p))
    derived = _used_by_derived(p)
    p.resolution = resolution_params(p) - built.used - derived - exported
    unread = p.values.keys() - built.used - derived - check_params(p) - exported
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
    flawed = _gear_flaws(p, built) or flawed
    problem = _physics_unfit(p, built)
    if problem:
        p.error("model-return", f"model.build {problem}")
    if flawed or problem:
        built.joints, built.loops, built.tendons, built.gears = {}, {}, {}, {}
        built.dropped = True
    _joint_values(p, built)
    built.masses = _mass_model(p, built)
    return built


def _joint_values(p: Project, built: Built) -> None:
    """[unit-quantity] for each pose value, and each end of a range check without between, in
    the other quantity than its joint's: a length for a revolute joint, an angle for a slide."""
    for c in p.checks:
        cid = c.get("id", "?")
        named = [
            (j, str(ref), f"in check {cid}'s pose") for j, ref in (c.get("pose") or {}).items()
        ]
        if joint_valued(c):
            named += [(c.get("joint"), str(ref), f"check {cid}") for ref in c.get("ends") or []]
        for joint, ref, use in named:
            if joint in built.moving:
                quantity = joint_type(built.moving[joint]).quantity
                expect_joint_value(p, ref, quantity, use)


def printed(*values: float) -> tuple[float, ...]:
    """values rounded to the 12 digits the MJCF prints, clear of a unit conversion's last bits, so
    the export and report.json show the same numbers."""
    return tuple(float(f"{v:.12g}") for v in values)


def _mass_model(p: Project, built: Built) -> dict[str, Mass]:
    """Each part's Mass from params.yaml's parts: its datasheet mass, or its volume times its
    density; the inertia is the solid's, scaled to that mass. A part of a model with joints that
    the entries leave unweighed, an entry naming an undefined param, or one naming no part is
    [part-mass]."""
    from build123d import CenterOf

    for name in p.parts.keys() - built.parts.keys():
        p.error("part-mass", f"params.yaml parts {name}: model.build returns no part {name}")
    masses = {}
    for name, part in built.parts.items():
        entry = p.parts.get(name) or {}
        by = next(iter(entry), None)
        if by is None:
            if built.joints:
                p.error(
                    "part-mass",
                    f"part {name}: params.yaml parts gives it no mass or density, so the MJCF "
                    "export cannot weigh it",
                )
            continue
        if entry[by] not in p.values:
            if entry[by] not in p.params:
                p.error(
                    "part-mass",
                    f"part {name}: params.yaml parts names {by} {entry[by]}, which params.yaml "
                    "does not define",
                )
            continue
        volume = part.volume
        value = p.values[entry[by]]
        mass = value if by == "mass" else volume * value
        inertia = part.matrix_of_inertia
        masses[name] = Mass(
            mass=printed(mass)[0],
            by=by,
            param=entry[by],
            center=printed(*part.center(CenterOf.MASS)),
            inertia=printed(
                *(
                    mass / volume * inertia[i][j]
                    for i, j in ((0, 0), (1, 1), (2, 2), (0, 1), (0, 2), (1, 2))
                )
            ),
        )
    return masses


def _check_physics(p: Project, built: Built, slots: dict, ranges: set) -> None:
    """[param-physics]: a param a physics slot names must be marked physics: true, and one so
    marked must not be read as geometry or kinematics, since exact leaves it out (ADR-0008)."""
    for name, where in sorted(slots.items()):
        if name in p.params and name not in p.physics:
            p.error(
                "param-physics",
                f"param {name}: {where[0][0]} is a physics value, so mark the param physics: true",
            )
    read = built.used | check_params(p) | ranges
    for name in sorted(p.physics & read):
        p.error(
            "param-physics",
            f"param {name}: is marked physics: true, but the model's geometry, a joint range or a "
            "check reads it; a physics value only goes to a joint or tendon",
        )


def instance_datum(built: Built, name: str) -> tuple[str, str] | None:
    """The instance <instance>.<feature> names and its part's datum <part>.<feature>, or None if
    it names no datum of an instance of the assembly."""
    inst = _prefix(name, built.assembly)
    if inst is None:
        return None
    datum = f"{built.assembly[inst][0]}.{name[len(inst) + 1 :]}"
    return (inst, datum) if datum in built.datums else None


def located(built: Built, name: str) -> tuple[str, tuple[float, float, float]]:
    """The instance a joint's, loop's or tendon's <instance>.<feature> names, and the datum's point
    in its part's frame, which is also its point in the instance's body frame."""
    named = instance_datum(built, name)
    assert named is not None  # build drops joints, loops and tendons naming no datum
    return named[0], built.datums[named[1]]


def _joint_flaw(p: Project, built: Built, joint: dict, moved_by: dict) -> str | None:
    """What makes this joint no hinge of the assembly, or None."""
    for key in ("parent", "child"):
        if joint[key] not in built.assembly:
            return f"{key} {joint[key]} is not an instance of the assembly"
    if joint["child"] in moved_by:
        return f"{joint['child']} is already the child of joint {moved_by[joint['child']]}"
    if joint_type(joint).mjcf is None:
        extra = [key for key in joint if key not in FIXED_KEYS]
        if extra:
            return (
                f"a fixed joint moves {joint['child']} with {joint['parent']}, so it takes no "
                f"{', '.join(extra)}; make it revolute or slide if it moves"
            )
        return None
    if "spring_rest" in joint and "stiffness" not in joint:
        return "spring_rest names no spring without a stiffness"
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
        (low, lo), (high, hi) = range_ends(p, joint)
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


def _gear_flaw(p: Project, built: Built, gear: dict) -> str | None:
    """What keeps this gear from coupling its joints, or None."""
    for key in ("driver", "driven"):
        if gear[key] not in built.joints:
            return f"{key} {gear[key]} is not a joint"
        if gear[key] not in built.moving:
            return f"{key} {gear[key]} is a fixed joint, which does not move"
    if gear["driver"] == gear["driven"]:
        return f"driver and driven are both {gear['driver']}; a gear couples two joints"
    driver, driven = (built.joints[gear[key]]["type"] for key in ("driver", "driven"))
    if driver != driven:
        return f"couples a {driver} joint with a {driven} one; a gear couples two of one type"
    if gear["ratio"] not in p.values:
        return f"ratio names {gear['ratio']}, which params.yaml does not define"
    return None


def _gear_flaws(p: Project, built: Built) -> bool:
    """Add [model-gear] for each gear that cannot couple its joints (an unknown or fixed joint,
    one joint twice, joints of two types, an undefined ratio param); True if there is any."""
    flawed = False
    for name, gear in built.gears.items():
        flaw = _gear_flaw(p, built, gear)
        if flaw:
            p.error("model-gear", f"gear {name}: {flaw}")
            flawed = True
    return flawed


def _physics_unfit(p: Project, built: Built) -> str | None:
    """Why the tendons or physics slots build() returns do not fit its assembly: an unknown datum
    or param."""
    for name, tendon in built.tendons.items():
        for datum in tendon["path"]:
            if instance_datum(built, datum) is None:
                return f"tendon {name}: {datum} names no <instance>.<feature> datum of the assembly"
    for param, where in physics_slots(built).items():
        if param not in p.values:
            return f"{where[0][0]} names {param}, which params.yaml does not define"
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


def _compared(
    p: Project,
    c: dict,
    rid: str,
    ref: str,
    measured: float,
    shown: str = "",
    quantity: str | None = None,
) -> CheckResult:
    """The comparison of a value a check evaluates with the ledger value at ref: it passes within
    the check's tolerance: tol, a length or for an angle check degrees, or for a mass check
    tol_rel, a fraction of that value. quantity, where given, is the one a range check compares
    its joint's own value in."""
    expected = p.value_as(ref, quantity or compared_quantity(c))
    if expected is None:
        raise KeyError(f"evidence value {ref}")
    tolerance = check_tolerance(p, c, quantity)
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


def _distance(c: dict, points: list) -> float:
    """The distance between a check's two datums, along its axis where it names one."""
    a, b = points
    if c.get("along"):
        i = AXES[c["along"]]
        return abs(a[i] - b[i])
    return math.dist(a, b)


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


def _joint_name(c: dict) -> str | None:
    """The joint a check names: a range check's joint, or the one a sweep is across."""
    return c.get("joint") or (c.get("sweep") or {}).get("joint")


def _joint(p: Project, built: Built, c: dict, poser: Poser | None) -> dict | None:
    """The ranged joint a range check names or an interference check is swept over; None, after
    a [check-config] finding, when the model has no such joint or it has no range."""
    cid, name = c.get("id", "?"), _joint_name(c)
    if name is None:
        raise KeyError("joint")
    if poser is None:
        p.error(
            "check-config", f"check {cid}: names joint {name}, but model.build returns no joints"
        )
        return None
    joint = built.joints.get(name)
    if joint is None:
        p.error("check-config", f"check {cid}: {name} is not a joint")
        return None
    if "range" not in joint:
        p.error("check-config", f"check {cid}: joint {name} has no range")
        return None
    return {"name": name, **joint}


def _sweep(p: Project, built: Built, c: dict, poser: Poser | None) -> tuple[dict, list] | None:
    """The sweep of an interference check: its joint at steps evenly spaced values from one end
    of its range to the other, each pose as (placed assembly, its pose); None, after a finding,
    when the joint, its range or steps cannot be swept, or a pose cannot be reached."""
    joint = _joint(p, built, c, poser)
    if joint is None or poser is None:
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
    (low_name, low), (high_name, high) = range_ends(p, joint)
    label, count, poses = f"{low_name}..{high_name}", int(steps), []
    for i in range(count):
        posed = poser(c, {name: (low + (high - low) * i / (count - 1), label)})
        if posed is None:
            return None
        poses.append(posed)
    shown = {"joint": name, "from": [low_name, high_name], "range": [low, high], "poses": count}
    return shown, poses


def _range(p: Project, built: Built, c: dict, poser: Poser | None) -> list[CheckResult]:
    """A range check, one result per end. With between, the model posed at that end of its
    joint's range, the angle there, or between two datums the distance, compared with the end's
    ledger value. Without, the model posed
    at the ledger value itself, so a loop that cannot close or a joint pushed past its own range
    there is a finding, and the range param for that end compared with it."""
    joint = _joint(p, built, c, poser)
    if joint is None or poser is None:
        return []
    cid, name, ends = c.get("id", "?"), joint["name"], c["ends"]
    if len(ends) != len(joint["range"]):
        wanted = "[low, high]" if len(joint["range"]) == 2 else "[end]"
        p.error("check-config", f"check {cid}: ends names {len(ends)} values, not {wanted}")
        return []
    kind = joint_type(joint)
    quantity = str(kind.quantity)
    results = []
    for param, ref in zip(joint["range"], ends):
        if "between" in c:
            reached = poser({**c, "pose": {**(c.get("pose") or {}), name: param}})
            if reached is None:
                continue
            placed, pose = reached
            points = _datums(p, placed, c)
            if points is not None and between_two(c):
                measured, shown = _distance(c, points), f" {' - '.join(c['between'])}"
            else:
                measured = None if points is None else _angle(p, c, points)
                if measured is None:
                    return results
                a, vertex, b = c["between"]
                shown = f"° at {vertex} between {a} and {b}"
        else:
            stated = p.evidence_value(ref)
            if stated is None or math.isnan(stated):
                raise KeyError(ref)
            reached = poser(c, {name: (stated, ref)})
            if reached is None:
                continue
            pose = reached[1]
            measured = p.values[param] * p.compared_size(quantity)
            shown = f"{kind.symbol} {name}'s range end ({param})"
        compared_in = compared_quantity(c) if "between" in c else quantity
        result = _compared(p, c, f"{cid}.{param}", ref, measured, shown, compared_in)
        result.pose = pose
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


def _mass(p: Project, built: Built, c: dict) -> CheckResult | None:
    """A mass check: the parts it names weighed by its density, or without one by the mass model
    as the MJCF export weighs them, times their counts, plus its add params; None after a
    [check-config] finding naming a part the mass model leaves unweighed."""
    names = c.get("parts") or list(built.parts)
    counts = c.get("counts", {})
    if "density" in c:
        density = p.values[c["density"]]
        each = {n: built.parts[n].volume * density for n in names}
    else:
        unweighed = [n for n in names if n not in built.masses]
        if unweighed:
            p.error(
                "check-config",
                f"check {c.get('id', '?')}: names no density, and the mass model in params.yaml "
                f"parts weighs no {', '.join(unweighed)}",
            )
            return None
        each = {n: built.masses[n].mass for n in names}
    measured = sum(each[n] * _count(p, counts, n) for n in names)
    measured += sum(p.values[n] for n in c.get("add", []))
    return _compared(p, c, c.get("id", "?"), f"{c['evidence']}.{c['key']}", measured)


def _interference(
    p: Project, built: Built, c: dict, placed: Built, poser: Poser | None
) -> CheckResult | None:
    """An interference check: the worst overlap among its pairs, on the placed assembly or, with
    sweep, across the poses of its joint's range, naming the pose it occurred at; None after a
    finding saying why it cannot be swept."""
    cid, limit = c.get("id", "?"), overlap_limit(p, c)
    pairs = [tuple(pair) for pair in c.get("pairs", [])]
    sweep, poses = None, [(placed, None)]
    if "sweep" in c:
        swept = _sweep(p, built, c, poser)
        if swept is None:
            return None
        sweep, poses = swept
    pair_set = "listed" if pairs else "all"
    if not pairs:
        names = sorted(placed.assembly)
        pairs = [(a, b) for i, a in enumerate(names) for b in names[i + 1 :]]
    worst, worst_pose, where, across = (0.0, ""), None, "", ""
    for assembly, pose in poses:
        shapes = dict(_instances(assembly))
        boxes = {name: shape.bounding_box().wrapped for name, shape in shapes.items()}
        for a, b in pairs:
            if boxes[a].IsOut(boxes[b]):
                continue  # apart, so no overlap: the boolean is the slow part of a sweep
            volume = _volume(shapes[a].intersect(shapes[b]))
            if volume > worst[0]:  # name a pair only where instances overlap
                worst, worst_pose = (volume, f"{a} ∩ {b}"), pose
    if sweep is not None:
        across = f" across {sweep['poses']} poses of {sweep['joint']}"
        if worst_pose is not None:
            where = f" at {sweep['joint']} {worst_pose[sweep['joint']]['value']:g}"
    return CheckResult(
        cid,
        "interference",
        worst[0] <= limit,
        f"overlap ≤ {limit:g}",
        f"{worst[0]:.4g} {worst[1]}".strip()
        + where
        + f" over {len(pairs)} pair{'s' * (len(pairs) != 1)} ({pair_set})"
        + across,
        c.get("interpretation", ""),
        pairs=len(pairs),
        pose=worst_pose,
        sweep=sweep,
    )


def _placed_for(
    p: Project, built: Built, c: dict, poser: Poser | None
) -> tuple[Built, dict | None] | None:
    """The assembly check c is evaluated on, with its pose: as built, or placed at the pose it
    names; None, after a finding, when it names a pose that cannot be placed."""
    if not c.get("pose"):
        return built, None
    if poser is None:
        if not built.dropped:  # else that finding says the joints were dropped
            p.error(
                "check-config",
                f"check {c.get('id', '?')}: its pose names {', '.join(c['pose'])}, but "
                "model.build returns no joints",
            )
        return None
    return poser(c)


def run_checks(p: Project, built: Built, poser: Poser | None = None) -> list[CheckResult]:
    """Evaluate every check: on the assembly as built, or, for a check that names a pose, on the
    assembly poser places at it, a check that cannot be posed adding a finding instead."""
    results = []
    for c in p.checks:
        cid, kind = c.get("id", "?"), c.get("kind")
        start = len(results)
        reached = _placed_for(p, built, c, poser)
        if reached is None:
            continue
        placed, pose = reached
        try:
            if kind == "bbox":
                shape = _envelope(p, placed, c)
                if shape is None:
                    continue
                s = shape.bounding_box().size
                size = (s.X, s.Y, s.Z)
                for key, axis in c["axes"].items():
                    ref, measured = f"{c['evidence']}.{key}", size[AXES[axis]]
                    results.append(_compared(p, c, f"{cid}.{key}", ref, measured, f" along {axis}"))
            elif kind == "distance":
                points = _datums(p, placed, c)
                if points is None:
                    continue
                measured = _distance(c, points)
                ref, between = f"{c['evidence']}.{c['key']}", " - ".join(c["between"])
                results.append(_compared(p, c, cid, ref, measured, f" {between}"))
            elif kind == "angle":
                points = _datums(p, placed, c)
                measured = None if points is None else _angle(p, c, points)
                if measured is None:
                    continue
                ref, (a, vertex, b) = f"{c['evidence']}.{c['key']}", c["between"]
                shown = f"° at {vertex} between {a} and {b}"
                results.append(_compared(p, c, cid, ref, measured, shown))
            elif kind == "mass":
                results += filter(None, [_mass(p, built, c)])
            elif kind == "range":
                results += _range(p, built, c, poser)
            elif kind == "interference":
                results += filter(None, [_interference(p, built, c, placed, poser)])
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
            r.pose = r.pose or pose
    for r in results:
        if not r.ok:
            p.error("check-failed", f"{r.id}: expected {r.expected}, measured {r.measured}")
    return results
