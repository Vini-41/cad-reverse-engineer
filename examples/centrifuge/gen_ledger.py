"""Writes evidence.yaml, params.yaml, checks.yaml and gaps.yaml for this project.

Run: python3 gen_ledger.py  (stdlib only; YAML written as JSON flow mappings).

Each released-geometry probe is one row: the probe (on the released body's datums, in the
file's frame), the source param that takes its value, and the check that compares the
built part's matching datums with it. Datum coordinates on the released bodies are worked
out here from the probed design values, as the model works its own out from the params.
"""

import json
import math

HDR = "# Written by gen_ledger.py: edit that script, not this file.\n"


def j(x):
    return json.dumps(x, ensure_ascii=False)


def polar(r, deg, y):
    return [round(r * math.cos(math.radians(deg)), 6), y, round(r * math.sin(math.radians(deg)), 6)]


def rnd(v):
    return [round(c, 6) for c in v]


# ------------------------------------------------------------------ released-body datums
datums = {}

# body (file frame = model frame)
R, H, Ri, T = 65, 34, 63, 7
gi, go, gd, gin, gout = 53.5, 61.5, 5, 1.0, 1.1
a_in, a_out = 37.133247, 39.133247
a_mid = (a_in + a_out) / 2
ad = 0.2
th = 21.756866
Rb, rb, bh, flat, drop = 58, 5, 1.6, 18.5, 8.6
yb = -(H + flat) / 2
u = (math.cos(math.radians(th)), math.sin(math.radians(th)))
B = "body_step"
datums.update({
    f"{B}.top": [-(R + go) / 2, 0, 0],
    f"{B}.bottom": [-(R + Ri) / 2, -H, 0],
    f"{B}.deck_under": [-(Ri + 22) / 2, -T, 0],
    f"{B}.bore_wall": [-Ri, -(H + T) / 2, 0],
    f"{B}.hole_wall": [-22, -T / 2, 0],
    f"{B}.axis_top": [0, -T / 2, 0],
    f"{B}.groove_in": [-gi, -gin / 2, 0],
    f"{B}.groove_out": [-go, -gout / 2, 0],
    f"{B}.groove_in_edge": [-gi, -gin, 0],
    f"{B}.groove_out_edge": [-go, -gout, 0],
    f"{B}.groove_floor": [-(gi + (gd - gin) + go - (gd - gout)) / 2, -gd, 0],
    f"{B}.arrow_floor": rnd([-a_mid / 2, -ad, math.sqrt(a_mid ** 2 - (a_mid / 2) ** 2)]),
    f"{B}.arrow_in": rnd([-a_in / 2, -ad / 2, math.sqrt(a_in ** 2 - (a_in / 2) ** 2)]),
    f"{B}.arrow_out": rnd([-a_out / 2, -ad / 2, math.sqrt(a_out ** 2 - (a_out / 2) ** 2)]),
    f"{B}.arrow_tip": rnd([2, -ad / 2, a_mid]),
    f"{B}.arrow_base": rnd([-2, -ad / 2, (36.0 + math.sqrt(a_in ** 2 - 4)) / 2]),
    f"{B}.arrow_z0": [-2, -ad / 2, 36.0],
    f"{B}.arrow_z1": [-2, -ad / 2, 40.2],
    f"{B}.fan_hole_p": [50.4, -T / 2, 0],
    f"{B}.fan_hole_n": [-50.4, -T / 2, 0],
    f"{B}.fan_hole_wall": [-50.4 + 2, -T / 2, 0],
    f"{B}.axis_low": [0, yb, 0],
    f"{B}.wall0": [Ri, yb, 0],
    f"{B}.boss1": polar(Rb, th, yb),
    f"{B}.boss3": polar(Rb, th + 180, yb),
    f"{B}.boss_wall": polar(Rb - rb, th, yb),
    f"{B}.boss_hole_wall": polar(Rb + bh, th, -H + 15 / 2),
    f"{B}.boss_hole_top": polar(Rb, th, -H + 15),
    f"{B}.cone_wall": polar(Ri, th, -drop),
    f"{B}.cone_up": polar(Ri, th, -(drop + T) / 2),
    f"{B}.cone_b": polar(Ri - 2, th, -drop - 2),
    f"{B}.boss_flat": polar(Rb - rb, th, -flat),
})
yr = -7.395837 - 19 / 2
p1, p2 = (-50.25184, 41.228055), (-48.830544, 39.806758)
dn = math.hypot(p2[0] - p1[0], p2[1] - p1[1])
dx, dz = (p2[0] - p1[0]) / dn, (p2[1] - p1[1]) / dn
nx, nz = -dz, dx
cx, cz = (p1[0] + p2[0]) / 2 + 6.5 * nx, (p1[1] + p2[1]) / 2 + 6.5 * nz
datums.update({
    f"{B}.rocker_p1": rnd([p1[0], yr, p1[1]]),
    f"{B}.rocker_p2": rnd([p2[0], yr, p2[1]]),
    f"{B}.rocker_p2w": rnd([p2[0] + 13 * nx, yr, p2[1] + 13 * nz]),
    f"{B}.rocker_top": rnd([cx, -7.395837, cz]),
    f"{B}.rocker_bottom": rnd([cx, -7.395837 - 19, cz]),
    f"{B}.axis_mid": rnd([0, yr, 0]),
    f"{B}.dc_q1": [-45.042935, -15.53615, -46.17384],
    f"{B}.dc_q2": [-44.335828, -15.53615, -45.466733],
    f"{B}.dc_wall": [-45.042935, -15.53615 + 4.25, -46.17384],
    f"{B}.slot_c1": [37.550742, -T, 39.804363],
    f"{B}.slot_c2": [42.147008, -T, 43.661088],
    f"{B}.slot_c3": [45.264193, -T, 30.611829],
})

