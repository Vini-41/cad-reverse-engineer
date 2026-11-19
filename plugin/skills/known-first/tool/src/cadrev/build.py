"""Run model.py and hold what it returns to the model contract: parts, datums, the assembly, and
for a mechanism its joints, loops, gears, cables and tendons."""

from __future__ import annotations

import importlib.util
import math
import re
import sys
import traceback
from dataclasses import dataclass, field
from pathlib import Path
from typing import NamedTuple

from . import Fault, ledger, released, schema, units
from .project import Project, expr_names


class _ParamError(AttributeError):
    """A param model.py reads that has no value."""


class Params:
    """Read-only parameter access that records which parameters the model used."""

    def __init__(self, values: dict[str, float], declared):
        self._values, self._declared, self.used = values, set(declared), set()

    def __setattr__(self, name: str, value) -> None:
        if not name.startswith("_") and name != "used":
            raise AttributeError(f"param {name!r} is set in params.yaml, not in model.py")
        super().__setattr__(name, value)

    def __getattr__(self, name: str) -> float:
        if name.startswith("_"):
            raise AttributeError(name)
        if name not in self._values:
            why = "has no value" if name in self._declared else "is not in params.yaml"
            raise _ParamError(f"param {name!r} {why}")
        self.used.add(name)
        return self._values[name]


class JointType(NamedTuple):
    mjcf: str | None  # its MJCF joint type; None for a fixed joint, one body with its parent
    quantity: str | None  # what its value, range and poses are in
    moves: str  # the verb a finding says it moves by
    symbol: str = ""  # printed after a compared value of it


JOINT_TYPES = {
    "revolute": JointType("hinge", "angle", "turns", "°"),
    "slide": JointType("slide", "length", "slides"),
    "fixed": JointType(None, None, "stays"),
}
DRIVES = ("actuated", "passive")
# The physics values a revolute joint, a slide or a tendon may name, each a param: the MJCF
# attribute it is written to, and its quantity.
PHYSICS = {
    "revolute": {
        "damping": ("damping", "torsional damping"),
        "stiffness": ("stiffness", "torsional stiffness"),
        "friction": ("frictionloss", "torque"),
        "spring_rest": ("springref", "angle"),
    },
    "slide": {
        "damping": ("damping", "linear damping"),
        "stiffness": ("stiffness", "linear stiffness"),
        "friction": ("frictionloss", "force"),
        "spring_rest": ("springref", "length"),
    },
    "tendon": {
        "stiffness": ("stiffness", "linear stiffness"),
        "damping": ("damping", "linear damping"),
    },
}
# What a gear is stated by: the quantity of its param, and whether it couples a revolute joint
# with a slide (a lead) or two joints of one type (a ratio).
GEAR_BY = {"ratio": ("fraction", False), "lead": ("length", True)}
AS_BUILT = "as built"  # names the end of a one-ended range that no param states: a move of 0
_MOTION = {
    "joint": schema.JOINT,
    "gear": schema.GEAR,
    "cable": schema.CABLE,
    "tendon": schema.TENDON,
}


@dataclass
class Mass:
    """A part's mass, the param it is weighed by (`by` is mass or density), and its centre of mass
    and inertia about it in the part's frame (ixx iyy izz ixy ixz iyz), as the MJCF prints them."""

    mass: float
    by: str
    param: str
    center: tuple[float, ...]
    inertia: tuple[float, ...]


class Threaded(NamedTuple):
    """A plain cylinder of a part made for a thread: the datum it is declared at, the thread
    param, whether it carries the thread or clears its screw, whether it is a hole or a shank,
    and the cylinder's diameter, a point on its axis and the axis's direction, in the part's
    frame."""

    at: str
    part: str
    param: str
    fit: str  # threaded or clearance
    hole: bool  # a hole, its wall facing its axis; else a shank
    diameter: float
    origin: tuple[float, float, float]
    direction: tuple[float, float, float]


