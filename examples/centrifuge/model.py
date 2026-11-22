"""Parametric model. Reads every dimension from p (params.yaml); holds no dimension literals.

The frame is the released bodies': +y up along the axis, the deck's top face at y = 0.
An angle about the axis is in the x-z plane, from +x towards +z.
"""

import math

from build123d import *  # noqa: F403


# ---------------------------------------------------------------- helpers


def polar(radius, angle, y=0):
    """The point at a distance from the y axis, at an angle from +x towards +z."""
    a = math.radians(angle)
    return (radius * math.cos(a), y, radius * math.sin(a))


def ycyl(radius, y_low, y_high):
    """A cylinder about the y axis between two heights."""
    return Pos(0, (y_low + y_high) / 2, 0) * Rot(90, 0, 0) * Cylinder(radius, y_high - y_low)


def ring(count, first_angle):
    """The angles of a pattern turned in equal steps about the axis."""
    return [first_angle + i * 360 / count for i in range(int(count))]


def level(y):
    """The x-z plane at a height: a sketch on it has x along +x and y along +z, and extrudes down."""
    return Plane.XZ.offset(-y)


def prism(points, y_low, y_high):
    """A polygon of (x, z) corners, extruded between two heights."""
    turn = sum(a[0] * b[1] - b[0] * a[1] for a, b in zip(points, points[1:] + points[:1]))
    if turn < 0:
        points = points[::-1]
    return extrude(level(y_high) * Polygon(*points, align=None), amount=y_high - y_low)


def turned(*edges):
    """A profile of (radius, y) edges, turned a full turn about the y axis."""
    profile = edges[0]
    for edge in edges[1:]:
        profile += edge
    return revolve(make_face(profile), Axis.Y)


def arc(centre, radius, toward_a, toward_b):
    """The arc about a centre from the direction toward_a to toward_b, the short way round."""
    def at(direction):
        n = math.hypot(*direction)
        return (centre[0] + radius * direction[0] / n, centre[1] + radius * direction[1] / n)

    na, nb = math.hypot(*toward_a), math.hypot(*toward_b)
    mid = (toward_a[0] / na + toward_b[0] / nb, toward_a[1] / na + toward_b[1] / nb)
    return at(toward_a), ThreePointArc(at(toward_a), at(mid), at(toward_b)), at(toward_b)


def along(direction, distance, across=0, y=0):
    """The point a distance from the axis along a direction, and an offset across it (towards direction + 90)."""
    ex, _, ez = polar(1, direction)
    ax, _, az = polar(1, direction + 90)
    return (ex * distance + ax * across, y, ez * distance + az * across)


def facing(direction, point):
    """A frame at a point with its x axis level, pointing out along a direction about the y axis."""
    return Location(point, (0, -direction, 0))


# ---------------------------------------------------------------- the printed parts


