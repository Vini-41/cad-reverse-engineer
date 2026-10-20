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
def leg_instances(leg):
    """A leg's instances, named as model.py puts them: plate, servos, thigh, four-bar, foot, toes."""
    names = ["plate", "dual", "thigh", "srv1", "whl1", "srv2", "whl2", "ped", "up_l", "lo_l", "up_r", "lo_r", "mid"]
    for side in "LR":
        names += [f"end_{side}"] + [f"lnk_{side}{ab}{row}" for ab in "AB" for row in "fb"]
        names += [f"bent_{side}{row}" for row in "fb"]
        names += [f"toe_{side}{row}_{k}" for row in "fb" for k in ("j", "p1", "p2", "c")]
    return [f"{leg}_{n}" for n in names]


for leg in MOTION_LEGS:
    add({"id": f"width-range-{leg}", "kind": "range", "joint": f"{leg}_slide", "ends": ["fig2d-width.Dmax"],
         "instances": [f"{leg}_up_l", f"{leg}_up_r"], "between": [f"{leg}_up_l.pin_b", f"{leg}_up_r.pin_b"], "along": "x",
         "interpretation": "pedestal pushed into the thigh by its full stroke: the knees spread to Dmax"})

for leg in MOTION_LEGS:
    add({"id": f"flip-range-{leg}", "kind": "range", "joint": f"{leg}_flip", "ends": ["P5-flip.turn"],
         "interpretation": "leg turned from standing to hanging about the dual-axis servo"})
    add({"id": f"wheel-range-{leg}1", "kind": "range", "joint": f"{leg}_whl1", "ends": ["P3-servo-turn.turn"],
         "interpretation": "claw servo steering wheel turned from slack to claw fully closed"})
    for side in "LR":
        add({"id": f"claw-stroke-{leg}{side}", "kind": "stroke", "cable": f"{leg}_claw_{side}",
             "evidence": "P3-tendon-stroke", "key": "stroke", "tol": 1.9,
             "interpretation": "the whole claw cable shared by the same-side pair of toes, shortened by wheel 1's full turn; 'approximately' 38 mm, so within the 5% cap"})
    for side in "LR":
        for row in "fb":
            j = f"{leg}_toe_{side}{row}_j_beta"
            add({"id": f"toe-range-{leg}{side}{row}", "kind": "range", "joint": j,
                 "ends": ["P2-toe-range.min", "P2-toe-range.max"],
                 "interpretation": "toe rotation joint beta from parallel to fully spread"})
    sweeps = [(f"{leg}_slide", "four-bar compressed over its stroke"),
              (f"{leg}_flip", "leg flipped from standing to hanging")]
    # wheel 2 spreads all four toes' beta together, so its sweep is the toe-range sweep
    sweeps += [(f"{leg}_whl2", "toe-motion wheel turned, spreading the toes over 0-40 degrees")]
    for j, what in sweeps:
        add({"id": f"sweep-{j}", "kind": "interference", "sweep": {"joint": j, "steps": "sweep_steps"},
             "interpretation": f"no two instances overlap: {what}"})
    # wheel 1 closes the toes: each closing toe segment against its own leg, except the opposite
    # side's toes, which close towards it around the branch (p. 2: the claws grasp from both sides)
    inst = leg_instances(leg)
    closing = {s: [f"{leg}_toe_{s}{r}_{k}" for r in "fb" for k in ("p1", "p2", "c")] for s in "LR"}
    pairs = []
    for s, other in (("L", "R"), ("R", "L")):
        for m in closing[s]:
            for o in inst:
                if o == m or o in closing[other]:
                    continue
                if o in closing[s] and closing[s].index(o) < closing[s].index(m):
                    continue  # this pair was listed from its other segment's side
                pairs.append([m, o])
    add({"id": f"sweep-{leg}_whl1", "kind": "interference", "pairs": pairs,
         "sweep": {"joint": f"{leg}_whl1", "steps": "sweep_steps"},
         "interpretation": "no two instances overlap: claw wheel turned its 385 degrees, each closing toe segment against every instance of its leg except the opposite side's closing segments, which meet them around the branch as the claws close"})

add({"id": "clear-as-built", "kind": "interference", "interpretation": "no two instances overlap as built"})

leg_counts = {"servo_single": "n_single_leg", "wheel": "n_single_leg", "comp": "n_comp", "bent": "n_bent",
              "foot_end": "n_end", "linkage": "n_linkage", "toe_joint": "n_toes", "phalanx1": "n_toes",
              "phalanx2": "n_toes", "claw": "n_toes"}
parts = ["plate", "servo_dual", "thigh", "servo_single", "wheel", "comp", "pedestal", "bent", "foot_mid",
         "foot_end", "linkage", "toe_joint", "phalanx1", "phalanx2", "claw"]


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
