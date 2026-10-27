"""Parametric model of the Poór 2022 mini benchtop centrifuge (static, lid off).

Every part is built Y-up. The body's frame is the released body's: top face at y = 0,
axis on Y. The plate's top face is its y = 0; the rotor's skirt bottom is its y = 0.
Reads every dimension from p (params.yaml); holds no dimension literals.
"""

import math

from build123d import *  # noqa: F403

C = (Align.CENTER, Align.CENTER, Align.MIN)


# ---------------------------------------------------------------- helpers
def cyl_y(r, y0, y1, x=0, z=0):
    """Solid cylinder on an axis parallel to Y, from y0 up to y1."""
    return Pos(x, y0, z) * Rot(-90, 0, 0) * Cylinder(r, y1 - y0, align=C)


def plane_y(y):
    """Plane at height y, normal +Y; local (u, v) lands on (x, z) = (u, -v)."""
    return Plane(origin=(0, y, 0), x_dir=(1, 0, 0), z_dir=(0, 1, 0))


def prism_y(pts_xz, y0, y1):
    """Prism of a polygon given in (x, z), from y0 up to y1."""
    return extrude(plane_y(y0) * Polygon(*[(x, -z) for x, z in pts_xz], align=None), amount=y1 - y0, dir=(0, 1, 0))


def prism_x(pts_yz, x0, x1):
    """Prism of a polygon given in (y, z), from x0 to x1 along X."""
    pl = Plane(origin=(x0, 0, 0), x_dir=(0, 1, 0), z_dir=(1, 0, 0))
    return extrude(pl * Polygon(*pts_yz, align=None), amount=x1 - x0, dir=(1, 0, 0))


def prism_z(pts_xy, z0, z1):
    """Prism of a polygon given in (x, y), from z0 to z1 along Z."""
    return extrude(Plane.XY.offset(z0) * Polygon(*pts_xy, align=None), amount=z1 - z0, dir=(0, 0, 1))


def revolve_y(pts_ry):
    """Solid of revolution about Y of a polygon given in (r, y)."""
    return revolve(Plane.XY * Polygon(*pts_ry, align=None), axis=Axis.Y)


def polar(r, deg):
    """(x, z) of radius r at angle deg, measured from +X toward +Z."""
    return (r * math.cos(math.radians(deg)), r * math.sin(math.radians(deg)))


def unit(ax, az):
    n = math.hypot(ax, az)
    return (ax / n, az / n)


def at(xz, y):
    return (xz[0], y, xz[1])


