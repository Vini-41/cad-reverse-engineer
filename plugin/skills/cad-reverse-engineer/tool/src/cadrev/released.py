"""Geometry the authors released (ADR-0011): its bodies, and the geometry a probe or a shape
check reads from them, with the datum geometry built parts share: where a datum lies on a solid,
and the distances and angles between datums."""

from __future__ import annotations

import importlib
import math
import re
from functools import cache
from pathlib import Path

from . import sources

# The file formats a cut file is read from: a laser-cut sheet, whose bodies are its regions.
SHEET_FORMATS = {".svg"}
# A length an SVG gives in no physical unit is in CSS pixels, 96 to the inch.
_PX_PER_INCH = 96
_MM_PER_PX = 25.4 / _PX_PER_INCH
# A region of a cut file named by a point inside it: <source>@<x>,<y> on the sheet.
_NUMBER = r"[-+]?(?:\d+\.?\d*|\.\d+)"
_AT = re.compile(rf"(?P<source>[^@]+)@\s*(?P<x>{_NUMBER})\s*,\s*(?P<y>{_NUMBER})")
# For a projection along each axis, the axes a point's sheet x and y and the projection axis
# are, in turn: a rotation carrying the axis onto z.
_TURNS = {"x": (1, 2, 0), "y": (2, 0, 1), "z": (0, 1, 2)}
# How finely inner_point searches a region's bbox for a point to name it by (a grid of n × n).
_GRID = 24
# How finely a shape check samples each face (an n × n grid of its parameters) and each edge.
SAMPLES = 8
# How finely off_solid samples each edge of a cylindrical face to find the face's axial extent.
_EDGE_SAMPLES = 16
# How far apart, in millimetres, two triangle corners of an STL may be and still be sewn as one:
# a released mesh rounds its corners to float32, a step of 7.6e-6 mm at 80 mm (#129).
_SEWING_TOL = 1e-4


def _step_solids(path: Path) -> list:
    """The solids of the STEP at path, in file order, in millimetres."""
    from build123d import import_step

    return import_step(str(path)).solids()


def _stl_solids(path: Path) -> list:
    """The solids of the STL at path, in file order, in millimetres: its triangles sewn into
    closed shells, each one solid of flat faces. Raises where the file holds no triangle, or a
    shell does not close."""
    from build123d import Shell, Solid
    from build123d.topology import Shape

    # OCP's modules re-export a compiled module whose names pyright cannot see, so they are
    # looked up at run time.
    ocp = {name: importlib.import_module(f"OCP.{name}") for name in ("BRepBuilderAPI", "StlAPI")}
    mesh = importlib.import_module("OCP.TopoDS").TopoDS_Shape()
    if not ocp["StlAPI"].StlAPI_Reader().Read(mesh, str(path)) or mesh.IsNull():
        raise ValueError("the file holds no triangle")
    sewing = ocp["BRepBuilderAPI"].BRepBuilderAPI_Sewing(_SEWING_TOL)
    sewing.Add(mesh)
    sewing.Perform()
    sewn = Shape.cast(sewing.SewedShape())
    shells = [sewn] if isinstance(sewn, Shell) else list(sewn.shells())
    if not shells or not all(s.is_manifold for s in shells):
        raise ValueError("the mesh does not close into solids")
    return [Solid(s) for s in shells]


# The file formats a geometry source is read from, each with its reader.
GEOMETRY_FORMATS = {".step": _step_solids, ".stp": _step_solids, ".stl": _stl_solids}


@cache
def _solids(path: Path, digest: str, scale: float) -> tuple:
    """The solids of the geometry file at path, in file order, scaled from millimetres, which
    the readers give, to the project's length unit; digest keys the cache to the file's content."""
    del digest
    solids = GEOMETRY_FORMATS[path.suffix.lower()](path)
    return tuple(s if scale == 1 else s.scale(scale) for s in solids)


def solids(path: Path, scale: float) -> tuple:
    """The solids of the geometry source at path, in file order, in the project's length unit
    (scale project units to a millimetre). Raises when the file cannot be read as STEP or STL."""
    if path.suffix.lower() not in GEOMETRY_FORMATS:
        raise ValueError(
            f"a geometry source is read as STEP or STL ({', '.join(sorted(GEOMETRY_FORMATS))}), "
            f"or as a cut file ({', '.join(sorted(SHEET_FORMATS))})"
        )
    found = _solids(path.resolve(), sources.sha256(path), scale)
    if not found:
        raise ValueError("the file holds no solid")
    return found