@dataclass
class Model:
    parts: dict
    datums: dict[str, tuple[float, float, float]]
    assembly: dict  # instance -> (part name, Location)
    used: set[str]  # the params model.py read
    joints: dict = field(default_factory=dict)
    loops: dict = field(default_factory=dict)
    gears: dict = field(default_factory=dict)
    cables: dict = field(default_factory=dict)
    tendons: dict = field(default_factory=dict)
    masses: dict[str, Mass] = field(default_factory=dict)
    # Each hole or shank declared for a thread, once held to the thread's sizes.
    threads: list[Threaded] = field(default_factory=list)
    # True when a finding dropped the joints, loops, gears, cables and tendons build() returned.
    dropped: bool = False
    # The joints the pose this assembly is placed at moves, itself or through a gear, cable or
    # loop.
    moved: frozenset[str] = frozenset()

    @property
    def moving(self) -> dict:
        """The joints that move their child: all but the fixed ones."""
        return {n: j for n, j in self.joints.items() if j["type"] != "fixed"}

    def quantity(self, joint: str) -> str:
        """What a moving joint's value is in: an angle or a length."""
        return str(JOINT_TYPES[self.joints[joint]["type"]].quantity)

    def instance_datum(self, name: str) -> tuple[str, tuple[float, float, float]]:
        """The instance <instance>.<feature> names, and that datum's point in its part's frame."""
        inst = prefix(name, self.assembly)
        datum = f"{self.assembly[inst][0]}.{name[len(inst) + 1 :]}" if inst else None
        if datum not in self.datums:
            raise Fault(f"{name} names no <instance>.<feature> datum of the assembly")
        return str(inst), self.datums[datum]

    def placed(self, name: str):
        """Where the assembly places the datum <instance>.<feature>, as a build123d Vector."""
        from build123d import Location

        inst, point = self.instance_datum(name)
        return (self.assembly[inst][1] * Location(point)).position

    def path_length(self, path: list[str]) -> float:
        """The length of a cable's path through its datums, where the assembly places them."""
        points = [self.placed(d) for d in path]
        return sum((b - a).length for a, b in zip(points, points[1:]))


def unmoving(model: Model, joint: str) -> str:
    """What a name is, where a joint that moves was expected."""
    return "a fixed joint" if joint in model.joints else "not a joint"


def prefix(name: str, owners) -> str | None:
    """The longest of owners that name starts with as <owner>.<feature>, or None."""
    return max((o for o in owners if str(name).startswith(f"{o}.")), key=len, default=None)


def printed(*values: float) -> tuple[float, ...]:
    """values rounded to the 12 digits the MJCF prints, so the export and report.json agree."""
    return tuple(float(f"{v:.12g}") for v in values)


def range_ends(p: Project, joint: dict) -> list[tuple[str, float]]:
    """A joint's range as its two ends, low first, each (the param it is from, its value): a range
    of one param runs from the assembly as built to that param, either way."""
    ends: list[tuple[str, float]] = [(str(name), p.values[name]) for name in joint["range"]]
    return ends if len(ends) == 2 else sorted([(AS_BUILT, 0.0), *ends], key=lambda end: end[1])


def gear_by(gear: dict) -> tuple[str, str]:
    """What a gear is stated by: (ratio or lead, its param)."""
    key = next(k for k in GEAR_BY if k in gear)
    return key, gear[key]


def physics_of(kind: str, entry: dict) -> dict[str, tuple[str, str]]:
    """The physics values a joint or tendon may name, from PHYSICS; none for a fixed joint."""
    return PHYSICS.get(entry["type"] if kind == "joint" else kind, {})


def physics_slots(model: Model) -> dict[str, list[tuple[str, str, str]]]:
    """Each param a joint or tendon names as a physics value, with each place it applies: what a
    finding calls the place, the MJCF attribute, and its quantity."""
    slots: dict[str, list] = {}
    for kind, entries in (("joint", model.joints), ("tendon", model.tendons)):
        for name, entry in entries.items():
            for key, (attr, quantity) in physics_of(kind, entry).items():
                if key in entry:
                    slots.setdefault(entry[key], []).append(
                        (f"{kind} {name}'s {key}", attr, quantity)
                    )
    return slots


class Coupling(NamedTuple):
    """Two joints that move in proportion: driven at ratio times driver, in the project's units of
    each; law says how, as a finding words it."""

    kind: str  # gear or cable
    name: str
    driver: str
    driven: str
    ratio: float
    law: str


