"""What each released body settles, and the frame its file holds it in.

Run:  cadrev python read_bodies.py            the values the model uses, body by body
      cadrev python read_bodies.py --faces ID  every face of one body, with its surface's parameters

Every number printed is read from the STEP files. Lengths are millimetres, as the files hold
them. A value prints as its design value where the file is within 0.0001 of one with at most
two decimals (32.5, not 32.4999); any other prints to four decimals as the file holds it,
marked ~. Angles about an axis are in the x-z plane, measured from +x towards +z, in degrees.
"""

import math
import sys
from pathlib import Path

import yaml
from build123d import GeomType, import_step
from OCP.BRepAdaptor import BRepAdaptor_Surface

HERE = Path(__file__).resolve().parent
PROJECT = yaml.safe_load((HERE / "project.yaml").read_text())
GEOMETRY = {s["id"]: HERE / s["path"] for s in PROJECT["sources"] if s["kind"] == "geometry"}
BUILT = ("body", "bottom_plate", "rotor")  # the bodies the target builds; evidence.yaml skips the rest
SQRT2 = math.sqrt(2)


# ---------------------------------------------------------------- reading


def d(v):
    """A length as its design value, or to four decimals marked ~."""
    for n in (0, 1, 2):
        r = round(v, n) + 0.0  # no negative zero
        if abs(v - r) <= 1e-4:
            return f"{r:.{n}f}" if n else f"{int(r)}"
    return f"~{v:.4f}"


def pt(a, b):
    return f"({d(a)}, {d(b)})"


def ang(x, z):
    return math.degrees(math.atan2(z, x))


def solids(source_id):
    return import_step(GEOMETRY[source_id]).solids()


def surface(face):
    """One face as a dict: its kind, its surface's parameters and its extent."""
    ad = BRepAdaptor_Surface(face.wrapped)
    bb = face.bounding_box()
    f = {"face": face, "kind": str(face.geom_type).split(".")[-1], "area": face.area,
         "min": (bb.min.X, bb.min.Y, bb.min.Z), "max": (bb.max.X, bb.max.Y, bb.max.Z)}
    g = face.geom_type
    if g == GeomType.PLANE:
        pl = ad.Plane()
        p, n = pl.Location(), pl.Axis().Direction()
        f.update(p=(p.X(), p.Y(), p.Z()), n=(n.X(), n.Y(), n.Z()))
    elif g == GeomType.CYLINDER:
        cy = ad.Cylinder()
        p, a = cy.Location(), cy.Axis().Direction()
        f.update(r=cy.Radius(), p=(p.X(), p.Y(), p.Z()), a=(a.X(), a.Y(), a.Z()))
    elif g == GeomType.CONE:
        co = ad.Cone()
        p, a = co.Apex(), co.Axis().Direction()
        f.update(half_angle=abs(math.degrees(co.SemiAngle())), apex=(p.X(), p.Y(), p.Z()), a=(a.X(), a.Y(), a.Z()))
    elif g == GeomType.TORUS:
        to = ad.Torus()
        p = to.Location()
        f.update(major=to.MajorRadius(), minor=to.MinorRadius(), p=(p.X(), p.Y(), p.Z()))
    return f


def surfaces(solid):
    return [surface(f) for f in solid.faces()]


def vertical(f):
    return abs(abs(f["a"][1]) - 1) < 1e-6


def on_axis(f):
    return math.hypot(f["p"][0], f["p"][2]) < 1e-4


def cylinders(fs, r=None, coaxial=None):
    out = [f for f in fs if f["kind"] == "CYLINDER" and (r is None or abs(f["r"] - r) < 1e-4)]
    if coaxial is not None:
        out = [f for f in out if (vertical(f) and on_axis(f)) == coaxial]
    return out


def level_planes(fs, level, tol=1e-4):
    return [f for f in fs if f["kind"] == "PLANE" and abs(abs(f["n"][1]) - 1) < 1e-6 and abs(f["p"][1] - level) < tol]


