"""Export a model with joints as MJCF, and pose its assembly through MuJoCo.

The loops close on MuJoCo's model of the export: Newton steps over the passive joints, on the
site positions and Jacobians MuJoCo gives, so cadrev holds no kinematics of its own. Every check
is still evaluated by cadrev on the build123d instances, placed where MuJoCo puts their bodies.
The MJCF is in the project's units, without gravity: a kinematic model, each body framed as its
part, so a datum is the same point in both.
"""

from __future__ import annotations

import copy
import importlib
import math
import tempfile
import xml.etree.ElementTree as ET
from dataclasses import replace
from pathlib import Path
from typing import Any

from . import Fault, units
from .build import JOINT_TYPES, Model, couplings, physics_of, printed, range_ends
from .project import Project

# Steps from the as-built pose to the one a check names: each step starts from the last, so the
# loops close on the branch the model is built on, in at most ITERATIONS Newton steps each.
STEPS = 20
ITERATIONS = 50
# MuJoCo's STL decoder takes a file of at most this many faces.
STL_FACES = 200_000
# The (linear, angular) tolerances a part's mesh is tessellated at where build123d's default
# (0.001, 0.1) gives more faces than STL_FACES, each coarser than the last, until it fits.
COARSER = ((0.01, 0.2), (0.1, 0.5), (1.0, 1.0))


def pose_text(pose: dict) -> str:
    """A pose as findings and report.md name it: `input at 60 (turn_60)`, `input at 360` for a
    number the pose gives, or `as built`."""
    named = [
        f"{j} at {s['value']:g}" + (f" ({s['from']})" if s["from"] else "") for j, s in pose.items()
    ]
    return ", ".join(named) or "as built"


def _num(*values: float) -> str:
    return " ".join(repr(v) for v in printed(*values))


def _frame(location) -> dict[str, str]:
    """The pos and xyaxes MJCF attributes of a Location."""
    from build123d import Plane

    plane = Plane(location)
    return {"pos": _num(*plane.origin), "xyaxes": _num(*plane.x_dir, *plane.y_dir)}


def _faces(stl: bytes) -> int:
    """The face count a binary STL's header gives."""
    return int.from_bytes(stl[80:84], "little")


def _mesh(part, path: Path) -> tuple[bytes, dict | None]:
    """The binary STL of part MuJoCo is given: at build123d's default tessellation, or where
    that has more faces than STL_FACES, at the first of COARSER that fits, or the coarsest; with
    how it was coarsened, None if it was not."""
    from build123d import export_stl

    export_stl(part, str(path))
    stl, coarser = path.read_bytes(), None
    default = _faces(stl)
    for tolerance, angular in COARSER if default > STL_FACES else ():
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
    return stl, coarser


def _unique(name: str, taken: set[str]) -> str:
    """name, or name_2, name_3... where taken has it; added to taken."""
    found, n = name, 1
    while found in taken:
        n += 1
        found = f"{name}_{n}"
    taken.add(found)
    return found


