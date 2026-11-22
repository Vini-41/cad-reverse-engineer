"""What each released body settles, and the frame its file holds it in.

Run:  cadrev python read_bodies.py            every part its bodies ship: design values, frame, regions
      cadrev python read_bodies.py --draw     also writes figures/sheets/<sheet>.png, each region named by its part

The cut sheets (Acryl6MM.svg, Acryl3MM.svg) are read in the sheet's frame, the one cadrev names regions in:
from the page's top-left corner, x right and y down, in mm at the scale the file declares (600 mm over
2125.9843 user units, 90 per inch), with every transform applied. A region is an outer contour with the holes
inside it. A part's values are printed in its region's own frame: origin at the top-left corner of the
region's box, u right, v down, the thickness square to the sheet.

The STL bodies (Clamp.stl, MoldFrame.stl) are read in the file's own frame, in mm.

Known misreading, found while building (build-model): _arc reads every SVG arc as a circle of radius
(rx + ry) / 2. The bearing retainer's outline is an ellipse (rx 36.475, ry 64.406 user units, turned a quarter
on the sheet): 36.354 x 20.588 mm, half-axes 18.177 and 10.294, about the middle this module prints. Its "four
arcs r14.235" and its 21.916 high box are not in the file. params.yaml and model.py hold the ellipse, and
model.py does not import this module: it reads its numbers from params.yaml alone, as cadrev requires.

model.py reads the bodies through this module:
  PARTS            part -> (sheet, thickness, what it is, its regions)
  profile(part)    its outline and holes as lines, arcs and beziers, snapped to design values
  part_regions, placement    each region of a part and how it lies against the first (turn, mirror)
  stl_bodies()     the design values of the clamp and the mould frame
  HOUSING          the rectangles of the 3 mm sheet that hold the controller's housing, outside the target
"""
from __future__ import annotations

import math
import re
import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
SHEETS = {"acryl6": HERE / "sources/Acryl6MM.svg", "acryl3": HERE / "sources/Acryl3MM.svg"}
STLS = {"clamp": HERE / "sources/Clamp.stl", "moldframe": HERE / "sources/MoldFrame.stl"}


# ---------------------------------------------------------------- SVG reading
def _mat(t: str | None) -> np.ndarray:
    m = np.eye(3)
    if not t:
        return m
    for name, args in re.findall(r"(\w+)\s*\(([^)]*)\)", t):
        a = [float(v) for v in re.split(r"[\s,]+", args.strip()) if v]
        n = np.eye(3)
        if name == "translate":
            n[0, 2], n[1, 2] = a[0], (a[1] if len(a) > 1 else 0.0)
        elif name == "scale":
            n[0, 0], n[1, 1] = a[0], (a[1] if len(a) > 1 else a[0])
        elif name == "matrix":
            n[0, 0], n[1, 0], n[0, 1], n[1, 1], n[0, 2], n[1, 2] = a
        elif name == "rotate":
            c, s = math.cos(math.radians(a[0])), math.sin(math.radians(a[0]))
            n[:2, :2] = [[c, -s], [s, c]]
        else:
            raise ValueError(f"transform {name}")
        m = m @ n
    return m


@dataclass
class Seg:
    kind: str                      # line | arc | bezier
    pts: list                      # line: p0 p1; bezier: p0 c1 c2 p1; arc: p0 p1
    centre: tuple | None = None    # arc
    radius: float | None = None    # arc
    sweep: int = 0                 # arc: 1 turns clockwise on the page (y down)

    def sample(self, n=24):
        if self.kind == "line":
            return [self.pts[0], self.pts[1]]
        if self.kind == "bezier":
            p0, c1, c2, p1 = (np.array(p) for p in self.pts)
            t = np.linspace(0, 1, n + 1)[:, None]
            return [tuple(p) for p in (1 - t) ** 3 * p0 + 3 * (1 - t) ** 2 * t * c1 + 3 * (1 - t) * t ** 2 * c2 + t ** 3 * p1]
        cx, cy = self.centre
        a0 = math.atan2(self.pts[0][1] - cy, self.pts[0][0] - cx)
        a1 = math.atan2(self.pts[1][1] - cy, self.pts[1][0] - cx)
        d = a1 - a0
        if self.sweep and d <= 1e-12:
            d += 2 * math.pi
        if not self.sweep and d >= -1e-12:
            d -= 2 * math.pi
        return [(cx + self.radius * math.cos(a0 + d * i / n), cy + self.radius * math.sin(a0 + d * i / n)) for i in range(n + 1)]


def _arc(p0, p1, rx, ry, large, sweep):
    """Centre of the SVG arc from p0 to p1 (circles only: rx == ry within the file's rounding)."""
    r = (rx + ry) / 2
    x0, y0 = p0
    x1, y1 = p1
    dx, dy = (x0 - x1) / 2, (y0 - y1) / 2
    d2 = dx * dx + dy * dy
    r = max(r, math.sqrt(d2))
    k = math.sqrt(max(0.0, (r * r - d2) / d2)) if d2 else 0.0
    if large == sweep:
        k = -k
    cx, cy = k * dy + (x0 + x1) / 2, -k * dx + (y0 + y1) / 2
    return (cx, cy), r


