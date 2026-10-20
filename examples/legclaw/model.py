"""LegClaw (BLCM, 7th iteration): two legs on their connecting plates.

Reads every dimension from p (params.yaml); holds no dimension literals.
Frames: each leg is built in a leg frame whose origin is on its flip axis (Y),
Z up, inboard (towards the mount plate) +X. Leg b is leg a turned 180 deg about Z.
The foot is built in a foot frame at the sole centre; its right half is its left
half turned 180 deg about Z.
"""

import math

from build123d import *  # noqa: F403


# ---------------------------------------------------------------- parts
def ybar(L, H, W, xa, xb, pin_r):
    """Rounded bar along X (width H in Z, thickness W in Y) with pin bores at xa, xb."""
    r = H / 2
    body = Box(L - H, W, H)
    body += Cylinder(r, W, rotation=(90, 0, 0)).moved(Location((-(L - H) / 2, 0, 0)))
    body += Cylinder(r, W, rotation=(90, 0, 0)).moved(Location(((L - H) / 2, 0, 0)))
    for x in (xa, xb):
        body -= Cylinder(pin_r, W, rotation=(90, 0, 0)).moved(Location((x, 0, 0)))
    d = {
        "pin_a": (xa, 0, 0), "pin_a_lo": (xa, -W / 2, 0), "pin_a_hi": (xa, W / 2, 0),
        "pin_b": (xb, 0, 0), "pin_b_lo": (xb, -W / 2, 0), "pin_b_hi": (xb, W / 2, 0),
        "tip_a": (-L / 2, 0, 0), "tip_b": (L / 2, 0, 0),
    }
    return body, d


def setback(depth, taper):
    """How far an end face tapered by `taper` from its outer-edge hinge lies back at `depth` from that edge."""
    return depth * math.tan(math.radians(taper))


def phalanx(L, H, W, cut_l, cut_w, cut_h, taper):
    """Toe segment along X with a cut_w x cut_h channel along its length (or a slot when
    cut_h exceeds H); flexion hinges on the outer (-Z) edges of both ends, each end face
    tapered back by `taper` towards the inner (+Z) face so the segments can flex inward."""
    s = setback(H, taper)
    prof = Polygon((-L / 2, -H / 2), (L / 2, -H / 2), (L / 2 - s, H / 2), (-L / 2 + s, H / 2), align=None)
    part = extrude(Plane.XZ * prof, W / 2, both=True) - Box(cut_l, cut_w, cut_h)
    d = {
        "hp_a": (-L / 2, -W / 2, -H / 2), "hp_b": (-L / 2, W / 2, -H / 2),
        "hd_a": (L / 2, -W / 2, -H / 2), "hd_b": (L / 2, W / 2, -H / 2),
    }
    return part, d


def cable_bore(part, d, L, H, z, x0, x1, r, taper):
    """Bore of radius r along X at height z, from x0 to x1; eye datums "e0", "e1" on its axis at
    each end, where it leaves the part (an end clipped to the tapered end face at that height)."""
    s = setback(z + H / 2, taper)
    x0, x1 = max(x0, -L / 2 + s), min(x1, L / 2 - s)
    part -= Cylinder(r, x1 - x0, rotation=(0, 90, 0)).moved(Location(((x0 + x1) / 2, 0, z)))
    d.update({"e0": (x0, 0, z), "e1": (x1, 0, z)})
    return part


def ycyl(r, y0, y1, x, z):
    """Cylinder about Y from y0 to y1, axis through (x, z)."""
    return Cylinder(r, y1 - y0, rotation=(90, 0, 0)).moved(Location((x, (y0 + y1) / 2, z)))


