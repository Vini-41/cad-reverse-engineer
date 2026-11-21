"""How far apart two shapes' surfaces lie, as a shape check evaluates it: the largest distance from
a sample point on either surface to the other. A mesh body has hundreds of thousands of sample
points. A point's distance to a flat surface, whose faces are all plane faces bounded by lines
(an STL body's triangles, or faces merged from them), is its distance to the nearest of the
triangles those faces are exactly made of, which numpy computes. To any other surface OCC computes
it, and since almost every point lies far closer than the largest distance, numpy first bounds
each point's distance from above, and OCC computes the distance of only the points whose bound
reaches the largest distance yet found: the result computing every point's distance gives. Flat
triangles, plane faces bounded by lines and circles, and cylinder, cone and torus faces give a
bound, a cut one only where the point's nearest point on it is on the face; a point near only
other faces, or over a cut face's hole, is left to OCC. A file may give an edge, where two faces
meet, by a curve that strays from them within the edge's BRep tolerance; such an edge is read
where its faces meet, so its sample points are moved there, and a point near it is read against
its faces."""

from __future__ import annotations

import importlib
import math
from typing import Literal, NamedTuple

import numpy as np

# OCP's modules re-export a compiled module whose names pyright cannot see, so they are looked up
# at run time.
_OCP = {
    name: importlib.import_module(f"OCP.{name}")
    for name in (
        "BRep",
        "BRepAdaptor",
        "IntTools",
        "BRepTools",
        "GeomAbs",
        "GeomAPI",
        "ShapeAnalysis",
        "TopAbs",
        "TopExp",
        "TopoDS",
        "gp",
    )
}
_LINE = _OCP["GeomAbs"].GeomAbs_CurveType.GeomAbs_Line
_CIRCLE = _OCP["GeomAbs"].GeomAbs_CurveType.GeomAbs_Circle
_PLANE = _OCP["GeomAbs"].GeomAbs_SurfaceType.GeomAbs_Plane
_CYLINDER = _OCP["GeomAbs"].GeomAbs_SurfaceType.GeomAbs_Cylinder
_CONE = _OCP["GeomAbs"].GeomAbs_SurfaceType.GeomAbs_Cone
_TORUS = _OCP["GeomAbs"].GeomAbs_SurfaceType.GeomAbs_Torus
# The kinds of curve a file approximates an edge by, where its faces meet in no line or conic.
_FREE_FORM = (
    _OCP["GeomAbs"].GeomAbs_CurveType.GeomAbs_BezierCurve,
    _OCP["GeomAbs"].GeomAbs_CurveType.GeomAbs_BSplineCurve,
    _OCP["GeomAbs"].GeomAbs_CurveType.GeomAbs_OffsetCurve,
    _OCP["GeomAbs"].GeomAbs_CurveType.GeomAbs_OtherCurve,
)
_IN = _OCP["TopAbs"].TopAbs_State.TopAbs_IN
_ON = _OCP["TopAbs"].TopAbs_State.TopAbs_ON
# How far from its face a grid point may lie and still be on it.
_ON_FACE = 1e-7
# How far from its triangle, in numpy, a grid point may lie and still be kept: well past _ON_FACE,
# so rounding never drops one that OCC keeps.
_NEAR_FACE = 1e-6
# How far apart two values of a face's parameter may lie and still be counted as one.
_SAME_PARAMETER = 1e-9
# How close two corners of a triangle may be and still be counted as two.
_SAME_CORNER = 1e-9
# How far numpy's rounding may leave a bound below OCC's distance, per unit of the shapes' size.
_ROUNDING = 1e-9
# How many times, at most, a sample on an edge is projected onto each of its faces' surfaces in
# turn, to find where they meet.
_ROUNDS = 50
# How many times a shape's tolerance OCC's distance to it may stray from numpy's: over three
# times was seen on a STEP body, so a bound allows ten.
_TOLERANCES = 10
# How many points the triangles' bound takes at once, against every triangle.
_CHUNK = 64


def surface_distance(a, b, samples: int) -> tuple[float, tuple[float, float, float], bool]:
    """The largest distance from a point on either shape's surface to the other's surface, the
    point where it occurs, and whether that point is on b's: of the points an samples × samples
    grid over each face's parameters gives, where they fall on the face rather than in a hole of
    it, and those samples + 1 along each edge, a's then b's, the first point farthest from the
    other surface."""
    surfaces = (_Surface(a, samples), _Surface(b, samples))
    boxes = [s.bounding_box() for s in (a, b)]
    size = max(abs(v) for box in boxes for corner in (box.min, box.max) for v in corner)
    slack = _ROUNDING * max(1.0, size)
    first = len(surfaces[0].points)
    worst: tuple[float, tuple[float, float, float]] = (0.0, (0.0, 0.0, 0.0))
    found = -1
    sides = list(enumerate(zip((s.points for s in surfaces), reversed(surfaces))))
    bounds = [np.full(len(points), -np.inf) for _, (points, _) in sides]
    # Every point's distance to a flat surface first, exactly; a grid point off its own triangle
    # has none. The other side's bounds then need only tell which points could reach the largest.
    for k, (points, other) in sides:
        if other.mesh is None:
            continue
        gaps = np.where(surfaces[k].on_face, _triangles_bound(points, other.mesh), -np.inf)
        if len(gaps) and gaps.max() > worst[0]:
            n = int(np.argmax(gaps))
            x, y, z = (float(v) for v in points[n])
            worst, found = (float(gaps[n]), (x, y, z)), n + k * first
    for k, (points, other) in sides:
        if other.mesh is None:
            bounds[k] = _bound(points, other, slack, worst[0])
    bounds = np.concatenate(bounds)
    # From the highest bound down, until no bound left can reach the largest distance found.
    for n in np.argsort(-bounds, kind="stable"):
        if bounds[n] < worst[0]:
            break
        k = int(n >= first)
        point = surfaces[k].point(int(n) - k * first)
        if point is None:
            continue
        gap = surfaces[1 - k].distance_to(point)
        # Of points equally far, the first in order, as computing every point's in turn finds.
        if gap > worst[0] or (gap == worst[0] > 0 and n < found):
            worst, found = (gap, (point.X, point.Y, point.Z)), n
    return (*worst, found >= first)