def is_sheet(path: Path) -> bool:
    """Whether the geometry source at path is a cut file, whose bodies are regions of a sheet."""
    return path.suffix.lower() in SHEET_FORMATS


@cache
def _regions(path: Path, digest: str, scale: float) -> tuple:
    """The regions of the cut file at path (regions), keyed to its content by digest."""
    import svgelements
    from build123d import Face, Wire
    from ocpsvg.svg import wires_from_svg_element

    del digest
    # svgelements applies the viewBox and every transform, reading lengths in CSS pixels.
    drawing = svgelements.SVG.parse(str(path), ppi=_PX_PER_INCH)
    contours = [
        Wire(wire).scale(_MM_PER_PX * scale)
        for element in drawing.elements()
        if isinstance(element, svgelements.Shape)
        for wire in wires_from_svg_element(element)
    ]
    contours = [w for w in contours if w.is_closed]
    filled = [Face(w) for w in contours]
    areas = [f.area for f in filled]
    boxes = [f.bounding_box() for f in filled]
    # Each contour lies inside those that enclose it; one inside an even number bounds a region
    # (its outer contour), one inside an odd number a hole of the smallest that encloses it. A
    # contour can only lie inside one whose bbox holds its own, which rules out most pairs cheaply.
    within = [
        [
            j
            for j, f in enumerate(filled)
            if areas[j] > areas[i] and _holds(boxes[j], boxes[i]) and _encloses(f, w)
        ]
        for i, w in enumerate(contours)
    ]
    out = []
    for i, outer in enumerate(contours):
        if len(within[i]) % 2:
            continue
        holes = [
            contours[j]
            for j in range(len(contours))
            if len(within[j]) == len(within[i]) + 1 and min(within[j], key=areas.__getitem__) == i
        ]
        out.append(Face(outer, holes))
    return tuple(out)


def _holds(outer, inner) -> bool:
    """Whether bbox outer holds bbox inner in the sheet's plane, within 1e-6."""
    return (
        outer.min.X <= inner.min.X + 1e-6
        and outer.min.Y <= inner.min.Y + 1e-6
        and outer.max.X >= inner.max.X - 1e-6
        and outer.max.Y >= inner.max.Y - 1e-6
    )


def _encloses(filled, contour) -> bool:
    """Whether contour lies inside the filled contour filled: no point of it outside, and some
    point off its edge, so two contours that share an edge enclose neither."""
    points = [contour.position_at(i / SAMPLES) for i in range(SAMPLES)]
    edge = filled.outer_wire()
    return all(filled.is_inside(at) for at in points) and any(
        edge.distance_to(at) > 1e-6 for at in points
    )


def regions(path: Path, scale: float) -> tuple:
    """The regions of the cut file at path, each one filled region (an outer contour plus its
    holes) as a face in the sheet's frame: from the page's top-left corner, x right and y down,
    at the scale the file declares with its transforms applied, in the project's length unit
    (scale project units to a millimetre). Raises when the file cannot be read as SVG or draws
    no closed contour."""
    found = _regions(path.resolve(), sources.sha256(path), scale)
    if not found:
        raise ValueError("the file draws no closed contour")
    return found


def at_point(name: str) -> tuple[str, tuple[float, float]] | None:
    """The source and point a body name gives as <source>@<x>,<y>: a region of a cut file named by
    a point inside it; None for any other name."""
    named = _AT.fullmatch(name)
    if named is None:
        return None
    return named["source"], (float(named["x"]), float(named["y"]))


def point_name(source_id: str, point: tuple[float, float]) -> str:
    """The body name of the region of cut file source_id with point inside it (at_point)."""
    return f"{source_id}@{point[0]:g},{point[1]:g}"


def regions_at(found: tuple, point: tuple[float, float], tol: float) -> list[int]:
    """The indices of the regions in found that point lies inside, or within tol of."""
    from build123d import Vector

    at = Vector(point[0], point[1], 0)
    return [i for i, region in enumerate(found) if region.distance_to(at) <= tol]