def build_body(p, datums, threads):
    rim_y = -p.b_h
    deck_y = -p.b_deck_t
    body = ycyl(p.b_r_out, rim_y, 0) - ycyl(p.b_r_in, rim_y, deck_y) - ycyl(p.b_centre_r, deck_y, 0)

    for i, a in enumerate(ring(p.b_fan_hole_n, p.b_fan_hole_a), 1):
        x, _, z = polar(p.b_fan_hole_R, a)
        body -= Pos(x, 0, z) * ycyl(p.b_fan_hole_r, deck_y, 0)
        datums[f"body.fan_hole_{i}"] = (x, deck_y / 2, z)

    # the lid groove: its profile, carried above the deck so the cut is clean
    over = p.g_in_round
    in_c = (p.g_in_c, -p.g_in_drop)
    out_c = (p.g_out_c, -p.g_out_drop)
    in_a, in_arc, in_b = arc(in_c, p.g_in_round, (-1, 0), (0, -1))
    out_a, out_arc, out_b = arc(out_c, p.g_out_round, (0, -1), (1, 0))
    body -= turned(
        Polyline((p.g_out_r, over), (p.g_in_r, over), in_a),
        in_arc,
        Line(in_b, out_a),
        out_arc,
        Polyline(out_b, (p.g_out_r, over)),
    )

    # the spin arrows: arrow 1 from the +x axis round towards -z, arrow 2 the same turned half a turn
    reach = 2 * p.a_r_out
    band = ycyl(p.a_r_out, -p.a_depth, p.a_depth) - ycyl(p.a_r_in, -p.a_depth, p.a_depth)
    shaft = band & (Pos(p.a_base_x + reach / 2, 0, -reach / 2) * Box(reach, reach, reach))
    head = prism(
        [(p.a_base_x, -p.a_head_z_out), (p.a_base_x, -p.a_head_z_in), (-p.a_base_x, -p.a_tip_z)],
        -p.a_depth,
        p.a_depth,
    )
    arrow = shaft + head
    body -= arrow
    body -= Rot(0, 180, 0) * arrow

    # the screw posts: a round post joined to the wall by two flat sides, its top cut by a cone
    slope = math.tan(math.radians(p.post_cone))
    flat_r = (p.post_flat_y - p.post_apex_y) * slope
    below = turned(
        Polyline(
            (0, rim_y),
            (p.b_r_out, rim_y),
            (p.b_r_out, p.post_apex_y + p.b_r_out / slope),
            (flat_r, p.post_flat_y),
            (0, p.post_flat_y),
            (0, rim_y),
        )
    )
    wall_mid = (p.b_r_in + p.b_r_out) / 2
    spread = 2 * math.degrees(math.asin(p.post_r / (2 * p.post_R)))
    for i, a in enumerate(ring(p.post_n, p.post_a), 1):
        cx, _, cz = polar(p.post_R, a)
        sides = []
        for sign in (1, -1):
            ax, _, az = polar(p.post_R, a + sign * spread)
            tx, tz = cz - az, ax - cx  # square to the post's radius at this point
            if tx * ax + tz * az < 0:
                tx, tz = -tx, -tz
            n = math.hypot(tx, tz)
            tx, tz = tx / n, tz / n
            b = ax * tx + az * tz
            t = -b + math.sqrt(b * b - (ax * ax + az * az - wall_mid * wall_mid))
            sides.append(((ax, az), (ax + t * tx, az + t * tz)))
        (a1, w1), (a2, w2) = sides
        post = Pos(cx, 0, cz) * ycyl(p.post_r, rim_y, deck_y) + prism([a1, w1, w2, a2], rim_y, deck_y)
        body += post & below
        body -= Pos(cx, 0, cz) * ycyl(p.post_hole_r, rim_y, p.post_hole_y)
        datums[f"body.post_hole_{i}"] = (cx, (rim_y + p.post_hole_y) / 2, cz)

    # the lid switch pocket, up through the deck into the groove
    pocket_at = along(p.pk_dir, p.pk_near + p.pk_len / 2, p.pk_side + p.pk_w / 2, deck_y / 2)
    body -= facing(p.pk_dir, pocket_at) * Box(p.pk_len, p.b_deck_t, p.pk_w)

    # the main switch cut-out and the DC socket hole, through the wall
    through = 2 * (p.b_r_out - p.b_r_in)
    cut_at = along(p.ms_dir, wall_mid, p.ms_side + p.ms_cut_w / 2, p.ms_top_y - p.ms_cut_h / 2)
    body -= facing(p.ms_dir, cut_at) * Box(through, p.ms_cut_h, p.ms_cut_w)
    hole_at = along(p.dc_dir, wall_mid, p.dc_off, p.dc_y)
    body -= facing(p.dc_dir, hole_at) * Rot(0, 90, 0) * Cylinder(p.dc_hole_r, through)

    for name, a in (("x_max", 0), ("z_max", 90), ("x_min", 180), ("z_min", 270)):
        datums[f"body.wall_{name}"] = polar(p.b_r_out, a, rim_y / 2)
    return body


