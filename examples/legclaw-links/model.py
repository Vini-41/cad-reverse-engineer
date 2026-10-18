"""Three LegClaw linkages as straight bars with rounded ends and two pin holes.

Envelopes come from Table S2; the rounded-bar form, pin size and pitch are proposed.
"""

from build123d import *  # noqa: F403


def bar(length, height, thickness, pitch, pin_d):
    """Slot-shaped bar in the XZ plane, thickness along Y, centred on the origin."""
    with BuildPart() as part:
        with BuildSketch(Plane.XZ):
            SlotOverall(length, height)
        extrude(amount=thickness / 2, both=True)
        with Locations((-pitch / 2, 0, 0), (pitch / 2, 0, 0)):
            Cylinder(pin_d / 2, thickness, rotation=(90, 0, 0), mode=Mode.SUBTRACT)
    return part.part


def build(p):
    parts = {
        "compression_linkage": bar(p.comp_L, p.comp_H, p.comp_W, p.comp_pitch, p.pin_d),
        "bent_linkage": bar(p.bent_L, p.bent_H, p.bent_W, p.bent_pitch, p.pin_d),
        "linkage": bar(p.link_L, p.link_H, p.link_W, p.link_pitch, p.pin_d),
    }
    datums = {}
    for name, pitch in (("compression_linkage", p.comp_pitch), ("bent_linkage", p.bent_pitch),
                        ("linkage", p.link_pitch)):
        datums[f"{name}.pin_a"] = (-pitch / 2, 0, 0)
        datums[f"{name}.pin_b"] = (pitch / 2, 0, 0)
    z = 0
    assembly = {}
    for name in parts:
        assembly[name] = (name, Location((0, 0, z)))
        z -= p.comp_H + p.layout_gap
    return {"parts": parts, "datums": datums, "assembly": assembly}