def couplings(p: Project, model: Model) -> list[Coupling]:
    """Each pair of joints moving in proportion: a gear's, at its ratio or at its lead per full
    turn of its revolute joint; and a cable's wheel with each joint it closes, at that joint's
    closed value over the wheel's full turn."""
    found = []
    for name, gear in model.gears.items():
        key, param = gear_by(gear)
        driver, driven, value = gear["driver"], gear["driven"], p.values[param]
        if key == "ratio":
            law = f"moves {driven} {value:g} times {driver}"
            found.append(Coupling("gear", name, driver, driven, value, law))
            continue
        turn = 2 * math.pi / units.size("angle", p.units)
        turns = model.quantity(driver) == "angle"
        revolute, slide = (driver, driven) if turns else (driven, driver)
        law = f"moves {slide} {value:g} per full turn of {revolute}"
        ratio = value / turn if turns else turn / value
        found.append(Coupling("gear", name, driver, driven, ratio, law))
    for name, cable in model.cables.items():
        if "wheel" in cable:
            wheel = cable["wheel"]
            turn = p.values[model.joints[wheel]["range"][0]]
            for joint, param in cable["closes"].items():
                closed = p.values[param]
                law = f"closes {joint} to {closed:g} as {wheel} turns to {turn:g}"
                found.append(Coupling("cable", name, wheel, joint, closed / turn, law))
    return found


def _contract(result) -> None:
    """A Fault saying why build()'s return breaks the model contract, if it does."""
    from build123d import Location
    from build123d.topology import Shape

    if not isinstance(result, dict):
        raise Fault(f"must return a mapping of parts, datums and assembly, not {_type(result)}")
    keys = ("parts", "datums", "assembly", "threads", "loops", *(f"{kind}s" for kind in _MOTION))
    for key in keys:
        if not isinstance(result.get(key, {}), dict):
            raise Fault(f"{key} must be a mapping of names, not {_type(result[key])}")
        for name in result.get(key, {}):
            if not isinstance(name, str):
                raise Fault(f"{key}: the name {name!r} must be text")
    for name, part in result.get("parts", {}).items():
        if not isinstance(part, Shape):
            raise Fault(f"part {name} must be a build123d shape, not {_type(part)}")
        if not re.fullmatch(r"[\w.-]+", str(name)):  # it names build/parts/<name>.step
            raise Fault(f"part name {name!r} must be letters, digits, '_', '.' or '-'")
    for name, point in result.get("datums", {}).items():
        if not (_listed(point, 3) and all(isinstance(c, (int, float)) for c in point)):
            raise Fault(f"datum {name} must be an (x, y, z) tuple of numbers, not {point!r}")
    for name, param in result.get("threads", {}).items():
        if not isinstance(param, str):
            raise Fault(f"thread at {name} must name a thread param, not {param!r}")
    for inst, entry in result.get("assembly", {}).items():
        if not (_listed(entry, 2) and isinstance(entry[0], str) and isinstance(entry[1], Location)):
            raise Fault(f"assembly instance {inst} must be a (part name, Location) pair")
    for name, pair in result.get("loops", {}).items():
        if not (_listed(pair, 2) and all(isinstance(d, str) for d in pair)):
            raise Fault(f"loop {name} must be two <instance>.<feature> datums, not {pair!r}")
    for kind, spec in _MOTION.items():
        entries = result.get(f"{kind}s", {})
        for name, entry in entries.items():
            problems: list[str] = []
            # As the schema reads it: a key set to None counts as absent.
            entries[name] = entry = schema.conform(entry, spec, f"{kind} {name}", problems)
            if not problems and (problem := _unfit(kind, entry)):
                problems.append(f"{kind} {name}: {problem}")
            if problems:
                raise Fault(problems[0].partition(";")[0])


def _type(value) -> str:
    return type(value).__name__


def _listed(value, count: int) -> bool:
    return isinstance(value, (list, tuple)) and len(value) == count


def _unfit(kind: str, entry: dict) -> str | None:
    """Why a joint, gear, cable or tendon of the right shape still states no motion."""
    if kind == "joint":
        if entry.get("type") not in JOINT_TYPES:
            return f"type must be one of {', '.join(JOINT_TYPES)}, not {entry.get('type')!r}"
        if "parent" not in entry or "child" not in entry:
            return "parent and child each name an assembly instance"
        if entry["type"] == "fixed":
            return None  # what else it takes is [model-joint]'s to say
        if len(entry.get("axis", ())) != 2:
            return f"axis must be two datums of its child, not {entry.get('axis')!r}"
        if "range" in entry and len(entry["range"]) not in (1, 2):
            return f"range must be one or two param names, not {entry['range']!r}"
        if entry.get("drive") not in DRIVES:
            return f"drive must be actuated or passive, not {entry.get('drive')!r}"
    elif kind == "gear":
        if len(GEAR_BY.keys() & entry.keys()) != 1 or not {"driver", "driven"} <= entry.keys():
            return "names a driver, a driven and one of ratio or lead"
    elif len(entry.get("path", ())) < 2:
        return f"path must be two or more datums, not {entry.get('path')!r}"
    elif kind == "cable" and ("wheel" in entry) != ("closes" in entry):
        return "wheel and closes go together"
    return None


