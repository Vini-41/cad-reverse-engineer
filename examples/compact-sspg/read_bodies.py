"""What each released STL body settles, and the frame its file holds it in.

Run:  cadrev python read_bodies.py [body ...]      (no argument: every body the target builds)

The files are binary STL in millimetres, read here corner by corner (an STL holds flat
facets whose corners lie on the true surface). Every value is printed as its design value,
rounded to 0.001 mm: an arc is read as the circle through its corners, never off a facet.

An arc read from only four corners, and three corners that may facet a small arc, are marked:
hold those readings loosely and let the shape check settle them.

Frame words used below, per body:
  h      the coordinate along the body's axis, in the file's own frame (not shifted)
  r, @   polar position about the body's axis in the plane across it: r in mm, @ in degrees,
         counted from the file's +U axis towards +V, where (U, V, axis) is (x, y, z) for a
         body whose axis is file z and (z, x, y) for one whose axis is file y
The axis line itself is printed per body as a point (U, V) of the file's frame.
"""
import struct
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
TOL = 5e-4          # a corner within this of a fitted circle or line lies on it

# body id -> (file, axis index in the file, what it is)
BODIES = {
    "sun": ("sources/sspg_sun.STL", 2, "sun gear, with its motor flange"),
    "planet": ("sources/sspg_planet.STL", 2, "planet gear (one body, placed three times)"),
    "carrier_updated": ("sources/sspg_carrier_updated.STL", 2, "carrier (front, the output), updated release"),
    "sec_carrier": ("sources/sspg_sec_carrier.STL", 2, "secondary (rear) carrier"),
    "gearbox_casing": ("sources/sspg_gearbox_casing.STL", 2, "gearbox casing with the ring gear inside it"),
    "bearing_retainer": ("sources/sspg_bearing_retainer.STL", 1, "output-bearing retainer ring"),
    # skipped in evidence.yaml, readable on request:
    "carrier": ("sources/sspg_carrier.STL", 2, "carrier, earlier release (skipped)"),
    "motor_casing": ("sources/sspg_motor_casing.STL", 2, "motor casing (skipped: motor subassembly)"),
}
DEFAULT = ["sun", "planet", "carrier_updated", "sec_carrier", "gearbox_casing", "bearing_retainer"]
# gears: body -> (internal?, radial band that holds the teeth)
GEARS = {"sun": (False, (5.5, 6.9)), "planet": (False, (15.5, 16.9)), "gearbox_casing": (True, (38.1, 39.5))}


def f(x):
    x = round(float(x), 3)
    return "%g" % (0.0 if x == 0 else x)


def circle(xy):
    """Least-squares circle through points: centre, radius, largest miss."""
    A = np.c_[2 * xy, np.ones(len(xy))]
    s = np.linalg.lstsq(A, (xy ** 2).sum(1), rcond=None)[0]
    c = s[:2]
    R = np.sqrt(max(s[2] + c @ c, 0))
    return c, R, np.abs(np.hypot(*(xy - c).T) - R).max()


def uniq(a, d=4):
    return np.unique(np.round(a, d), axis=0)