def upright_planes(fs):
    return [f for f in fs if f["kind"] == "PLANE" and abs(f["n"][1]) < 1e-6]


def corners(f):
    """The distinct (x, z) of a face's vertices."""
    seen = []
    for v in f["face"].vertices():
        if not any(math.hypot(v.X - x, v.Z - z) < 1e-5 for x, z in seen):
            seen.append((v.X, v.Z))
    return seen


def offset(f):
    """How far an upright plane lies from the y axis, along its normal."""
    return f["n"][0] * f["p"][0] + f["n"][2] * f["p"][2]


def r_at(cone, y):
    """The radius of a cone about the y axis at height y."""
    return abs(y - cone["apex"][1]) * math.tan(math.radians(cone["half_angle"]))


def coaxial_circles(solid):
    """(r, y) of every circular edge about the y axis: the corners of a turned profile."""
    out = set()
    for e in solid.edges():
        if e.geom_type != GeomType.CIRCLE:
            continue
        c = e.arc_center
        if math.hypot(c.X, c.Z) < 1e-4 and all(abs(e.position_at(t).Y - c.Y) < 1e-6 for t in (0, 0.5, 1)):
            out.add((round(e.radius, 4), round(c.Y, 4)))
    return sorted(out, key=lambda q: (q[1], q[0]))


def summary(source_id):
    ss = solids(source_id)
    for i, s in enumerate(ss, 1):
        bb = s.bounding_box()
        name = source_id if len(ss) == 1 else f"{source_id}#{i}"
        print(f"  {name:14s} x {d(bb.min.X)}..{d(bb.max.X)}  y {d(bb.min.Y)}..{d(bb.max.Y)}  z {d(bb.min.Z)}..{d(bb.max.Z)}"
              f"  volume {s.volume:.1f} mm3")


# ---------------------------------------------------------------- the body


