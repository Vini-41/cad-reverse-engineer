"""Parametric model. Reads every dimension from p (params.yaml); holds no dimension literals."""

from math import acos, asin, atan2, cos, degrees, pi, radians, sin, sqrt, tan

from build123d import *  # noqa: F403


# ---- involute teeth ---------------------------------------------------------------------

def _involute(rb, t, turn=0, flip=1):
    """The point at roll angle t on the involute of the base circle rb that leaves it on +x,
    mirrored about the line at `turn`/2 where flip is -1 (a tooth's other flank)."""
    x, y = rb * (cos(t) + t * sin(t)), rb * (sin(t) - t * cos(t))
    a = flip * atan2(y, x) + (turn if flip < 0 else 0)
    r = sqrt(x * x + y * y)
    return Vector(r * cos(a), r * sin(a))


def tooth_face(z, module, pressure_angle, r_in, r_out, points):
    """The face a row of z involute teeth encloses, from the circle r_in out to the circle r_out.

    An external gear's own section (r_in its root, r_out its tip), and the section of the space
    an internal gear's teeth leave (r_in its tip, r_out its root). The first flank is the
    involute that leaves the base circle on +x, as the released bodies hold it. Each flank is a
    spline through `points` points of the involute, evenly spaced in roll angle, which it is
    parametrised by, from the base circle (or r_in) out to r_out.
    """
    z, n = int(z), int(points)
    rp = module * z / 2
    rb = rp * cos(radians(pressure_angle))
    roll = lambda r: sqrt(max((r / rb) ** 2 - 1, 0))  # noqa: E731
    t_in, t_out = roll(max(r_in, rb)), roll(r_out)
    ts = [t_in + (t_out - t_in) * i / (n - 1) for i in range(n)]
    centre = pi / (2 * z) + tan(radians(pressure_angle)) - radians(pressure_angle)
    pitch = 2 * pi / z

    def flank(flip):
        pts = [_involute(rb, t, 2 * centre, flip) for t in ts]
        edges = [Edge.make_spline(pts, parameters=ts)]
        foot = pts[0]
        if r_in < rb:  # below the base circle the flank runs straight in along a radius
            foot = pts[0] * (r_in / rb)
            edges.insert(0, Edge.make_line(foot, pts[0]))
        return edges, foot, pts[-1]

    right, r_foot, r_tip = flank(1)
    left, l_foot, l_tip = flank(-1)
    a_foot, a_tip = atan2(r_foot.Y, r_foot.X), atan2(r_tip.Y, r_tip.X)
    top = Edge.make_circle(r_out, start_angle=degrees(a_tip), end_angle=degrees(2 * centre - a_tip))
    bottom = Edge.make_circle(r_in, start_angle=degrees(2 * centre - a_foot), end_angle=degrees(pitch + a_foot))
    one = right + [top] + left[::-1] + [bottom]
    edges = [e.rotate(Axis.Z, degrees(k * pitch)) for k in range(z) for e in one]
    return Face(Wire(edges))


def flank_datums(z, module, pressure_angle):
    """Two points on opposite flanks at the pitch radius, half a turn apart, in the gear's plane."""
    rp = module * int(z) / 2
    a = _involute(rp * cos(radians(pressure_angle)), tan(radians(pressure_angle)))
    return a, -a


def turned(points):
    """The solid a closed polygon of (r, h) points sweeps about the z axis."""
    return revolve(Plane.XZ * Polygon(*points, align=None), Axis.Z)


def placed(datums, at):
    """Datums worked out about a part's own axis, carried into its body's frame."""
    return {name: tuple((at * Pos(*Vector(v))).position) for name, v in datums.items()}


# ---- the parts, each in its released body's frame -----------------------------------------

