"""Writes checks.yaml: one check per probe (the model datums that realise it) plus the train, shape and motion checks.
Run: python3 checks_gen.py"""
import json

D = []  # (probe, part, datums, key, along, kind)


def d(probe, part, a, b, key, along=None):
    D.append((probe, part, [f"{part}.{a}", f"{part}.{b}"], key, along, "distance"))


def ang(probe, part, a, b, c, key="a"):
    D.append((probe, part, [f"{part}.{a}", f"{part}.{b}", f"{part}.{c}"], key, None, "angle"))


P, S, C, K, G, R = "planet_gear", "sun_gear", "primary_carrier", "secondary_carrier", "casing", "retainer"
d("P-w", P, "tip0", "tip0_top", "w", "z"); d("P-bore", P, "bore_a", "bore_b", "d"); d("P-cb", P, "cb_a", "cb_b", "d")
d("P-cbd", P, "cb_a", "cb_floor", "h", "z")
d("S-len", S, "tip_bot", "fl_top", "l", "z"); d("S-bdr", S, "bd0", "cb0", "dr"); d("S-cb", S, "cb1", "cb_b", "d")
d("S-cbd", S, "cb0", "cb1", "h", "z"); d("S-tdr", S, "td0", "tip_bot", "dr"); d("S-cham", S, "tip_bot", "ch1", "h", "z")
d("S-sdr", S, "sd0", "sh1", "dr"); d("S-shl", S, "tip_bot", "sh1", "l", "z"); d("S-step", S, "st1", "step_b", "d")
d("S-steph", S, "sh1", "st1", "h", "z"); d("S-hub", S, "hub_a", "hub_b", "d"); d("S-hubc", S, "st1", "hub_a", "h", "z")
d("S-face", S, "gt0", "gt1", "w", "z"); d("S-fdr", S, "cb1", "fl_top", "dr"); d("S-flt", S, "ft0", "fl_top", "t", "z")
d("S-pcd", S, "h90", "h270", "pcd", "y"); d("S-hole", S, "h90", "h90_b", "d"); d("S-csk", S, "csk_a", "csk_b", "d")
d("S-cskd", S, "csk_a", "ck1", "h", "z"); ang("S-nh", S, "h90", "h0", "h270")
d("C-h", C, "bot", "pintop", "h", "z"); d("C-disc", C, "disc_a", "disc_b", "d"); d("C-cham", C, "bot", "disc_a", "h", "z")
d("C-dh", C, "bot", "ft0", "h", "z"); d("C-fdr", C, "fd0", "ft0", "dr"); d("C-flt", C, "ft0", "ft1", "t", "z")
d("C-b1", C, "b1_a", "b1_b", "d"); d("C-b1d", C, "b1_a", "b2_a", "h", "z"); d("C-b2", C, "b2_a", "b2_b", "d")
d("C-b2d", C, "b2_a", "b2z1", "h", "z"); d("C-b2c", C, "b2c_a", "b2c_b", "d"); d("C-pock", C, "pk0", "pk1", "dr", "x")
d("C-pockd", C, "pkd0", "pk0", "h", "z"); d("C-pinb", C, "pinb_a", "pinb_b", "d"); d("C-pin", C, "pintop", "pin_b", "d")
d("C-col", C, "col_a", "col_b", "d"); d("C-colh", C, "col_a", "co1", "h", "z"); d("C-colf", C, "cf0", "co1", "h", "z")
d("C-bolt", C, "bolt_a", "bolt_b", "d"); d("C-bcb", C, "bc0", "bc1", "dr", "x"); d("C-bcbd", C, "bcd0", "bc0", "h", "z")
d("C-bR", C, "bolt_a", "bR1", "dy", "y"); d("C-nut", C, "nR0", "nut_b", "d"); d("C-nutR", C, "nR0", "nR1", "d")
d("C-hex", C, "hx0", "hx1", "ac"); d("C-hexd", C, "hxd0", "hx0", "h", "z"); ang("C-nn", C, "nR0", "n60", "n120"); ang("C-hexang", C, "hx30", "hx0", "hx150")
d("C-tip", C, "etip", "b2c_s", "dy", "y")
d("K-od", K, "od_a", "od_b", "d"); d("K-id", K, "id_a", "id_b", "d"); d("K-t", K, "t0", "od_a", "t", "z")
d("K-bh", K, "bh0", "bh1", "h", "z"); d("K-bid", K, "bh1", "bid_b", "d"); d("K-bch", K, "bc0", "bh0", "h", "z")
d("K-btr", K, "bt0", "bt1", "dr"); d("K-pin", K, "pin_a", "pin_b", "d"); d("K-phex", K, "ph0", "ph1", "ac")
d("K-hexd", K, "hd0", "ph0", "h", "z"); d("K-bolt", K, "bolt_a", "bolt_b", "d"); d("K-bhex", K, "bx0", "bx1", "ac")
d("K-bR", K, "bolt_a", "bR1", "dy", "y")
d("G-h", G, "h0", "h1", "h", "z"); d("G-odr", G, "bc0", "h0", "dr"); d("G-b0", G, "bc0", "b0_b", "d")
d("G-b1r", G, "bc0", "bc1", "dr", "x"); d("G-bch", G, "bc0", "bc1", "h", "z"); d("G-b1d", G, "bc0", "bd1", "h", "z")
d("G-lipr", G, "lh0", "bd1", "dr"); d("G-liph", G, "lh0", "lh1", "h", "z"); d("G-ringw", G, "rw0", "rw1", "w", "z")
d("G-neck0", G, "nk0", "nk1", "h", "z"); d("G-neck1", G, "nk1", "nk2", "h", "z"); d("G-fl", G, "fe0", "h1", "h", "z")
d("G-body", G, "h1", "body_b", "d"); d("G-pk", G, "pk_a", "pk_b", "d"); d("G-pkd", G, "pd0", "pk_a", "h", "z")
d("G-lobe", G, "lb0", "lb180", "d"); ang("G-nlobe", G, "lb0", "lb20", "lb40"); d("G-sh45", G, "sh45_a", "sh45_b", "d")
d("G-sh43", G, "sc0", "sh43_b", "d"); d("G-shc", G, "sc0", "sh45_a", "h", "z"); d("G-shb", G, "sb0", "sc0", "h", "z")
d("G-shf", G, "sf0", "sb0", "h", "z"); d("G-lugt", G, "lt90", "lt270", "d"); d("G-lugR", G, "lR90", "lR270", "d")
d("G-lugh", G, "lR90", "lugh_b", "d"); ang("G-nlug", G, "lR90", "l30", "lm30"); d("G-lcb", G, "lz0", "lcb_b", "d")
d("G-lcbz", G, "lz0", "lR90", "h", "z"); d("G-hole", G, "hd0", "hole_b", "d"); d("G-holed", G, "hd0", "hd1", "h", "z")
d("G-holeR", G, "hd0", "hR270", "d"); ang("G-nhole", G, "hd0", "h30", "hm30"); d("G-nut", G, "nt0", "nt1", "ac")
d("G-nutz", G, "hd0", "nt1", "h", "z"); d("G-nutt", G, "nt1", "nt2", "t", "z")
d("R-od", R, "od_a", "od_b", "d"); d("R-id", R, "id_a", "id_b", "d"); d("R-t", R, "od_a", "od_t", "t", "z")
d("R-hole", R, "hR0", "hole_b", "d"); d("R-hR", R, "hR0", "hR1", "d"); ang("R-nh", R, "hR0", "h30", "hm30")


