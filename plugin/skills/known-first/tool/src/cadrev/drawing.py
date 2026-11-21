"""build/isometric.png, build/drawings/<part>.png and build/steps/<n>.png: the object as a
reviewer first looks at it, and as the person putting it together does.

A part's drawing is its front, top and right views in third-angle projection beside an isometric
one, dimensioned by the part's own checks: each dimension is the value as built, so a reviewer
verifies the part on one sheet. Under a plan, a made part's title line also prints the material
and the plan's general tolerance. A step's view is the isometric view of what the plan's step
places, in black, on what the steps before it placed, in grey, drawn apart with a guideline where
the step names the direction it comes from. The drawings read the build and add no pass or fail.
"""

from __future__ import annotations

import importlib
import math
from dataclasses import dataclass, field
from pathlib import Path

from . import Fault, released
from .build import Model, prefix
from .checks import Result, part_of
from .project import AXES, Project

INK, HIDDEN, CHECKED, FAILED, REFERENCE = "#1a1a1a", "#a0a0a0", "#1f5fa8", "#c62828", "#707070"
PLACED = "#8c8c8c"  # what a step's view shows as already there
GUIDE = "#c2570c"  # the line from where a step's instances are drawn to their place
DPI = 200
WIDTH, HEIGHT = 11.0, 7.5  # inches a sheet fits in, under its title
TITLE = 0.75  # inches of title above the sheet
NARROWEST = 6.5  # inches: the width its title's note needs
NOTE = 7.5  # points: a title's note
MARGIN = 0.02  # of a sheet's width, either side of its title
# A sheet is laid out in steps of `u`, a fraction of the views' size: a dimension's text is
# 0.8 u tall, and each further dimension on a side of a view sits one LEVEL further out.
STEPS, LEVEL, GAP, TEXT = 46, 2.0, 3.5, 0.8
# The angle between a cylinder's axis and a view's, within which the view shows it as a circle.
SQUARE = math.cos(math.radians(1))

Vec = tuple[float, ...]  # a model point or direction: x, y, z
Frame = tuple[Vec, Vec, Vec]


def _dot(a: Vec, b: Vec) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _cross(a: Vec, b: Vec) -> Vec:
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def _unit(axis: str, sign: int = 1) -> Vec:
    return tuple(float(sign * (i == AXES[axis])) for i in range(3))


def frames(up: str) -> dict[str, Frame]:
    """Each view of an object standing on axis `up`, as the model directions that run right and
    up on the page and the one towards the viewer. With z up the front view shows X right and Z
    up, the top view X right and Y up, the right view Y right and Z up; with y up, X and Y, X and
    -Z, -Z and Y. The isometric view looks down on the front, right and top faces."""
    right = _unit("x")
    rise, toward = (_unit("z"), _unit("y", -1)) if up == "z" else (_unit("y"), _unit("z"))
    back = tuple(-c for c in toward)
    corner = tuple(r + t + u for r, t, u in zip(right, toward, rise))
    return {
        "front": (right, rise, toward),
        "top": (right, back, rise),
        "right": (back, rise, right),
        "isometric": (_cross(rise, corner), rise, corner),
    }


def _projected(shape, frame: Frame, diagonal: float) -> tuple[list, list]:
    """A shape's visible and hidden edges seen along a frame, each a polyline of (x, y) points on
    the page: x along the frame's right, y along its up."""
    from build123d import GeomType

    _, rise, toward = frame
    far = 10 * diagonal + 1
    seen = shape.project_to_viewport(tuple(far * c for c in toward), rise, (0, 0, 0))
    lines: tuple[list, list] = ([], [])
    for edges, kept in zip(seen, lines):
        for edge in edges:
            if edge.geom_type == GeomType.LINE:
                steps = 1
            else:  # enough chords that a small hole still reads as round
                steps = max(8, min(96, int(48 * edge.length / diagonal) + 12))
            points = [edge.position_at(i / steps) for i in range(steps + 1)]
            kept.append([(q.X, q.Y) for q in points])
    return lines


@dataclass
class _View:
    """One view of a part on its sheet: its frame, its edges, and where its page origin lies."""

    name: str
    frame: Frame
    visible: list
    hidden: list
    box: tuple[float, float, float, float]  # xmin, xmax, ymin, ymax of the part, in its own page
    at: tuple[float, float] = (0.0, 0.0)  # what is added to its own page to reach the sheet
    below: bool = True  # its horizontal dimensions stack below it, else above
    left: bool = True  # its vertical ones to its left, else its right
    # The dimensions stacked beside it, across the page and up it: each as its two model
    # points, its text, its colour and its length.
    across: list = field(default_factory=list)
    upright: list = field(default_factory=list)

    def on(self, point: Vec) -> tuple[float, float]:
        """A model point on the sheet."""
        return (
            _dot(point, self.frame[0]) + self.at[0],
            _dot(point, self.frame[1]) + self.at[1],
        )

    @property
    def width(self) -> float:
        return self.box[1] - self.box[0]

    @property
    def height(self) -> float:
        return self.box[3] - self.box[2]

    def shows(self, direction: Vec) -> bool:
        """Whether the view looks along direction, so a cylinder on it shows as a circle."""
        return abs(_dot(direction, self.frame[2])) >= SQUARE


