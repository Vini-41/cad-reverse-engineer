"""Parametric model. Reads every dimension from p (params.yaml); holds no dimension literals.

A cut part is built in its region's frame, as read_bodies.py prints it: x = u, y = v as the sheet lies,
z through the sheet's thickness. The two printed parts are built in the frames of their STL files.
World frame of the assembly: x across the unit, from the side of the first long profile; y along the rods,
from the long profiles' ends at the stationary end towards the motors; z up from the profiles' underside.
"""

import math

from build123d import *  # noqa: F403

X, Y, Z = (1, 0, 0), (0, 1, 0), (0, 0, 1)
NX, NY, NZ = (-1, 0, 0), (0, -1, 0), (0, 0, -1)


# ----------------------------------------------------------------------------- sketch helpers
def poly(pts):
    return make_face(Polyline(*pts, close=True))


def disc(u, v, d):
    return Pos(u, v) * Circle(d / 2)


def rect(u0, v0, u1, v1):
    return poly([(u0, v0), (u1, v0), (u1, v1), (u0, v1)])


def bez_box(u0, v0, u1, v1, du, dv, hu, hv):
    """A box whose corners are each one cubic Bezier spanning du x dv with handles hu and hv, as the sheets
    draw their rounded cut-outs. A straight side of no length is left out."""
    pts = [(u0 + du, v0), (u1 - du, v0), (u1, v0 + dv), (u1, v1 - dv), (u1 - du, v1), (u0 + du, v1), (u0, v1 - dv), (u0, v0 + dv)]
    handles = [((hu, 0), (0, hv)), ((0, hv), (-hu, 0)), ((-hu, 0), (0, -hv)), ((0, -hv), (hu, 0))]
    edges = []
    for k, (out, into) in enumerate(handles):
        a, b, c = pts[2 * k], pts[2 * k + 1], pts[(2 * k + 2) % len(pts)]
        if math.dist(a, b) > 0:
            edges.append(Line(a, b))
        edges.append(Bezier(b, (b[0] + out[0], b[1] + out[1]), (c[0] - into[0], c[1] - into[1]), c))
    return make_face(edges)


def arc_to(a, b, centre, r, bulge):
    """The arc of radius r about centre from a to b, through the point of the circle towards bulge."""
    n = math.hypot(*bulge)
    return ThreePointArc(a, (centre[0] + r * bulge[0] / n, centre[1] + r * bulge[1] / n), b)


def tabs(first, n, pitch, width):
    return [(first + k * pitch, first + k * pitch + width) for k in range(int(n))]


def castle(spans, base, tip, reverse=False):
    """Corner points of an edge that runs at `base` and steps to `tip` over each span."""
    pts = []
    for s, e in (reversed(spans) if reverse else spans):
        a, b = (e, s) if reverse else (s, e)
        pts += [(a, base), (a, tip), (b, tip), (b, base)]
    return pts


def place(origin, udir, vdir):
    """Where a part's frame sits: its origin, and where its x and y axes point. Its z follows."""
    zdir = (udir[1] * vdir[2] - udir[2] * vdir[1], udir[2] * vdir[0] - udir[0] * vdir[2], udir[0] * vdir[1] - udir[1] * vdir[0])
    return Location(Plane(origin=origin, x_dir=udir, z_dir=zdir))


class Clears(str):
    """In a hole's tuple, the thread param whose screw the hole clears; a plain name is one it carries."""


class Model:
    def __init__(self):
        self.parts, self.datums, self.assembly, self.sheets, self.threads, self.clears = {}, {}, {}, {}, {}, {}

    def cut(self, name, t, outer, holes=(), cutouts=()):
        """A plate cut from a sheet: its outline less its round holes and cut-outs. A hole is
        (label, u, v, d, thread param or None) and gets a datum at mid-thickness, on its axis."""
        sk = outer
        minus = [disc(u, v, d) for (_l, u, v, d, _t) in holes] + list(cutouts)
        if minus:
            sk = sk - minus
        self.parts[name] = extrude(sk, amount=t)
        for label, u, v, _d, thread in holes:
            self.datums[f"{name}.{label}"] = (u, v, t / 2)
            if thread:
                (self.clears if isinstance(thread, Clears) else self.threads)[f"{name}.{label}"] = str(thread)

    def on_sheet(self, sheet, part, x, y, w=0, h=0, turned=False):
        loc = Location((x + w, y + h, 0), (0, 0, 180)) if turned else Location((x, y, 0))
        px, py = (x + w / 2, y + h / 2)
        self.sheets[sheet] = (part, loc)
        return px, py


