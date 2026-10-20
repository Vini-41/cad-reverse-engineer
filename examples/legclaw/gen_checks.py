"""Writes checks.yaml: the checks repeated per leg, per toe and per servo are generated here."""
import yaml

LEGS = ("a", "b")
MOTION_LEGS = LEGS
checks = []
add = checks.append

# Table S2 envelopes, each part in its own frame
for cid, part, ev, axes, interp in [
    ("env-phalanx1", "phalanx1", "S2-phalanx1", {"L": "x", "H": "z", "W": "y"}, "L along the toe (part X), H in the flexion plane (part Z), W along the joint axes (part Y)"),
    ("env-phalanx2", "phalanx2", "S2-phalanx2", {"L": "x", "H": "z", "W": "y"}, "as phalanx 1"),
    ("env-claw", "claw", "S2-claw", {"L": "x", "H": "z", "W": "y"}, "L along the toe, H in the flexion plane, W along the joint axis; the hook is not shaped, the envelope is"),
    ("env-compression", "comp", "S2-compression", {"L": "x", "H": "z", "W": "y"}, "L along the link, H in the four-bar plane, W along the pivots"),
    ("env-bent", "bent", "S2-bent", {"L": "x", "H": "z", "W": "y"}, "L along the link, H in its plane, W along the pivots"),
    ("env-linkage", "linkage", "S2-linkage", {"L": "x", "H": "z", "W": "y"}, "L along the link, H in the X plane, W along the pins"),
    ("env-pedestal", "pedestal", "S2-pedestal", {"L": "x", "H": "y", "W": "z"}, "the 63 mm read as the column length along the leg axis"),
    ("env-thigh", "thigh", "S2-thigh", {"L": "z", "H": "x", "W": "y"}, "L along the leg axis including the flip-axis ears, H lateral, W along the flip axis"),
    ("env-wheel", "wheel", "S2-wheel", {"L": "x", "H": "y", "W": "z"}, "a disc: L and W the diameter, H the thickness along the servo axis"),
]:
    add({"id": cid, "kind": "bbox", "part": part, "evidence": ev, "axes": axes, "interpretation": interp})

add({"id": "len-bent-L14", "kind": "distance", "between": ["bent.tip_a", "bent.tip_b"], "evidence": "M42-L14",
     "key": "L14", "along": "x", "interpretation": "L14 read as the overall tip-to-tip length (conflict K3)"})

for leg in LEGS:
    foot = [f"{leg}_mid", f"{leg}_end_L", f"{leg}_end_R"] + [
        f"{leg}_lnk_{s}{ab}{r}" for s in "LR" for ab in "AB" for r in "fb"]
    add({"id": f"env-sole-{leg}", "kind": "bbox", "instances": foot, "evidence": "fig2a-sole",
         "axes": {"L": "x", "W": "y", "H": "z"},
         "interpretation": "the sole: end frames, centre post and X-structure linkages; L across the bending direction, W along the toe rows, H the frame height"})
    add({"id": f"width-min-{leg}", "kind": "distance", "instances": [f"{leg}_up_l", f"{leg}_up_r"],
         "between": [f"{leg}_up_l.pin_b", f"{leg}_up_r.pin_b"], "evidence": "fig2d-width", "key": "Dmin", "along": "x",
         "interpretation": "D between the knee pins, leg extended as built"})

# ---- motion
for leg in MOTION_LEGS:
    add({"id": f"width-range-{leg}", "kind": "range", "joint": f"{leg}_slide", "ends": ["fig2d-width.Dmax"],
         "instances": [f"{leg}_up_l", f"{leg}_up_r"], "between": [f"{leg}_up_l.pin_b", f"{leg}_up_r.pin_b"], "along": "x",
         "interpretation": "pedestal pushed into the thigh by its full stroke: the knees spread to Dmax"})