def _path(d: str):
    """Subpaths of a path's d, each a list of Seg, in the element's own coordinates."""
    tok = re.findall(r"[MmLlHhVvCcAaZz]|-?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?", d)
    i, cmd, cur, start, subs, segs = 0, None, (0.0, 0.0), (0.0, 0.0), [], []

    def num():
        nonlocal i
        i += 1
        return float(tok[i - 1])

    while i < len(tok):
        if re.fullmatch(r"[A-Za-z]", tok[i]):
            cmd = tok[i]
            i += 1
            if cmd in "Zz":
                if math.dist(cur, start) > 1e-9:
                    segs.append(Seg("line", [cur, start]))
                cur = start
                if segs:
                    subs.append(segs)
                segs = []
                continue
        rel = cmd.islower()
        c = cmd.upper()
        ox, oy = cur if rel else (0.0, 0.0)
        if c == "M":
            if segs:
                subs.append(segs)
                segs = []
            cur = start = (ox + num(), oy + num())
            cmd = "l" if rel else "L"
        elif c == "L":
            p = (ox + num(), oy + num())
            segs.append(Seg("line", [cur, p]))
            cur = p
        elif c == "H":
            p = (ox + num(), cur[1])
            segs.append(Seg("line", [cur, p]))
            cur = p
        elif c == "V":
            p = (cur[0], oy + num())
            segs.append(Seg("line", [cur, p]))
            cur = p
        elif c == "C":
            c1, c2, p = (ox + num(), oy + num()), (ox + num(), oy + num()), (ox + num(), oy + num())
            segs.append(Seg("bezier", [cur, c1, c2, p]))
            cur = p
        elif c == "A":
            rx, ry, _rot, large, sweep = num(), num(), num(), int(num()), int(num())
            p = (ox + num(), oy + num())
            centre, r = _arc(cur, p, rx, ry, large, sweep)
            segs.append(Seg("arc", [cur, p], centre, r, sweep))
            cur = p
    if segs:
        subs.append(segs)
    return subs


def _rect(e):
    x, y, w, h = (float(e.get(k)) for k in ("x", "y", "width", "height"))
    r = float(e.get("rx") or e.get("ry") or 0)
    if not r:
        c = [(x, y), (x + w, y), (x + w, y + h), (x, y + h)]
        return [[Seg("line", [c[k], c[(k + 1) % 4]]) for k in range(4)]]
    segs = []
    corners = [((x + w - r, y), (x + w, y + r), (x + w - r, y + r)), ((x + w, y + h - r), (x + w - r, y + h), (x + w - r, y + h - r)),
               ((x + r, y + h), (x, y + h - r), (x + r, y + h - r)), ((x, y + r), (x + r, y), (x + r, y + r))]
    prev = (x + r, y)
    for a, b, c in corners:
        if math.dist(prev, a) > 1e-9:
            segs.append(Seg("line", [prev, a]))
        segs.append(Seg("arc", [a, b], c, r, 1))
        prev = b
    return [segs]


@dataclass
class Contour:
    segs: list
    poly: np.ndarray = field(default=None)       # sampled, mm, sheet frame
    _box: tuple = field(default=None, repr=False)

    def __post_init__(self):
        pts = []
        for s in self.segs:
            pts.extend(s.sample()[:-1])
        self.poly = np.array(pts)

    @property
    def area(self):
        x, y = self.poly[:, 0], self.poly[:, 1]
        return abs(float(np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1)))) / 2

    @property
    def box(self):
        if self._box is None:
            self._box = (*self.poly.min(0), *self.poly.max(0))
        return self._box

    def holds(self, p):
        x, y = p
        x0, y0, x1, y1 = self.box
        if not (x0 <= x <= x1 and y0 <= y <= y1):
            return False
        px, py = self.poly[:, 0], self.poly[:, 1]
        qx, qy = np.roll(px, -1), np.roll(py, -1)
        hit = ((py > y) != (qy > y)) & (x < (qx - px) * (y - py) / (qy - py + 1e-300) + px)
        return bool(hit.sum() % 2)

    def circle(self):
        """(cx, cy, d) where the contour is a circle, else None."""
        if any(s.kind == "line" for s in self.segs):
            return None
        x0, y0, x1, y1 = self.box
        c = np.array([(x0 + x1) / 2, (y0 + y1) / 2])
        r = np.hypot(*(self.poly - c).T)
        if r.max() - r.min() > 0.02:
            return None
        arcs = [s.radius for s in self.segs if s.kind == "arc"]
        d = 2 * float(np.mean(arcs)) if len(arcs) == len(self.segs) else float(r.max() + r.min())
        return (float(c[0]), float(c[1]), d)

    def vertices(self):
        """Corners where two straight edges meet, collinear points dropped."""
        v = [s.pts[0] for s in self.segs]
        out = []
        for k, p in enumerate(v):
            a, b = v[k - 1], v[(k + 1) % len(v)]
            if abs((p[0] - a[0]) * (b[1] - p[1]) - (p[1] - a[1]) * (b[0] - p[0])) > 1e-6 or self.segs[k].kind != "line" or self.segs[k - 1].kind != "line":
                out.append(p)
        return out