# bottom plate (file frame = model frame shifted by -34 in y)
PL, oy = "plate_step", -34
fa = 34.369022
datums.update({
    f"{PL}.rim": [-65, oy - 0.5, 0],
    f"{PL}.top": [-(65 + 58) / 2, oy, 0],
    f"{PL}.bottom": [-(65 + 58) / 2, oy - 1, 0],
    f"{PL}.foot_p": polar(58, fa, oy - 2.5),
    f"{PL}.foot_n": polar(58, fa + 180, oy - 2.5),
    f"{PL}.foot_wall": [polar(58, fa, 0)[0] + 5, oy - 2.5, polar(58, fa, 0)[2]],
    f"{PL}.foot_bottom": polar(58, fa, oy - 4),
    f"{PL}.foot_end": polar(58, fa, oy - 1),
    f"{PL}.ref0": [58, oy - 1, 0],
    f"{PL}.centre_bottom": [0, oy - 1, 0],
    f"{PL}.hole_wall": polar(58 + 1.75, th, oy - 0.5),
    f"{PL}.hole": polar(58, th, oy - 0.5),
})

# rotor (file frame = model frame shifted by -40.288 in y)
RO, ry = "rotor_pcr325_step", -40.288
ri, w, ro = 16.25, 2, 18.25
ta, phi0 = 15.746991, -9.345627
pitch_t = 360 / 7
rmid = (ri + ro) / 2
zt, top, sb = 27, -1.3, -11.3
yc = top - 3.878679
zc = zt + (yc - (sb + w))
ym, zm = yc - w / 2 * math.sqrt(0.5), zc + w / 2 * math.sqrt(0.5)
datums.update({
    f"{RO}.tab_bottom": polar(rmid, phi0 - ta / 2, ry),
    f"{RO}.notch_roof": polar(rmid, phi0 - (pitch_t + ta) / 2, ry + 5),
    f"{RO}.ledge": [(12.25 + ri) / 2, -35.232528, 0],
    f"{RO}.skirt_top": [ro, -35.0, 0],
    f"{RO}.ledge_p": [12.25, -35.232528, 0],
    f"{RO}.ledge_n": [-12.25, -35.232528, 0],
    f"{RO}.cone_top_p": [12.663571, sb, 0],
    f"{RO}.cone_top_n": [-12.663571, sb, 0],
    f"{RO}.kink": [11.551618, -15.3, 0],
    f"{RO}.slab_bot": [0, sb, zt],
    f"{RO}.bend_p": [0, sb + w, zt],
    f"{RO}.bend_n": [0, sb + w, -zt],
    f"{RO}.slab_top_mid": [0, sb + w, 18],
    f"{RO}.holder_top_edge": [0, top, 35],
    f"{RO}.ridge": [0, top, 0],
    f"{RO}.ridge_xp": [6.55, top, 0],
    f"{RO}.ridge_xn": [-6.55, top, 0],
    f"{RO}.ridge_zp": [0, top, 1],
    f"{RO}.ridge_zn": [0, top, -1],
    f"{RO}.slab_side_p": [14.55, sb + w / 2, zt],
    f"{RO}.slab_side_n": [-14.55, sb + w / 2, zt],
    f"{RO}.end_p": [36.55, -4.3, 32.0],
    f"{RO}.end_n": [-36.55, -4.3, 32.0],
    f"{RO}.cut_corner": [33.55, top, 35.0],
    f"{RO}.hole_in_p": rnd([4.5, ym, zm]),
    f"{RO}.hole_in_n": rnd([-4.5, ym, zm]),
    f"{RO}.hole_2_p": rnd([4.5 + 9.003333, ym, zm]),
    f"{RO}.hole_out_p": rnd([31.51, ym, zm]),
    f"{RO}.hole_out_n": rnd([-31.51, ym, zm]),
    f"{RO}.hole_wall": rnd([4.5 + 3.3, ym, zm]),
    f"{RO}.hole_top": rnd([4.5, yc, zc]),
    f"{RO}.axis_low": [0, ry + 2.5, 0],
    f"{RO}.tab_e1": polar(rmid, phi0, ry + 2.5),
    f"{RO}.tab_e2": polar(rmid, phi0 - ta, ry + 2.5),
    f"{RO}.tab_corner": polar(ro, phi0, ry),
    f"{RO}.hub_bore": polar(ri, phi0 - ta / 2, ry + 2.5),
})
datums = {k: [round(c, 6) for c in v] for k, v in datums.items()}

