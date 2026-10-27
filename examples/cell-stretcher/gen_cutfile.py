"""Writes the cut-file shape checks and their sheet datums.

Run:  uv run --project <skill>/tool python -I gen_cutfile.py
Reads evidence.src.yaml and checks.src.yaml (hand-written) and writes evidence.yaml and
checks.yaml with, appended, one shape check per cut-file region a part reproduces and the
sheet datums those checks pair with. Each part's anchors are given in the frame of one
representative region (bbox corner, x right, y down); every other region of the part is
matched to it by the bbox symmetry (turn or flip) that carries its holes and corners onto
the representative's, and the anchors are carried along.
"""

import sys
from pathlib import Path

import numpy as np
from matplotlib.path import Path as MPath
from svgelements import SVG, Path as SPath, Shape

HERE = Path(__file__).resolve().parent
K = 25.4 / 96

# part: (sheet, representative point, tol, [(datum, x, y)] in the representative's frame)
PARTS = {
    "end_far_in": ("acryl6mm", (195.28, 558.3), 0.05, [("m3_l", 71.336, 12), ("screw_l", 20, 24), ("rod_l", 60, 24)]),
    "end_far_out": ("acryl6mm", (195.28, 486.51), 0.05, [("m3_l", 71.336, 12), ("m3_r", 318.664, 12), ("m6_l", 10, 61)]),
    "end_motor_in": ("acryl6mm", (49.28, 342.62), 1.2, [("rod_l", 12, 24), ("rod_r", 282, 24), ("m3_l", 23.336, 12)]),
    "end_motor_out": ("acryl6mm", (49.28, 414.51), 0.3, [("m3_l", 23.336, 12), ("m3_r", 270.664, 12), ("m5_l", 14.5, 61)]),
    "carriage_top": ("acryl6mm", (114.03, 153.42), 0.05, [("p1", 80, 22.5), ("p2", 195, 22.5), ("p3", 87, 42)]),
    "carriage_face": ("acryl6mm", (195.28, 246.92), 0.05, [("brg_l", 60, 19), ("nut_r", 370, 19), ("mid", 195, 23)]),
    "carriage_flange": ("acryl6mm", (206.95, 76.8), 0.05, [("h1", 14, 67.5), ("h12", 234, 67.5), ("p_mid", 124, 22.5)]),
    "carriage_partition": ("acryl6mm", (318.62, 387.24), 0.05, [("p1", 22.5, 23), ("p2", 3, 23), ("p3", 22.5, 9)]),
    "carriage_end": ("acryl6mm", (318.62, 436.57), 0.05, [("p1", 22.5, 23), ("p2", 3, 23), ("p3", 22.5, 9)]),
    "stat_bar": ("acryl6mm", (48.75, 290.92), 0.05, [("m4_1", 85, 7.5), ("m5_a", 10, 10), ("m5_b", 380, 30)]),
    "mount_plate": ("acryl6mm", (410.55, 488.48), 0.05, [("post_a", 5.05, 5.025), ("post_b", 29.95, 5.025), ("m4_a", 7.5, 32.973)]),
    "frame_wide": ("acryl6mm", (468.52, 206.74), 0.5, [("s1", 4.67, 22.286), ("s2", 68.269, 22.286), ("s3", 36.4695, 2.3)]),
    "frame_narrow": ("acryl6mm", (399.92, 206.61), 0.5, [("s1", 4.896, 22.286), ("s2", 61.996, 22.286), ("s3", 33.446, 2.3)]),
    "corner_plate": ("acryl6mm", (414.55, 163.36), 0.05, [("a", 10, 10), ("b", 70, 10), ("c", 10, 30)]),
    "switch_plate": ("acryl6mm", (565.86, 206.38), 0.05, [("sw_a", 15.14, 7.75), ("m5_a", 10, 30), ("m5_d", 30, 50)]),
    "rod_flange": ("acryl6mm", (331.64, 344.59), 0.05, [("c", 18.177, 10.294), ("a", 5.427, 10.294), ("top_pt", 18.177, 5.147)]),
    "motor_face": ("acryl6mm", (575.07, 424.93), 0.05, [("c", 27, 27), ("h1", 11.5, 11.5), ("h2", 42.5, 11.5)]),
    "motor_base": ("acryl6mm", (568.14, 333.08), 0.05, [("h1", 17, 15), ("h2", 37, 15), ("h3", 17, 45)]),
    "motor_gusset": ("acryl6mm", (558.09, 577.8), 0.05, [("a", 3, 15), ("b", 27, 51), ("c", 9, 45)]),
    "mould_base": ("acryl3mm", (85, 570), 0.05, [("post_1", 12.5, 12.5), ("post_2", 37.5, 12.5), ("post_3", 12.5, 37.5)]),
    "platform_jig": ("acryl3mm", (7, 492), 0.05, [("h1", 5, 5), ("h2", 45, 5), ("h3", 5, 45)]),
    "platform": ("acryl3mm", (140, 475), 0.05, [("p_a", 5, 5), ("p_b", 15, 5), ("top_c", 10, 10)]),
    "post_ring": ("acryl3mm", (178.689, 522), 0.05, [("c", 2.5, 2.5), ("mid_e", 4.5, 2.5), ("mid_n", 2.5, 4.5)]),
}
FILES = {"acryl6mm": "sources/Acryl6MM.svg", "acryl3mm": "sources/Acryl3MM.svg"}


def area(P):
    x, y = P[:, 0], P[:, 1]
    return 0.5 * abs(np.dot(x, np.roll(y, 1)) - np.dot(y, np.roll(x, 1)))