def planet(p):
    at = Pos(p.planet_axis_x, p.planet_axis_y)
    body = extrude(tooth_face(p.z_planet, p.module, p.pressure_angle, p.planet_root_d / 2, p.planet_tip_d / 2, p.flank_points), p.planet_width)
    body -= Cylinder(p.planet_bore_d / 2, p.planet_width, align=(Align.CENTER, Align.CENTER, Align.MIN))
    seat = Cylinder(p.planet_seat_d / 2, p.planet_seat_depth, align=(Align.CENTER, Align.CENTER, Align.MIN))
    body -= seat
    body -= Pos(0, 0, p.planet_width - p.planet_seat_depth) * seat
    a, b = flank_datums(p.z_planet, p.module, p.pressure_angle)
    mid = Vector(0, 0, p.planet_width / 2)
    datums = {
        "planet.flank_a": a + mid,
        "planet.flank_b": b + mid,
        "planet.axis": mid,
        "planet.axis_end": Vector(0, 0, p.planet_width - p.planet_seat_depth / 2),
    }
    return at * body, placed(datums, at), {}


def sun(p):
    at = Pos(p.sun_axis_x, p.sun_axis_y)
    h_teeth = p.sun_journal_len + p.sun_shoulder_len
    h_flange = h_teeth + p.sun_teeth_len
    h_top = h_flange + p.sun_flange_t
    bore, journal, shoulder = p.sun_bore_d / 2, p.sun_journal_d / 2, p.sun_shoulder_d / 2
    core = shoulder + p.sun_shoulder_chamfer
    body = turned([
        (bore, 0), (journal - p.sun_journal_chamfer, 0), (journal, p.sun_journal_chamfer),
        (journal, p.sun_journal_len), (shoulder, p.sun_journal_len),
        (shoulder, h_teeth - p.sun_shoulder_chamfer), (core, h_teeth), (core, h_flange),
        (p.sun_flange_d / 2, h_flange), (p.sun_flange_d / 2, h_top),
        (p.sun_pocket_d / 2, h_top), (p.sun_pocket_d / 2, h_top - p.sun_pocket_depth),
        (bore, h_top - p.sun_pocket_depth),
    ])
    teeth = extrude(tooth_face(p.z_sun, p.module, p.pressure_angle, p.sun_root_d / 2, p.sun_tip_d / 2, p.flank_points), p.sun_teeth_len)
    body += Pos(0, 0, h_teeth) * (teeth - Cylinder(core, p.sun_teeth_len, align=(Align.CENTER, Align.CENTER, Align.MIN)))
    mounts = PolarLocations(p.sun_mount_circle_r, int(p.sun_n_mounts))
    body -= mounts * (Pos(0, 0, h_flange) * Cylinder(p.sun_mount_d / 2, p.sun_flange_t, align=(Align.CENTER, Align.CENTER, Align.MIN)))
    body -= mounts * (Pos(0, 0, h_flange) * Cone(p.sun_csk_d / 2, p.sun_mount_d / 2, p.sun_csk_depth, align=(Align.CENTER, Align.CENTER, Align.MIN)))
    a, b = flank_datums(p.z_sun, p.module, p.pressure_angle)
    mid = Vector(0, 0, h_teeth + p.sun_teeth_len / 2)
    datums = {
        "sun.flank_a": a + mid,
        "sun.flank_b": b + mid,
        "sun.axis": Vector(0, 0, p.sun_journal_len / 2),
        "sun.axis_end": mid,
    }
    clears = {"sun.axis": "sun_bolt"}
    return at * body, placed(datums, at), clears


def rod(radius, length):
    """A cylinder standing on the plane z = 0 about the z axis."""
    return Cylinder(radius, length, align=(Align.CENTER, Align.CENTER, Align.MIN))


def nut_pocket(p, across_flats, depth, turn):
    """A hexagonal pocket standing on z = 0, a corner on +x turned by `turn` degrees."""
    return extrude(RegularPolygon(across_flats / 2, int(p.hex_sides), major_radius=False, rotation=turn), depth)


