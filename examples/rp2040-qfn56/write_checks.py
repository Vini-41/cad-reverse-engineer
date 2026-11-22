"""Write checks.yaml: the checks written once, and the ones repeated for each lead.

Run from the project directory:  cadrev python write_checks.py
"""

from pathlib import Path

PER_SIDE = 14      # F167-pins.per_side and the body's four sides: which leads share a row
# Row k runs along this axis, on the body's face this datum is on (model.py's frame).
ROW = [("y", "x", "x_min"), ("x", "y", "y_min"), ("y", "x", "x_max"), ("x", "y", "y_max")]

HEAD = """\
# Geometry checks. Expected values come from evidence.yaml, never from params.yaml.
# Written by write_checks.py (cadrev python write_checks.py): edit that, not this file.
checks:
"""

ONCE = """\
  # ---- the lead, in its own frame: outer end at X = 0, running inward along +X -----------------------
  - {id: lead-L, kind: distance, between: [lead.outer, lead.tip], along: x,
     evidence: F167-L, key: nom, interpretation: "L on the seating plane, from the lead's outer end to the crown of its rounded inner end"}
  - {id: lead-L-range, kind: distance, between: [lead.outer, lead.tip], along: x,
     min: F167-L.min, max: F167-L.max}
  - {id: lead-b, kind: distance, between: [lead.side_a, lead.side_b], along: y,
     evidence: F167-b, key: nom, interpretation: "b across the lead on the seating plane, the wide side of its trapezoid"}
  - {id: lead-b-range, kind: distance, between: [lead.side_a, lead.side_b], along: y,
     min: F167-b.min, max: F167-b.max}
  - {id: lead-A3, kind: distance, between: [lead.bottom, lead.top], along: z,
     evidence: F167-A3, key: ref, interpretation: "A3 is a reference dimension, compared like a nominal: the lead frame's thickness, seating plane to the lead's top face"}
  - {id: lead-R-min, kind: distance, between: [lead.round_centre, lead.tip], along: x,
     min: F167-R.min, interpretation: "R from the axis of the rounded inner end to its crown, along the lead; only a MIN is stated. The axis datum lies on no flat face, so a lead with no round there is refused"}

  # ---- the 56 leads --------------------------------------------------------------------------------------
  - {id: lead-count, kind: count, part: lead, evidence: T632-caption, key: leads}
"""