@dataclass
class Region:
    outer: Contour
    holes: list

    @property
    def box(self):
        return self.outer.box

    def holds(self, p):
        return self.outer.holds(p) and not any(h.holds(p) for h in self.holes)

    def point(self):
        """A point of the region's material, well clear of its edges: what names it, `<sheet>@x,y`."""
        x0, y0, x1, y1 = self.box
        best = None
        for fy in (0.5, 0.25, 0.75, 0.1, 0.9):
            y = y0 + fy * (y1 - y0)
            xs = np.linspace(x0, x1, 801)
            inside = np.array([self.holds((x, y)) for x in xs])
            run, start = 0, 0
            for k, v in enumerate(list(inside) + [False]):
                if v and run == 0:
                    start = k
                run = run + 1 if v else 0
                if not v and k and inside[k - 1]:
                    n = k - start
                    if best is None or n > best[0]:
                        best = (n, (xs[start] + xs[k - 1]) / 2, y)
            if best and best[0] > 40:
                break
        return (round(float(best[1]), 2), round(float(best[2]), 2))


_cache: dict = {}


def contours(sheet: str) -> list[Contour]:
    """Every closed contour of a sheet, in mm in the sheet's frame."""
    if sheet in _cache:
        return _cache[sheet]
    root = ET.parse(SHEETS[sheet]).getroot()
    ns = "{http://www.w3.org/2000/svg}"
    scale = float(root.get("width").rstrip("m")) / float(root.get("viewBox").split()[2])
    out = []

    def walk(e, m):
        if e.tag in (ns + "defs", ns + "clipPath", ns + "metadata"):
            return
        m = m @ _mat(e.get("transform"))
        subs = _path(e.get("d")) if e.tag == ns + "path" else _rect(e) if e.tag == ns + "rect" else []
        k = math.sqrt(abs(np.linalg.det(m[:2, :2])))
        flip = np.linalg.det(m[:2, :2]) < 0
        tr = lambda p: tuple(float(v) * scale for v in (m @ [p[0], p[1], 1.0])[:2])
        for segs in subs:
            new = []
            for s in segs:
                if s.kind == "arc":
                    new.append(Seg("arc", [tr(p) for p in s.pts], tr(s.centre), s.radius * k * scale, s.sweep ^ int(flip)))
                else:
                    new.append(Seg(s.kind, [tr(p) for p in s.pts]))
            new = [s for s in new if s.kind != "line" or math.dist(*s.pts) > 1e-3]   # a closing step of under a micron
            c = Contour(new)
            if c.area > 1e-6:
                out.append(c)
        for ch in e:
            walk(ch, m)

    walk(root, np.eye(3))
    _cache[sheet] = out
    return out


_regions: dict = {}


def regions(sheet: str) -> list[Region]:
    """Outer contours with the holes directly inside them: nesting depth even is material's edge."""
    if sheet in _regions:
        return _regions[sheet]
    cs = sorted(contours(sheet), key=lambda c: -c.area)
    depth, parent = [], []
    for i, c in enumerate(cs):
        p = tuple(c.poly[0])
        inside = [j for j in range(i) if cs[j].holds(p) and cs[j].area > c.area]
        depth.append(len(inside))
        parent.append(inside[-1] if inside else None)   # the smallest one holding it
    regs = {i: Region(c, []) for i, c in enumerate(cs) if depth[i] % 2 == 0}
    for i, c in enumerate(cs):
        if depth[i] % 2 == 1:
            regs[parent[i]].holes.append(c)
    _regions[sheet] = list(regs.values())
    return _regions[sheet]


def region(sheet: str, x: float, y: float) -> Region:
    """The region holding the point (x, y) of the sheet's frame."""
    hit = [r for r in regions(sheet) if r.holds((x, y))]
    if len(hit) != 1:
        raise LookupError(f"{sheet}@{x},{y}: {len(hit)} regions hold it")
    return hit[0]


# ---------------------------------------------------------------- STL reading
def stl_mesh(name: str):
    """(vertices Nx3, triangles Mx3) of an STL body, vertices welded, in its file's frame, mm."""
    import struct
    raw = STLS[name].read_bytes()
    n = struct.unpack("<I", raw[80:84])[0]
    if 84 + 50 * n == len(raw):
        tri = np.frombuffer(raw, dtype=np.dtype([("n", "<f4", 3), ("v", "<f4", (3, 3)), ("a", "<u2")]), count=n, offset=84)["v"].astype(float)
    else:
        nums = re.findall(r"vertex\s+(\S+)\s+(\S+)\s+(\S+)", raw.decode("ascii", "ignore"))
        tri = np.array(nums, dtype=float).reshape(-1, 3, 3)
    v, inv = np.unique(np.round(tri.reshape(-1, 3), 4), axis=0, return_inverse=True)
    return v, inv.reshape(-1, 3)