def build(p):
    m = Model()
    t6, t3, tab = p.t6, p.t3, p.tab
    fj = 2 * tab                                   # pitch of a finger joint: a tab and a gap
    W = p.unit_w

    # ============================================================== carriage
    # --- wall: the rods cross it; v 0 is the edge the cover closes
    end_a = tabs(p.fj_end_u0, p.fj_end_n, fj, tab)
    mid = tabs(p.fj_mid_u0, p.fj_mid_n, fj, tab)
    end_b = [(W - e, W - s) for s, e in reversed(end_a)]
    end_a_stop = end_a[-1][1]                        # where the end section's fingers stop
    mid_stop = mid[-1][1]
    wall_h = p.cw_h + t6
    low_tabs = [(end_a_stop, p.fj_mid_u0)] + [(s + tab, e + tab) for s, e in mid[:-1]] + [(mid_stop, W - end_a_stop)]
    side = p.rib_tab_v
    pts = [(0, 0)] + castle(end_a + mid + end_b, 0, t6) + [(W, 0), (W, side), (W - t6, side), (W - t6, side + tab), (W, side + tab), (W, p.cw_h)]
    pts += castle(low_tabs, p.cw_h, wall_h, reverse=True)
    pts += [(0, p.cw_h), (0, side + tab), (t6, side + tab), (t6, side), (0, side)]
    holes = []
    for end, sx in (("a", 1), ("b", -1)):
        us = p.screw_u if sx > 0 else W - p.screw_u
        ug = p.guide_u if sx > 0 else W - p.guide_u
        holes.append((f"nut_{end}", us, p.cw_rod_v, p.cw_nut_d, None))
        holes.append((f"bearing_{end}", ug, p.cw_rod_v, p.cw_bearing_d, None))
        k = 0
        for du in (-1, 1):
            for dv in (-1, 1):
                k += 1
                holes.append((f"nut_{end}_m3_{k}", us + du * p.cw_nut_hole_off, p.cw_rod_v + dv * p.cw_nut_hole_off, p.m3.tap, "m3"))
        # the retainer's pair lies on the diagonal that rises towards the unit's side
        holes.append((f"ret_{end}_m3_1", ug - sx * p.cw_ret_hole_off, p.cw_rod_v + p.cw_ret_hole_off, p.m3.tap, "m3"))
        holes.append((f"ret_{end}_m3_2", ug + sx * p.cw_ret_hole_off, p.cw_rod_v - p.cw_ret_hole_off, p.m3.tap, "m3"))
    windows = [rect(u, side, u + t6, side + tab) for u in (p.rib_u, W - p.rib_u - t6)]
    m.cut("carriage_wall", t6, poly(pts), holes, windows)
    m.datums["carriage_wall.face_a"] = (W / 2, p.cw_h / 2, 0)
    m.datums["carriage_wall.face_b"] = (W / 2, p.cw_h / 2, t6)
    m.on_sheet("acryl6@195.28,199.92", "carriage_wall", p.at_left, p.cw_at_y1)
    m.on_sheet("acryl6@195.28,246.92", "carriage_wall", p.at_left, p.cw_at_y2)

    # --- cover: closes the box over both walls, fingers on both long edges
    D = p.box_depth
    et = p.end_tab_v
    fingers = end_a + mid + end_b
    slots = [(p.rib_u, p.rib_u + t6), (W - p.rib_u - t6, W - p.rib_u)]

    def cover_edge(base, tip, deep, reverse):
        spans = [(s, e, tip) for s, e in fingers] + [(s, e, deep) for s, e in slots]
        spans.sort(key=lambda q: q[0], reverse=reverse)
        out = []
        for s, e, lvl in spans:
            a, b = (e, s) if reverse else (s, e)
            out += [(a, base), (a, lvl), (b, lvl), (b, base)]
        return out

    pts = [(t6, t6)] + cover_edge(t6, 0, et, False) + [(W - t6, t6), (W - t6, et), (W, et), (W, et + tab), (W - t6, et + tab), (W - t6, D - t6)]
    pts += cover_edge(D - t6, D, et + tab, True) + [(t6, D - t6), (t6, et + tab), (0, et + tab), (0, et), (t6, et)]
    m.cut("carriage_cover", t6, poly(pts))
    m.datums["carriage_cover.a"] = (W / 2, t6, t6 / 2)
    m.datums["carriage_cover.b"] = (W / 2, D - t6, t6 / 2)
    m.on_sheet("acryl6@114.03,153.42", "carriage_cover", p.at_left, p.cc_at_y)

    # --- plate: the box's floor between the tall cross plates, and the shelf with the twelve threads
    L = p.cpl_len
    pf = tabs(p.cpl_finger_u0, p.cpl_n_fingers, fj, tab)
    w2 = D - t6                                      # where the second wall stands on the plate
    pts = [(t6, t6)] + castle(pf, t6, 0) + [(L - t6, t6), (L - t6, et), (L, et), (L, et + tab), (L - t6, et + tab), (L - t6, w2),
                                             (L - p.cpl_finger_u0, w2), (L - p.cpl_finger_u0, D), (L - t6, D), (L - t6, p.cpl_wid), (t6, p.cpl_wid),
                                             (t6, D), (p.cpl_finger_u0, D), (p.cpl_finger_u0, w2), (t6, w2), (t6, et + tab), (0, et + tab), (0, et), (t6, et)]
    holes = [(f"thread_{k + 1}", p.cpl_thread_u0 + k * p.mount_hole_pitch, p.cpl_thread_v, p.mount_screw.tap, "mount_screw")
             for k in range(int(p.n_mount_threads))]
    wall_slots = [rect(s + tab, w2, e + tab, D) for s, e in pf[:-1]]
    m.cut("carriage_plate", t6, poly(pts), holes, wall_slots)
    m.on_sheet("acryl6@206.95,76.8", "carriage_plate", p.at_left, p.cpl_at_y)

    # --- cross plates: a tall one each side of the plate, a short one closing each end
    def rib(height, low_notch):
        pts = [(t6, 0), (t6, side), (0, side), (0, side + tab), (t6, side + tab), (t6, height)]
        if low_notch:
            pts += [(et, height), (et, height - t6), (et + tab, height - t6), (et + tab, height)]
        pts += [(D - t6, height), (D - t6, side + tab), (D, side + tab), (D, side), (D - t6, side), (D - t6, 0),
                (et + tab, 0), (et + tab, t6), (et, t6), (et, 0)]
        return poly(pts)

    m.cut("carriage_rib_tall", t6, rib(wall_h, True))
    m.cut("carriage_rib_short", t6, rib(p.cw_h, False))
    m.on_sheet("acryl6@318.62,387.24", "carriage_rib_tall", p.rib_at_x1, p.rt_at_y)
    m.on_sheet("acryl6@367.16,387.24", "carriage_rib_tall", p.rib_at_x2, p.rt_at_y)
    m.on_sheet("acryl6@318.62,436.57", "carriage_rib_short", p.rib_at_x1, p.rs_at_y)
    m.on_sheet("acryl6@367.16,436.57", "carriage_rib_short", p.rib_at_x2, p.rs_at_y)

    # --- bearing retainer: an ellipse over a bearing's end, its three holes along its long axis
    cu, cv = p.br_half_len, p.br_half_wid
    m.cut("bearing_retainer", t6, Pos(cu, cv) * Ellipse(cu, cv), [("rod", cu, cv, p.br_rod_d, None),
                                                                ("m3_1", cu - p.br_hole_off, cv, p.d_m3_clear, Clears("m3")),
                                                                ("m3_2", cu + p.br_hole_off, cv, p.d_m3_clear, Clears("m3"))])
    for name, x, y in (("331.64,330.03", p.br_at_x1, p.br_at_y1), ("372.28,330.03", p.br_at_x2, p.br_at_y1),
                       ("331.64,344.59", p.br_at_x1, p.br_at_y2), ("372.28,344.59", p.br_at_x2, p.br_at_y2)):
        m.on_sheet(f"acryl6@{name}", "bearing_retainer", x, y)

    # ============================================================== stationary bar and mountings
    rows = (p.slot_edge, p.slot_edge + p.slot_pitch)
    holes = []
    for j, v in enumerate(rows):
        for i, u in enumerate((p.slot_edge, p.slot_edge + p.slot_pitch, W - p.slot_edge - p.slot_pitch, W - p.slot_edge)):
            holes.append((f"long_{j + 1}_{i + 1}", u, v, p.d_m5, None))
        us = [p.sb_slot_u1] + [p.sb_slot_u2 + k * p.sb_slot_pitch for k in range(int(p.sb_slot_n))] + [W - p.sb_slot_u1]
        for i, u in enumerate(us):
            holes.append((f"short_{j + 1}_{i + 1}", u, v, p.sb_slot_d, Clears("m5")))
    holes += [(f"thread_{k + 1}", p.sb_thread_u0 + k * p.mount_hole_pitch, p.sb_thread_v, p.mount_screw.tap, "mount_screw")
              for k in range(int(p.n_mount_threads))]
    m.cut("stationary_bar", t6, rect(0, 0, W, p.sb_wid), holes)
    m.on_sheet("acryl6@48.75,290.92", "stationary_bar", 0, p.sb_at_y)

    # --- mounting: a lobe about each hook's hole, a recess between them
    ML, MW, lr, hu = p.mt_len, p.mt_wid, p.mt_lobe_r, p.mt_hook_u
    chord = math.sqrt(lr * lr - (lr - p.mt_recess_v) ** 2)
    a1, a2 = (hu, lr), (ML - hu, lr)
    edges = [
        Polyline((hu - lr, lr), (0, lr), (0, MW), (ML, MW), (ML, lr), (ML - hu + lr, lr)),
        arc_to((ML - hu + lr, lr), (ML - hu - chord, p.mt_recess_v), a2, lr, (0, -1)),
        Line((ML - hu - chord, p.mt_recess_v), (hu + chord, p.mt_recess_v)),
        arc_to((hu + chord, p.mt_recess_v), (hu - lr, lr), a1, lr, (0, -1)),
    ]
    holes = [("hook_1", hu, lr, p.hook_thread.tap, "hook_thread"), ("hook_2", ML - hu, lr, p.hook_thread.tap, "hook_thread"),
             ("bolt_1", p.mt_bolt_u, p.mt_bolt_v, p.frame_bolt.tap, "frame_bolt"), ("bolt_2", ML - p.mt_bolt_u, p.mt_bolt_v, p.frame_bolt.tap, "frame_bolt"),
             ("screw_1", p.mt_screw_u, p.mt_screw_v, p.mt_screw_d, Clears("mount_screw")),
             ("screw_2", ML - p.mt_screw_u, p.mt_screw_v, p.mt_screw_d, Clears("mount_screw"))]
    m.cut("mounting", t6, make_face(edges), holes)
    mt_x = (p.mt_at_x1, p.mt_at_x2, p.mt_at_x3, p.mt_at_x4)
    mt_names = (("410.55,488.48", "445.95,498.52", "481.59,488.48", "516.99,498.52"), ("410.55,530.39", "445.95,540.42", "481.59,530.39", "516.99,540.42"),
                ("410.55,571.5", "445.95,581.53", "481.59,571.5", "516.99,581.53"))
    for names, y in zip(mt_names, (p.mt_at_y1, p.mt_at_y2, p.mt_at_y3)):
        for k, (name, x) in enumerate(zip(names, mt_x)):
            m.on_sheet(f"acryl6@{name}", "mounting", x, y, ML, MW, turned=bool(k % 2))

    # ============================================================== end-pieces
    def end_piece(name, length, shift, rods, pin_d, pin_thread, m6, m5_u, extra_holes=(), extra_cuts=()):
        """A 71 high end-piece. `shift` is how far its u 0 edge lies in from the unit's side."""
        holes = [(f"rod_{i + 1}", u - shift, p.ep_rod_v, p.ep_rod_d, None) for i, u in enumerate(rods)]
        if m6:
            for i, u in enumerate((p.slot_edge, p.slot_edge + p.slot_pitch, W - p.slot_edge - p.slot_pitch, W - p.slot_edge)):
                holes.append((f"m6_{i + 1}", u, p.ep_bolt_v, p.ep_m6_d, None))
        for i, u in enumerate((m5_u, m5_u + p.slot_pitch, length - m5_u - p.slot_pitch, length - m5_u)):
            holes.append((f"m5_{i + 1}", u, p.ep_bolt_v, p.d_m5, None))
        for i, u in enumerate((p.ep_pin_u - shift, length - p.ep_pin_u + shift)):
            holes.append((f"pin_{i + 1}", u, p.ep_pin_v, pin_d, pin_thread))
        cuts = list(extra_cuts)
        for k in range(2):
            u0 = p.ep_slot_u0 - shift + k * p.ep_slot_pitch
            cuts.append(bez_box(u0, p.ep_bolt_v - p.ep_slot_w / 2, u0 + p.ep_slot_len, p.ep_bolt_v + p.ep_slot_w / 2,
                                p.ep_slot_w / 2, p.ep_slot_w / 2, p.ep_slot_k, p.ep_slot_k))
        m.cut(name, t6, rect(0, 0, length, p.ep_h), holes + list(extra_holes), cuts)

    all_rods = (p.screw_u, p.guide_u, W - p.guide_u, W - p.screw_u)
    end_piece("end_plate", W, 0, all_rods, p.m3.tap, "m3", True, p.ep_m5_u)
    m.datums["end_plate.over_screw_1"] = (p.screw_u, 0, t6 / 2)                       # on its top edge, square over a screw's axis
    m.datums["end_plate.over_screw_2"] = (W - p.screw_u, 0, t6 / 2)
    end_piece("end_cover", W, 0, (), p.d_m3_clear, Clears("m3"), True, p.ep_m5_u)
    m.on_sheet("acryl6@195.28,558.3", "end_plate", p.at_left, p.ep_at_y)
    m.on_sheet("acryl6@195.28,486.51", "end_cover", p.at_left, p.ec_at_y)

    inset = (W - p.mp_len) / 2                        # the motor end-pieces stand between the two motor mounting frames
    mid_u = p.mp_len / 2
    right_half = [(p.ds_u1, p.ds_v1), (p.ds_u2, p.ds_v1), (p.ds_u3, p.ds_v3), (p.ds_u4, p.ds_v4), (p.ds_u5, p.ds_v5),
                  (p.ds_u6, p.ds_v6), (p.ds_u7, p.ds_v7), (p.ds_u8, p.ds_v7)]
    r1, r2, r3, r4, r5, r6, r7, r8 = [(mid_u + u, v) for u, v in right_half]
    l1, l2, l3, l4, l5, l6, l7, l8 = [(mid_u - u, v) for u, v in right_half]
    dsub = make_face([Line(l1, r1), Bezier(r1, r2, r3, r4), Line(r4, r5), Bezier(r5, r6, r7, r8),
                      Line(r8, l8), Bezier(l8, l7, l6, l5), Line(l5, l4), Bezier(l4, l3, l2, l1)])
    ds_holes = [("dsub_1", mid_u - p.ds_hole_off, p.ds_hole_v, p.ds_hole_d, None), ("dsub_2", mid_u + p.ds_hole_off, p.ds_hole_v, p.ds_hole_d, None)]
    end_piece("motor_end_plate", p.mp_len, inset, (p.guide_u, W - p.guide_u), p.m3.tap, "m3", False, p.mp_m5_u, ds_holes, [dsub])
    window = bez_box(mid_u - p.mc_win_half, p.mc_win_v0, mid_u + p.mc_win_half, p.mc_win_v1, p.mc_cor_du, p.mc_cor_dv, p.mc_cor_hu, p.mc_cor_hv)
    end_piece("motor_end_cover", p.mp_len, inset, (), p.mc_pin_d, Clears("m3"), False, p.mp_m5_u, (), [window])
    m.on_sheet("acryl6@49.28,342.62", "motor_end_plate", p.at_left, p.mp_at_y)
    m.on_sheet("acryl6@49.28,414.51", "motor_end_cover", p.at_left, p.mc_at_y)

    # ============================================================== frame plates
    holes = [(f"m5_{j + 1}_{i + 1}", p.slot_edge + i * p.slot_pitch, v, p.d_m5, None) for j, v in enumerate(rows) for i in range(int(p.cp_hole_n))]
    m.cut("corner_plate", t6, rect(0, 0, p.cp_len, p.cp_wid), holes)
    for name, x, y in (("414.55,122.86", p.cp_at_x1, p.cp_at_y1), ("534.98,122.86", p.cp_at_x2, p.cp_at_y1),
                       ("414.55,163.36", p.cp_at_x1, p.cp_at_y2), ("534.98,163.36", p.cp_at_x2, p.cp_at_y2)):
        m.on_sheet(f"acryl6@{name}", "corner_plate", x, y)

    # --- motor mounting frame: base on the profile, face the motor bolts to, a gusset each side
    S = p.mm_size
    mt = tabs(p.mm_tab_u0, 2, fj, tab)
    right_side, left_side = [], []
    for s, e in mt:
        right_side += [(S - t6, s), (S, s), (S, e), (S - t6, e)]
    for s, e in reversed(mt):
        left_side += [(t6, e), (0, e), (0, s), (t6, s)]
    pts = [(t6, t6)] + castle(mt, t6, 0) + [(S - t6, t6)] + right_side + [(S - t6, S), (t6, S)] + left_side
    holes = [(f"m5_{j + 1}_{i + 1}", p.mb_hole_u + i * p.slot_pitch, v, p.mb_hole_d, None)
             for j, v in enumerate((p.mb_hole_v1, p.mb_hole_v2)) for i in range(2)]
    m.cut("motor_base", t6, poly(pts), holes)
    m.on_sheet("acryl6@568.14,277.2", "motor_base", p.mb_at_x, p.mb_at_y1)
    m.on_sheet("acryl6@568.14,333.08", "motor_base", p.mb_at_x, p.mb_at_y2)

    right_side, left_side = [], []
    for s, e in mt:
        left_side += [(0, s), (t6, s), (t6, e), (0, e)]
    for s, e in reversed(mt):
        right_side += [(S, e), (S - t6, e), (S - t6, s), (S, s)]
    pts = [(0, 0)] + left_side + [(0, S)] + castle(mt, S, S - t6) + [(S, S)] + right_side + [(S, 0)]
    c, h = S / 2, p.mf_hole_pitch / 2
    holes = [("pilot", c, c, p.mf_pilot_d, None)] + [(f"m3_{i + 1}", c + dx * h, c + dy * h, p.mf_hole_d, None)
                                                      for i, (dx, dy) in enumerate(((-1, -1), (1, -1), (1, 1), (-1, 1)))]
    m.cut("motor_face", t6, poly(pts), holes)
    m.on_sheet("acryl6@575.07,369.06", "motor_face", p.mf_at_x, p.mf_at_y1)
    m.on_sheet("acryl6@575.07,424.93", "motor_face", p.mf_at_x, p.mf_at_y2)

    right_side = []
    for s, e in reversed(mt):
        right_side += [(S - t6, e), (S, e), (S, s), (S - t6, s)]
    top = []
    for s, e in reversed(mt):
        top += [(e, 0), (e, t6), (s, t6), (s, 0)]
    pts = [(S - t6, S)] + right_side + [(S - t6, 0)] + top + [(0, 0), (0, t6)]
    m.cut("motor_gusset", t6, poly(pts))
    m.datums["motor_gusset.foot"] = (S / 2, 0, t6 / 2)
    for name, x, y, turned in (("578.17,495.25", p.mg_at_x1, p.mg_at_y1, False), ("558.09,515.54", p.mg_at_x2, p.mg_at_y2, True),
                               ("578.17,557.52", p.mg_at_x1, p.mg_at_y3, False), ("558.09,577.8", p.mg_at_x2, p.mg_at_y4, True)):
        m.on_sheet(f"acryl6@{name}", "motor_gusset", x, y, S, S, turned=turned)

    # --- limit-switch plate
    holes = [(f"m5_{j + 1}_{i + 1}", p.slot_edge + i * p.slot_pitch, p.sp_hole_v + j * p.slot_pitch, p.d_m5, None) for j in range(2) for i in range(2)]
    holes += [(f"switch_{i + 1}", p.sp_sw_u + i * p.sp_sw_pitch, p.sp_sw_v, p.sp_sw_d, None) for i in range(2)]
    m.cut("switch_plate", t6, rect(0, 0, p.sp_wid, p.sp_len), holes)
    m.on_sheet("acryl6@565.86,206.38", "switch_plate", p.sp_at_x, p.sp_at_y)

    # ============================================================== holding frames
    def holding_frame(name, length, cor_du, cor_hu, win_u0, win_w, slot_us):
        outer = bez_box(0, 0, length, p.hf_wid, cor_du, p.hf_cor_dv, cor_hu, p.hf_cor_hv)
        cuts = [bez_box(win_u0, p.hf_win_v0, win_u0 + win_w, p.hf_win_v0 + p.hf_win_h, p.hf_win_du, p.hf_win_dv, p.hf_win_hu, p.hf_win_hv)]
        for u in slot_us:
            for v in (p.hf_slot_v, p.hf_wid - p.hf_slot_v):
                cuts.append(bez_box(u - p.hf_slot_len / 2, v - p.hf_slot_w / 2, u + p.hf_slot_len / 2, v + p.hf_slot_w / 2,
                                    p.hf_slot_w / 2, p.hf_slot_w / 2, p.hf_slot_k, p.hf_slot_k))
        m.cut(name, t6, outer, (), cuts)
        m.datums[f"{name}.face"] = (length / 2, p.hf_win_v0 / 2, 0)

    holding_frame("holding_frame_narrow", p.hn_len, p.hn_cor_du, p.hn_cor_hu, p.hn_win_u0, p.hn_win_w, (p.hn_slot_u, p.hn_len - p.hn_slot_u))
    holding_frame("holding_frame_wide", p.hw_len, p.hw_cor_du, p.hw_cor_hu, p.hw_win_u0, p.hw_win_w, (p.hw_slot_u1, p.hw_slot_u2))
    hn_names = ("399.92,206.61", "399.92,254.18", "399.92,301.22", "399.92,346.65", "399.92,394.23", "399.92,441.27")
    hw_names = ("468.52,206.74", "468.52,254.32", "468.52,301.36", "468.52,346.79", "468.52,394.37", "468.52,441.41")
    for nn, wn, y in zip(hn_names, hw_names, (p.hn_at_y1, p.hn_at_y2, p.hn_at_y3, p.hn_at_y4, p.hn_at_y5, p.hn_at_y6)):
        m.on_sheet(f"acryl6@{nn}", "holding_frame_narrow", p.hn_at_x, y)
        m.on_sheet(f"acryl6@{wn}", "holding_frame_wide", p.hw_at_x, y + p.hw_at_dy)

    # ============================================================== mould
    ms = p.mo_side
    ins = (p.mo_screw_in, ms - p.mo_screw_in)
    posts = (p.mo_post_in, ms - p.mo_post_in)
    holes = [(f"screw_{2 * j + i + 1}", u, v, p.mould_screw.tap, "mould_screw") for j, v in enumerate(ins) for i, u in enumerate(ins)]
    holes += [(f"post_{2 * j + i + 1}", u, v, p.mo_post_hole_d, None) for j, v in enumerate(posts) for i, u in enumerate(posts)]
    m.cut("mould_base", t3, rect(0, 0, ms, ms), holes)
    m.datums["mould_base.top"] = (ms / 2, ms / 2, t3)
    for name, x, y in (("85,515", p.mo_at_x2, p.mo_at_y1), ("140,515", p.mo_at_x3, p.mo_at_y1), ("30,570", p.mo_at_x1, p.mo_at_y2),
                       ("85,570", p.mo_at_x2, p.mo_at_y2), ("140,570", p.mo_at_x3, p.mo_at_y2), ("195,570", p.mo_at_x4, p.mo_at_y2)):
        m.on_sheet(f"acryl3@{name}", "mould_base", x, y)

    mp_ = p.mo_plat
    m.parts["mould_platform"] = extrude(Pos(mp_ / 2, mp_ / 2) * RectangleRounded(mp_, mp_, p.mo_plat_r), amount=t3)
    m.datums["mould_platform.top"] = (mp_ / 2, mp_ / 2, t3)
    m.datums["mould_platform.side_a"] = (0, mp_ / 2, t3 / 2)
    m.datums["mould_platform.side_b"] = (mp_, mp_ / 2, t3 / 2)
    for k, name in enumerate(("15,475", "40,475", "65,475", "90,475", "115,475", "140,475")[:int(p.pl_at_n)]):
        m.on_sheet(f"acryl3@{name}", "mould_platform", p.pl_at_x1 + k * p.pl_at_dx, p.pl_at_y)

    c = ms / 2
    win = bez_box(c - mp_ / 2, c - mp_ / 2, c + mp_ / 2, c + mp_ / 2, p.mo_plat_r, p.mo_plat_r, p.mo_templ_k, p.mo_templ_k)
    holes = [(f"screw_{2 * j + i + 1}", u, v, p.mo_templ_d, None) for j, v in enumerate(ins) for i, u in enumerate(ins)]
    m.cut("mould_template", t3, rect(0, 0, ms, ms), holes, [win])
    m.on_sheet("acryl3@40.42,498.33", "mould_template", p.mo_at_x1, p.mo_at_y1)

    rd = p.mo_ring_d
    m.cut("mould_ring", t3, disc(rd / 2, rd / 2, rd), [("bore", rd / 2, rd / 2, p.mo_ring_bore, None)])
    rg_names = (("176.81,517.41", "186.1,517.41"), ("176.81,523.41", "186.1,523.41"), ("176.81,529.41", "186.1,529.41"), ("176.81,535.41", "186.1,535.41"))
    for k, names in enumerate(rg_names[:int(p.rg_at_rows)]):
        for name, x in zip(names, (p.rg_at_x1, p.rg_at_x2)):
            m.on_sheet(f"acryl3@{name}", "mould_ring", x, p.rg_at_y1 + k * p.rg_at_dy)

    # --- mould frame (frame of MoldFrame.stl: origin at the centre of the underside)
    fs, at, la = p.mfr_side, p.mfr_hole_at, p.mfr_lobe_at
    sk = Rectangle(fs, fs) - [Rectangle(p.mfr_open, p.mfr_open)] - [Pos(sx * la, sy * la) * Circle(p.mfr_lobe_d / 2) for sx in (-1, 1) for sy in (-1, 1)]
    sk = sk - [Pos(sx * at, sy * at) * Circle(p.mfr_hole_d / 2) for sx in (-1, 1) for sy in (-1, 1)]
    m.parts["mould_frame"] = extrude(sk, amount=p.mfr_h)
    k = 0
    for sy in (-1, 1):
        for sx in (-1, 1):
            k += 1
            m.datums[f"mould_frame.screw_{k}"] = (sx * at, sy * at, p.mfr_h / 2)
    m.datums["mould_frame.top"] = (fs / 2 - (fs - p.mfr_open) / 2 / 2, 0, p.mfr_h)
    m.datums["mould_frame.bottom"] = (fs / 2 - (fs - p.mfr_open) / 2 / 2, 0, 0)

    # ============================================================== clamp (frame of Clamp.stl)
    hx, hy, lr = p.cl_hole_x, p.cl_hole_y, p.cl_lobe_d / 2
    ax, ri, ro = p.cl_arc_x, p.cl_wall_ri, p.cl_wall_ro
    fa = math.radians(p.cl_flank_deg)
    tx, ty = hx + lr * math.sin(fa), hy - lr * math.cos(fa)         # where the flank leaves the lobe
    foot = tx - ty / math.tan(fa)
    back_x = hx - math.sqrt(lr * lr - (p.cl_back_y - hy) ** 2)

    def notch(r):
        return [arc_to((ax + r, 0), (ax, r), (ax, 0), r, (1, 1)), Line((ax, r), (-ax, r)), arc_to((-ax, r), (-ax - r, 0), (-ax, 0), r, (-1, 1))]

    base = make_face(notch(ri) + [
        Polyline((-ax - ri, 0), (-foot, 0), (-tx, ty)),
        arc_to((-tx, ty), (-back_x, p.cl_back_y), (-hx, hy), lr, (-1, 1)),
        Line((-back_x, p.cl_back_y), (back_x, p.cl_back_y)),
        arc_to((back_x, p.cl_back_y), (tx, ty), (hx, hy), lr, (1, 1)),
        Polyline((tx, ty), (foot, 0), (ax + ri, 0)),
    ]) - [Pos(-hx, hy) * Circle(p.cl_hole_d / 2), Pos(hx, hy) * Circle(p.cl_hole_d / 2)]
    wall = make_face(notch(ro) + [Line((-ax - ro, 0), (-ax - ri, 0))] + notch(ri) + [Line((ax + ri, 0), (ax + ro, 0))])
    m.parts["clamp"] = extrude(base, amount=p.cl_base_t) + extrude(wall, amount=p.cl_h)
    m.datums["clamp.hole_1"] = (-hx, hy, p.cl_base_t / 2)
    m.datums["clamp.hole_2"] = (hx, hy, p.cl_base_t / 2)

    # ============================================================== bought parts, each held as its envelope
    low = (Align.CENTER, Align.CENTER, Align.MIN)

    def profile(length):
        """A 20x40 profile along x: y across its width, z up its height, a plain slot where each T-slot is."""
        a, b, sw, sd = p.prof_a, p.prof_b, p.prof_slot_w, p.prof_slot_depth
        cuts = [Pos(sd / 2, a / 2) * Rectangle(sd, sw), Pos(b - sd / 2, a / 2) * Rectangle(sd, sw)]
        for y in (p.slot_edge, p.slot_edge + p.slot_pitch):
            cuts += [Pos(y, sd / 2) * Rectangle(sw, sd), Pos(y, a - sd / 2) * Rectangle(sw, sd)]
        return extrude(Plane(origin=(0, 0, 0), x_dir=Y, z_dir=X) * (Pos(b / 2, a / 2) * Rectangle(b, a) - cuts), amount=length)

    m.parts["profile_long"] = profile(p.prof_long_len)
    m.parts["profile_short"] = profile(p.prof_short_len)

    m.parts["lead_screw"] = Cylinder(p.screw_d / 2, p.screw_len, align=low)
    m.datums["lead_screw.a"] = (0, 0, 0)
    m.datums["lead_screw.b"] = (0, 0, p.screw_len)
    m.datums["lead_screw.mark"] = (p.screw_d / 2, 0, 0)                               # on its rim, to read its turn by
    m.parts["guide_rod"] = Cylinder(p.rod_d / 2, p.rod_len, align=low)
    m.datums["guide_rod.zero"] = (0, 0, p.carriage_y + p.box_depth / 2 + t6)      # where a bearing's middle rides at zero stretch
    m.parts["bearing"] = Cylinder(p.bearing_od / 2, p.bearing_len, align=low) - Cylinder(p.rod_d / 2, p.bearing_len, align=low)
    m.datums["bearing.mid"] = (0, 0, p.bearing_len / 2)

    stub = p.nut_len - p.nut_flange_t
    off = p.cw_nut_hole_off
    corners = ((-1, -1), (1, -1), (1, 1), (-1, 1))
    nut = Cylinder(p.nut_flange_d / 2, p.nut_flange_t, align=low) + Pos(0, 0, -stub) * Cylinder(p.nut_body_d / 2, stub, align=low)
    nut -= [Pos(0, 0, -stub) * Cylinder(p.screw_d / 2, p.nut_len, align=low)] + [Pos(dx * off, dy * off, 0) * Cylinder(p.nut_hole_d / 2, p.nut_flange_t, align=low) for dx, dy in corners]
    m.parts["lead_nut"] = nut
    for i, (dx, dy) in enumerate(corners):
        m.datums[f"lead_nut.m3_{i + 1}"] = (dx * off, dy * off, p.nut_flange_t / 2)
        m.clears[f"lead_nut.m3_{i + 1}"] = "m3"

    mw, h = p.motor_w, p.mf_hole_pitch / 2
    motor = Pos(0, 0, -p.motor_len / 2) * Box(mw, mw, p.motor_len) + Cylinder(p.motor_boss_d / 2, p.motor_boss_h, align=low) + Cylinder(p.motor_shaft_d / 2, p.motor_shaft_len, align=low)
    motor -= [Pos(dx * h, dy * h, -p.motor_hole_depth) * Cylinder(p.m3.tap / 2, p.motor_hole_depth, align=low) for dx, dy in corners]
    m.parts["motor"] = motor
    for i, (dx, dy) in enumerate(corners):
        m.datums[f"motor.m3_{i + 1}"] = (dx * h, dy * h, -p.motor_hole_depth / 2)
        m.threads[f"motor.m3_{i + 1}"] = "m3"

    cl2 = p.coup_len / 2
    m.parts["coupling"] = Cylinder(p.coup_d / 2, p.coup_len, align=low) - [Cylinder(p.motor_shaft_d / 2, cl2, align=low), Pos(0, 0, cl2) * Cylinder(p.screw_d / 2, cl2, align=low)]

    sw_hole_x, sw_hole_y = (p.sw_len - p.sp_sw_pitch) / 2, p.sw_h - p.sw_hole_in
    m.parts["limit_switch"] = Pos(p.sw_len / 2, p.sw_h / 2, p.sw_t / 2) * Box(p.sw_len, p.sw_h, p.sw_t) - [
        Pos(sw_hole_x + i * p.sp_sw_pitch, sw_hole_y, 0) * Cylinder(p.sw_hole_d / 2, p.sw_t, align=low) for i in range(2)]

    m.parts["foot"] = Pos(0, 0, -p.foot_h) * Cylinder(p.foot_d / 2, p.foot_h, align=low) + Cylinder(p.foot_thread.tap / 2, p.foot_stud_len, align=low)
    m.datums["foot.wall"] = (p.foot_d / 2, 0, -p.foot_h / 2)
    m.datums["foot.stud"] = (0, 0, p.foot_stud_len / 2)
    m.threads["foot.stud"] = "foot_thread"

    hexagon = RegularPolygon(p.hook_af / 2, int(p.hook_sides), major_radius=False)
    m.parts["hook"] = extrude(hexagon, amount=p.hook_len) + Pos(0, 0, -p.hook_stud_len) * Cylinder(p.hook_thread.tap / 2, p.hook_stud_len, align=low)
    m.datums["hook.seat"] = (0, 0, 0)
    m.datums["hook.stud"] = (0, 0, -p.hook_stud_len / 2)
    m.threads["hook.stud"] = "hook_thread"

    m.parts["mould_post"] = Cylinder(p.post_d / 2, p.post_len, align=low)
    m.datums["mould_post.wall"] = (p.post_d / 2, 0, p.post_len / 2)

    # ============================================================== assembly, at zero stretch
    A = m.assembly
    pa, pb, rz = p.prof_a, p.prof_b, p.rod_z
    yme, F, yc = p.motor_end_y, p.motor_face_y, p.carriage_y
    yms = yme - pb                                    # inner side of the motor-end short profile

    # --- frame: the profiles flat, the short ones between the long ones, a corner plate under each joint
    A["profile_long_1"] = ("profile_long", place((pb, 0, 0), Y, NX))
    A["profile_long_2"] = ("profile_long", place((W, 0, 0), Y, NX))
    A["profile_short_1"] = ("profile_short", Location((pb, 0, 0)))
    A["profile_short_2"] = ("profile_short", Location((pb, yms, 0)))
    k = 0
    for y0, yfoot in ((0, p.slot_edge + p.slot_pitch), (yms, yms + p.slot_edge)):
        for x0, xfoot in ((0, p.slot_edge + p.slot_pitch), (W - p.cp_len, W - p.slot_edge - p.slot_pitch)):
            k += 1
            A[f"corner_plate_{k}"] = ("corner_plate", Location((x0, y0, -t6)))
            A[f"foot_{k}"] = ("foot", Location((xfoot, yfoot, -t6)))       # in the plate's hole over the long profile's inner slot

    # --- end-pieces and the stationary bar
    A["end_plate_1"] = ("end_plate", place((0, -t6, p.ep_h), X, NZ))
    A["end_cover_1"] = ("end_cover", place((0, -2 * t6, p.ep_h), X, NZ))
    A["motor_end_plate_1"] = ("motor_end_plate", place((inset, yme, p.ep_h), X, NZ))
    A["motor_end_cover_1"] = ("motor_end_cover", place((inset, yme + t6, p.ep_h), X, NZ))
    A["stationary_bar_1"] = ("stationary_bar", place((0, p.sb_wid, pa + t6), X, NY))
    sp_x, sp_y = (W - p.sp_wid) / 2, yme - p.sp_len
    A["switch_plate_1"] = ("switch_plate", Location((sp_x, sp_y, pa)))
    A["limit_switch_1"] = ("limit_switch", Location((sp_x + p.sp_sw_u - sw_hole_x, sp_y + p.sp_sw_v - sw_hole_y, pa + t6)))

    # --- drives: a motor in its mounting frame on each long profile, its screw, and the guide rod beside it
    static = []
    for k, (xs, xg) in enumerate(((p.screw_u, p.guide_u), (W - p.screw_u, W - p.guide_u))):
        n = k + 1
        x0 = xs - S / 2
        A[f"motor_base_{n}"] = ("motor_base", place((x0, F, pa + t6), X, NY))
        A[f"motor_face_{n}"] = ("motor_face", place((x0, F - t6, pa + S), X, NZ))
        A[f"motor_gusset_{2 * k + 1}"] = ("motor_gusset", place((x0, F - S, pa), Y, Z))
        A[f"motor_gusset_{2 * k + 2}"] = ("motor_gusset", place((x0 + S - t6, F - S, pa), Y, Z))
        A[f"motor_{n}"] = ("motor", place((xs, F, rz), X, Z))
        A[f"coupling_{n}"] = ("coupling", place((xs, F - p.motor_shaft_len + cl2, rz), X, Z))
        A[f"lead_screw_{n}"] = ("lead_screw", place((xs, -t6, rz), X, NZ))
        A[f"guide_rod_{n}"] = ("guide_rod", place((xg, -t6, rz), X, NZ))

    # --- carriage: cover on top, plate below with its shelf towards the stationary bar
    carriage = []
    zt = rz + p.cw_rod_v                              # top of the carriage
    A["carriage_cover_1"] = ("carriage_cover", Location((0, yc, zt - t6)))

    def ride(name, part, loc):
        A[name] = (part, loc)
        carriage.append(name)

    ride("carriage_wall_1", "carriage_wall", place((0, yc, zt), X, NZ))
    ride("carriage_wall_2", "carriage_wall", place((0, yc + D - t6, zt), X, NZ))
    ride("carriage_plate_1", "carriage_plate", place((p.rib_u, yc + D, zt - p.cw_h), X, NY))
    ride("carriage_rib_tall_1", "carriage_rib_tall", place((p.rib_u + t6, yc, zt), Y, NZ))
    ride("carriage_rib_tall_2", "carriage_rib_tall", place((W - p.rib_u, yc, zt), Y, NZ))
    ride("carriage_rib_short_1", "carriage_rib_short", place((t6, yc, zt), Y, NZ))
    ride("carriage_rib_short_2", "carriage_rib_short", place((W, yc, zt), Y, NZ))
    rk = math.sqrt(0.5)
    n = 0
    for k, (xs, xg, sx) in enumerate(((p.screw_u, p.guide_u, 1), (W - p.screw_u, W - p.guide_u, -1))):
        ride(f"bearing_{k + 1}", "bearing", place((xg, yc, rz), X, NZ))
        ride(f"lead_nut_{k + 1}", "lead_nut", place((xs, yc + D, rz), X, NZ))       # its flange on the wall's face towards the motors
        ud, vd = (sx * rk, 0, rk), (rk, 0, -sx * rk)
        for y0 in (yc - t6, yc + D):
            n += 1
            o = (xg - ud[0] * p.br_half_len - vd[0] * p.br_half_wid, y0, rz - ud[2] * p.br_half_len - vd[2] * p.br_half_wid)
            ride(f"bearing_retainer_{n}", "bearing_retainer", place(o, ud, vd))

    # --- mountings, hooks and clamps: six on the stationary bar, six on the carriage's shelf
    z_mt = pa + t6                                    # the mountings' underside, on the bar and on the shelf
    z_clamp = z_mt + t6 + p.clamp_lift
    z_hook = z_clamp + p.cl_base_t
    ys_bolt = p.sb_wid - p.sb_thread_v
    ym_bolt = yc - (p.cpl_thread_v - D)
    reach = p.mt_screw_v - p.mt_lobe_r
    y_hs, y_hm = ys_bolt + reach, ym_bolt - reach
    n_wells = int(p.n_mount_threads) // 2
    for i in range(n_wells):
        x0 = p.sb_thread_u0 - p.mt_screw_u + 2 * i * p.mount_hole_pitch
        xm = p.rib_u + p.cpl_thread_u0 - p.mt_screw_u + 2 * i * p.mount_hole_pitch
        A[f"mounting_{i + 1}"] = ("mounting", place((x0, ys_bolt + p.mt_screw_v, z_mt + t6), X, NY))
        ride(f"mounting_{n_wells + i + 1}", "mounting", Location((xm, ym_bolt - p.mt_screw_v, z_mt)))
        A[f"clamp_{i + 1}"] = ("clamp", Location((x0 + ML / 2, y_hs + p.cl_hole_y, z_clamp), (0, 0, 180)))
        ride(f"clamp_{n_wells + i + 1}", "clamp", Location((xm + ML / 2, y_hm - p.cl_hole_y, z_clamp)))
        for j, u in enumerate((p.mt_hook_u, ML - p.mt_hook_u)):
            A[f"hook_{2 * i + j + 1}"] = ("hook", Location((x0 + u, y_hs, z_hook)))
            ride(f"hook_{2 * n_wells + 2 * i + j + 1}", "hook", Location((xm + u, y_hm, z_hook)))

    # --- beside the unit, on the surface it stands on: the holding frames in two stacks, and one mould
    zf = -t6 - p.foot_h
    xa = W + S
    for i in range(n_wells):
        A[f"holding_frame_narrow_{i + 1}"] = ("holding_frame_narrow", Location((xa, 0, zf + i * t6)))
        A[f"holding_frame_wide_{i + 1}"] = ("holding_frame_wide", Location((xa, 2 * p.hf_wid, zf + i * t6)))
    bx, by = xa, yms
    A["mould_base_1"] = ("mould_base", Location((bx, by, zf)))
    A["mould_platform_1"] = ("mould_platform", Location((bx + (ms - mp_) / 2, by + (ms - mp_) / 2, zf + t3)))
    A["mould_frame_1"] = ("mould_frame", Location((bx + ms / 2, by + ms / 2, zf + t3)))
    k = 0
    for v in posts:
        for u in posts:
            k += 1
            A[f"mould_post_{k}"] = ("mould_post", Location((bx + u, by + v, zf)))

    # ============================================================== motion
    # Each motor turns its own lead screw through a rigid coupling; each screw's nut is fixed in the carriage,
    # which slides on the two guide rods. The two motors are stepped together.
    joints = {
        "screw_1": {"type": "revolute", "parent": "end_plate_1", "child": "lead_screw_1", "axis": ["lead_screw_1.a", "lead_screw_1.b"],
                    "range": ["screw_turn_max"], "drive": "actuated"},
        "screw_2": {"type": "revolute", "parent": "end_plate_1", "child": "lead_screw_2", "axis": ["lead_screw_2.a", "lead_screw_2.b"],
                    "drive": "passive"},
        "carriage": {"type": "slide", "parent": "end_plate_1", "child": "carriage_cover_1",
                     "axis": ["carriage_cover_1.a", "carriage_cover_1.b"], "drive": "passive"},
        "coupling_1": {"type": "fixed", "parent": "lead_screw_1", "child": "coupling_1"},
        "coupling_2": {"type": "fixed", "parent": "lead_screw_2", "child": "coupling_2"},
    }
    for name in carriage:
        joints[f"on_carriage_{name}"] = {"type": "fixed", "parent": "carriage_cover_1", "child": name}
    couplings = {
        "lead_1": {"driver": "screw_1", "driven": "carriage", "lead": "screw_lead"},
        "lead_2": {"driver": "screw_2", "driven": "carriage", "lead": "screw_lead"},
    }
    return {"parts": m.parts, "datums": m.datums, "assembly": A, "sheets": m.sheets, "threads": m.threads, "clears": m.clears,
            "joints": joints, "couplings": couplings}

