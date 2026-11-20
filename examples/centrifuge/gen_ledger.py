"""Writes evidence.yaml, params.yaml, checks.yaml and gaps.yaml for this project.

Run: python3 gen_ledger.py  (stdlib only; YAML written as JSON flow mappings).

Each value a released body settles is one row: the source param that cites the body. The
part is built in the body's frame, and its shape check, comparing the two whole, checks them.
"""

import json

HDR = "# Written by gen_ledger.py: edit that script, not this file.\n"


def j(x):
    return json.dumps(x, ensure_ascii=False)


# ------------------------------------------------------------------ what the released bodies settle
# Each part a released body ships is built in that body's frame and compared whole with it by
# one shape check, which checks every param citing the body: (param, body, value, what it is).
B, PL, RO = "body_step", "plate_step", "rotor_pcr325_step"
rows = [
    ('body_bore_d', B, 126, 'inner wall bore'),
    ('deck_t', B, 7, 'top deck thickness (along y)'),
    ('hub_hole_d', B, 44, 'central hole through the deck'),
    ('groove_di', B, 107, 'lid groove, inner wall'),
    ('groove_do', B, 123, 'lid groove, outer wall'),
    ('groove_depth', B, 5, 'lid groove depth to its flat floor (along y)'),
    ('groove_in_wall', B, 1.0, 'lid groove, straight part of the inner wall (along y)'),
    ('groove_out_wall', B, 1.1, 'lid groove, straight part of the outer wall (along y)'),
    ('arrow_depth', B, 0.2, 'spin-direction arrow recess depth (along y)'),
    ('arrow_d_in', B, 74.266494, 'arrow band, inner edge'),
    ('arrow_d_out', B, 78.266494, 'arrow band, outer edge'),
    ('arrow_tip_x', B, 2, 'arrow head tip, past the axis plane (along x)'),
    ('arrow_base_x', B, 2, 'arrow head base, before the axis plane (along x)'),
    ('arrow_z0', B, 36.0, 'arrow head base, inner corner (along z)'),
    ('arrow_z1', B, 40.2, 'arrow head base, outer corner (along z)'),
    ('fan_hole_d', B, 4, 'fan screw holes in the deck'),
    ('fan_hole_pcd', B, 100.8, 'fan screw holes, opposite pair'),
    ('boss_pcd', B, 116, 'screw bosses, opposite pair'),
    ('boss_angle', B, 21.756866, 'screw boss angle from +X'),
    ('boss_d', B, 10, 'screw boss'),
    ('boss_hole_d', B, 3.2, 'screw boss tapping hole'),
    ('boss_hole_depth', B, 15, 'screw boss hole depth (along y)'),
    ('boss_cone_drop', B, 8.6, 'boss top cone meets the wall (along y)'),
    ('boss_cone_open', B, 135, 'boss top cone against the wall'),
    ('boss_flat', B, 18.5, 'boss top flat (along y)'),
    ('rocker_p1x', B, 50.25184, 'main-switch cut-out, outer corner P1 (along x)'),
    ('rocker_p1z', B, 41.228055, 'main-switch cut-out, outer corner P1 (along z)'),
    ('rocker_p2x', B, 48.830544, 'main-switch cut-out, inner corner P2 (along x)'),
    ('rocker_p2z', B, 39.806758, 'main-switch cut-out, inner corner P2 (along z)'),
    ('rocker_w', B, 13.0, 'main-switch cut-out width'),
    ('rocker_top', B, 7.395837, 'main-switch cut-out, top below the deck top (along y)'),
    ('rocker_h', B, 19.0, 'main-switch cut-out height (along y)'),
    ('dc_q1x', B, 45.042935, 'DC socket hole axis, point Q1 (along x)'),
    ('dc_q1z', B, 46.17384, 'DC socket hole axis, point Q1 (along z)'),
    ('dc_q2x', B, 44.335828, 'DC socket hole axis, point Q2 (along x)'),
    ('dc_q2z', B, 45.466733, 'DC socket hole axis, point Q2 (along z)'),
    ('dc_y', B, 15.53615, 'DC socket hole axis below the top (along y)'),
    ('dc_d', B, 8.5, 'DC socket hole'),
    ('slot_c1x', B, 37.550742, 'lid-switch slot, corner C1 (along x)'),
    ('slot_c1z', B, 39.804363, 'lid-switch slot, corner C1 (along z)'),
    ('slot_c2x', B, 42.147008, 'lid-switch slot, corner C2 (along x)'),
    ('slot_c2z', B, 43.661088, 'lid-switch slot, corner C2 (along z)'),
    ('slot_len', B, 12.0, 'lid-switch slot length'),
    ('plate_d', PL, 130, 'bottom plate rim'),
    ('plate_t', PL, 1, 'bottom plate thickness (along y)'),
    ('foot_d', PL, 10, 'foot'),
    ('foot_h', PL, 3, 'foot height (along y)'),
    ('foot_pcd', PL, 116, 'feet, opposite pair'),
    ('foot_angle', PL, 34.369022, 'foot angle from +X'),
    ('plate_hole_d', PL, 3.5, 'screw clearance hole'),
    ('rotor_wall', RO, 2, 'slab thickness (along y)'),
    ('notch_h', RO, 5, 'notch height between tabs (along y)'),
    ('ledge_y', RO, 5.055472, 'hub ledge above the skirt bottom (along y)'),
    ('skirt_top_y', RO, 5.288, 'outer skirt height (along y)'),
    ('ledge_d', RO, 24.5, 'hub ledge inner edge'),
    ('cone_top_d', RO, 25.327142, 'outer cone meets the slab'),
    ('kink_y', RO, 24.988, 'cavity cone to tip kink (along y)'),
    ('slab_bot_y', RO, 28.988, 'slab underside (along y)'),
    ('top_y', RO, 38.988, 'overall height to the ridge (along y)'),
    ('slab_w', RO, 29.1, 'slab width'),
    ('holder_l', RO, 73.1, 'strip holder length'),
    ('holder_chamfer', RO, 3, 'strip holder end chamfer (along x)'),
    ('bend_span', RO, 54, 'slab length between the bends'),
    ('rotor_bend_open', RO, 135, 'holder against the slab'),
    ('ridge_l', RO, 13.1, 'roof ridge length'),
    ('ridge_w', RO, 2, 'roof ridge width'),
    ('hole_d', RO, 6.6, 'tube hole'),
    ('hole_in_span', RO, 9.0, 'innermost tube holes, axis to axis'),
    ('hole_out_span', RO, 63.02, 'outermost tube holes, axis to axis'),
    ('hole_pitch', RO, 9.003333, 'tube hole pitch'),
    ('hole_drop', RO, 3.878679, 'tube hole centre on the holder face, below the top (along y)'),
    ('tab_angle', RO, 15.746991, 'hub tab angular width'),
    ('tab_edge_z', RO, 2.963611, 'hub tab 0 edge, outer corner offset from the XY plane (along z)'),
    ("rotor_file_y", RO, 40.288, "rotor's skirt bottom below its file's origin, where the file places it"),
]