class Body:
    def __init__(self, path, axis):
        b = Path(path).read_bytes()
        n = struct.unpack("<I", b[80:84])[0]
        rec = np.dtype([("n", "<f4", 3), ("v", "<f4", (3, 3)), ("a", "<u2")])
        v = np.frombuffer(b, dtype=rec, count=n, offset=84)["v"].astype(float)
        perm = {2: [0, 1, 2], 1: [2, 0, 1], 0: [1, 2, 0]}[axis]  # cyclic: (U, V, axis), right-handed
        v = v[:, :, perm]
        self.pts, inv = np.unique(np.round(v.reshape(-1, 3), 4), axis=0, return_inverse=True)
        self.tri = inv.reshape(-1, 3)
        P = self.pts[self.tri]
        n_ = np.cross(P[:, 1] - P[:, 0], P[:, 2] - P[:, 0])
        self.area = np.linalg.norm(n_, axis=1) / 2
        self.n = n_ / (2 * self.area[:, None] + 1e-30)
        self.vol = np.einsum("ij,ij->i", P[:, 0], np.cross(P[:, 1], P[:, 2])).sum() / 6
        self.em = defaultdict(list)
        for t, (a, b_, c) in enumerate(self.tri):
            for e in ((a, b_), (b_, c), (c, a)):
                self.em[(min(e), max(e))].append(t)
        self.flat = np.ptp(P[:, :, 2], axis=1) < 1e-4          # facets square to the axis

    def patches(self, mask, ang=35.0):
        """Facets of `mask` joined across every edge that bends less than `ang` degrees."""
        cosang = np.cos(np.radians(ang))
        adj = defaultdict(list)
        for ts in self.em.values():
            ts = [t for t in ts if mask[t]]
            for i in range(len(ts)):
                for j in range(i + 1, len(ts)):
                    if self.n[ts[i]] @ self.n[ts[j]] > cosang:
                        adj[ts[i]].append(ts[j])
                        adj[ts[j]].append(ts[i])
        seen, out = set(), []
        for s in np.where(mask)[0]:
            if s in seen:
                continue
            comp, st = [], [s]
            seen.add(s)
            while st:
                x = st.pop()
                comp.append(x)
                for y in adj[x]:
                    if y not in seen:
                        seen.add(y)
                        st.append(y)
            out.append(np.array(comp))
        return out

    def flat_loops(self):
        """Each face square to the axis -> {(h, facing): [closed boundary loops as point arrays, signed]}."""
        faces = defaultdict(list)
        for t in np.where(self.flat)[0]:
            faces[(round(self.pts[self.tri[t, 0], 2], 3), 1 if self.n[t, 2] > 0 else -1)].append(t)
        out = {}
        for key, ts in faces.items():
            cnt = defaultdict(int)
            for t in ts:
                a, b_, c = self.tri[t]
                for e in ((a, b_), (b_, c), (c, a)):
                    cnt[e] += 1
            nxt = defaultdict(list)
            for (a, b_), _ in cnt.items():
                if (b_, a) not in cnt:               # a boundary edge, material on its left seen from the normal
                    nxt[a].append(b_)
            loops = []
            while nxt:
                s = next(iter(nxt))
                path = [s]
                while True:
                    cur = path[-1]
                    if cur not in nxt:
                        break
                    b_ = nxt[cur].pop()
                    if not nxt[cur]:
                        del nxt[cur]
                    if b_ == s:
                        break
                    path.append(b_)
                xy = self.pts[path][:, :2]
                sa = 0.5 * np.sum(xy[:, 0] * np.roll(xy[:, 1], -1) - np.roll(xy[:, 0], -1) * xy[:, 1]) * key[1]
                loops.append((xy, sa))
            out[key] = (sum(self.area[t] for t in ts), loops)
        return out


def _off(a, b, c):
    """How far b lies off the straight line from a to c."""
    d = c - a
    return abs(d[0] * (b[1] - a[1]) - d[1] * (b[0] - a[0])) / (np.linalg.norm(d) + 1e-30)


def _bend(P):
    d = np.diff(P, axis=0)
    return np.abs(d[:-1, 0] * d[1:, 1] - d[:-1, 1] * d[1:, 0]) / (np.linalg.norm(d[:-1], axis=1) * np.linalg.norm(d[1:], axis=1) + 1e-30)


def _split(P, o):
    """Greedy runs along an open polyline: (kind, first index, last index, centre, radius)."""
    out, i = [], 0
    ro = np.hypot(*(P - o).T) if o is not None else None
    while i < len(P) - 1:
        if o is not None:                          # three or more corners at one radius from the body's axis
            j = i
            while j + 1 < len(P) and abs(ro[j + 1] - ro[i]) < TOL:
                j += 1
            if j - i >= 2 and ro[i] > 1e-3:
                out.append(("arc", i, j, np.array(o, float), ro[i:j + 1].mean()))
                i = j
                continue
        j, best = i + 3, None
        while j < len(P):
            c, R, res = circle(P[i:j + 1])
            ch = P[j] - P[i]
            sag = np.abs(ch[0] * (P[i:j + 1, 1] - P[i, 1]) - ch[1] * (P[i:j + 1, 0] - P[i, 0])).max() / (np.linalg.norm(ch) + 1e-30)
            if np.linalg.norm(ch) > 1e-6 and sag < 2e-4:   # corners in a straight row: no arc
                break
            if res < TOL and R < 1e3 and _bend(P[i:j + 1]).max() < 0.55:   # a facetted arc bends under ~33 deg a corner
                best = (j, c, R)
            else:
                break
            j += 1
        if best:
            out.append(("arc", i, best[0], best[1], best[2]))
            i = best[0]
        else:
            out.append(("line", i, i + 1, None, 0.0))
            i += 1
    return out