def _xyz(p) -> tuple[float, float, float]:
    return p.X(), p.Y(), p.Z()


def _curve(edge):
    """edge's curve, as OCC adapts it, with its kind and its two ends as arrays."""
    curve = _OCP["BRepAdaptor"].BRepAdaptor_Curve(edge)
    ends = (curve.Value(curve.FirstParameter()), curve.Value(curve.LastParameter()))
    return curve, curve.GetType(), *(np.array(_xyz(p)) for p in ends)


def _vertices(edge) -> tuple[np.ndarray, np.ndarray]:
    """edge's two vertices: its ends as the edges that share one give them, alike to the bit."""
    first, last = (
        _OCP["TopExp"].TopExp.FirstVertex_s(edge),
        _OCP["TopExp"].TopExp.LastVertex_s(edge),
    )
    point = _OCP["BRep"].BRep_Tool.Pnt_s
    return np.array(_xyz(point(first))), np.array(_xyz(point(last)))


def _edges(shape) -> list:
    """The edges of shape (a TopoDS shape), in its wires' order."""
    explorer = _OCP["TopExp"].TopExp_Explorer(shape, _OCP["TopAbs"].TopAbs_ShapeEnum.TopAbs_EDGE)
    out = []
    while explorer.More():
        out.append(_OCP["TopoDS"].TopoDS.Edge(explorer.Current()))
        explorer.Next()
    return out


def _triangle(face, kind):
    """The corners of face, an array of three, where it is a flat triangle: a plane face bounded
    by three lines. None otherwise."""
    if kind != _PLANE:
        return None
    edges = _edges(face.wrapped)
    if len(edges) != 3:
        return None
    ends = []
    for edge in edges:
        if _OCP["BRepAdaptor"].BRepAdaptor_Curve(edge).GetType() != _LINE:
            return None
        ends += [tuple(v) for v in _vertices(edge)]
    corners = ends[:1]
    for end in ends[1:]:
        if all(math.dist(end, c) > _SAME_CORNER for c in corners):
            corners.append(end)
    return np.array(corners) if len(corners) == 3 else None


