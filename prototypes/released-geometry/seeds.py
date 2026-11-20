"""PROTOTYPE for #246, throwaway: the seeded errors.

Each seed copies an unmodified example (made without build/) and appends to its model.py a
wrapper around build(p): a param read off (as an agent's wrong value would be, datums moving with
it), or an edit of the built part (a hole filled, cut, moved; the part turned, its datums with it).

    python seeds.py <base dir holding the three examples> <seeds dir>   # writes one copy per seed
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

# id: (example, error kind, what, shape checks the comparison runs, param overrides, part edit)
SEEDS = {
    # centrifuge: STEP bodies
    "C1": ("centrifuge", "bore 2% off", "body bore 126 -> 128.52", ["body-shape"],
           {"body_bore_d": "v * 1.02"}, ""),
    "C2": ("centrifuge", "hole moved", "plate's four screw holes 0.5 out (boss_pcd + 1)",
           ["plate-shape"], {"boss_pcd": "v + 1.0"}, ""),
    "C3": ("centrifuge", "feature missing", "plate's fourth screw hole left out", ["plate-shape"], {},
           """
    n = int(p.screw_n)
    x, z = polar(p.boss_pcd / 2, p.boss_angle + (n - 1) * 360 / n)
    out["parts"]["plate"] = out["parts"]["plate"] + cyl_y(p.plate_hole_d / 2, -p.plate_t, 0, x, z)
"""),
    "C4": ("centrifuge", "feature added", "a 3 mm hole through the body's deck", ["body-shape"], {},
           """
    x, z = polar(30, 45)
    out["parts"]["body"] = out["parts"]["body"] - cyl_y(1.5, -p.deck_t - 0.5, 0.5, x, z)
"""),
    "C5": ("centrifuge", "turned one feature over",
           "body turned 180 deg about its axis, onto its other fan hole", ["body-shape"], {},
           """
    out["parts"]["body"] = Rot(0, 180, 0) * out["parts"]["body"]
    for k, (x, y, z) in list(out["datums"].items()):
        if k.startswith("body."):
            out["datums"][k] = (-x, y, -z)
"""),
    "C6": ("centrifuge", "param off a little", "body diameter + 0.005", ["body-shape"],
           {"body_d": "v + 0.005"}, ""),
    # compact-sspg: STL bodies
    "K1": ("compact-sspg", "bore 2% off", "planet bore 10 -> 10.2", ["planet-shape"],
           {"planet_bore": "v * 1.02"}, ""),
    "K1b": ("compact-sspg", "bore 2% off", "retainer bore x 1.02", ["retainer-shape"],
            {"ret_id": "v * 1.02"}, ""),
    "K2": ("compact-sspg", "hole moved", "retainer's bolt holes 0.5 out (ret_hole_d + 1)",
           ["retainer-shape"], {"ret_hole_d": "v + 1.0"}, ""),
    "K3": ("compact-sspg", "feature missing", "retainer's last bolt hole left out",
           ["retainer-shape"], {}, """
    n = int(p.ret_n_holes)
    out["parts"]["retainer"] = out["parts"]["retainer"] + at(
        p.ret_hole_d / 2, 90 + (n - 1) * 360 / n, 0) * Cylinder(p.ret_hole / 2, p.ret_t, align=UP)
"""),
    "K4": ("compact-sspg", "feature added", "a bolt hole added between the retainer's first two",
           ["retainer-shape"], {}, """
    n = int(p.ret_n_holes)
    out["parts"]["retainer"] = out["parts"]["retainer"] - at(
        p.ret_hole_d / 2, 90 + 180 / n, 0) * Cylinder(p.ret_hole / 2, p.ret_t, align=UP)
"""),
    "K5": ("compact-sspg", "turned one feature over", "sun turned one tooth about its axis",
           ["sun-shape"], {}, """
    import math as _m
    a = 360 / p.z_sun
    out["parts"]["sun_gear"] = Rot(0, 0, a) * out["parts"]["sun_gear"]
    c, s = _m.cos(_m.radians(a)), _m.sin(_m.radians(a))
    for k, (x, y, z) in list(out["datums"].items()):
        if k.startswith("sun_gear."):
            out["datums"][k] = (c * x - s * y, s * x + c * y, z)