class _Sheet:
    """The marks of one drawing, in sheet units, and the extent they cover."""

    def __init__(self, u: float):
        self.u = u
        self.lines: list[tuple[list, str, float, str]] = []  # points, colour, width, style
        self.texts: list[tuple[float, float, str, str, float, str, float]] = []
        self.arrows: list[tuple[tuple, tuple, str, bool]] = []  # tip, tail, colour, both ends
        self.callouts: list[tuple[float, float, float, float]] = []  # each callout's text box
        self.extent = [math.inf, math.inf, -math.inf, -math.inf]

    def cover(self, x: float, y: float) -> None:
        e = self.extent
        e[0], e[1], e[2], e[3] = min(e[0], x), min(e[1], y), max(e[2], x), max(e[3], y)

    def line(self, points, colour=INK, width=0.9, style="-", cover=True) -> None:
        """A line through points; one not covered is drawn only where the sheet's other marks
        reach."""
        self.lines.append((list(points), colour, width, style))
        for x, y in points if cover else ():
            self.cover(x, y)

    def text(self, x, y, text, colour, turn=0.0, ha="center", size=1.0) -> None:
        self.texts.append((x, y, text, colour, turn, ha, size))
        # Covered as a box about as wide as its letters, whichever way it is turned.
        wide, tall = len(text) * 0.6 * TEXT * self.u * size, TEXT * self.u * size
        if ha == "center":
            reach = max(wide / 2, tall) if turn else wide / 2
            self.cover(x - reach, y - (reach if turn else tall))
            self.cover(x + reach, y + (reach if turn else tall))
        else:
            self.cover(x, y - tall)
            self.cover(x + (wide if ha == "left" else -wide), y + tall)

    def arrow(self, tip, tail, colour, both=False) -> None:
        self.arrows.append((tip, tail, colour, both))
        self.cover(*tip)
        self.cover(*tail)

    def arc(self, centre, radius, start, end, colour=INK, width=0.5) -> None:
        steps = max(8, int(abs(end - start) / 5))
        angles = [math.radians(start + (end - start) * i / steps) for i in range(steps + 1)]
        self.line(
            [(centre[0] + radius * math.cos(a), centre[1] + radius * math.sin(a)) for a in angles],
            colour,
            width,
        )

    def dimension(self, view: _View, upright: bool, level: int, a, b, text, colour) -> None:
        """A dimension between sheet points a and b, measured across the page or up it, on the
        level-th line out from its view; an extension line runs to it from each point, or from
        the view's edge for a point given with None where it would lie."""
        u = self.u
        out = -1 if (view.left if upright else view.below) else 1
        low, high = (view.box[0], view.box[1]) if upright else (view.box[2], view.box[3])
        edge = (low if out < 0 else high) + view.at[0 if upright else 1]
        line = edge + out * (level + 1) * LEVEL * u
        ends = []
        for along, across in (a, b):
            start = (edge if across is None else across) + out * 0.4 * u
            if upright:
                self.line([(start, along), (line + out * 0.5 * u, along)], colour, 0.35)
            else:
                self.line([(along, start), (along, line + out * 0.5 * u)], colour, 0.35)
            ends.append((line, along) if upright else (along, line))
        self.arrow(ends[0], ends[1], colour, both=True)
        middle = ((ends[0][0] + ends[1][0]) / 2, (ends[0][1] + ends[1][1]) / 2)
        if upright:
            self.text(middle[0] - 0.75 * u, middle[1], text, colour, turn=90)
        else:
            self.text(middle[0], middle[1] + 0.75 * u, text, colour)

    def leader(self, centre, radius: float, toward, text: str, colour: str, on=None) -> None:
        """A callout of a circle, or of a point where radius is 0: an arrow to its edge from a
        shelf carrying the text, on the side toward a sheet point and clear of the callouts
        already placed. The arrow ends at `on` where that is given, a point known to lie on the
        edge, since an arc has no edge all the way round."""
        u = self.u
        wide, tall = len(text) * 0.6 * TEXT * u, 1.6 * TEXT * u

        def placed(angle: float) -> tuple:
            """The leader out at an angle: its tip, elbow, shelf end and side, and its text's
            box."""
            cos, sin = math.cos(math.radians(angle)), math.sin(math.radians(angle))
            tip = on or (centre[0] + radius * cos, centre[1] + radius * sin)
            elbow = (tip[0] + 3 * u * cos, tip[1] + 3 * u * sin)
            side = 1 if cos >= 0 else -1
            shelf = (elbow[0] + side * u, elbow[1])
            x0, x1 = sorted((shelf[0], shelf[0] + side * (wide + 0.3 * u)))
            return tip, elbow, shelf, side, (x0, shelf[1] - tall / 2, x1, shelf[1] + tall / 2)

        def clear(box: tuple) -> bool:
            return not any(
                box[0] < other[2] and other[0] < box[2] and box[1] < other[3] and other[1] < box[3]
                for other in self.callouts
            )

        aim = math.degrees(math.atan2(toward[1] - centre[1], toward[0] - centre[0]))
        angles = sorted((35, 145, 215, 325), key=lambda a: abs((a - aim + 180) % 360 - 180))
        # The nearest side to its aim that is clear, or the nearest where none is.
        tip, elbow, shelf, side, box = next(
            (found for found in map(placed, angles) if clear(found[4])), placed(angles[0])
        )
        self.callouts.append(box)
        self.arrow(tip, elbow, colour)
        self.line([elbow, shelf], colour, 0.5)
        self.text(
            shelf[0] + side * 0.3 * u, shelf[1], text, colour, ha="left" if side > 0 else "right"
        )