def segments(xy, closed, o=None):
    """An ordered polyline -> circle | arcs (4 or more corners on one circle) | straight lines.

    With `o`, the body's axis, three or more corners in a row at one radius from it are an arc about it.
    An arc is ("arc", centre, radius, start, end, corners, sweep in degrees, + from U towards V).
    """
    n = len(xy)
    if closed and n >= 8:
        c, R, res = circle(xy)
        if res < TOL:
            return [("circle", c, R, n)]
    if closed:                                    # split two turns of the loop, and keep one turn between true breaks
        P = np.r_[xy, xy, xy[:1]]
        runs = _split(P, o)
        ends = [r_[2] for r_ in runs if r_[0] == "arc" and r_[2] < n + 1]
        i0 = ends[0] if ends else 0                # an arc's far end is a true break; a loop of lines starts anywhere
        runs = [r_ for r_ in runs if i0 <= r_[1] < i0 + n]
    else:
        P = xy
        runs = _split(P, o)
    out = []
    for kind, i, j, c, R in runs:
        if kind == "arc":
            a = np.unwrap(np.arctan2(*(P[i:j + 1] - c).T[::-1]))
            out.append(("arc", c, R, P[i], P[j], j - i + 1, np.degrees(a[-1] - a[0])))
        elif out and out[-1][0] == "line" and _off(out[-1][1], P[i], P[j]) < 2e-4:
            out[-1] = ("line", out[-1][1], P[j])
        else:
            out.append(("line", P[i], P[j]))
    if closed and len(out) > 2 and out[0][0] == "line" and out[-1][0] == "line" and _off(out[-1][1], out[0][1], out[0][2]) < 2e-4:
        out = [("line", out[-1][1], out[0][2])] + out[1:-1]      # the loop began part-way along a straight edge
    return out