def build_bottom_plate(p, datums, threads):
    top = p.bp_top_y
    under = top - p.bp_t
    plate = ycyl(p.bp_r, under, top)
    for i, a in enumerate(ring(p.bp_hole_n, p.bp_hole_a), 1):
        x, _, z = polar(p.bp_hole_R, a)
        plate -= Pos(x, 0, z) * ycyl(p.bp_hole_r, under, top)
        datums[f"bottom_plate.hole_{i}"] = (x, (under + top) / 2, z)
    for a in ring(p.bp_hole_n, p.bp_foot_a):
        x, _, z = polar(p.bp_foot_R, a)
        plate += Pos(x, 0, z) * ycyl(p.bp_foot_r, under - p.bp_foot_h, under)
    x, _, z = polar(p.bp_foot_R, p.bp_foot_a)
    datums["bottom_plate.foot_bottom"] = (x, under - p.bp_foot_h, z)
    return plate


def build_rotor(p, datums, threads):
    half = math.radians(p.r_bowl_half)
    kb, sb, cb = math.tan(half), math.sin(half), math.cos(half)
    r0 = p.r_bowl_r0
    m = (p.r_skirt_r - r0) / p.r_cone_drop  # the outer cone widens by m per unit down
    hyp = math.hypot(1, m)
    out0 = r0 + p.r_bowl_wall / cb  # the bowl's outside cone at y = 0
    cav0 = r0 - p.r_shell_wall * hyp  # the cavity cone at y = 0

    y_rim = p.r_bowl_slope * cb
    apex = (0, -r0 / kb)
    rim_in = (r0 + y_rim * kb, y_rim)
    rim_out = (out0 + y_rim * kb, y_rim)

    # where the outer cone and the bowl's outside would meet, and the chamfer across it
    y_meet = -(out0 - r0) / (kb + m)
    meet = (r0 - y_meet * m, y_meet)
    cham_high = (meet[0] + p.r_chamfer * sb, meet[1] + p.r_chamfer * cb)
    cham_low = (meet[0] + p.r_chamfer * m / hyp, meet[1] - p.r_chamfer / hyp)

    foot = (p.r_skirt_r, -p.r_cone_drop)
    seat_out = (p.r_skirt_r, p.r_seat_y)
    seat_in = (p.r_seat_r, p.r_seat_y)
    kl = math.tan(math.radians(p.r_lip_half))
    y_lip = (cav0 - p.r_seat_r + p.r_seat_y * kl) / (kl + m)
    lip_top = (p.r_seat_r + (y_lip - p.r_seat_y) * kl, y_lip)

    # the round between the cavity cone and the bowl's underside
    y_round = (cav0 - p.r_round * hyp - out0 - p.r_round / cb) / (kb + m)
    round_c = (out0 + y_round * kb + p.r_round / cb, y_round)
    round_a, round_arc, round_b = arc(round_c, p.r_round, (1, m), (-cb, sb))

    # the round under the bowl's point, tangent to the bowl's underside
    tip_c = (p.r_tip_c, (p.r_tip_c + p.r_tip_round * cb - out0) / kb + p.r_tip_round * sb)
    tip_a, tip_arc, tip_b = arc(tip_c, p.r_tip_round, (cb, -sb), (0, -1))

    rotor = turned(
        Polyline(apex, rim_in, rim_out, cham_high, cham_low, foot, seat_out, seat_in, lip_top, round_a),
        round_arc,
        Line(round_b, tip_a),
        tip_arc,
        Polyline(tip_b, (0, tip_b[1]), apex),
    )

    # the prongs: sectors of the skirt's ring, each between two planes through the axis
    band = ycyl(p.r_skirt_r, p.r_prong_y, p.r_seat_y) - ycyl(p.r_bore_r, p.r_prong_y, p.r_seat_y)
    width = math.degrees(math.asin(p.r_prong_w / p.r_skirt_r))
    reach = 2 * p.r_skirt_r
    for a in ring(p.r_prong_n, p.r_prong_a):
        x1, _, z1 = polar(reach, a - width)
        x2, _, z2 = polar(reach, a)
        rotor += band & prism([(0, 0), (x1, z1), (x2, z2)], p.r_prong_y, p.r_seat_y)

    # the tube holes: square to the bowl's wall, through it
    tilt = math.radians(p.r_hole_tilt)
    rw, yw = r0 + p.r_hole_slope * sb, p.r_hole_slope * cb
    for i, a in enumerate(ring(p.r_hole_n, p.r_hole_a), 1):
        hx, _, hz = polar(1, a)
        down = (math.sin(tilt) * hx, -math.cos(tilt), math.sin(tilt) * hz)
        at = (rw * hx, yw, rw * hz)
        rotor -= Plane(origin=at, z_dir=down) * Cylinder(p.r_hole_r, 2 * p.r_hole_r)
        datums[f"rotor.tube_{i}"] = tuple(c + d * p.r_bowl_wall / 2 for c, d in zip(at, down))

    datums["rotor.axis"] = (0, (p.r_seat_y - p.r_cone_drop) / 2, 0)
    datums["rotor.seat"] = ((p.r_seat_r + p.r_bore_r) / 2, p.r_seat_y, 0)
    datums["rotor.bore_wall"] = polar(p.r_bore_r, p.r_prong_a - width / 2, (p.r_prong_y + p.r_seat_y) / 2)
    return rotor