def regions_within(found: tuple, rectangle, tol: float) -> list[int]:
    """The indices of the regions in found that lie wholly inside rectangle, given by its least
    and greatest corner, or within tol of it."""
    (x0, y0), (x1, y1) = rectangle
    out = []
    for i, region in enumerate(found):
        box = region.bounding_box()
        if box.min.X >= x0 - tol and box.min.Y >= y0 - tol:
            if box.max.X <= x1 + tol and box.max.Y <= y1 + tol:
                out.append(i)
    return out


def outlines_at(found: tuple, point: tuple[float, float], tol: float) -> list[int]:
    """The indices of the regions in found whose outer contour point lies inside, or within tol
    of: on the region or in one of its holes."""
    from build123d import Face, Vector

    at = Vector(point[0], point[1], 0)
    return [i for i, r in enumerate(found) if Face(r.outer_wire()).distance_to(at) <= tol]


def inner_point(region) -> tuple[float, float]:
    """A point well inside region, to name it by: of a grid over its bbox, the one inside it
    farthest from its edges, rounded to 0.01."""
    from build123d import Compound, Vector

    box, edges = region.bounding_box(), Compound(region.edges())
    best, deepest = (round(box.center().X, 2), round(box.center().Y, 2)), -1.0
    for i in range(1, _GRID):
        for j in range(1, _GRID):
            x = round(box.min.X + box.size.X * i / _GRID, 2)
            y = round(box.min.Y + box.size.Y * j / _GRID, 2)
            at = Vector(x, y, 0)
            if region.distance_to(at) > 0:
                continue
            depth = edges.distance_to(at)
            if depth > deepest:
                best, deepest = (x, y), depth
    return best


def source_of(body: str) -> str:
    """The geometry source a body name (body_names) is of."""
    return body.rpartition("#")[0] if re.fullmatch(r".+#[1-9]\d*", body) else body


def body_names(source_id: str, count: int) -> list[str]:
    """The names of a geometry source's bodies: its id for its one body, else <source>#<n> in
    file order from 1."""
    return [source_id] if count == 1 else [f"{source_id}#{n}" for n in range(1, count + 1)]


def off_solid(part, point: tuple[float, float, float], tol: float) -> float | None:
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


def diameters_at(shape, point: tuple[float, float, float], tol: float) -> list[float]:
    """The diameters of the cylindrical faces of shape that point lies on within tol, each once
    (two within tol of each other are one), smallest first: none for a point on no cylindrical
    face, several for one on the edge where two meet."""
    from build123d import GeomType, Vector

    surface_of = importlib.import_module("OCP.BRepAdaptor").BRepAdaptor_Surface
    at = Vector(*point)
    found: list[float] = []
    for face in shape.faces():
        if face.geom_type == GeomType.CYLINDER and face.distance_to(at) <= tol:
            # OCC's surface adaptor sees through a trim, where build123d's face.radius is None.
            diameter = 2 * surface_of(face.wrapped).Cylinder().Radius()
            if all(abs(diameter - d) > tol for d in found):
                found.append(diameter)
    return sorted(found)


def diameter_at(shape, point: tuple[float, float, float], tol: float) -> float | str:
    """The diameter of the one cylindrical face of shape that point lies on within tol
    (diameters_at), else where point lies instead: on no cylindrical face, or on the edge of
    several."""
    found = diameters_at(shape, point, tol)
    if len(found) == 1:
        return found[0]
    if not found:
        return "no cylindrical face"
    return "the edge of cylindrical faces of diameters " + " and ".join(f"{d:.4g}" for d in found)


def datum_distance(a, b, along: str | None = None) -> float:
    """The distance between two datums' points, along the axis x, y or z where along names one."""
    if along is None:
        return math.dist(a, b)
    i = "xyz".index(along)
    return abs(a[i] - b[i])


def angle_at(a, vertex, b, tol: float) -> float | None:
    """The angle in degrees at vertex from the direction to a to that to b; None where a or b lies
    within tol of vertex, which leaves it undefined."""
    u, w = ([x - v for x, v in zip(end, vertex)] for end in (a, b))
    if min(math.hypot(*u), math.hypot(*w)) <= tol:
        return None
    cross = (u[1] * w[2] - u[2] * w[1], u[2] * w[0] - u[0] * w[2], u[0] * w[1] - u[1] * w[0])
    return math.degrees(math.atan2(math.hypot(*cross), sum(x * y for x, y in zip(u, w))))