def classify(body, comp):
    """One smooth patch of facets not square to the axis -> what surface it is."""
    tri = body.tri[comp]
    P = body.pts[np.unique(tri)]
    nz, w = body.n[comp][:, 2], body.area[comp]
    xy = uniq(P[:, :2])
    d = dict(h0=P[:, 2].min(), h1=P[:, 2].max(), nf=len(comp), area=w.sum(), P=P)
    along = (np.abs(nz) * w).sum() / w.sum() < 2e-2      # sliver facets carry noisy normals
    if along:                                     # a wall along the axis: flat, round, or a profile
        if len(xy) == 2:
            return dict(d, kind="wall", a=xy[0], b=xy[1])
        q = xy - xy.mean(0)
        u, s, vt = np.linalg.svd(q)
        if s[-1] < TOL:
            t = q @ vt[0]
            return dict(d, kind="wall", a=xy[np.argmin(t)], b=xy[np.argmax(t)])
        c, R, res = circle(xy)
        if res < TOL and len(xy) >= 4:
            a = np.sort(np.arctan2(*(xy - c).T[::-1]))
            gaps = np.diff(np.r_[a, a[0] + 2 * np.pi])
            span = 360 - np.degrees(gaps.max()) if gaps.max() > 1.6 * np.median(gaps) else 360.0
            trimmed = bool(np.any((P[:, 2] > d["h0"] + 1e-3) & (P[:, 2] < d["h1"] - 1e-3)))
            return dict(d, kind="cyl", c=c, R=R, span=span, trimmed=trimmed)
        return dict(d, kind="profile", xy=xy)
    # a surface of revolution about a line along the axis: rings of corners at each height
    lv = defaultdict(list)
    for p in P:
        lv[round(p[2], 3)].append(p)
    rings = []
    for q in lv.values():
        q = uniq(np.array(q)[:, :2])
        if len(q) >= 5:
            c, R, res = circle(q)
            if res < TOL and R < 500:
                rings.append((len(q), c))
    if rings:
        rings.sort(key=lambda t: -t[0])
        c = np.mean([cc for m, cc in rings if m >= 0.5 * rings[0][0]], axis=0)
        prof, stray = [], 0
        for _, q in sorted(lv.items()):
            q = np.array(q)
            r = np.hypot(*(q[:, :2] - c).T)
            vals, cnt = np.unique(np.round(r, 3), return_counts=True)
            near = np.abs(r - vals[np.argmax(cnt)]) < 2e-3
            if near.sum() >= max(3, 0.5 * len(r)):
                prof.append((r[near].mean(), q[near, 2].mean()))
                stray += int((~near).sum())
            else:
                stray += len(r)
        if len(prof) >= 2:
            prof = np.array(prof)
            a = np.sort(np.arctan2(*(P[:, :2] - c).T[::-1]))
            gaps = np.diff(np.r_[a, a[0] + 2 * np.pi])
            span = 360 - np.degrees(gaps.max()) if gaps.max() > 0.9 else 360.0
            d = dict(d, c=c, span=span, stray=stray)
            if len(prof) == 2:
                if abs(prof[0, 0] - prof[1, 0]) < TOL:
                    return dict(d, kind="cyl", R=prof[0, 0])
                return dict(d, kind="cone", r0=prof[0, 0], r1=prof[1, 0])
            segs = segments(prof, False)
            if len(segs) == 1 and segs[0][0] == "line":
                if abs(prof[0, 0] - prof[-1, 0]) < TOL:
                    return dict(d, kind="cyl", R=prof[0, 0])
                return dict(d, kind="cone", r0=prof[0, 0], r1=prof[-1, 0])
            return dict(d, kind="revolved", prof=prof, segs=segs)
    return dict(d, kind="other")


def gear(body, o, internal, band):
    """The tooth form, read off the corners of the toothed outline at the teeth's first height."""
    P = body.pts
    q = P[:, :2] - o
    r = np.hypot(*q.T)
    inband = (r > band[0]) & (r < band[1])
    hv, hc = np.unique(np.round(P[inband, 2], 3), return_counts=True)
    hv = hv[hc >= 0.5 * hc.max()]                 # the heights that carry the whole toothed outline
    h0, h1 = hv.min(), hv.max()
    h0, h1 = P[np.abs(P[:, 2] - h0) < 1e-3, 2].mean(), P[np.abs(P[:, 2] - h1) < 1e-3, 2].mean()
    k = inband & (np.abs(P[:, 2] - h0) < 1e-3)
    r, th = r[k], np.degrees(np.arctan2(q[k, 1], q[k, 0])) % 360
    tip = r.min() if internal else r.max()
    root = r.max() if internal else r.min()
    tips = np.sort(th[np.abs(r - tip) < 2e-3])
    d = np.diff(np.r_[tips, tips[0] + 360])
    if d[0] > d[1]:                               # pair the two corners of each tip land
        tips = np.r_[tips[1:], tips[0] + 360]
    cent = (tips[0::2] + tips[1::2]) / 2
    z = len(cent)
    pitch = 360 / z
    m = 2 * tip / (z - 2 if internal else z + 2)
    rp, rb = m * z / 2, m * z / 2 * np.cos(np.radians(20))
    inv = lambda a: np.tan(a) - a
    print(f"  GEAR ({'internal' if internal else 'external'}), teeth from h={f(h0)} to h={f(h1)} (face width {h1 - h0:.4f})")
    print(f"    teeth counted on the outline: {z}  (tooth pitch {pitch:.5f} deg, spacing even within {np.abs(np.diff(cent) - pitch).max():.4f} deg)")
    print(f"    a tooth's centre line lies @ {cent[0] % pitch:.4f} deg, and every {pitch:.5f} deg from it")
    print(f"    tip radius {f(tip)}, root radius {f(root)}")
    print(f"    module {f(m)} = 2 x tip radius / (teeth {'-' if internal else '+'} 2); pitch radius {f(rp)} (pitch diameter {f(2 * rp)}); base radius at 20 deg {rb:.4f}")
    if internal:
        print(f"    root radius = module x (teeth + 2.5) / 2 = {f(m * (z + 2.5) / 2)}")
    else:
        print(f"    root radius = module x (teeth - 2.5) / 2 = {f(m * (z - 2.5) / 2)}")
    delta = np.abs(((th - cent[0] + pitch / 2) % pitch) - pitch / 2)
    print("    flank corners (radius, half-angle of the tooth there from its centre line, miss from a 20 deg involute with tooth thickness pi x module / 2 at the pitch circle):")
    worst = 0.0
    order = np.argsort(r)
    for sel in np.split(order, np.where(np.diff(r[order]) > 5e-3)[0] + 1):
        rr, s = r[sel].mean(), delta[sel].mean()
        if rr < rb - 1e-3:
            print(f"      r={rr:.4f}  half-angle {s:.4f} deg  (below the base circle: the flank runs straight in along a radius)")
            continue
        a = np.arccos(min(rb / rr, 1))
        half = np.pi / (2 * z) + inv(np.radians(20)) - inv(a)
        if internal:
            half = np.pi / z - half
        miss = (np.radians(s) - half) * rr
        worst = max(worst, abs(miss))
        print(f"      r={rr:.4f}  half-angle {s:.4f} deg  miss {miss * 1000:+.2f} um")
    print(f"    => standard involute teeth: pressure angle 20 deg, no profile shift, no backlash allowance; largest miss {worst * 1000:.2f} um")
    return z, m