# ------------------------------------------------------------------ probe rows
# (evidence id, body, kind, datum features, along, value, param, part, locator / interpretation)
rows = [
    # body
    ("B-bore", B, "diameter", ["bore_wall"], None, 126, "body_bore_d", "body", "inner wall bore"),
    ("B-deck", B, "distance", ["top", "deck_under"], "y", 7, "deck_t", "body", "top deck thickness"),
    ("B-hole", B, "diameter", ["hole_wall"], None, 44, "hub_hole_d", "body", "central hole through the deck"),
    ("B-groove-in", B, "diameter", ["groove_in"], None, 107, "groove_di", "body", "lid groove, inner wall"),
    ("B-groove-out", B, "diameter", ["groove_out"], None, 123, "groove_do", "body", "lid groove, outer wall"),
    ("B-groove-depth", B, "distance", ["top", "groove_floor"], "y", 5, "groove_depth", "body",
     "lid groove depth to its flat floor"),
    ("B-groove-in-wall", B, "distance", ["top", "groove_in_edge"], "y", 1.0, "groove_in_wall", "body",
     "lid groove, straight part of the inner wall"),
    ("B-groove-out-wall", B, "distance", ["top", "groove_out_edge"], "y", 1.1, "groove_out_wall", "body",
     "lid groove, straight part of the outer wall"),
    ("B-arrow-depth", B, "distance", ["top", "arrow_floor"], "y", 0.2, "arrow_depth", "body",
     "spin-direction arrow recess depth"),
    ("B-arrow-in", B, "diameter", ["arrow_in"], None, 74.266494, "arrow_d_in", "body", "arrow band, inner edge"),
    ("B-arrow-out", B, "diameter", ["arrow_out"], None, 78.266494, "arrow_d_out", "body", "arrow band, outer edge"),
    ("B-arrow-tip", B, "distance", ["axis_top", "arrow_tip"], "x", 2, "arrow_tip_x", "body",
     "arrow head tip, past the axis plane"),
    ("B-arrow-base", B, "distance", ["axis_top", "arrow_base"], "x", 2, "arrow_base_x", "body",
     "arrow head base, before the axis plane"),
    ("B-arrow-z0", B, "distance", ["axis_top", "arrow_z0"], "z", 36.0, "arrow_z0", "body", "arrow head base, inner corner"),
    ("B-arrow-z1", B, "distance", ["axis_top", "arrow_z1"], "z", 40.2, "arrow_z1", "body", "arrow head base, outer corner"),
    ("B-fan-hole", B, "diameter", ["fan_hole_wall"], None, 4, "fan_hole_d", "body", "fan screw holes in the deck"),
    ("B-fan-pcd", B, "distance", ["fan_hole_p", "fan_hole_n"], None, 100.8, "fan_hole_pcd", "body",
     "fan screw holes, opposite pair"),
    ("B-boss-pcd", B, "distance", ["boss1", "boss3"], None, 116, "boss_pcd", "body", "screw bosses, opposite pair"),
    ("B-boss-angle", B, "angle", ["wall0", "axis_low", "boss1"], None, 21.756866, "boss_angle", "body",
     "screw boss angle from +X"),
    ("B-boss-d", B, "diameter", ["boss_wall"], None, 10, "boss_d", "body", "screw boss"),
    ("B-boss-hole", B, "diameter", ["boss_hole_wall"], None, 3.2, "boss_hole_d", "body", "screw boss tapping hole"),
    ("B-boss-hole-depth", B, "distance", ["bottom", "boss_hole_top"], "y", 15, "boss_hole_depth", "body",
     "screw boss hole depth"),
    ("B-cone-drop", B, "distance", ["top", "cone_wall"], "y", 8.6, "boss_cone_drop", "body",
     "boss top cone meets the wall"),
    ("B-cone-open", B, "angle", ["cone_up", "cone_wall", "cone_b"], None, 135, "boss_cone_open", "body",
     "boss top cone against the wall"),
    ("B-boss-flat", B, "distance", ["top", "boss_flat"], "y", 18.5, "boss_flat", "body", "boss top flat"),
    ("B-rocker-p1x", B, "distance", ["axis_mid", "rocker_p1"], "x", 50.25184, "rocker_p1x", "body",
     "main-switch cut-out, outer corner P1"),
    ("B-rocker-p1z", B, "distance", ["axis_mid", "rocker_p1"], "z", 41.228055, "rocker_p1z", "body",
     "main-switch cut-out, outer corner P1"),
    ("B-rocker-p2x", B, "distance", ["axis_mid", "rocker_p2"], "x", 48.830544, "rocker_p2x", "body",
     "main-switch cut-out, inner corner P2"),
    ("B-rocker-p2z", B, "distance", ["axis_mid", "rocker_p2"], "z", 39.806758, "rocker_p2z", "body",
     "main-switch cut-out, inner corner P2"),
    ("B-rocker-w", B, "distance", ["rocker_p2", "rocker_p2w"], None, 13.0, "rocker_w", "body",
     "main-switch cut-out width"),
    ("B-rocker-top", B, "distance", ["top", "rocker_top"], "y", 7.395837, "rocker_top", "body",
     "main-switch cut-out, top below the deck top"),
    ("B-rocker-h", B, "distance", ["rocker_top", "rocker_bottom"], "y", 19.0, "rocker_h", "body",
     "main-switch cut-out height"),
    ("B-dc-q1x", B, "distance", ["axis_mid", "dc_q1"], "x", 45.042935, "dc_q1x", "body", "DC socket hole axis, point Q1"),
    ("B-dc-q1z", B, "distance", ["axis_mid", "dc_q1"], "z", 46.17384, "dc_q1z", "body", "DC socket hole axis, point Q1"),
    ("B-dc-q2x", B, "distance", ["axis_mid", "dc_q2"], "x", 44.335828, "dc_q2x", "body", "DC socket hole axis, point Q2"),
    ("B-dc-q2z", B, "distance", ["axis_mid", "dc_q2"], "z", 45.466733, "dc_q2z", "body", "DC socket hole axis, point Q2"),
    ("B-dc-y", B, "distance", ["top", "dc_q1"], "y", 15.53615, "dc_y", "body", "DC socket hole axis below the top"),
    ("B-dc-d", B, "diameter", ["dc_wall"], None, 8.5, "dc_d", "body", "DC socket hole"),
    ("B-slot-c1x", B, "distance", ["axis_top", "slot_c1"], "x", 37.550742, "slot_c1x", "body", "lid-switch slot, corner C1"),
    ("B-slot-c1z", B, "distance", ["axis_top", "slot_c1"], "z", 39.804363, "slot_c1z", "body", "lid-switch slot, corner C1"),
    ("B-slot-c2x", B, "distance", ["axis_top", "slot_c2"], "x", 42.147008, "slot_c2x", "body", "lid-switch slot, corner C2"),
    ("B-slot-c2z", B, "distance", ["axis_top", "slot_c2"], "z", 43.661088, "slot_c2z", "body", "lid-switch slot, corner C2"),
    ("B-slot-len", B, "distance", ["slot_c1", "slot_c3"], None, 12.0, "slot_len", "body", "lid-switch slot length"),
    # plate
    ("P-d", PL, "diameter", ["rim"], None, 130, "plate_d", "plate", "bottom plate rim"),
    ("P-t", PL, "distance", ["top", "bottom"], "y", 1, "plate_t", "plate", "bottom plate thickness"),
    ("P-foot-d", PL, "diameter", ["foot_wall"], None, 10, "foot_d", "plate", "foot"),
    ("P-foot-h", PL, "distance", ["bottom", "foot_bottom"], "y", 3, "foot_h", "plate", "foot height"),
    ("P-foot-pcd", PL, "distance", ["foot_p", "foot_n"], None, 116, "foot_pcd", "plate", "feet, opposite pair"),
    ("P-foot-angle", PL, "angle", ["ref0", "centre_bottom", "foot_end"], None, 34.369022, "foot_angle", "plate",
     "foot angle from +X"),
    ("P-hole-d", PL, "diameter", ["hole_wall"], None, 3.5, "plate_hole_d", "plate", "screw clearance hole"),
    # rotor
    ("R-wall", RO, "distance", ["slab_bot", "bend_p"], "y", 2, "rotor_wall", "rotor", "slab thickness"),
    ("R-notch", RO, "distance", ["tab_bottom", "notch_roof"], "y", 5, "notch_h", "rotor", "notch height between tabs"),
    ("R-ledge", RO, "distance", ["tab_bottom", "ledge"], "y", 5.055472, "ledge_y", "rotor",
     "hub ledge above the skirt bottom"),
    ("R-skirt-top", RO, "distance", ["tab_bottom", "skirt_top"], "y", 5.288, "skirt_top_y", "rotor",
     "outer skirt height"),
    ("R-ledge-d", RO, "distance", ["ledge_p", "ledge_n"], None, 24.5, "ledge_d", "rotor", "hub ledge inner edge"),
    ("R-cone-top-d", RO, "distance", ["cone_top_p", "cone_top_n"], None, 25.327142, "cone_top_d", "rotor",
     "outer cone meets the slab"),
    ("R-kink", RO, "distance", ["tab_bottom", "kink"], "y", 24.988, "kink_y", "rotor", "cavity cone to tip kink"),
    ("R-slab-bot", RO, "distance", ["tab_bottom", "slab_bot"], "y", 28.988, "slab_bot_y", "rotor", "slab underside"),
    ("R-top", RO, "distance", ["tab_bottom", "ridge"], "y", 38.988, "top_y", "rotor", "overall height to the ridge"),
    ("R-slab-w", RO, "distance", ["slab_side_p", "slab_side_n"], None, 29.1, "slab_w", "rotor", "slab width"),
    ("R-holder-l", RO, "distance", ["end_p", "end_n"], None, 73.1, "holder_l", "rotor", "strip holder length"),
    ("R-chamfer", RO, "distance", ["cut_corner", "end_p"], "x", 3, "holder_chamfer", "rotor", "strip holder end chamfer"),
    ("R-bend-span", RO, "distance", ["bend_p", "bend_n"], None, 54, "bend_span", "rotor",
     "slab length between the bends"),
    ("R-bend-open", RO, "angle", ["slab_top_mid", "bend_p", "holder_top_edge"], None, 135, "rotor_bend_open", "rotor",
     "holder against the slab"),
    ("R-ridge-l", RO, "distance", ["ridge_xp", "ridge_xn"], None, 13.1, "ridge_l", "rotor", "roof ridge length"),
    ("R-ridge-w", RO, "distance", ["ridge_zp", "ridge_zn"], None, 2, "ridge_w", "rotor", "roof ridge width"),
    ("R-hole-d", RO, "diameter", ["hole_wall"], None, 6.6, "hole_d", "rotor", "tube hole"),
    ("R-hole-in", RO, "distance", ["hole_in_p", "hole_in_n"], None, 9.0, "hole_in_span", "rotor",
     "innermost tube holes, axis to axis"),
    ("R-hole-out", RO, "distance", ["hole_out_p", "hole_out_n"], None, 63.02, "hole_out_span", "rotor",
     "outermost tube holes, axis to axis"),
    ("R-hole-pitch", RO, "distance", ["hole_in_p", "hole_2_p"], None, 9.003333, "hole_pitch", "rotor",
     "tube hole pitch"),
    ("R-hole-drop", RO, "distance", ["ridge", "hole_top"], "y", 3.878679, "hole_drop", "rotor",
     "tube hole centre on the holder face, below the top"),
    ("R-tab-angle", RO, "angle", ["tab_e1", "axis_low", "tab_e2"], None, 15.746991, "tab_angle", "rotor",
     "hub tab angular width"),
    ("R-tab-edge", RO, "distance", ["axis_low", "tab_corner"], "z", 2.963611, "tab_edge_z", "rotor",
     "hub tab 0 edge, outer corner offset from the XY plane"),
]