BODY = """\
  # ---- the body ------------------------------------------------------------------------------------------
  - {id: body-size, kind: bbox, part: body, evidence: P13-size, axes: {D: x, E: y},
     interpretation: "D and E are basic dimensions (7 BSC in Figure 167), compared like nominals: D along X, E along Y"}
  - {id: height-A-max, kind: distance, instances: [lead_1, body_1], between: [lead_1.bottom, body_1.top], along: z,
     max: F167-A.max, interpretation: "A from the seating plane, the leads' undersides, to the body's top face; only a MAX is stated"}
  - {id: mould-A2, kind: distance, instances: [lead_1, body_1], between: [lead_1.top, body_1.top], along: z,
     evidence: F167-A2, key: nom, interpretation: "A2 from the top of the lead frame to the body's top face"}
  - {id: mould-A2-max, kind: distance, instances: [lead_1, body_1], between: [lead_1.top, body_1.top], along: z,
     max: F167-A2.max}
  - {id: standoff-A1, kind: distance, instances: [lead_1, body_1], between: [lead_1.bottom, body_1.underside], along: z,
     min: F167-A1.min, max: F167-A1.max, interpretation: "A1 from the seating plane to the body's underside; a MIN and a MAX are stated, no nominal"}
  - {id: dot-size, kind: diameter, at: body.dot_x_min, evidence: T633-dot, key: size}
  - {id: dot-X, kind: distance, between: [body.x_min, body.dot_x_min], along: x,
     evidence: T633-dot, key: X, interpretation: "Coord. X from the package's left side, its -X face, to the left side of the dot"}
  - {id: dot-Y, kind: distance, between: [body.y_min, body.dot_y_min], along: y,
     evidence: T633-dot, key: Y, interpretation: "Coord. Y from the package's bottom side seen from above, its -Y face, to the lower side of the dot"}

  # ---- the centre pad ------------------------------------------------------------------------------------
  - {id: pad-D2, kind: distance, between: [pad.x_min, pad.x_max], along: x, evidence: F167-D2, key: nom}
  - {id: pad-D2-range, kind: distance, between: [pad.x_min, pad.x_max], along: x,
     min: F167-D2.min, max: F167-D2.max}
  - {id: pad-E2, kind: distance, between: [pad.y_min, pad.y_max], along: y, evidence: F167-E2, key: nom}
  - {id: pad-E2-range, kind: distance, between: [pad.y_min, pad.y_max], along: y,
     min: F167-E2.min, max: F167-E2.max}
  - {id: notch-R, kind: diameter, at: pad.notch_wall, expect: "2 * F167-notch.R"}
  - {id: notch-offset, kind: distance, between: [pad.notch_axis, pad.y_max], along: y,
     evidence: F167-notch, key: offset, interpretation: "from the notch's centre to the pad's edge facing leads 43 to 56"}
  - {id: pad-gap-leads-1-14, kind: distance, instances: [lead_14, pad_1], between: [lead_14.tip, pad_1.x_min], along: x,
     evidence: F167-gap, key: gap, interpretation: "the 1.550 the bottom view prints from lead 14's inner end to the pad"}
  - {id: pad-gap-leads-15-28, kind: distance, instances: [lead_24, pad_1], between: [lead_24.tip, pad_1.y_min], along: y,
     evidence: F167-gap, key: gap, interpretation: "the 1.550 the bottom view prints from the inner ends of leads 15 to 28 to the pad"}
  - {id: pad-gap-leads-43-56, kind: distance, instances: [lead_43, pad_1], between: [lead_43.tip, pad_1.y_max], along: y,
     evidence: F167-gap, key: gap, interpretation: "the 1.550 the bottom view prints from lead 43's inner end to the pad: the one the pad is not placed by"}

  # ---- the assembly --------------------------------------------------------------------------------------
  - {id: clear, kind: interference}
"""


def lead_checks(with_body):
    out = []
    for k, (run, inward, face) in enumerate(ROW):
        first, last = k * PER_SIDE + 1, (k + 1) * PER_SIDE
        out.append(f"  # leads {first} to {last}")
        out.append(f"  - {{id: row-{first}-{last}, kind: distance, instances: [lead_{first}, lead_{last}], "
                   f"between: [lead_{first}.outer, lead_{last}.outer], along: {run},\n"
                   f'     expect: "F167-e.bsc * (F167-pins.per_side - 1)", '
                   f'interpretation: "14 leads to the row: 13 pitches from lead {first} to lead {last}"}}')
        for n in range(first, last):
            out.append(f"  - {{id: pitch-{n}-{n + 1}, kind: distance, instances: [lead_{n}, lead_{n + 1}], "
                       f"between: [lead_{n}.outer, lead_{n + 1}.outer], along: {run}, evidence: F167-e, key: bsc}}")
        if with_body:
            for n in range(first, last + 1):
                out.append(f"  - {{id: reach-{n}, kind: distance, instances: [body_1, lead_{n}], "
                           f"between: [body_1.{face}, lead_{n}.tip], along: {inward}, evidence: F167-L, key: nom}}")
    return "\n".join(out) + "\n"


def write(with_body=True):
    text = HEAD + ONCE + lead_checks(with_body) + (BODY if with_body else "")
    Path(__file__).with_name("checks.yaml").write_text(text)


if __name__ == "__main__":
    import sys
    write(with_body="--lead-only" not in sys.argv)