# ---------------------------------------------------------------- body
def build_body(p, d):
    R = p.body_d / 2
    H = p.body_h
    Ri = p.body_bore_d / 2
    T = p.deck_t
    wall = R - Ri

    body = cyl_y(R, -H, 0) - cyl_y(Ri, -H - 1, -T) - cyl_y(p.hub_hole_d / 2, -H, 1)

    # lid groove: straight inner and outer walls, rounded floor
    gi, go = p.groove_di / 2, p.groove_do / 2
    f_in = p.groove_depth - p.groove_in_wall
    f_out = p.groove_depth - p.groove_out_wall
    with BuildSketch(Plane.XY) as groove_sk:
        with BuildLine():
            Line((gi, 1), (gi, -p.groove_in_wall))
            CenterArc((gi + f_in, -p.groove_in_wall), f_in, 180, 90)
            Line((gi + f_in, -p.groove_depth), (go - f_out, -p.groove_depth))
            CenterArc((go - f_out, -p.groove_out_wall), f_out, 270, 90)
            Line((go, -p.groove_out_wall), (go, 1))
            Line((go, 1), (gi, 1))
        make_face()
    body -= revolve(groove_sk.sketch, axis=Axis.Y)

    # spin-direction arrows: recessed band plus head, two point-symmetric copies
    a_in, a_out = p.arrow_d_in / 2, p.arrow_d_out / 2
    a_mid = (a_in + a_out) / 2
    band = cyl_y(a_out, -p.arrow_depth, 1) - cyl_y(a_in, -p.arrow_depth - 1, 2)
    band &= prism_y([(-a_out - 1, 0), (-p.arrow_base_x, 0), (-p.arrow_base_x, a_out + 1), (-a_out - 1, a_out + 1)],
                    -p.arrow_depth, 1)
    head = prism_y([(-p.arrow_base_x, p.arrow_z0), (-p.arrow_base_x, p.arrow_z1), (p.arrow_tip_x, a_mid)],
                   -p.arrow_depth, 1)
    arrow = band + head
    body -= arrow
    body -= Rot(0, 180, 0) * arrow

    # fan screw holes through the deck, on the axes
    fr = p.fan_hole_pcd / 2
    for x, z in [(fr, 0), (-fr, 0), (0, fr), (0, -fr)]:
        body -= cyl_y(p.fan_hole_d / 2, -T - 1, 1, x, z)

    # screw bosses: a cylinder joined to the wall by two webs, each tangent to the boss and
    # aimed at the opposite boss's axis; topped by a cone at boss_cone_angle and a flat
    n = int(p.screw_n)
    Rb, rb = p.boss_pcd / 2, p.boss_d / 2
    beta = math.degrees(math.asin(rb / (2 * Rb)))
    cut_r1 = Ri - (p.boss_flat - p.boss_cone_drop) * math.tan(math.radians(p.boss_cone_angle))
    top_cut = revolve_y([(0, -p.boss_flat), (cut_r1, -p.boss_flat), (Ri, -p.boss_cone_drop), (Ri, -T), (0, -T)])
    rho = (R + Ri) / 2
    yb = -(H + p.boss_flat) / 2
    for k in range(n):
        th = p.boss_angle + k * 360 / n
        bx, bz = polar(Rb, th)
        ux, uz = polar(1, th)
        ear = cyl_y(rb, -H, -T, bx, bz)
        web = []
        for sgn in (1, -1):
            wx, wz = polar(1, th + sgn * beta)
            reach = 2 * Rb * math.cos(math.radians(beta))
            tx, tz = -bx + reach * wx, -bz + reach * wz           # tangent point, seen from the opposite boss
            b = tx * wx + tz * wz
            t = -b + math.sqrt(b * b - (tx * tx + tz * tz) + rho * rho)
            web.append(((tx, tz), (tx + t * wx, tz + t * wz)))
        (t1, w1), (t2, w2) = web
        ear += prism_y([t1, w1, w2, t2], -H, -T)
        ear -= top_cut
        ear -= cyl_y(p.boss_hole_d / 2, -H - 1, -H + p.boss_hole_depth, bx, bz)
        body += ear
        if k == 0:
            d["body.boss1"] = (bx, yb, bz)
            d["body.boss_wall"] = (bx - rb * ux, yb, bz - rb * uz)
            hr = p.boss_hole_d / 2
            d["body.boss_hole_wall"] = (bx + hr * ux, -H + p.boss_hole_depth / 2, bz + hr * uz)
            d["body.boss_hole_top"] = (bx, -H + p.boss_hole_depth, bz)
            d["body.cone_wall"] = (Ri * ux, -p.boss_cone_drop, Ri * uz)
            d["body.cone_up"] = (Ri * ux, -(p.boss_cone_drop + T) / 2, Ri * uz)
            d["body.cone_b"] = ((Ri - wall) * ux,
                                -p.boss_cone_drop - wall / math.tan(math.radians(p.boss_cone_angle)), (Ri - wall) * uz)
            d["body.boss_flat"] = ((Rb - rb) * ux, -p.boss_flat, (Rb - rb) * uz)
        if k == n // 2:
            d["body.boss3"] = (bx, yb, bz)

    # main (rocker) switch cut-out through the wall: one side face through P1 (outer) and P2 (inner)
    p1 = (-p.rocker_p1x, p.rocker_p1z)
    p2 = (-p.rocker_p2x, p.rocker_p2z)
    dx, dz = unit(p2[0] - p1[0], p2[1] - p1[1])
    nx, nz = -dz, dx
    W = p.rocker_w
    a = (p1[0] - wall * dx, p1[1] - wall * dz)
    b = (p1[0] + 2 * wall * dx, p1[1] + 2 * wall * dz)
    body -= prism_y([a, b, (b[0] + W * nx, b[1] + W * nz), (a[0] + W * nx, a[1] + W * nz)],
                    -p.rocker_top - p.rocker_h, -p.rocker_top)
    yr = -p.rocker_top - p.rocker_h / 2
    d["body.rocker_p1"] = at(p1, yr)
    d["body.rocker_p2"] = at(p2, yr)
    d["body.rocker_p2w"] = at((p2[0] + W * nx, p2[1] + W * nz), yr)
    cx, cz = (p1[0] + p2[0]) / 2 + W / 2 * nx, (p1[1] + p2[1]) / 2 + W / 2 * nz
    d["body.rocker_top"] = (cx, -p.rocker_top, cz)
    d["body.rocker_bottom"] = (cx, -p.rocker_top - p.rocker_h, cz)
    d["body.axis_mid"] = (0, yr, 0)

    # DC socket hole: axis through Q2 (inner) and Q1 (outer)
    q1 = (-p.dc_q1x, -p.dc_y, -p.dc_q1z)
    q2 = (-p.dc_q2x, -p.dc_y, -p.dc_q2z)
    ax, az = unit(q1[0] - q2[0], q1[2] - q2[2])
    start = (q2[0] - wall * ax, -p.dc_y, q2[2] - wall * az)
    span = math.hypot(q1[0] - q2[0], q1[2] - q2[2]) + 2 * wall
    body -= Location(Plane(origin=start, z_dir=(ax, 0, az))) * Cylinder(p.dc_d / 2, span, align=C)
    d["body.dc_q1"] = q1
    d["body.dc_q2"] = q2
    d["body.dc_wall"] = (q1[0], -p.dc_y + p.dc_d / 2, q1[2])

    # lid-switch slot: rectangle C1-C2 (short side) by C1-C3 (long side), deck underside up into the groove
    c1 = (p.slot_c1x, p.slot_c1z)
    c2 = (p.slot_c2x, p.slot_c2z)
    sx, sz = unit(c2[0] - c1[0], c2[1] - c1[1])
    ex, ez = sz, -sx
    L = p.slot_len
    c3 = (c1[0] + L * ex, c1[1] + L * ez)
    c4 = (c2[0] + L * ex, c2[1] + L * ez)
    body -= prism_y([c1, c2, c4, c3], -T - 1, 1)
    d["body.slot_c1"] = at(c1, -T)
    d["body.slot_c2"] = at(c2, -T)
    d["body.slot_c3"] = at(c3, -T)

    # datums
    d["body.top"] = (-(R + go) / 2, 0, 0)
    d["body.bottom"] = (-(R + Ri) / 2, -H, 0)
    d["body.deck_under"] = (-(Ri + p.hub_hole_d / 2) / 2, -T, 0)
    d["body.bore_wall"] = (-Ri, -(H + T) / 2, 0)
    d["body.hole_wall"] = (-p.hub_hole_d / 2, -T / 2, 0)
    d["body.axis_top"] = (0, -T / 2, 0)
    d["body.groove_in"] = (-gi, -p.groove_in_wall / 2, 0)
    d["body.groove_out"] = (-go, -p.groove_out_wall / 2, 0)
    d["body.groove_in_edge"] = (-gi, -p.groove_in_wall, 0)
    d["body.groove_out_edge"] = (-go, -p.groove_out_wall, 0)
    d["body.groove_floor"] = (-(gi + f_in + go - f_out) / 2, -p.groove_depth, 0)
    d["body.arrow_floor"] = (-a_mid / 2, -p.arrow_depth, math.sqrt(a_mid ** 2 - (a_mid / 2) ** 2))
    d["body.arrow_in"] = (-a_in / 2, -p.arrow_depth / 2, math.sqrt(a_in ** 2 - (a_in / 2) ** 2))
    d["body.arrow_out"] = (-a_out / 2, -p.arrow_depth / 2, math.sqrt(a_out ** 2 - (a_out / 2) ** 2))
    d["body.arrow_tip"] = (p.arrow_tip_x, -p.arrow_depth / 2, a_mid)
    d["body.arrow_base"] = (-p.arrow_base_x, -p.arrow_depth / 2,
                            (p.arrow_z0 + math.sqrt(a_in ** 2 - p.arrow_base_x ** 2)) / 2)
    d["body.arrow_z0"] = (-p.arrow_base_x, -p.arrow_depth / 2, p.arrow_z0)
    d["body.arrow_z1"] = (-p.arrow_base_x, -p.arrow_depth / 2, p.arrow_z1)
    d["body.fan_hole_p"] = (fr, -T / 2, 0)
    d["body.fan_hole_n"] = (-fr, -T / 2, 0)
    d["body.fan_hole_wall"] = (-fr + p.fan_hole_d / 2, -T / 2, 0)
    d["body.axis_low"] = (0, yb, 0)
    d["body.wall0"] = (Ri, yb, 0)
    return body