def carrier(p):
    at = Pos(p.car_axis_x, p.car_axis_y, p.car_z0)
    n = int(p.n_planets)
    inner = p.car_journal_len + p.car_flange_t  # the plate's inner face
    stand = p.car_len - inner  # how far the posts and extrusions stand off it
    bore, journal, flange, seat = p.car_bore_d / 2, p.car_journal_d / 2, p.car_flange_d / 2, p.car_seat_d / 2
    body = turned([
        (bore, 0), (journal - p.car_journal_chamfer, 0), (journal, p.car_journal_chamfer),
        (journal, p.car_journal_len), (flange, p.car_journal_len), (flange, inner),
        (seat + p.car_seat_chamfer, inner), (seat, inner - p.car_seat_chamfer),
        (seat, inner - p.car_seat_depth), (bore, inner - p.car_seat_depth),
    ])
    posts = PolarLocations(p.car_post_circle_r, n, start_angle=90)
    between = PolarLocations(p.car_ext_circle_r, n, start_angle=90 + 180 / n)
    outs = PolarLocations(p.car_out_circle_r, int(p.car_n_out))
    lobes = Circle(p.car_lobe_outer_d / 2) - Circle(p.car_lobe_inner_d / 2) - posts * Circle(p.car_lobe_clear_r)
    lobes = fillet(lobes.vertices(), p.car_lobe_fillet)
    boss = rod(p.car_boss_d / 2, p.car_boss_h)
    boss = fillet(boss.edges().sort_by(Axis.Z)[-1], p.car_boss_round)
    body += Pos(0, 0, inner) * (extrude(lobes, stand) + posts * (boss + rod(p.car_post_d / 2, stand)))
    body -= posts * (rod(p.car_head_d / 2, p.car_head_depth) + rod(p.car_shaft_hole_d / 2, p.car_len))
    body -= between * (rod(p.car_ext_head_d / 2, p.car_ext_head_depth) + rod(p.car_ext_hole_d / 2, p.car_len))
    pocket = Pos(0, 0, p.car_out_hole_len) * nut_pocket(p, p.car_out_nut_af, inner - p.car_out_hole_len, 180 / p.hex_sides)
    body -= outs * (rod(p.car_out_hole_d / 2, inner) + pocket)
    datums = {
        "carrier.axis": Vector(0, 0, (inner - p.car_seat_depth) / 2),
        "carrier.axis_seat": Vector(0, 0, inner - p.car_seat_depth / 2),
        "carrier.mark": Vector(0, journal, p.car_journal_len / 2),
    }
    clears = {}
    for name, where, height, thread in (("shaft_hole", posts, inner + stand / 2, "shaft_bolt"),
                                        ("ext_hole", between, inner + stand / 2, "ext_bolt"),
                                        ("out_hole", outs, p.car_out_hole_len / 2, "out_thread")):
        for i, loc in enumerate(where):
            datums[f"carrier.{name}_{i + 1}"] = loc.position + Vector(0, 0, height)
            clears[f"carrier.{name}_{i + 1}"] = thread
    return at * body, placed(datums, at), clears


