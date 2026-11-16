"""Draw model edges over a figure, scaled by a published dimension: visual evidence for a human."""

from __future__ import annotations

import math
import textwrap
from pathlib import Path

from . import Fault
from .build import Model
from .drawing import frames
from .project import Project

VIEWS = ("front", "top", "right")
DPI = 100
MARKER_RADIUS = 2 * DPI / 72  # pixels: a 4 pt marker
# The title, in 8 pt type, wraps to the image's width in lines of this many pixels.
TITLE_LINE, TITLE_CHAR = 12, 6


def _target(model: Model, o: dict) -> tuple[str, list]:
    """What overlay o draws, as its title names it, and its shapes: a part in its own frame, an
    instance where the assembly places it, or with part "assembly" every instance so placed."""
    if ("part" in o) == ("instance" in o):
        raise Fault("name one of part or instance")
    if o.get("part") == "assembly":
        return "assembly", [model.parts[part].moved(loc) for part, loc in model.assembly.values()]
    if "instance" in o:
        if o["instance"] not in model.assembly:
            raise Fault(f"{o['instance']} is not an instance of the assembly")
        part, loc = model.assembly[o["instance"]]
        return f"instance {o['instance']}", [model.parts[part].moved(loc)]
    if o["part"] not in model.parts:
        raise Fault(f"{o['part']} is not a part model.py builds")
    return o["part"], [model.parts[o["part"]]]


def _crosses(a: tuple, b: tuple, width: int, height: int) -> bool:
    """Whether the segment from pixel a to pixel b passes over a width × height image, clipped
    to its pixels' outer edges as Liang-Barsky clips a line to a box."""
    low, high = 0.0, 1.0
    for start, delta, size in ((a[0], b[0] - a[0], width), (a[1], b[1] - a[1], height)):
        bounds = (-0.5 - start, size - 0.5 - start)  # where the box lies along this axis
        if delta == 0:
            if bounds[0] > 0 or bounds[1] < 0:
                return False
            continue
        t1, t2 = sorted(edge / delta for edge in bounds)
        low, high = max(low, t1), min(high, t2)
        if low > high:
            return False
    return True


def render(p: Project, model: Model) -> list[Path]:
    """Write build/overlays/<id>.png for each overlay. Below its title strip one PNG pixel is one
    pixel of the image, so origin and calibration pixels land as written."""
    if not p.overlays:
        return []
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
        try:
            cal = o["calibration"]
            known = p.stated(cal["evidence"])
            (x1, y1), (x2, y2) = cal["pixels"]
            scale = math.dist((x1, y1), (x2, y2)) / known  # pixels per model unit
            if o.get("view") not in VIEWS:
                raise Fault(f"view must be one of {', '.join(VIEWS)}, not {o.get('view')!r}")
            across, rise, _ = frames(p.up)[o["view"]]  # the model directions right and up
            ox, oy = o["origin"]
            if not (p.root / o["image"]).is_file():
                raise Fault(f"image {o['image']} not found")
            image = mpimg.imread(p.root / o["image"])
            name, shapes = _target(model, o)
            flip = -1 if o.get("mirror") else 1
            lines = [  # each edge as 25 points along it, in the image's pixels
                [
                    (
                        ox + flip * sum(a * b for a, b in zip(q, across)) * scale,
                        oy - sum(a * b for a, b in zip(q, rise)) * scale,
                    )
                    for q in (tuple(edge.position_at(t / 24)) for t in range(25))
                ]
                for shape in shapes
                for edge in shape.edges()
            ]
            height, width = image.shape[:2]
            title = textwrap.wrap(
                f"{oid}: {name} {o['view']} view, scaled by {cal['evidence']} = {known:g}",
                max(1, width // TITLE_CHAR),
            )
            strip = TITLE_LINE * (len(title) + 1)
            fig = plt.figure(figsize=(width / DPI, (height + strip) / DPI), dpi=DPI)
            ax = fig.add_axes((0, 0, 1, height / (height + strip)))
            ax.imshow(image, interpolation="nearest")
            for line in lines:
                xs, ys = zip(*line)
                ax.plot(
                    xs, ys, color=o.get("color", "#e4007c"), linewidth=1.2, alpha=0.85, snap=False
                )
            # Unsnapped lines, and circles where a marker would be rounded to the next whole
            # pixel: each lands on the pixel it names.
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
            try:
                fig.savefig(out / f"{oid}.png", dpi=DPI)
            finally:
                plt.close(fig)
        except (Fault, KeyError, TypeError, ValueError, ZeroDivisionError, OSError) as exc:
            p.error("overlay-config", f"overlay {oid}: {exc}")
            continue
        written.append(out / f"{oid}.png")
        if not any(_crosses(a, b, width, height) for line in lines for a, b in zip(line, line[1:])):
            xs, ys = zip(*(q for line in lines for q in line)) if lines else ((0,), (0,))
            p.warn(
                "overlay-empty",
                f"overlay {oid}: no model edge of {name} falls on the {width}×{height} image: its "
                f"edges project to x {min(xs):.0f} to {max(xs):.0f}, y {min(ys):.0f} to "
                f"{max(ys):.0f} pixels; correct its origin, view or calibration",
            )
    return written
