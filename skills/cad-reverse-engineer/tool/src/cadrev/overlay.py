"""Draw model edges over a figure, scaled by a published dimension."""

from __future__ import annotations

import math
import textwrap
from pathlib import Path

from .geometry import Built
from .project import Project, calibration_ref

VIEWS = {"front": (0, 2), "top": (0, 1), "right": (1, 2)}  # (horizontal, vertical) axes
DPI = 100
MARKER_RADIUS = 2 * DPI / 72  # pixels: a 4 pt marker
# The title, in 8 pt type, wraps to the image's width in lines of this many pixels.
TITLE_LINE, TITLE_CHAR = 12, 6


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
    from matplotlib.patches import Circle

    out = p.root / "build" / "overlays"
    out.mkdir(parents=True, exist_ok=True)
    written = []
    for o in p.overlays:
        oid = o.get("id", "?")
        if p.cites_repeated(calibration_ref(o)):
            continue  # it is scaled by neither item; check_citations said so before the build
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
        # One pixel of the image is one PNG pixel: the image axes fill a W×H area of the figure,
        # under a strip that holds the title.
        height, width = image.shape[:2]
        title = textwrap.wrap(
            f"{oid}: {o['part']} {o['view']} view, scaled by {cal['evidence']} = {known:g}",
            max(1, width // TITLE_CHAR),
        )
        strip = TITLE_LINE * (len(title) + 1)
        fig = plt.figure(figsize=(width / DPI, (height + strip) / DPI), dpi=DPI)
        ax = fig.add_axes((0, 0, 1, height / (height + strip)))
        ax.imshow(image, interpolation="nearest")
        for edge in edges:
            points = [(q.X, q.Y, q.Z) for q in (edge.position_at(t / 24) for t in range(25))]
            ax.plot(
                [ox + flip * pt[h] * scale for pt in points],
                [oy - pt[v] * scale for pt in points],
                color=o.get("color", "#e4007c"),
                linewidth=1.2,
                alpha=0.85,
                snap=False,
            )
        # Unsnapped lines, and circles where a marker would be rounded to the next whole pixel:
        # each lands on the pixel it names.
        ax.plot([x1, x2], [y1, y2], "--", color="#00a0e4", linewidth=1, snap=False)
        for end in ((x1, y1), (x2, y2)):
            ax.add_patch(Circle(end, MARKER_RADIUS, color="#00a0e4", linewidth=0, zorder=3))
        ax.set_xlim(-0.5, width - 0.5)  # edges past the image must not widen the axes
        ax.set_ylim(height - 0.5, -0.5)
        fig.text(
            0.5,
            1 - strip / 2 / (height + strip),
            "\n".join(title),
            fontsize=8,
            ha="center",
            va="center",
        )
        ax.set_axis_off()
        target = out / f"{oid}.png"
        try:
            fig.savefig(target, dpi=DPI)
        except (OSError, ValueError) as exc:
            p.error("overlay-config", f"overlay {oid}: cannot write {target.name}: {exc}")
            continue
        finally:
            plt.close(fig)
        written.append(target)
    return written