def collinear(points: list[tuple[float, float, float]], tol: float) -> bool:
    """Whether points all lie within tol of one line, or of one point."""
    if not points:
        return True
    a = points[0]
    b = max(points, key=lambda q: math.dist(a, q))
    span = math.dist(a, b)
    if span <= tol:
        return True
    u = [(y - x) / span for x, y in zip(a, b)]
    for q in points:
        w = [y - x for x, y in zip(a, q)]
        along = sum(x * y for x, y in zip(w, u))
        if math.dist(w, [along * x for x in u]) > tol:
            return False
    return True


def fit(ours: list, theirs: list) -> tuple[object, float, int]:
    """The rigid motion (a build123d Location, no mirroring) that best carries the points ours onto
    the points theirs, pair by pair, with the largest distance it leaves between a pair and the
    index of that pair."""
    import numpy as np
    from build123d import Location, Plane

    p, q = np.asarray(ours, float), np.asarray(theirs, float)
    cp, cq = p.mean(axis=0), q.mean(axis=0)
    u, _, vt = np.linalg.svd((p - cp).T @ (q - cq))
    turn = np.diag([1.0, 1.0, float(np.sign(np.linalg.det(vt.T @ u.T)))])
    rotation = vt.T @ turn @ u.T
    shift = cq - rotation @ cp
    left = np.linalg.norm(p @ rotation.T + shift - q, axis=1)
    # The plane whose axes are the rotation's columns maps a point p to shift + rotation · p.
    axes = [tuple(float(v) for v in rotation[:, i]) for i in (0, 2)]
    where = Location(Plane(origin=tuple(float(v) for v in shift), x_dir=axes[0], z_dir=axes[1]))
    worst = int(np.argmax(left))
    return where, float(left[worst]), worst


def projected(point: tuple[float, float, float], along: str) -> tuple[float, float, float]:
    """Where point projects along the axis x, y or z onto the plane of a cut file's sheet (z 0),
    the other two axes in turn as its x and y."""
    i, j, _ = _TURNS[along]
    return point[i], point[j], 0.0


def outline(part, along: str):
    """part's outline projected along the axis x, y or z onto the plane of a cut file's sheet, as
    projected maps a point: the union of its plane faces square to that axis, as a cut part's
    are. Raises where it has none."""
    from build123d import GeomType, Location, Plane, Vector

    turn = [[1.0 if k == i else 0.0 for k in range(3)] for i in _TURNS[along]]
    columns = [tuple(row[c] for row in turn) for c in (0, 2)]
    turned = part.moved(Location(Plane(origin=(0, 0, 0), x_dir=columns[0], z_dir=columns[1])))
    across = [
        face.moved(Location((0, 0, -face.center().Z)))
        for face in turned.faces()
        if face.geom_type == GeomType.PLANE
        and abs(abs(face.normal_at().dot(Vector(0, 0, 1))) - 1) < 1e-9
    ]
    if not across:
        raise ValueError(f"the part has no plane face square to {along}, so no outline along it")
    found = across[0]
    for face in across[1:]:
        found = found.fuse(face)
    return found.clean()


def outline_distance(a, b) -> tuple[float, tuple[float, float]]:
    """The largest distance from a point on either outline's edges to the other's edges, sampled
    along each edge, and the point on the sheet where it occurs."""
    from build123d import Compound

    worst: tuple[float, tuple[float, float]] = (0.0, (0.0, 0.0))
    for ours, theirs in ((a, b), (b, a)):
        edges = Compound(theirs.edges())
        for edge in ours.edges():
            for i in range(SAMPLES + 1):
                point = edge.position_at(i / SAMPLES)
                gap = edges.distance_to(point)
                if gap > worst[0]:
                    worst = (gap, (point.X, point.Y))
    return worst


def surface_distance(a, b) -> tuple[float, tuple[float, float, float]]:
    """The largest distance from a point on either shape's surface to the other's surface, as
    sampled (an SAMPLES × SAMPLES grid over each face's parameters, kept where it falls on the face
    rather than in a hole of it, and points along each edge), and the point where it occurs."""
    from . import distance

    return distance.surface_distance(a, b, SAMPLES)
