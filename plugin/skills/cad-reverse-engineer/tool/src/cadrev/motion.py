"""Export a model with joints as MJCF, and pose its assembly through MuJoCo (ADR-0008).

MuJoCo closes the loops; every check is still evaluated by cadrev on the build123d instances,
placed where MuJoCo puts their bodies. The MJCF is in the project's units, without gravity: a
kinematic model, each body framed as its part, so a datum is the same point in both.
"""

from __future__ import annotations

import importlib
import math
import tempfile
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

from . import units
from .geometry import (
    Built,
    Coupling,
    Poser,
    couplings,
    joint_type,
    located,
    physics_named,
    pose_text,
    printed,
    range_ends,
)
from .project import Project

# Steps from the as-built pose to the one a check names: each step starts from the last, so the
# loops close on the branch the model is built on.
STEPS = 20
ITERATIONS = 50
# MuJoCo's STL decoder takes a file of at most this many faces.
STL_FACES = 200_000
# The (linear, angular) tolerances a part's mesh is tessellated at where build123d's default
# (0.001, 0.1) gives more faces than STL_FACES, each coarser than the last, until it fits.
COARSER = ((0.01, 0.2), (0.1, 0.5), (1.0, 1.0))


def _mujoco() -> Any:
    """The mujoco module, imported when first needed; it ships no type stubs."""
    return importlib.import_module("mujoco")


def _num(*values: float) -> str:
    return " ".join(repr(v) for v in printed(*values))


def _frame(location) -> dict[str, str]:
    """The pos and xyaxes MJCF attributes of a Location."""
    from build123d import Plane

    plane = Plane(location)
    return {
        "pos": _num(*plane.origin),
        "xyaxes": _num(*plane.x_dir, *plane.y_dir),
    }


def _point(built: Built, name: str) -> tuple[float, float, float]:
    return located(built, name)[1]


def mjcf_size(p: Project, quantity: str) -> float:
    """The SI size of one MJCF unit of quantity: the project's length, mass and time, the force
    they make (g·mm/s² by default, not N), and radians."""
    base = {q: units.size(q, p.units) for q in ("length", "mass", "time")}
    base |= {"force": base["mass"] * base["length"] / base["time"] ** 2, "angle": 1.0}
    if quantity in base:
        return base[quantity]
    return math.prod(base[q] ** power for q, power in units.DERIVED[quantity].items())


def joint_size(p: Project, joint: dict) -> float:
    """The size of one of the project's units of a joint's quantity in the MJCF's: a radian for a
    revolute joint's angle, 1 for a slide's length, which the MJCF keeps in the project's unit."""
    quantity = str(joint_type(joint).quantity)
    return units.size(quantity, p.units) / mjcf_size(p, quantity)


def _physics(p: Project, entry: dict, kind: str) -> dict[str, str]:
    """The MJCF attributes of the physics params entry names, at their values converted from
    the project's units to the MJCF's."""
    attrs = {}
    for key, slot in physics_named(kind, entry).items():
        quantity = slot.quantity
        assert quantity is not None  # only a fixed joint has none, and it exports no joint
        size = units.size(quantity, p.units) / mjcf_size(p, quantity)
        attrs[slot.attr] = _num(p.values[entry[key]] * size)
    return attrs


@dataclass
class Linkage:
    """A model's MJCF, the part meshes it reads, and MuJoCo's model of it once loaded."""

    xml: str
    meshes: dict[str, bytes]
    # part -> how its mesh was coarsened to fit STL_FACES: its faces at the default, and the
    # tolerances and faces it was exported at
    coarsened: dict[str, dict] = field(default_factory=dict)
    model: Any = None
    # pose key -> the posed assembly, or None where it cannot be reached
    posed: dict = field(default_factory=dict)