def _failure(exc: BaseException, model: Path) -> str:
    """The exception, with the model.py line it was raised from unless it names a param."""
    if isinstance(exc, _ParamError):
        return f"AttributeError: {exc}"
    message = f"{type(exc).__name__}: {exc}" if str(exc) else type(exc).__name__
    frames = [f for f in traceback.extract_tb(exc.__traceback__) if Path(f.filename) == model]
    return (
        f"{message} (model.py line {frames[-1].lineno}: {frames[-1].line})" if frames else message
    )


def build(p: Project) -> Model | None:
    """The model model.py builds from the resolved params, held to the contract; None after a
    [model-build] or [model-return] finding. A finding on its motion keeps the build and drops
    the joints, loops, gears, cables and tendons."""
    path = p.root / "model.py"
    spec = importlib.util.spec_from_file_location("cadrev_model", path)
    assert spec is not None and spec.loader is not None  # a .py path always gets a source loader
    module = importlib.util.module_from_spec(spec)
    params = Params(p.values, p.params)
    writes_bytecode, sys.dont_write_bytecode = sys.dont_write_bytecode, True  # no __pycache__/
    try:
        spec.loader.exec_module(module)
        result = module.build(params)
    except (Exception, SystemExit) as exc:  # noqa: BLE001 - a broken model is a finding, not a crash
        p.error("model-build", f"model.build failed: {_failure(exc, path)}")
        return None
    finally:
        sys.dont_write_bytecode = writes_bytecode
    try:
        _contract(result)
    except Fault as fault:
        p.error("model-return", f"model.build {fault.message}")
        return None
    model = Model(
        parts=result.get("parts", {}),
        datums={
            k: (float(x), float(y), float(z)) for k, (x, y, z) in result.get("datums", {}).items()
        },
        assembly=result.get("assembly", {}),
        used=params.used,
        **{
            f"{kind}s": result.get(f"{kind}s", {})
            for kind in ("joint", "loop", "gear", "cable", "tendon")
        },
    )
    declared = result.get("threads", {})
    _hold_units(p, model, set(declared.values()))
    for name, part in model.parts.items():
        solids = len(part.solids())
        if not part.is_valid:
            p.error("part-invalid", f"part {name}: solid is not valid")
        elif solids == 1 and part.volume <= p.length_tol**3:
            p.error("part-invalid", f"part {name}: has no volume; build it as a solid")
        elif solids != 1:
            p.error(
                "part-invalid",
                f"part {name}: is {solids} solids, not one; fuse its bodies, or make each its own "
                "part placed in the assembly",
            )
    for name, point in model.datums.items():
        part = prefix(name, model.parts)
        if part is not None:
            gap = released.off_solid(model.parts[part], point, p.length_tol)
            if gap is not None:
                p.error("datum-off-solid", f"datum {name} of part {part}: {released.off(gap)}")
    faces: dict[tuple, str] = {}  # each part's cylindrical face declared for a thread: its datum
    for at, param in declared.items():
        with p.filing("model-thread", f"thread at {at}: "):
            model.threads.append(_threaded(p, model, at, param, faces))
    for inst, (part, _) in list(model.assembly.items()):
        if part not in model.parts:
            p.error("assembly-part", f"assembly instance {inst}: unknown part {part!r}")
            del model.assembly[inst]
    if _motion_faults(p, model):
        model.joints, model.loops, model.gears, model.cables, model.tendons = {}, {}, {}, {}, {}
        model.dropped = True
    _cables_on_axes(p, model)
    model.masses = _mass_model(p, model)
    return model