# ---------------------------------------------------------------- bottom plate
def build_plate(p, d):
    Rp = p.plate_d / 2
    t = p.plate_t
    n = int(p.screw_n)
    plate = cyl_y(Rp, -t, 0)
    Rf = p.foot_pcd / 2
    Rb = p.boss_pcd / 2
    for k in range(n):
        plate += cyl_y(p.foot_d / 2, -t - p.foot_h, -t, *polar(Rf, p.foot_angle + k * 360 / n))
        plate -= cyl_y(p.plate_hole_d / 2, -t - 1, 1, *polar(Rb, p.boss_angle + k * 360 / n))
    f = polar(Rf, p.foot_angle)
    g = polar(Rf, p.foot_angle + 180)
    h = polar(Rb, p.boss_angle)
    hu = polar(p.plate_hole_d / 2, p.boss_angle)
    yf = -t - p.foot_h / 2
    d["plate.rim"] = (-Rp, -t / 2, 0)
    d["plate.top"] = (-(Rp + Rf) / 2, 0, 0)
    d["plate.bottom"] = (-(Rp + Rf) / 2, -t, 0)
    d["plate.foot_p"] = at(f, yf)
    d["plate.foot_n"] = at(g, yf)
    d["plate.foot_wall"] = (f[0] + p.foot_d / 2, yf, f[1])
    d["plate.foot_bottom"] = at(f, -t - p.foot_h)
    d["plate.foot_end"] = at(f, -t)
    d["plate.ref0"] = (Rf, -t, 0)
    d["plate.centre_bottom"] = (0, -t, 0)
    d["plate.hole_wall"] = (h[0] + hu[0], -t / 2, h[1] + hu[1])
    d["plate.hole"] = at(h, -t / 2)
    return plate


