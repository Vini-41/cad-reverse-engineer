"""COMPAct SSPG 7.2:1 gearbox: parametric model. Every dimension comes from p (params.yaml).

Frames: each part's axis is z. The casing's output face is z = 0; the motor end is up.
Angles (deg) of the bolt patterns follow the released bodies: the casing's lugs and output-end holes at 90 + k * 360 / n,
the carriers' planet pins at 90 + k * 360 / n_planets, their extrusion bolts at -90 + k * 360 / n_planets.
"""

from math import acos, cos, floor, radians, sin, sqrt, tan

from build123d import *  # noqa: F403

UP = (Align.CENTER, Align.CENTER, Align.MIN)


def inv(a):
    return tan(a) - a


def flank_psi(z, rb, alpha, r):
    """Half the angular thickness of a zero-backlash tooth at radius r (rad); radial below the base circle."""
    return radians(90 / z) + inv(radians(alpha)) - inv(acos(rb / max(r, rb)))


def involute_outline(z, m, alpha, ra, rf, phase):
    """Closed outline of an external involute gear: z teeth of module m, pressure angle alpha (deg), tip radius ra,
    root radius rf, tooth 0 centred at angle phase (deg). Flank vertices at the root (or base), the pitch, the tip and
    halfway between; below the base circle the flank runs radially to the root."""
    rp = m * z / 2
    rb = rp * cos(radians(alpha))
    r0 = max(rf, rb)
    side = []
    if rf < rb:
        side.append((rf, flank_psi(z, rb, alpha, rb)))
    for r in (r0, (r0 + rp) / 2, rp, (rp + ra) / 2, ra):
        side.append((r, flank_psi(z, rb, alpha, r)))
    pts = []
    for k in range(int(z)):
        th = radians(phase + k * 360 / z)
        for r, ps in side:
            pts.append((r * cos(th - ps), r * sin(th - ps)))
        for r, ps in reversed(side):
            pts.append((r * cos(th + ps), r * sin(th + ps)))
    return pts


def flank_point(z, m, alpha, r, k, phase, sense, h):
    """Point at radius r on tooth k's flank (sense -1: clockwise flank, 1: counter-clockwise), at height h."""
    rb = m * z / 2 * cos(radians(alpha))
    th = radians(phase + k * 360 / z) + sense * flank_psi(z, rb, alpha, r)
    return (r * cos(th), r * sin(th), h)


def prism(pts, h):
    return extrude(Face(Wire.make_polygon([Vector(x, y, 0) for x, y in pts], close=True)), amount=h)


def polar(r, deg, h):
    return (r * cos(radians(deg)), r * sin(radians(deg)), h)


def at(r, deg, h):
    return Pos(*polar(r, deg, h))


def revolve_rz(pts):
    """Solid of revolution about z of a closed (r, z) polygon."""
    face = Face(Wire.make_polygon([Vector(r, z, 0) for r, z in pts], close=True))
    return revolve(Plane.XZ * face, Axis.Z)


def frac(x):
    return x - floor(x)


def junction_fillet(face, centres, small_r, big_r, radius):
    """Round the corners where small circles (at centres) meet a circle of radius big_r about the origin."""
    vs = []
    for v in face.vertices():
        on_big = abs(sqrt(v.X * v.X + v.Y * v.Y) - big_r) < small_r / big_r
        on_small = min(abs(sqrt((v.X - cx) ** 2 + (v.Y - cy) ** 2) - small_r) for cx, cy in centres) < small_r / big_r
        if on_big and on_small:
            vs.append(v)
    return fillet(vs, radius)