def _number(value: float) -> str:
    return f"{value:.5g}"


def _colour(results: dict[str, Result], rid) -> str | None:
    """The colour of the dimension a check's result gives; None where it was not evaluated."""
    result = results.get(str(rid))
    return None if result is None else CHECKED if result.ok else FAILED


def _layout(views: dict[str, _View], u: float) -> None:
    """Place the front view at the origin, the top view above it and the right view beside it,
    each clear of the dimensions stacked between them, and the isometric view in the corner."""
    front, top, right, iso = (views[name] for name in ("front", "top", "right", "isometric"))
    top.below, right.left = False, False
    front.at = (-front.box[0], -front.box[2])
    top.at = (-top.box[0], front.height + GAP * u - top.box[2])
    right.at = (front.width + GAP * u - right.box[0], -right.box[2])
    side = max(top.height, right.width, 0.45 * max(front.width, front.height))
    scale = side / max(iso.width, iso.height, 1e-9)
    for lines in (iso.visible, iso.hidden):
        lines[:] = [[(x * scale, y * scale) for x, y in line] for line in lines]
    x0, x1, y0, y1 = iso.box
    iso.box = (x0 * scale, x1 * scale, y0 * scale, y1 * scale)
    iso.at = (front.width + GAP * u - iso.box[0], front.height + GAP * u - iso.box[2])


def _linear(views: dict[str, _View], size: Vec, axis: Vec) -> tuple[_View, bool]:
    """The view a dimension along a model axis is drawn in, and whether it runs up the page: of
    the two views that show the axis, the one in which the part is larger across it."""
    front, top, right = (views[name] for name in ("front", "top", "right"))
    shown = [
        (view, abs(_dot(axis, view.frame[1])) > 0.5)
        for view in (front, top, right)
        if abs(_dot(axis, view.frame[2])) < 0.5
    ]

    def extent(choice) -> float:
        view, upright = choice
        other = view.frame[0 if upright else 1]
        return sum(abs(c) * s for c, s in zip(other, size))

    return max(shown, key=extent)


def _dimensions(p: Project, model: Model, part: str, results: dict[str, Result], views) -> list:
    """What a part's sheet is dimensioned by, as the marks to add once the views are placed:
    its envelope, each distance, diameter and angle check that reads it alone, and each thread
    declared on it."""
    solid = model.parts[part]
    box = solid.bounding_box()
    size, tol = tuple(box.size), p.length_tol
    front, top, right = (views[name] for name in ("front", "top", "right"))
    marks: list = []
    own = [c for c in p.checks if part_of(c, model) == part]

    def datums(names) -> list[tuple[float, float, float]]:
        """The points of the datums named, where each is one of this part's; else none."""
        if any(prefix(str(n), model.parts) != part or str(n) not in model.datums for n in names):
            return []
        return [model.datums[str(n)] for n in names]

    for c in own:
        kind, colour = c.get("kind"), _colour(results, str(c.get("id")))
        if colour is None:
            continue
        if kind == "distance" and (points := datums(c.get("between") or ())) and len(points) == 2:
            a, b = points
            delta = tuple(q - r for q, r in zip(b, a))
            along = c.get("along")
            value = released.datum_distance(points, along)
            if along is None:  # one that runs along an axis is drawn as one along it
                runs = [axis for axis, i in AXES.items() if abs(abs(delta[i]) - value) <= tol]
                along = runs[0] if runs else None
            if along in AXES:
                view, upright = _linear(views, size, _unit(along))
                entry = (a, b, _number(value), colour, value)
                (view.upright if upright else view.across).append(entry)
            else:
                view = max(
                    (front, top, right),
                    key=lambda v: math.hypot(_dot(delta, v.frame[0]), _dot(delta, v.frame[1])),
                )
                marks.append(("aligned", view, a, b, _number(value), colour))
        elif kind == "diameter" and (points := datums([c.get("at")])):
            try:
                found = released.cylinder_at(solid, points[0], tol, str(c["at"]))[:3]
            except Fault:
                continue
            marks.append(("round", found, f"Ø{_number(found[0])}", colour, points[0]))
        elif kind == "angle" and (points := datums(c.get("between") or ())) and len(points) == 3:
            try:
                value = released.angle_at(points, tol, c["between"], c.get("along"))
            except Fault:
                continue
            marks.append(("angle", points, c.get("along"), f"{_number(value)}°", colour))
    # The envelope: a bbox check's value, else a reference dimension no check compares, unless
    # a checked dimension already spans the part along that axis.
    enveloped = {}
    for c in own:
        if c.get("kind") == "bbox":
            for key, axis in (c.get("axes") or {}).items():
                colour = _colour(results, f"{c['id']}.{key}")
                if axis in AXES and colour:
                    enveloped[axis] = colour
    for axis, index in AXES.items():
        view, upright = _linear(views, size, _unit(axis))
        stacked = view.upright if upright else view.across
        text, colour = _number(size[index]), enveloped.get(axis)
        if colour or not any(abs(d[4] - size[index]) <= tol for d in stacked):
            ends = (None, None, text if colour else f"({text})", colour or REFERENCE)
            stacked.append((*ends, size[index]))
    for thread in model.threads:
        if thread.part == part:
            sized = p.thread_params[thread.param]
            cylinder = (thread.diameter, thread.origin, thread.direction)
            text = sized.thread.name
            if thread.fit == "threaded":
                # The thread as a drawing shows one: a thin three-quarter circle at the major
                # diameter around a hole, at the minor diameter inside a shank.
                marks.append(
                    ("thread", cylinder, (float(sized) if thread.hole else sized.minor) / 2)
                )
            else:
                text = f"Ø{_number(thread.diameter)} for {sized.thread.size}"
            marks.append(("round", cylinder, text, CHECKED, model.datums[thread.at]))
    return marks