# ---------------------------------------------------------------- the bought parts, as envelopes


def build_fan(p, datums, threads):
    """Its own frame: the face that meets the deck at y = 0, the hub's axis on y, its corners on the x and z axes."""
    back_y = -p.fan_t
    corner = p.fan_size / math.sqrt(2)
    corners = [polar(corner, a) for a in ring(p.b_fan_hole_n, p.b_fan_hole_a)]
    outline = fillet(Polygon(*[(x, z) for x, _, z in corners], align=None).vertices(), p.fan_corner_r)
    outline -= Circle(p.fan_bore_d / 2)
    flange_y = -p.fan_flange_t / 2
    for i, a in enumerate(ring(p.fan_screw_n, p.b_fan_hole_a), 1):
        x, _, z = polar(p.fan_mount_R, a)
        outline -= Pos(x, z) * Circle(p.fan_mount_d / 2)
        datums[f"fan.mount_{i}"] = (x, flange_y, z)
    # open corners: a flange at each face, and between them a round duct, so a screw's head
    # sits on the deck-side flange and its driver comes through the other flange's hole (Fig. 9)
    flange = extrude(level(0) * outline, amount=p.fan_flange_t)
    duct_low, duct_high = back_y + p.fan_flange_t, -p.fan_flange_t
    duct = ycyl(p.fan_size / 2, duct_low, duct_high) - ycyl(p.fan_bore_d / 2, duct_low, duct_high)
    fan = flange + Pos(0, duct_low, 0) * flange + duct

    # the struts across the back, and the motor and hub as one cylinder standing on them
    strut_y = back_y + p.fan_strut_t
    bar = Pos(0, (back_y + strut_y) / 2, 0) * Box(p.fan_bore_d + 2 * p.fan_strut_w, p.fan_strut_t, p.fan_strut_w)
    hub_y = -p.hub_recess
    fan += bar + Rot(0, 90, 0) * bar + ycyl(p.fan_hub_d / 2, back_y, hub_y)

    # the blades: flat plates pitched about their radial axis, trimmed to the tip circle
    pitch = math.radians(p.fan_blade_pitch)
    tall = p.fan_blade_chord * math.sin(pitch) + p.fan_blade_t * math.cos(pitch)
    mid_y = (strut_y + hub_y) / 2
    tip_r = p.fan_tip_d / 2
    reach = tip_r + p.fan_blade_chord
    plate = Pos(reach / 2, mid_y, 0) * Rot(p.fan_blade_pitch, 0, 0) * Box(reach, p.fan_blade_t, p.fan_blade_chord)
    plate &= ycyl(tip_r, strut_y, hub_y)
    for i, a in enumerate(ring(p.fan_blades, p.fan_blade_a), 1):
        fan += Rot(0, -a, 0) * plate
        datums[f"fan.blade_{i}"] = polar(tip_r, a, mid_y)

    datums["fan.axis"] = (0, back_y / 2, 0)
    datums["fan.hub_wall"] = (p.fan_hub_d / 2, (hub_y + mid_y + tall / 2) / 2, 0)
    datums["fan.hub_top"] = (0, hub_y, 0)
    datums["fan.side_a"] = (corner / 2, flange_y, corner / 2)
    datums["fan.side_b"] = (-corner / 2, flange_y, -corner / 2)
    datums["fan.side_c"] = (-corner / 2, flange_y, corner / 2)
    datums["fan.side_d"] = (corner / 2, flange_y, -corner / 2)
    return fan