class _Surface:
    """A shape's surface, read once: its faces and edges, each flat triangle's corners, its loose
    edges, and its sample points (surface_distance), numpy's where it can compute them, in order;
    and a point's distance to it."""

    def __init__(self, shape, samples: int):
        from build123d import Compound

        self.shape, self.samples = shape, samples
        self.faces, self.edges = shape.faces(), shape.edges()
        self._faces = Compound(self.faces)
        self._adapted = [_OCP["BRepAdaptor"].BRepAdaptor_Surface(f.wrapped) for f in self.faces]
        self.kinds = [a.GetType() for a in self._adapted]
        self.triangles = [_triangle(f, kind) for f, kind in zip(self.faces, self.kinds)]
        self.mesh = self._mesh()
        self._loose = self._loose_edges()
        self.points, self._places, self._given, own_distance = self._sample()
        # Whether each point lies on its face: numpy settles a grid point near its triangle, and
        # OCC (point) the few that lie farther, as it does where numpy bounds the distance.
        self.on_face = own_distance <= _ON_FACE
        for n in np.flatnonzero(~self.on_face):
            self.on_face[n] = self.point(int(n)) is not None
        # How far the faces' bounds may stray from where OCC puts them: a vertex or an edge
        # holds within its tolerance.
        self.tolerance = (
            _OCP["ShapeAnalysis"].ShapeAnalysis_ShapeTolerance().Tolerance(shape.wrapped, 1)
        )

    def _mesh(self) -> np.ndarray | None:
        """The triangles (n × 3 × 3) the surface is exactly made of, where it is flat: every face a
        plane face bounded by lines, as a mesh's triangles and the faces merged from them are,
        each split along its own corners. None for any other surface."""
        out = []
        for face, kind, corners in zip(self.faces, self.kinds, self.triangles):
            if corners is not None:
                out.append(corners[None])
                continue
            if kind != _PLANE or any(_curve(e)[1] != _LINE for e in _edges(face.wrapped)):
                return None
            # A flat face's triangulation has only its corners as vertices, so it covers the face
            # exactly, whatever the tolerance.
            vertices, triangles = face.tessellate(1.0)
            out.append(np.array([tuple(v) for v in vertices])[np.array(triangles)])
        return np.concatenate(out) if out else None

    def _loose_edges(self) -> dict[int, tuple[float, list]]:
        """Each loose edge's BRep tolerance and the faces it bounds, with their surfaces, by the
        edge's index. An edge is loose where its file approximates where its faces meet by a
        free-form curve, which its tolerance lets stray from them farther than _ON_FACE, as
        another CAD's intersection curve can. Where the faces meet, not its curve, is the edge."""
        out: dict[int, tuple[float, list]] = {}
        for e, edge in enumerate(self.edges):
            tolerance = _OCP["BRep"].BRep_Tool.Tolerance_s(edge.wrapped)
            if tolerance > _ON_FACE and _curve(edge.wrapped)[1] in _FREE_FORM:
                out[e] = (tolerance, [])
        if not out:
            return out
        index = {self.edges[e]: e for e in out}
        for face in self.faces:
            for edge in face.edges():
                if edge in index:
                    surface = _OCP["BRep"].BRep_Tool.Surface_s(face.wrapped)
                    out[index[edge]][1].append((face, surface))
        return out

    def _sample(self):
        """The sample points, each with its place: (face, i, j) for a triangle's grid point,
        (-1, n) for the n-th point OCC gave, (-2, edge, i) for a line's i-th point; and each
        one's distance from its triangle as numpy finds it, 0 where it has none."""
        s = self.samples
        steps = np.arange(s + 1) / s
        grid = np.array([(u, v) for u in steps for v in steps])
        blocks, places, given = [], [], []
        triangles = []  # each grid point's triangle, NaN for a point OCC gave
        for f, face in enumerate(self.faces):
            corners = self.triangles[f]
            if corners is None:
                for i in range(s + 1):
                    for j in range(s + 1):
                        point = face.position_at(i / s, j / s)
                        if face.distance_to(point) <= _ON_FACE:
                            places.append((-1, len(given)))
                            given.append(point)
                            blocks.append(np.array([tuple(point)]))
                            triangles.append(np.full((1, 3, 3), np.nan))
                continue
            # A plane's point is affine in its parameters, which position_at spans over their
            # bounds.
            u0, u1, v0, v1 = _OCP["BRepTools"].BRepTools.UVBounds_s(face.wrapped)
            at = self._adapted[f].Value
            o, u, v = (np.array(_xyz(at(*uv))) for uv in ((u0, v0), (u1, v0), (u0, v1)))
            blocks.append(o + grid[:, :1] * (u - o) + grid[:, 1:] * (v - o))
            places += [(f, i, j) for i in range(s + 1) for j in range(s + 1)]
            triangles.append(np.broadcast_to(corners, (len(grid), 3, 3)))
        for e, edge in enumerate(self.edges):
            _, kind, start, end = _curve(edge.wrapped)
            if kind == _LINE:
                blocks.append(start + steps[:, None] * (end - start))
                places += [(-2, e, i) for i in range(s + 1)]
            else:
                along = [edge.position_at(i / s) for i in range(s + 1)]
                if e in self._loose:
                    meeting = [surface for _, surface in self._loose[e][1]]
                    along = [_meet(p, meeting) for p in along]
                places += [(-1, len(given) + i) for i in range(s + 1)]
                given += along
                blocks.append(np.array([tuple(p) for p in along]))
            triangles.append(np.full((len(blocks[-1]), 3, 3), np.nan))
        if not blocks:
            return np.zeros((0, 3)), [], given, np.zeros(0)
        points, corners = np.concatenate(blocks), np.concatenate(triangles)
        # A triangle's grid point that numpy finds off it is off it; OCC tests the rest (point).
        gridded = ~np.isnan(corners[:, 0, 0])
        own_distance = np.zeros(len(points))
        near = corners[gridded]
        own_distance[gridded] = _triangle_distance(points[gridded], *near.transpose(1, 0, 2))
        off = own_distance > _NEAR_FACE
        places = [p for p, o in zip(places, off) if not o]
        return points[~off], places, given, own_distance[~off]

    def distance_to(self, point) -> float:
        """point's distance to the surface, as OCC computes it, unless a loose edge
        (_loose_edges) lies as near: OCC takes the edge's curve, so the point's distance is then
        also read to each face of the edge, at its nearest point on the face's surface where that
        lies within the edge's tolerance of the face."""
        gap = self._faces.distance_to(point)
        for e, (tolerance, faces) in self._loose.items():
            if gap <= _ON_FACE or self.edges[e].distance_to(point) > gap + _ON_FACE:
                continue
            for face, surface in faces:
                found = _onto(point, surface)
                if found and face.distance_to(_xyz(found.NearestPoint())) <= tolerance + _ON_FACE:
                    gap = min(gap, found.LowerDistance())
        return gap

    def point(self, n: int):
        """The n-th sample point as OCC gives it, or None where it falls off its face."""
        place = self._places[n]
        if place[0] == -1:
            return self._given[place[1]]
        s = self.samples
        if place[0] == -2:
            return self.edges[place[1]].position_at(place[2] / s)
        face = self.faces[place[0]]
        point = face.position_at(place[1] / s, place[2] / s)
        return point if face.distance_to(point) <= _ON_FACE else None


def _onto(point, surface):
    """OCC's projection of point onto surface, or None where it finds none."""
    found = _OCP["GeomAPI"].GeomAPI_ProjectPointOnSurf(_OCP["gp"].gp_Pnt(*point), surface)
    return found if found.NbPoints() else None


def _meet(point, surfaces):
    """The point near point where surfaces meet, found by projecting it onto each in turn until a
    turn moves it no farther than _ON_FACE; after _ROUNDS turns, where it last lies. point itself
    where a surface has no point nearest it."""
    from build123d import Vector

    at = tuple(point)
    for _ in range(_ROUNDS):
        moved = 0.0
        for surface in surfaces:
            found = _onto(at, surface)
            if found is None:
                return point
            at, moved = _xyz(found.NearestPoint()), max(moved, found.LowerDistance())
        if moved <= _ON_FACE:
            break
    return Vector(*at)