def mjcf(p: Project, built: Built) -> Linkage | None:
    """The MJCF of a model with joints, loaded into MuJoCo, else [mjcf-load] naming why MuJoCo
    rejects it; None for a model with no joints, which is static. A loop whose datums lie apart
    in the assembly as built is [loop-open]."""
    if not built.joints:
        return None
    _as_built_loops(p, built)
    meshes, coarsened, fits = {}, {}, True
    with tempfile.TemporaryDirectory() as tmp:
        for name, part in built.parts.items():
            path = Path(tmp) / f"{name}.stl"
            stl, coarser = _mesh(part, path)
            meshes[f"{name}.stl"] = stl
            if _faces(stl) > STL_FACES:
                fits = False
                tolerance, angular = COARSER[-1]
                p.error(
                    "mjcf-load",
                    f"part {name}: its mesh has {_faces(stl)} faces at the coarsest tessellation "
                    f"cadrev tries (tolerance {tolerance:g}, angular tolerance {angular:g}), over "
                    f"the {STL_FACES} faces MuJoCo's STL decoder takes, so MuJoCo cannot load "
                    "build/model.mjcf and no check with a pose is evaluated; build the part from "
                    "fewer faces: a flat face, such as an imported mesh's triangle, stays at least "
                    "one triangle at any tolerance",
                )
            elif coarser is not None:
                coarsened[name] = coarser

    root = ET.Element("mujoco", model=str(p.meta.get("name", "model")))
    ET.SubElement(root, "compiler", angle="radian", meshdir="meshes", autolimits="true")
    ET.SubElement(root, "option", gravity="0 0 0")
    asset = ET.SubElement(root, "asset")
    for name in built.parts:
        ET.SubElement(asset, "mesh", name=name, file=f"{name}.stl")

    moved_by = {j["child"]: (name, j) for name, j in built.joints.items()}
    sites: dict[str, list[str]] = {}
    paths = [*built.loops.values(), *(t["path"] for t in built.tendons.values())]
    for path in [*paths, *(c["path"] for c in built.cables.values())]:
        for datum in path:
            on = sites.setdefault(located(built, datum)[0], [])
            if datum not in on:  # a datum two loops or tendons name is one site
                on.append(datum)

    def body(parent: ET.Element, inst: str, parent_location) -> None:
        part, location = built.assembly[inst]
        frame = _frame(
            location if parent_location is None else parent_location.inverse() * location
        )
        element = ET.SubElement(parent, "body", {"name": inst, **frame})
        if (
            inst in moved_by and moved_by[inst][0] in built.moving
        ):  # a fixed joint's child is one body with its parent
            name, joint = moved_by[inst]
            a, b = (_point(built, d) for d in joint["axis"])
            attrs = {"name": name, "type": str(joint_type(joint).mjcf), "pos": _num(*a)}
            attrs["axis"] = _num(*(y - x for x, y in zip(a, b)))
            if "range" in joint:
                size = joint_size(p, joint)
                attrs["range"] = _num(*(value * size for _, value in range_ends(p, joint)))
            ET.SubElement(element, "joint", attrs | _physics(p, joint, "joint"))
        ET.SubElement(element, "geom", type="mesh", mesh=part, contype="0", conaffinity="0")
        weighed = built.masses.get(part)
        if weighed is not None:
            ET.SubElement(
                element,
                "inertial",
                pos=_num(*weighed.center),
                mass=_num(weighed.mass),
                fullinertia=_num(*weighed.inertia),
            )
        for datum in sites.get(inst, []):
            ET.SubElement(element, "site", name=datum, pos=_num(*_point(built, datum)))
        for child, (_, joint) in moved_by.items():
            if joint["parent"] == inst:
                body(element, child, location)

    world = ET.SubElement(root, "worldbody")
    for inst in built.assembly:
        if inst not in moved_by:
            body(world, inst, None)
    coupled = couplings(p, built)
    if built.loops or coupled:
        equality = ET.SubElement(root, "equality")
        for name, (a, b) in built.loops.items():
            ET.SubElement(equality, "connect", name=name, site1=a, site2=b)
        taken = {*built.loops, *built.gears}
        for c in coupled:  # driven = ratio × driver
            name = c.name if c.kind == "gear" else _unique(f"{c.name}_{c.driven}", taken)
            ET.SubElement(
                equality,
                "joint",
                name=name,
                joint1=c.driven,
                joint2=c.driver,
                polycoef=_num(0, _mjcf_ratio(p, built, c), 0, 0, 0),
            )
    if built.tendons or built.cables:
        tendon = ET.SubElement(root, "tendon")
        for name, t in built.tendons.items():
            spatial = ET.SubElement(tendon, "spatial", {"name": name} | _physics(p, t, "tendon"))
            for datum in t["path"]:
                ET.SubElement(spatial, "site", site=datum)
        named = cable_tendons(built)
        for name, c in built.cables.items():  # no stiffness: its length is only read
            spatial = ET.SubElement(tendon, "spatial", name=named[name])
            for datum in c["path"]:
                ET.SubElement(spatial, "site", site=datum)
    actuated = [name for name, j in built.moving.items() if j["drive"] == "actuated"]
    if actuated:
        actuator = ET.SubElement(root, "actuator")
        for name in actuated:
            ET.SubElement(actuator, "motor", name=name, joint=name)
    ET.indent(root)
    linkage = Linkage(ET.tostring(root, encoding="unicode") + "\n", meshes, coarsened)
    if not fits:
        return linkage

    mujoco = _mujoco()

    try:
        linkage.model = mujoco.MjModel.from_xml_string(linkage.xml, linkage.meshes)
    except ValueError as exc:
        why = " ".join(str(exc).split())
        p.error(
            "mjcf-load",
            f"MuJoCo rejects build/model.mjcf, so no check with a pose is evaluated: {why}",
        )
    return linkage