def read_body():
    s = solids("body")[0]
    fs = surfaces(s)
    bb = s.bounding_box()
    print("BODY  (source body, Centrifuge body.step, one solid)")
    print("  frame: the assembly's. Origin on the body's axis, in the plane of the deck's top face.")
    print("         +y is up along the axis: the deck's top is y = 0, the open rim the bottom plate closes is y = -34.")
    print("         x and z lie in the deck: the four fan holes are on +x, -x, +z and -z.")
    print("         About the axis from +x towards +z: lid switch pocket near 40 deg, main switch cut-out at 135,")
    print("         DC socket hole at 225.")
    print(f"  envelope: x {d(bb.size.X)}, y {d(bb.size.Y)}, z {d(bb.size.Z)};  volume {s.volume:.1f} mm3")

    co = sorted(cylinders(fs, coaxial=True), key=lambda f: -f["r"])
    wall_out, wall_in = co[0], co[1]
    print(f"  wall: outside radius {d(wall_out['r'])} over y {d(wall_out['min'][1])}..{d(wall_out['max'][1])};"
          f" inside radius {d(wall_in['r'])} over y {d(wall_in['min'][1])}..{d(wall_in['max'][1])}")
    print(f"  deck: top face y = {d(bb.max.Y)}, underside y = {d(wall_in['max'][1])}")
    hole = cylinders(fs, r=22, coaxial=True)[0]
    print(f"  centre hole: radius {d(hole['r'])}, through the deck (y {d(hole['min'][1])}..{d(hole['max'][1])})")

    fan = sorted((f for f in cylinders(fs, r=2) if vertical(f)), key=lambda f: ang(f["p"][0], f["p"][2]))
    r_fan = math.hypot(fan[0]["p"][0], fan[0]["p"][2])
    print(f"  fan holes: {len(fan)}, radius {d(fan[0]['r'])}, through the deck (y {d(fan[0]['min'][1])}..{d(fan[0]['max'][1])}),"
          f" {d(r_fan)} from the axis: (x, z) = " + ", ".join(pt(f["p"][0], f["p"][2]) for f in fan))
    print(f"             neighbouring holes are {r_fan * SQRT2:.4f} apart: the fan's square hole pattern, its corners on the x and z axes")

    print("  lid groove, turned about the axis, in (radius, y):")
    g_in, g_out = cylinders(fs, r=53.5, coaxial=True)[0], cylinders(fs, r=61.5, coaxial=True)[0]
    tori = sorted((f for f in fs if f["kind"] == "TORUS"), key=lambda f: f["major"])
    floor = level_planes(fs, tori[0]["p"][1] - tori[0]["minor"])[0]
    print(f"    inner wall: radius {d(g_in['r'])} from y = {d(g_in['max'][1])} down to y = {d(g_in['min'][1])}")
    print(f"    inner round: an arc of radius {d(tori[0]['minor'])} centred at {pt(tori[0]['major'], tori[0]['p'][1])},"
          f" down to the floor")
    print(f"    floor: flat at y = {d(floor['p'][1])} from radius {d(tori[0]['major'])} to {d(tori[1]['major'])}")
    print(f"    outer round: an arc of radius {d(tori[1]['minor'])} centred at {pt(tori[1]['major'], tori[1]['p'][1])},"
          f" up from the floor")
    print(f"    outer wall: radius {d(g_out['r'])} from y = {d(g_out['min'][1])} up to y = {d(g_out['max'][1])}")

    print("  spin arrows: two recesses in the deck's top, the second the first turned 180 about the axis")
    recess = [f for f in fs if f["kind"] == "PLANE" and abs(abs(f["n"][1]) - 1) < 1e-6 and -1 < f["p"][1] < -1e-3]
    floors = sorted(recess, key=lambda f: -f["face"].center().X)
    band = sorted((f for f in cylinders(fs, coaxial=True) if f["max"][1] - f["min"][1] < 0.5 and f["r"] < 45),
                  key=lambda f: f["r"])
    pts = corners(floors[0])
    tip = min(pts, key=lambda q: q[0])
    tail = sorted((q for q in pts if abs(q[1]) < 1e-4), key=lambda q: q[0])
    base = sorted((q for q in pts if q is not tip and q not in tail), key=lambda q: q[1])
    print(f"    depth: floor at y = {d(floors[0]['p'][1])}")
    print(f"    arrow 1 shaft: the band between radius {d(band[0]['r'])} and {d(band[-1]['r'])} about the axis,")
    print(f"      from its square end on the +x axis, (x, z) = {pt(*tail[0])} to {pt(*tail[1])}, round through -z")
    print(f"      to the line x = {d(base[0][0])}, which it meets at z = {d(base[1][1])} and z = {d(base[2][1])}")
    print(f"    arrow 1 head: the triangle (x, z) = {pt(*base[0])}, {pt(*base[3])}, tip {pt(*tip)}")
    other = corners(floors[1])
    turned = all(any(math.hypot(x + u, z + w) < 1e-4 for u, w in other) for x, z in pts)
    print(f"    arrow 2: every corner of arrow 1 at (-x, -z): {'yes' if turned else 'NO'}")

    print("  screw posts for the bottom plate: four, each the one before turned 90 about the axis")
    posts = sorted((f for f in cylinders(fs, r=5) if vertical(f)), key=lambda f: ang(f["p"][0], f["p"][2]))
    holes = [f for f in cylinders(fs, r=1.6) if vertical(f)]
    print("    centres (x, z): " + ", ".join(pt(f["p"][0], f["p"][2]) for f in posts))
    p1 = next(f for f in posts if f["p"][0] > 0 and f["p"][2] < 0)
    cx, cz = p1["p"][0], p1["p"][2]
    print(f"    post 1 centre {pt(cx, cz)}: {d(math.hypot(cx, cz))} from the axis, at {ang(cx, cz):.4f} deg")
    print(f"    post: radius {d(p1['r'])}, y {d(p1['min'][1])}..{d(p1['max'][1])} where it is longest")
    print(f"    screw hole: radius {d(holes[0]['r'])} on the post's centre, y {d(holes[0]['min'][1])}..{d(holes[0]['max'][1])}"
          f" (open at the rim, blind)")
    cone = next(f for f in fs if f["kind"] == "CONE")
    webs = [f for f in upright_planes(fs) if abs(f["min"][1] - bb.min.Y) < 1e-4 and abs(f["max"][1] - cone["max"][1]) < 1e-4]
    print("    post 1's two flat sides join it to the wall, each tangent to the post's circle; (x, z) on the post -> on the wall:")
    for f in webs:
        if math.hypot(f["face"].center().X - cx, f["face"].center().Z - cz) < 8:
            a, b = sorted(corners(f), key=lambda q: math.hypot(*q))
            print(f"      {pt(*a)} -> {pt(*b)}   [{d(math.hypot(*a))} and {d(math.hypot(*b))} from the axis]")
    flat = min((f for f in fs if f["kind"] == "PLANE" and abs(abs(f["n"][1]) - 1) < 1e-6
                and cone["min"][1] - 1e-4 < f["p"][1] < cone["max"][1]), key=lambda f: f["p"][1])
    print(f"    top: cut by a cone about the body's axis, half-angle {d(cone['half_angle'])}, apex at y = {d(cone['apex'][1])}:")
    print(f"      the post's top is at y = radius - {d(-cone['apex'][1])}, so y = {d(cone['max'][1])} at the wall,"
          f" and it is flat at y = {d(flat['p'][1])} inside radius {d(r_at(cone, flat['p'][1]))}")

    print("  lid switch pocket: a rectangle cut up through the deck from its underside into the lid groove's floor")
    pocket = [f for f in upright_planes(fs) if abs(f["min"][1] - wall_in["max"][1]) < 1e-4 and f["max"][1] < -1]
    pcx = sum(f["face"].center().X for f in pocket) / 4
    pcz = sum(f["face"].center().Z for f in pocket) / 4
    long_side = max(pocket, key=lambda f: f["area"])
    e = long_side["n"] if long_side["n"][0] * pcx + long_side["n"][2] * pcz > 0 else tuple(-c for c in long_side["n"])
    across = (-e[2], 0.0, e[0])
    along = sorted(e[0] * f["p"][0] + e[2] * f["p"][2] for f in pocket if abs(f["n"][0] * e[0] + f["n"][2] * e[2]) > 0.99)
    cross = sorted(across[0] * f["p"][0] + across[2] * f["p"][2] for f in pocket if abs(f["n"][0] * e[0] + f["n"][2] * e[2]) < 0.01)
    quad = [(u * e[0] + v * across[0], u * e[2] + v * across[2]) for u in along for v in cross]
    print(f"    {d(along[1] - along[0])} along the direction ({e[0]:.5f}, 0, {e[2]:.5f}), which is {d(ang(e[0], e[2]))} deg:"
          f" its faces at {d(along[0])} and {d(along[1])} along it from the axis")
    print(f"    {d(cross[1] - cross[0])} across it, along ({across[0]:.5f}, 0, {across[2]:.5f}): its faces at {d(cross[0])} and {d(cross[1])}")
    print("    corners (x, z): " + ", ".join(pt(*q) for q in quad))
    print(f"    cut from y = {d(pocket[0]['min'][1])} upward; it opens into the groove, whose floor there is no higher than"
          f" y = {max(f['max'][1] for f in pocket):.4f}")

    print("  main switch cut-out: a rectangle through the wall, its two sides parallel")
    cut = [f for f in upright_planes(fs) if f not in pocket and f not in webs and f["max"][1] - f["min"][1] > 10]
    lo, hi = min(f["min"][1] for f in cut), max(f["max"][1] for f in cut)
    n = cut[0]["n"] if cut[0]["n"][0] > 0 else tuple(-c for c in cut[0]["n"])
    offs = sorted(n[0] * f["p"][0] + n[2] * f["p"][2] for f in cut)
    mx = sum(f["face"].center().X for f in cut) / 2
    mz = sum(f["face"].center().Z for f in cut) / 2
    out = (-n[2], n[0]) if (-n[2] * mx + n[0] * mz) > 0 else (n[2], -n[0])
    print(f"    height: y {d(lo)}..{d(hi)}  ({d(hi - lo)} tall)")
    print(f"    width: between two planes square to the direction ({n[0]:.5f}, 0, {n[2]:.5f}), at {d(offs[0])} and {d(offs[1])}"
          f" along it from the axis  ({d(offs[1] - offs[0])} wide)")
    print(f"    it runs out through the wall along ({out[0]:.5f}, 0, {out[1]:.5f}), which is {d(ang(*out))} deg")

    print("  DC socket hole: a round hole through the wall")
    dc = next(f for f in cylinders(fs) if not vertical(f))
    px, py, pz = dc["p"]
    ax, az = dc["a"][0], dc["a"][2]
    t = -(px * ax + pz * az)
    qx, qz = px + t * ax, pz + t * az
    cdc = dc["face"].center()
    sign = 1 if (cdc.X * ax + cdc.Z * az) > 0 else -1
    print(f"    radius {d(dc['r'])}; axis level, at y = {d(py)}, pointing out along ({sign * ax:.5f}, 0, {sign * az:.5f}),"
          f" which is {d(ang(sign * ax, sign * az) % 360)} deg")
    print(f"    the axis passes {d(math.hypot(qx, qz))} from the body's axis, through (x, z) = {pt(qx, qz)}")
    print()