def build(p):
    parts, datums, assembly = {}, {}, {}
    m, a = p.module, p.pressure_angle
    n_pl = int(p.n_planets)
    cd = p.centre_dist

    def D(part, feat, xyz):
        datums[f"{part}.{feat}"] = tuple(xyz)

    # ================================================================ planet: faces at z = 0 and planet_w
    zp = p.z_planet
    rp_p = m * zp / 2
    ra_p = rp_p + p.addendum_coef * m
    rf_p = rp_p - p.dedendum_coef * m
    planet = prism(involute_outline(zp, m, a, ra_p, rf_p, p.planet_phase), p.planet_w)
    planet -= Cylinder(p.planet_bore / 2, p.planet_w, align=UP)
    planet -= Cylinder(p.planet_cb_d / 2, p.planet_cb_h, align=UP)
    planet -= Pos(0, 0, p.planet_w - p.planet_cb_h) * Cylinder(p.planet_cb_d / 2, p.planet_cb_h, align=UP)
    parts["planet_gear"] = planet
    P = "planet_gear"
    half_p = (zp - 1) / 2
    D(P, "axis", (0, 0, p.planet_w / 2))
    D(P, "axis_seat", (0, 0, p.planet_cb_h / 2))
    D(P, "flank_a", polar(rp_p, p.planet_phase - 90 / zp, p.planet_w / 2))
    D(P, "flank_b", polar(rp_p, p.planet_phase + 180 - 90 / zp, p.planet_w / 2))
    D(P, "tip0", flank_point(zp, m, a, ra_p, 0, p.planet_phase, -1, 0))
    D(P, "tip0_top", flank_point(zp, m, a, ra_p, 0, p.planet_phase, -1, p.planet_w))
    D(P, "tip_h", flank_point(zp, m, a, ra_p, half_p, p.planet_phase, -1, 0))
    D(P, "bore_a", (p.planet_bore / 2, 0, p.planet_cb_h))
    D(P, "bore_b", (-p.planet_bore / 2, 0, p.planet_cb_h))
    D(P, "cb_a", (p.planet_cb_d / 2, 0, 0))
    D(P, "cb_b", (-p.planet_cb_d / 2, 0, 0))
    D(P, "cb_floor", (p.planet_cb_d / 2, 0, p.planet_cb_h))

    # ================================================================ sun: shaft end at z = 0
    zs = p.z_sun
    rp_s = m * zs / 2
    ra_s = rp_s + p.addendum_coef * m
    rf_s = rp_s - p.dedendum_coef * m
    s_step0 = p.sun_shaft_l
    s_step1 = s_step0 + p.sun_step_h
    s_g0 = s_step1 + p.sun_hub_ch
    s_g1 = s_g0 + p.sun_face
    s_top = s_g1 + p.sun_fl_t
    sun = revolve_rz([(0, 0), (p.sun_tip_d / 2, 0), (p.sun_shaft_d / 2, p.sun_cham), (p.sun_shaft_d / 2, s_step0),
                      (p.sun_step_d / 2, s_step0), (p.sun_step_d / 2, s_step1), (p.sun_hub_d / 2, s_g0), (0, s_g0)])
    sun += Pos(0, 0, s_g0) * prism(involute_outline(zs, m, a, ra_s, rf_s, p.sun_phase), p.sun_face)
    sun += Pos(0, 0, s_g1) * Cylinder(p.sun_fl_d / 2, p.sun_fl_t, align=UP)
    sun -= Cylinder(p.sun_bore_d / 2, s_top, align=UP)
    sun -= Pos(0, 0, s_top - p.sun_cb_h) * Cylinder(p.sun_cb_d / 2, p.sun_cb_h, align=UP)
    n_sh = int(p.sun_n_holes)
    for k in range(n_sh):
        ang = k * 360 / n_sh
        sun -= at(p.sun_pcd / 2, ang, s_g1) * Cylinder(p.sun_hole / 2, p.sun_fl_t, align=UP)
        sun -= at(p.sun_pcd / 2, ang, s_g1) * Cone(p.sun_csk / 2, p.sun_hole / 2, p.sun_csk_h, align=UP)
    parts["sun_gear"] = sun
    S = "sun_gear"
    hr = p.sun_pcd / 2
    D(S, "axis_lo", (0, 0, s_step0 / 2))
    D(S, "axis_hi", (0, 0, s_g0))
    D(S, "flank_a", polar(rp_s, p.sun_phase - 90 / zs, (s_g0 + s_g1) / 2))
    D(S, "flank_b", polar(rp_s, p.sun_phase + 180 - 90 / zs, (s_g0 + s_g1) / 2))
    D(S, "gt0", flank_point(zs, m, a, ra_s, 0, p.sun_phase, -1, s_g0))
    D(S, "gt1", flank_point(zs, m, a, ra_s, 0, p.sun_phase, -1, s_g1))
    D(S, "tip_h", flank_point(zs, m, a, ra_s, (zs - 1) / 2, p.sun_phase, -1, s_g0))
    D(S, "tip_bot", (p.sun_tip_d / 2, 0, 0))
    D(S, "fl_top", (p.sun_fl_d / 2, 0, s_top))
    D(S, "bd0", (p.sun_bore_d / 2, 0, s_top - p.sun_cb_h))
    D(S, "cb0", (p.sun_cb_d / 2, 0, s_top - p.sun_cb_h))
    D(S, "cb1", (p.sun_cb_d / 2, 0, s_top))
    D(S, "cb_b", (-p.sun_cb_d / 2, 0, s_top))
    D(S, "td0", (p.sun_bore_d / 2, 0, 0))
    D(S, "ch1", (p.sun_shaft_d / 2, 0, p.sun_cham))
    D(S, "sd0", (p.sun_shaft_d / 2, 0, s_step0))
    D(S, "sh1", (p.sun_step_d / 2, 0, s_step0))
    D(S, "st1", (p.sun_step_d / 2, 0, s_step1))
    D(S, "step_b", (-p.sun_step_d / 2, 0, s_step1))
    D(S, "hub_a", (p.sun_hub_d / 2, 0, s_g0))
    D(S, "hub_b", (-p.sun_hub_d / 2, 0, s_g0))
    D(S, "ft0", (p.sun_fl_d / 2, 0, s_g1))
    D(S, "h90", (p.sun_hole / 2, hr, s_top))
    D(S, "h90_b", (-p.sun_hole / 2, hr, s_top))
    D(S, "h270", (p.sun_hole / 2, -hr, s_top))
    D(S, "h0", (hr + p.sun_hole / 2, 0, s_top))
    D(S, "csk_a", (p.sun_csk / 2, hr, s_g1))
    D(S, "csk_b", (-p.sun_csk / 2, hr, s_g1))
    D(S, "ck1", (p.sun_hole / 2, hr, s_g1 + p.sun_csk_h))

    # ================================================================ primary carrier: output face at z = 0
    c_top = p.car_disc_h + p.car_fl_t
    pin_ang = [90 + k * 360 / n_pl for k in range(n_pl)]
    bolt_ang = [-90 + k * 360 / n_pl for k in range(n_pl)]
    car = revolve_rz([(0, 0), (p.car_disc_d / 2 - p.car_cham, 0), (p.car_disc_d / 2, p.car_cham), (p.car_disc_d / 2, p.car_disc_h),
                      (p.car_fl_d / 2, p.car_disc_h), (p.car_fl_d / 2, c_top), (0, c_top)])
    ext = Circle(p.car_disc_d / 2) - Circle(p.ext_in_r)
    for ang in pin_ang:
        ext -= Pos(*polar(cd, ang, 0)[:2]) * Circle(p.ext_clear_r)
    ext = fillet(ext.vertices(), p.ext_fillet)
    car += Pos(0, 0, c_top) * extrude(ext, amount=p.car_h - c_top)
    col_top = c_top + p.car_col_h
    for ang in pin_ang:
        collar = Pos(0, 0, c_top) * Cylinder(p.car_col / 2, p.car_col_h, align=UP)
        collar = fillet(collar.edges().group_by(Axis.Z)[-1], p.car_col_f)
        car += at(cd, ang, 0) * collar
        car += at(cd, ang, col_top) * Cylinder(p.car_pin / 2, p.car_h - col_top, align=UP)
        car -= at(cd, ang, 0) * Cylinder(p.car_pinb / 2, p.car_h, align=UP)
        car -= at(cd, ang, 0) * Cylinder(p.car_pinb / 2 + p.car_pock_dr, p.car_pock_h, align=UP)
    for ang in bolt_ang:
        car -= at(p.car_bolt_r, ang, 0) * Cylinder(p.car_bolt / 2, p.car_h, align=UP)
        car -= at(p.car_bolt_r, ang, 0) * Cylinder(p.car_bolt / 2 + p.car_bcb_dr, p.car_bcb_h, align=UP)
    car -= Cylinder(p.car_b1 / 2, p.car_b1_h, align=UP)
    car -= Pos(0, 0, p.car_b1_h) * Cylinder(p.car_b2 / 2, p.car_b2_h, align=UP)
    car -= Pos(0, 0, p.car_b1_h + p.car_b2_h) * Cone(p.car_b2 / 2, p.car_b2c / 2, c_top - p.car_b1_h - p.car_b2_h, align=UP)
    n_nut = int(p.car_n_nuts)
    rn = p.car_nut_d / 2
    for k in range(n_nut):
        ang = k * 360 / n_nut
        car -= at(rn, ang, 0) * Cylinder(p.car_nut / 2, c_top, align=UP)
        car -= at(rn, ang, c_top - p.car_hex_h) * extrude(RegularPolygon(p.car_hex / 2, int(p.hex_sides), rotation=90), amount=p.car_hex_h)
    parts["primary_carrier"] = car
    C = "primary_carrier"
    pin = (0, cd)
    rb_ = p.car_bolt_r
    pock_r = p.car_pinb / 2 + p.car_pock_dr
    bcb_r = p.car_bolt / 2 + p.car_bcb_dr
    b30 = polar(rb_, -90 + 360 / n_pl, p.car_h)
    nut_ang = [k * 360 / n_nut for k in range(n_nut)]
    n60 = polar(rn, nut_ang[1], 0)
    n120 = polar(rn, nut_ang[2], 0)
    D(C, "axis_lo", (0, 0, p.car_b1_h / 2))
    D(C, "axis_hi", (0, 0, p.car_b1_h + p.car_b2_h / 2))
    D(C, "bot", (p.car_disc_d / 2 - p.car_cham, 0, 0))
    D(C, "pintop", (p.car_pin / 2, cd, p.car_h))
    D(C, "pin_b", (-p.car_pin / 2, cd, p.car_h))
    D(C, "disc_a", (p.car_disc_d / 2, 0, p.car_cham))
    D(C, "disc_b", (-p.car_disc_d / 2, 0, p.car_cham))
    D(C, "fd0", (p.car_disc_d / 2, 0, p.car_disc_h))
    D(C, "ft0", (p.car_fl_d / 2, 0, p.car_disc_h))
    D(C, "ft1", (p.car_fl_d / 2, 0, c_top))
    D(C, "b1_a", (p.car_b1 / 2, 0, 0))
    D(C, "b1_b", (-p.car_b1 / 2, 0, 0))
    D(C, "b2_a", (p.car_b2 / 2, 0, p.car_b1_h))
    D(C, "b2_b", (-p.car_b2 / 2, 0, p.car_b1_h))
    D(C, "b2z1", (p.car_b2 / 2, 0, p.car_b1_h + p.car_b2_h))
    D(C, "b2c_a", (p.car_b2c / 2, 0, c_top))
    D(C, "b2c_b", (-p.car_b2c / 2, 0, c_top))
    D(C, "b2c_s", (0, -p.car_b2c / 2, c_top))
    D(C, "etip", (0, -p.ext_in_r, c_top))
    D(C, "pk0", (-pock_r, cd, p.car_pock_h))
    D(C, "pk1", (-p.car_pinb / 2, cd, p.car_pock_h))
    D(C, "pkd0", (-pock_r, cd, 0))
    D(C, "pinb_a", (p.car_pinb / 2, cd, p.car_h))
    D(C, "pinb_b", (-p.car_pinb / 2, cd, p.car_h))
    D(C, "col_a", (p.car_col / 2, cd, c_top))
    D(C, "col_b", (-p.car_col / 2, cd, c_top))
    D(C, "co1", (p.car_pin / 2, cd, col_top))
    D(C, "cf0", (p.car_col / 2, cd, col_top - p.car_col_f))
    D(C, "bolt_a", (p.car_bolt / 2, -rb_, p.car_h))
    D(C, "bolt_b", (-p.car_bolt / 2, -rb_, p.car_h))
    D(C, "bc0", (-bcb_r, -rb_, p.car_bcb_h))
    D(C, "bc1", (-p.car_bolt / 2, -rb_, p.car_bcb_h))
    D(C, "bcd0", (-bcb_r, -rb_, 0))
    D(C, "bR1", (b30[0] + p.car_bolt / 2, b30[1], p.car_h))
    D(C, "nR0", (rn + p.car_nut / 2, 0, 0))
    D(C, "nut_b", (rn - p.car_nut / 2, 0, 0))
    D(C, "nR1", (-rn + p.car_nut / 2, 0, 0))
    D(C, "n60", (n60[0] + p.car_nut / 2, n60[1], 0))
    D(C, "n120", (n120[0] + p.car_nut / 2, n120[1], 0))
    D(C, "hx0", (rn, p.car_hex / 2, c_top))
    D(C, "hx1", (rn, -p.car_hex / 2, c_top))
    D(C, "hxd0", (rn, p.car_hex / 2, c_top - p.car_hex_h))
    hx30 = polar(p.car_hex / 2, 90 - 360 / p.hex_sides, c_top)
    hx150 = polar(p.car_hex / 2, 90 + 360 / p.hex_sides, c_top)
    D(C, "hx30", (rn + hx30[0], hx30[1], c_top))
    D(C, "hx150", (rn + hx150[0], hx150[1], c_top))
    mid = (c_top + p.car_h) / 2
    D(C, "pin_axis", (0, cd, mid))
    D(C, "pin_axis_lo", (0, cd, p.cas_b1_h + p.cas_lip_h / 2))
    D(C, "ext_side", (polar(p.ext_clear_r, -90 + 180 / n_pl, 0)[0], cd + polar(p.ext_clear_r, -90 + 180 / n_pl, 0)[1], mid))

    # ================================================================ secondary carrier: boss faces at z = 0
    s_pl0 = p.sec_boss_h
    s_pl1 = s_pl0 + p.sec_t
    boss_top_r = p.sec_pin / 2 + p.sec_boss_dr
    sec = Pos(0, 0, s_pl0) * (Cylinder(p.sec_od / 2, p.sec_t, align=UP) - Cylinder(p.sec_id / 2, p.sec_t, align=UP))
    boss = revolve_rz([(p.sec_boss_id / 2 + p.sec_boss_ch, 0), (p.sec_boss_bot_r, 0), (boss_top_r, s_pl0),
                       (p.sec_boss_id / 2, s_pl0), (p.sec_boss_id / 2, p.sec_boss_ch)])
    for ang in pin_ang:
        sec += (at(cd, ang, 0) * boss) & Cylinder(p.sec_od / 2, s_pl0, align=UP)
        sec -= at(cd, ang, 0) * Cylinder(p.sec_pin / 2, s_pl1, align=UP)
        sec -= at(cd, ang, s_pl1 - p.sec_hex_h) * extrude(RegularPolygon(p.sec_phex / 2, int(p.hex_sides)), amount=p.sec_hex_h)
    for ang in bolt_ang:
        sec -= at(p.sec_bolt_r, ang, 0) * Cylinder(p.sec_bolt / 2, s_pl1, align=UP)
        sec -= at(p.sec_bolt_r, ang, s_pl1 - p.sec_hex_h) * extrude(RegularPolygon(p.sec_bhex / 2, int(p.hex_sides), rotation=90), amount=p.sec_hex_h)
    parts["secondary_carrier"] = sec
    K = "secondary_carrier"
    sb = p.sec_bolt_r
    k30 = polar(sb, -90 + 360 / n_pl, s_pl0)
    pin2 = polar(cd, pin_ang[-1], s_pl1)
    D(K, "od_a", (p.sec_od / 2, 0, s_pl1))
    D(K, "od_b", (-p.sec_od / 2, 0, s_pl1))
    D(K, "id_a", (p.sec_id / 2, 0, s_pl1))
    D(K, "id_b", (-p.sec_id / 2, 0, s_pl1))
    D(K, "t0", (p.sec_od / 2, 0, s_pl0))
    D(K, "bh0", (p.sec_boss_id / 2 + p.sec_boss_ch, cd, 0))
    D(K, "bh1", (p.sec_boss_id / 2, cd, s_pl0))
    D(K, "bid_b", (-p.sec_boss_id / 2, cd, s_pl0))
    D(K, "bc0", (p.sec_boss_id / 2, cd, p.sec_boss_ch))
    D(K, "bt0", (0, cd - p.sec_pin / 2, s_pl0))
    D(K, "bt1", (0, cd - boss_top_r, s_pl0))
    D(K, "pin_a", (p.sec_pin / 2, cd, s_pl0))
    D(K, "pin_b", (-p.sec_pin / 2, cd, s_pl0))
    D(K, "ph0", (p.sec_phex / 2, cd, s_pl1))
    D(K, "ph1", (-p.sec_phex / 2, cd, s_pl1))
    D(K, "hd0", (p.sec_phex / 2, cd, s_pl1 - p.sec_hex_h))
    D(K, "ph2", (pin2[0] + p.sec_phex / 2, pin2[1], s_pl1))
    D(K, "bolt_a", (p.sec_bolt / 2, -sb, s_pl0))
    D(K, "bolt_b", (-p.sec_bolt / 2, -sb, s_pl0))
    D(K, "bx0", (0, -sb + p.sec_bhex / 2, s_pl1))
    D(K, "bx1", (0, -sb - p.sec_bhex / 2, s_pl1))
    D(K, "bR1", (k30[0] + p.sec_bolt / 2, k30[1], s_pl0))

    # ================================================================ casing: output face at z = 0
    h = p.cas_h
    b0_r = p.cas_b0 / 2
    od_r = b0_r + p.cas_od_dr
    b1_r = b0_r - p.cas_b1_dr
    lip_r = b1_r - p.cas_lip_dr
    zr0 = p.cas_b1_h + p.cas_lip_h
    zr1 = zr0 + p.cas_ring_w
    zr = p.z_ring
    rp_r = m * zr / 2
    neck_r = rp_r + p.drw
    z_n1 = zr0 + p.cas_neck0
    z_n2 = z_n1 + p.cas_neck1
    body_r = p.cas_body / 2
    z_fe = h - p.cas_fl
    dr_f = body_r - neck_r
    flare_r = (dr_f * dr_f + (z_fe - z_n2) ** 2) / (2 * dr_f)
    lug_r_c = p.cas_lug_d / 2
    lug_rad = p.cas_lugt / 2 - lug_r_c
    n_lug = int(p.cas_n_lugs)
    lug_ang = [90 + k * 360 / n_lug for k in range(n_lug)]
    outline = Circle(body_r)
    for ang in lug_ang:
        outline += Pos(*polar(lug_r_c, ang, 0)[:2]) * Circle(lug_rad)
    outline = junction_fillet(outline, [polar(lug_r_c, ang, 0)[:2] for ang in lug_ang], lug_rad, body_r, p.lug_fillet)
    cas = extrude(outline, amount=h)
    env_r = neck_r + flare_r
    cas &= revolve_rz([(0, 0), (od_r, 0), (od_r, zr0), (neck_r, z_n1), (neck_r, z_n2), (env_r, z_n2), (env_r, h), (0, h)])
    cas -= Pos(0, 0, z_n2) * Torus(env_r, flare_r)
    # bore, lip, ring, upper bore
    cas -= revolve_rz([(0, 0), (b0_r, 0), (b1_r, p.cas_bch), (b1_r, p.cas_b1_h), (lip_r, p.cas_b1_h), (lip_r, zr0), (0, zr0)])
    rr_tip = rp_r - p.addendum_coef * m
    rr_root = rp_r + p.dedendum_coef * m
    cas -= Pos(0, 0, zr0) * prism(involute_outline(zr, m, a, rr_root, rr_tip, p.ring_phase), p.cas_ring_w)
    sh43_r = p.cas_sh43 / 2
    sh45_r = p.cas_sh45 / 2
    z_sb = zr1 + p.cas_shf
    z_sc = z_sb + p.cas_shb
    z_sh = z_sc + p.cas_shc
    upper = Plane.XZ * Face(Wire([
        Line((0, zr1), (sh43_r - p.cas_shf, zr1)),
        CenterArc((sh43_r - p.cas_shf, z_sb), p.cas_shf, 270, 90),
        Line((sh43_r, z_sb), (sh43_r, z_sc)),
        Line((sh43_r, z_sc), (sh45_r, z_sh)),
        Line((sh45_r, z_sh), (0, z_sh)),
        Line((0, z_sh), (0, zr1)),
    ]))
    cas -= revolve(upper, Axis.Z)
    # motor-end pocket with lobes
    n_lobe = int(p.cas_n_lobes)
    pk_r = p.cas_pk / 2
    lobe_r = p.cas_lobe / 2 - pk_r
    lobe_ang = [k * 360 / n_lobe for k in range(n_lobe)]
    lobe_c = [polar(pk_r, x, 0)[:2] for x in lobe_ang]
    pocket = Circle(pk_r)
    for c in lobe_c:
        pocket += Pos(*c) * Circle(lobe_r)
    pocket = junction_fillet(pocket, lobe_c, lobe_r, pk_r, p.lobe_fillet)
    cas -= Pos(0, 0, h - p.cas_pk_h) * extrude(pocket, amount=p.cas_pk_h)
    # lug holes and counterbores from below
    z_lcb = h - p.cas_lcbz
    for ang in lug_ang:
        cas -= at(lug_r_c, ang, 0) * Cylinder(p.cas_lugh / 2, h, align=UP)
        cas -= at(lug_r_c, ang, 0) * Cylinder(p.cas_lcb / 2, z_lcb, align=UP)
    # output-end bolt holes and radial nut slots
    n_h = int(p.cas_n_holes)
    hR = p.cas_hole_d / 2
    slot_l = od_r - hR + p.cas_nut
    for k in range(n_h):
        ang = 90 + k * 360 / n_h
        cas -= at(hR, ang, 0) * Cylinder(p.cas_hole / 2, p.cas_hole_h, align=UP)
        nut = RegularPolygon(p.cas_nut / 2, int(p.hex_sides), rotation=90) + Rectangle(slot_l, p.cas_nut, align=(Align.MIN, Align.CENTER))
        cas -= at(hR, ang, p.cas_nut_z) * Rot(0, 0, ang) * extrude(nut, amount=p.cas_nut_t)
    parts["casing"] = cas
    G = "casing"
    rph = p.ring_phase
    D(G, "axis_lo", (0, 0, p.cas_bch))
    D(G, "h0", (od_r, 0, 0))
    D(G, "h1", (body_r, 0, h))
    D(G, "bc0", (b0_r, 0, 0))
    D(G, "b0_b", (-b0_r, 0, 0))
    D(G, "bc1", (b1_r, 0, p.cas_bch))
    D(G, "bd1", (b1_r, 0, p.cas_b1_h))
    D(G, "lh0", (lip_r, 0, p.cas_b1_h))
    D(G, "lh1", (lip_r, 0, zr0))
    D(G, "rw0", flank_point(zr, m, a, rr_tip, 0, rph, 1, zr0))
    D(G, "rw1", flank_point(zr, m, a, rr_tip, 0, rph, 1, zr1))
    D(G, "rw_h", flank_point(zr, m, a, rr_tip, (zr - 1) / 2, rph, 1, zr0))
    D(G, "rp_a", polar(rp_r, rph - 90 / zr, (zr0 + zr1) / 2))
    D(G, "rp_b", polar(rp_r, rph + 180 - 90 / zr, (zr0 + zr1) / 2))
    D(G, "nk0", (od_r, 0, zr0))
    D(G, "nk1", (neck_r, 0, z_n1))
    D(G, "nk2", (neck_r, 0, z_n2))
    D(G, "nk2_b", (-neck_r, 0, z_n2))
    D(G, "fe0", (body_r, 0, z_fe))
    D(G, "body_b", (-body_r, 0, h))
    D(G, "pk_a", polar(pk_r, 180 / n_lobe, h))
    D(G, "pk_b", polar(pk_r, 180 + 180 / n_lobe, h))
    D(G, "pd0", polar(pk_r, 180 / n_lobe, h - p.cas_pk_h))
    D(G, "lb0", (pk_r + lobe_r, 0, h))
    D(G, "lb180", (-pk_r - lobe_r, 0, h))
    D(G, "lb20", polar(pk_r + lobe_r, 360 / n_lobe, h))
    D(G, "lb40", polar(pk_r + lobe_r, lobe_ang[2], h))
    D(G, "sh45_a", (sh45_r, 0, z_sh))
    D(G, "sh45_b", (-sh45_r, 0, z_sh))
    D(G, "sc0", (sh43_r, 0, z_sc))
    D(G, "sh43_b", (-sh43_r, 0, z_sc))
    D(G, "sb0", (sh43_r, 0, z_sb))
    D(G, "sf0", (sh43_r - p.cas_shf, 0, zr1))
    D(G, "lt90", (0, lug_r_c + lug_rad, h))
    D(G, "lt270", (0, -lug_r_c - lug_rad, h))
    l30 = polar(lug_r_c, lug_ang[-1], h)
    lm30 = polar(lug_r_c, lug_ang[-2], h)
    D(G, "lR90", (p.cas_lugh / 2, lug_r_c, h))
    D(G, "lugh_b", (-p.cas_lugh / 2, lug_r_c, h))
    D(G, "lR270", (p.cas_lugh / 2, -lug_r_c, h))
    D(G, "l30", (l30[0] + p.cas_lugh / 2, l30[1], h))
    D(G, "lm30", (lm30[0] + p.cas_lugh / 2, lm30[1], h))
    D(G, "lz0", (p.cas_lcb / 2, lug_r_c, z_lcb))
    D(G, "lcb_b", (-p.cas_lcb / 2, lug_r_c, z_lcb))
    hole_ang = [90 + k * 360 / n_h for k in range(n_h)]
    h30 = polar(hR, hole_ang[-1], 0)
    hm30 = polar(hR, hole_ang[-2], 0)
    D(G, "hd0", (p.cas_hole / 2, hR, 0))
    D(G, "hole_b", (-p.cas_hole / 2, hR, 0))
    D(G, "hd1", (p.cas_hole / 2, hR, p.cas_hole_h))
    D(G, "hR270", (p.cas_hole / 2, -hR, 0))
    D(G, "h30", (h30[0] + p.cas_hole / 2, h30[1], 0))
    D(G, "hm30", (hm30[0] + p.cas_hole / 2, hm30[1], 0))
    D(G, "nt0", (-p.cas_nut / 2, hR, p.cas_nut_z))
    D(G, "nt1", (p.cas_nut / 2, hR, p.cas_nut_z))
    D(G, "nt2", (p.cas_nut / 2, hR, p.cas_nut_z + p.cas_nut_t))
    z_ang = p.cas_b1_h + p.cas_lip_h / 2
    D(G, "ang_axis", (0, 0, z_ang))
    D(G, "ang_ref", (lip_r, 0, z_ang))

    # ================================================================ bearing retainer: casing side at z = 0
    n_r = int(p.ret_n_holes)
    ret = Cylinder(p.ret_od / 2, p.ret_t, align=UP) - Cylinder(p.ret_id / 2, p.ret_t, align=UP)
    for k in range(n_r):
        ret -= at(p.ret_hole_d / 2, 90 + k * 360 / n_r, 0) * Cylinder(p.ret_hole / 2, p.ret_t, align=UP)
    parts["retainer"] = ret
    R = "retainer"
    rh = p.ret_hole_d / 2
    ret_ang = [90 + k * 360 / n_r for k in range(n_r)]
    r30 = polar(rh, ret_ang[-1], 0)
    rm30 = polar(rh, ret_ang[-2], 0)
    D(R, "od_a", (p.ret_od / 2, 0, 0))
    D(R, "od_b", (-p.ret_od / 2, 0, 0))
    D(R, "od_t", (p.ret_od / 2, 0, p.ret_t))
    D(R, "id_a", (p.ret_id / 2, 0, 0))
    D(R, "id_b", (-p.ret_id / 2, 0, 0))
    D(R, "hR0", (p.ret_hole / 2, rh, 0))
    D(R, "hole_b", (-p.ret_hole / 2, rh, 0))
    D(R, "hR1", (p.ret_hole / 2, -rh, 0))
    D(R, "h30", (r30[0] + p.ret_hole / 2, r30[1], 0))
    D(R, "hm30", (rm30[0] + p.ret_hole / 2, rm30[1], 0))
    D(R, "s_od", (0, p.ret_od / 2, p.ret_t))

    # ================================================================ assembly, as built: sun at 0, carrier pins at 90 + k * 360 / n
    # Mesh phases (fractions of a tooth pitch, 0 = tooth centre): each planet's tooth sits in the ring's tooth space where
    # they touch, and the sun's tooth sits in the planet's tooth space; planet k's turn psi and the sun's turn sigma follow.
    # Each part is built where its released file holds it, with its datums; an instance of it is
    # placed where the assembly puts the part, through the inverse of that frame.
    files = {
        "planet_gear": Location((p.planet_file_x, p.planet_file_y, 0), (0, 0, 1), p.planet_file_turn),
        "sun_gear": Location((p.sun_file_x, p.sun_file_y, 0)),
        "primary_carrier": Location((p.car_file_x, p.car_file_y, p.car_file_z)),
        "secondary_carrier": Location((p.sec_file_x, p.sec_file_y, p.sec_file_z)),
        "casing": Location((p.cas_file_x, p.cas_file_y, 0)),
        "retainer": Location((p.ret_file_x, 0, p.ret_file_z), (1, 0, 0), -90),
    }
    for name, frame in files.items():
        parts[name] = parts[name].moved(frame)
        for key in [k for k in datums if k.startswith(f"{name}.")]:
            datums[key] = tuple((frame * Location(datums[key])).position)

    def place(name, where):
        return (name, where * files[name].inverse())

    assembly["casing_1"] = place("casing", Location((0, 0, 0)))
    assembly["retainer_1"] = place("retainer", Location((0, 0, -p.ret_t)))
    assembly["carrier_1"] = place("primary_carrier", Location((0, 0, 0)))
    assembly["sec_1"] = place("secondary_carrier", Location((0, 0, p.sec_z)))
    sigma = 0
    for k, ang in enumerate(pin_ang):
        g_r = frac((ang - rph) * zr / 360)
        psi = ang - p.planet_phase - g_r * 360 / zp
        if k == 0:
            g_p = frac((ang + 180 - psi - p.planet_phase) * zp / 360)
            f_s = frac(-g_p - 0.5)
            sigma = ang - p.sun_phase - f_s * 360 / zs
        x, y, _ = polar(cd, ang, 0)
        assembly[f"planet_{k + 1}"] = place("planet_gear", Location((x, y, p.planet_z), (0, 0, psi)))
    assembly["sun_1"] = place("sun_gear", Location((0, 0, p.sun_z), (0, 0, sigma)))

    joints = {
        "sun": {"type": "revolute", "parent": "casing_1", "child": "sun_1", "axis": ["sun_1.axis_lo", "sun_1.axis_hi"], "drive": "actuated"},
        "carrier": {"type": "revolute", "parent": "casing_1", "child": "carrier_1", "axis": ["carrier_1.axis_lo", "carrier_1.axis_hi"], "drive": "passive"},
        "sec": {"type": "fixed", "parent": "carrier_1", "child": "sec_1"},
    }
    gears = {"sun_carrier": {"driver": "sun", "driven": "carrier", "ratio": "carrier_ratio"}}
    for k in range(n_pl):
        joints[f"planet_{k + 1}"] = {"type": "revolute", "parent": "carrier_1", "child": f"planet_{k + 1}",
                                     "axis": [f"planet_{k + 1}.axis_seat", f"planet_{k + 1}.axis"], "drive": "passive"}
        gears[f"carrier_planet_{k + 1}"] = {"driver": "carrier", "driven": f"planet_{k + 1}", "ratio": "planet_ratio"}
    return {"parts": parts, "datums": datums, "assembly": assembly, "joints": joints, "gears": gears}