def _faces(stl: bytes) -> int:
    """The face count a binary STL's header gives."""
    return int.from_bytes(stl[80:84], "little")


def _mesh(part, path: Path) -> tuple[bytes, dict | None]:
    """The binary STL of part MuJoCo is given, written to path: at build123d's default
    tessellation, or where that has more faces than STL_FACES, at the first of COARSER that fits,
    or the coarsest; with how it was coarsened, None if it was not."""
    import copy

    from build123d import export_stl

    export_stl(part, str(path))
    stl = path.read_bytes()
    default = _faces(stl)
    if default <= STL_FACES:
        return stl, None
    coarser = None
    for tolerance, angular in COARSER:
        # A copy has no triangulation, so it is tessellated anew; the part keeps its own, which
        # the checks' bounding boxes read.
        export_stl(copy.deepcopy(part), str(path), tolerance=tolerance, angular_tolerance=angular)
        stl = path.read_bytes()
        coarser = {
            "faces": _faces(stl),
            "default_faces": default,
            "tolerance": tolerance,
            "angular_tolerance": angular,
        }
        if coarser["faces"] <= STL_FACES:
            break
    assert coarser is not None  # COARSER is not empty
    return stl, coarser


def cable_tendons(built: Built) -> dict[str, str]:
    """cable name -> the name of its spatial tendon in the MJCF: its own, unless a tendon has it."""
    taken = set(built.tendons)
    return {name: _unique(name, taken) for name in built.cables}


def _unique(name: str, taken: set[str]) -> str:
    """name, or name_2, name_3... where taken has it; added to taken."""
    found, n = name, 1
    while found in taken:
        n += 1
        found = f"{name}_{n}"
    taken.add(found)
    return found


def _mjcf_ratio(p: Project, built: Built, c: Coupling) -> float:
    """A coupling's ratio in the MJCF's units of each joint (radians or the project's length)."""
    return c.ratio * joint_size(p, built.joints[c.driven]) / joint_size(p, built.joints[c.driver])


def _as_built_loops(p: Project, built: Built) -> None:
    """[loop-open] for each loop whose two datums lie more than tolerance.length apart where the
    assembly places their instances: the model is not built closed."""
    from build123d import Location

    for name, pair in built.loops.items():
        a, b = (
            (built.assembly[inst][1] * Location(point)).position
            for inst, point in (located(built, d) for d in pair)
        )
        gap = (a - b).length
        if gap > p.length_tol:
            p.error(
                "loop-open",
                f"loop {name}: {pair[0]} and {pair[1]} stay {gap:.4g} apart as built; build the "
                "assembly closed, with every loop's datums together",
            )