def circle3(a, b, c):
    """Centre and diameter of the circle through three points of a plane (2D)."""
    (ax, ay), (bx, by), (cx, cy) = a, b, c
    d = 2 * (ax * (by - cy) + bx * (cy - ay) + cx * (ay - by))
    ux = ((ax * ax + ay * ay) * (by - cy) + (bx * bx + by * by) * (cy - ay) + (cx * cx + cy * cy) * (ay - by)) / d
    uy = ((ax * ax + ay * ay) * (cx - bx) + (bx * bx + by * by) * (ax - cx) + (cx * cx + cy * cy) * (bx - ax)) / d
    return (ux, uy), 2 * math.hypot(ax - ux, ay - uy)


# ---------------------------------------------------------------- the parts the bodies ship
# part -> (sheet, sheet thickness in mm, what it is, its regions as cadrev names them).
# The names of the stretcher's plates are read from their holes and finger joints and from
# Fig. 2 of the paper: the paper itself names only the carriage, the stationary bar, the motor
# mounting frames, the end-pieces, the mountings and the narrow and wide frames.
PARTS = {
    "carriage_plate": ("acryl6", 6, "carriage: the mobile bar's plate, 12 x M4-tapped d3.3 for six mountings, 9 slots for the wall's tabs",
                       ["206.95,76.8"]),
    "carriage_cover": ("acryl6", 6, "carriage: the box's closing plate, tabs on both long edges, no holes",
                       ["114.03,153.42"]),
    "carriage_wall": ("acryl6", 6, "carriage: a wall the rods cross, d15.2 for a linear bearing and d11 with 4 x d2.5 for a lead-screw nut at each end",
                      ["195.28,199.92", "195.28,246.92"]),
    "carriage_rib_tall": ("acryl6", 6, "carriage: a 45 x 46 cross plate of the box", ["318.62,387.24", "367.16,387.24"]),
    "carriage_rib_short": ("acryl6", 6, "carriage: a 45 x 40 cross plate of the box", ["318.62,436.57", "367.16,436.57"]),
    "bearing_retainer": ("acryl6", 6, "carriage: an oval over a bearing's end, d10 for the rod, two d3.1 for M3 into a wall's d2.5 pair",
                         ["331.64,330.03", "372.28,330.03", "331.64,344.59", "372.28,344.59"]),
    "stationary_bar": ("acryl6", 6, "the stationary bar, flat on the frame's end: 12 x M4-tapped d3.3 for six mountings, d5.3 and d5 on the profiles' slots",
                       ["48.75,290.92"]),
    "mounting": ("acryl6", 6, "a substrate mounting: two d4 for its M4 screws, two d3.3 central threads (M4), two d2.5 (M3) for the hooks",
                 ["410.55,488.48", "445.95,498.52", "481.59,488.48", "516.99,498.52", "410.55,530.39", "445.95,540.42",
                  "481.59,530.39", "516.99,540.42", "410.55,571.5", "445.95,581.53", "481.59,571.5", "516.99,581.53"]),
    "end_plate": ("acryl6", 6, "end-piece at the stationary end: four d8 for the ends of the lead screws (350 apart) and guide rods (270 apart)",
                  ["195.28,558.3"]),
    "end_cover": ("acryl6", 6, "end-piece at the stationary end, no rod holes: two d3.1 over the end plate's d2.5 pair", ["195.28,486.51"]),
    "motor_end_plate": ("acryl6", 6, "end-piece between the motor mounts: two d8 for the guide rods (270 apart), the D-sub cut-out",
                        ["49.28,342.62"]),
    "motor_end_cover": ("acryl6", 6, "end-piece between the motor mounts: a 50 x 20 window, two d3.06 over the motor end plate's d2.5 pair",
                        ["49.28,414.51"]),
    "corner_plate": ("acryl6", 6, "frame: 80 x 40 plate joining a long and a short profile, eight d5 on the slots' 20 mm pitch",
                     ["414.55,122.86", "534.98,122.86", "414.55,163.36", "534.98,163.36"]),
    "motor_base": ("acryl6", 6, "motor mounting frame: the plate on the profile, four d6", ["568.14,277.2", "568.14,333.08"]),
    "motor_face": ("acryl6", 6, "motor mounting frame: the plate the motor bolts to, d23 pilot and four d3 on a 31 mm square",
                   ["575.07,369.06", "575.07,424.93"]),
    "motor_gusset": ("acryl6", 6, "motor mounting frame: a triangular side plate",
                     ["578.17,495.25", "558.09,515.54", "578.17,557.52", "558.09,577.8"]),
    "switch_plate": ("acryl6", 6, "limit-switch plate: two d2 9.5 apart for the switch, four d5 on a 20 mm square", ["565.86,206.38"]),
    "holding_frame_narrow": ("acryl6", 6, "narrow frame that holds a substrate stretched off the device (0-5 mm)",
                             ["399.92,206.61", "399.92,254.18", "399.92,301.22", "399.92,346.65", "399.92,394.23", "399.92,441.27"]),
    "holding_frame_wide": ("acryl6", 6, "wide frame that holds a substrate stretched off the device (5-10 mm)",
                           ["468.52,206.74", "468.52,254.32", "468.52,301.36", "468.52,346.79", "468.52,394.37", "468.52,441.41"]),
    "mould_base": ("acryl3", 3, "mould: the base, four M4-tapped d3.3 for the frame's screws, four d3 for the posts",
                   ["85,515", "140,515", "30,570", "85,570", "140,570", "195,570"]),
    "mould_platform": ("acryl3", 3, "mould: the raised central platform, 20 x 20 with r5 corners",
                       ["15,475", "40,475", "65,475", "90,475", "115,475", "140,475"]),
    "mould_template": ("acryl3", 3, "mould: a 50 x 50 plate with a 20 x 20 r5 window and four d4, which the paper does not name",
                       ["40.42,498.33"]),
    "mould_ring": ("acryl3", 3, "mould: a d5 ring with a d3 hole, which the paper does not name",
                   ["176.81,517.41", "186.1,517.41", "176.81,523.41", "186.1,523.41", "176.81,529.41", "186.1,529.41",
                    "176.81,535.41", "186.1,535.41"]),
}
# The rest of the 3 mm sheet is the controller's housing, outside the target: every region wholly
# inside one of these rectangles of the sheet's frame.
HOUSING = [((0, 0), (600, 464)), ((226, 464), (600, 600))]


