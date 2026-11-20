"""PROTOTYPE for #246, throwaway: one deviation analysis per released part.

Question: can a released part be proven by one comparison with its body, the part built in the
file's frame, in place of a shape check's alignment pairs, a probe per value and derived datums?

For every shape check of a project this places the built part in its body's frame and compares
the two whole, with no alignment:

- STEP body: the largest distance between their sampled surfaces, both ways (distance.py).
- STL body: each mesh corner held to the built surface (a corner is the only point a mesh stores
  on the true surface), and each of the part's own corners and closed edges held to mesh
  corners, which a mesh of the same shape holds there. Both sides are exact points, so facet sag
  loosens neither direction.
- Cut-file region: the part's outline, projected, against the region's edges, both ways.

Each passes within tolerance.length. The file's frame is the rigid motion today's alignment pairs
fit on the unmodified model (--save-frames), standing in for the part built there; a run on a
seeded copy reads it back (--frames), so a seeded error cannot move the frame with it.

    scripts/cadrev python prototypes/released-geometry/deviation.py <project> \
        [--save-frames f.json | --frames f.json] [--json out.json] [--today]

--today also times each of today's shape checks and the ledger's probes, for the run-time
comparison.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import time
from pathlib import Path

import numpy as np

from cadrev import build, distance, ledger, released
from cadrev import checks as checks_mod
from cadrev import project as project_mod

SAMPLES = released.SAMPLES


def location_matrix(where) -> list[list[float]]:
    t = where.wrapped.Transformation()
    return [[t.Value(i, j) for j in (1, 2, 3, 4)] for i in (1, 2, 3)]


def matrix_location(m):
    from build123d import Location, Plane

    m = np.asarray(m, float)
    return Location(
        Plane(
            origin=tuple(m[:, 3]),
            x_dir=tuple(m[:, 0]),
            z_dir=tuple(m[:, 2]),
        )
    )


def frame_cost(m) -> dict:
    m = np.asarray(m, float)
    angle = math.degrees(math.acos(max(-1.0, min(1.0, (np.trace(m[:, :3]) - 1) / 2))))
    return {"turn_deg": round(angle, 4), "shift": round(float(np.linalg.norm(m[:, 3])), 4)}


def fit_frame(p, c, model):
    """Today's alignment: the rigid motion the shape check's datum pairs fit."""
    name = str(c["body"])
    sheet, along = released.at_point(name), c.get("along")
    on = name if sheet is None else sheet[0]
    ours, theirs = [], []
    for a, b in c["pairs"]:
        point = model.datums[a]
        ours.append(point if sheet is None else released.projected(point, str(along)))
        theirs.append(p.datum_on(b, on))
    where, residual, _ = released.fit(ours, theirs)
    return where, residual


def mesh_of(body) -> np.ndarray:
    tri = distance._Surface(body, 1).mesh
    assert tri is not None, "an STL body is flat triangles"
    return tri


def corners_to_part(corners: np.ndarray, part, tol: float, count: bool = False):
    """The largest distance from a mesh corner to the part's surface, exact where it matters:
    numpy bounds every corner from above, OCC computes those whose bound reaches tol or the
    largest found (with count, every one whose bound passes tol, to count those past it)."""
    from build123d import Vector

    surface = distance._Surface(part, SAMPLES)
    slack = 1e-9 * max(1.0, float(np.abs(corners).max()))
    bounds = distance._bound(corners, surface, slack, tol)
    worst, at, computed, over = 0.0, None, 0, 0
    for n in np.argsort(-bounds, kind="stable"):
        if bounds[n] <= tol:
            if not computed:
                worst, at = float(bounds[n]), corners[n]  # every corner within tol, as bounded
            break
        if bounds[n] < worst and not count:
            break
        gap = surface.distance_to(Vector(*corners[n]))
        computed += 1
        over += gap > tol
        if gap > worst:
            worst, at = gap, corners[n]
    return worst, at, computed, over


# How far two faces' normals across an edge, or two edges' tangents at a vertex, may turn
# (degrees) and still be one smooth surface or curve: a join there is the part's parametrisation,
# not its shape, so a mesh of the same shape need not hold a corner there.
SMOOTH = 1.0


def part_corners(part):
    """The part's own exact points a mesh of the same shape must hold as corners: each vertex
    where sharp edges (whose two faces meet at an angle) meet at a corner, and each sharp closed
    edge (a hole's circle), which a mesh holds by corners along it. A seam, where a periodic face
    closes on itself, a smooth edge, and a vertex where two sharp edges join tangentially are
    artefacts of the part's own topology and left out."""
    import importlib

    brep = importlib.import_module("OCP.BRep").BRep_Tool
    faces_of: dict = {}
    for face in part.faces():
        for edge in face.edges():
            if brep.IsClosed_s(edge.wrapped, face.wrapped):
                faces_of.setdefault(edge, []).append(None)  # a seam
            else:
                faces_of.setdefault(edge, []).append(face)
    cos = math.cos(math.radians(SMOOTH))
    sharp = []
    for edge, faces in faces_of.items():
        if None in faces or len(faces) != 2:
            continue
        at = edge.position_at(0.5)
        n0, n1 = (f.normal_at(at) for f in faces)
        if abs(n0.dot(n1)) < cos:
            sharp.append(edge)
    of: dict = {}
    for edge in sharp:
        if edge.is_closed:
            continue
        for vertex in edge.vertices():
            of.setdefault(vertex, []).append(edge)
    vertices = []
    for vertex, edges in of.items():
        if len(edges) == 2:
            ends = []
            for e in edges:
                start = (e.position_at(0) - vertex.center()).length
                ends.append(e.tangent_at(0 if start < 1e-6 else 1))
            if abs(ends[0].dot(ends[1])) >= cos:
                continue
        vertices.append(tuple(vertex))
    closed = [e for e in sharp if e.is_closed]
    return np.array(vertices).reshape(-1, 3), closed


def smooth_groups(part) -> list[list]:
    """The part's faces grouped into smooth patches: faces joined by an edge across which their
    normals turn no more than SMOOTH (a fillet's tangent edge, a face split by the part's own
    topology) are one patch; a sharp edge parts two."""
    import importlib

    brep = importlib.import_module("OCP.BRep").BRep_Tool
    faces = part.faces()
    index = {face: i for i, face in enumerate(faces)}
    parent = list(range(len(faces)))

    def root(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    of: dict = {}
    for face in faces:
        for edge in face.edges():
            if not brep.IsClosed_s(edge.wrapped, face.wrapped):
                of.setdefault(edge, []).append(face)
    cos = math.cos(math.radians(SMOOTH))
    for edge, two in of.items():
        if len(two) != 2:
            continue
        at = edge.position_at(0.5)
        if abs(two[0].normal_at(at).dot(two[1].normal_at(at))) >= cos:
            parent[root(index[two[0]])] = root(index[two[1]])
    groups: dict = {}
    for face in faces:
        groups.setdefault(root(index[face]), []).append(face)
    return list(groups.values())


def facets_on_patches(tri: np.ndarray, part, tol: float):
    """Each mesh facet held to the part by its corners: all three must lie within tol of one
    smooth patch of the part (smooth_groups), as a facet of a mesh of the same shape lies on one
    face of it. A filled hole's wall facet has corners on the plate's two faces and on no one
    patch. The number of facets that fail, and the deepest any of them lies in the part or out
    of it, at its centre."""
    from build123d import Vector

    groups = smooth_groups(part)
    keys = np.round(tri.reshape(-1, 3), 9)
    corners, inverse = np.unique(keys, axis=0, return_inverse=True)
    inverse = inverse.reshape(-1, 3)
    on = [set() for _ in corners]
    for g, group in enumerate(groups):
        for face in group:
            box = face.bounding_box()
            lo, hi = np.array(tuple(box.min)) - tol, np.array(tuple(box.max)) + tol
            for n in np.flatnonzero(np.all((corners >= lo) & (corners <= hi), 1)):
                if g not in on[n] and face.distance_to(Vector(*corners[n])) <= tol:
                    on[n].add(g)
    failing = [t for t in range(len(tri)) if not (on[inverse[t, 0]] & on[inverse[t, 1]] & on[inverse[t, 2]])]
    surface = distance._Surface(part, 1)
    deepest, at = 0.0, None
    for t in failing[:20]:  # the depth is a report, read on a few
        centre = tri[t].mean(0)
        gap = surface.distance_to(Vector(*centre))
        if gap > deepest:
            deepest, at = gap, centre
    return len(failing), deepest, at


def part_on_corners(part, corners: np.ndarray, tol: float):
    """How far the part's exact points (part_corners) lie from the mesh's corners: each vertex
    to its nearest corner, each closed edge to the third corner nearest it (three fix a circle).
    The worst, where, and how many points were held."""
    from build123d import Vector
    from scipy.spatial import KDTree

    vertices, closed = part_corners(part)
    tree = KDTree(corners)
    worst, at, over = 0.0, None, 0
    if len(vertices):
        gaps, _ = tree.query(vertices)
        k = int(np.argmax(gaps))
        worst, at = float(gaps[k]), ("vertex", vertices[k])
        over += int((gaps > tol).sum())
    for edge in closed:
        box = edge.bounding_box()
        lo, hi = np.array(tuple(box.min)) - tol, np.array(tuple(box.max)) + tol
        near = corners[np.all((corners >= lo) & (corners <= hi), 1)]
        gaps = sorted(edge.distance_to(Vector(*q)) for q in near)
        third = gaps[2] if len(gaps) >= 3 else math.inf
        over += third > tol
        if third > worst:
            worst, at = third, ("closed edge", np.array(tuple(edge.center())))
    held = len(vertices) + len(closed)
    return worst, at, held, over


def compare_mesh(part, body, tol: float, count: bool = False) -> dict:
    """Every mesh corner on the part, and every corner and closed edge of the part on mesh
    corners, each within tol: points both shapes hold exactly, so facet sag loosens neither."""
    tri = mesh_of(body)
    corners = np.unique(np.round(tri.reshape(-1, 3), 9), axis=0)
    fwd, fwd_at, computed, fwd_over = corners_to_part(corners, part, tol, count)
    rev, rev_at, held, rev_over = part_on_corners(part, corners, tol)
    facets_over, facet_dev, facet_at = facets_on_patches(tri, part, tol)
    return {
        "corners": len(corners),
        "corner_dev": fwd,
        "corner_at": [round(float(v), 3) for v in fwd_at] if fwd_at is not None else None,
        "occ_points": computed,
        "part_points": held,
        "corners_over": fwd_over if count else None,
        "part_points_over": rev_over,
        "part_dev": rev,
        "part_at": None if rev_at is None else [rev_at[0], [round(float(v), 3) for v in rev_at[1]]],
        "facets": len(tri),
        "facets_over": facets_over,
        "facet_dev": facet_dev,
        "facet_at": None if facet_at is None else [round(float(v), 3) for v in facet_at],
        "deviation": max(fwd, rev, facet_dev),
        "ok": fwd <= tol and rev <= tol and facets_over == 0,
    }


def compare_step(part, body, tol: float) -> dict:
    d, at, on_body = released.surface_distance(part, body)
    return {
        "deviation": d,
        "at": [round(v, 3) for v in at],
        "on_body": on_body,
        "ok": d <= tol,
    }


def compare_region(part, along, where, region, tol: float) -> dict:
    outline = released.outline(part, str(along)).moved(where)
    d, at, on_body = released.outline_distance(outline, region)
    return {"deviation": d, "at": [round(v, 3) for v in at], "on_body": on_body, "ok": d <= tol}


def edge_points(shape, per_mm: float = 4.0, least: int = 16) -> np.ndarray:
    out = []
    for edge in shape.edges():
        n = max(least, int(edge.length * per_mm))
        out += [tuple(edge.position_at(i / n))[:2] for i in range(n + 1)]
    return np.array(out)


def refine_region_frame(part, along, where, region, rounds: int = 30):
    """The frame of a cut part on its sheet, refined from the pairs' fit by point-to-point ICP of
    its outline onto the region's edges: where the file draws the part, read to better than the
    0.01 its datums are typed to. Prototype only, to tell frame error from model error."""
    from build123d import Location
    from scipy.spatial import KDTree

    theirs = edge_points(region, per_mm=20)
    tree = KDTree(theirs)
    base = released.outline(part, str(along))
    ours0 = edge_points(base.moved(where))
    total = np.eye(3)
    ours = ours0.copy()
    for _ in range(rounds):
        _, idx = tree.query(ours)
        q = theirs[idx]
        cp, cq = ours.mean(0), q.mean(0)
        u, _, vt = np.linalg.svd((ours - cp).T @ (q - cq))
        r = vt.T @ np.diag([1, np.sign(np.linalg.det(vt.T @ u.T))]) @ u.T
        t = cq - r @ cp
        step = np.eye(3)
        step[:2, :2], step[:2, 2] = r, t
        total = step @ total
        ours = ours0 @ total[:2, :2].T + total[:2, 2]
        if np.linalg.norm(t) < 1e-9 and abs(r[1, 0]) < 1e-12:
            break
    angle = math.degrees(math.atan2(total[1, 0], total[0, 0]))
    shift = Location((float(total[0, 2]), float(total[1, 2]), 0)) * Location(
        (0, 0, 0), (0, 0, 1), angle
    )
    return shift * where, float(np.hypot(total[0, 2], total[1, 2])), angle


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("project")
    ap.add_argument("--frames")
    ap.add_argument("--save-frames")
    ap.add_argument("--json")
    ap.add_argument("--today", action="store_true")
    ap.add_argument("--only", help="comma-separated shape check ids")
    ap.add_argument("--refine", action="store_true", help="refine cut-file frames by ICP")
    ap.add_argument("--count", action="store_true", help="count every mesh corner past tol")
    a = ap.parse_args()

    p = project_mod.load(Path(a.project))
    spent = [0.0]
    evaluate = ledger._probe

    def timed(*args, **kwargs):
        start = time.perf_counter()
        try:
            return evaluate(*args, **kwargs)
        finally:
            spent[0] += time.perf_counter() - start

    ledger._probe = timed
    ledger.check(p)  # evaluates every probe
    probe_seconds = spent[0]
    t0 = time.perf_counter()
    model = build.build(p)
    build_seconds = time.perf_counter() - t0
    if model is None:
        print("build failed:", [f"{f}" for f in p.findings][-5:])
        return 2
    tol = p.length_tol
    frames = json.loads(Path(a.frames).read_text()) if a.frames else {}
    saved, rows = {}, []
    today = checks_mod.Checks(p, model, None, set()) if a.today else None
    only = set(a.only.split(",")) if a.only else None
    for c in p.checks:
        if c.get("kind") != "shape" or (only and c["id"] not in only):
            continue
        cid, name = c["id"], str(c["body"])
        part = model.parts[c["part"]]
        sheet = released.at_point(name)
        sid = sheet[0] if sheet else released.source_of(name)
        path = p.source_path(sid)
        kind = "svg" if sheet else ("stl" if released.is_mesh(path) else "step")
        row = {"check": cid, "part": c["part"], "body": name, "kind": kind}
        if cid in frames:
            m = frames[cid]
        else:
            try:
                where, residual = fit_frame(p, c, model)
            except Exception as exc:  # a seeded model can lose a datum the pairs name
                row["error"] = f"no frame: {exc}"
                rows.append(row)
                continue
            m = location_matrix(where)
            row["fit_residual"] = residual
        where = matrix_location(m)
        body = p.body(name)
        if a.refine and kind == "svg" and cid not in frames:
            where, moved, turned = refine_region_frame(part, c.get("along"), where, body)
            m = location_matrix(where)
            row["refined_by"] = {"shift": moved, "turn_deg": turned}
        saved[cid] = m
        row["frame"] = frame_cost(m)
        start = time.perf_counter()
        try:
            if kind == "svg":
                row |= compare_region(part, c.get("along"), where, body, tol)
            elif kind == "stl":
                row |= compare_mesh(part.moved(where), body, tol, a.count)
            else:
                row |= compare_step(part.moved(where), body, tol)
        except Exception as exc:
            row["error"] = repr(exc)
        row["seconds"] = round(time.perf_counter() - start, 2)
        if today is not None:
            start = time.perf_counter()
            try:
                res = list(today._shape(c, model))
                row["today_ok"] = all(r.ok for r in res)
                row["today_measured"] = res[0].measured if res else None
            except Exception as exc:
                row["today_ok"], row["today_measured"] = False, repr(exc)
            row["today_seconds"] = round(time.perf_counter() - start, 2)
        rows.append(row)
        dev = row.get("deviation")
        print(
            f"{cid:28} {kind:4} {'PASS' if row.get('ok') else 'FAIL'} "
            f"dev={dev if dev is None else f'{dev:.3g}'} frame={row['frame']} {row['seconds']}s"
            + (f" corner={row['corner_dev']:.3g} part={row['part_dev']:.3g} at {row['part_at']}"
               f" facets_over={row['facets_over']}/{row['facets']} facet_dev={row['facet_dev']:.3g}"
               if kind == "stl" and "corner_dev" in row else "")
            + (f" today={row['today_ok']} {row['today_seconds']}s" if a.today else "")
            + (f" ERROR {row['error']}" if "error" in row else ""),
            flush=True,
        )
    if a.save_frames:
        Path(a.save_frames).write_text(json.dumps(saved))
    summary = {
        "project": p.root.name,
        "probes": len(p.probes),
        "probe_seconds": round(probe_seconds, 2),
        "build_seconds": round(build_seconds, 2),
        "rows": rows,
    }
    if a.json:
        Path(a.json).write_text(json.dumps(summary, indent=1, default=float))
    print(
        f"probes {len(p.probes)} in {probe_seconds:.1f}s, build {build_seconds:.1f}s,"
        f" deviation total {sum(r.get('seconds', 0) for r in rows):.1f}s"
        + (f", today's shape checks {sum(r.get('today_seconds', 0) for r in rows):.1f}s"
           if a.today else "")
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