# ---------------------------------------------------------------- the bottom plate


def read_bottom_plate():
    s = solids("bottom_plate")[0]
    fs = surfaces(s)
    bb = s.bounding_box()
    print("BOTTOM PLATE  (source bottom_plate, Bottom plate.step, one solid)")
    print("  frame: the body's, so the plate is built in place. +y up; its top face lies on the body's rim, y = -34;")
    print("         its feet reach down from it. Its four holes are on the body's four post centres.")
    print(f"  envelope: x {d(bb.size.X)}, y {d(bb.size.Y)} (y {d(bb.min.Y)}..{d(bb.max.Y)}), z {d(bb.size.Z)};  volume {s.volume:.1f} mm3")
    disc = cylinders(fs, coaxial=True)[0]
    print(f"  disc: radius {d(disc['r'])}, y {d(disc['min'][1])}..{d(disc['max'][1])}")
    holes = sorted(cylinders(fs, r=1.75), key=lambda f: ang(f["p"][0], f["p"][2]))
    print(f"  screw holes: {len(holes)}, radius {d(holes[0]['r'])}, through the disc, {d(math.hypot(holes[0]['p'][0], holes[0]['p'][2]))}"
          f" from the axis, (x, z) = " + ", ".join(pt(f["p"][0], f["p"][2]) for f in holes))
    feet = sorted(cylinders(fs, r=5), key=lambda f: ang(f["p"][0], f["p"][2]))
    print(f"  feet: {len(feet)}, radius {d(feet[0]['r'])}, y {d(feet[0]['min'][1])}..{d(feet[0]['max'][1])},"
          f" {d(math.hypot(feet[0]['p'][0], feet[0]['p'][2]))} from the axis, (x, z) = "
          + ", ".join(pt(f["p"][0], f["p"][2]) for f in feet))
    print(f"        the first foot listed is at {ang(feet[0]['p'][0], feet[0]['p'][2]):.4f} deg, the first hole at"
          f" {ang(holes[0]['p'][0], holes[0]['p'][2]):.4f} deg; each set turns 90 about the axis")
    print()