def _threaded(p: Project, model: Model, at: str, param: str, faces: dict[tuple, str]) -> Threaded:
    """The cylinder a thread is declared on, held to the thread's sizes: it carries the thread
    from its minor diameter to its major, or clears its screw from there to the loosest
    clearance hole its table gives, as a released body's hole may be any of them. A hole or
    shank is declared once, at one datum, so a count of them counts each once."""
    part = prefix(at, model.parts)
    if part is None or at not in model.datums:
        raise Fault("is not a <part>.<feature> datum")
    size = p.thread_params.get(param)
    if size is None:
        if param in p.values or param not in p.params:
            raise Fault(f"{param} is not a thread param; give it thread: in params.yaml")
        raise Fault()  # the param's own finding says why it has no value
    tol, thread = p.length_tol, size.thread
    loosest = None if thread.loosest is None else thread.loosest * size.per_mm
    widest = float(size) if loosest is None else loosest
    # A datum on the axis of a hole in a boss lies on the boss's axis too: the hole is the one
    # of them the thread fits.
    diameter, origin, direction, face = released.cylinder_at(
        model.parts[part],
        model.datums[at],
        tol,
        at,
        or_axis=True,
        fits=lambda found: size.minor - tol <= found <= widest + tol,
    )
    # By part too: two parts may be built as one shape.
    if faces.setdefault((part, id(face)), at) != at:
        raise Fault(f"lies on the hole or shank {faces[part, id(face)]} already declares")
    if size.minor - tol <= diameter <= size + tol:
        fit = "threaded"
    elif loosest is not None and size < diameter <= loosest + tol:
        fit = "clearance"
    else:
        hole = "" if loosest is None else f" nor a clearance hole for it (up to Ø{loosest:.4g})"
        raise Fault(
            f"its cylinder is Ø{diameter:.4g}, {'neither' if hole else 'not'} {thread.name}'s "
            f"thread (Ø{size.minor:.4g} to Ø{float(size):g}; its tap drill is Ø{size.tap:.4g})"
            f"{hole}"
        )
    return Threaded(
        at, part, param, fit, released.is_hole(face), printed(diameter)[0], origin, direction
    )


def _hold_units(p: Project, model: Model, threaded: set[str]) -> None:
    """Each param the model reads or exports is printed in a unit of the quantity it is used as,
    a physics value goes nowhere else, and each param is read by something."""
    for name in sorted(model.used):
        p.hold_param(name, ("length", "angle", "count"), "in model.py")
    ranges = {n for joint in model.joints.values() for n in joint.get("range", [])}
    for name, joint in model.moving.items():
        for param in joint.get("range", []):
            p.hold_param(param, (model.quantity(name),), f"in a {joint['type']} joint's range")
    coupled = set()
    for name, gear in model.gears.items():
        key, param = gear_by(gear)
        coupled.add(param)
        p.hold_param(param, (GEAR_BY[key][0],), f"as gear {name}'s {key}")
        for count in _worked_from(p, param) if key == "ratio" else []:
            # A ratio is worked out from counts, or from lengths as a belt's pulley diameters are.
            unit, ref = p.printed_as(count)
            if not (ref and p.prints_length(ref)):
                counted = unit is None or units.quantity(unit) == "count"
                expected = ("count",) if counted else ("count", "length")
                p.hold_param(count, expected, f"in gear {name}'s ratio")
    for name, cable in model.cables.items():
        for joint, param in cable.get("closes", {}).items():
            coupled.add(param)
            if joint in model.moving:
                p.hold_param(param, (model.quantity(joint),), f"as cable {name}'s closed {joint}")
    slots = physics_slots(model)
    for name, places in sorted(slots.items()):
        for place, _, quantity in places:
            if quantity is not None:
                p.hold_param(name, (quantity,), f"as {place}")
        if name in p.params and name not in p.physics:
            p.error(
                "param-physics",
                f"param {name}: {places[0][0]} is a physics value, so mark the param physics: true",
            )
    named = {n for c in p.checks for n in ledger.named_by_checks(p, c)}
    fit = {p.meta.get("clearance")} - {None}  # the loosest fit
    for name in sorted(p.physics & (model.used | named | ranges | coupled | fit)):
        p.error(
            "param-physics",
            f"param {name}: is marked physics: true, but the model's geometry, a joint range, a "
            "check or project.yaml's clearance reads it; a physics value only goes to a joint or "
            "tendon",
        )
    # A screw's length is what is bought, whether or not the model reads it.
    exported = ranges | coupled | slots.keys() | set(ledger.mass_params(p)) | threaded
    exported |= set(p.screws.values()) | fit
    derived = {n for spec in p.params.values() for n in expr_names(str(spec.get("expr") or ""))}
    p.resolution = ledger.resolution(p) - model.used - derived - exported
    for name in sorted(p.values.keys() - model.used - derived - named - exported):
        p.warn("param-unused", f"param {name} is defined but the model never reads it")