def _bound(points: np.ndarray, surface: _Surface, slack: float, need: float) -> np.ndarray:
    """An upper bound on each point's distance to surface: its distance to a point on a flat
    triangle, a plane face bounded by lines and circles, or a cylinder, cone or torus face of it,
    whichever is nearest, plus slack for rounding and for surface's tolerance, within which OCC's
    distance strays, and its sample points moved onto where a loose edge's faces meet. B-spline
    and other faces give no bound, nor does a plane face with other edges, nor a cut cylinder,
    cone or torus face where the point's nearest point on its surface falls in a hole: a point
    near only those is bounded by the others, however far, and so left to OCC. A point whose
    bound already lies below need, a distance already found, can never reach OCC, so the costly
    bounds, the lines' and the cut faces', leave it as it is."""
    extra = slack + _TOLERANCES * surface.tolerance
    # First each point's distance to the nearest of surface's own sample points, which lie on it:
    # a bound that settles most points at once, so the faces bound only the rest.
    settled = _samples_bound(points, surface)
    rest = np.flatnonzero(settled + extra >= need)
    if len(rest):
        settled[rest] = _faces_bound(points[rest], surface, settled[rest], extra, need)
    return settled + extra


def _samples_bound(points: np.ndarray, surface: _Surface) -> np.ndarray:
    """Each point's distance to the nearest of surface's sample points that lie on their face."""
    from scipy.spatial import KDTree

    on = surface.points[surface.on_face]
    if not len(on) or not len(points):
        return np.full(len(points), np.inf)
    return KDTree(on).query(points)[0] + _ON_FACE


def _faces_bound(
    points: np.ndarray, surface: _Surface, out: np.ndarray, extra: float, need: float
) -> np.ndarray:
    """The bounds out, lowered to each point's distance to a point on a face of surface that
    gives one (_bound)."""
    triangles = [c for c in surface.triangles if c is not None]
    if triangles:
        out = np.minimum(out, _triangles_bound(points, np.array(triangles)))
    cut = []
    for face, kind in zip(surface.faces, surface.kinds):
        if kind not in (_CYLINDER, _CONE, _TORUS):
            continue
        if _whole(face):
            on, _ = _nearest_on(points, face, kind)
            out = np.minimum(out, np.linalg.norm(points - on, axis=1))
        else:
            cut.append((face, kind))
    planes = [
        f
        for f, kind, corners in zip(surface.faces, surface.kinds, surface.triangles)
        if kind == _PLANE and corners is None
    ]
    lines = []
    for face in planes:
        over, edges = _plane_bound(points, face, out)
        out, lines = np.minimum(out, over), lines + edges
    # A plane face's lines bound the points over no face, and those over one but high above it.
    loose = np.flatnonzero((out > _NEAR_FACE) & (out + extra >= need))
    for n, (start, end) in enumerate(lines):
        if n % _CHUNK == 0:  # a point the lines so far have settled needs no more of them
            loose = loose[out[loose] + extra >= need]
        out[loose] = np.minimum(
            out[loose], _segment_distance(points[loose], start, end, out[loose])
        )
    # A cylinder, cone or torus face cut by a hole or a notch bounds a point by its nearest point
    # only where _on_face shows that point on the face, and only where it would lower the bound: a
    # point whose nearest point falls in a hole gets no bound from it.
    for face, kind in cut:
        on, uv = _nearest_on(points, face, kind)
        gap = np.linalg.norm(points - on, axis=1)
        classify = _OCP["IntTools"].IntTools_FClass2d(face.wrapped, _ON_FACE)
        for n in np.flatnonzero((gap < out) & (out + extra >= need)):
            if _on_face(classify, face, on[n], uv[n]):
                out[n] = gap[n]
    return out


def _triangle_distance(p, a, b, c) -> np.ndarray:
    """The distance from each point p[k] to the triangle a[k], b[k], c[k]: the closest point by
    Ericson's regions (Real-Time Collision Detection, 5.1.5)."""
    ab, ac, ap, bp, cp = b - a, c - a, p - a, p - b, p - c
    d1, d2 = (ab * ap).sum(1), (ac * ap).sum(1)
    d3, d4 = (ab * bp).sum(1), (ac * bp).sum(1)
    d5, d6 = (ab * cp).sum(1), (ac * cp).sum(1)
    va, vb, vc = d3 * d6 - d5 * d4, d5 * d2 - d1 * d6, d1 * d4 - d3 * d2
    with np.errstate(divide="ignore", invalid="ignore"):
        whole = va + vb + vc
        closest = a + ab * (vb / whole)[:, None] + ac * (vc / whole)[:, None]
        on_bc = (d4 - d3) / ((d4 - d3) + (d5 - d6))
        # The regions in Ericson's order reversed, so the first that holds is applied last.
        for holds, at in (
            ((va <= 0) & (d4 >= d3) & (d5 >= d6), b + (c - b) * on_bc[:, None]),
            ((vb <= 0) & (d2 >= 0) & (d6 <= 0), a + ac * (d2 / (d2 - d6))[:, None]),
            ((d6 >= 0) & (d5 <= d6), c),
            ((vc <= 0) & (d1 >= 0) & (d3 <= 0), a + ab * (d1 / (d1 - d3))[:, None]),
            ((d3 >= 0) & (d4 <= d3), b),
            ((d1 <= 0) & (d2 <= 0), a),
        ):
            closest = np.where(holds[:, None], at, closest)
    found = np.linalg.norm(p - closest, axis=1)
    # A triangle with no area has no regions: its nearest corner bounds the distance.
    corner = np.linalg.norm(np.stack([ap, bp, cp]), axis=2).min(0)
    return np.where(np.isfinite(found), found, corner)


