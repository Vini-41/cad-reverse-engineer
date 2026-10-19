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
from .geometry import EXPORT_DENSITY, Built, Poser, instance_datum
from .project import Project

# Steps from the as-built pose to the one a check names: each step starts from the last, so the
# loops close on the branch the model is built on.
STEPS = 20
ITERATIONS = 50


def _mujoco() -> Any:
    """The mujoco module, imported when first needed; it ships no type stubs."""
    return importlib.import_module("mujoco")


def _num(*values: float) -> str:
    return " ".join(f"{v:.12g}" for v in values)


def _frame(location) -> dict[str, str]:
    """The pos and xyaxes MJCF attributes of a Location."""
    from build123d import Plane

    plane = Plane(location)
    return {
        "pos": _num(*plane.origin),
        "xyaxes": _num(*plane.x_dir, *plane.y_dir),
    }


def _located(built: Built, name: str) -> tuple[str, tuple[float, float, float]]:
    """The instance <instance>.<feature> names, and the datum's point in its part's frame, which
    is also its point in the instance's body frame."""
    named = instance_datum(built, name)
    assert named is not None  # geometry.build drops joints and loops naming no datum
    return named[0], built.datums[named[1]]


def _point(built: Built, name: str) -> tuple[float, float, float]:
    return _located(built, name)[1]


@dataclass
class Linkage:
    """A model's MJCF, the part meshes it reads, and MuJoCo's model of it once loaded."""

    xml: str
    meshes: dict[str, bytes]
    model: Any = None
    # pose key -> the posed assembly and its report entry, or None where a loop stays open
    posed: dict = field(default_factory=dict)