def rounded_corner(corner, toward_a, toward_b, radius):
    """The round of a radius in the corner between two points, as arc() gives it."""
    ua = (toward_a[0] - corner[0], toward_a[1] - corner[1])
    ub = (toward_b[0] - corner[0], toward_b[1] - corner[1])
    na, nb = math.hypot(*ua), math.hypot(*ub)
    ua, ub = (ua[0] / na, ua[1] / na), (ub[0] / nb, ub[1] / nb)
    half = math.acos(ua[0] * ub[0] + ua[1] * ub[1]) / 2
    bis = (ua[0] + ub[0], ua[1] + ub[1])
    nbis = math.hypot(*bis)
    reach = radius / math.sin(half)
    centre = (corner[0] + bis[0] / nbis * reach, corner[1] + bis[1] / nbis * reach)
    run = radius / math.tan(half)
    ta = (corner[0] + ua[0] * run, corner[1] + ua[1] * run)
    tb = (corner[0] + ub[0] * run, corner[1] + ub[1] * run)
    return arc(centre, radius, (ta[0] - centre[0], ta[1] - centre[1]), (tb[0] - centre[0], tb[1] - centre[1]))


def build_lid(p, datums, threads):
    """Its own frame: the rim it stands on at y = 0, its axis on y, its closed top at y = lid_h."""
    rim_r, top_r, wall = p.lid_d / 2, p.lid_top_d / 2, p.lid_wall
    out_a, out_arc, out_b = rounded_corner((top_r, p.lid_h), (rim_r, 0), (0, p.lid_h), p.lid_corner_r)
    in_a, in_arc, in_b = rounded_corner(
        (top_r - wall, p.lid_h - wall), (0, p.lid_h - wall), (rim_r - wall, 0), p.lid_corner_r - wall
    )
    lid = turned(
        Polyline((rim_r - wall, 0), (rim_r, 0), out_a),
        out_arc,
        Polyline(out_b, (0, p.lid_h), (0, p.lid_h - wall), in_a),
        in_arc,
        Polyline(in_b, (rim_r - wall, 0)),
    )
    datums["lid.rim_a"] = (rim_r, 0, 0)
    datums["lid.rim_b"] = (-rim_r, 0, 0)
    datums["lid.top"] = (0, p.lid_h, 0)
    return lid


def build_lid_switch(p, datums, threads):
    """Its own frame: its top face at y = 0, x across its thickness, z along its length."""
    datums["lid_switch.top"] = (0, 0, 0)
    return Pos(0, -p.ls_h / 2, 0) * Box(p.ls_t, p.ls_h, p.ls_l)