def _mark(sheet: _Sheet, views: dict[str, _View], marks: list) -> None:
    """Add the marks that are not stacked dimensions: aligned dimensions, angles, cosmetic
    threads, and the callouts, those of one text in one view sharing a leader."""
    u = sheet.u
    front, top, right = (views[name] for name in ("front", "top", "right"))
    callouts: dict[tuple[str, str, str], list] = {}
    for mark in marks:
        if mark[0] == "aligned":
            _, view, a, b, text, colour = mark
            (ax, ay), (bx, by) = view.on(a), view.on(b)
            length = math.hypot(bx - ax, by - ay) or 1.0
            nx, ny = -(by - ay) / length, (bx - ax) / length
            centre = (view.at[0] + sum(view.box[:2]) / 2, view.at[1] + sum(view.box[2:]) / 2)
            if (ax + bx - 2 * centre[0]) * nx + (ay + by - 2 * centre[1]) * ny < 0:
                nx, ny = -nx, -ny
            off = 1.6 * u
            p1, p2 = (ax + nx * off, ay + ny * off), (bx + nx * off, by + ny * off)
            for start, end in (((ax, ay), p1), ((bx, by), p2)):
                sheet.line([start, (end[0] + nx * 0.4 * u, end[1] + ny * 0.4 * u)], colour, 0.35)
            sheet.arrow(p1, p2, colour, both=True)
            turn = math.degrees(math.atan2(by - ay, bx - ax))
            turn = turn + 180 if turn > 90 else turn - 180 if turn < -90 else turn
            mid = ((p1[0] + p2[0]) / 2 + nx * 0.75 * u, (p1[1] + p2[1]) / 2 + ny * 0.75 * u)
            sheet.text(mid[0], mid[1], text, colour, turn=turn)
        elif mark[0] == "angle":
            _, (a, vertex, b), along, text, colour = mark
            if along in AXES:
                normal = _unit(along)
            else:
                va, vb = (tuple(q - r for q, r in zip(end, vertex)) for end in (a, b))
                normal = _cross(va, vb)
            view = max((front, top, right), key=lambda v, n=normal: abs(_dot(n, v.frame[2])))
            (ax, ay), (vx, vy), (bx, by) = view.on(a), view.on(vertex), view.on(b)
            reach = min(math.hypot(ax - vx, ay - vy), math.hypot(bx - vx, by - vy))
            if reach <= 0:
                continue
            start = math.degrees(math.atan2(ay - vy, ax - vx))
            sweep = (math.degrees(math.atan2(by - vy, bx - vx)) - start + 180) % 360 - 180
            radius = min(0.7 * reach, 7 * u)
            for ex, ey in ((ax, ay), (bx, by)):
                sheet.line([(vx, vy), (ex, ey)], colour, 0.35)
            sheet.arc((vx, vy), radius, start, start + sweep, colour)
            mid = math.radians(start + sweep / 2)
            sheet.text(
                vx + (radius + 1.2 * u) * math.cos(mid),
                vy + (radius + 1.2 * u) * math.sin(mid),
                text,
                colour,
            )
        elif mark[0] == "thread":
            _, (_, origin, direction), radius = mark
            for view in (front, top, right):
                if view.shows(direction):
                    sheet.arc(view.on(origin), radius, 100, 370, INK, 0.45)
        else:
            _, (diameter, origin, direction), text, colour, point = mark
            view = next((v for v in (front, top, right) if v.shows(direction)), None)
            centre, radius = (view.on(origin), diameter / 2) if view else (front.on(point), 0.0)
            # A datum on the wall is where the arrow ends; one on the axis leaves that open.
            wall = (
                view.on(point) if view and math.dist(view.on(point), centre) > radius / 2 else None
            )
            callouts.setdefault(((view or front).name, text, colour), []).append(
                (centre, radius, wall)
            )
    for (name, text, colour), holes in callouts.items():
        view = views[name]
        middle = (view.at[0] + sum(view.box[:2]) / 2, view.at[1] + sum(view.box[2:]) / 2)
        # One leader for the holes of one callout, from the one nearest the view's middle and
        # toward it: the text then lies on the part, clear of the dimensions stacked around it.
        centre, radius, wall = min(holes, key=lambda h: math.dist(h[0], middle))
        count = f"{len(holes)}× " if len(holes) > 1 else ""
        sheet.leader(centre, radius, middle, count + text, colour, wall)