def flow(c):
    return "  - {" + ", ".join(f"{k}: {json.dumps(v)}" for k, v in c.items()) + "}"


out = ["# Written by checks_gen.py; edit that and rerun. Expected values come from evidence.yaml, never from params.yaml.", "checks:"]
out.append("  # ---- the train: pitch circles, centre distances, planet count, ring outside, extrusion clearance")
for c in [
    {"id": "sun-pitch", "kind": "distance", "between": ["sun_gear.flank_a", "sun_gear.flank_b"], "expect": "T1.module * T1.z_sun",
     "interpretation": "opposite flanks at the pitch radius, half a turn apart"},
    {"id": "planet-pitch", "kind": "distance", "between": ["planet_gear.flank_a", "planet_gear.flank_b"], "expect": "T1.module * T1.z_planet",
     "interpretation": "opposite flanks at the pitch radius, half a turn apart"},
    {"id": "ring-pitch", "kind": "distance", "between": ["casing.rp_a", "casing.rp_b"], "expect": "T1.module * T1.z_ring",
     "interpretation": "opposite flanks of the internal ring at its pitch radius"},
    {"id": "sun-planet", "kind": "distance", "instances": ["sun_1", "planet_1"], "between": ["sun_1.axis_hi", "planet_1.axis"], "along": "y",
     "expect": "T1.module * (T1.z_sun + T1.z_planet) / 2", "interpretation": "planet 1 sits at 90 deg, so its axis's y is the centre distance"},
    {"id": "ring-planet", "kind": "distance", "instances": ["casing_1", "planet_1"], "between": ["casing_1.axis_lo", "planet_1.axis"], "along": "y",
     "expect": "T1.module * (T1.z_ring - T1.z_planet) / 2", "interpretation": "the planet axis's distance from the ring axis"},
    {"id": "planets", "kind": "count", "part": "planet_gear", "evidence": "T1", "key": "n_planets"},
    {"id": "ring-od", "kind": "distance", "between": ["casing.nk2", "casing.nk2_b"], "expect": "T1.module * T1.z_ring + 2 * DRW.drw",
     "interpretation": "the ring's outside cylinder below the flare: pitch diameter plus twice the stated radial width"},
    {"id": "ext-clear", "kind": "distance", "between": ["primary_carrier.pin_axis", "primary_carrier.ext_side"],
     "expect": "T1.module * T1.z_planet / 2 + T1.module + DCE.dce",
     "interpretation": "an extrusion's flank from the planet axis: the planet's tip radius (one-module addendum) plus the stated clearance"},
]:
    out.append(flow(c))