def build_main_switch(p, datums, threads):
    """Its own frame: the back of its bezel, which meets the wall, at x = 0; +x out of the wall, y up."""
    body = Pos(-p.msw_depth / 2, 0, 0) * Box(p.msw_depth, p.msw_L, p.msw_W)
    bezel = Pos(p.msw_bezel_t / 2, 0, 0) * Box(p.msw_bezel_t, p.msw_bezel_h, p.msw_bezel_w)
    datums["main_switch.top"] = (-p.msw_depth / 2, p.msw_L / 2, 0)
    datums["main_switch.bottom"] = (-p.msw_depth / 2, -p.msw_L / 2, 0)
    datums["main_switch.side_a"] = (-p.msw_depth / 2, 0, p.msw_W / 2)
    datums["main_switch.side_b"] = (-p.msw_depth / 2, 0, -p.msw_W / 2)
    return body + bezel


def build_dc_socket(p, datums, threads):
    """Its own frame: the back of its flange, which meets the wall, at x = 0; its axis on x, +x out of the wall."""
    def xcyl(diameter, x_low, x_high):
        return Pos((x_low + x_high) / 2, 0, 0) * Rot(0, 90, 0) * Cylinder(diameter / 2, x_high - x_low)

    front = p.dcs_flange_t
    floor = front - p.dcs_bore_depth
    socket = xcyl(p.dcs_body_d, -p.dcs_len, 0) + xcyl(p.dcs_flange_d, 0, front)
    socket -= xcyl(p.dcs_bore_d, floor, front)
    socket += xcyl(p.dcs_pin_d, floor, front)
    datums["dc_socket.bore_wall"] = ((floor + front) / 2, p.dcs_bore_d / 2, 0)
    datums["dc_socket.pin_wall"] = ((floor + front) / 2, p.dcs_pin_d / 2, 0)
    return socket


def build_plate_screw(p, datums, threads):
    """Its own frame: the flat face of its countersunk head at y = 0, its shank up along +y to its tip."""
    head_h = (p.plate_screw_head_d - p.plate_screw) / 2  # a 90 degree head: as deep as it is wide
    head = Pos(0, head_h / 2, 0) * Rot(-90, 0, 0) * Cone(p.plate_screw_head_d / 2, p.plate_screw / 2, head_h)
    screw = head + ycyl(p.plate_screw / 2, head_h, p.plate_screw_len)
    datums["plate_screw.head_face"] = (0, 0, 0)
    datums["plate_screw.tip"] = (0, p.plate_screw_len, 0)
    datums["plate_screw.shank"] = (0, (head_h + p.plate_screw_len) / 2, 0)
    threads["plate_screw.shank"] = "plate_screw"
    return screw


# ---------------------------------------------------------------- made beside the object


def build_fit_coupon(p, datums, threads):
    """A slice of the body, printed and tried before it: the deck with the wall standing on it.

    Its own frame: the deck's top at y = 0, as the body's, x along its length, the wall's outside at z = 0.
    The wall holds the main switch's cut-out and the DC socket's hole at the fit's gap and a step
    either side; the deck holds the lid switch's pocket and a bottom plate screw's hole.
    """
    m = p.coupon_margin
    wall_t = p.b_r_out - p.b_r_in
    deck_y, rim_y = -p.b_deck_t, -p.b_h
    hole_d = 2 * p.dc_hole_r
    steps = (-p.coupon_step, 0, p.coupon_step)
    length = m + p.ms_cut_w + m + sum(hole_d + 2 * s + m for s in steps)
    width = wall_t + m + p.pk_len + m

    def block(x_low, x_high, y_low, y_high, z_low, z_high):
        centre = ((x_low + x_high) / 2, (y_low + y_high) / 2, (z_low + z_high) / 2)
        return Pos(*centre) * Box(x_high - x_low, y_high - y_low, z_high - z_low)

    coupon = block(0, length, deck_y, 0, 0, width) + block(0, length, rim_y, deck_y, 0, wall_t)

    # through the wall: the main switch's cut-out, then the DC socket's hole three times
    coupon -= block(m, m + p.ms_cut_w, p.ms_top_y - p.ms_cut_h, p.ms_top_y, 0, wall_t)
    x = m + p.ms_cut_w + m
    for i, s in enumerate(steps, 1):
        d = hole_d + 2 * s
        coupon -= Pos(x + d / 2, p.dc_y, wall_t / 2) * Cylinder(d / 2, wall_t)
        datums[f"fit_coupon.socket_hole_{i}"] = (x + d / 2, p.dc_y + d / 2, wall_t / 2)
        x += d + m

    # through the deck: the lid switch's pocket and a screw post's hole
    z_mid = wall_t + m + p.pk_len / 2
    coupon -= block(m, m + p.pk_w, deck_y, 0, z_mid - p.pk_len / 2, z_mid + p.pk_len / 2)
    screw_x = m + p.pk_w + m + p.post_hole_r
    coupon -= Pos(screw_x, 0, z_mid) * ycyl(p.post_hole_r, deck_y, 0)
    datums["fit_coupon.screw_hole"] = (screw_x, deck_y / 2, z_mid)
    return coupon