def sec_boss(p, rounded):
    """One boss of the secondary carrier with its fillet, about its own axis, end face on z = 0;
    the plate's axis lies at -x. The fillet is the surface a ball of its radius leaves, rolling
    on the boss and the plate's face, and on the rim's edge where the rim cuts that face short.
    """
    height, ball, boss_r, rim = p.sec_boss_h, p.sec_boss_fillet, p.sec_boss_d / 2, p.sec_od / 2
    track = boss_r + ball  # the ball's centre stays this far from the boss's axis
    plate_axis = Pos(-p.sec_post_circle_r, 0, 0)
    tall = 2 * (height + ball)
    # where the ball's centre runs while it rolls on the rim's edge
    off_rim = Pos(0, 0, height) * Torus(rim, ball) - rod(rim, tall) - Pos(0, 0, height) * rod(2 * rim, tall)
    crossing = (plate_axis * off_rim) & rod(track, tall)
    spine = [e for e in crossing.edges() if e.geom_type == GeomType.BSPLINE and e.center().X > 0
             and abs(sqrt(e.center().X ** 2 + e.center().Y ** 2) - track) < ball / 2][0]
    reach = degrees(acos((rim ** 2 - p.sec_post_circle_r ** 2 - track ** 2) / (2 * p.sec_post_circle_r * track)))
    start = spine @ 0
    inward = Vector(-start.X, -start.Y, 0).normalized()
    across = Plane(origin=start, x_dir=inward, z_dir=inward.cross(Vector(0, 0, 1)))
    guide = spine.transform_geometry(Matrix([[0.5, 0, 0, 0], [0, 0.5, 0, 0], [0, 0, 1, 0]]))
    small = p.sec_boss_round
    worn = sweep(Plane(origin=start, z_dir=spine % 0) * Circle(ball + small), path=spine)
    swept = sweep(across * (Circle(ball) + Rectangle(ball, tall, align=(Align.MIN, Align.MAX))), path=spine, binormal=guide)
    sector = revolve(Rot(0, 0, -reach) * (Plane.XZ * Rectangle(track, height, align=(Align.MIN, Align.MIN))), Axis.Z, 2 * reach)
    section = make_face([Polyline((track, height), (0, height), (0, 0), (boss_r, 0)), CenterArc((track, 0), ball, 180, -90)])
    boss = (sector - swept) + revolve(Rot(0, 0, reach) * (Plane.XZ * section), Axis.Z, 360 - 2 * reach)
    if not rounded:
        return boss
    # the round: the boss's end, worn back by the round's radius and grown out again by it. Up
    # to the height the round leaves the fillet at, the end is the worn floor carried down to
    # the end face with the round's ball swept along its edge. That height is exact off the
    # rim; over it, it is read at the fillet ball's own direction about the boss, which sits
    # within 0.001 of where the two surfaces touch.
    core = Pos(0, 0, small) * rod(track, tall) - Torus(track, ball + small) - worn
    floor = core.faces().sort_by(Axis.Z)[0]
    edge = floor.outer_wire().edges()[0]
    ring = sweep(Plane(origin=edge @ 0, z_dir=edge % 0) * Circle(small), path=floor.outer_wire())
    share = small / (ball + small)
    touch = ball * share  # the height the round leaves the fillet at, off the rim
    lifted = spine.transform_geometry(Matrix([[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, share, touch]]))  # and over the rim
    lifted_in = spine.transform_geometry(Matrix([[0.5, 0, 0, 0], [0, 0.5, 0, 0], [0, 0, share, touch]]))
    low = rod(2 * track, touch) + extrude(Face.make_surface_from_curves(lifted, lifted_in), tall, dir=(0, 0, -1))
    return (boss & low & (extrude(floor, small, dir=(0, 0, -1)) + ring)) + (boss - low)


def sec_carrier(p):
    at = Pos(p.sec_axis_x, p.sec_axis_y, p.sec_z0)
    n = int(p.n_planets)
    height = p.sec_boss_h
    posts = PolarLocations(p.sec_post_circle_r, n, start_angle=90)
    between = PolarLocations(p.sec_ext_circle_r, n, start_angle=90 + 180 / n)
    body = Pos(0, 0, height) * (rod(p.sec_od / 2, p.sec_t) - rod(p.sec_id / 2, p.sec_t))
    plain = sec_boss(p, False)
    for i, where in enumerate(posts):
        body += where * (sec_boss(p, True) if i == 0 else plain)
    body &= rod(p.sec_od / 2, height + p.sec_t)
    far = height + p.sec_t - p.sec_nut_depth
    socket = rod(p.sec_socket_d / 2, p.sec_socket_depth) + Cone(
        p.sec_socket_d / 2 + p.sec_socket_chamfer, p.sec_socket_d / 2, p.sec_socket_chamfer, align=(Align.CENTER, Align.CENTER, Align.MIN))
    body -= posts * (socket + rod(p.sec_shaft_hole_d / 2, height + p.sec_t)
                     + Pos(0, 0, far) * nut_pocket(p, p.sec_shaft_nut_af, p.sec_nut_depth, 180 / p.hex_sides))
    body -= between * (Pos(0, 0, height) * rod(p.sec_ext_hole_d / 2, p.sec_t) + Pos(0, 0, far) * nut_pocket(p, p.sec_ext_nut_af, p.sec_nut_depth, 0))
    datums, clears = {}, {}
    for name, where, thread in (("shaft_hole", posts, "shaft_bolt"), ("ext_hole", between, "ext_bolt")):
        for i, loc in enumerate(where):
            datums[f"sec_carrier.{name}_{i + 1}"] = loc.position + Vector(0, 0, (height + far) / 2)
            clears[f"sec_carrier.{name}_{i + 1}"] = thread
    return at * body, placed(datums, at), clears