def _triangles_bound(points: np.ndarray, triangles: np.ndarray) -> np.ndarray:
    """Each point's distance to the nearest of triangles (n × 3 × 3). Only a triangle whose bbox
    lies no farther than the nearest triangle centre can be the nearest, so only those are
    looked at, a chunk of nearby points at a time."""
    low, high, centres = triangles.min(1), triangles.max(1), triangles.mean(1)
    out = np.full(len(points), np.inf)
    # By cell of a coarse grid, so a chunk's points lie together.
    cell = np.floor((points - points.min(0)) / (np.ptp(points, 0).max() / 16 + 1e-300))
    order = np.lexsort(cell.T)
    for start in range(0, len(points), _CHUNK):
        chunk = order[start : start + _CHUNK]
        p = points[chunk]
        # No point of the chunk lies farther from its nearest centre than the chunk's middle's
        # nearest centre and the chunk's reach from its middle, so farther triangles drop out.
        middle = (p.min(0) + p.max(0)) / 2
        reach = np.linalg.norm(p - middle, axis=1).max()
        cut = np.linalg.norm(centres - middle, axis=1).min() + reach
        gap = np.maximum(low - p.max(0), 0) + np.maximum(p.min(0) - high, 0)
        kept = np.flatnonzero(np.linalg.norm(gap, axis=1) <= cut)
        p3 = p[:, None]
        outside = np.maximum(low[kept] - p3, 0) + np.maximum(p3 - high[kept], 0)
        nearest = np.linalg.norm(centres[kept] - p3, axis=2).min(1)
        i, j = np.nonzero(np.linalg.norm(outside, axis=2) <= nearest[:, None])
        found = _triangle_distance(p[i], *triangles[kept[j]].transpose(1, 0, 2))
        best = np.full(len(p), np.inf)
        np.minimum.at(best, i, found)
        out[chunk] = best
    return out


def _whole(face) -> bool:
    """Whether a face is the whole rectangle of the parameters it spans: every edge's curve on it
    a line along one parameter at the other's first or last value, as no hole or notch in the face
    leaves it. Every point of that rectangle then lies on the face."""
    u0, u1, v0, v1 = _OCP["BRepTools"].BRepTools.UVBounds_s(face.wrapped)
    for edge in _edges(face.wrapped):
        curve = _OCP["BRepAdaptor"].BRepAdaptor_Curve2d(edge, face.wrapped)
        if curve.GetType() != _LINE:
            return False
        line = curve.Line()
        (du, dv), (u, v) = (_uv(line.Direction()), _uv(line.Location()))
        if abs(dv) <= _SAME_PARAMETER:
            at, ends = v, (v0, v1)
        elif abs(du) <= _SAME_PARAMETER:
            at, ends = u, (u0, u1)
        else:
            return False
        if min(abs(at - e) for e in ends) > _SAME_PARAMETER:
            return False
    return True


def _uv(p) -> tuple[float, float]:
    return p.X(), p.Y()


def _clamp_angle(angle: np.ndarray, first: float, last: float) -> np.ndarray:
    """Each angle, turned into the turn from first, clamped to first..last: past last, the nearer
    of the two ends."""
    angle = first + np.mod(angle - first, 2 * math.pi)
    if last - first >= 2 * math.pi:
        return angle
    nearer_first = angle - last > first + 2 * math.pi - angle
    return np.where(nearer_first, first, np.minimum(angle, last))


def _on_face(classify, face, point: np.ndarray, uv: np.ndarray) -> bool:
    """Whether point, a point of a face's surface at the face's parameters uv, lies on the face,
    by classify, OCC's classifier of the face's parameters, built once for the face. It finds uv
    in the face or out of it, as distance_to within _ON_FACE does, but computes no distance. On an
    edge it strays either way, so there distance_to settles it. A point it finds in the face lies
    on the face's surface within its pcurves, which stray from its edges by no more than the
    tolerance _bound allows for."""
    state = classify.Perform(_OCP["gp"].gp_Pnt2d(float(uv[0]), float(uv[1])))
    if state == _ON:
        return face.distance_to(tuple(point)) <= _ON_FACE
    return state == _IN


def _nearest_on(points: np.ndarray, face, kind) -> tuple[np.ndarray, np.ndarray]:
    """For each point, the point of a cylinder, cone or torus face's surface at the point's own
    angle around the axis and its own place along the face's other parameter (height, place along
    the cone's line, or angle around the torus's tube), each clamped to the face's range, and
    those two parameters (n × 2). Exact where the point lies over the face; elsewhere a point of
    the surface, which a face cut by a hole or a notch may not have there."""
    adapted = _OCP["BRepAdaptor"].BRepAdaptor_Surface(face.wrapped)
    surface = {_CYLINDER: adapted.Cylinder, _CONE: adapted.Cone, _TORUS: adapted.Torus}[kind]()
    frame = surface.Position()
    o, x, y, axis = (
        np.array(_xyz(v))
        for v in (frame.Location(), frame.XDirection(), frame.YDirection(), frame.Direction())
    )
    u0, u1, v0, v1 = _OCP["BRepTools"].BRepTools.UVBounds_s(face.wrapped)
    w = points - o
    angle = _clamp_angle(np.arctan2(w @ y, w @ x), u0, u1)
    out = np.cos(angle)[:, None] * x + np.sin(angle)[:, None] * y
    if kind == _CYLINDER:
        height = np.clip(w @ axis, v0, v1)
        return o + surface.Radius() * out + height[:, None] * axis, np.stack([angle, height], 1)
    if kind == _CONE:
        # The cone's line at that angle, from its circle of RefRadius at the frame's origin.
        slope = surface.SemiAngle()
        start = o + surface.RefRadius() * out
        along = math.sin(slope) * out + math.cos(slope) * axis
        place = np.clip(((points - start) * along).sum(1), v0, v1)
        return start + place[:, None] * along, np.stack([angle, place], 1)
    # The torus's tube circle at that angle, around its centre on the major circle.
    centre = o + surface.MajorRadius() * out
    w = points - centre
    tube = _clamp_angle(np.arctan2(w @ axis, (w * out).sum(1)), v0, v1)
    across = np.cos(tube)[:, None] * out + np.sin(tube)[:, None] * axis
    return centre + surface.MinorRadius() * across, np.stack([angle, tube], 1)