WITHIN = 0.0015     # how far the file's number may sit from a round one and still be read as it
_snap_miss = [0.0]


def snap(v: float) -> float:
    """The design value of a number of the file: 32.5 for 32.4999, and the file's own, to a micron, where it
    is not within WITHIN of a hundredth. The sheets were drawn by hand: their round numbers scatter by up to
    0.0015 mm (the corner plates' holes), which is more than the project's default tolerance of 0.001."""
    r = round(v, 2)
    r = r if abs(v - r) <= WITHIN else round(v, 3)
    _snap_miss[0] = max(_snap_miss[0], abs(v - r))
    return r


def _f(v):
    return f"{snap(v):.3f}".rstrip("0").rstrip(".") if abs(snap(v)) > 5e-4 else "0"


def part_regions(part: str) -> list[Region]:
    sheet, _t, _what, names = PARTS[part]
    return [region(sheet, *map(float, n.split(","))) for n in names]


def profile(part: str, n: int = 0) -> dict:
    """A part's outline off its nth region, in the region's own frame: origin at the top-left corner of
    its box on the sheet, u right and v DOWN as the sheet lies, mm, snapped to design values.

    Set WITHIN = 0 before the call for the file's own numbers to a micron.

    {"size": (w, h), "outer": [segment...], "holes": [{"d": .., "at": (u, v)} | {"segs": [segment...], "size", "at"}],
     "spurs": [...]}, the outline cleaned of the drawing's repeated points and spurs (see _clean),
    a segment ("line", p0, p1), ("arc", p0, p1, centre, r, sweep) with sweep 1 clockwise as seen on the sheet,
    or ("bezier", p0, c1, c2, p1). Mirror v for a right-handed part frame seen from the sheet's far side: a cut
    plate is its own mirror image.
    """
    r = part_regions(part)[n]
    x0, y0, x1, y1 = r.box
    loc = lambda p: (snap(p[0] - x0), snap(p[1] - y0))

    def segs(c):
        out = []
        for s in c.segs:
            if s.kind == "arc":
                out.append(("arc", loc(s.pts[0]), loc(s.pts[1]), loc(s.centre), snap(s.radius), s.sweep))
            else:
                out.append((s.kind, *[loc(p) for p in s.pts]))
        return out

    holes = []
    for h in r.holes:
        c = h.circle()
        hx0, hy0, hx1, hy1 = h.box
        holes.append({"d": snap(c[2]), "at": loc(c[:2])} if c else
                     {"segs": _clean(segs(h))[0], "size": (snap(hx1 - hx0), snap(hy1 - hy0)), "at": loc(((hx0 + hx1) / 2, (hy0 + hy1) / 2))})
    outer, spurs = _clean(segs(r.outer))
    return {"size": (snap(x1 - x0), snap(y1 - y0)), "outer": outer, "holes": holes, "spurs": spurs}


def _clean(segs):
    """A closed run of segments without what the drawing left in it: zero-length lines, a corner's point
    repeated along a straight edge, and spurs, where the line runs out past a corner and straight back.
    Returns (segments, spurs as (corner, tip))."""
    spurs = []
    changed = True
    while changed:
        changed = False
        out = []
        for s in segs:
            if s[0] == "line" and math.dist(s[1], s[2]) < 2e-3:
                changed = True
                continue
            out.append(s)
        segs = out
        n = len(segs)
        for i in range(n):
            a, b = segs[i], segs[(i + 1) % n]
            if a[0] != "line" or b[0] != "line":
                continue
            ux, uy = a[2][0] - a[1][0], a[2][1] - a[1][1]
            vx, vy = b[2][0] - b[1][0], b[2][1] - b[1][1]
            if abs(ux * vy - uy * vx) > 2e-3 * max(math.hypot(ux, uy), math.hypot(vx, vy)):
                continue
            if ux * vx + uy * vy < 0:           # straight back: a spur, kept to the longer run's end
                la, lb = math.hypot(ux, uy), math.hypot(vx, vy)
                spurs.append((b[2] if lb < la else a[1], a[2]))
            merged = ("line", a[1], b[2])
            segs = [merged if k == i else s for k, s in enumerate(segs) if k != (i + 1) % n]
            changed = True
            break
    return segs, spurs


