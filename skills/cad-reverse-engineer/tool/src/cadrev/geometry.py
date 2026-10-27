"""Run model.py, export it, and compare the geometry with the evidence."""

from __future__ import annotations

import importlib.util
import math
import re
import sys
from collections import Counter
from collections.abc import Callable, Iterable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from functools import partial
from pathlib import Path
from typing import NamedTuple, Protocol

from . import accounting, released
from .project import (
    AXES,
    CLAIMS,
    POSES,
    Project,
    between_two,
    check_params,
    cited_refs,
    claim_config,
    check_tolerance,
    compared_quantity,
    expect_joint_value,
    joint_valued,
    expect_param_quantity,
    expr_names,
    mass_params,
    overlap_limit,
    resolution_params,
)


class Params:
    """Read-only parameter access that records which parameters the model used."""

    def __init__(self, values: dict[str, float], declared: Iterable[str]):
        self._values = values
        self._declared = set(declared)
        self.used: set[str] = set()

    def __getattr__(self, name: str) -> float:
        if name.startswith("_"):
            raise AttributeError(name)
        try:
            value = self._values[name]
        except KeyError:
            if name in self._declared:
                raise AttributeError(f"param {name!r} has no value") from None
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
    # A stroke check's from pose, in the same form, which its stroke is taken from; None when
    # taken from as built.
    from_pose: dict | None = None
    # A swept interference check's joint, the range params it is swept between, their values and
    # how many poses it evaluated; None for a check not swept.
    sweep: dict | None = None
    # A mass check's parts weighed in several instances with no counts entry: part -> how many,
    # which make it rest on proposed; None for other kinds.
    uncounted: dict | None = None
    # A shape check's fit: the largest distance its datum pairs are left apart (residual), and,
    # once they fit, the largest distance between the surfaces (distance) and where it occurs in
    # the body's frame (worst_point); None for other kinds.
    shape: dict | None = None


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
    # cable name -> {path: [<instance>.<feature>, ...], wheel: joint, closes: {joint: param}}: an
    # inextensible cord; its wheel's full turn moves each joint it closes to that param's value
    cables: dict = field(default_factory=dict)
    # part name -> its Mass, for each part params.yaml's parts weighs
    masses: dict = field(default_factory=dict)
    # True when a [model-joint], [model-loop], [model-gear], [model-cable] or [model-return]
    # finding dropped the joints, loops, gears, tendons and cables build() returned
    dropped: bool = False
    # The joints the pose this assembly is placed at moves, itself or through a gear or cable;
    # none as built
    moved: frozenset[str] = frozenset()

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
    those set_to gives (joint -> (value in the project's angle unit, what it is from)), its moved
    naming those joints and each a gear or cable moves with them, with the pose as report.json
    shows it; None after a finding saying why it cannot be posed. A joint
    set_to names is where its check puts it, so its own range is not held against it. at names the
    key of c whose joint values it poses at, and which its findings name: pose, or a stroke
    check's from (POSES)."""

    def __call__(
        self, c: dict, set_to: dict | None = None, at: str = "pose"
    ) -> tuple[Built, dict] | None: ...


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
CABLE_KEYS = ("path", "wheel", "closes")


def _motion_breach(result) -> str | None:
    """Why build()'s joints, loops, gears, cables or tendons break the model contract, or None if
    they keep it."""
    for kind in ("joint", "loop", "gear", "cable"):
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
    for name, cable in result.get("cables", {}).items():
        if not isinstance(cable, dict):
            return f"cable {name} must be a mapping, not {type(cable).__name__}"
        for key in sorted(set(cable) - set(CABLE_KEYS)):
            return f"cable {name}: unknown key {key!r}"
        path = cable.get("path")
        if not (isinstance(path, (list, tuple)) and len(path) >= 2 and _names(path, len(path))):
            return f"cable {name}: path must be two or more datums, not {path!r}"
        if ("wheel" in cable) != ("closes" in cable):
            return f"cable {name}: wheel and closes go together"
        if "wheel" in cable and not isinstance(cable["wheel"], str):
            return f"cable {name}: wheel must be a joint name, not {cable['wheel']!r}"
        closes = cable.get("closes", {})
        if not (
            isinstance(closes, dict)
            and all(isinstance(k, str) and isinstance(v, str) for k, v in closes.items())
        ):
            return f"cable {name}: closes must map joint names to param names, not {closes!r}"
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
    for key in ("parts", "datums", "assembly", "joints", "loops", "gears", "tendons", "cables"):
        if not isinstance(result.get(key, {}), dict):
            return f"{key} must be a mapping of names, not {type(result[key]).__name__}"
    for name, part in result.get("parts", {}).items():
        if not isinstance(part, Shape):
            return f"part {name} must be a build123d shape, not {type(part).__name__}"
        if not re.fullmatch(r"[\w.-]+", str(name)):
            return (
                f"part name {name!r} must be letters, digits, '_', '.' or '-': "
                "it names build/parts/<name>.step"
            )
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
    params = Params(p.values, p.params)
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
        cables=result.get("cables", {}),
    )
    for name in sorted(built.used):
        expect_param_quantity(p, name, ("length", "angle"), "in model.py")
    ranges = {n for joint in built.joints.values() for n in joint.get("range", [])}
    for joint in built.joints.values():
        quantity = joint_type(joint).quantity
        for name in joint.get("range", []):
            if name in p.values and quantity is not None:
                expect_param_quantity(p, name, (quantity,), f"in a {joint['type']} joint's range")
    # gear ratios and cables' closed poses, which the MJCF exports as joint equalities
    ratios = {gear["ratio"] for gear in built.gears.values()}
    for name, gear in built.gears.items():
        if gear["ratio"] in p.values:
            expect_param_quantity(p, gear["ratio"], ("fraction",), f"as gear {name}'s ratio")
    for name, cable in built.cables.items():
        for joint, param in cable.get("closes", {}).items():
            quantity = joint_type(built.joints[joint]).quantity if joint in built.joints else None
            if param in p.values and quantity is not None:
                expect_param_quantity(p, param, (quantity,), f"as cable {name}'s closed {joint}")
    ratios |= {n for cable in built.cables.values() for n in cable.get("closes", {}).values()}
    slots = physics_slots(built)
    for name, where in sorted(slots.items()):
        for place, slot in where:
            if slot.quantity is not None:
                expect_param_quantity(p, name, (slot.quantity,), f"as {place}")
    _check_physics(p, built, slots, ranges | ratios)
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
            gap = released.off_solid(built.parts[part], point, p.length_tol)
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
    flawed = _cable_flaws(p, built) or flawed
    problem = _physics_unfit(p, built)
    if problem:
        p.error("model-return", f"model.build {problem}")
    if flawed or problem:
        built.joints, built.loops, built.tendons, built.gears, built.cables = {}, {}, {}, {}, {}
        built.dropped = True
    _cables_on_axes(p, built)
    _joint_values(p, built)
    built.masses = _mass_model(p, built)
    return built


def _joint_values(p: Project, built: Built) -> None:
    """[unit-quantity] for each pose value, and each end of a range check without between, in
    the other quantity than its joint's: a length for a revolute joint, an angle for a slide."""
    for c in p.checks:
        cid = c.get("id", "?")
        named = [
            (j, str(ref), f"in check {cid}'s {key}")
            for key in POSES
            for j, ref in (c.get(key) or {}).items()
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
        return (
            f"axis {joint['axis'][0]} and {joint['axis'][1]} coincide, "
            "so they give the hinge no direction"
        )
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


def _cable_flaw(p: Project, built: Built, cable: dict, closed_by: dict) -> str | None:
    """What keeps this cable from being laid or from closing its joints, or None."""
    for datum in cable["path"]:
        if instance_datum(built, datum) is None:
            return f"{datum} names no <instance>.<feature> datum of the assembly"
    if "wheel" not in cable:
        return None
    wheel = cable["wheel"]
    if wheel not in built.moving:
        return f"wheel {wheel} is {'a fixed joint' if wheel in built.joints else 'not a joint'}"
    if len(built.joints[wheel].get("range", [])) != 1:
        return (
            f"wheel {wheel} needs a one-ended range, its full turn from as built; "
            f"it has {built.joints[wheel].get('range', 'none')}"
        )
    turn = cable_turn(built, cable)
    if p.values.get(turn) == 0:
        return f"wheel {wheel}'s full turn {turn} is 0, so it closes nothing"
    first = instance_datum(built, cable["path"][0])
    if first is not None and first[0] == built.joints[wheel]["child"]:
        return (
            f"its path starts at {cable['path'][0]}, on the wheel; start it where the cable "
            "leaves the wheel, on an instance the wheel does not turn"
        )
    geared = {g[k] for g in built.gears.values() for k in ("driver", "driven")}
    for joint, param in cable["closes"].items():
        if joint not in built.moving:
            what = "a fixed joint" if joint in built.joints else "not a joint"
            return f"closes {joint}, which is {what}"
        if joint == wheel:
            return f"closes its own wheel {wheel}"
        if joint in geared:
            return f"closes {joint}, which a gear couples"
        if joint in closed_by:
            return f"closes {joint}, which cable {closed_by[joint]} closes too"
        if param not in p.values:
            return f"closes {joint} to {param}, which params.yaml does not define"
    return None


def _cables_on_axes(p: Project, built: Built) -> None:
    """[cable-on-axis] for each path datum of a cable that lies on the axis of a revolute joint the
    cable closes and turns with it: turning that joint leaves the cable's length unchanged."""
    from build123d import Location, Vector

    def placed(datum: str) -> Vector:
        inst, point = located(built, datum)
        return (built.assembly[inst][1] * Location(point)).position

    for name, cable in built.cables.items():
        for joint in cable.get("closes", {}):
            hinge = built.joints[joint]
            if joint_type(hinge).quantity != "angle":
                continue
            turned, grew = {hinge["child"]}, True  # the instances the joint turns
            while grew:
                below = {j["child"] for j in built.joints.values() if j["parent"] in turned}
                grew, turned = not below <= turned, turned | below
            a, b = (placed(d) for d in hinge["axis"])
            for datum in cable["path"]:
                if located(built, datum)[0] in turned:
                    off = (placed(datum) - a).cross((b - a).normalized()).length
                    if off <= p.length_tol:
                        p.warn(
                            "cable-on-axis",
                            f"cable {name}: {datum} lies on the axis of {joint}, which it closes, "
                            f"so turning {joint} leaves the cable's length unchanged; lay the path "
                            "through a datum off that axis, such as a guide's eye on a face",
                        )


def _cable_flaws(p: Project, built: Built) -> bool:
    """Add [model-cable] for each cable that cannot be laid or close its joints; True if any."""
    flawed, closed_by = False, {}
    for name, cable in built.cables.items():
        flaw = _cable_flaw(p, built, cable, closed_by)
        if flaw:
            p.error("model-cable", f"cable {name}: {flaw}")
            flawed = True
        for joint in cable.get("closes", {}):
            closed_by.setdefault(joint, name)
    return flawed


class Coupling(NamedTuple):
    """Two joints that move in proportion: driven at ratio times driver, in the project's units of
    each; law says how, as a finding words it."""

    kind: str  # gear or cable
    name: str
    driver: str
    driven: str
    ratio: float
    law: str


def cable_turn(built: Built, cable: dict) -> str:
    """The param of a wound cable's full turn: its wheel's one-ended range."""
    return built.joints[cable["wheel"]]["range"][0]


def couplings(p: Project, built: Built) -> list[Coupling]:
    """Each pair of joints moving in proportion: a gear's, and a cable's wheel with each joint it
    closes, at its closed value over the wheel's full turn."""
    found = [
        Coupling(
            "gear",
            name,
            g["driver"],
            g["driven"],
            ratio := p.values[g["ratio"]],
            f"moves {g['driven']} {ratio:g} times {g['driver']}",
        )
        for name, g in built.gears.items()
    ]
    for name, cable in built.cables.items():
        if "wheel" not in cable:
            continue
        wheel = cable["wheel"]
        turn = p.values[cable_turn(built, cable)]
        for joint, param in cable["closes"].items():
            closed = p.values[param]
            law = f"closes {joint} to {closed:g} as {wheel} turns to {turn:g}"
            found.append(Coupling("cable", name, wheel, joint, closed / turn, law))
    return found


def cable_length(built: Built, cable: dict) -> float:
    """The length of a cable's path through its datums, where the assembly places them."""
    from build123d import Location

    points = [
        (built.assembly[inst][1] * Location(point)).position
        for inst, point in (located(built, d) for d in cable["path"])
    ]
    return sum((b - a).length for a, b in zip(points, points[1:]))


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


def _datum_distance(c: dict, points: list) -> float:
    """The distance between a check's two datums, along its axis where it names one."""
    along = c.get("along")
    if along and along not in AXES:
        raise KeyError(f"axis {along}")
    return released.datum_distance(points[0], points[1], along or None)


def _datum_angle(p: Project, c: dict, points: list) -> float | None:
    """The angle in degrees at between[1] from the direction to between[0] to that to between[2];
    None, after a [check-config] finding, when there are not three datums or one coincides with
    the vertex, which leaves the angle undefined."""
    cid, names = c.get("id", "?"), c["between"]
    if len(points) != 3:
        p.error(
            "check-config", f"check {cid}: between names {len(points)} datums, not [a, vertex, b]"
        )
        return None
    # Zero-length within tolerance.length, not exactly: a direction that short has no angle the
    # check could confirm.
    angle = released.angle_at(points[0], points[1], points[2], p.length_tol)
    if angle is None:
        p.error(
            "check-config",
            f"check {cid}: {names[0]} or {names[2]} coincides with the vertex {names[1]}, "
            "so the angle is undefined",
        )
    return angle


def _joint_name(c: dict) -> str | None:
    """The joint a check names: a range check's joint, or the one a sweep is across."""
    return c.get("joint") or (c.get("sweep") or {}).get("joint")


def _given(built: Built, c: dict, *placed: Built) -> tuple[str, ...]:
    """The params the model gives check c: the range ends of a joint it names, and for each cable
    whose wheel the pose of an assembly placed for it moves, the wheel's turn and closed values."""
    given = list(built.joints.get(_joint_name(c) or "", {}).get("range", ()))
    moved = set().union(*(posed.moved for posed in placed))
    for cable in built.cables.values():
        if cable.get("wheel") in moved:
            given += (cable_turn(built, cable), *cable["closes"].values())
    return tuple(dict.fromkeys(given))


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


Evaluated = tuple[list[CheckResult], accounting.Reads]
"""What a check's evaluation hands back: its results, and its Reads, which a finding that stops
it leaves at what it had read so far."""


@dataclass
class _Reading:
    """What check c's evaluation has read so far: the assemblies it was placed or posed at, and
    for a mass check the parts it weighs (weighs) and those it weighs in several instances with no
    stated count (uncounted)."""

    p: Project
    built: Built
    c: dict
    placed: list[Built] = field(default_factory=list)
    weighs: tuple[str, ...] | None = None
    uncounted: tuple[str, ...] = ()

    def at(self, *placed: Built) -> None:
        """Record the assemblies the check was placed or posed at."""
        self.placed += placed

    @property
    def reads(self) -> accounting.Reads:
        """The check's Reads: what it has read so far, with what the model gives it there."""
        given = _given(self.built, self.c, *self.placed)
        return accounting.reads(self.p, self.c, given, self.weighs, self.uncounted)


def _evaluate(
    p: Project, built: Built, c: dict, evaluation: Callable[[_Reading], Iterable[CheckResult]]
) -> Evaluated:
    """Check c evaluated by its kind's evaluation, which records what it reads in a _Reading. A
    missing or unknown key or value that stops it is a [check-config] finding; it keeps the
    results a generator yielded before (an evaluation returning a list keeps none), and its Reads
    are what it had read so far."""
    reading, results = _Reading(p, built, c), []
    with _config_findings(p, c):
        for result in evaluation(reading):
            results.append(result)
    return results, reading.reads


@contextmanager
def _config_findings(p: Project, c: dict) -> Iterator[None]:
    """A missing or unknown key or value met evaluating check c, as a [check-config] finding."""
    try:
        yield
    except (KeyError, TypeError, ValueError) as exc:
        p.error("check-config", f"check {c.get('id', '?')}: missing or unknown {exc}")


def _range(
    p: Project, built: Built, c: dict, poser: Poser | None, reading: _Reading
) -> list[CheckResult]:
    """A range check's results, one per end, reading its joint's range ends and what the model
    gives each pose it reaches. With between, the model posed at that end of its joint's range,
    the angle there, or between two datums the distance, compared with the end's ledger value.
    Without, the model posed at the ledger value itself, so a loop that cannot close or a joint
    pushed past its own range there is a finding, and the range param for that end compared with
    it."""
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
            reading.at(placed)
            points = _datums(p, placed, c)
            if points is not None and between_two(c):
                measured, shown = _datum_distance(c, points), f" {' - '.join(c['between'])}"
            else:
                measured = None if points is None else _datum_angle(p, c, points)
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
            reading.at(reached[0])
            pose = reached[1]
            measured = p.values[param] * p.compared_size(quantity)
            shown = f"{kind.symbol} {name}'s range end ({param})"
        compared_in = compared_quantity(c) if "between" in c else quantity
        result = _compared(p, c, f"{cid}.{param}", ref, measured, shown, compared_in)
        result.pose = pose
        results.append(result)
    return results


def _volume(overlap) -> float:
    """The volume of an intersect() result: nothing, one shape, or a list of shapes."""
    if overlap is None:
        return 0.0
    if isinstance(overlap, list):  # a ShapeList, when the overlap is not one shape
        return sum(shape.volume for shape in overlap)
    return overlap.volume


def _weighed(p: Project, built: Built, c: dict) -> Counter | None:
    """How many instances of each part a mass check weighs: those it names in instances, else
    every instance of the assembly, narrowed by parts to those parts' instances; None, after a
    [check-config] finding, when it names an unknown instance or a part it weighs no instance of."""
    placed = _placed(p, built, c) if "instances" in c else built.assembly
    if placed is None:
        return None
    named = c.get("parts") or None
    tally = Counter(part for part, _ in placed.values() if named is None or part in named)
    missing = [name for name in named or [] if name not in tally]
    for name in missing:
        p.error(
            "check-config",
            f"check {c.get('id', '?')}: parts names {name}, but it weighs no instance of it",
        )
    return None if missing else tally


def _mass(p: Project, built: Built, c: dict, reading: _Reading) -> list[CheckResult]:
    """A mass check, reading the params of the parts it weighs, even where a finding then stops
    it, and the parts it weighs in several instances with no counts entry."""
    tally = _weighed(p, built, c)
    if tally is None:
        return []
    reading.weighs = tuple(tally)
    result = _weighed_mass(p, built, c, tally)
    if result is None:
        return []
    counts = c.get("counts", {})
    result.uncounted = {n: k for n, k in tally.items() if k > 1 and n not in counts}
    reading.uncounted = tuple(result.uncounted)
    return [result]


def _weighed_mass(p: Project, built: Built, c: dict, tally: Counter) -> CheckResult | None:
    """A mass check's result: each instance in tally weighed by its part's volume times the
    check's density, or without one by the mass model as the MJCF export weighs it, plus its add
    params. None after a [check-config] finding: a counts param other than its part's instances
    in tally, or a part the mass model leaves unweighed."""
    cid, names, counts = c.get("id", "?"), list(tally), c.get("counts", {})
    wrong = [(part, param) for part, param in counts.items() if p.values[param] != tally[part]]
    for part, param in wrong:
        p.error(
            "check-config",
            f"check {cid}: counts {part} as {param} ({p.values[param]:g}), but it weighs "
            f"{tally[part]} instances of it",
        )
    if wrong:
        return None
    if "density" in c:
        density = p.values[c["density"]]
        each = {n: built.parts[n].volume * density for n in names}
    else:
        unweighed = [n for n in names if n not in built.masses]
        if unweighed:
            p.error(
                "check-config",
                f"check {cid}: names no density, and the mass model in params.yaml "
                f"parts weighs no {', '.join(unweighed)}",
            )
            return None
        each = {n: built.masses[n].mass for n in names}
    measured = sum(each[n] * tally[n] for n in names) + sum(p.values[n] for n in c.get("add", []))
    return _compared(p, c, cid, f"{c['evidence']}.{c['key']}", measured)


def _interference(
    p: Project, built: Built, c: dict, placed: Built, poser: Poser | None, reading: _Reading
) -> list[CheckResult]:
    """An interference check, on the placed assembly or, with sweep, across the poses of its
    joint's range, reading that joint's range ends and what the model gives the poses it is
    evaluated at; no result after a finding saying why it cannot be swept."""
    reading.at(placed)  # read where a sweep stops; each swept pose moves what placed does
    swept = _sweep(p, built, c, poser) if "sweep" in c else (None, [(placed, None)])
    if swept is None:
        return []
    sweep, poses = swept
    reading.at(*(assembly for assembly, _ in poses))
    return [_worst_overlap(p, c, poses, sweep)]


def _worst_overlap(p: Project, c: dict, poses: list, sweep: dict | None) -> CheckResult:
    """An interference check's result: the worst overlap among its pairs across poses, each a
    (placed assembly, its pose), naming the pose it occurred at where sweep says how they were
    swept."""
    cid, limit = c.get("id", "?"), overlap_limit(p, c)
    pairs = [tuple(pair) for pair in c.get("pairs", [])]
    pair_set = "listed" if pairs else "all"
    if not pairs:
        names = sorted(poses[0][0].assembly)
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


def _stroke(
    p: Project,
    built: Built,
    c: dict,
    reached: tuple[Built, dict | None],
    poser: Poser | None,
    reading: _Reading,
) -> list[CheckResult]:
    """A stroke check: how much its cable shortens from as built, or from its from pose, to the
    pose the check names (reached), or without one to its wheel's full turn, compared with the
    ledger value, or with its claim; reading what the model gives each pose."""
    placed, pose = reached
    reading.at(placed)
    cid, name = c.get("id", "?"), c["cable"]
    cable = built.cables.get(name)
    if cable is None:
        if not built.dropped:  # else that finding says the cables were dropped
            p.error("check-config", f"check {cid}: {name} is not a cable")
        return []
    start, start_pose = built, None
    if c.get("from"):
        posed = _placed_for(p, built, c, poser, at="from")
        if posed is None:
            return []
        start, start_pose = posed
        reading.at(start)
    if pose is None:
        if "wheel" not in cable:
            p.error(
                "check-config",
                f"check {cid}: cable {name} has no wheel, so name the pose its stroke is taken at",
            )
            return []
        if poser is None:
            return []
        turn = cable_turn(built, cable)
        posed = poser(c, {cable["wheel"]: (p.values[turn], turn)})
        if posed is None:
            return []
        placed, pose = posed
        reading.at(placed)
    shortening = cable_length(start, cable) - cable_length(placed, cable)
    shown = f" shortening of {name}"
    if "claim" in c:
        result = _claimed(p, c, cid, shortening, shown)
    else:
        result = _compared(p, c, cid, f"{c['evidence']}.{c['key']}", shortening, shown)
    result.pose, result.from_pose = pose, start_pose
    return [result]


def _claimed(p: Project, c: dict, rid: str, change: float, shown: str = "") -> CheckResult:
    """A claim check's result: it passes where change, signed as its claim says (CLAIMS), exceeds
    tolerance.length, the model's resolution, so a change within it or the other way fails."""
    claim, tol = c["claim"], p.length_tol
    return CheckResult(
        rid,
        c["kind"],
        CLAIMS[claim] * change > tol,
        f"{claim} by more than {tol:g} ({c['evidence']})",
        f"{change:.4g}{shown}",
        c.get("interpretation", ""),
    )


def _bbox(p: Project, c: dict, placed: Built, reading: _Reading) -> Iterator[CheckResult]:
    """A bbox check, one result per axis it names: its envelope's size along that axis, each
    yielded as it is compared, so a finding that stops it at an axis keeps the earlier axes'."""
    cid = c.get("id", "?")
    reading.at(placed)
    shape = _envelope(p, placed, c)
    if shape is None:
        return
    s = shape.bounding_box().size
    size = (s.X, s.Y, s.Z)
    for key, axis in c["axes"].items():
        ref, measured = f"{c['evidence']}.{key}", size[AXES[axis]]
        yield _compared(p, c, f"{cid}.{key}", ref, measured, f" along {axis}")


def _distance(p: Project, c: dict, placed: Built, reading: _Reading) -> list[CheckResult]:
    """A distance check: the distance between its two datums."""
    reading.at(placed)
    points = _datums(p, placed, c)
    if points is None:
        return []
    measured = _datum_distance(c, points)
    ref, between = f"{c['evidence']}.{c['key']}", " - ".join(c["between"])
    return [_compared(p, c, c.get("id", "?"), ref, measured, f" {between}")]


def _angle(p: Project, c: dict, placed: Built, reading: _Reading) -> list[CheckResult]:
    """An angle check: the angle at its vertex datum between the other two."""
    reading.at(placed)
    points = _datums(p, placed, c)
    measured = None if points is None else _datum_angle(p, c, points)
    if measured is None:
        return []
    ref, (a, vertex, b) = f"{c['evidence']}.{c['key']}", c["between"]
    shown = f"° at {vertex} between {a} and {b}"
    return [_compared(p, c, c.get("id", "?"), ref, measured, shown)]


def _diameter(p: Project, built: Built, c: dict, reading: _Reading) -> list[CheckResult]:
    """A diameter check: the diameter of the cylindrical face its datum at lies on, in its part's
    frame. No result, after a [check-config] finding, where at is no part's datum or lies on no
    cylindrical face, or on the edge of two of different diameters."""
    reading.at(built)
    cid, at = c.get("id", "?"), str(c["at"])
    part = _owner(built, at)
    if part is None or at not in built.datums:
        p.error("check-config", f"check {cid}: {at} is not a datum of a part")
        return []
    found = released.diameter_at(built.parts[part], built.datums[at], p.length_tol)
    if isinstance(found, str):
        p.error(
            "check-config",
            f"check {cid}: {at} lies on {found} of part {part}; place it on the face whose "
            "diameter the check compares",
        )
        return []
    ref = f"{c['evidence']}.{c['key']}"
    return [_compared(p, c, cid, ref, found, f" at {at}")]


def _shape(p: Project, built: Built, c: dict, reading: _Reading) -> list[CheckResult]:
    """A shape check: its part carried onto its released body by the rigid motion that best fits
    its datum pairs, then the largest distance between their surfaces, compared with its
    tolerance; failed, without that distance, where the pairs fit no closer than
    tolerance.length. No result, after a [check-config] finding, where its body or a datum is
    unknown or its pairs are fewer than three off one line."""
    reading.at(built)
    cid, name, part = c.get("id", "?"), str(c["body"]), built.parts[c["part"]]
    body = p.bodies.get(name)
    if body is None:
        p.error("check-config", f"check {cid}: {name} is not a body of a geometry source")
        return []
    pairs, ours, theirs = c.get("pairs") or [], [], []
    for pair in pairs:
        if len(pair) != 2:
            p.error(
                "check-config",
                f"check {cid}: pair {pair} is not [<part>.<feature>, <body>.<feature>]",
            )
            return []
        if _owner(built, pair[0]) != c["part"] or pair[0] not in built.datums:
            p.error("check-config", f"check {cid}: {pair[0]} is not a datum of part {c['part']}")
            return []
        named = p.released_datum(pair[1])
        if named is None or named[0] != name:
            p.error(
                "check-config", f"check {cid}: {pair[1]} is not a datum declared on body {name}"
            )
            return []
        ours.append(built.datums[pair[0]])
        theirs.append(named[1])
    if len(pairs) < 3 or released.collinear(theirs, p.length_tol):
        p.error(
            "check-config",
            f"check {cid}: aligns by {len(pairs)} datum pair{'s' * (len(pairs) != 1)}; name three "
            "or more whose datums on the body are not on one line",
        )
        return []
    where, residual, worst = released.fit(ours, theirs)
    fitted = {"residual": printed(residual)[0]}
    if residual > p.length_tol:
        return [
            CheckResult(
                cid,
                "shape",
                False,
                f"datum pairs fit within {p.length_tol:g} (tolerance.length)",
                f"datum pairs fit within {residual:.4g}, {pairs[worst][0]} to {pairs[worst][1]} "
                "the farthest apart",
                c.get("interpretation", ""),
                shape=fitted,
            )
        ]
    distance, at = released.surface_distance(part.moved(where), body)
    tolerance = check_tolerance(p, c)
    assert tolerance is not None  # a shape check's kind has a tolerance
    shown = ", ".join(f"{v:.4g}" for v in at)
    return [
        CheckResult(
            cid,
            "shape",
            distance <= tolerance[1],
            f"surfaces within {tolerance[1]:g} of body {name}",
            f"{distance:.4g} largest surface distance, at ({shown}) on body {name}",
            c.get("interpretation", ""),
            shape=fitted | {"distance": printed(distance)[0], "worst_point": list(printed(*at))},
        )
    ]


def _unknown_kind(p: Project, c: dict, reading: _Reading) -> list[CheckResult]:
    """A check of a kind with no evaluation: a [check-kind] finding, reading only what it names
    and the range ends of a joint it names."""
    p.error("check-kind", f"check {c.get('id', '?')}: unknown kind {c.get('kind')!r}")
    return []


def _placed_for(
    p: Project, built: Built, c: dict, poser: Poser | None, at: str = "pose"
) -> tuple[Built, dict | None] | None:
    """The assembly check c is evaluated on, with its pose: as built, or placed at the pose its
    key at names; None, after a finding, when it names a pose that cannot be placed."""
    if not c.get(at):
        return built, None
    if poser is None:
        if not built.dropped:  # else that finding says the joints were dropped
            p.error(
                "check-config",
                f"check {c.get('id', '?')}: its {at} names {', '.join(c[at])}, but "
                "model.build returns no joints",
            )
        return None
    return poser(c, at=at)


def run_checks(
    p: Project, built: Built, poser: Poser | None = None
) -> tuple[list[CheckResult], list[accounting.Reads]]:
    """Evaluate every check: on the assembly as built, or, for a check that names a pose, on the
    assembly poser places at it, a check that cannot be posed adding a finding instead. With each
    check's Reads: what its evaluation read, or as estimated from the check alone where it read
    nothing."""
    results, reads = [], accounting.estimated(p)
    for i, c in enumerate(p.checks):
        kind = c.get("kind")
        if any(p.cites_repeated(ref) for ref in cited_refs(p, c)):
            continue  # it compares with neither item; check_citations said so before the build
        if claim_config(p, c):
            continue  # check_claims said why before the build
        reached = _placed_for(p, built, c, poser)
        if reached is None:
            continue
        placed, pose = reached
        evaluation: Callable[[_Reading], Iterable[CheckResult]]
        if kind == "bbox":
            evaluation = partial(_bbox, p, c, placed)
        elif kind == "distance":
            evaluation = partial(_distance, p, c, placed)
        elif kind == "angle":
            evaluation = partial(_angle, p, c, placed)
        elif kind == "diameter":
            evaluation = partial(_diameter, p, built, c)
        elif kind == "mass":
            evaluation = partial(_mass, p, built, c)
        elif kind == "stroke":
            evaluation = partial(_stroke, p, built, c, reached, poser)
        elif kind == "range":
            evaluation = partial(_range, p, built, c, poser)
        elif kind == "shape":
            evaluation = partial(_shape, p, built, c)
        elif kind == "interference":
            evaluation = partial(_interference, p, built, c, placed, poser)
        else:
            evaluation = partial(_unknown_kind, p, c)
        found, read = _evaluate(p, built, c, evaluation)
        results += found
        reads[i] = read
        basis, params = accounting.rests_on(p, read)
        for r in found:
            r.rests_on, r.rests_on_params = basis, params
            r.pose = r.pose or pose
    for r in results:
        if not r.ok:
            moved = "" if r.from_pose is None else f" from {pose_text(r.from_pose)}"
            moved += f" to {pose_text(r.pose)}" if moved and r.pose else ""
            p.error("check-failed", f"{r.id}: expected {r.expected}, measured {r.measured}{moved}")
    return results, reads