class Mechanism:
    """A model with joints as MuJoCo holds it: its MJCF, the part meshes it reads, and the
    assembly placed at each pose a check asks for."""

    def __init__(self, p: Project, model: Model):
        self.p, self.model = p, model
        self.couplings = couplings(p, model)
        self.meshes: dict[str, bytes] = {}
        # part -> how its mesh was coarsened to fit STL_FACES
        self.coarsened: dict[str, dict] = {}
        self._posed: dict = {}  # pose -> the assembly placed there, or None where it is not reached
        self._as_built_loops()
        fits = self._tessellate()
        self.xml = self._xml()
        self.mujoco: Any = importlib.import_module("mujoco")  # it ships no type stubs
        self.loaded: Any = None  # MuJoCo's model of it, once it loads
        try:
            if fits:
                self.loaded = self.mujoco.MjModel.from_xml_string(self.xml, self.meshes)
        except ValueError as exc:
            why = " ".join(str(exc).split())
            p.error(
                "mjcf-load",
                f"MuJoCo rejects build/model.mjcf, so no check with a pose is evaluated: {why}",
            )

    def _size(self, quantity: str) -> float:
        """How many MJCF units one project unit of quantity is. The MJCF is in the project's
        length, mass and time, the force they make (g·mm/s² by default, not N), and radians."""
        base = {q: units.size(q, self.p.units) for q in ("length", "mass", "time")}
        base |= {"force": base["mass"] * base["length"] / base["time"] ** 2, "angle": 1.0}
        powers = units.DERIVED.get(quantity, {quantity: 1})
        mjcf = math.prod(base[q] ** power for q, power in powers.items())
        return units.size(quantity, self.p.units) / mjcf

    def _joint_size(self, joint: str) -> float:
        return self._size(self.model.quantity(joint))

    def _ratio(self, c) -> float:
        """A coupling's ratio in the MJCF's units of each joint."""
        return c.ratio * self._joint_size(c.driven) / self._joint_size(c.driver)

    def _as_built_loops(self) -> None:
        for name, (a, b) in self.model.loops.items():
            gap = (self.model.placed(a) - self.model.placed(b)).length
            if gap > self.p.length_tol:
                self.p.error(
                    "loop-open",
                    f"loop {name}: {a} and {b} stay {gap:.4g} apart as built; build the assembly "
                    "closed, with every loop's datums together",
                )

    def _tessellate(self) -> bool:
        """Mesh every part; False after [mjcf-load] for one MuJoCo's STL decoder cannot take."""
        fits = True
        with tempfile.TemporaryDirectory() as tmp:
            for name, part in self.model.parts.items():
                stl, coarser = _mesh(part, Path(tmp) / f"{name}.stl")
                self.meshes[f"{name}.stl"] = stl
                if _faces(stl) > STL_FACES:
                    fits = False
                    self.p.error(
                        "mjcf-load",
                        f"part {name}: its mesh has {_faces(stl)} faces at the coarsest "
                        f"tessellation cadrev tries, over the {STL_FACES} MuJoCo's STL decoder "
                        "takes, so no check with a pose is evaluated; build the part from fewer "
                        "faces",
                    )
                elif coarser is not None:
                    self.coarsened[name] = coarser
        return fits

    def _physics(self, joint: dict) -> dict[str, str]:
        """The MJCF attributes of the physics params a joint names, in its units."""
        return {
            attr: _num(self.p.values[joint[key]] * self._size(quantity))
            for key, (attr, quantity) in physics_of(joint).items()
            if key in joint
        }

    def _xml(self) -> str:
        p, model = self.p, self.model
        root = ET.Element("mujoco", model=str(p.meta.get("name", "model")))
        ET.SubElement(root, "compiler", angle="radian", meshdir="meshes", autolimits="true")
        ET.SubElement(root, "option", gravity="0 0 0")
        asset = ET.SubElement(root, "asset")
        for name in model.parts:
            ET.SubElement(asset, "mesh", name=name, file=f"{name}.stl")
        moved_by = {j["child"]: (name, j) for name, j in model.joints.items()}
        sites: dict[str, list[str]] = {}
        for path in [*model.loops.values(), *(c["path"] for c in model.cables.values())]:
            for datum in path:
                on = sites.setdefault(model.instance_datum(datum)[0], [])
                if datum not in on:  # a datum two loops or cables name is one site
                    on.append(datum)

        def body(parent: ET.Element, inst: str, parent_location) -> None:
            part, location = model.assembly[inst]
            frame = location if parent_location is None else parent_location.inverse() * location
            element = ET.SubElement(parent, "body", {"name": inst, **_frame(frame)})
            name, joint = moved_by.get(inst, (None, {}))
            if name in model.moving:  # a fixed joint's child is one body with its parent
                a, b = (model.instance_datum(d)[1] for d in joint["axis"])
                attrs = {
                    "name": name,
                    "type": str(JOINT_TYPES[joint["type"]].mjcf),
                    "pos": _num(*a),
                }
                attrs["axis"] = _num(*(y - x for x, y in zip(a, b)))
                if "range" in joint:
                    size = self._joint_size(name)
                    attrs["range"] = _num(*(value * size for _, value in range_ends(p, joint)))
                ET.SubElement(element, "joint", attrs | self._physics(joint))
            ET.SubElement(element, "geom", type="mesh", mesh=part, contype="0", conaffinity="0")
            if (weighed := model.masses.get(part)) is not None:
                ET.SubElement(
                    element,
                    "inertial",
                    pos=_num(*weighed.center),
                    mass=_num(weighed.mass),
                    fullinertia=_num(*weighed.inertia),
                )
            for datum in sites.get(inst, []):
                ET.SubElement(
                    element, "site", name=datum, pos=_num(*model.instance_datum(datum)[1])
                )
            for child, (_, joint) in moved_by.items():
                if joint["parent"] == inst:
                    body(element, child, location)

        world = ET.SubElement(root, "worldbody")
        for inst in model.assembly:
            if inst not in moved_by:
                body(world, inst, None)
        if model.loops or self.couplings:
            equality = ET.SubElement(root, "equality")
            for name, (a, b) in model.loops.items():
                ET.SubElement(equality, "connect", name=name, site1=a, site2=b)
            taken = {*model.loops, *model.gears}
            for c in self.couplings:  # driven = ratio × driver
                name = c.name if c.kind == "gear" else _unique(f"{c.name}_{c.driven}", taken)
                polycoef = _num(0, self._ratio(c), 0, 0, 0)
                ET.SubElement(
                    equality,
                    "joint",
                    name=name,
                    joint1=c.driven,
                    joint2=c.driver,
                    polycoef=polycoef,
                )
        if model.cables:
            # A cable is a spatial tendon with no stiffness: its length is only read.
            tendon = ET.SubElement(root, "tendon")
            for name, cable in model.cables.items():
                spatial = ET.SubElement(tendon, "spatial", name=name)
                for datum in cable["path"]:
                    ET.SubElement(spatial, "site", site=datum)
        actuated = [name for name, j in model.moving.items() if j["drive"] == "actuated"]
        if actuated:
            actuator = ET.SubElement(root, "actuator")
            for name in actuated:
                ET.SubElement(actuator, "motor", name=name, joint=name)
        ET.indent(root)
        return ET.tostring(root, encoding="unicode") + "\n"

    def write(self) -> list[Path]:
        """Write build/model.mjcf and build/meshes/<part>.stl."""
        out = self.p.root / "build"
        (out / "meshes").mkdir(parents=True, exist_ok=True)
        written = []
        for name, data in self.meshes.items():
            written.append(out / "meshes" / name)
            written[-1].write_bytes(data)
        written.append(out / "model.mjcf")
        written[-1].write_text(self.xml, encoding="utf8")
        return written

    def at(self, values: dict[str, float], pose: dict, free: frozenset[str] = frozenset()) -> Model:
        """The assembly with the named joints at values (in the project's units, from as built),
        every other actuated joint held as built and the passive ones solved to close the loops.
        A joint in free is where its check puts it, so its own range is not held against it. A
        Fault where the pose sets a gear's or cable's joints out of proportion; one already filed
        where a loop stays open ([loop-open]) or a joint ends outside its range ([joint-range])."""
        if self.loaded is None:
            raise Fault()  # [mjcf-load] says no check with a pose is evaluated
        values = dict(values)
        changed = True
        while changed:  # each joint a gear or cable couples to one of them moves with it
            changed = False
            for c in self.couplings:
                if c.driver in values and c.driven not in values:
                    values[c.driven], changed = c.ratio * values[c.driver], True
                elif c.driven in values and c.driver not in values and c.ratio:
                    values[c.driver], changed = values[c.driven] / c.ratio, True
        for c in self.couplings:
            if c.driver in values and c.driven in values:
                if not math.isclose(values[c.driven], c.ratio * values[c.driver], abs_tol=1e-9):
                    raise Fault(
                        f"{pose_text(pose)}: {c.kind} {c.name} {c.law}, so set one of them and the "
                        f"{c.kind} moves the other"
                    )
            elif c.kind == "cable" and c.driven in values and not c.ratio:
                raise Fault(
                    f"{pose_text(pose)}: {c.kind} {c.name} {c.law}, so {c.driven} cannot set "
                    f"{c.driver}; set {c.driver}"
                )
        key = (tuple(sorted(values.items())), tuple(sorted(free)))
        if key not in self._posed:
            self._posed[key] = self._solve(values, pose_text(pose), free)
        if self._posed[key] is None:
            raise Fault()
        return self._posed[key]

    def _solve(self, values: dict, at: str, free: frozenset[str]) -> Model | None:
        import numpy as np
        from build123d import Location, Plane

        p, model, mujoco, m = self.p, self.model, self.mujoco, self.loaded
        tol = p.length_tol
        size = {name: self._joint_size(name) for name in model.moving}
        d = mujoco.MjData(m)
        jid = {name: mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_JOINT, name) for name in model.moving}
        passive = [
            jid[name]
            for name, joint in model.moving.items()
            if joint["drive"] == "passive" and name not in values
        ]
        columns = [m.jnt_dofadr[j] for j in passive]  # their columns in a Jacobian
        qpos = [m.jnt_qposadr[j] for j in passive]
        loops = {
            name: tuple(mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_SITE, s) for s in pair)
            for name, pair in model.loops.items()
        }
        jac1, jac2 = np.zeros((3, m.nv)), np.zeros((3, m.nv))
        # Each coupling whose joints values leaves free to move: (it, driven, driver, ratio).
        coupled = [
            (c, jid[c.driven], jid[c.driver], self._ratio(c))
            for c in self.couplings
            if not {c.driver, c.driven} <= values.keys()
        ]
        coupled_rows = np.zeros((len(coupled), m.nv))
        for row, (_, driven, driver, ratio) in zip(coupled_rows, coupled):
            row[m.jnt_dofadr[driven]] += 1
            row[m.jnt_dofadr[driver]] -= ratio

        def slips() -> list[float]:
            """How far each coupled joint stands from where its coupling puts it, in MJCF units."""
            return [
                float(d.qpos[m.jnt_qposadr[driven]] - ratio * d.qpos[m.jnt_qposadr[driver]])
                for _, driven, driver, ratio in coupled
            ]

        def residual():
            loop_gaps = [d.site_xpos[a] - d.site_xpos[b] for a, b in loops.values()]
            return np.concatenate([*loop_gaps, slips()])

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
        reached = True
        for name, (a, b) in loops.items():
            gap = float(np.linalg.norm(d.site_xpos[a] - d.site_xpos[b]))
            if gap > tol:
                first, second = model.loops[name]
                p.error(
                    "loop-open",
                    f"loop {name}: {first} and {second} stay {gap:.4g} apart with {at}; the links "
                    "cannot close there, so checks at this pose are not evaluated",
                )
                reached = False
        # The solve weighs a loop's gap and a coupling's slip together, so a loop can close while
        # a coupling the loops do not allow slips.
        for (c, *_), slip in zip(coupled, slips()) if reached else ():
            quantity = model.quantity(c.driven)
            off = slip / size[c.driven]  # in the project's unit
            if abs(off) > p.tolerance(quantity) / p.degrees(quantity):
                p.error(
                    "loop-open",
                    f"{c.kind} {c.name} {c.law}, but with {at} {c.driven} stands {off:.4g} off "
                    "that; the loops do not allow both, so checks at this pose are not evaluated",
                )
                reached = False
        moved = set(values)  # and each joint the loops move from as built
        for name, joint in model.moving.items() if reached else ():
            quantity = model.quantity(name)
            slack = p.tolerance(quantity) / p.degrees(quantity)  # in the project's unit
            turned = float(d.qpos[m.jnt_qposadr[jid[name]]]) / size[name]
            if abs(turned) > slack:
                moved.add(name)
            if "range" not in joint or name in free:
                continue
            (low_name, low), (high_name, high) = range_ends(p, joint)
            if not low - slack <= turned <= high + slack:
                p.error(
                    "joint-range",
                    f"joint {name}: {JOINT_TYPES[joint['type']].moves} {turned:.4g} with {at}, "
                    f"outside its range {low_name} {low:g} to {high_name} {high:g}; the mechanism "
                    "cannot reach this pose, so checks at it are not evaluated",
                )
                reached = False
        if not reached:
            return None
        assembly = {}
        for inst, (part, _) in model.assembly.items():
            bid = mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_BODY, inst)
            frame = d.xmat[bid].reshape(3, 3)
            plane = Plane(
                origin=tuple(d.xpos[bid]), x_dir=tuple(frame[:, 0]), z_dir=tuple(frame[:, 2])
            )
            assembly[inst] = (part, Location(plane))
        return replace(model, assembly=assembly, moved=frozenset(moved))