def _plane_bound(points: np.ndarray, face, within: np.ndarray) -> tuple[np.ndarray, list]:
    """Each point's height over a plane face where the point lies over the face, inf beyond, and
    the face's lines, each as its two ends; inf throughout, and no lines, where the face is
    bounded by anything but lines and circles in its plane. Only points whose height is under
    within are looked at."""
    plane = _OCP["BRepAdaptor"].BRepAdaptor_Surface(face.wrapped).Plane().Position()
    o, x, y, normal = (
        np.array(_xyz(v))
        for v in (plane.Location(), plane.XDirection(), plane.YDirection(), plane.Direction())
    )

    def flat(p: np.ndarray) -> np.ndarray:
        return np.stack([(p - o) @ x, (p - o) @ y], -1)

    out = np.full(len(points), np.inf)
    height = (points - o) @ normal
    looked = np.flatnonzero(np.abs(height) < within)
    q = flat(points[looked])
    # Over the face: inside an odd number of its loops, each loop being the polygon of its
    # edges' chords with the region between each arc and its chord added or taken away. The
    # chords end at the edges' vertices, which edges meeting there share to the bit.
    over = np.zeros(len(q), bool)
    lines = []
    for edge in _edges(face.wrapped):
        curve = _OCP["BRepAdaptor"].BRepAdaptor_Curve(edge)
        kind, (start, end) = curve.GetType(), _vertices(edge)
        a, b = flat(start), flat(end)
        if kind == _LINE:
            lines.append((start, end))
        elif kind != _CIRCLE:
            return out, []
        first, last = (
            f(edge)
            for f in (_OCP["TopExp"].TopExp.FirstVertex_s, _OCP["TopExp"].TopExp.LastVertex_s)
        )
        whole = kind == _CIRCLE and first.IsSame(last)
        if not whole:
            with np.errstate(divide="ignore", invalid="ignore"):
                across = (a[1] > q[:, 1]) != (b[1] > q[:, 1])
                at = a[0] + (q[:, 1] - a[1]) * (b[0] - a[0]) / (b[1] - a[1])
            over ^= across & (q[:, 0] < at)
        if kind == _CIRCLE:
            circle = curve.Circle()
            if abs(abs(np.array(_xyz(circle.Axis().Direction())) @ normal) - 1) > 1e-12:
                return out, []
            centre = flat(np.array(_xyz(circle.Location())))
            disk = np.linalg.norm(q - centre, axis=1) < circle.Radius()
            if whole:
                over ^= disk
                continue
            middle = curve.Value((curve.FirstParameter() + curve.LastParameter()) / 2)
            arc_side = _side(a, b, flat(np.array(_xyz(middle)))) > 0
            over ^= disk & ((_side(a, b, q) > 0) == arc_side)
    out[looked[over]] = np.abs(height[looked[over]])
    return out, lines


def _side(a: np.ndarray, b: np.ndarray, p: np.ndarray) -> np.ndarray:
    """Which side of the line through a and b each point p lies on, by the sign."""
    return (b[0] - a[0]) * (p[..., 1] - a[1]) - (b[1] - a[1]) * (p[..., 0] - a[0])


def _segment_distance(points: np.ndarray, a, b, within: np.ndarray) -> np.ndarray:
    """Each point's distance to the segment a to b where its bbox lies nearer than within; inf
    for the rest."""
    out = np.full(len(points), np.inf)
    outside = np.maximum(np.minimum(a, b) - points, 0) + np.maximum(points - np.maximum(a, b), 0)
    near = np.flatnonzero(np.linalg.norm(outside, axis=1) < within)
    ab = b - a
    t = np.clip(((points[near] - a) @ ab) / max(float(ab @ ab), 1e-300), 0, 1)
    out[near] = np.linalg.norm(points[near] - a - t[:, None] * ab, axis=1)
    return out


# An STL body is held to a part only at points both shapes hold exactly, so facet sag loosens
# nothing.

_SPHERE = _OCP["GeomAbs"].GeomAbs_SurfaceType.GeomAbs_Sphere
# How far, in degrees, two faces' normals across an edge, or two edges' tangents at a vertex, may
# turn and still be one smooth surface or curve: a join there is the part's parametrisation, not
# its shape, so a mesh of the same shape need not hold a corner there.
_SMOOTH = 1.0
# How many spans each edge of a closed chain is split into, to bound corners' distances to it.
_CHAIN = 64


# What found an STL's largest deviation: a mesh corner off the part, a corner or a closed edge of
# the part on no mesh corner, or a facet whose corners lie on no one smooth patch of the part.
Found = Literal["mesh corner", "part corner", "closed edge", "facet"]


class MeshFit(NamedTuple):
    """How a part fits an STL body (mesh_fit): whether it passes, the largest deviation found,
    where it lies, what found it, and how many facets lie on no one smooth patch."""

    ok: bool
    distance: float
    at: tuple[float, float, float]
    found: Found
    facets: int


