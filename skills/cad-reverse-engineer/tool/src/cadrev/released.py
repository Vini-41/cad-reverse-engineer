"""Geometry the authors released (ADR-0011): its bodies, and the geometry a probe or a shape
check reads from them, with the datum geometry built parts share: where a datum lies on a solid,
and the distances and angles between datums."""

from __future__ import annotations

import math
import re
from functools import cache
from pathlib import Path

from . import sources

# The file formats a geometry source is read from.
GEOMETRY_FORMATS = {".step", ".stp"}
# How finely a shape check samples each face (an n × n grid of its parameters) and each edge.
SAMPLES = 8
# How finely off_solid samples each edge of a cylindrical face to find the face's axial extent.
_EDGE_SAMPLES = 16


@cache
def _solids(path: Path, digest: str, scale: float) -> tuple:
    """The solids of the STEP at path, in file order, scaled from millimetres, which the reader
    gives, to the project's length unit; digest keys the cache to the file's content."""
    from build123d import import_step

    del digest
    solids = import_step(str(path)).solids()
    return tuple(s if scale == 1 else s.scale(scale) for s in solids)


def solids(path: Path, scale: float) -> tuple:
    """The solids of the geometry source at path, in file order, in the project's length unit
    (scale project units to a millimetre). Raises when the file cannot be read as STEP."""
    if path.suffix.lower() not in GEOMETRY_FORMATS:
        raise ValueError(
            f"a geometry source is read as STEP ({', '.join(sorted(GEOMETRY_FORMATS))})"
        )
    found = _solids(path.resolve(), sources.sha256(path), scale)
    if not found:
        raise ValueError("the file holds no solid")
    return found


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


def _samples(shape) -> list:
    """Points on shape's surface: an SAMPLES × SAMPLES grid over each face's parameters, kept where
    it falls on the face rather than in a hole of it, and points along each edge."""
    points = []
    for face in shape.faces():
        for i in range(SAMPLES + 1):
            for j in range(SAMPLES + 1):
                point = face.position_at(i / SAMPLES, j / SAMPLES)
                if face.distance_to(point) <= 1e-7:
                    points.append(point)
    for edge in shape.edges():
        points += [edge.position_at(i / SAMPLES) for i in range(SAMPLES + 1)]
    return points


def surface_distance(a, b) -> tuple[float, tuple[float, float, float]]:
    """The largest distance from a point on either shape's surface to the other's surface, as
    sampled (_samples), and the point where it occurs."""
    from build123d import Compound

    worst: tuple[float, tuple[float, float, float]] = (0.0, (0.0, 0.0, 0.0))
    for points, other in ((_samples(a), b), (_samples(b), a)):
        surface = Compound(other.faces())
        for point in points:
            gap = surface.distance_to(point)
            if gap > worst[0]:
                worst = (gap, (point.X, point.Y, point.Z))
    return worst
