"""Which instances of an assembly hold together: whether the model is one object.

An instance is held by another where the two touch, or lie within the clearance of each other:
the gap the loosest fit leaves, a param project.yaml names. Two solids touch where they lie
within the model's length tolerance, how closely it realises any length: two gears built in mesh
are a fraction of that apart. The instances then fall into groups, each reaching its every member
through instances that hold each other, and an object that can be put together is one group. What
floats is an error under a plan, which claims the object is put together, and a warning without
one, where what holds a part may be left out of the target.

Whether two solids lie within the limit is OCC's exact distance, which takes seconds between two
gears. So each part is meshed once, and OCC's proximity test on the meshes first names the faces
of a pair that may lie that near: it reports no face of a pair that lies further apart, and the
exact distance is then computed between the faces it names alone. A group it leaves apart from
the rest is confirmed by the exact distance between whole solids, so a mesh never decides that an
instance floats.
"""

from __future__ import annotations

import importlib
import math
from collections import Counter

import numpy as np

from .build import Model
from .project import Finding, Project

# OCP's modules re-export a compiled module whose names pyright cannot see, so they are looked up
# at run time.
_OCP = {
    name: importlib.import_module(f"OCP.{name}")
    for name in (
        "BRep",
        "BRepBuilderAPI",
        "BRepClass3d",
        "BRepExtrema",
        "BRepMesh",
        "TopAbs",
        "TopExp",
        "TopoDS",
        "gp",
    )
}
# A part is meshed to this fraction of its box's diagonal.
_SAG = 1e-3


def _distance(a, b) -> float:
    return _OCP["BRepExtrema"].BRepExtrema_DistShapeShape(a, b).Value()


def _box_gaps(low: np.ndarray, high: np.ndarray) -> np.ndarray:
    """How far apart each two of the boxes lie, 0 where they meet."""
    apart = np.maximum(low[:, None, :] - high[None, :, :], low[None, :, :] - high[:, None, :])
    return np.linalg.norm(np.maximum(apart, 0.0), axis=2)


class _Placed:
    """The instances of an assembly as placed, each a meshed copy of its part's solid: the mesh
    is left off the model's own solids, which the exports mesh in their own way."""

    def __init__(self, model: Model):
        self.names = list(model.assembly)
        self.solids, self.sags, self.faces = [], [], []
        low, high = [], []
        meshed: dict[str, tuple] = {}
        for part, at in model.assembly.values():
            if part not in meshed:
                solid = model.parts[part]
                copy = _OCP["BRepBuilderAPI"].BRepBuilderAPI_Copy(solid.wrapped, True, False)
                sag: float | None = _SAG * solid.bounding_box().diagonal
                try:
                    _OCP["BRepMesh"].BRepMesh_IncrementalMesh(copy.Shape(), sag, False, 0.5, True)
                except Exception:  # noqa: BLE001 - a part too small for OCC to mesh is read exactly
                    sag = None
                meshed[part] = (copy.Shape(), sag, len(solid.faces()))
            shape, sag, faces = meshed[part]
            self.solids.append(shape.Moved(at.wrapped))
            self.sags.append(sag)
            self.faces.append(faces)
            box = model.parts[part].moved(at).bounding_box()
            low.append(tuple(box.min))
            high.append(tuple(box.max))
        self.low, self.high = np.array(low), np.array(high)
        self.gaps = _box_gaps(self.low, self.high)

    def near(self, i: int, j: int, limit: float) -> bool:
        """Whether instances i and j touch, overlap or lie within limit of each other."""
        a, b = self.solids[i], self.solids[j]
        if self.sags[i] is None or self.sags[j] is None:
            return _distance(a, b) <= limit or self._within(i, j) or self._within(j, i)
        reach = limit + 2 * (self.sags[i] + self.sags[j])
        proximity = _OCP["BRepExtrema"].BRepExtrema_ShapeProximity(a, b, reach)
        proximity.Perform()  # done or not, it names the faces it found near: none where none is
        mine = [
            proximity.GetSubShape1(k)
            for k in range(self.faces[i])
            if proximity.OverlapSubShapes1().IsBound(k)
        ]
        theirs = [
            proximity.GetSubShape2(k)
            for k in range(self.faces[j])
            if proximity.OverlapSubShapes2().IsBound(k)
        ]
        if mine and theirs:
            builder, others = _OCP["BRep"].BRep_Builder(), _OCP["TopoDS"].TopoDS_Compound()
            builder.MakeCompound(others)
            for face in theirs:
                builder.Add(others, face)
            if any(_distance(face, others) <= limit for face in mine):
                return True
        return self._within(i, j) or self._within(j, i)

    def _within(self, i: int, j: int) -> bool:
        """Whether instance i lies inside instance j's material, where no faces of the two need
        lie near: a point of i is then inside j."""
        if not (np.all(self.low[i] >= self.low[j]) and np.all(self.high[i] <= self.high[j])):
            return False
        explorer = _OCP["TopExp"].TopExp_Explorer(
            self.solids[i], _OCP["TopAbs"].TopAbs_ShapeEnum.TopAbs_VERTEX
        )
        if not explorer.More():
            return False
        point = _OCP["BRep"].BRep_Tool.Pnt_s(_OCP["TopoDS"].TopoDS.Vertex(explorer.Current()))
        classifier = _OCP["BRepClass3d"].BRepClass3d_SolidClassifier(self.solids[j], point, 1e-9)
        return classifier.State() == _OCP["TopAbs"].TopAbs_State.TopAbs_IN

    def nearest(self, group: list[int]) -> tuple[float, int, int]:
        """The least distance from a group to an instance outside it, exactly, with the member
        and the instance it lies between."""
        inside = set(group)
        pairs = sorted(
            (self.gaps[i, j], i, j)
            for i in group
            for j in range(len(self.names))
            if j not in inside
        )
        best = (math.inf, group[0], group[0])
        for gap, i, j in pairs:
            if gap >= best[0]:  # no nearer than its box
                break
            if self._within(i, j) or self._within(j, i):
                return (0.0, i, j)
            best = min(best, (_distance(self.solids[i], self.solids[j]), i, j))
        return best