evidence, params, checks = [], {}, []
for param, body, value, what in rows:
    params[param] = {"basis": "source", "from": body, "value": value,
                     "interpretation": f"{what}, as the released body gives it"}

# ------------------------------------------------------------------ quotes and figure readings
quotes = [
    {"id": "P3-pcr325", "source": "paper", "page": 3, "locator": "Design files table, PCR strip 32.5 mm rotor",
     "quote": "Rotor – PCR strip – 32.5 mm Centrifuge rotor of PCR strips for 7 bladed fans with 32.5 mm hub diameter.",
     "values": {"hub_d": 32.5, "blades": 7}},
    {"id": "P3-fan", "source": "paper", "page": 3, "locator": "Bill of materials, PC fan",
     "quote": "PC fan 80 mm, 12 V computer fan with 7 blades", "values": {"w": 80}},
    {"id": "P4-screws", "source": "paper", "page": 4, "locator": "Bill of materials, bottom plate screws",
     "quote": "M3 * 10–12 mm metric screws 4", "values": {"d": 3, "L": 10, "n": 4}},
    {"id": "P11-mass", "source": "paper", "page": 11, "locator": "7.3 Safety notes",
     "quote": "low weight of the rotor (16 g)", "values": {"m": 16}},
    # not modelled
    {"id": "P3-lid-switch", "source": "paper", "page": 3, "locator": "Bill of materials, lid switch",
     "quote": "Hinge lever micro switch 6*9 mm", "values": {"w": 6, "l": 9}, "scope": "not-modeled",
     "reason": "electronics: the lid micro switch is not built; the body's slot for it, 6 x 12 mm to leave its lever room, is (slot_*)"},
    {"id": "P3-main-switch", "source": "paper", "page": 3, "locator": "Bill of materials, main switch",
     "quote": "Rocker switch 19*12.5 mm", "values": {"h": 19, "w": 12.5}, "scope": "not-modeled",
     "reason": "electronics: the rocker switch is not built; the body's cut-out for it, 19 x 13 mm to clear it, is (rocker_*)"},
    {"id": "P4-psu", "source": "paper", "page": 4, "locator": "Bill of materials, power supply",
     "quote": "12 V, 1 A DC power supply, 5.5 mm * 2.1 mm connector", "values": {"od": 5.5, "id": 2.1},
     "scope": "not-modeled", "reason": "electronics outside the device: the mains power supply"},
    {"id": "P4-dc", "source": "paper", "page": 4, "locator": "Bill of materials, DC socket",
     "quote": "DC socket 5.5 mm * 2.1 mm DC socket", "values": {"od": 5.5, "id": 2.1}, "scope": "not-modeled",
     "reason": "electronics: the DC socket is not built; the body's hole for it is (dc_*)"},
    {"id": "P4-lid", "source": "paper", "page": 4, "locator": "Bill of materials note, lid",
     "quote": "Its diameter is 116 mm", "values": {"d": 116}, "scope": "not-modeled",
     "reason": "the lid is a purchased food container resting in the body's groove; the target is the lid-off configuration"},
    # context
    {"id": "P1-fan", "source": "paper", "page": 1, "locator": "Abstract",
     "quote": "cheap off-the-shelf components (80 mm computer fan", "values": {"w": 80}, "scope": "context",
     "reason": "restates P3-fan"},
    {"id": "P4-fan-upcycle", "source": "paper", "page": 4, "locator": "Bill of materials note",
     "quote": "80 mm fans can be found in computer cases", "values": {"w": 80}, "scope": "context",
     "reason": "restates P3-fan"},
    {"id": "P7-hub-sizes", "source": "paper", "page": 7, "locator": "5.1.1 Printing the centrifuge rotor",
     "quote": "the two common sizes are 32.5 mm and 36.6 mm", "values": {"d325": 32.5, "d366": 36.6},
     "scope": "context", "reason": "restates P3-pcr325 for the 32.5 mm hub; 36.6 mm is the variant not modelled"},
    {"id": "P3-pcr366-row", "source": "paper", "page": 3, "locator": "Design files table, PCR strip 36.6 mm rotor",
     "quote": "Rotor – PCR strip – 36.6 mm Centrifuge rotor of PCR strips for 7 bladed fans with 32.5 mm hub diameter.",
     "values": {"name_d": 36.6, "hub_d": 32.5}, "scope": "context",
     "reason": "the 36.6 mm PCR-strip rotor, a variant not modelled; see conflict K1"},
    {"id": "P7-rotor-infill", "source": "paper", "page": 7, "locator": "5.1.1 Printing the centrifuge rotor",
     "quote": "the rotor was printed with 100 %", "values": {"infill": 100}, "scope": "context",
     "reason": "solid rotor: supports weighing it at the full PLA density in chk-rotor-mass"},
    {"id": "P9-pcr-radius", "source": "paper", "page": 9, "locator": "7.1 Testing operation and reliability",
     "quote": "The rotational radius of the innermost tubes of the PCR strip is also 4.4 cm.", "values": {"r": 4.4},
     "scope": "context",
     "reason": "radius of the tube tips, which depends on the PCR tubes' length; the tubes are not part of the device"},
    {"id": "P10-dims", "source": "paper", "page": 10, "locator": "Table 2, DIY column, Dimensions W*L*H (cm)",
     "quote": "13*13*10", "values": {"W": 13, "L": 13, "H": 10}, "scope": "context",
     "reason": "in cm, a unit printed only in the row header: W and L restate fig8-body-dims (130 mm); H includes the lid, not modelled"},
    {"id": "P9-m3", "source": "paper", "page": 9, "locator": "5.2 Assembling the centrifuge",
     "quote": "Attach the bottom plate with M3 screws", "scope": "context", "reason": "restates P4-screws"},
    {"id": "P2-strip", "source": "paper", "page": 2, "locator": "1. Hardware in context",
     "quote": "eight small, 200 ll tubes are connected", "values": {"n": "eight"}, "scope": "context",
     "reason": "a PCR strip of eight tubes: the holder's eight holes are the released rotor's (hole_*)"},
    # figure readings
    {"id": "fig8-body-dims", "source": "paper", "page": 8, "locator": "Fig. 8 right, Cura object list, AG_Centrifuge body",
     "image": "figures/crops/fig8-body-dims.png", "image_sha256": "7be75cac317dfd20852bd2cd466b86a29bac33f28a1e158ffbf22de3f835ae2d",
     "reading": "130.0 x 130.0 x 34.0 mm", "values": {"W": 130.0, "L": 130.0, "H": 34.0},
     "confirmed_by": "Vini Rezanejad"},
]
evidence = quotes + evidence