def _worked_from(p: Project, name: str, through: tuple[str, ...] = ()) -> list[str]:
    """The params a derived param's value is worked out from, through every derived param its
    expr reads: those with a basis of their own."""
    spec = p.params.get(name) or {}
    if spec.get("basis") != "derived" or name in through:
        return []
    out = []
    for n in sorted(expr_names(str(spec.get("expr", ""))) & p.params.keys()):
        derived = (p.params[n] or {}).get("basis") == "derived"
        out += _worked_from(p, n, (*through, name)) if derived else [n]
    return list(dict.fromkeys(out))


def _motion_faults(p: Project, model: Model) -> bool:
    """File [model-joint], [model-loop], [model-gear], [model-cable] and [model-return] for each
    joint, loop, gear, cable and tendon the assembly cannot hold; whether there is any."""
    before = len(p.findings)
    moved_by: dict[str, str] = {}  # child instance -> the joint moving it
    for name, joint in model.joints.items():
        with p.filing("model-joint", f"joint {name}: "):
            _joint_fault(p, model, joint, moved_by)
        if (
            joint["child"] not in moved_by
            and {joint["parent"], joint["child"]} <= model.assembly.keys()
        ):
            moved_by[joint["child"]] = name
    ringed: set[str] = set()
    for start in moved_by:
        ring, inst = [moved_by[start]], model.joints[moved_by[start]]["parent"]
        while inst in moved_by and inst != start and len(ring) <= len(moved_by):
            ring.append(moved_by[inst])
            inst = model.joints[moved_by[inst]]["parent"]
        if inst == start and not ringed & set(ring):
            ringed |= set(ring)
            p.error(
                "model-joint",
                f"joint {ring[0]}: {start} moves itself through {', '.join(ring)}; close a ring of "
                "joints with a loop instead",
            )
    for name, pair in model.loops.items():
        with p.filing("model-loop", f"loop {name}: "):
            for datum in pair:
                model.instance_datum(datum)
    for name, gear in model.gears.items():
        with p.filing("model-gear", f"gear {name}: "):
            _gear_fault(p, model, gear)
    closed_by: dict[str, str] = {}
    for name, cable in model.cables.items():
        with p.filing("model-cable", f"cable {name}: "):
            _cable_fault(p, model, cable, closed_by)
        for joint in cable.get("closes", {}):
            closed_by.setdefault(joint, name)
    with p.filing("model-return", "model.build "):
        for name, tendon in model.tendons.items():
            for datum in tendon["path"]:
                try:
                    model.instance_datum(datum)
                except Fault as fault:
                    raise Fault(f"tendon {name}: {fault.message}") from None
        for param, places in physics_slots(model).items():
            if param not in p.values:
                raise Fault(f"{places[0][0]} names {param}, which params.yaml does not define")
    return len(p.findings) > before


def _joint_fault(p: Project, model: Model, joint: dict, moved_by: dict) -> None:
    for key in ("parent", "child"):
        if joint[key] not in model.assembly:
            raise Fault(f"{key} {joint[key]} is not an instance of the assembly")
    if joint["child"] in moved_by:
        raise Fault(f"{joint['child']} is already the child of joint {moved_by[joint['child']]}")
    if joint["type"] == "fixed":
        if extra := [key for key in joint if key not in ("type", "parent", "child")]:
            raise Fault(
                f"a fixed joint moves {joint['child']} with {joint['parent']}, so it takes no "
                f"{', '.join(extra)}; make it revolute or slide if it moves"
            )
        return
    if "spring_rest" in joint and "stiffness" not in joint:
        raise Fault("spring_rest names no spring without a stiffness")
    points = []
    for datum in joint["axis"]:
        if prefix(datum, model.assembly) != joint["child"]:
            raise Fault(f"axis {datum} is not a datum of its child {joint['child']}")
        points.append(model.instance_datum(datum)[1])
    if math.dist(*points) <= p.length_tol:
        raise Fault(f"axis {' and '.join(joint['axis'])} coincide, so they give no direction")
    for param in joint.get("range", []):
        if param not in p.values:
            raise Fault(f"range names {param}, which params.yaml does not define")
    if "range" in joint:
        (low, lo), (high, hi) = range_ends(p, joint)
        if lo > hi:
            raise Fault(f"range {low} {lo:g} exceeds {high} {hi:g}")