def casing(p):
    at = Pos(p.cas_axis_x, p.cas_axis_y)
    body_r, waist, seat, shoulder = p.cas_body_d / 2, p.cas_waist_d / 2, p.cas_seat_d / 2, p.cas_shoulder_d / 2
    floor_r, mouth = p.cas_well_floor_d / 2, p.cas_mouth_d / 2
    well = floor_r + p.cas_well_fillet
    ring_top = p.cas_ring_z + p.cas_ring_width
    well_top = ring_top + p.cas_well_len
    pocket_floor = well_top + p.cas_mouth_len
    reach = p.cas_ear_circle_r + p.cas_ear_r  # the ears' tips
    flare_c = waist + p.cas_flare_r
    flare_turn = degrees(asin(sqrt(p.cas_flare_r ** 2 - (flare_c - reach) ** 2) / p.cas_flare_r))
    flare = CenterArc((flare_c, p.cas_flare_z), p.cas_flare_r, 180, -flare_turn)
    fillet_arc = CenterArc((floor_r, ring_top + p.cas_well_fillet), p.cas_well_fillet, 270, 90)
    outline = [
        Polyline((seat + p.cas_seat_chamfer, 0), (body_r, 0), (body_r, p.cas_body_len),
                 (waist, p.cas_body_len + p.cas_neck_len), (waist, p.cas_flare_z)),
        flare,
        Polyline(flare @ 1, (reach, p.cas_len), (mouth, p.cas_len), (mouth, pocket_floor),
                 (well, well_top), (well, ring_top + p.cas_well_fillet)),
        fillet_arc,
        Polyline(fillet_arc @ 0, (shoulder, ring_top), (shoulder, p.cas_seat_depth), (seat, p.cas_seat_depth),
                 (seat, p.cas_seat_chamfer), (seat + p.cas_seat_chamfer, 0)),
    ]
    body = revolve(Plane.XZ * make_face(outline), Axis.Z)
    ears = PolarLocations(p.cas_ear_circle_r, int(p.cas_n_ears), start_angle=180 / p.cas_n_ears)
    flange = Circle(p.cas_flange_d / 2) + ears * Circle(p.cas_ear_r)
    flange = fillet(flange.vertices(), p.cas_ear_fillet)
    body &= extrude(flange, p.cas_len)
    spaces = tooth_face(p.z_ring, p.module, p.pressure_angle, p.cas_ring_tip_d / 2, p.cas_ring_root_d / 2, p.flank_points)
    body -= Pos(0, 0, p.cas_ring_z) * extrude(spaces, p.cas_ring_width)
    pocket = Circle(p.cas_pocket_d / 2) + PolarLocations(p.cas_pocket_d / 2, int(p.cas_n_notches)) * Circle(p.cas_notch_r)
    pocket = fillet(pocket.vertices(), p.cas_notch_fillet)
    body -= Pos(0, 0, pocket_floor) * extrude(pocket, p.cas_len - pocket_floor)
    body -= ears * (rod(p.cas_ear_hole_d / 2, p.cas_len) + rod(p.cas_ear_cbore_d / 2, p.cas_len - p.cas_ear_hole_len))
    rets = PolarLocations(p.cas_ret_circle_r, int(p.cas_n_ret), start_angle=180 / p.cas_n_ret)
    slot = RegularPolygon(p.cas_slot_af / 2, int(p.hex_sides), major_radius=False, rotation=180 / p.hex_sides)
    slot += Rectangle(body_r, p.cas_slot_af / cos(pi / p.hex_sides), align=(Align.MIN, Align.CENTER))
    body -= rets * (rod(p.cas_ret_hole_d / 2, p.cas_ret_hole_depth) + Pos(0, 0, p.cas_slot_z) * extrude(slot, p.cas_slot_w))
    a, b = flank_datums(p.z_ring, p.module, p.pressure_angle)
    mid = Vector(0, 0, p.cas_ring_z + p.cas_ring_width / 2)
    girth = Vector(0, 0, (p.cas_body_len + p.cas_neck_len + p.cas_flare_z) / 2)  # mid-height of the waist
    datums = {
        "gearbox_casing.flank_a": a + mid,
        "gearbox_casing.flank_b": b + mid,
        "gearbox_casing.pitch": a + girth,
        "gearbox_casing.waist": a * (waist / a.length) + girth,
        "gearbox_casing.axis": Vector(0, 0, p.cas_seat_depth / 2),
        "gearbox_casing.mark": Vector(seat, 0, p.cas_seat_depth / 2),
    }
    clears = {}
    for i, loc in enumerate(rets):
        datums[f"gearbox_casing.ret_hole_{i + 1}"] = loc.position + Vector(0, 0, p.cas_slot_z / 2)
        clears[f"gearbox_casing.ret_hole_{i + 1}"] = "ret_screw"
    return at * body, placed(datums, at), clears