conflicts = [
    {"id": "K1", "evidence": ["P3-pcr366-row", "P7-hub-sizes"],
     "summary": "The design-file table describes the 36.6 mm PCR-strip rotor as for fans 'with 32.5 mm hub diameter'; its name and §5.1.1 give 36.6 mm.",
     "resolution": "A copy error in the 36.6 mm row, which concerns the variant not modelled. The modelled 32.5 mm PCR-strip rotor's own row (P3-pcr325) gives 32.5 mm, as does its released body, which the rotor's shape check compares with the rotor built from it."},
]

skipped_bodies = [
    {"source": "body_compat_step", "reason": "not part of the device built: the broader-lid-compatibility body, a variant for other lids (target: standard body)"},
    {"source": "arrows_step", "body": "arrows_step#1", "reason": "not part of the device: an optional coloured arrow inlay, printed separately (§5.1.2); the body's arrow recess is modelled"},
    {"source": "arrows_step", "body": "arrows_step#2", "reason": "not part of the device: an optional coloured arrow inlay, printed separately (§5.1.2); the body's arrow recess is modelled"},
    {"source": "rotor325_step", "reason": "six-tube rotor, a variant not modelled (target: PCR-strip rotor)"},
    {"source": "rotor366_step", "reason": "six-tube rotor for 36.6 mm hubs, a variant not modelled"},
    {"source": "rotor_pcr366_step", "reason": "PCR-strip rotor for 36.6 mm hubs, a variant not modelled"},
    {"source": "fit325_step", "reason": "a fit tester for the 32.5 mm hub, not part of the device"},
    {"source": "fit366_step", "reason": "a fit tester for the 36.6 mm hub, not part of the device"},
    {"source": "adapter05_step", "reason": "0.5 ml tube adapter, an accessory for the six-tube rotor not modelled"},
    {"source": "adapter02_step", "reason": "0.2 ml tube adapter, an accessory for the six-tube rotor not modelled"},
]