def _signature(r: Region):
    """Points that fix a region up to a rigid motion: outline corners and hole centres, about the box centre."""
    x0, y0, x1, y1 = r.box
    c = np.array([(x0 + x1) / 2, (y0 + y1) / 2])
    pts = [np.array(s.pts[0]) - c for s in r.outer.segs] + [np.array(h.box).reshape(2, 2).mean(0) - c for h in r.holes]
    return np.array(pts)


def placement(a: Region, b: Region):
    """How region b lies against region a: (turn in degrees clockwise on the sheet, mirrored?, worst miss in mm)."""
    pa, pb = _signature(a), _signature(b)
    best = None
    for mirror in (False, True):
        for k in range(4):
            ang = math.radians(90 * k)
            m = np.array([[math.cos(ang), -math.sin(ang)], [math.sin(ang), math.cos(ang)]])
            q = (pa * ([-1, 1] if mirror else [1, 1])) @ m.T
            if len(q) != len(pb):
                continue
            miss = max(float(np.min(np.hypot(*(pb - p).T))) for p in q)
            if best is None or miss < best[2] - 1e-6:
                best = (90 * k, mirror, miss)
    return best


def describe_part(part: str):
    sheet, t, what, names = PARTS[part]
    regs = part_regions(part)
    _snap_miss[0] = 0.0
    pr = profile(part)
    miss = _snap_miss[0]
    w, h = pr["size"]
    print(f"\n{part}: {what}")
    print(f"  {len(regs)} cut, {sheet}, sheet thickness {t} (quoted); box {_f(w)} x {_f(h)}; frame: origin at the box's top-left "
          f"corner on the sheet, u right, v down, thickness square to the sheet")
    kinds = {k: sum(1 for s in pr["outer"] if s[0] == k) for k in ("line", "arc", "bezier")}
    print(f"  outline: {kinds['line']} lines, {kinds['arc']} arcs, {kinds['bezier']} beziers")
    if kinds["line"] <= 160:
        path = []
        for s in pr["outer"]:
            if s[0] == "line":
                path.append(f"({_f(s[1][0])},{_f(s[1][1])})")
            elif s[0] == "arc":
                path.append(f"({_f(s[1][0])},{_f(s[1][1])}) arc r{_f(s[4])} about ({_f(s[3][0])},{_f(s[3][1])}) {'cw' if s[5] else 'ccw'} to")
            else:
                path.append(f"({_f(s[1][0])},{_f(s[1][1])}) bezier [{_f(s[2][0])},{_f(s[2][1])}] [{_f(s[3][0])},{_f(s[3][1])}] to")
        print("  outline, closed: " + " ".join(path))
    tally: dict = {}
    for hole in pr["holes"]:
        if "d" in hole:
            tally.setdefault(f"d{_f(hole['d'])}", []).append(hole["at"])
        else:
            rr = sorted({snap(s[4]) for s in hole["segs"] if s[0] == "arc"})
            kind = "rect" if all(s[0] == "line" for s in hole["segs"]) else ("cut-out r" + "/".join(_f(v) for v in rr) if rr else "cut-out (bezier corners)")
            tally.setdefault(f"{kind} {_f(hole['size'][0])} x {_f(hole['size'][1])}", []).append(hole["at"])
    for key, at in tally.items():
        print(f"  {len(at)} x {key} centred at: " + " ".join(f"({_f(a)},{_f(b)})" for a, b in sorted(at)))
    for corner, tip in pr["spurs"]:
        print(f"  the file's outline runs a spur out to ({_f(tip[0])},{_f(tip[1])}) and straight back: no edge of the part, left out above")
    print(f"  the design values above sit within {miss:.4f} of the file's own numbers")
    for n, r in enumerate(regs):
        x0, y0, _, _ = r.box
        turn, mirror, miss = placement(regs[0], r)
        print(f"  region {sheet}@{names[n]}: box top-left ({x0:.3f},{y0:.3f}); the first region turned {turn} deg cw"
              f"{', mirrored' if mirror else ''}, worst miss {miss:.4f}")


# ---------------------------------------------------------------- STL bodies
def _loops(v, t, z):
    """Boundary loops, as vertex indices, of the triangles lying in the plane z."""
    from collections import Counter, defaultdict
    cnt = Counter()
    for tri in t:
        if all(abs(v[k][2] - z) < 1e-6 for k in tri):
            for i in range(3):
                a, b = int(tri[i]), int(tri[(i + 1) % 3])
                cnt[(min(a, b), max(a, b))] += 1
    adj = defaultdict(list)
    for (a, b), c in cnt.items():
        if c == 1:
            adj[a].append(b)
            adj[b].append(a)
    seen, loops = set(), []
    for s in adj:
        if s in seen:
            continue
        loop, prev, cur = [s], None, s
        seen.add(s)
        while True:
            nxt = [n for n in adj[cur] if n != prev and n not in seen]
            if not nxt:
                break
            prev, cur = cur, nxt[0]
            loop.append(cur)
            seen.add(cur)
        loops.append(loop)
    return loops