out.append("  # ---- motion: the carrier's turn per sun turn, the output of the 7.2:1 train")
out.append(flow({"id": "carrier-turn", "kind": "angle", "instances": ["casing_1", "carrier_1"],
                 "between": ["casing_1.ang_ref", "casing_1.ang_axis", "carrier_1.pin_axis_lo"], "from": {}, "pose": {"sun": 360},
                 "expect": "360 / R1.ratio", "interpretation": "the carrier's pin 1 starts a quarter turn from the casing's reference; one sun turn moves it 50 deg on"}))
out.append(flow({"id": "mesh-clear", "kind": "interference", "pairs": [["sun_1", "planet_1"], ["sun_1", "planet_2"], ["sun_1", "planet_3"],
                 ["planet_1", "casing_1"], ["planet_2", "casing_1"], ["planet_3", "casing_1"], ["carrier_1", "casing_1"], ["sec_1", "casing_1"],
                 ["planet_1", "carrier_1"], ["planet_1", "sec_1"], ["sun_1", "carrier_1"], ["sun_1", "sec_1"], ["retainer_1", "casing_1"]],
                 "max_volume": 0.001}))
out.append("  # ---- each released body against the part that reproduces it")
for c in [
    {"id": "planet-shape", "kind": "shape", "part": "planet_gear", "body": "planet", "tol": 0.08,
     "pairs": [["planet_gear.tip0", "planet.tip0"], ["planet_gear.tip0_top", "planet.tip0_top"], ["planet_gear.tip_h", "planet.tip_h"]]},
    {"id": "sun-shape", "kind": "shape", "part": "sun_gear", "body": "sun", "tol": 0.1,
     "pairs": [["sun_gear.gt0", "sun.gt0"], ["sun_gear.gt1", "sun.gt1"], ["sun_gear.tip_h", "sun.tip_h"]]},
    {"id": "carrier-shape", "kind": "shape", "part": "primary_carrier", "body": "carrier_updated", "tol": 0.2,
     "pairs": [["primary_carrier.pintop", "carrier_updated.s_pin90"], ["primary_carrier.bolt_a", "carrier_updated.s_bolt"], ["primary_carrier.disc_a", "carrier_updated.s_disc"]]},
    {"id": "sec-shape", "kind": "shape", "part": "secondary_carrier", "body": "sec_carrier", "tol": 0.5,
     "pairs": [["secondary_carrier.ph0", "sec_carrier.s_pin"], ["secondary_carrier.bolt_a", "sec_carrier.s_bolt"], ["secondary_carrier.ph2", "sec_carrier.s_pin2"]]},
    {"id": "casing-shape", "kind": "shape", "part": "casing", "body": "gearbox_casing", "tol": 0.3,
     "pairs": [["casing.lR90", "gearbox_casing.s_lug"], ["casing.hd0", "gearbox_casing.s_hole"], ["casing.rw0", "gearbox_casing.s_ring"]]},
    {"id": "retainer-shape", "kind": "shape", "part": "retainer", "body": "bearing_retainer", "tol": 0.2,
     "pairs": [["retainer.hR0", "bearing_retainer.hR1"], ["retainer.hR1", "bearing_retainer.hR0"], ["retainer.s_od", "bearing_retainer.s_od"]]},
]:
    out.append(flow(c))
out.append("  # ---- each probed value on the part that realises it")
for probe, part, between, key, along, kind in D:
    c = {"id": "p-" + probe, "kind": kind, "between": between, "evidence": probe, "key": key}
    if along:
        c["along"] = along
    if probe == "C-tip":
        c["tol"] = 0.005
    out.append(flow(c))
open("checks.yaml", "w").write("\n".join(out) + "\n")
print(len(D), "probe checks")