# ------------------------------------------------------------------ params with other bases
params.update({
    "body_d": {"basis": "source", "from": "fig8-body-dims.W", "interpretation": "body outer diameter: Cura's X extent of the body"},
    "body_h": {"basis": "source", "from": "fig8-body-dims.H", "interpretation": "body height, deck top to wall bottom: Cura's Z extent of the body as printed upside down"},
    "boss_cone_angle": {"basis": "derived", "expr": "180 - boss_cone_open", "interpretation": "boss top cone from the vertical wall"},
    "rotor_slope": {"basis": "derived", "expr": "180 - rotor_bend_open", "interpretation": "rise of the strip holders above the slab; read also for the roof hips and the cavity's flare and tip, which the shape check confirms share it"},
    "hole_x_in": {"basis": "derived", "expr": "hole_in_span / 2", "interpretation": "innermost holes symmetric about the rotor's YZ plane"},
    "hole_x_out": {"basis": "derived", "expr": "hole_out_span / 2", "interpretation": "outermost holes symmetric about the rotor's YZ plane"},
    "hub_d": {"basis": "source", "from": "P3-pcr325.hub_d", "interpretation": "rotor skirt bore = fan hub outer diameter (snug press fit, §5.1.1)"},
    "n_tabs": {"basis": "source", "from": "P3-pcr325.blades", "interpretation": "one hub tab per fan blade gap: seven tabs on the rotor skirt"},
    "fan_w": {"basis": "source", "from": "P3-fan.w", "interpretation": "fan frame side, square"},
    "screw_d": {"basis": "source", "from": "P4-screws.d", "interpretation": "M3 nominal diameter; shank only, no head or thread"},
    "screw_l": {"basis": "source", "from": "P4-screws.L", "interpretation": "the stated range's shorter end, 10 mm"},
    "screw_n": {"basis": "source", "from": "P4-screws.n", "interpretation": "four screws, one per body boss; the plate's four feet follow the same count"},
    "screw_fit": {"basis": "derived", "expr": "(boss_hole_d - screw_d) / 2", "interpretation": "the gap around each screw's shank in its boss, whose hole the released body draws over the screw's diameter: the thread that holds it there is not modelled"},
    "fan_t": {"basis": "proposed", "value": 25, "rationale": "the common 80 x 80 x 25 mm case fan; the paper gives no thickness", "gap": "G-fan"},
    "fan_bore_d": {"basis": "proposed", "value": 76, "rationale": "blade bore of a typical 80 mm fan frame", "gap": "G-fan"},
    "fan_rot": {"basis": "proposed", "value": 45, "rationale": "fan frame turned so its corner screw holes meet the deck's four holes on the axes", "gap": "G-fan"},
    "fan_top_y": {"basis": "derived", "expr": "-deck_t", "gap": "G-seat", "interpretation": "fan screwed up against the deck underside (Fig. 9)"},
    "rotor_seat_y": {"basis": "derived", "expr": "fan_top_y - ledge_y", "gap": "G-seat", "interpretation": "rotor pressed on until its hub ledge sits on the fan hub, whose top is flush with the fan frame's"},
    "pla_density": {"basis": "proposed", "value": 0.00124, "rationale": "typical PLA density, 1.24 g/cm³, for a rotor printed at 100 % infill (P7-rotor-infill)", "gap": "G-pla"},
})

