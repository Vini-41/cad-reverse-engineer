"""The RP2040's QFN-56 package: the moulded body, its 56 leads and the exposed centre pad.

Built in its footprint's frame, so the STEP file drops into an ECAD library with no transform. The
origin is the package's centre, where the land pattern's centrelines cross (Figure 168). Z = 0 is the
board's surface, the seating plane the leads stand on (datum C of Figure 167), and the package stands
on it along +Z. Seen from above, as Figure 3 and Figure 167's top view show it, X runs left to right
and Y bottom to top: pin 1 is at -X +Y, lead 1 the first down the -X side, and the numbers run
counter-clockwise, 15 to 28 along -Y, 29 to 42 up +X and 43 to 56 along +Y.

Reads every dimension from p (params.yaml); holds no dimension literals.
"""

from build123d import *  # noqa: F403

MID = (Align.CENTER, Align.CENTER, Align.MIN)


def lead_solid(p):
    """One lead in its own frame: its outer end on the body's side face at X = 0, running inward
    along +X, centred on Y, standing on the seating plane."""
    half_b, half_top = p.lead_b / 2, p.lead_top_w / 2
    # The end the side view draws: a trapezoid, b wide on the seating plane.
    end = Polygon((-half_b, 0), (half_b, 0), (half_top, p.frame_A3), (-half_top, p.frame_A3), align=None)
    bar = extrude(Plane.YZ * end, p.lead_L)
    # The outline the bottom view draws: L long, its inner end a half-round.
    straight = p.lead_L - p.lead_R
    outline = Pos(straight / 2, 0) * Rectangle(straight, p.lead_b) + Pos(straight, 0) * Circle(p.lead_R)
    return bar & extrude(outline, p.frame_A3)


def lead_places(p):
    """Lead number -> where it sits: row k on the side a quarter turn on from row k - 1."""
    places = {}
    per_side = round(p.leads_per_side)
    for k in range(round(p.lead_rows)):
        half = (p.body_D, p.body_E)[k % 2] / 2
        for j in range(per_side):
            along = p.lead_row_end - j * p.lead_pitch
            places[k * per_side + j + 1] = Rot(0, 0, 360 / p.lead_rows * k) * Pos(-half, along, 0)
    return places


def pad_solid(p):
    """The centre pad in its own frame: centred on the origin, standing on the seating plane, its
    notch in the -X edge, the one facing leads 1 to 14."""
    plate = Box(p.pad_D2, p.pad_E2, p.pad_t, align=MID)
    notch = Pos(-p.pad_D2 / 2 - p.notch_out, p.pad_E2 / 2 - p.notch_offset, 0) * Cylinder(p.notch_R, p.pad_t, align=MID)
    return plate - notch


def build(p):
    lead = lead_solid(p)
    pad = pad_solid(p)
    places = lead_places(p)
    pad_place = Pos(p.pad_x, p.pad_y, 0)

    # The body in the package's frame: moulded round the leads and the pad, which stand out under it
    # by the standoff, with the pin 1 dot sunk in its top face.
    block = Pos(0, 0, p.standoff) * Box(p.body_D, p.body_E, p.body_top - p.standoff, align=MID)
    dot = Pos(p.dot_x, p.dot_y, p.body_top - p.dot_depth) * Cylinder(p.dot_size / 2, p.dot_depth, align=MID)
    body = block - dot - [place * lead for place in places.values()] - pad_place * pad

    straight = p.lead_L - p.lead_R
    side_z = (p.standoff + p.body_top) / 2
    dot_z = p.body_top - p.dot_depth / 2
    notch_x, notch_y = -p.pad_D2 / 2 - p.notch_out, p.pad_E2 / 2 - p.notch_offset
    parts = {"body": body, "lead": lead, "pad": pad}
    datums = {
        # The body's four side faces, between two leads and above them, its top face and its underside.
        "body.x_min": (-p.body_D / 2, 0, side_z),
        "body.x_max": (p.body_D / 2, 0, side_z),
        "body.y_min": (0, -p.body_E / 2, side_z),
        "body.y_max": (0, p.body_E / 2, side_z),
        "body.top": (0, 0, p.body_top),
        "body.underside": ((p.body_D / 2 - p.lead_L + p.pad_x + p.pad_D2 / 2) / 2, 0, p.standoff),
        # The pin 1 dot's wall, at its -X and its -Y side.
        "body.dot_x_min": (p.dot_x - p.dot_size / 2, p.dot_y, dot_z),
        "body.dot_y_min": (p.dot_x, p.dot_y - p.dot_size / 2, dot_z),
        "lead.outer": (0, 0, p.frame_A3 / 2),
        "lead.tip": (p.lead_L, 0, 0),
        "lead.round_centre": (straight, 0, 0),
        "lead.side_a": (straight / 2, -p.lead_b / 2, 0),
        "lead.side_b": (straight / 2, p.lead_b / 2, 0),
        "lead.bottom": (straight / 2, 0, 0),
        "lead.top": (straight / 2, 0, p.frame_A3),
        "pad.x_min": (-p.pad_D2 / 2, 0, p.pad_t / 2),
        "pad.x_max": (p.pad_D2 / 2, 0, p.pad_t / 2),
        "pad.y_min": (0, -p.pad_E2 / 2, p.pad_t / 2),
        "pad.y_max": (0, p.pad_E2 / 2, p.pad_t / 2),
        "pad.notch_axis": (notch_x, notch_y, p.pad_t / 2),
        "pad.notch_wall": (notch_x + p.notch_R, notch_y, p.pad_t / 2),
    }
    assembly = {"body_1": ("body", Pos(0, 0, 0)), "pad_1": ("pad", pad_place)}
    assembly.update({f"lead_{n}": ("lead", place) for n, place in places.items()})
    return {"parts": parts, "datums": datums, "assembly": assembly}
