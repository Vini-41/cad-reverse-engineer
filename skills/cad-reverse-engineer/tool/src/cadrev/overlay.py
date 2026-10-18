"""Draw model edges over a source figure, scaled by a published dimension."""

from __future__ import annotations

import math
from pathlib import Path

from .geometry import Built
from .project import Project

VIEWS = {"front": (0, 2), "top": (0, 1), "right": (1, 2)}  # (horizontal, vertical) axes


def _edges(built: Built, target: str):
    if target == "assembly":
        shapes = [built.parts[part].moved(loc) for part, loc in built.assembly.values()]
    elif target in built.assembly:
        part, loc = built.assembly[target]
        shapes = [built.parts[part].moved(loc)]
    else:
        shapes = [built.parts[target]]
    for shape in shapes:
        yield from shape.edges()


def render(p: Project, built: Built) -> list[Path]:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.image as mpimg
    import matplotlib.pyplot as plt

    out = p.root / "build" / "overlays"
    out.mkdir(parents=True, exist_ok=True)
    written = []
    for o in p.overlays:
        oid = o.get("id", "?")
        try:
            cal = o["calibration"]
            known = p.evidence_value(cal["evidence"])
            if known is None:
                raise KeyError(f"evidence value {cal['evidence']}")
            (x1, y1), (x2, y2) = cal["pixels"]
            scale = math.dist((x1, y1), (x2, y2)) / known  # pixels per model unit
            h, v = VIEWS[o["view"]]
            ox, oy = o["origin"]
            image = mpimg.imread(p.root / o["image"])
            edges = list(_edges(built, o["part"]))
        except (KeyError, TypeError, ValueError, ZeroDivisionError, OSError) as exc:
            p.error("overlay-config", f"overlay {oid}: {exc}")
            continue
        flip = -1 if o.get("mirror") else 1
        fig, ax = plt.subplots(figsize=(image.shape[1] / 100, image.shape[0] / 100), dpi=100)
        ax.imshow(image)
        for edge in edges:
            points = [(q.X, q.Y, q.Z) for q in (edge.position_at(t / 24) for t in range(25))]
            ax.plot([ox + flip * pt[h] * scale for pt in points],
                    [oy - pt[v] * scale for pt in points],
                    color=o.get("color", "#e4007c"), linewidth=1.2, alpha=0.85)
        ax.plot([x1, x2], [y1, y2], "o--", color="#00a0e4", markersize=4, linewidth=1)
        ax.set_title(f"{oid}: {o['part']} {o['view']} view, scaled by {cal['evidence']} = {known:g}",
                     fontsize=8)
        ax.set_axis_off()
        target = out / f"{oid}.png"
        try:
            fig.savefig(target, bbox_inches="tight", dpi=100)
        except (OSError, ValueError) as exc:
            p.error("overlay-config", f"overlay {oid}: cannot write {target.name}: {exc}")
            continue
        finally:
            plt.close(fig)
        written.append(target)
    return written