# ---------------------------------------------------------------- rotor (PCR strip, 32.5 mm hub)
def build_rotor(p, d):
    ri = p.hub_d / 2
    w = p.rotor_wall
    ro = ri + w
    s = p.rotor_slope
    ts = math.tan(math.radians(s))
    st, sb = p.skirt_top_y, p.slab_bot_y
    st_top = sb + w                        # slab top face
    ct_r = p.cone_top_d / 2

    # hub: skirt plus outer cone up to the slab
    hub = revolve_y([(0, 0), (ro, 0), (ro, st), (ct_r, sb), (0, sb)])

    # cavity: skirt bore, hub ledge, flare at the slope, cone parallel to the outside (wall w), tip at the slope
    k = (ro - ct_r) / (sb - st)            # outer cone: r = ro - k (y - st)
    g = math.sqrt(1 + k * k)
    ledge_r = p.ledge_d / 2
    cav_y = (ro - w * g + k * st - ledge_r + p.ledge_y / ts) / (1 / ts + k)
    cav_r = ledge_r + (cav_y - p.ledge_y) / ts
    kink_r = ro - k * (p.kink_y - st) - w * g
    apex_y = p.kink_y + kink_r * ts
    cavity = revolve_y([(0, -1), (ri, -1), (ri, p.ledge_y), (ledge_r, p.ledge_y), (cav_r, cav_y),
                        (kink_r, p.kink_y), (0, apex_y)])

    # slab between the two holders, its ends mitred at half the bend
    zt = p.bend_span / 2
    zb = zt + w * math.tan(math.radians(s / 2))
    sw = p.slab_w / 2
    slab = prism_x([(sb, -zb), (sb, zb), (st_top, zt), (st_top, -zt)], -sw, sw)

    # hipped roof over the hub, rising at the slope to the ridge
    hr = p.top_y - st_top
    rl, rw = p.ridge_l / 2, p.ridge_w / 2
    roof = loft([plane_y(st_top) * Rectangle(2 * (rl + hr / ts), 2 * (rw + hr / ts)),
                 plane_y(p.top_y) * Rectangle(2 * rl, 2 * rw)])

    # strip holder (+z side): plate rising at the slope from the mitre, cut level at top_y
    L = p.holder_l / 2
    c = p.holder_chamfer
    z_top_t = zt + (p.top_y - st_top) / ts
    z_top_b = zb + (p.top_y - sb) / ts
    holder = prism_x([(st_top, zt), (sb, zb), (p.top_y, z_top_b), (p.top_y, z_top_t)], -L, L)
    # top corners: chamfer c by c in the front view
    top_wedge = prism_z([(L - c, p.top_y), (L + 1, p.top_y - c - 1), (L + 1, p.top_y + 1), (L - c, p.top_y + 1)],
                        -2 * L, 2 * L)
    # bottom corners: equal chamfer c between the end face and the mitre plane
    ey, ez = unit(sb - st_top, zb - zt)            # along the mitre line, in (y, z)
    oy, oz = (sb + st_top) / 2 - L * ey, (zb + zt) / 2 - L * ez
    mit_pl = Plane(origin=(0, oy, oz), x_dir=(1, 0, 0), z_dir=(0, ey, ez))   # local v: into the holder
    mit_wedge = extrude(mit_pl * Polygon((L - c, 0), (L + 1, c + 1), (L + 1, -1), align=None), amount=2 * L,
                        dir=(0, ey, ez))
    for wedge in (top_wedge, mit_wedge):
        holder -= wedge
        holder -= mirror(wedge, about=Plane.YZ)
    # tube holes, perpendicular to the holder plate
    ny, nz = math.cos(math.radians(s)), -math.sin(math.radians(s))     # top-surface normal (up, inward)
    pitch = p.hole_pitch
    n_side = round((p.hole_x_out - p.hole_x_in) / pitch) + 1
    y_c = p.top_y - p.hole_drop
    z_c = zt + (y_c - st_top) / ts
    for i in range(n_side):
        for sx in (1, -1):
            org = (sx * (p.hole_x_in + i * pitch), y_c + w / 2 * ny, z_c + w / 2 * nz)
            holder -= Location(Plane(origin=org, z_dir=(0, -ny, -nz))) * Cylinder(p.hole_d / 2, 2 * w, align=C)
    holders = holder + mirror(holder, about=Plane.XY)

    rotor = hub + slab + roof + holders
    rotor -= cavity

    # notches between the tabs that key onto the fan blades
    nt = int(p.n_tabs)
    pitch_t = 360 / p.n_tabs
    phi0 = -math.degrees(math.asin(p.tab_edge_z / ro))      # upper edge of tab 0
    ta = p.tab_angle
    for j in range(nt):
        a1 = phi0 + j * pitch_t
        a2 = phi0 - ta + (j + 1) * pitch_t
        rotor -= prism_y([(0, 0), polar(2 * ro, a1), polar(2 * ro, (a1 + a2) / 2), polar(2 * ro, a2)],
                         -1, p.notch_h)

    # datums
    r_mid = (ri + ro) / 2
    yt = p.notch_h / 2
    d["rotor.tab_bottom"] = at(polar(r_mid, phi0 - ta / 2), 0)
    d["rotor.notch_roof"] = at(polar(r_mid, phi0 - (pitch_t + ta) / 2), p.notch_h)
    d["rotor.ledge"] = ((ledge_r + ri) / 2, p.ledge_y, 0)
    d["rotor.skirt_top"] = (ro, st, 0)
    d["rotor.ledge_p"] = (ledge_r, p.ledge_y, 0)
    d["rotor.ledge_n"] = (-ledge_r, p.ledge_y, 0)
    d["rotor.cone_top_p"] = (ct_r, sb, 0)
    d["rotor.cone_top_n"] = (-ct_r, sb, 0)
    d["rotor.kink"] = (kink_r, p.kink_y, 0)
    d["rotor.slab_bot"] = (0, sb, zt)
    d["rotor.bend_p"] = (0, st_top, zt)
    d["rotor.bend_n"] = (0, st_top, -zt)
    d["rotor.slab_top_mid"] = (0, st_top, (zt + rw + hr / ts) / 2)
    d["rotor.holder_top_edge"] = (0, p.top_y, z_top_t)
    d["rotor.ridge"] = (0, p.top_y, 0)
    d["rotor.ridge_xp"] = (rl, p.top_y, 0)
    d["rotor.ridge_xn"] = (-rl, p.top_y, 0)
    d["rotor.ridge_zp"] = (0, p.top_y, rw)
    d["rotor.ridge_zn"] = (0, p.top_y, -rw)
    d["rotor.slab_side_p"] = (sw, sb + w / 2, zt)
    d["rotor.slab_side_n"] = (-sw, sb + w / 2, zt)
    y_e = p.top_y - c
    z_e = zt + (y_e - st_top) / ts
    d["rotor.end_p"] = (L, y_e, z_e)
    d["rotor.end_n"] = (-L, y_e, z_e)
    d["rotor.cut_corner"] = (L - c, p.top_y, z_top_t)
    y_m, z_m = y_c - w / 2 * ny, z_c - w / 2 * nz
    d["rotor.hole_in_p"] = (p.hole_x_in, y_m, z_m)
    d["rotor.hole_in_n"] = (-p.hole_x_in, y_m, z_m)
    d["rotor.hole_2_p"] = (p.hole_x_in + pitch, y_m, z_m)
    d["rotor.hole_out_p"] = (p.hole_x_out, y_m, z_m)
    d["rotor.hole_out_n"] = (-p.hole_x_out, y_m, z_m)
    d["rotor.hole_wall"] = (p.hole_x_in + p.hole_d / 2, y_m, z_m)
    d["rotor.hole_top"] = (p.hole_x_in, y_c, z_c)
    d["rotor.axis_low"] = (0, yt, 0)
    d["rotor.tab_e1"] = at(polar(r_mid, phi0), yt)
    d["rotor.tab_e2"] = at(polar(r_mid, phi0 - ta), yt)
    d["rotor.tab1_e1"] = at(polar(r_mid, phi0 + pitch_t), yt)
    d["rotor.tab_corner"] = at(polar(ro, phi0), 0)
    d["rotor.hub_bore"] = at(polar(ri, phi0 - ta / 2), yt)
    return rotor