def write(p: Project, linkage: Linkage) -> list[Path]:
    """Write build/model.mjcf and build/meshes/<part>.stl."""
    out = p.root / "build"
    (out / "meshes").mkdir(parents=True, exist_ok=True)
    written = []
    for name, data in linkage.meshes.items():
        path = out / "meshes" / name
        path.write_bytes(data)
        written.append(path)
    path = out / "model.mjcf"
    path.write_text(linkage.xml, encoding="utf8")
    return [*written, path]


def poser(p: Project, built: Built, linkage: Linkage) -> Poser:
    """What poses a check of this model: see geometry.Poser."""

    def place(c: dict, set_to: dict | None = None, at: str = "pose") -> tuple[Built, dict] | None:
        cid, named = c.get("id", "?"), c.get(at) or {}
        if linkage.model is None:
            return None  # the [mjcf-load] finding says no posed check is evaluated
        values, pose = {}, {}
        for joint, ref in named.items():
            if joint not in built.moving:
                why = "a fixed joint" if joint in built.joints else "not a joint"
                p.error("check-config", f"check {cid}: {at} names {joint}, which is {why}")
                return None
            value = p.values[ref] if ref in p.params else p.evidence_value(ref)
            if value is None or math.isnan(value):
                p.error(
                    "check-config",
                    f"check {cid}: {at} {joint}: {ref} names neither a param nor a ledger value",
                )
                return None
            values[joint], pose[joint] = value, {"from": ref, "value": printed(value)[0]}
        for joint, (value, label) in (set_to or {}).items():
            values[joint], pose[joint] = value, {"from": label, "value": printed(value)[0]}
        values = _through_couplings(p, built, values)
        clash = _coupling_clash(p, built, values)
        if clash:
            p.error("check-config", f"check {cid}: {at} {pose_text(pose)}: {clash}")
            return None
        key = (tuple(sorted(values.items())), tuple(sorted(set_to or {})))
        if key not in linkage.posed:
            linkage.posed[key] = _solve(p, built, linkage, values, pose, set(set_to or {}))
        placed = linkage.posed[key]
        return None if placed is None else (placed, pose)

    return place


def _through_couplings(p: Project, built: Built, values: dict) -> dict:
    """values with each joint a gear couples to one of them set too: a driven joint at ratio
    times its driver, a driver at its driven over ratio."""
    geared, changed = dict(values), True
    while changed:
        changed = False
        for c in couplings(p, built):
            if c.driver in geared and c.driven not in geared:
                geared[c.driven], changed = c.ratio * geared[c.driver], True
            elif c.driven in geared and c.driver not in geared and c.ratio:
                geared[c.driver], changed = geared[c.driven] / c.ratio, True
    return geared


def _coupling_clash(p: Project, built: Built, values: dict) -> str | None:
    """Why values cannot be reached, where it sets a gear's or cable's two joints out of its ratio,
    or sets alone a joint a cable closes to 0, which cannot set its wheel; None where it can."""
    for c in couplings(p, built):
        if c.driver in values and c.driven in values:
            if not math.isclose(values[c.driven], c.ratio * values[c.driver], abs_tol=1e-9):
                return (
                    f"{c.kind} {c.name} {c.law}, so set one of them and the {c.kind} moves "
                    "the other"
                )
        elif c.kind == "cable" and c.driven in values and not c.ratio:
            return f"{c.kind} {c.name} {c.law}, so {c.driven} cannot set {c.driver}; set {c.driver}"
    return None