def _note_width(note: str) -> float:
    """The inches a sheet needs for a title's note, with its margin on either side."""
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    from matplotlib.figure import Figure

    figure = Figure(dpi=DPI)
    canvas = FigureCanvasAgg(figure)
    text = figure.text(0, 0, note, fontsize=NOTE, parse_math=False)
    return text.get_window_extent(canvas.get_renderer()).width / DPI / (1 - 2 * MARGIN)


def _paint(sheet: _Sheet, title: str, note: str, path: Path, authored: bool = False) -> None:
    """Write a sheet as a PNG, its marks scaled to fit under its title. An authored note holds
    the plan author's text: it prints as written, and the sheet widens to hold it."""
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    from matplotlib.collections import LineCollection
    from matplotlib.figure import Figure

    u = sheet.u
    x0, y0, x1, y1 = sheet.extent
    x0, y0, x1, y1 = x0 - 2 * u, y0 - 2 * u, x1 + 2 * u, y1 + 2 * u
    per_inch = max((x1 - x0) / WIDTH, (y1 - y0) / HEIGHT)
    wide = max((x1 - x0) / per_inch, NARROWEST, _note_width(note) if authored else 0.0)
    high = (y1 - y0) / per_inch
    figure = Figure(figsize=(wide, high + TITLE), dpi=DPI, facecolor="white")
    FigureCanvasAgg(figure)
    ax = figure.add_axes((0, 0, 1, high / (high + TITLE)))
    ax.set_xlim((x0 + x1) / 2 - wide * per_inch / 2, (x0 + x1) / 2 + wide * per_inch / 2)
    ax.set_ylim(y0, y1)
    ax.set_aspect("equal")
    ax.set_axis_off()
    size = TEXT * u / per_inch * 72  # a dimension's text, in points
    for colour, width, style in sorted({mark[1:] for mark in sheet.lines}, key=lambda m: m[1]):
        ax.add_collection(
            LineCollection(
                [
                    points
                    for points, *drawn in sheet.lines
                    if tuple(drawn) == (colour, width, style)
                ],
                colors=colour,
                linewidths=width,
                linestyles="solid" if style == "-" else (0, (4, 3)),
                capstyle="round",
            )
        )
    for tip, tail, colour, both in sheet.arrows:
        ax.annotate(
            "",
            xy=tip,
            xytext=tail,
            arrowprops={
                "arrowstyle": "<|-|>" if both else "-|>",
                "color": colour,
                "linewidth": 0.5,
                "mutation_scale": size * 0.9,
                "shrinkA": 0,
                "shrinkB": 0,
            },
        )
    for x, y, text, colour, turn, ha, scale in sheet.texts:
        ax.text(
            x,
            y,
            text,
            color=colour,
            fontsize=size * scale,
            rotation=turn,
            rotation_mode="anchor",
            ha=ha,
            va="center",
            bbox={"facecolor": "white", "edgecolor": "none", "pad": 0.6, "alpha": 0.85},
        )
    figure.text(
        MARGIN, 1 - 0.3 / (high + TITLE), title, fontsize=13, fontweight="bold", va="center"
    )
    figure.text(
        MARGIN,
        1 - 0.58 / (high + TITLE),
        note,
        fontsize=NOTE,
        color=REFERENCE,
        va="center",
        parse_math=not authored,
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(path, dpi=DPI)


def _making(p: Project, planned: dict | None, part: str) -> list[str]:
    """What a made part's title line says of how it is made: the material and the general
    tolerance, each where stated; nothing for a part the plan does not make, or with no plan."""
    if not planned or part not in {made["part"] for made in planned["make"]}:
        return []
    material = " ".join((p.meta.get("material") or "").split())
    general = planned.get("general_tolerance")
    return [item for item in (material, general and f"general tolerance {general}") if item]


def _part(
    p: Project, model: Model, part: str, results: dict[str, Result], making: list[str], path: Path
) -> None:
    solid = model.parts[part]
    box = solid.bounding_box()
    diagonal = box.diagonal
    views = {}
    for name, frame in frames(p.up).items():
        visible, hidden = _projected(solid, frame, diagonal)
        xs = [x for line in visible + hidden for x, _ in line] or [0.0]
        ys = [y for line in visible + hidden for _, y in line] or [0.0]
        views[name] = _View(name, frame, visible, hidden, (min(xs), max(xs), min(ys), max(ys)))
    front, top, right, iso = (views[n] for n in ("front", "top", "right", "isometric"))
    u = max(front.width + right.width, front.height + top.height) / STEPS
    sheet = _Sheet(u)
    marks = _dimensions(p, model, part, results, views)
    _layout(views, u)
    for view in views.values():
        pictorial = view is iso
        for line in view.visible:
            sheet.line([(x + view.at[0], y + view.at[1]) for x, y in line], INK, 0.9)
        for line in [] if pictorial else view.hidden:
            sheet.line([(x + view.at[0], y + view.at[1]) for x, y in line], HIDDEN, 0.4, "--")
        if not pictorial:
            for upright, stacked in ((False, view.across), (True, view.upright)):
                index = 1 if upright else 0
                levels: list[list[tuple[float, float]]] = []  # the spans taken on each level
                # Shorter dimensions first, each on the nearest level its span and its text
                # leave free, so a longer one sits further out than those it spans.
                for a, b, text, colour, _ in sorted(stacked, key=lambda d: d[4]):
                    # An envelope runs between the view's own edges, anything else from its points.
                    ends = [
                        (view.box[2 * index + i] + view.at[index], None)
                        if point is None
                        else (view.on(point)[index], view.on(point)[1 - index])
                        for i, point in enumerate((a, b))
                    ]
                    middle = (ends[0][0] + ends[1][0]) / 2
                    reach = max(abs(ends[0][0] - ends[1][0]), len(text) * 0.6 * TEXT * u) / 2 + u
                    span = (middle - reach, middle + reach)
                    level = next(
                        (
                            i
                            for i, taken in enumerate(levels)
                            if all(span[1] <= low or high <= span[0] for low, high in taken)
                        ),
                        len(levels),
                    )
                    levels[level:] = levels[level:] or [[]]
                    levels[level].append(span)
                    sheet.dimension(view, upright, level, ends[0], ends[1], text, colour)
        if not pictorial:  # named in the gap between the views, clear of its dimensions
            beside = view.box[2] - 1.1 * u if not view.below else view.box[3] + 1.1 * u
            label = (view.at[0] + view.box[0], view.at[1] + beside)
            sheet.text(*label, view.name.upper(), REFERENCE, ha="left", size=0.8)
    _mark(sheet, views, marks)
    note = " · ".join(
        [
            str(p.meta.get("name", "")),
            p.units["length"],
            "third-angle projection",
            *making,
            "as built: blue passes its check, red fails it, (grey) no check compares",
        ]
    )
    _paint(sheet, part, note, path, authored=bool(making))


def _assembly(p: Project, model: Model, path: Path) -> None:
    from build123d import Compound

    placed = Compound(
        children=[model.parts[part].moved(at) for part, at in model.assembly.values()]
    )
    box = placed.bounding_box()
    visible, _ = _projected(placed, frames(p.up)["isometric"], box.diagonal)
    xs = [x for line in visible for x, _ in line] or [0.0, 1.0]
    sheet = _Sheet((max(xs) - min(xs) or 1.0) / STEPS)
    for line in visible:
        sheet.line(line, INK, 0.8)
    parts = len({part for part, _ in model.assembly.values()})
    size = " × ".join(_number(s) for s in box.size)
    note = (
        f"isometric, {p.up} up · {parts} part{'s' * (parts != 1)} in {len(model.assembly)} "
        f"instance{'s' * (len(model.assembly) != 1)} · envelope {size} {p.units['length']}"
    )
    _paint(sheet, str(p.meta.get("name", "assembly")), note, path)


def _way_in(own, along: int, sign: int, boxes: list) -> tuple[float, float, float]:
    """An instance's box on its way in along an axis, in coordinates that grow toward where it
    comes from: its leading end and its trailing end as it rests, and the top of what stands in
    its path, or its leading end where nothing does."""
    lead, trail = sorted(sign * c[along] for c in (tuple(own.min), tuple(own.max)))
    tops = [
        max(sign * c[along] for c in (tuple(other.min), tuple(other.max)))
        for other in boxes
        if all(
            low < other_high and other_low < high
            for i, (low, high, other_low, other_high) in enumerate(
                zip(tuple(own.min), tuple(own.max), tuple(other.min), tuple(other.max))
            )
            if i != along
        )
    ]
    return lead, trail, max(tops, default=lead)


def _apart(direction: str | None, owns: list, boxes: list) -> Vec:
    """How far a step's instances are drawn from their place along the direction they come from,
    all by one distance: the furthest any needs to pass its own place and what stands in its
    path, and half its own size more. Nothing with no direction."""
    if direction is None:
        return (0.0, 0.0, 0.0)
    along, sign = AXES[direction[1]], 1 if direction[0] == "+" else -1

    def travel(own) -> float:
        lead, trail, top = _way_in(own, along, sign, boxes)
        return max(trail, top) - lead + own.diagonal / 2

    distance = max(travel(own) for own in owns)
    return tuple(sign * distance * (i == along) for i in range(3))


def _corners(up: str) -> dict[str, Frame]:
    """The eight isometric views of an object standing on axis `up`, by the corner each looks
    from (`+x-y+z`): the default first, then the others from above, then those from below."""
    right, rise, toward = frames(up)["front"]
    views = {}
    for over in (1, -1):
        for a, b in ((1, 1), (-1, 1), (-1, -1), (1, -1)):
            corner = tuple(a * r + b * t + over * u for r, t, u in zip(right, toward, rise))
            name = "".join(f"{'+' if c > 0 else '-'}{axis}" for axis, c in zip(AXES, corner))
            views[name] = (_cross(rise, corner), rise, corner)
    return views


def _shown(shape, others, frame: Frame) -> float:
    """The length of a shape's edges a view shows, with others, if any, in the way."""
    # OCP's modules re-export a compiled module whose names pyright cannot see, so they are
    # looked up by name.
    ocp = {
        module: importlib.import_module(f"OCP.{module}")
        for module in ("BRepGProp", "BRepLib", "gp", "GProp", "HLRAlgo", "HLRBRep")
    }
    _, rise, toward = frame
    camera = ocp["gp"].gp_Ax2(ocp["gp"].gp_Pnt(*toward), ocp["gp"].gp_Dir(*toward))
    camera.SetYDirection(ocp["gp"].gp_Dir(*rise))
    hidden = ocp["HLRBRep"].HLRBRep_Algo()
    hidden.Add(shape.wrapped)
    if others is not None:
        hidden.Add(others.wrapped)
    hidden.Projector(ocp["HLRAlgo"].HLRAlgo_Projector(camera))
    hidden.Update()
    hidden.Hide()
    lines = ocp["HLRBRep"].HLRBRep_HLRToShape(hidden)
    total = 0.0
    for edges in (
        lines.VCompound(shape.wrapped),
        lines.Rg1LineVCompound(shape.wrapped),
        lines.OutLineVCompound(shape.wrapped),
    ):
        if not edges.IsNull():
            ocp["BRepLib"].BRepLib.BuildCurves3d_s(edges)
            props = ocp["GProp"].GProp_GProps()
            ocp["BRepGProp"].BRepGProp.LinearProperties_s(edges, props)
            total += props.Mass()
    return total


def _best_corner(views: dict[str, Frame], shapes: list, others) -> str:
    """The corner that shows the most edge of the shapes past what stands in their way: the
    default where nothing hides them from it, else the first that shows the most, a later corner
    taking over only by more than 1%, so that a symmetric part keeps the earlier view."""
    default, frame = next(iter(views.items()))
    if others is None or all(
        _shown(shape, others, frame) >= 0.999 * _shown(shape, None, frame) for shape in shapes
    ):
        return default
    best, most = default, -1.0
    for name, frame in views.items():
        shown = sum(_shown(shape, others, frame) for shape in shapes)
        if shown > most * 1.01:
            best, most = name, shown
    return best


def _step(
    p: Project, model: Model, number: int, step: dict, new: list, before: list, fit: float, path
) -> None:
    """A step's view: the instances it places, drawn whole in black and each part named, over
    those of the steps before it that lie near them, in grey where the new ones leave them
    seen. Where the step names the direction they come from, they are drawn apart along it with
    a guideline to their place. fit is the gap across which one instance holds another, as
    held.check takes it."""
    from build123d import Compound, Location

    def placed(instances) -> list:
        return [model.parts[model.assembly[i][0]].moved(model.assembly[i][1]) for i in instances]

    solids = dict(zip(new, placed(new)))
    box = Compound(children=list(solids.values())).bounding_box()
    reach = box.diagonal / 2 + fit
    low, high = tuple(box.min), tuple(box.max)
    # What is already there, as far around the new instances as they are large, and a fit
    # further.
    near, boxes = [], []
    for solid in placed(before):
        other = solid.bounding_box()
        spans = zip(tuple(other.min), tuple(other.max), low, high)
        if all(a <= top + reach and b >= bottom - reach for a, b, bottom, top in spans):
            near.append(solid)
            boxes.append(other)
    direction = step.get("from")
    shift = _apart(direction, [solid.bounding_box() for solid in solids.values()], boxes)
    drawn = {inst: solid.moved(Location(shift)) for inst, solid in solids.items()}
    # Judged on the instances in their place, so the view shows where they land, and where they
    # are drawn. A compound takes its children from the last one, so each is built where it is
    # used.
    views = _corners(p.up)
    shapes = [Compound(children=list(solids.values()))]
    shapes += [Compound(children=list(drawn.values()))] * any(shift)
    seen_from = _best_corner(views, shapes, Compound(children=near) if near else None)
    frame = views[seen_from]
    _, rise, toward = frame
    diagonal = Compound(children=[*near, *drawn.values()]).bounding_box().diagonal
    inked, _ = _projected(Compound(children=list(drawn.values())), frame, diagonal)
    xs = [x for line in inked for x, _ in line] or [0.0, 1.0]
    sheet = _Sheet((max(xs) - min(xs) or 1.0) / STEPS)
    if near:
        seen, _ = _projected(Compound(children=[*near, *drawn.values()]), frame, diagonal)
        for line in seen:
            sheet.line(line, PLACED, 0.5, cover=False)
    for line in inked:
        sheet.line(line, INK, 1.1)
    # The view's own axes on the page, as OCC projects a point: across, and up.
    norm = math.sqrt(_dot(toward, toward))
    eye = tuple(c / norm for c in toward)
    across = _cross(rise, eye)
    norm = math.sqrt(_dot(across, across))
    across = tuple(c / norm for c in across)
    up = _cross(eye, across)

    def on_page(point) -> tuple[float, float]:
        return _dot(tuple(point), across), _dot(tuple(point), up)

    centres = {inst: on_page(solid.bounding_box().center()) for inst, solid in drawn.items()}
    if direction:  # from its leading face as drawn to where it enters what is there
        along, sign = AXES[direction[1]], 1 if direction[0] == "+" else -1
        for solid in solids.values():
            own = solid.bounding_box()
            lead, trail, top = _way_in(own, along, sign, boxes)
            centre = tuple(own.center())
            start = (*centre[:along], sign * lead + shift[along], *centre[along + 1 :])
            end = (*centre[:along], sign * min(trail, max(lead, top)), *centre[along + 1 :])
            sheet.arrow(on_page(end), on_page(start), GUIDE)
    x0, y0, x1, y1 = sheet.extent
    middle = ((x0 + x1) / 2, (y0 + y1) / 2)
    # The view takes in what each new instance goes onto, whole: the smallest instance already
    # there whose box meets its own, or lies within the fit of it, so a pin is seen on its plate
    # and not in mid-air.
    for solid in solids.values():
        own = solid.bounding_box()
        hosts = [
            other
            for other in boxes
            if all(
                a <= top + fit and b >= bottom - fit
                for a, b, bottom, top in zip(
                    tuple(other.min), tuple(other.max), tuple(own.min), tuple(own.max)
                )
            )
        ]
        if hosts:
            host = min(hosts, key=lambda other: other.diagonal)
            ends = list(zip(tuple(host.min), tuple(host.max)))
            for corner in ((x, y, z) for x in ends[0] for y in ends[1] for z in ends[2]):
                sheet.cover(*on_page(corner))
    x0, y0, x1, y1 = sheet.extent
    margin = 0.08 * max(x1 - x0, y1 - y0)
    sheet.cover(x0 - margin, y0 - margin)
    sheet.cover(x1 + margin, y1 + margin)
    sheet.u = (max(x1 - x0, y1 - y0) + 2 * margin) / STEPS  # names sized to the view as framed
    by_part: dict[str, list[str]] = {}
    for inst in new:
        by_part.setdefault(model.assembly[inst][0], []).append(inst)
    for part, instances in by_part.items():
        # Named at the instance furthest out, so the names ring the view.
        at = centres[max(instances, key=lambda i: math.dist(centres[i], middle))]
        away = (2 * at[0] - middle[0], 2 * at[1] - middle[1])
        count = f" ×{len(instances)}" * (len(instances) > 1)
        sheet.leader(at, 0.0, away, part + count, INK)
    note = f"{p.meta.get('name', '')} · black: what this step places · grey: already there"
    note += " · orange: where it goes" * any(shift)
    turned = seen_from != next(iter(views))
    note += f" · seen from {seen_from}" * turned
    _paint(sheet, f"step {number}", note, path)
    if turned:
        step["corner"] = seen_from


def render(
    p: Project, model: Model, results: list[Result], planned: dict | None, holds: dict | None
) -> list[Path]:
    """Write build/isometric.png, the assembly as built, build/drawings/<part>.png for each
    part that is one valid solid, and build/steps/<n>.png for each of the plan's steps that
    places an instance; the paths written, the isometric first where there is one. A sheet OCC
    cannot project is left out and said so: the run's verdict does not wait on a picture."""
    out = p.root / "build"
    by_id = {str(r.id): r for r in results}
    sheets = []
    if any(model.parts[part].edges() for part, _ in model.assembly.values()):
        sheets.append((out / "isometric.png", lambda path: _assembly(p, model, path)))
    for name, part in model.parts.items():
        # One that is no solid has its own finding, and nothing to draw.
        if part.is_valid and len(part.solids()) == 1 and part.edges():
            making = _making(p, planned, name)
            draw = lambda path, name=name, making=making: _part(  # noqa: E731
                p, model, name, by_id, making, path
            )
            sheets.append((out / "drawings" / f"{name}.png", draw))
    steps = planned["steps"] if planned else []
    fit = p.length_tol + ((holds or {}).get("clearance") or {}).get("value", 0.0)
    before: list[str] = []
    for number, step in enumerate(steps, 1):
        # An instance the assembly lacks, or one placed twice, is the plan's finding.
        new = [i for i in dict.fromkeys(step["place"]) if i in model.assembly and i not in before]
        if any(model.parts[model.assembly[i][0]].edges() for i in new):
            draw = lambda path, n=number, s=step, new=new, b=tuple(before): _step(  # noqa: E731
                p, model, n, s, new, list(b), fit, path
            )
            sheets.append((out / "steps" / f"{number:0{len(str(len(steps)))}d}.png", draw))
        before += new
    written = []
    for path, draw in sheets:
        try:
            draw(path)
        except Exception as exc:  # noqa: BLE001 - OCC's projection and matplotlib raise many types
            print(f"not drawn: {path.relative_to(p.root)} ({type(exc).__name__}: {exc})")
            continue
        written.append(path)
    return written