def mesh_fit(part, mesh, tol: float, samples: int) -> MeshFit:
    """Hold part to mesh, an STL body of flat triangles, at points both hold exactly, each within
    tol: every mesh corner lies on the part; every corner of the part where sharp edges meet lies
    on a mesh corner, and every sharp closed edge passes through three; every facet's three
    corners lie on one smooth patch of the part, faces joined by tangent edges. The deviation is
    the largest any of them finds, exact: a mesh corner's distance to the part, a point of the
    part's to its mesh corners, or a failing facet's centre's to the part."""
    triangles = _Surface(mesh, 1).mesh
    if triangles is None:
        raise ValueError("an STL body is flat triangles")
    corners, of = np.unique(np.round(triangles.reshape(-1, 3), 9), axis=0, return_inverse=True)
    surface = _Surface(part, samples)
    box = part.bounding_box()
    size = max(abs(v) for corner in (box.min, box.max) for v in corner)
    slack = _ROUNDING * max(1.0, size, float(np.abs(corners).max(initial=0)))
    gap, n = _farthest(corners, surface, slack)
    found: list[tuple[Found, float, tuple | None]] = [
        ("mesh corner", gap, tuple(corners[n]) if n >= 0 else None),
        _on_corners(part, corners),
    ]
    off = _off_patches(part, corners, of.reshape(-1, 3), tol, samples, slack)
    if len(off):
        centres = triangles[off].mean(1)
        gap, n = _farthest(centres, surface, slack)
        found.append(("facet", gap, tuple(centres[n])))
    ok = all(gap <= tol for _, gap, _ in found) and not len(off)
    # A failing facet is what fails where every distance passes.
    what, distance, at = max(found, key=lambda f: (f[1] > tol or f[0] == "facet", f[1]))
    x, y, z = (0.0, 0.0, 0.0) if at is None else (float(v) for v in at)
    return MeshFit(ok, float(distance), (x, y, z), what, len(off))


def _farthest(points: np.ndarray, surface: _Surface, slack: float) -> tuple[float, int]:
    """The largest distance from points to surface, and the index of the first point at it, as
    computing every point's distance finds it: OCC computes the points from the highest bound
    (_bound) down, until no bound left can reach the largest found. (0, -1) for no points."""
    from build123d import Vector

    bounds = _bound(points, surface, slack, 0.0)
    worst, at = 0.0, -1
    for n in np.argsort(-bounds, kind="stable"):
        if bounds[n] < worst or (at >= 0 and bounds[n] == worst == 0):
            break
        gap = surface.distance_to(Vector(*points[n]))
        if gap > worst or at < 0 or (gap == worst and n < at):
            worst, at = gap, int(n)
    return worst, at


def _sharp(part) -> tuple[list, dict]:
    """The part's sharp edges, across which its two faces meet at an angle, and each edge's faces,
    None for a face it is a seam of: where a periodic face closes on itself, joining no two."""
    is_closed = _OCP["BRep"].BRep_Tool.IsClosed_s
    faces_of: dict = {}
    for face in part.faces():
        for edge in face.edges():
            seam = is_closed(edge.wrapped, face.wrapped)
            faces_of.setdefault(edge, []).append(None if seam else face)
    turn = math.cos(math.radians(_SMOOTH))
    sharp = []
    for edge, faces in faces_of.items():
        if None in faces or len(faces) != 2:
            continue
        at = edge.position_at(0.5)
        if abs(faces[0].normal_at(at).dot(faces[1].normal_at(at))) < turn:
            sharp.append(edge)
    return sharp, faces_of