# ---------------------------------------------------------------- the rotor


def read_rotor():
    s = solids("rotor")[0]
    fs = surfaces(s)
    bb = s.bounding_box()
    top = bb.max.Y
    cones = [f for f in fs if f["kind"] == "CONE"]
    steep = sorted((f for f in cones if abs(f["half_angle"] - 45) < 1e-3), key=lambda f: f["apex"][1])
    lip, bowl_in = steep[0], steep[-1]
    bowl_out = next(f for f in steep[1:-1] if abs(f["max"][1] - top) < 1e-4)
    under = next(f for f in steep[1:-1] if f is not bowl_out)
    slim = sorted((f for f in cones if f["half_angle"] < 14), key=lambda f: f["apex"][1])
    cavity, outer = slim[0], slim[1]
    chamfer = next(f for f in cones if f not in steep and f not in slim)
    tor = next(f for f in fs if f["kind"] == "TORUS")
    spline = next(f for f in fs if f["kind"] == "BSPLINE")
    skirt_in, skirt_out = sorted(cylinders(fs, coaxial=True), key=lambda f: f["r"])
    down = [f for f in fs if f["kind"] == "PLANE" and abs(abs(f["n"][1]) - 1) < 1e-6]
    seat = max((f for f in down if abs(f["p"][1] - lip["min"][1]) < 1e-4), key=lambda f: f["area"])
    tips = level_planes(fs, bb.min.Y)
    roots = [f for f in down if f not in tips and f is not seat and f["p"][1] < skirt_out["max"][1]]
    y_root = roots[0]["p"][1]
    tip_arc = next(e for e in s.edges() if e.geom_type == GeomType.CIRCLE and math.hypot(e.arc_center.X, e.arc_center.Z) > 1e-3
                   and e.arc_center.Y < 0 and e.radius > tor["minor"] + 1e-3 and abs(e.arc_center.X) < 1e-6)
    arc_r, arc_c = tip_arc.radius, (math.hypot(tip_arc.arc_center.X, tip_arc.arc_center.Z), tip_arc.arc_center.Y)
    t = math.tan(math.radians(outer["half_angle"]))
    y_corner = (outer["apex"][1] * t + bowl_out["apex"][1]) / (1 + t)
    corner = (r_at(outer, y_corner), y_corner)
    p_neck = (r_at(outer, outer["max"][1]), outer["max"][1])
    p_cham = (r_at(chamfer, chamfer["max"][1]), chamfer["max"][1])
    wall = (outer["apex"][1] - cavity["apex"][1]) * math.sin(math.radians(outer["half_angle"]))
    bowl_wall = (bowl_in["apex"][1] - bowl_out["apex"][1]) / SQRT2

    print("ROTOR  (source rotor, Rotor - 32,5 mm.step, one solid)")
    print("  frame: its own, NOT the assembly's. +y is the spin axis, from the hub end (prongs, y < 0) up to the bowl's rim.")
    print(f"         Origin on the axis where the bowl's inside cone has radius {d(r_at(bowl_in, 0))} and the outer cone, carried on,"
          f" radius {d(r_at(outer, 0))}:")
    print(f"         {d(-outer['min'][1])} above the foot of the outer cone, {d(-seat['p'][1])} above the seat face.")
    print("         About the axis: prong 1 has one side in the plane x = 0, on +z; tube hole 1 leans out towards -z.")
    print("         In the assembly its axis is the body's axis, and its seat face rests on the top of the fan's hub:")
    print("         how high that is, the sources do not say (gap G-rotor-place).")
    print(f"  envelope: x {d(bb.size.X)}, y {d(bb.size.Y)} (y {d(bb.min.Y)}..{d(top)}), z {d(bb.size.Z)};  volume {s.volume:.1f} mm3")
    print("  a turned shell with seven prongs below and six tube holes through its bowl.")
    print("  circular edges about the axis, (radius, y):")
    print("    " + "  ".join(pt(r, y) for r, y in coaxial_circles(s)))
    print("  cones about the axis, radius = |y - apex| * tan(half-angle):")
    for name, f in (("lip", lip), ("outer cone", outer), ("cavity cone", cavity), ("chamfer", chamfer),
                    ("bowl's inside", bowl_in), ("bowl's outside", bowl_out), ("bowl's underside", under)):
        print(f"    {name:17s} y {d(f['min'][1])}..{d(f['max'][1])}: half-angle {d(f['half_angle'])}, apex y = {d(f['apex'][1])}")

    print("  outside, bottom to top, in (radius, y):")
    print(f"    skirt: radius {d(skirt_out['r'])} from the prong tips, y = {d(skirt_out['min'][1])}, up to y = {d(skirt_out['max'][1])}")
    print(f"    outer cone: {pt(r_at(outer, outer['min'][1]), outer['min'][1])} -> {pt(*p_neck)}")
    print(f"    chamfer: -> {pt(*p_cham)}; its ends are {d(math.dist(corner, p_neck))} and {d(math.dist(corner, p_cham))} from where"
          f" the two cones would meet, {pt(*corner)}")
    print(f"    bowl's outside, at 45: -> {pt(r_at(bowl_out, top), top)}")
    print(f"    rim: flat at y = {d(top)}, which is {d(top / SQRT2)}*sqrt(2), from radius {d(r_at(bowl_out, top))} in to {d(r_at(bowl_in, top))}")
    print(f"    bowl's inside, at 45: {pt(r_at(bowl_in, top), top)} -> its point at {pt(0, bowl_in['apex'][1])};"
          f" the rim is {d((r_at(bowl_in, top) - r_at(bowl_in, 0)) * SQRT2)} up this slope from {pt(r_at(bowl_in, 0), 0)}")
    print(f"    the bowl's wall is {d(bowl_wall)} thick, measured square to it")
    print("  inside the hub end, bottom to top, in (radius, y):")
    print(f"    bore that takes the fan's hub: radius {d(skirt_in['r'])}, the prongs' inner faces, y {d(skirt_in['min'][1])}..{d(y_root)}")
    print(f"    seat face: flat at y = {d(seat['p'][1])}, from radius {d(r_at(lip, seat['p'][1]))} to {d(skirt_in['r'])};"
          f" it faces down, onto the hub's top")
    print(f"      (the faces between the prongs are at y = {d(y_root)}, {abs(y_root - seat['p'][1]):.4f} lower: one plane at the model's tolerance)")
    print(f"    lip, at 45: {pt(r_at(lip, lip['min'][1]), lip['min'][1])} -> {pt(r_at(lip, lip['max'][1]), lip['max'][1])}")
    print(f"    cavity cone: -> {pt(r_at(cavity, cavity['max'][1]), cavity['max'][1])}; parallel to the outer cone and {d(wall)} inside it,"
          f" measured square to both")
    print(f"    round: radius {d(tor['minor'])}, centred at {pt(tor['major'], tor['p'][1])}, -> {pt(r_at(under, under['max'][1]), under['max'][1])}")
    print(f"    bowl's underside, at 45, the bowl's outside cone again: -> {pt(r_at(under, under['min'][1]), under['min'][1])}")
    print(f"    tip round: radius {d(arc_r)}, centred at {pt(*arc_c)}, -> {pt(arc_c[0], arc_c[1] - arc_r)};"
          f" a revolved arc, which the file holds as a B-spline face")
    print(f"    tip flat: y = {d(spline['min'][1])}, inside radius {d(arc_c[0])}")

    print(f"  prongs: {len(tips)}, evenly about the axis ({360 / len(tips):.4f} deg apart)")
    print(f"    each: between radius {d(skirt_in['r'])} and {d(skirt_out['r'])}, from y = {d(bb.min.Y)} up to y = {d(y_root)}"
          f" ({d(y_root - bb.min.Y)} long), its two sides planes through the axis")
    angles = sorted(ang(f["face"].center().X, f["face"].center().Z) % 360 for f in upright_planes(fs))
    a0, a1 = [a for a in angles if 70 < a < 91]
    print(f"    prong 1: from {a1:.4f} deg, the +z axis, to {a0:.4f} deg, so {a1 - a0:.4f} deg wide: its outer corner is"
          f" {d(skirt_out['r'] * math.sin(math.radians(a1 - a0)))} from the plane of its other side")
    print("    the others: prong 1 turned by whole steps of 360/7")

    tubes = sorted(cylinders(fs, coaxial=False), key=lambda f: ang(f["p"][0], f["p"][2]))
    h1 = next(f for f in tubes if abs(f["a"][0]) < 1e-6 and f["p"][2] < 0)
    px, py, pz = h1["p"]
    y_cross = py - pz / h1["a"][2] * h1["a"][1]
    y_wall = (y_cross + bowl_in["apex"][1]) / 2
    print(f"  tube holes: {len(tubes)}, evenly about the axis, radius {d(h1['r'])}, each through the bowl's wall only")
    print(f"    hole 1: its axis in the plane x = 0 (to within {abs(px):.4f}), tilted {d(math.degrees(math.acos(abs(h1['a'][1]))))}"
          f" from the spin axis, leaning out towards -z as it goes down")
    print(f"      it crosses the spin axis at y = {d(y_cross)}, and the bowl's inside cone at (radius, y) = {pt(r_at(bowl_in, y_wall), y_wall)},"
          f" {d((r_at(bowl_in, y_wall) - r_at(bowl_in, 0)) * SQRT2)} up the slope from {pt(r_at(bowl_in, 0), 0)}")
    print("    the holes lean out towards, deg: " + ", ".join(f"{ang(f['p'][0], f['p'][2]) % 360:.1f}" for f in tubes))
    print()