def polar(c, o):
    q = np.asarray(c, float) - o
    r = np.hypot(*q)
    return r, (np.degrees(np.arctan2(q[1], q[0])) % 360 if r > 1e-3 else 0.0)


def angles(th):
    th = sorted(round(float(t), 2) % 360 for t in th)
    return f"x{len(th)} @ {th}" if len(th) <= 12 else f"x{len(th)} @ {th[:6]} ..."


def loop_text(xy, o, band):
    """One closed boundary loop -> (key, angle, text): loops alike but for a turn about the axis share a key."""
    r = np.hypot(*(xy - o).T)
    if len(xy) > 60 and band and band[0] < r.min() and r.max() < band[1]:
        return ("toothed",), 0.0, f"toothed outline of {len(xy)} corners, r={f(r.min())}..{f(r.max())} (read under GEAR)"
    segs = segments(xy, True, o)
    if segs[0][0] == "circle":
        rc, th = polar(segs[0][1], o)
        return ("circle", f(segs[0][2]), f(rc)), th, None
    if len(segs) == 6 and all(s[0] == "line" for s in segs):
        L = [np.linalg.norm(s[1] - s[2]) for s in segs]
        if np.ptp(L) < 2e-3:
            c = np.mean([s[1] for s in segs], axis=0)
            rc, th = polar(c, o)
            flat_dir = (np.degrees(np.arctan2(*(segs[0][2] - segs[0][1])[::-1])) - th) % 60
            return ("hexagon", f(np.mean(L) * np.sqrt(3)), f(rc), "%g" % round(flat_dir, 1)), th, None
    # a loop about the axis is read in the body's own angles; any other is turned back by the
    # angle of its centroid, so repeats about the axis read alike
    ends = np.array([sg[3] if sg[0] == "arc" else sg[1] for sg in segs])
    ang = np.unwrap(np.arctan2(*(np.r_[ends, ends[:1]] - o).T[::-1]))
    around = abs(ang[-1] - ang[0]) > 3
    rc, th0 = (0.0, 0.0) if around else polar(ends.mean(0), o)

    def pol(p):
        rr, tt = polar(p, o)
        if rr < 1e-3:
            return 0.0, 0.0
        return rr, (tt % 360 if around else (tt - th0 + 180) % 360 - 180)

    rows = []
    for sg in segs:
        if sg[0] == "arc":
            rows.append(("arc", sg[2], *pol(sg[1]), *pol(sg[3]), *pol(sg[4]), sg[5] <= 4 and np.hypot(*(sg[1] - o)) > 1e-3, sg[6]))
        else:
            rows.append(("line", np.linalg.norm(sg[1] - sg[2]), 0.0, 0.0, *pol(sg[1]), *pol(sg[2]), False, 0.0))
    k = min(range(len(rows)), key=lambda i: (round(rows[i][5], 1), round(rows[i][4], 2)))
    rows = rows[k:] + rows[:k]

    def same(p, q, turn):
        if p[0] != q[0] or abs(p[1] - q[1]) > 2e-3 or abs(p[2] - q[2]) > 2e-3 or abs(p[4] - q[4]) > 2e-3 or abs(p[6] - q[6]) > 2e-3:
            return False
        return all(abs((q[i] - p[i] - turn + 180) % 360 - 180) < 0.02 for i in ((5, 7) if p[2] < 1e-3 else (3, 5, 7)))

    fold = 1
    if around:
        for n in range(len(rows), 1, -1):
            if len(rows) % n == 0:
                per = len(rows) // n
                if any(all(same(rows[i], rows[i + per], sg * 360 / n) for i in range(len(rows) - per)) for sg in (1, -1)):
                    fold = n
                    rows = rows[:per]
                    break

    def fmt(t):
        return f"{t:.2f}" if around else f"{t:+.2f}"

    lines = []
    for i, (kind, R, rm, tm, ra, ta, rb, tb, few, sweep) in enumerate(rows):
        if kind == "line" and i and rows[i - 1][0] == "line" and abs(rows[i - 1][1] - R) < 2e-3:
            # two equal chords in a row may be a small arc facetted by three corners: name its circle
            p = [np.array([rr * np.cos(np.radians(tt)), rr * np.sin(np.radians(tt))]) for rr, tt in ((rows[i - 1][4], rows[i - 1][5]), (ra, ta), (rb, tb))]
            cc, RR, _ = circle(np.array(p))
            d1, d2 = p[1] - p[0], p[2] - p[1]
            if abs(d1[0] * d2[1] - d1[1] * d2[0]) / (np.linalg.norm(d1) * np.linalg.norm(d2)) < 0.55:
                lines.append(f"          line from (r={f(ra)} @ {fmt(ta)}) to (r={f(rb)} @ {fmt(tb)}), length {f(R)}   [with the line before, three corners of a circle R={f(RR)} about (r={f(np.hypot(*cc))} @ {fmt(np.degrees(np.arctan2(cc[1], cc[0])) % 360 if around else np.degrees(np.arctan2(cc[1], cc[0])))}), if they facet an arc]")
                continue
        if kind == "arc":
            about = "about the axis" if rm < 1e-3 else f"about (r={f(rm)} @ {fmt(tm)})"
            weak = "  (only 4 corners: a weak reading)" if few else ""
            lines.append(f"          arc R={f(R)} {about} from (r={f(ra)} @ {fmt(ta)}) to (r={f(rb)} @ {fmt(tb)}), turning {sweep:+.2f} deg about its centre{weak}")
        else:
            lines.append(f"          line from (r={f(ra)} @ {fmt(ta)}) to (r={f(rb)} @ {fmt(tb)}), length {f(R)}")
    key = ("outline", len(segs), tuple((r_[0], round(r_[1], 2), round(r_[4], 2), round(r_[5], 1)) for r_ in rows), f(rc), around, fold)
    return key, th0, "\n".join(lines)