def apart(model: Model, limit: float) -> list[dict]:
    """The groups of instances that hold together apart from the largest, the object: each as its
    instances, how far it lies from the nearest instance outside it, and that instance. Empty
    where every instance is held."""
    placed = _Placed(model)
    count = len(placed.names)
    group = list(range(count))

    def of(i: int) -> int:
        while group[i] != i:
            group[i] = group[group[i]]
            i = group[i]
        return i

    # The pairs whose boxes lie within the limit, the nearest first: once every instance is in
    # one group, nothing is left to compute.
    i, j = np.nonzero(np.triu(placed.gaps <= limit, 1))
    left = count
    for a, b in sorted(zip(i.tolist(), j.tolist()), key=lambda pair: placed.gaps[pair]):
        if left == 1:
            break
        if of(a) != of(b) and placed.near(a, b, limit):
            group[of(a)] = of(b)
            left -= 1
    found = []
    while True:
        members: dict[int, list[int]] = {}
        for k in range(count):
            members.setdefault(of(k), []).append(k)
        groups = sorted(members.values(), key=len, reverse=True)
        for floating in groups[1:]:
            gap, inside, outside = placed.nearest(floating)
            if gap <= limit:  # the meshes left apart two solids that hold each other
                group[of(inside)] = of(outside)
                break
            found.append(
                {
                    "instances": [placed.names[k] for k in floating],
                    "gap": gap,
                    "from": placed.names[inside],
                    "nearest": placed.names[outside],
                }
            )
        else:
            return found
        found = []


def check(p: Project, model: Model) -> dict | None:
    """[held] for each instance, or group of instances, that nothing holds to the rest: an error
    under a plan, a warning without one. What holds as the report gives it: the clearance, the
    param project.yaml names and its value, and what floats. None for a known-first project with
    no plan, whose parts may wait on what holds them."""
    if p.known_first and p.plan is None:
        return None
    limit, clearance, fit = p.length_tol, None, p.meta.get("clearance")
    if fit is not None:
        if fit not in p.values:
            p.error("held", f"clearance names {fit}, which is no param with a value")
        elif p.values[fit] < 0:
            p.error("held", f"clearance {fit} is {p.values[fit]:g}; a fit's gap is no less than 0")
        else:
            p.hold_param(fit, ("length",), "as project.yaml's clearance")
            clearance = {"from": fit, "value": p.values[fit]}
            limit += p.values[fit]
    floating = []
    # A part that is no solid has its own finding, and nothing to hold.
    if len(model.assembly) > 1 and not any(f.rule == "part-invalid" for f in p.findings):
        try:
            floating = apart(model, limit)
        except Exception as exc:  # noqa: BLE001 - OCC raises many types on a solid it cannot read
            p.error(
                "held",
                "whether the instances hold together could not be evaluated "
                f"({type(exc).__name__}: {exc})",
            )
    floating.sort(key=lambda group: -group["gap"])
    # One finding for all that floats as far from the rest: a fit left unnamed shows as one gap,
    # whatever number of instances ride on it.
    by_gap: dict[str, dict[tuple, list[dict]]] = {}
    for group in floating:
        parts = sorted(Counter(model.assembly[inst][0] for inst in group["instances"]).items())
        by_gap.setdefault(f"{group['gap']:.4g}", {}).setdefault(tuple(parts), []).append(group)
    for gap, alike in by_gap.items():
        said = []
        for parts, groups in alike.items():
            first, more = groups[0], ", …" * (len(groups) > 1)
            between = f"{first['from']} from {first['nearest']}"
            if len(first["instances"]) > 1:
                count = f"{len(groups)} groups of " * (len(groups) > 1)
                between = f"touching only each other, {between}"
                said.append(f"{count}{len(first['instances'])} instances ({between}{more})")
            elif len(groups) > 1:
                said.append(f"{parts[0][0]} ×{len(groups)} ({between}{more})")
            else:
                said.append(f"{first['instances'][0]} (from {first['nearest']})")
        more = f"; and {len(said) - 3} more kinds" * (len(said) > 3)
        p.findings.append(
            Finding(
                "warning" if p.plan is None else "error",
                "held",
                f"{gap} {p.units['length']} from the nearest instance, and held by nothing: "
                f"{'; '.join(said[:3])}{more}. An instance sits on what holds it, or within "
                "project.yaml's clearance of it",
            )
        )
    return {"clearance": clearance, "floating": floating}