# ---------------------------------------------------------------- output


def dump_faces(source_id):
    for i, s in enumerate(solids(source_id), 1):
        print(f"{source_id} solid {i}: {len(s.faces())} faces, volume {s.volume:.3f} mm3")
        for f in sorted(surfaces(s), key=lambda f: (f["kind"], f["min"][1])):
            line = f"  {f['kind']:9s} area {f['area']:10.4f}  y {f['min'][1]:.4f}..{f['max'][1]:.4f}"
            if f["kind"] == "PLANE":
                line += f"  through ({f['p'][0]:.5f}, {f['p'][1]:.5f}, {f['p'][2]:.5f}) normal ({f['n'][0]:.5f}, {f['n'][1]:.5f}, {f['n'][2]:.5f})"
            elif f["kind"] == "CYLINDER":
                line += f"  radius {f['r']:.5f} axis through ({f['p'][0]:.5f}, {f['p'][1]:.5f}, {f['p'][2]:.5f}) along ({f['a'][0]:.5f}, {f['a'][1]:.5f}, {f['a'][2]:.5f})"
            elif f["kind"] == "CONE":
                line += f"  half-angle {f['half_angle']:.5f} apex ({f['apex'][0]:.5f}, {f['apex'][1]:.5f}, {f['apex'][2]:.5f}) along ({f['a'][0]:.5f}, {f['a'][1]:.5f}, {f['a'][2]:.5f})"
            elif f["kind"] == "TORUS":
                line += f"  major {f['major']:.5f} minor {f['minor']:.5f} centre ({f['p'][0]:.5f}, {f['p'][1]:.5f}, {f['p'][2]:.5f})"
            else:
                line += f"  x {f['min'][0]:.4f}..{f['max'][0]:.4f}  z {f['min'][2]:.4f}..{f['max'][2]:.4f}"
            print(line)


def main():
    if len(sys.argv) > 2 and sys.argv[1] == "--faces":
        dump_faces(sys.argv[2])
        return
    read_body()
    read_bottom_plate()
    read_rotor()
    print("EVERY RELEASED BODY  (its extent in its file's frame; evidence.yaml skips the ones not read above)")
    for source_id in GEOMETRY:
        summary(source_id)
    print(f"  built: {', '.join(BUILT)}")


if __name__ == "__main__":
    main()