def describe(name):
    path, axis, what = BODIES[name]
    B = Body(HERE / path, axis)
    P = B.pts
    D = [classify(B, c) for c in B.patches(~B.flat)]
    o = max((d for d in D if d["kind"] == "cyl" and d["span"] > 300), key=lambda d: d["R"])["c"]
    o = np.round(o, 4)
    uv = {2: "x, y", 1: "z, x", 0: "y, z"}[axis]
    print(f"\n===== {name}: {what}")
    print(f"  file {path}: {len(B.tri)} facets, one solid, volume {B.vol:.1f} mm3")
    print(f"  FRAME: axis along file {'xyz'[axis]}, through ({uv}) = ({o[0]:.4f}, {o[1]:.4f}); the body spans h={f(P[:, 2].min())}..{f(P[:, 2].max())} (length {np.ptp(P[:, 2]):.4f})")
    lo, hi = P.min(0), P.max(0)
    print(f"  bounding box in the file's frame ({uv}, axis): ({lo[0]:.4f}, {lo[1]:.4f}, {lo[2]:.4f}) .. ({hi[0]:.4f}, {hi[1]:.4f}, {hi[2]:.4f})")
    if name in GEARS:
        gear(B, o, *GEARS[name])

    print("  FACES SQUARE TO THE AXIS, each with its boundary loops (a positive loop bounds material, a negative one is a hole):")
    for (h, s), (area, loops) in sorted(B.flat_loops().items()):
        if area < 1e-3:
            continue
        print(f"    h={f(h)} facing {'+' if s > 0 else '-'}h, area {area:.2f}:")
        grp, text = defaultdict(list), {}
        for xy, sa in loops:
            key, th, txt = loop_text(xy, o, GEARS[name][1] if name in GEARS else None)
            key = ("+" if sa > 0 else "-",) + key
            grp[key].append(th)
            text.setdefault(key, txt)
        for key in sorted(grp, key=lambda k: (k[1] != "circle", k[1] != "hexagon", str(k))):
            if key[1] == "circle":
                where = "on the axis" if float(key[3]) == 0 else f"centred at r={key[3]}: {angles(grp[key])}"
                print(f"      {key[0]} circle R={key[2]} {where}")
            elif key[1] == "hexagon":
                print(f"      {key[0]} hexagon {key[2]} across flats centred at r={key[3]}, a flat lying {key[4]} deg (mod 60) from the radius through its centre: {angles(grp[key])}")
            elif key[1] == "toothed":
                print(f"      {key[0]} {text[key]}")
            else:
                if key[5]:
                    turn = f", the same {key[6]} times about the axis, every {f(360 / key[6])} deg; one repeat" if key[6] > 1 else ""
                    print(f"      {key[0]} outline about the axis, {key[2]} edges{turn}:")
                else:
                    print(f"      {key[0]} outline of {key[2]} edges, its centroid at r={key[4]}: {angles(grp[key])}; the angles below are counted from the centroid's:")
                print(text[key])

    groups = defaultdict(list)
    rest = []
    for d in D:
        if d["kind"] == "cyl":
            r, th = polar(d["c"], o)
            cover = ("full" if d["span"] > 359 else f(d["span"]) + " deg") + (", an end trimmed by the surface it meets" if d.get("trimmed") else "")
            groups[("cyl", f(d["R"]), f(d["h0"]), f(d["h1"]), f(r), cover)].append(th)
        elif d["kind"] == "cone":
            r, th = polar(d["c"], o)
            groups[("cone", f(d["r0"]), f(d["r1"]), f(d["h0"]), f(d["h1"]), f(r), "full" if d["span"] > 359 else f(d["span"]) + " deg")].append(th)
        else:
            rest.append(d)
    print("  ROUND WALLS ALONG THE AXIS (radius, heights, where its own axis lies, how much of the circle it covers):")
    for key in sorted((k for k in groups if k[0] == "cyl"), key=lambda k: (float(k[4]), float(k[1]), float(k[2]))):
        if name in GEARS and GEARS[name][1][0] < float(key[1]) + float(key[4]) < GEARS[name][1][1] + 30 and len(groups[key]) > 12 and float(key[4]) > 1:
            continue                              # tooth flanks, read under GEAR
        where = "on the axis" if float(key[4]) == 0 else f"centred at r={key[4]}: {angles(groups[key])}"
        print(f"    R={key[1]} (dia {f(2 * float(key[1]))}) h={key[2]}..{key[3]}, {key[5]}, {where}")
    print("  CONES about a line along the axis (radius at its lower h -> at its upper h):")
    for key in sorted((k for k in groups if k[0] == "cone"), key=lambda k: (float(k[5]), float(k[3]), float(k[1]))):
        where = "on the axis" if float(key[5]) == 0 else f"centred at r={key[5]}: {angles(groups[key])}"
        print(f"    r={key[1]} -> {key[2]} over h={key[3]}..{key[4]}, {key[6]}, {where}")
    nwall = sum(1 for d in rest if d["kind"] in ("wall", "profile"))
    print(f"  FLAT AND PROFILED WALLS ALONG THE AXIS: {nwall} patches; their outlines are the loops printed above at the heights they join")
    wl = defaultdict(int)
    for d in rest:
        if d["kind"] in ("wall", "profile"):
            wl[(f(d["h0"]), f(d["h1"]))] += 1
    for key in sorted(wl, key=lambda k: (float(k[0]), float(k[1]))):
        print(f"    h={key[0]}..{key[1]}: {wl[key]} patches")
    print("  OTHER CURVED SURFACES:")
    grp = defaultdict(list)
    for d in rest:
        if d["kind"] == "revolved":
            r, th = polar(d["c"], o)
            lines = []
            for s in d["segs"]:
                if s[0] == "arc":
                    lines.append(f"        arc of radius {f(s[2])} about (r'={f(s[1][0])}, h={f(s[1][1])}) from (r'={f(s[3][0])}, h={f(s[3][1])}) to (r'={f(s[4][0])}, h={f(s[4][1])})")
                else:
                    lines.append(f"        line from (r'={f(s[1][0])}, h={f(s[1][1])}) to (r'={f(s[2][0])}, h={f(s[2][1])})")
            cut = ", cut by a neighbouring surface" if d["stray"] else ""
            grp[(f(r), "full" if d["span"] > 359 else f(d["span"]) + " deg", cut, "\n".join(lines))].append(th)
    for key in sorted(grp, key=lambda k: float(k[0])):
        print(f"    surface of revolution about a line along the axis at r={key[0]}, {key[1]}{key[2]}: {angles(grp[key])}")
        print("      its profile, r' being the distance from that line:")
        print(key[3])
    for d in rest:
        if d["kind"] == "other":
            Q = d["P"]
            r = np.hypot(*(Q[:, :2] - o).T)
            th = np.degrees(np.arctan2(Q[:, 1] - o[1], Q[:, 0] - o[0])) % 360
            small = " (a sliver where two surfaces meet)" if d["area"] < 0.5 else ""
            print(f"    unread patch{small}: {d['nf']} facets, area {d['area']:.2f}, h={f(d['h0'])}..{f(d['h1'])}, r={f(r.min())}..{f(r.max())}, @ {th.min():.1f}..{th.max():.1f}")
    return B, D, o


