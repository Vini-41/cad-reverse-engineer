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


def _target(built: Built, o: dict) -> tuple[str, list]:
    """What overlay o draws, as its title's name for it and its shapes: part in the part's own
    frame, instance where the assembly places it, or with part "assembly" every instance so
    placed. ValueError when o names both, neither, or one the model lacks."""
    if ("part" in o) == ("instance" in o):
        raise ValueError(
            "name one of part or instance, not " + ("both" if "part" in o else "neither")
        )
    if o.get("part") == "assembly":
        return "assembly", [built.parts[part].moved(loc) for part, loc in built.assembly.values()]
    if "instance" in o:
        name = o["instance"]
        if name not in built.assembly:
            also = "; part draws the part of that name" if name in built.parts else ""
            raise ValueError(f"instance {name} is not an instance of the assembly{also}")
        part, loc = built.assembly[name]
        return f"instance {name}", [built.parts[part].moved(loc)]
    name = o["part"]
    if name not in built.parts:
        also = "; instance draws the instance of that name" if name in built.assembly else ""
        raise ValueError(f"part {name} is not a part model.py builds{also}")
    return name, [built.parts[name]]


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


def _projected(shapes: list, h: int, v: int):
    """Each edge of shapes as 25 points along it, each as its (horizontal, vertical) model
    coordinates in the view."""
    for shape in shapes:
        for edge in shape.edges():
            points = [tuple(edge.position_at(t / 24)) for t in range(25)]
            yield [(q[h], q[v]) for q in points]


def _off_image(name: str, lines: list, width: int, height: int) -> str:
    """Why an overlay of name draws no model edge on its width × height image, naming the pixel
    bounds its edges project to."""
    points = [q for line in lines for q in line]
    if not points:
        return f"{name} has no edges to draw; name a part or instance that has"
    xs, ys = [x for x, _ in points], [y for _, y in points]
    return (
        f"no model edge of {name} falls on the {width}×{height} image: its edges project to "
        f"x {min(xs):.0f} to {max(xs):.0f}, y {min(ys):.0f} to {max(ys):.0f} pixels; correct its "
        "origin, view or calibration, or name the part, in its own frame, rather than an instance"
    )


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
            name, shapes = _target(built, o)
            flip = -1 if o.get("mirror") else 1
            lines = [
                [(ox + flip * x * scale, oy - y * scale) for x, y in points]
                for points in _projected(shapes, h, v)
            ]
        except (KeyError, TypeError, ValueError, ZeroDivisionError, OSError) as exc:
            p.error("overlay-config", f"overlay {oid}: {exc}")
            continue
        # One pixel of the image is one PNG pixel: the image axes fill a W×H area of the figure,
        # under a strip that holds the title.
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
            ax.plot(
                [x for x, _ in line],
                [y for _, y in line],
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
        if not any(_crosses(a, b, width, height) for line in lines for a, b in zip(line, line[1:])):
            p.warn("overlay-empty", f"overlay {oid}: {_off_image(name, lines, width, height)}")
    return written