def mjcf(p: Project, built: Built) -> Linkage | None:
    """The MJCF of a model with joints, loaded into MuJoCo, else [mjcf-load] naming why MuJoCo
    rejects it; None for a model with no joints, which is static."""
    if not built.joints:
        return None
    from build123d import CenterOf, export_stl

    meshes = {}
    with tempfile.TemporaryDirectory() as tmp:
        for name, part in built.parts.items():
            path = Path(tmp) / f"{name}.stl"
            export_stl(part, str(path))
            meshes[f"{name}.stl"] = path.read_bytes()

    radian = units.size("angle", p.units)
    root = ET.Element("mujoco", model=str(p.meta.get("name", "model")))
    ET.SubElement(root, "compiler", angle="radian", meshdir="meshes", autolimits="true")
    ET.SubElement(root, "option", gravity="0 0 0")
    asset = ET.SubElement(root, "asset")
    for name in built.parts:
        ET.SubElement(asset, "mesh", name=name, file=f"{name}.stl")

    moved_by = {j["child"]: (name, j) for name, j in built.joints.items()}
    sites: dict[str, list[str]] = {}
    for pair in built.loops.values():
        for datum in pair:
            on = sites.setdefault(_located(built, datum)[0], [])
            if datum not in on:  # a datum two loops name is one site
                on.append(datum)
    density = p.values.get(EXPORT_DENSITY)

    def body(parent: ET.Element, inst: str, parent_location) -> None:
        part, location = built.assembly[inst]
        frame = _frame(
            location if parent_location is None else parent_location.inverse() * location
        )
        element = ET.SubElement(parent, "body", {"name": inst, **frame})
        if inst in moved_by:
            name, joint = moved_by[inst]
            a, b = (_point(built, d) for d in joint["axis"])
            attrs = {"name": name, "type": "hinge", "pos": _num(*a)}
            attrs["axis"] = _num(*(y - x for x, y in zip(a, b)))
            if "range" in joint:
                attrs["range"] = _num(*(p.values[n] * radian for n in joint["range"]))
            ET.SubElement(element, "joint", **attrs)
        ET.SubElement(element, "geom", type="mesh", mesh=part, contype="0", conaffinity="0")
        if density is not None:
            solid = built.parts[part]
            inertia = solid.matrix_of_inertia
            ET.SubElement(
                element,
                "inertial",
                pos=_num(*solid.center(CenterOf.MASS)),
                mass=_num(solid.volume * density),
                fullinertia=_num(
                    *(
                        density * inertia[i][j]
                        for i, j in ((0, 0), (1, 1), (2, 2), (0, 1), (0, 2), (1, 2))
                    )
                ),
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
    if built.loops:
        equality = ET.SubElement(root, "equality")
        for name, (a, b) in built.loops.items():
            ET.SubElement(equality, "connect", name=name, site1=a, site2=b)
    actuated = [name for name, j in built.joints.items() if j["drive"] == "actuated"]
    if actuated:
        actuator = ET.SubElement(root, "actuator")
        for name in actuated:
            ET.SubElement(actuator, "motor", name=name, joint=name)
    ET.indent(root)
    linkage = Linkage(ET.tostring(root, encoding="unicode") + "\n", meshes)

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

    def pose(c: dict, at: dict | None = None) -> tuple[Built, dict] | None:
        cid, joints = c.get("id", "?"), c.get("pose") or {}
        if linkage.model is None:
            return None  # the [mjcf-load] finding says no posed check is evaluated
        values, shown = {}, {}
        for joint, ref in joints.items():
            if joint not in built.joints:
                p.error("check-config", f"check {cid}: pose names {joint}, which is not a joint")
                return None
            value = p.values[ref] if ref in p.params else p.evidence_value(ref)
            if value is None or math.isnan(value):
                p.error(
                    "check-config",
                    f"check {cid}: pose {joint}: {ref} names neither a param nor a ledger value",
                )
                return None
            values[joint] = value * units.size("angle", p.units)
            # In the project's angle unit, rounded clear of the unit conversion's last bits.
            shown[joint] = {"from": ref, "value": float(f"{value:.12g}")}
        for joint, (value, label) in (at or {}).items():
            values[joint] = value * units.size("angle", p.units)
            shown[joint] = {"from": label, "value": float(f"{value:.12g}")}
        key = tuple(sorted(values.items()))
        if key not in linkage.posed:
            linkage.posed[key] = _solve(p, built, linkage, values, shown)
        placed = linkage.posed[key]
        return None if placed is None else (placed, shown)

    return pose


def _solve(p: Project, built: Built, linkage: Linkage, values: dict, shown: dict) -> Built | None:
    """The assembly with the named joints at values (radians from as built), every other actuated
    joint held as built and the passive ones solved to close the loops; None after [loop-open]
    for each loop that stays open."""
    mujoco = _mujoco()
    import numpy as np

    from build123d import Location, Plane

    m, tol = linkage.model, p.length_tol
    d = mujoco.MjData(m)
    jid = {name: mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_JOINT, name) for name in built.joints}
    free = [
        jid[name]
        for name, joint in built.joints.items()
        if joint["drive"] == "passive" and name not in values
    ]
    dofs = [m.jnt_dofadr[j] for j in free]
    qpos = [m.jnt_qposadr[j] for j in free]
    loops = {
        name: tuple(mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_SITE, s) for s in pair)
        for name, pair in built.loops.items()
    }
    jac1, jac2 = np.zeros((3, m.nv)), np.zeros((3, m.nv))

    def residual():
        return np.concatenate([d.site_xpos[a] - d.site_xpos[b] for a, b in loops.values()])

    for step in range(1, STEPS + 1):
        for name, value in values.items():
            d.qpos[m.jnt_qposadr[jid[name]]] = value * step / STEPS
        for _ in range(ITERATIONS):
            mujoco.mj_kinematics(m, d)
            if not loops or not dofs:
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
            d.qpos[qpos] += np.linalg.lstsq(np.vstack(rows)[:, dofs], -r, rcond=None)[0]
    mujoco.mj_kinematics(m, d)
    at = ", ".join(f"{j} at {s['value']:g} ({s['from']})" for j, s in shown.items())
    open_ = False
    for name, (a, b) in loops.items():
        gap = float(np.linalg.norm(d.site_xpos[a] - d.site_xpos[b]))
        if gap > tol:
            first, second = built.loops[name]
            p.error(
                "loop-open",
                f"loop {name}: {first} and {second} stay {gap:.4g} apart with {at}; the links "
                "cannot close there, so checks at this pose are not evaluated",
            )
            open_ = True
    if open_:
        return None
    assembly = {}
    for inst, (part, _) in built.assembly.items():
        bid = mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_BODY, inst)
        frame = d.xmat[bid].reshape(3, 3)
        plane = Plane(origin=tuple(d.xpos[bid]), x_dir=tuple(frame[:, 0]), z_dir=tuple(frame[:, 2]))
        assembly[inst] = (part, Location(plane))
    return replace(built, assembly=assembly)
