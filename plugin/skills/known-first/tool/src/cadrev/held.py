"""Which instances of an assembly hold together, as a plan's steps must leave them.

An instance is held by another where the two touch, or lie within a limit of each other: the gap
a fit leaves. The instances then fall into groups, each reaching its every member through
instances that hold each other, and an object that can be put together is one group.

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

import numpy as np

from .build import Model

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
                sag = _SAG * solid.bounding_box().diagonal
                _OCP["BRepMesh"].BRepMesh_IncrementalMesh(copy.Shape(), sag, False, 0.5, True)
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