# ---------------------------------------------------------------- the model


def build(p):
    parts = {}
    datums = {}
    threads = {}
    assembly = {}

    parts["body"] = build_body(p, datums, threads)
    parts["bottom_plate"] = build_bottom_plate(p, datums, threads)
    parts["rotor"] = build_rotor(p, datums, threads)
    parts["fan"] = build_fan(p, datums, threads)
    parts["lid"] = build_lid(p, datums, threads)
    parts["lid_switch"] = build_lid_switch(p, datums, threads)
    parts["main_switch"] = build_main_switch(p, datums, threads)
    parts["dc_socket"] = build_dc_socket(p, datums, threads)
    parts["plate_screw"] = build_plate_screw(p, datums, threads)
    # the fit coupon is made beside the object: no instance places it
    parts["fit_coupon"] = build_fit_coupon(p, datums, threads)

    deck_y = -p.b_deck_t
    assembly["body_1"] = ("body", Location((0, 0, 0)))
    assembly["bottom_plate_1"] = ("bottom_plate", Location((0, 0, 0)))
    # the fan under the deck, its hub up through the centre hole; the rotor's seat on the hub's top
    assembly["fan_1"] = ("fan", Location((0, deck_y, 0)))
    assembly["rotor_1"] = ("rotor", Location((0, p.rotor_y, 0)))
    # the lid's rim in the groove, on the inner round
    assembly["lid_1"] = ("lid", Location((0, p.lid_seat_y, 0)))
    # the lid switch in its pocket, the main switch and the DC socket through the wall
    pocket_at = along(p.pk_dir, p.pk_near + p.pk_len / 2, p.pk_side + p.pk_w / 2, p.ls_top_y)
    assembly["lid_switch_1"] = ("lid_switch", facing(p.pk_dir, pocket_at))
    cut_at = along(p.ms_dir, p.b_r_out, p.ms_side + p.ms_cut_w / 2, p.ms_top_y - p.ms_cut_h / 2)
    assembly["main_switch_1"] = ("main_switch", facing(p.ms_dir, cut_at))
    hole_at = along(p.dc_dir, p.b_r_out, p.dc_off, p.dc_y)
    assembly["dc_socket_1"] = ("dc_socket", facing(p.dc_dir, hole_at))
    # the screws up through the plate into the posts, each head's cone on its hole's edge
    under_y = p.bp_top_y - p.bp_t
    head_y = under_y - (p.plate_screw_head_d / 2 - p.bp_hole_r)
    for i, a in enumerate(ring(p.bp_hole_n, p.bp_hole_a), 1):
        assembly[f"plate_screw_{i}"] = ("plate_screw", Location(polar(p.bp_hole_R, a, head_y)))

    for i in range(1, int(p.bp_hole_n) + 1):
        threads[f"body.post_hole_{i}"] = "plate_screw"
        threads[f"bottom_plate.hole_{i}"] = "plate_screw"

    return {"parts": parts, "datums": datums, "assembly": assembly, "threads": threads}