def regions(fn):
    svg = SVG.parse(str(HERE / fn), reify=True, ppi=96)
    loops = []
    for el in svg.elements():
        if not isinstance(el, Shape):
            continue
        path = SPath(el)
        path.reify()
        for sp in path.as_subpaths():
            sp = SPath(sp)
            if sp.length() == 0:
                continue
            n = min(4000, max(16, int(sp.length() * K / 0.2)))
            P = np.array([[q.x, q.y] for q in (sp.point(t) for t in np.linspace(0, 1, n))]) * K
            verts = np.array([[s.end.x, s.end.y] for s in sp if type(s).__name__ != "Move"]) * K
            if area(P) > 1e-6:
                loops.append((P, verts))
    loops.sort(key=lambda lv: -area(lv[0]))
    paths = [MPath(P) for P, _ in loops]
    depth, parent = [], []
    for i, (P, _) in enumerate(loops):
        cs = [j for j in range(i) if paths[j].contains_points(P[:: max(1, len(P) // 20)]).all()]
        depth.append(len(cs))
        parent.append(cs[-1] if cs else None)
    out = []
    for i, (P, V) in enumerate(loops):
        if depth[i] % 2:
            continue
        holes = [j for j in range(len(loops)) if parent[j] == i and depth[j] == depth[i] + 1]
        mn, mx = P.min(0), P.max(0)
        feats = [(loops[j][0].min(0) + loops[j][0].max(0)) / 2 for j in holes] + list(V)
        out.append({"min": mn, "size": mx - mn, "outer": paths[i], "holes": [paths[j] for j in holes],
                    "feats": np.array(feats) - mn})
    return out


def transforms(w, h):
    """The eight bbox symmetries: rep-frame point -> region-frame point, with the region's size."""
    return [
        (lambda x, y: (x, y), (w, h)), (lambda x, y: (w - x, y), (w, h)),
        (lambda x, y: (x, h - y), (w, h)), (lambda x, y: (w - x, h - y), (w, h)),
        (lambda x, y: (y, x), (h, w)), (lambda x, y: (h - y, x), (h, w)),
        (lambda x, y: (y, w - x), (h, w)), (lambda x, y: (h - y, w - x), (h, w)),
    ]


def inside(r, x, y):
    return r["outer"].contains_point((x, y)) and not any(hp.contains_point((x, y)) for hp in r["holes"])


def interior_point(r):
    mn, sz = r["min"], r["size"]
    for fy in np.linspace(0.05, 0.95, 37):
        for fx in np.linspace(0.05, 0.95, 37):
            x, y = mn[0] + fx * sz[0], mn[1] + fy * sz[1]
            ok = all(inside(r, x + dx, y + dy) for dx in (-0.3, 0, 0.3) for dy in (-0.3, 0, 0.3))
            if ok:
                return round(x, 2), round(y, 2)
    raise SystemExit("no interior point")


def main():
    regs = {s: regions(f) for s, f in FILES.items()}
    used = {s: set() for s in regs}
    checks, datums = [], []
    for part, (sheet, rp, tol, anchors) in PARTS.items():
        rs = regs[sheet]
        rep = next(r for r in rs if inside(r, *rp))
        w, h = rep["size"]
        k = 0
        for ri, r in enumerate(rs):
            best = None
            for T, (tw, th) in transforms(w, h):
                if abs(tw - r["size"][0]) > 0.05 or abs(th - r["size"][1]) > 0.05:
                    continue
                if len(r["feats"]) != len(rep["feats"]):
                    continue
                mapped = np.array([T(*f) for f in rep["feats"]])
                dmax = max(np.min(np.hypot(*(r["feats"] - m).T)) for m in mapped)
                if dmax < 0.05 and (best is None or dmax < best[0]):
                    best = (dmax, T)
            if best is None:
                continue
            if ri in used[sheet]:
                sys.exit(f"region {ri} of {sheet} matched twice")
            used[sheet].add(ri)
            k += 1
            T = best[1]
            pairs = []
            for name, x, y in anchors:
                sx, sy = T(x, y)
                dn = f"{sheet}.{part}_{k}_{name}"
                datums.append((dn, round(r["min"][0] + sx, 4), round(r["min"][1] + sy, 4)))
                pairs.append(f"[{part}.{name}, {dn}]")
            ip = interior_point(r)
            checks.append(f"  - {{id: shape-{part}-{k}, kind: shape, part: {part}, body: \"{sheet}@{ip[0]},{ip[1]}\", "
                          f"along: z, tol: {tol},\n     pairs: [{', '.join(pairs)}]}}")
        print(f"{part}: {k} regions", file=sys.stderr)
    for s, rs in regs.items():
        left = [interior_point(r) for i, r in enumerate(rs) if i not in used[s]]
        print(f"{s}: {len(rs)} regions, {len(left)} unmatched", file=sys.stderr)
    head = "# Written by gen_cutfile.py from {src}; edit {src}, then rerun gen_cutfile.py.\n"
    ev = (HERE / "evidence.src.yaml").read_text()
    dl = "\n".join(f"  {n}: [{x}, {y}]" for n, x, y in datums)
    ev = ev.replace("# @CUTFILE-DATUMS@", "# cut-file sheet datums (gen_cutfile.py)\n" + dl)
    (HERE / "evidence.yaml").write_text(head.format(src="evidence.src.yaml") + ev)
    ck = (HERE / "checks.src.yaml").read_text()
    ck = ck.replace("# @CUTFILE-CHECKS@", "# cut-file shape checks (gen_cutfile.py)\n" + "\n".join(checks))
    (HERE / "checks.yaml").write_text(head.format(src="checks.src.yaml") + ck)


if __name__ == "__main__":
    main()