def _gear_fault(p: Project, model: Model, gear: dict) -> None:
    for key in ("driver", "driven"):
        if gear[key] not in model.moving:
            raise Fault(f"{key} {gear[key]} is {unmoving(model, gear[key])}")
    if gear["driver"] == gear["driven"]:
        raise Fault(f"driver and driven are both {gear['driver']}; a gear couples two joints")
    key, param = gear_by(gear)
    across = model.quantity(gear["driver"]) != model.quantity(gear["driven"])
    if across != GEAR_BY[key][1]:
        raise Fault(
            f"a {key} does not couple these joints: a ratio couples two joints of one type, a "
            "lead a revolute joint and a slide"
        )
    if param not in p.values:
        raise Fault(f"{key} names {param}, which params.yaml does not define")
    if key == "lead" and p.values[param] == 0:
        raise Fault(f"lead {param} is 0, so the slide never moves")


def _cable_fault(p: Project, model: Model, cable: dict, closed_by: dict) -> None:
    first = model.instance_datum(cable["path"][0])[0]
    for datum in cable["path"]:
        model.instance_datum(datum)
    if "wheel" not in cable:
        return
    wheel = cable["wheel"]
    if wheel not in model.moving:
        raise Fault(f"wheel {wheel} is {unmoving(model, wheel)}")
    turn = model.joints[wheel].get("range", [])
    if len(turn) != 1:
        raise Fault(f"wheel {wheel} needs a one-ended range, its full turn from as built")
    if p.values.get(turn[0]) == 0:
        raise Fault(f"wheel {wheel}'s full turn {turn[0]} is 0, so it closes nothing")
    if first == model.joints[wheel]["child"]:
        raise Fault(
            f"its path starts at {cable['path'][0]}, on the wheel; start it where the cable "
            "leaves the wheel, on an instance the wheel does not turn"
        )
    geared = {g[k] for g in model.gears.values() for k in ("driver", "driven")}
    for joint, param in cable["closes"].items():
        if joint not in model.moving:
            raise Fault(f"closes {joint}, which is {unmoving(model, joint)}")
        if joint == wheel:
            raise Fault(f"closes its own wheel {wheel}")
        if joint in geared:
            raise Fault(f"closes {joint}, which a gear couples")
        if joint in closed_by:
            raise Fault(f"closes {joint}, which cable {closed_by[joint]} closes too")
        if param not in p.values:
            raise Fault(f"closes {joint} to {param}, which params.yaml does not define")


def _cables_on_axes(p: Project, model: Model) -> None:
    """[cable-on-axis] for each path datum of a cable that lies on the axis of a revolute joint the
    cable closes and turns with it: turning that joint leaves the cable's length unchanged."""
    for name, cable in model.cables.items():
        for joint in cable.get("closes", {}):
            hinge = model.joints[joint]
            if hinge["type"] != "revolute":
                continue
            turned, grew = {hinge["child"]}, True  # the instances the joint turns
            while grew:
                below = {j["child"] for j in model.joints.values() if j["parent"] in turned}
                grew, turned = not below <= turned, turned | below
            a, b = (model.placed(d) for d in hinge["axis"])
            for datum in cable["path"]:
                if model.instance_datum(datum)[0] in turned:
                    if (model.placed(datum) - a).cross((b - a).normalized()).length <= p.length_tol:
                        p.warn(
                            "cable-on-axis",
                            f"cable {name}: {datum} lies on the axis of {joint}, which it closes, "
                            f"so turning {joint} leaves the cable's length unchanged",
                        )


def _mass_model(p: Project, model: Model) -> dict[str, Mass]:
    """Each part's Mass from params.yaml's parts: its datasheet mass, or its volume times its
    density, with the solid's inertia scaled to that mass. In a model with joints every part an
    instance places needs an entry."""
    from build123d import CenterOf

    for name in p.parts.keys() - model.parts.keys():
        p.error("part-mass", f"params.yaml parts {name}: model.build returns no part {name}")
    placed = {part for part, _ in model.assembly.values()}
    masses = {}
    for name, part in model.parts.items():
        entry = p.parts.get(name) or {}
        by = next(iter(entry), None)
        if by is None:
            if model.joints and name in placed:
                p.error(
                    "part-mass",
                    f"part {name}: params.yaml parts gives it no mass or density, so the MJCF "
                    "export cannot weigh it",
                )
        elif entry[by] not in p.params:
            p.error(
                "part-mass",
                f"part {name}: params.yaml parts names {by} {entry[by]}, which params.yaml does "
                "not define",
            )
        elif entry[by] in p.values and part.volume > 0:  # one with none is [part-invalid]
            volume, value = part.volume, p.values[entry[by]]
            mass = value if by == "mass" else volume * value
            inertia = part.matrix_of_inertia
            pairs = ((0, 0), (1, 1), (2, 2), (0, 1), (0, 2), (1, 2))
            masses[name] = Mass(
                mass=printed(mass)[0],
                by=by,
                param=entry[by],
                center=printed(*part.center(CenterOf.MASS)),
                inertia=printed(*(mass / volume * inertia[i][j] for i, j in pairs)),
            )
    return masses