for leg in MOTION_LEGS:
    add({"id": f"flip-range-{leg}", "kind": "range", "joint": f"{leg}_flip", "ends": ["P5-flip.turn"],
         "interpretation": "leg turned from standing to hanging about the dual-axis servo"})
    for k in (1, 2):
        add({"id": f"wheel-range-{leg}{k}", "kind": "range", "joint": f"{leg}_whl{k}", "ends": ["P3-servo-turn.turn"],
             "interpretation": "tendon-servo steering wheel turned from slack to claw fully closed"})
    for side in "LR":
        for row in "fb":
            j = f"{leg}_toe_{side}{row}_j_beta"
            add({"id": f"toe-range-{leg}{side}{row}", "kind": "range", "joint": j,
                 "ends": ["P2-toe-range.min", "P2-toe-range.max"],
                 "interpretation": "toe rotation joint beta from parallel to fully spread"})
    sweeps = [(f"{leg}_slide", "four-bar compressed over its stroke"),
              (f"{leg}_flip", "leg flipped from standing to hanging")]
    sweeps += [(f"{leg}_whl{k}", "servo wheel turned its 385 degrees") for k in (1, 2)]
    sweeps += [(f"{leg}_toe_{s}{r}_j_beta", "toe spread over 0-40 degrees") for s in "LR" for r in "fb"]
    for j, what in sweeps:
        add({"id": f"sweep-{j}", "kind": "interference", "sweep": {"joint": j, "steps": "sweep_steps"},
             "interpretation": f"no two instances overlap: {what}"})

add({"id": "clear-as-built", "kind": "interference", "interpretation": "no two instances overlap as built"})

leg_counts = {"servo_single": "n_single_leg", "wheel": "n_single_leg", "comp": "n_comp", "bent": "n_bent",
              "foot_end": "n_end", "linkage": "n_linkage", "toe_joint": "n_toes", "phalanx1": "n_toes",
              "phalanx2": "n_toes", "claw": "n_toes"}
parts = ["plate", "servo_dual", "thigh", "servo_single", "wheel", "comp", "pedestal", "bent", "foot_mid",
         "foot_end", "linkage", "toe_joint", "phalanx1", "phalanx2", "claw"]


def leg_instances(leg):
    """A leg's instances, named as model.py puts them: plate, servos, thigh, four-bar, foot, toes."""
    names = ["plate", "dual", "thigh", "srv1", "whl1", "srv2", "whl2", "ped", "up_l", "lo_l", "up_r", "lo_r", "mid"]
    for side in "LR":
        names += [f"end_{side}"] + [f"lnk_{side}{ab}{row}" for ab in "AB" for row in "fb"]
        names += [f"bent_{side}{row}" for row in "fb"]
        names += [f"toe_{side}{row}_{k}" for row in "fb" for k in ("j", "p1", "p2", "c")]
    return [f"{leg}_{n}" for n in names]


add({"id": "mass-leg", "kind": "mass", "instances": leg_instances("a"), "counts": leg_counts, "evidence": "P3-leg-mass", "key": "m",
     "tol_rel": 0.10, "interpretation": "one leg with its connecting plate, as the mass model weighs it; within 10%, as only the servos' 63 g is stated, the printed parts rest on a proposed solid-resin density (gap G-density) and 200 g is a round figure"})
all_counts = {k: v + "_all" for k, v in leg_counts.items() if v != "n_single_leg"}
all_counts.update({"servo_single": "n_single_all", "wheel": "n_single_all",
                   "plate": "n_legs", "servo_dual": "n_legs", "thigh": "n_legs", "pedestal": "n_legs", "foot_mid": "n_legs"})
add({"id": "mass-gear", "kind": "mass", "parts": parts, "counts": all_counts, "add": ["board_mass"],
     "evidence": "P3-gear-mass", "key": "m", "tol_rel": 0.10,
     "interpretation": "both legs and plates plus the stated control board and wiring; within 10%, as for mass-leg, the stated mass being about 430 g"})

with open("checks.yaml", "w") as f:
    f.write("# Geometry checks. Expected values come from evidence.yaml, never from params.yaml.\n")
    f.write("# Written by gen_checks.py; edit that script, not this file.\n")
    yaml.safe_dump({"checks": checks}, f, sort_keys=False, width=200, allow_unicode=True)