def retainer(p):
    """Bearing retainer ring, in its file's frame: axis along y."""
    at = Plane.ZX * Pos(p.ret_axis_z, p.ret_axis_x)
    holes = PolarLocations(p.ret_hole_circle_r, int(p.ret_n_holes))
    ring = Circle(p.ret_od / 2) - Circle(p.ret_id / 2) - holes * Circle(p.ret_hole_d / 2)
    datums, clears = {}, {}
    for i, loc in enumerate(holes):
        datums[f"bearing_retainer.hole_{i + 1}"] = loc.position + Vector(0, 0, p.ret_t / 2)
        clears[f"bearing_retainer.hole_{i + 1}"] = "ret_screw"
    return extrude(at * ring, p.ret_t), placed(datums, at), clears


def bearing(bore, outer, width):
    """A purchased bearing as its envelope: a plain ring about z, standing on z = 0."""
    return rod(outer / 2, width) - rod(bore / 2, width)


def tooth_centre(z, pressure_angle):
    """The angle of a tooth's centre line as tooth_face draws it, in radians."""
    return pi / (2 * int(z)) + tan(radians(pressure_angle)) - radians(pressure_angle)


def build(p):
    parts, datums, clears = {}, {}, {}
    makers = (("sun", sun), ("planet", planet), ("carrier", carrier), ("sec_carrier", sec_carrier),
              ("gearbox_casing", casing), ("bearing_retainer", retainer))
    for name, make in makers:
        parts[name], d, t = make(p)
        datums.update(d)
        clears.update(t)
    parts["output_bearing"] = bearing(p.out_brg_bore, p.out_brg_od, p.out_brg_w)
    parts["sun_bearing"] = bearing(p.sun_brg_bore, p.sun_brg_od, p.sun_brg_w)
    parts["planet_bearing"] = bearing(p.planet_brg_bore, p.planet_brg_od, p.planet_brg_w)

    # The assembly stands on the casing's axis, z = 0 at the casing's output end, as built:
    # the carrier as its file holds it, each planet and the sun turned into mesh with the ring.
    n = int(p.n_planets)
    ring_pitch, planet_pitch = 2 * pi / p.z_ring, 2 * pi / p.z_planet
    ring_space = tooth_centre(p.z_ring, p.pressure_angle)  # tooth_face draws the ring's spaces
    assembly = {
        "gearbox_casing_1": ("gearbox_casing", Pos(-p.cas_axis_x, -p.cas_axis_y, 0)),
        "bearing_retainer_1": ("bearing_retainer", Pos(0, 0, p.ret_z) * Rot(0, 0, p.ret_turn)
                               * Pos(-p.ret_axis_z, -p.ret_axis_x, 0) * Plane.ZX.location.inverse()),
        "carrier_1": ("carrier", Pos(-p.car_axis_x, -p.car_axis_y, p.carrier_z - p.car_z0)),
        "sec_carrier_1": ("sec_carrier", Pos(-p.sec_axis_x, -p.sec_axis_y, p.sec_z - p.sec_z0)),
        "output_bearing_1": ("output_bearing", Pos(0, 0, p.cas_seat_depth - p.out_brg_w)),
        "sun_bearing_1": ("sun_bearing", Pos(0, 0, p.carrier_z + p.car_journal_len + p.car_flange_t - p.sun_brg_w)),
    }
    joints = {
        "carrier": {"type": "revolute", "parent": "gearbox_casing_1", "child": "carrier_1",
                    "axis": ["carrier_1.axis", "carrier_1.axis_seat"], "drive": "passive"},
        "sun": {"type": "revolute", "parent": "gearbox_casing_1", "child": "sun_1",
                "axis": ["sun_1.axis", "sun_1.axis_end"], "drive": "actuated"},
        "sec_carrier": {"type": "fixed", "parent": "carrier_1", "child": "sec_carrier_1"},
        "retainer": {"type": "fixed", "parent": "gearbox_casing_1", "child": "bearing_retainer_1"},
        "output_bearing": {"type": "fixed", "parent": "gearbox_casing_1", "child": "output_bearing_1"},
        "sun_bearing": {"type": "fixed", "parent": "carrier_1", "child": "sun_bearing_1"},
    }
    couplings = {"sun_carrier": {"driver": "sun", "driven": "carrier", "ratio": "carrier_ratio"}}
    sun_turn = 0
    for i in range(n):
        at = radians(90) + i * 2 * pi / n  # the post's direction about the axis
        # the ring's space nearest this direction leads it by `lead`: the planet's tooth follows
        # it there, and the sun's tooth meets the planet's space on the line of centres
        lead = (ring_space - at + ring_pitch / 2) % ring_pitch - ring_pitch / 2
        turn = at + lead * p.z_ring / p.z_planet - tooth_centre(p.z_planet, p.pressure_angle)
        if i == 0:
            inner = (planet_pitch / 2 - pi) % planet_pitch - planet_pitch / 2  # its tooth nearest the sun, off that line
            sun_turn = (at - (lead * p.z_ring / p.z_planet + inner) * p.z_planet / p.z_sun + pi / p.z_sun
                        - tooth_centre(p.z_sun, p.pressure_angle))
        name = f"planet_{i + 1}"
        assembly[name] = ("planet", Pos(p.car_post_circle_r * cos(at), p.car_post_circle_r * sin(at), p.planet_z)
                          * Rot(0, 0, degrees(turn)) * Pos(-p.planet_axis_x, -p.planet_axis_y, 0))
        joints[name] = {"type": "revolute", "parent": "carrier_1", "child": name,
                        "axis": [f"{name}.axis", f"{name}.axis_end"], "drive": "passive"}
        couplings[f"carrier_{name}"] = {"driver": "carrier", "driven": name, "ratio": "planet_ratio"}
        # a bearing flush in each of the planet's seats, the near one on the post's boss
        seats = [p.planet_z + k * (p.planet_width - p.planet_brg_w) / (int(p.planet_brgs) - 1) for k in range(int(p.planet_brgs))]
        for k, z in enumerate(seats):
            brg = f"planet_bearing_{i * int(p.planet_brgs) + k + 1}"
            assembly[brg] = ("planet_bearing", Pos(p.car_post_circle_r * cos(at), p.car_post_circle_r * sin(at), z))
            joints[brg] = {"type": "fixed", "parent": name, "child": brg}
    assembly["sun_1"] = ("sun", Pos(0, 0, p.sun_z) * Rot(0, 0, degrees(sun_turn)) * Pos(-p.sun_axis_x, -p.sun_axis_y, 0))
    return {"parts": parts, "datums": datums, "assembly": assembly, "clears": clears, "joints": joints, "couplings": couplings}