# The project length units build123d's STEP export names; a part in any other is scaled to mm.
_STEP_UNITS = {"mm": "MM", "cm": "CM", "m": "M", "µm": "MC", "in": "IN", "ft": "FT"}


def export(p: Project, model: Model) -> list[Path]:
    """Write build/parts/<part>.step and build/assembly.step, each at its true size whatever the
    project's length unit: a CAD program opens a 2 in part as 50.8 mm, not as 2 mm."""
    from build123d import Unit, export_step

    out = p.root / "build"
    (out / "parts").mkdir(parents=True, exist_ok=True)
    unit = p.units["length"]
    written = []
    for name, part in model.parts.items():
        written.append(out / "parts" / f"{name}.step")
        if unit in _STEP_UNITS:
            part.label = name
            export_step(part, str(written[-1]), unit=Unit[_STEP_UNITS[unit]])
        else:
            scaled = part.scale(units.convert(1.0, unit, {"length": "mm"}))
            scaled.label = name
            export_step(scaled, str(written[-1]))
    if model.assembly:
        written.append(out / "assembly.step")
        _export_assembly(p.meta.get("name", "assembly"), model, units.UNITS[unit].si, written[-1])
    return written


def _export_assembly(name: str, model: Model, unit: float, path: Path) -> None:
    """Write the assembly as a CAD program's tree shows it: each part once, under its own name,
    and each instance an occurrence of its part, under the instance's name. build123d's
    export_step names a part after the last of its instances. unit is the project's length unit
    in metres."""
    # OCP's modules re-export a compiled module whose names pyright cannot see, so they are
    # looked up by name.
    ocp = {
        module: importlib.import_module(f"OCP.{module}")
        for module in (
            "IFSelect", "Message", "STEPCAFControl", "STEPControl", "TCollection", "TDataStd",
            "TDocStd", "TopLoc", "XCAFApp", "XCAFDoc",
        )
    }  # fmt: skip
    text = ocp["TCollection"].TCollection_ExtendedString
    named = ocp["TDataStd"].TDataStd_Name.Set_s
    tool = ocp["XCAFDoc"].XCAFDoc_DocumentTool

    doc = ocp["TDocStd"].TDocStd_Document(text("XmlOcaf"))
    ocp["XCAFApp"].XCAFApp_Application.GetApplication_s().NewDocument(text("MDTV-XCAF"), doc)
    tool.SetLengthUnit_s(doc, unit)  # as export_step is told a part's
    shapes = tool.ShapeTool_s(doc.Main())
    top = shapes.NewShape()
    named(top, text(name))
    origin = ocp["TopLoc"].TopLoc_Location()
    parts = {}
    for inst, (part, location) in model.assembly.items():
        shape = model.parts[part].wrapped
        if part not in parts:
            # A part built at a location of its own is added without it, and each instance
            # carries it: a located shape would be written as an unnamed part.
            parts[part] = shapes.AddShape(shape.Located(origin), False)
            named(parts[part], text(part))
        placed = location.wrapped.Multiplied(shape.Location())
        named(shapes.AddComponent(top, parts[part], placed), text(inst))
    shapes.UpdateAssemblies()
    quiet = ocp["Message"].Message_Gravity.Message_Fail  # OCCT's transfer log, off the console
    for printer in ocp["Message"].Message.DefaultMessenger_s().Printers():
        printer.SetTraceLevel(quiet)
    writer = ocp["STEPCAFControl"].STEPCAFControl_Writer()
    writer.Transfer(doc, ocp["STEPControl"].STEPControl_StepModelType.STEPControl_AsIs)
    if writer.Write(str(path)) != ocp["IFSelect"].IFSelect_ReturnStatus.IFSelect_RetDone:
        raise RuntimeError(f"could not write {path}")