def _miss(p, prims):
    """Distance from a point to the nearest design line ('x', c) / ('y', c) or circle ('c', cx, cy, r)."""
    return min(abs(p[0] - q[1]) if q[0] == "x" else abs(p[1] - q[1]) if q[0] == "y"
               else abs(math.hypot(p[0] - q[1], p[1] - q[2]) - q[3]) if q[0] == "c"
               else abs((p[0] - q[1]) * q[3] + (p[1] - q[2]) * q[4]) for q in prims)


# Design values of the two printed bodies, each proved below against every mesh corner.
MOULD_FRAME = {"side": 50, "height": 3.5, "screw_hole_d": 4, "screw_hole_at": 20, "opening": 30, "lobe_d": 10, "lobe_at": 12.5}
CLAMP = {"length": 33, "depth": 11.5, "height": 5, "base_t": 1, "hole_d": 3, "hole_x": 12.5, "hole_y": 7.5, "lobe_d": 8,
         "back_y": 10, "wall_outer_r": 5, "wall_inner_r": 4, "wall_arc_x": 5, "wall_t": 1, "wall_outer_y": 5, "wall_inner_y": 4,
         "notch_half_width": 9, "flank_foot_x": 10.6569}


def stl_bodies():
    """{'clamp': CLAMP, 'moldframe': MOULD_FRAME}: the design values model.py builds the two printed parts from."""
    return {"clamp": CLAMP, "moldframe": MOULD_FRAME}