evidence, params, checks = [], {}, []
for eid, body, kind, feats, along, value, param, part, loc in rows:
    key = "d" if kind == "diameter" else ("a" if kind == "angle" else "v")
    ev = {"id": eid, "source": body, "locator": f"released body, {loc}", "probe": kind}
    if kind == "diameter":
        ev["at"] = f"{body}.{feats[0]}"
    else:
        ev["between"] = [f"{body}.{f}" for f in feats]
    if along:
        ev["along"] = along
    ev["values"] = {key: value}
    evidence.append(ev)
    params[param] = {"basis": "source", "from": f"{eid}.{key}",
                     "interpretation": f"{loc}, as the released body gives it" + (f" (along {along})" if along else "")}
    ck = {"id": f"chk-{eid}", "kind": kind}
    if kind == "diameter":
        ck["at"] = f"{part}.{feats[0]}"
    else:
        ck["between"] = [f"{part}.{f}" for f in feats]
    if along:
        ck["along"] = along
    ck.update({"evidence": eid, "key": key})
    checks.append(ck)

# context probe: the released rotor's hub bore restates the paper's 32.5 mm
evidence.append({"id": "R-hub-bore", "source": RO, "locator": "released body, hub skirt bore", "probe": "diameter",
                 "at": f"{RO}.hub_bore", "values": {"d": 32.5}, "scope": "context",
                 "reason": "restates P3-pcr325 (hub diameter 32.5 mm)"})

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
     "reason": "electronics: the lid micro switch is not built; the body's slot for it is (B-slot-*)"},
    {"id": "P3-main-switch", "source": "paper", "page": 3, "locator": "Bill of materials, main switch",
     "quote": "Rocker switch 19*12.5 mm", "values": {"h": 19, "w": 12.5}, "scope": "not-modeled",
     "reason": "electronics: the rocker switch is not built; the body's cut-out for it is (B-rocker-*)"},
    {"id": "P4-psu", "source": "paper", "page": 4, "locator": "Bill of materials, power supply",
     "quote": "12 V, 1 A DC power supply, 5.5 mm * 2.1 mm connector", "values": {"od": 5.5, "id": 2.1},
     "scope": "not-modeled", "reason": "electronics outside the device: the mains power supply"},
    {"id": "P4-dc", "source": "paper", "page": 4, "locator": "Bill of materials, DC socket",
     "quote": "DC socket 5.5 mm * 2.1 mm DC socket", "values": {"od": 5.5, "id": 2.1}, "scope": "not-modeled",
     "reason": "electronics: the DC socket is not built; the body's hole for it is (B-dc-*)"},
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
     "reason": "a PCR strip of eight tubes: the holder's eight holes are probed (R-hole-*)"},
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
     "resolution": "A copy error in the 36.6 mm row, which concerns the variant not modelled. The modelled 32.5 mm PCR-strip rotor's own row (P3-pcr325) and its released body (R-hub-bore) agree on 32.5 mm."},
    {"id": "K2", "evidence": ["P3-main-switch", "B-rocker-w"],
     "summary": "The rocker switch is listed as 19*12.5 mm; the body's cut-out for it is 19 x 13 mm.",
     "resolution": "Different objects: 12.5 mm is the purchased switch (not built), 13 mm the cut-out that clears it. The model takes the cut-out from the released body."},
    {"id": "K3", "evidence": ["P3-lid-switch", "B-slot-len"],
     "summary": "The lid micro switch is listed as 6*9 mm; the body's slot for it is 6 x 12 mm.",
     "resolution": "Different objects: the slot holds the switch and leaves room for its lever. The model takes the slot from the released body."},
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
    {"id": "body-shape", "kind": "shape", "part": "body", "body": "body_step",
     "pairs": [[f"body.{f}", f"body_step.{f}"] for f in ["boss1", "fan_hole_p", "arrow_tip", "rocker_p1", "slot_c1", "dc_q1"]]},
    {"id": "plate-shape", "kind": "shape", "part": "plate", "body": "plate_step",
     "pairs": [[f"plate.{f}", f"plate_step.{f}"] for f in ["foot_p", "foot_n", "hole", "rim"]]},
    {"id": "rotor-shape", "kind": "shape", "part": "rotor", "body": "rotor_pcr325_step",
     "pairs": [[f"rotor.{f}", f"rotor_pcr325_step.{f}"] for f in ["ridge_xp", "hole_out_p", "tab_corner", "end_n", "ledge_p"]]},
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
      + block("conflicts", conflicts)
      + "datums:\n" + "".join(f"  {k}: {j(v)}\n" for k, v in datums.items()))
write("params.yaml", "params:\n" + "".join(f"  {k}: {j(v)}\n" for k, v in params.items()))
write("checks.yaml", block("checks", checks))
write("gaps.yaml", block("gaps", gaps))
print(len(evidence), "evidence;", len(params), "params;", len(checks), "checks;", len(datums), "datums")