def _on_corners(part, corners: np.ndarray) -> tuple[Found, float, tuple | None]:
    """How far the part's exact points lie from the mesh's corners: each vertex where sharp edges
    meet from its nearest corner, and each sharp closed edge from the third corner nearest it,
    since three fix a circle. Sharp edges that join tangentially are one edge, so a vertex there is
    no corner, and a rim split into arcs is one closed edge. The largest, what it is, and where."""
    from scipy.spatial import KDTree

    sharp, _ = _sharp(part)
    turn = math.cos(math.radians(_SMOOTH))
    meeting: dict = {}
    for edge in sharp:
        if not edge.is_closed:
            for vertex in edge.vertices():
                meeting.setdefault(vertex, []).append(edge)
    index = {edge: i for i, edge in enumerate(sharp)}
    parent = list(range(len(sharp)))

    def root(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    vertices, ends = [], set()
    for vertex, edges in meeting.items():
        if len(edges) == 2:
            at = vertex.center()
            starts = [(e.position_at(0) - at).length < 1e-6 for e in edges]
            tangents = [e.tangent_at(0 if start else 1) for e, start in zip(edges, starts)]
            if abs(tangents[0].dot(tangents[1])) >= turn:
                parent[root(index[edges[0]])] = root(index[edges[1]])
                continue
        vertices.append(tuple(vertex))
        ends |= {index[e] for e in edges}
    chains: dict[int, list] = {}
    for edge in sharp:
        chains.setdefault(root(index[edge]), []).append(edge)
    worst: tuple[Found, float, tuple | None] = ("part corner", 0.0, None)
    if vertices and len(corners):
        gaps, _ = KDTree(corners).query(np.array(vertices))
        k = int(np.argmax(gaps))
        worst = ("part corner", float(gaps[k]), vertices[k])
    for chain in chains.values():
        if any(index[e] in ends for e in chain):
            continue  # an open run of sharp edges, held by its corners
        third = _third_nearest(chain, corners)
        if third > worst[1]:
            worst = ("closed edge", third, tuple(chain[0].position_at(0.5)))
    return worst


def _third_nearest(chain: list, corners: np.ndarray) -> float:
    """The distance from a closed chain of edges to the third corner nearest it: by numpy where
    its edges are arcs of one circle, else by OCC for the corners near its bbox."""
    from build123d import Vector

    curves = [_OCP["BRepAdaptor"].BRepAdaptor_Curve(e.wrapped) for e in chain]
    circles = [c.Circle() for c in curves if c.GetType() == _CIRCLE]
    centres = [np.array(_xyz(c.Location())) for c in circles]
    normals = [np.array(_xyz(c.Axis().Direction())) for c in circles]
    one = len(circles) == len(chain) and all(
        np.linalg.norm(o - centres[0]) <= _SAME_CORNER
        and abs(abs(n @ normals[0]) - 1) <= _SAME_PARAMETER
        and abs(c.Radius() - circles[0].Radius()) <= _SAME_CORNER
        for o, n, c in zip(centres, normals, circles)
    )
    if one:
        w = corners - centres[0]
        up = w @ normals[0]
        across = np.linalg.norm(w - up[:, None] * normals[0], axis=1) - circles[0].Radius()
        gaps = np.sort(np.hypot(up, across))
    elif len(corners) >= 3:
        from scipy.spatial import KDTree

        # Each corner's distance to the nearest of points spaced along the chain bounds its
        # distance to the chain from above, and from below less half the spacing: only the corners
        # whose lower bound is under the third least upper bound can be among the three nearest.
        points = np.array(
            [tuple(e.position_at(i / _CHAIN)) for e in chain for i in range(_CHAIN + 1)]
        )
        half = max(e.length for e in chain) / _CHAIN / 2
        upper = KDTree(points).query(corners)[0]
        near = corners[upper <= np.partition(upper, 2)[2] + half]
        gaps = np.sort([min(e.distance_to(Vector(*q)) for e in chain) for q in near])
    else:
        gaps = []
    return float(gaps[2]) if len(gaps) >= 3 else math.inf


def _patches(part) -> list[list]:
    """The part's faces grouped into smooth patches: faces joined by an edge across which their
    normals turn no more than _SMOOTH are one patch, and a sharp edge parts two."""
    faces = part.faces()
    index = {face: i for i, face in enumerate(faces)}
    parent = list(range(len(faces)))

    def root(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    sharp, faces_of = _sharp(part)
    parted = set(sharp)
    for edge, two in faces_of.items():
        if edge not in parted and None not in two and len(two) == 2:
            parent[root(index[two[0]])] = root(index[two[1]])
    groups: dict[int, list] = {}
    for face in faces:
        groups.setdefault(root(index[face]), []).append(face)
    return list(groups.values())


def _off_patches(
    part, corners: np.ndarray, facets: np.ndarray, tol: float, samples: int, slack: float
) -> np.ndarray:
    """The facets, by index, whose three corners lie within tol of no one smooth patch of the
    part. Numpy settles which faces most corners lie on: off a face where the corner's distance
    to the face's whole surface passes tol, on it where an upper bound (_bound) on its distance
    to the face does not; OCC computes the rest."""
    from build123d import Vector

    on = []
    for group in _patches(part):
        held = np.zeros(len(corners), bool)
        for face in group:
            box = face.bounding_box()
            low, high = np.array(tuple(box.min)) - tol, np.array(tuple(box.max)) + tol
            near = np.flatnonzero(~held & np.all((corners >= low) & (corners <= high), 1))
            near = near[_floor(corners[near], face) <= tol]
            if not len(near):
                continue
            bounds = _bound(corners[near], _Surface(face, samples), slack, tol)
            held[near[bounds <= tol]] = True
            for n in near[bounds > tol]:
                held[n] = face.distance_to(Vector(*corners[n])) <= tol
        on.append(held)
    patches = np.stack(on, 1) if on else np.zeros((len(corners), 1), bool)
    shared = patches[facets[:, 0]] & patches[facets[:, 1]] & patches[facets[:, 2]]
    return np.flatnonzero(~shared.any(1))


def _floor(points: np.ndarray, face) -> np.ndarray:
    """A lower bound on each point's distance to a face: its distance to the face's whole
    surface, a plane, cylinder, sphere or torus; 0 for any other."""
    adapted = _OCP["BRepAdaptor"].BRepAdaptor_Surface(face.wrapped)
    kind = adapted.GetType()
    if kind == _PLANE:
        frame = adapted.Plane().Position()
        o, normal = np.array(_xyz(frame.Location())), np.array(_xyz(frame.Direction()))
        return np.abs((points - o) @ normal)
    if kind == _SPHERE:
        sphere = adapted.Sphere()
        centre = np.array(_xyz(sphere.Location()))
        return np.abs(np.linalg.norm(points - centre, axis=1) - sphere.Radius())
    if kind in (_CYLINDER, _TORUS):
        whole = adapted.Cylinder() if kind == _CYLINDER else adapted.Torus()
        frame = whole.Position()
        o, axis = np.array(_xyz(frame.Location())), np.array(_xyz(frame.Direction()))
        w = points - o
        up = w @ axis
        out = np.linalg.norm(w - up[:, None] * axis, axis=1)
        if kind == _CYLINDER:
            return np.abs(out - whole.Radius())
        return np.abs(np.hypot(out - whole.MajorRadius(), up) - whole.MinorRadius())
    return np.zeros(len(points))