def _solve(
    p: Project, built: Built, linkage: Linkage, values: dict, pose: dict, set_by_check: set
) -> Built | None:
    """The assembly with the named joints at values (in the project's angle unit, from as built),
    every other actuated joint held as built and the passive ones solved to close the loops; None
    after [loop-open] for each loop that stays open, or [joint-range] for each joint, but those
    set_by_check, that ends outside its range. The assembly's moved names the joints values sets."""
    mujoco = _mujoco()
    import numpy as np

    from build123d import Location, Plane

    m, tol = linkage.model, p.length_tol
    size = {name: joint_size(p, joint) for name, joint in built.moving.items()}
    d = mujoco.MjData(m)
    jid = {name: mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_JOINT, name) for name in built.moving}
    free = [
        jid[name]
        for name, joint in built.moving.items()
        if joint["drive"] == "passive" and name not in values
    ]
    columns = [m.jnt_dofadr[j] for j in free]  # their columns in a Jacobian
    qpos = [m.jnt_qposadr[j] for j in free]
    loops = {
        name: tuple(mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_SITE, s) for s in pair)
        for name, pair in built.loops.items()
    }
    jac1, jac2 = np.zeros((3, m.nv)), np.zeros((3, m.nv))
    # Each coupling whose joints values leaves free to move: (driven, driver, ratio) as MuJoCo ids.
    coupled = [
        (jid[c.driven], jid[c.driver], _mjcf_ratio(p, built, c))
        for c in couplings(p, built)
        if not {c.driver, c.driven} <= values.keys()
    ]
    coupled_rows = np.zeros((len(coupled), m.nv))
    for row, (driven, driver, ratio) in zip(coupled_rows, coupled):
        row[m.jnt_dofadr[driven]] += 1
        row[m.jnt_dofadr[driver]] -= ratio

    def residual():
        loop_gaps = [d.site_xpos[a] - d.site_xpos[b] for a, b in loops.values()]
        turns = [
            [d.qpos[m.jnt_qposadr[driven]] - ratio * d.qpos[m.jnt_qposadr[driver]]]
            for driven, driver, ratio in coupled
        ]
        return np.concatenate([*loop_gaps, *turns])

    for step in range(1, STEPS + 1):
        for name, value in values.items():
            d.qpos[m.jnt_qposadr[jid[name]]] = value * size[name] * step / STEPS
        for _ in range(ITERATIONS):
            mujoco.mj_kinematics(m, d)
            if not (loops or coupled) or not columns:
                break
            mujoco.mj_comPos(m, d)
            r = residual()
            if np.linalg.norm(r) < tol * 1e-3:
                break
            rows = []
            for a, b in loops.values():
                mujoco.mj_jacSite(m, d, jac1, None, a)
                mujoco.mj_jacSite(m, d, jac2, None, b)
                rows.append(jac1 - jac2)
            rows.append(coupled_rows)
            d.qpos[qpos] += np.linalg.lstsq(np.vstack(rows)[:, columns], -r, rcond=None)[0]
    mujoco.mj_kinematics(m, d)
    at = pose_text(pose)
    reached = True
    for name, (a, b) in loops.items():
        gap = float(np.linalg.norm(d.site_xpos[a] - d.site_xpos[b]))
        if gap > tol:
            first, second = built.loops[name]
            p.error(
                "loop-open",
                f"loop {name}: {first} and {second} stay {gap:.4g} apart with {at}; the links "
                "cannot close there, so checks at this pose are not evaluated",
            )
            reached = False
    if not reached:
        return None
    for name, joint in built.moving.items():
        if "range" not in joint or name in set_by_check:
            continue
        kind = joint_type(joint)
        quantity = str(kind.quantity)
        slack = p.tolerance(quantity) / p.compared_size(quantity)  # in the project's unit
        turned = float(d.qpos[m.jnt_qposadr[jid[name]]]) / size[name]
        (low_name, low), (high_name, high) = range_ends(p, joint)
        if not low - slack <= turned <= high + slack:
            p.error(
                "joint-range",
                f"joint {name}: {kind.moves} {turned:.4g} with {at}, outside its range {low_name} "
                f"{low:g} to {high_name} {high:g}; the mechanism cannot reach this pose, so "
                "checks at it are not evaluated",
            )
            reached = False
    if not reached:
        return None
    assembly = {}
    for inst, (part, _) in built.assembly.items():
        bid = mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_BODY, inst)
        frame = d.xmat[bid].reshape(3, 3)
        plane = Plane(origin=tuple(d.xpos[bid]), x_dir=tuple(frame[:, 0]), z_dir=tuple(frame[:, 2]))
        assembly[inst] = (part, Location(plane))
    return replace(built, assembly=assembly, moved=frozenset(values))