"""),
    "K6": ("compact-sspg", "param off by less than the facet sag",
           "retainer outside diameter + 0.01 (its rim's facets sag 0.13)", ["retainer-shape"],
           {"ret_od": "v + 0.01"}, ""),
    "K6b": ("compact-sspg", "param off by less than the facet sag",
            "planet counterbore + 0.01", ["planet-shape"], {"planet_cb_d": "v + 0.01"}, ""),
    # cell-stretcher: STL clamp, cut-file mould base
    "Z1": ("cell-stretcher", "bore 2% off", "clamp post hole 3 -> 3.06", ["shape-clamp"],
           {"cl_hole": "v * 1.02"}, ""),
    "Z2": ("cell-stretcher", "hole moved", "clamp's second post hole 0.5 along x, its datum too",
           ["shape-clamp"], {}, """
    r_cl = (p.cl_L - p.cl_pitch) / 2
    hy, px = p.cl_W - r_cl, p.cl_pitch / 2
    cl = out["parts"]["stretch_clamp"] + disc(px, hy, p.cl_hole, p.cl_t)
    out["parts"]["stretch_clamp"] = cl - disc(px + 0.5, hy, p.cl_hole, p.cl_t)
    for k in ("stretch_clamp.hole_b", "stretch_clamp.hole_b_w"):
        x, y, z = out["datums"][k]
        out["datums"][k] = (x + 0.5, y, z)
"""),
    "Z3": ("cell-stretcher", "feature missing", "clamp's second post hole left out",
           ["shape-clamp"], {}, """
    r_cl = (p.cl_L - p.cl_pitch) / 2
    hy, px = p.cl_W - r_cl, p.cl_pitch / 2
    out["parts"]["stretch_clamp"] = out["parts"]["stretch_clamp"] + disc(px, hy, p.cl_hole, p.cl_t)
"""),
    "Z4": ("cell-stretcher", "feature added", "a 2 mm hole in the clamp's plate", ["shape-clamp"],
           {}, """
    out["parts"]["stretch_clamp"] = out["parts"]["stretch_clamp"] - disc(0, 7.5, 2, p.cl_t)
"""),
    "Z6": ("cell-stretcher", "param off by less than the facet sag", "clamp post hole + 0.01",
           ["shape-clamp"], {"cl_hole": "v + 0.01"}, ""),
    "Y1": ("cell-stretcher", "bore 2% off", "mould base post holes x 1.02 (cut file)",
           [f"shape-mould_base-{k}" for k in range(1, 7)], {"straw_d": "v * 1.02"}, ""),
    "Y2": ("cell-stretcher", "hole moved", "mould base's first corner hole 0.5 along x (cut file)",
           [f"shape-mould_base-{k}" for k in range(1, 7)], {}, """
    c = p.mb_corner
    b = out["parts"]["mould_base"] + disc(c, c, p.d_m4tap, p.t3)
    out["parts"]["mould_base"] = b - disc(c + 0.5, c, p.d_m4tap, p.t3)
"""),
    "Y3": ("cell-stretcher", "feature missing", "mould base's last corner hole left out (cut file)",
           [f"shape-mould_base-{k}" for k in range(1, 7)], {}, """
    c, mw = p.mb_corner, p.mb_side
    out["parts"]["mould_base"] = out["parts"]["mould_base"] + disc(mw - c, mw - c, p.d_m4tap, p.t3)
"""),
    "Y4": ("cell-stretcher", "feature added", "a 3 mm hole at the mould base's centre (cut file)",
           [f"shape-mould_base-{k}" for k in range(1, 7)], {}, """
    mw = p.mb_side
    out["parts"]["mould_base"] = out["parts"]["mould_base"] - disc(mw / 2, mw / 2, 3, p.t3)
"""),
}

WRAPPER = '''

# ---------------------------------------------------------------- PROTOTYPE SEED {sid} (#246)
_seed_build = build


class _SeedParams:
    def __init__(self, p):
        self._p = p

    def __getattr__(self, name):
        v = getattr(self._p, name)
        over = {over}
        return eval(over[name], {{"v": v}}) if name in over else v


def build(p):
    p = _SeedParams(p)
    out = _seed_build(p)
{edit}
    return out
'''


def write(base: Path, seeds: Path) -> None:
    for sid, (example, _, _, _, over, edit) in SEEDS.items():
        dst = seeds / sid
        if dst.exists():
            shutil.rmtree(dst)
        shutil.copytree(base / example, dst, ignore=shutil.ignore_patterns("build"))
        model = dst / "model.py"
        model.write_text(
            model.read_text()
            + WRAPPER.format(sid=sid, over=repr(over), edit=edit.rstrip() or "    pass")
        )


if __name__ == "__main__":
    write(Path(sys.argv[1]), Path(sys.argv[2]))