def describe_stl():
    v, t = stl_mesh("moldframe")
    m = MOULD_FRAME
    print("\nmould_frame: body moldframe (MoldFrame.stl), one solid, %d corners, %d facets" % (len(v), len(t)))
    print("  frame of the file: origin at the centre of the bottom face, x and y along the square's sides, z up through the height")
    print(f"  box {_f(np.ptp(v[:, 0]))} x {_f(np.ptp(v[:, 1]))} x {_f(np.ptp(v[:, 2]))}: x {_f(v[:, 0].min())}..{_f(v[:, 0].max())}, "
          f"y {_f(v[:, 1].min())}..{_f(v[:, 1].max())}, z {_f(v[:, 2].min())}..{_f(v[:, 2].max())}; a prism, every corner at z 0 or {_f(m['height'])}")
    a, o, la, lr, s = m["screw_hole_at"], m["opening"] / 2, m["lobe_at"], m["lobe_d"] / 2, m["side"] / 2
    worst = {"outer": 0.0, "hole": 0.0, "opening": 0.0}
    for loop in _loops(v, t, 0.0):
        pts = v[loop][:, :2]
        ext = np.abs(pts).max()
        if ext > 24:
            worst["outer"] = max(worst["outer"], max(_miss(p, [("x", s), ("x", -s), ("y", s), ("y", -s)]) for p in pts))
        elif np.abs(pts).min() > 17:
            c, d = circle3(pts[0], pts[len(pts) // 3], pts[2 * len(pts) // 3])
            print(f"  screw hole: d {_f(d)} through three rim corners, centre ({_f(c[0])},{_f(c[1])}), {len(pts)} rim corners")
            worst["hole"] = max(worst["hole"], max(abs(math.hypot(*(p - (math.copysign(a, c[0]), math.copysign(a, c[1])))) - m["screw_hole_d"] / 2) for p in pts))
        else:
            prims = [("x", o), ("x", -o), ("y", o), ("y", -o)] + [("c", sx * la, sy * la, lr) for sx in (1, -1) for sy in (1, -1)]
            worst["opening"] = max(worst["opening"], max(_miss(p, prims) for p in pts))
            print(f"  opening: {len(pts)} corners, extent +-{_f(np.abs(pts).max())}")
    print(f"  design: {m['side']} square, {m['height']} high; four d{m['screw_hole_d']} screw holes at (+-{a}, +-{a}); the opening a "
          f"{m['opening']} square joined with four d{m['lobe_d']} lobes about (+-{la}, +-{la}), sharp where they meet")
    print("  worst miss of a mesh corner from that design: " + ", ".join(f"{k} {w:.4f}" for k, w in worst.items()))

    v, t = stl_mesh("clamp")
    c = CLAMP
    print("\nclamp: body clamp (Clamp.stl), one solid, %d corners, %d facets" % (len(v), len(t)))
    print("  frame of the file: origin on the bottom face at the middle of the notched edge (y 0); x along the line of the two holes, "
          "y from the notch to the back edge, z up through the height")
    print(f"  box of its corners x {v[:, 0].min():.4f}..{v[:, 0].max():.4f}, y {v[:, 1].min():.4f}..{v[:, 1].max():.4f}, z {_f(v[:, 2].min())}..{_f(v[:, 2].max())}; "
          f"corners at z 0, {_f(c['base_t'])} and {_f(c['height'])} only")
    hx, hy, lr = c["hole_x"], c["hole_y"], c["lobe_d"] / 2
    ax, ro, ri = c["wall_arc_x"], c["wall_outer_r"], c["wall_inner_r"]
    k = math.sqrt(0.5)
    base = [("y", 0.0), ("y", c["back_y"]), ("c", hx, hy, lr), ("c", -hx, hy, lr), ("c", ax, 0, ri), ("c", -ax, 0, ri), ("y", c["wall_inner_y"]),
            ("l", hx + lr * k, hy - lr * k, k, -k), ("l", -hx - lr * k, hy - lr * k, -k, -k)]
    wall = [("y", 0.0), ("c", ax, 0, ro), ("c", -ax, 0, ro), ("c", ax, 0, ri), ("c", -ax, 0, ri), ("y", c["wall_outer_y"]), ("y", c["wall_inner_y"])]
    worst = {"base outline": 0.0, "holes": 0.0, "wall": 0.0}
    for z in (0.0, 1.0, 5.0):
        for loop in _loops(v, t, z):
            pts = v[loop][:, :2]
            if np.ptp(pts[:, 0]) < 4:
                ctr, d = circle3(pts[0], pts[len(pts) // 3], pts[2 * len(pts) // 3])
                if z == 0.0:
                    print(f"  hole: d {_f(d)} through three rim corners, centre ({ctr[0]:.4f},{ctr[1]:.4f}), {len(pts)} rim corners")
                worst["holes"] = max(worst["holes"], max(abs(math.hypot(p[0] - math.copysign(hx, ctr[0]), p[1] - hy) - c["hole_d"] / 2) for p in pts))
            elif z == 5.0:
                worst["wall"] = max(worst["wall"], max(_miss(p, wall) for p in pts))
            else:
                worst["base outline"] = max(worst["base outline"], max(_miss(p, base + (wall if z == 1.0 else [])) for p in pts))
    print(f"  design, base (z 0..{c['base_t']}): two d{c['hole_d']} holes at (+-{hx}, {hy}), each in a d{c['lobe_d']} lobe about its centre; back edge y {c['back_y']}; "
          f"each lobe leaves at 45 deg on a tangent flank down to (+-{c['flank_foot_x']}, 0); a notch +-{c['notch_half_width']} wide in the y 0 edge, "
          f"r{ri} about (+-{ax}, 0) up to y {c['wall_inner_y']}")
    print(f"  design, wall (z 0..{c['height']}): {c['wall_t']} thick around the notch, between r{ri} and r{ro} about (+-{ax}, 0) and between y {c['wall_inner_y']} and y {c['wall_outer_y']}; "
          f"its outer face is a 20 wide end with r{ro} corners")
    print(f"  design envelope {c['length']} x {c['depth']} x {c['height']} (the lobes' extremes are no mesh corner)")
    print("  worst miss of a mesh corner from that design: " + ", ".join(f"{k_} {w:.4f}" for k_, w in worst.items()))


def check_cover():
    """Every region of both sheets is a part's or the housing's."""
    for sheet in SHEETS:
        claimed = []
        for part, (s, _t, _w, names) in PARTS.items():
            if s == sheet:
                claimed += [id(r) for r in part_regions(part)]
        assert len(claimed) == len(set(claimed)), "a region is named twice"
        rest = [r for r in regions(sheet) if id(r) not in claimed]
        out = [r for r in rest if not any(a[0] <= r.box[0] and a[1] <= r.box[1] and r.box[2] <= b[0] and r.box[3] <= b[1] for a, b in HOUSING)]
        print(f"\n{sheet}: {len(regions(sheet))} regions, {len(claimed)} in parts, {len(rest) - len(out)} in the housing rectangles, {len(out)} unplaced")


def draw(sheet: str):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    out = HERE / "figures/sheets"
    out.mkdir(parents=True, exist_ok=True)
    owner = {id(r): p for p, (s, *_r) in PARTS.items() if s == sheet for r in part_regions(p)}
    fig, ax = plt.subplots(figsize=(24, 24))
    for r in regions(sheet):
        p = np.vstack([r.outer.poly, r.outer.poly[:1]])
        ax.fill(p[:, 0], p[:, 1], color="#cfe3f5" if id(r) in owner else "#e6e6e6", zorder=1)
        ax.plot(p[:, 0], p[:, 1], "k-", lw=0.7, zorder=3)
        for h in r.holes:
            q = np.vstack([h.poly, h.poly[:1]])
            ax.fill(q[:, 0], q[:, 1], color="white", zorder=2)
            ax.plot(q[:, 0], q[:, 1], "r-", lw=0.6, zorder=3)
        x0, y0, x1, y1 = r.box
        ax.text((x0 + x1) / 2, (y0 + y1) / 2, owner.get(id(r), "housing"), fontsize=5, ha="center", color="blue", zorder=4)
    ax.set_aspect("equal")
    ax.set_xlim(0, 600)
    ax.set_ylim(600, 0)
    ax.grid(True, lw=0.2)
    ax.set_xticks(range(0, 601, 20))
    ax.set_yticks(range(0, 601, 20))
    ax.tick_params(labelsize=6)
    fig.savefig(out / f"{sheet}.png", dpi=100, bbox_inches="tight")
    plt.close(fig)
    print("wrote", out / f"{sheet}.png")


if __name__ == "__main__":
    print("Cut sheets: values in mm in each region's own frame, snapped to design values (see snap).")
    for part in PARTS:
        describe_part(part)
    describe_stl()
    check_cover()
    if "--draw" in sys.argv:
        for s in SHEETS:
            draw(s)