gaps = [
    {"id": "G-fan", "question": "What are the 80 mm fan's thickness, blade-bore diameter and screw-hole layout (AKYGA AW-8A-BK datasheet)?", "ask": "datasheet"},
    {"id": "G-seat", "question": "Is the fan's hub flush with its frame's top face, so that the rotor's hub ledge sits level with the deck underside?", "ask": "measure"},
    {"id": "G-pla", "question": "What does the PLA used for the rotor weigh per cm³ as printed?", "ask": "measure"},
]

# ------------------------------------------------------------------ remaining checks
checks += [
    {"id": "body-envelope", "kind": "bbox", "part": "body", "evidence": "fig8-body-dims",
     "axes": {"W": "x", "L": "z", "H": "y"}, "interpretation": "Cura's X x Y x Z read as the body's X x Z x Y"},
    {"id": "hub-bore", "kind": "diameter", "at": "rotor.hub_bore", "evidence": "P3-pcr325", "key": "hub_d"},
    {"id": "tab-pitch", "kind": "angle", "between": ["rotor.tab_e1", "rotor.axis_low", "rotor.tab1_e1"],
     "expect": "360 / P3-pcr325.blades", "interpretation": "one tab per blade: adjacent tabs one blade pitch apart"},
    {"id": "fan-w-x", "kind": "bbox", "part": "fan_frame", "evidence": "P3-fan", "axes": {"w": "x"}},
    {"id": "fan-w-z", "kind": "bbox", "part": "fan_frame", "evidence": "P3-fan", "axes": {"w": "z"}},
    {"id": "screw-d", "kind": "diameter", "at": "screw.wall", "evidence": "P4-screws", "key": "d"},
    {"id": "screw-l", "kind": "bbox", "part": "screw", "evidence": "P4-screws", "axes": {"L": "y"}},
    {"id": "screw-count", "kind": "count", "part": "screw", "evidence": "P4-screws", "key": "n"},
    {"id": "rotor-mass", "kind": "mass", "parts": ["rotor"], "density": "pla_density", "evidence": "P11-mass",
     "key": "m", "tol_rel": 0.05,
     "interpretation": "'the rotor' read as the modelled PCR-strip rotor, printed solid; the paper does not say which rotor weighs 16 g"},
    {"id": "clear", "kind": "interference"},
    {"id": "body-shape", "kind": "shape", "part": "body", "body": "body_step"},
    {"id": "plate-shape", "kind": "shape", "part": "plate", "body": "plate_step"},
    {"id": "rotor-shape", "kind": "shape", "part": "rotor", "body": "rotor_pcr325_step"},
]


def write(path, text):
    with open(path, "w") as f:
        f.write(HDR + text)


def block(name, items):
    if not items:
        return f"{name}: []\n"
    return f"{name}:\n" + "".join(f"  - {j(i)}\n" for i in items)


for sb_ in skipped_bodies:
    sb_.setdefault("body", sb_["source"])
skips = json.load(open("skips.json")) if __import__("os").path.exists("skips.json") else []
write("evidence.yaml",
      block("evidence", evidence)
      + block("skipped", skipped_bodies + skips)
      + block("conflicts", conflicts))
write("params.yaml", "params:\n" + "".join(f"  {k}: {j(v)}\n" for k, v in params.items()))
write("checks.yaml", block("checks", checks))
write("gaps.yaml", block("gaps", gaps))
print(len(evidence), "evidence;", len(params), "params;", len(checks), "checks")