def box(x0, x1, y0, y1, z0, z1):
    return Box(x1 - x0, y1 - y0, z1 - z0).moved(Location(((x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2)))


def place(pa, pb, xa, y):
    """Location of a bar part whose pin xa lands on pa and whose X axis points to pb (XZ plane)."""
    ux, uz = pb[0] - pa[0], pb[1] - pa[1]
    n = math.hypot(ux, uz)
    ux, uz = ux / n, uz / n
    phi = math.degrees(math.atan2(-uz, ux))
    return Location((pa[0] - xa * ux, y, pa[1] - xa * uz), (0, phi, 0))


# Which joints, loops, gears, tendons and cables build() returns, by name prefix (None: all).
MOTION = None


def build(p):
    parts, datums, assembly = {}, {}, {}
    joints, loops, gears, tendons, cables = {}, {}, {}, {}, {}

    def add_part(name, shape, d):
        parts[name] = shape
        datums.update({f"{name}.{k}": v for k, v in d.items()})

    # --- toe segments
    # the claw cable runs in a bore along each segment's inner wall (Fig. 2B end view)
    for name, L, H, W in (("phalanx1", p.ph1_L, p.ph1_H, p.ph1_W), ("phalanx2", p.ph2_L, p.ph2_H, p.ph2_W)):
        ph, d = phalanx(L, H, W, L, W - p.ph_wall * 2, H - p.ph_wall * 2, p.toe_taper)
        ph = cable_bore(ph, d, L, H, H / 2 - p.ph_wall / 2, -L / 2, L / 2, p.cab_r, p.toe_taper)
        add_part(name, ph, d)
    claw, d = phalanx(p.claw_L, p.claw_H, p.claw_W, p.claw_L - p.ph_wall * 2, p.claw_slot, p.claw_H, p.toe_taper)
    # through the proximal end wall only, into the slot, where the cable crosses to the paired toe
    claw = cable_bore(claw, d, p.claw_L, p.claw_H, p.claw_H / 2 - p.ph_wall / 2,
                      -p.claw_L / 2, -p.claw_L / 2 + p.ph_wall, p.cab_r, p.toe_taper)
    add_part("claw", claw, d)
    # toe-joint block: its bottom face tapered back from phalanx 1's hinge like the segments' ends
    th = p.tj_H / 2
    s_tj = setback(p.ph1_H, p.toe_taper)
    prof = Polygon((-p.ph1_H / 2, -th), (-p.ph1_H / 2, th), (p.ph1_H / 2, th), (p.ph1_H / 2, -th + s_tj), align=None)
    tj = extrude(Plane.XZ * prof, p.ph1_W / 2, both=True)
    tj -= Cylinder(p.pin_r, p.ph1_H, rotation=(0, 90, 0))
    x_cb = p.ph1_H / 2 - p.ph_wall / 2
    z_cb = -th + setback(x_cb + p.ph1_H / 2, p.toe_taper)
    tj -= Cylinder(p.cab_r, th - z_cb).moved(Location((x_cb, 0, (th + z_cb) / 2)))
    add_part("toe_joint", tj, {"axle_a": (-p.ph1_H / 2, 0, 0), "axle_b": (p.ph1_H / 2, 0, 0),
                               "eye_in": (x_cb, 0, th), "eye_out": (x_cb, 0, z_cb)})

    # --- bars
    comp_xa = -p.comp_L / 2 + p.comp_hub
    comp_xb = comp_xa + p.comp_pitch
    comp, d = ybar(p.comp_L, p.comp_H, p.comp_W, comp_xa, comp_xb, p.pin_r)
    add_part("comp", comp, d)
    bent_xa = -p.bent_pitch / 2
    bent, d = ybar(p.bent_L, p.bent_H, p.bent_W, bent_xa, -bent_xa, p.pin_r)
    add_part("bent", bent, d)
    lnk_xa = -p.lnk_pitch / 2
    lnk, d = ybar(p.lnk_L, p.lnk_H, p.lnk_W, lnk_xa, -lnk_xa, p.pin_r)
    add_part("linkage", lnk, d)

    # --- thigh (leg frame: flip axis on Y through the origin)
    tz_bot = -(p.thigh_L - p.ear_r)
    th_x, th_y = p.thigh_H / 2, p.thigh_W / 2
    thigh = box(-th_x, th_x, -th_y, th_y, tz_bot, -p.r_clear)
    thigh -= box(-th_x + p.wall, th_x - p.wall, -th_y + p.wall, th_y - p.wall,
                 tz_bot + p.wall, -p.r_clear - p.wall)
    hx, hy = p.ped_L / 2 + p.ped_clear, p.ped_H / 2 + p.ped_clear
    thigh -= box(-hx, hx, -hy, hy, tz_bot, tz_bot + p.wall)
    ear_y0 = th_y - p.ear_t
    for s in (1, -1):
        y0, y1 = sorted((s * ear_y0, s * th_y))
        thigh += box(-p.ear_r, p.ear_r, y0, y1, -p.r_clear, 0)
        thigh += ycyl(p.ear_r, y0, y1, 0, 0)
    thigh -= ycyl(p.pin_r, -th_y, th_y, 0, 0)
    # tendon servos: upper one left of centre, lower one right, both against the front (-Y) wall
    in_x = th_x - p.wall
    sx1 = -in_x + p.servo_in
    sx2 = in_x - p.servo_in
    sz1 = -p.r_clear - p.wall - p.servo_H / 2
    sz2 = sz1 - p.srv_pitch_z
    for sx, sz in ((sx1, sz1), (sx2, sz2)):
        thigh -= ycyl(p.shaft_r, -th_y, -th_y + p.wall, sx, sz)
    z_up = tz_bot + p.piv_in
    hx4 = p.d4 / 2
    add_part("thigh", thigh, {
        "flip_a": (0, -(ear_y0 + p.ear_t / 2), 0), "flip_b": (0, ear_y0 + p.ear_t / 2, 0),
        "up_l": (-hx4, th_y, z_up), "up_r": (hx4, th_y, z_up),
        "guide": (-th_x, 0, tz_bot + p.wall),
    })

    # --- servos, steering wheel, plate
    srv = box(-p.servo_in, p.servo_L - p.servo_in, 0, p.servo_D, -p.servo_H / 2, p.servo_H / 2)
    srv += ycyl(p.shaft_r, -p.wall, 0, 0, 0)
    add_part("servo_single", srv, {"out": (0, -p.wall, 0), "out_in": (0, 0, 0)})
    dual = box(-p.servo_in, p.servo_L - p.servo_in, -p.servo_D / 2, p.servo_D / 2, -p.servo_H / 2, p.servo_H / 2)
    dual += ycyl(p.shaft_r, -ear_y0, -p.servo_D / 2, 0, 0)
    dual += ycyl(p.shaft_r, p.servo_D / 2, ear_y0, 0, 0)
    add_part("servo_dual", dual, {"out_a": (0, -ear_y0, 0), "out_b": (0, ear_y0, 0)})
    wheel = ycyl(p.wheel_d / 2, -p.wheel_t / 2, p.wheel_t / 2, 0, 0)
    add_part("wheel", wheel, {"hub_a": (0, -p.wheel_t / 2, 0), "hub_b": (0, p.wheel_t / 2, 0)})
    plate = box(-p.plate_t / 2, p.plate_t / 2, -p.plate_w / 2, p.plate_w / 2, -p.plate_h / 2, p.plate_h / 2)
    add_part("plate", plate, {"face": (-p.plate_t / 2, 0, 0)})

    # --- four-bar geometry and pedestal
    z_k = z_up - p.h_min
    z_lo = z_k - p.h_min
    z_p = z_lo - p.ped_lo_in + p.ped_bent_in
    pz0, pz1 = -p.ped_bent_in, p.ped_W - p.ped_bent_in
    ped = box(-p.ped_L / 2, p.ped_L / 2, -p.ped_H / 2, p.ped_H / 2, pz0, pz0 + p.ped_base_h)
    ped += Cylinder(p.ped_shaft_r, p.ped_W - p.ped_base_h).moved(
        Location((0, 0, (pz0 + p.ped_base_h + pz1) / 2)))
    z_lo_rel = p.ped_lo_in - p.ped_bent_in
    for x, z in ((0, 0), (-hx4, z_lo_rel), (hx4, z_lo_rel)):
        ped -= ycyl(p.pin_r, -p.ped_H / 2, p.ped_H / 2, x, z)
    add_part("pedestal", ped, {"slide_a": (0, 0, pz0), "slide_b": (0, 0, pz1),
                               "piv_bent": (0, 0, 0)})

    # --- foot (foot frame at the sole centre; left half built, right half = turned 180 about Z)
    fy = p.foot_fy
    zsh = p.sole_H / 2 - p.pin_r
    x_e = -(p.mid_m + p.cell_s)
    v2 = p.cell_v / 2
    y_bf = p.ped_H / 2 + p.bent_W / 2                 # front bent linkage layer (left half)
    y_bb = -p.bent_yb                                  # back bent linkage layer (left half)
    endf = box(-p.sole_L / 2, -p.sole_L / 2 + p.end_wall, -fy, fy, -p.sole_H / 2, p.sole_H / 2)
    for s in (1, -1):
        y0, y1 = sorted((s * (fy - p.cheek_t), s * fy))
        endf += box(-p.sole_L / 2, -p.x_sh + p.frame_in, y0, y1, -p.sole_H / 2, p.sole_H / 2)
    endf += ycyl(p.pin_r, -fy, fy, -p.x_sh, zsh)
    y_boss = fy + p.lnk_W
    endf += ycyl(p.pin_r, fy, y_boss, x_e, v2)
    endf += ycyl(p.pin_r, -y_boss, -fy, x_e, v2)
    add_part("foot_end", endf, {
        "pin_bot_f": (x_e, fy, -v2), "pin_bot_b": (x_e, -fy, -v2),
        "spr_top_f": (x_e, fy, v2), "spr_top_b": (x_e, -fy, v2),
        "boss_top_f": (x_e, y_boss, v2), "boss_top_b": (x_e, -y_boss, v2),
        "sh_f": (-p.x_sh, y_bf, zsh), "sh_b": (-p.x_sh, y_bb, zsh),
    })
    mid_x = p.mid_m + p.lnk_H
    mid = box(-mid_x, mid_x, -fy, fy, -p.bar_h / 2, p.bar_h / 2)
    for s in (1, -1):
        y0, y1 = sorted((s * (fy - p.post_t), s * fy))
        mid += box(-mid_x, mid_x, y0, y1, -p.sole_H / 2, p.sole_H / 2)
    md = {"slide_a": (0, 0, -p.bar_h / 2), "slide_b": (0, 0, p.bar_h / 2)}
    for side, sx in (("L", -1), ("R", 1)):
        for row, sy in (("f", 1), ("b", -1)):
            md[f"spr_top_{side}{row}"] = (sx * p.mid_m, sy * fy, v2)
            md[f"spr_bot_{side}{row}"] = (sx * p.mid_m, sy * fy, -v2)
    add_part("foot_mid", mid, md)

    # --- per-leg assembly
    h_drop = math.sqrt(p.bent_pitch ** 2 - p.x_sh ** 2)
    z_f = z_p - h_drop - zsh
    y_up = th_y + p.comp_W / 2
    y_lo = th_y - p.comp_W / 2
    yA, yB = p.lnk_yA, p.lnk_yB
    tz = -p.sole_H / 2 - p.beta_gap - p.tj_H / 2
    turn = Location((0, 0, 0), (0, 0, 180))

    for leg, leg_loc in (("a", Location((-p.leg_dx / 2, 0, 0))),
                         ("b", Location((p.leg_dx / 2, 0, 0)) * turn)):
        def put(inst, part, loc):
            assembly[f"{leg}_{inst}"] = (part, leg_loc * loc)
            return f"{leg}_{inst}"

        plate_i = put("plate", "plate", Location((p.servo_L - p.servo_in + p.plate_t / 2, 0, 0)))
        dual_i = put("dual", "servo_dual", Location((0, 0, 0)))
        thigh_i = put("thigh", "thigh", Location((0, 0, 0)))
        joints[f"{leg}_dual_mount"] = {"type": "fixed", "parent": plate_i, "child": dual_i}
        joints[f"{leg}_flip"] = {"type": "revolute", "parent": dual_i, "child": thigh_i,
                                 "axis": [f"{thigh_i}.flip_a", f"{thigh_i}.flip_b"],
                                 "range": ["flip_turn"], "drive": "actuated"}
        sy_face = -th_y + p.wall
        for k, (sx, sz, rot) in enumerate(((sx1, sz1, 0), (sx2, sz2, 180)), start=1):
            s_i = put(f"srv{k}", "servo_single", Location((sx, sy_face, sz), (0, rot, 0)))
            w_i = put(f"whl{k}", "wheel", Location((sx, -th_y - p.wheel_t / 2, sz)))
            joints[f"{leg}_srv{k}_mount"] = {"type": "fixed", "parent": thigh_i, "child": s_i}
            joints[f"{leg}_whl{k}"] = {"type": "revolute", "parent": s_i, "child": w_i,
                                       "axis": [f"{w_i}.hub_b", f"{w_i}.hub_a"],
                                       "range": ["servo_turn" if k == 1 else "splay_turn"], "drive": "actuated"}

        ped_i = put("ped", "pedestal", Location((0, 0, z_p)))
        joints[f"{leg}_slide"] = {"type": "slide", "parent": thigh_i, "child": ped_i,
                                  "axis": [f"{ped_i}.slide_a", f"{ped_i}.slide_b"],
                                  "range": ["slide_max"], "drive": "passive"}
        for side, sx in (("l", -1), ("r", 1)):
            up_i = put(f"up_{side}", "comp", place((sx * hx4, z_up), (sx * p.Dmin / 2, z_k), comp_xa, y_up))
            lo_i = put(f"lo_{side}", "comp", place((sx * hx4, z_lo), (sx * p.Dmin / 2, z_k), comp_xa, y_lo))
            joints[f"{leg}_up_{side}"] = {"type": "revolute", "parent": thigh_i, "child": up_i,
                                          "axis": [f"{up_i}.pin_a_lo", f"{up_i}.pin_a_hi"], "drive": "passive"}
            joints[f"{leg}_lo_{side}"] = {"type": "revolute", "parent": ped_i, "child": lo_i,
                                          "axis": [f"{lo_i}.pin_a_lo", f"{lo_i}.pin_a_hi"], "drive": "passive"}
            loops[f"{leg}_knee_{side}"] = [f"{up_i}.pin_b_lo", f"{lo_i}.pin_b_hi"]
        gears[f"{leg}_mesh"] = {"driver": f"{leg}_up_l", "driven": f"{leg}_up_r", "ratio": "gear_ratio"}

        foot = Location((0, 0, z_f))
        mid_i = put("mid", "foot_mid", foot)
        joints[f"{leg}_foot"] = {"type": "slide", "parent": ped_i, "child": mid_i,
                                 "axis": [f"{mid_i}.slide_a", f"{mid_i}.slide_b"], "drive": "passive"}
        for side, half in (("L", foot), ("R", foot * turn)):
            end_i = put(f"end_{side}", "foot_end", half)
            # X-structure linkages: A from the centre post's top pin to the end frame's bottom pin,
            # B from the post's bottom pin to the frame's top pin; front (+Y) and back (-Y) rows.
            a_f = put(f"lnk_{side}Af", "linkage", half * place((-p.mid_m, v2), (x_e, -v2), lnk_xa, yA))
            b_f = put(f"lnk_{side}Bf", "linkage", half * place((-p.mid_m, -v2), (x_e, v2), lnk_xa, yB))
            a_b = put(f"lnk_{side}Ab", "linkage", half * place((-p.mid_m, v2), (x_e, -v2), lnk_xa, -yA))
            b_b = put(f"lnk_{side}Bb", "linkage", half * place((-p.mid_m, -v2), (x_e, v2), lnk_xa, -yB))
            for li in (a_f, b_f, a_b, b_b):
                joints[f"{li}_pin"] = {"type": "revolute", "parent": mid_i, "child": li,
                                       "axis": [f"{li}.pin_a_lo", f"{li}.pin_a_hi"], "drive": "passive"}
            joints[f"{end_i}_pin"] = {"type": "revolute", "parent": a_f, "child": end_i,
                                      "axis": [f"{end_i}.pin_bot_b", f"{end_i}.pin_bot_f"], "drive": "passive"}
            loops[f"{b_f}_end"] = [f"{b_f}.pin_b_lo", f"{end_i}.boss_top_f"]
            loops[f"{a_b}_end"] = [f"{a_b}.pin_b_hi", f"{end_i}.pin_bot_b"]
            loops[f"{b_b}_end"] = [f"{b_b}.pin_b_hi", f"{end_i}.boss_top_b"]
            # tension springs along the top and bottom of each cell, front and back rows.
            # The right half is the left half turned about Z, so its local front row is the
            # centre post's back row.
            for row in ("f", "b"):
                mrow = row if side == "L" else ("b" if row == "f" else "f")
                for lvl, end_d in (("top", f"spr_top_{row}"), ("bot", f"pin_bot_{row}")):
                    tendons[f"{leg}_spr_{side}{row}_{lvl}"] = {
                        "path": [f"{mid_i}.spr_{lvl}_{side}{mrow}", f"{end_i}.{end_d}"],
                        "stiffness": "spring_k"}
            # bent linkages from the concentric pedestal pivot to the end frame's shaft
            pivot = (0, z_p - z_f)
            for row, yb in (("f", y_bf), ("b", y_bb)):
                b_i = put(f"bent_{side}{row}", "bent",
                          half * place(pivot, (-p.x_sh, zsh), bent_xa, yb))
                joints[f"{b_i}_pin"] = {"type": "revolute", "parent": ped_i, "child": b_i,
                                        "axis": [f"{b_i}.pin_a_lo", f"{b_i}.pin_a_hi"], "drive": "passive"}
                loops[f"{b_i}_shaft"] = [f"{b_i}.pin_b", f"{end_i}.sh_{row}"]
            # toes: rotation joint (beta) about X, then two phalanges and the claw flexing inward
            toe = {}
            for row, sy in (("f", 1), ("b", -1)):
                tl = half * Location((-p.toe_x, sy * p.toe_y, tz))
                tj_i = put(f"toe_{side}{row}_j", "toe_joint", tl)
                z1 = -p.tj_H / 2 - p.ph1_L / 2
                z2 = -p.tj_H / 2 - p.ph1_L - p.ph2_L / 2
                z3 = -p.tj_H / 2 - p.ph1_L - p.ph2_L - p.claw_L / 2
                p1_i = put(f"toe_{side}{row}_p1", "phalanx1", tl * Location((0, 0, z1), (0, 90, 0)))
                p2_i = put(f"toe_{side}{row}_p2", "phalanx2", tl * Location((0, 0, z2), (0, 90, 0)))
                c_i = put(f"toe_{side}{row}_c", "claw",
                          tl * Location((p.ph2_H / 2 - p.claw_H / 2, 0, z3), (0, 90, 0)))
                # +X turns a front toe outward (+Y); the right half is the left one turned
                ax = ["axle_a", "axle_b"] if row == "f" else ["axle_b", "axle_a"]
                joints[f"{tj_i}_beta"] = {"type": "revolute", "parent": end_i, "child": tj_i,
                                          "axis": [f"{tj_i}.{ax[0]}", f"{tj_i}.{ax[1]}"],
                                          "range": ["toe_min", "toe_max"], "drive": "passive",
                                          "stiffness": "toe_k"}
                for parent, child in ((tj_i, p1_i), (p1_i, p2_i), (p2_i, c_i)):
                    joints[f"{child}_flex"] = {"type": "revolute", "parent": parent, "child": child,
                                               "axis": [f"{child}.hp_a", f"{child}.hp_b"], "drive": "passive"}
                toe[row] = (tj_i, p1_i, p2_i, c_i)
            # one claw cable per same-side pair of toes (wheel 1): down toe f through its bores, across
            # between the claws' slots, up toe b; one toe-motion cable (wheel 2) spreads the pair's beta
            (tf, p1f, p2f, cf), (tb, p1b, p2b, cb) = toe["f"], toe["b"]
            down = [f"{tf}.eye_in", f"{tf}.eye_out"] + [f"{i}.{e}" for i in (p1f, p2f, cf) for e in ("e0", "e1")]
            up = [f"{i}.{e}" for i in (cb, p2b, p1b) for e in ("e1", "e0")] + [f"{tb}.eye_out", f"{tb}.eye_in"]
            cables[f"{leg}_claw_{side}"] = {
                "path": [f"{thigh_i}.guide", *down, *up], "wheel": f"{leg}_whl1",
                "closes": {f"{i}_flex": "claw_close" for i in (p1f, p2f, cf, p1b, p2b, cb)}}
            cables[f"{leg}_splay_{side}"] = {
                "path": [f"{thigh_i}.guide", f"{tf}.eye_in", f"{tb}.eye_in"], "wheel": f"{leg}_whl2",
                "closes": {f"{tf}_beta": "toe_max", f"{tb}_beta": "toe_max"}}

    def keep(d):
        return {k: v for k, v in d.items() if MOTION is None or k.startswith(MOTION)}

    return {"parts": parts, "datums": datums, "assembly": assembly,
            "joints": keep(joints), "loops": keep(loops), "gears": keep(gears), "tendons": keep(tendons),
            "cables": keep(cables)}