# ---------------------------------------------------------------- purchased parts
def build_fan(p, d):
    frame = Box(p.fan_w, p.fan_t, p.fan_w, align=(Align.CENTER, Align.MAX, Align.CENTER))
    frame -= cyl_y(p.fan_bore_d / 2, -p.fan_t - 1, 1)
    hub = cyl_y(p.hub_d / 2, -p.fan_t, 0)
    return frame, hub


def build_screw(p, d):
    d["screw.wall"] = (p.screw_d / 2, p.screw_l / 2, 0)
    return cyl_y(p.screw_d / 2, 0, p.screw_l)


def build(p):
    d = {}
    body = build_body(p, d)
    plate = build_plate(p, d)
    rotor = build_rotor(p, d)
    fan_frame, fan_hub = build_fan(p, d)
    screw = build_screw(p, d)

    assembly = {
        "body_1": ("body", Location((0, 0, 0))),
        "plate_1": ("plate", Location((0, -p.body_h, 0))),
        "fan_frame_1": ("fan_frame", Location((0, p.fan_top_y, 0), (0, p.fan_rot, 0))),
        "fan_hub_1": ("fan_hub", Location((0, p.fan_top_y, 0))),
        "rotor_1": ("rotor", Location((0, p.rotor_seat_y, 0))),
    }
    n = int(p.screw_n)
    for k in range(n):
        x, z = polar(p.boss_pcd / 2, p.boss_angle + k * 360 / n)
        assembly[f"screw_{k + 1}"] = ("screw", Location((x, -p.body_h - p.plate_t, z)))
    return {
        "parts": {"body": body, "plate": plate, "rotor": rotor, "fan_frame": fan_frame, "fan_hub": fan_hub,
                  "screw": screw},
        "datums": d,
        "assembly": assembly,
    }