def circles(D, o, R):
    """Where the round walls of radius R stand: (distance from the axis, sorted angles)."""
    at = [polar(d["c"], o) for d in D if d["kind"] == "cyl" and abs(d["R"] - R) < 2e-3]
    return (f(np.mean([a[0] for a in at])), sorted({round(float(a[1]), 1) for a in at})) if at else ("-", [])


def across(read):
    """Features of different bodies that face each other, side by side. Each body's angles are its own file's."""
    print("\n===== ACROSS THE BODIES (each angle in its own body's frame)")
    c, s, g, b = (read.get(k) for k in ("carrier_updated", "sec_carrier", "gearbox_casing", "bearing_retainer"))
    if c and s:
        print(f"  planet shafts: carrier posts R=4 at r={circles(c[1], c[2], 4)[0]} @ {circles(c[1], c[2], 4)[1]}; secondary carrier's shaft holes R=2.5 at r={circles(s[1], s[2], 2.5)[0]} @ {circles(s[1], s[2], 2.5)[1]}")
        rc, rs = circles(c[1], c[2], 1.7), circles(s[1], s[2], 1.5)
        print(f"  extrusion bolts: carrier holes R=1.7 at r={rc[0]} @ {rc[1]}; secondary carrier's holes R=1.5 at r={rs[0]} @ {rs[1]}")
        if rc[0] != rs[0]:
            print(f"    => the two hole circles differ by {f(abs(float(rc[0]) - float(rs[0])))} mm in radius: the released plates do not line up on these bolts")
    if g and b:
        print(f"  retainer screws: casing holes R=2 at r={circles(g[1], g[2], 2)[0]} @ {circles(g[1], g[2], 2)[1]}; retainer holes R=2 at r={circles(b[1], b[2], 2)[0]} @ {circles(b[1], b[2], 2)[1]}")


if __name__ == "__main__":
    read = {name: describe(name) for name in (sys.argv[1:] or DEFAULT)}
    across(read)
