"""PROTOTYPE for #246, throwaway: would a cut part pass at tolerance.length if it were placed
exactly where its region is drawn? For each cut-file shape check, from the frame the datum pairs
fit, search the placement on the sheet (shift x, y and turn) that minimises the largest outline
distance (Nelder-Mead), and report it beside the pairs' frame. A part that passes here is built
right and only its typed datums' 0.01 precision placed it off; one that still fails differs.

    scripts/cadrev python minimax_frames.py <project> <frames.json> [--json out.json]
"""

import json
import sys
from pathlib import Path

import numpy as np
from scipy.optimize import minimize

sys.path.insert(0, str(Path(__file__).parent))
import deviation as D  # noqa: E402
from build123d import Location  # noqa: E402
from cadrev import build, ledger, released  # noqa: E402
from cadrev import project as project_mod  # noqa: E402

p = project_mod.load(Path(sys.argv[1]))
ledger.check(p)
model = build.build(p)
frames = json.loads(Path(sys.argv[2]).read_text())
rows = []
for c in p.checks:
    if c.get("kind") != "shape" or released.at_point(str(c["body"])) is None:
        continue
    where = D.matrix_location(frames[c["id"]])
    outline = released.outline(model.parts[c["part"]], str(c.get("along")))
    region = p.body(str(c["body"]))
    centre = outline.moved(where).center()

    def worst(x):
        turn = Location((centre.X, centre.Y, 0)) * Location((0, 0, 0), (0, 0, 1), x[2])
        back = Location((-centre.X, -centre.Y, 0))
        return released.outline_distance(
            outline.moved(Location((x[0], x[1], 0)) * turn * back * where), region
        )[0]

    before = worst([0, 0, 0])
    found = minimize(worst, [0, 0, 0], method="Nelder-Mead",
                     options={"xatol": 1e-6, "fatol": 1e-7, "initial_simplex":
                              [[0, 0, 0], [0.005, 0, 0], [0, 0.005, 0], [0, 0, 0.005]]})
    rows.append({"check": c["id"], "pairs_frame": before, "best_frame": float(found.fun),
                 "moved": [float(v) for v in found.x]})
    print(f"{c['id']:28} pairs {before:.3g} -> best {found.fun:.3g} "
          f"(shift {found.x[0]:.4f}, {found.x[1]:.4f}, turn {found.x[2]:.4f} deg)", flush=True)
if "--json" in sys.argv:
    Path(sys.argv[sys.argv.index("--json") + 1]).write_text(json.dumps(rows, indent=1))
