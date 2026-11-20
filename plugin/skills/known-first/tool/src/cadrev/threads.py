"""The two thread tables a thread is named from, ISO metric and Unified, and the lengths a screw
of each is bought in.

A thread is a designation one of the tables holds (`M3`, `M8x1`, `1/4-20`, `6-32`), never a
diameter and a pitch made up beside them. The model builds its hole or shank as a plain cylinder
and declares the thread on it, so the table's sizes are what the cylinder is held to. A screw is
a thread and a length, and a proposed one's length is a standard length of its thread's table.
"""

from __future__ import annotations

import re
from fractions import Fraction
from typing import NamedTuple

STANDARDS = {"metric": "ISO metric", "unified": "Unified"}
INCH = 25.4  # millimetres
# The project length units of the inch, in which a proposed thread is a Unified one.
INCH_UNITS = ("in", "ft", "thou")

# ISO 888's nominal lengths from 2 to 300 mm, less those it brackets as to be avoided where
# possible. Millimetres.
_METRIC_LENGTHS = (
    2, 3, 4, 5, 6, 8, 10, 12, 16, 20, 25, 30, 35, 40, 45, 50, 55, 60, 65, 70, 80, 90, 100, 110,
    120, 130, 140, 150, 160, 180, 200, 220, 240, 260, 280, 300,
)  # fmt: skip
# ASME B18.3's standard length increments, from 1/8 in: up to each length, in steps of. Inches.
_UNIFIED_STEPS = (
    (Fraction(1, 4), Fraction(1, 16)),
    (Fraction(1), Fraction(1, 8)),
    (Fraction(7, 2), Fraction(1, 4)),
    (Fraction(7), Fraction(1, 2)),
    (Fraction(10), Fraction(1)),
)

# ISO 261's first- and second-choice diameters from M1 to M39: the coarse pitch first, then the
# fine pitches of its table 2, and ISO 273's clearance holes of the medium series and of the
# coarse, its loosest, None where it lists none. Millimetres.
_METRIC = {
    "1": ((0.25, 0.2), (1.2, 1.3)),
    "1.1": ((0.25, 0.2), None),
    "1.2": ((0.25, 0.2), (1.4, 1.5)),
    "1.4": ((0.3, 0.2), (1.6, 1.8)),
    "1.6": ((0.35, 0.2), (1.8, 2)),
    "1.8": ((0.35, 0.2), (2.1, 2.2)),
    "2": ((0.4, 0.25), (2.4, 2.6)),
    "2.2": ((0.45, 0.25), None),
    "2.5": ((0.45, 0.35), (2.9, 3.1)),
    "3": ((0.5, 0.35), (3.4, 3.6)),
    "3.5": ((0.6, 0.35), (3.9, 4.2)),
    "4": ((0.7, 0.5), (4.5, 4.8)),
    "4.5": ((0.75, 0.5), (5, 5.3)),
    "5": ((0.8, 0.5), (5.5, 5.8)),
    "6": ((1, 0.75), (6.6, 7)),
    "7": ((1, 0.75), (7.6, 8)),
    "8": ((1.25, 1, 0.75), (9, 10)),
    "10": ((1.5, 1.25, 1, 0.75), (11, 12)),
    "12": ((1.75, 1.5, 1.25, 1), (13.5, 14.5)),
    "14": ((2, 1.5, 1.25, 1), (15.5, 16.5)),
    "16": ((2, 1.5, 1), (17.5, 18.5)),
    "18": ((2.5, 2, 1.5, 1), (20, 21)),
    "20": ((2.5, 2, 1.5, 1), (22, 24)),
    "22": ((2.5, 2, 1.5, 1), (24, 26)),
    "24": ((3, 2, 1.5, 1), (26, 28)),
    "27": ((3, 2, 1.5, 1), (30, 32)),
    "30": ((3.5, 3, 2, 1.5, 1), (33, 35)),
    "33": ((3.5, 3, 2, 1.5), (36, 38)),
    "36": ((4, 3, 2, 1.5), (39, 42)),
    "39": ((4, 3, 2, 1.5), (42, 45)),
}
# ASME B1.1's coarse and fine series from #0 to 1 in: the major diameter, the threads per inch
# of UNC then UNF, and the clearance holes of ASME B18.2.8's table 2 for the normal fit and for
# the loose, None where it lists none. Inches.
_UNIFIED = {
    "#0": (0.06, (None, 80), (0.076, 0.094)),
    "#1": (0.073, (64, 72), (0.089, 0.104)),
    "#2": (0.086, (56, 64), (0.102, 0.116)),
    "#3": (0.099, (48, 56), (0.116, 0.128)),
    "#4": (0.112, (40, 48), (0.128, 0.144)),
    "#5": (0.125, (40, 44), (0.156, 0.172)),
    "#6": (0.138, (32, 40), (0.17, 0.185)),
    "#8": (0.164, (32, 36), (0.196, 0.213)),
    "#10": (0.19, (24, 32), (0.221, 0.238)),
    "#12": (0.216, (24, 28), None),
    "1/4": (0.25, (20, 28), (0.281, 0.297)),
    "5/16": (0.3125, (18, 24), (0.344, 0.359)),
    "3/8": (0.375, (16, 24), (0.406, 0.422)),
    "7/16": (0.4375, (14, 20), (0.469, 0.484)),
    "1/2": (0.5, (13, 20), (0.562, 0.609)),
    "9/16": (0.5625, (12, 18), None),
    "5/8": (0.625, (11, 18), (0.688, 0.734)),
    "3/4": (0.75, (10, 16), (0.812, 0.906)),
    "7/8": (0.875, (9, 14), (0.938, 1.031)),
    "1": (1.0, (8, 12), (1.094, 1.156)),
}
_SERIES = ("UNC", "UNF")

_NUMBER = r"\d+(?:\.\d+)?"
# M3, M2.5x0.45, M8 × 1: a capital M, since m3 is a volume and m1 a gear's module.
_METRIC_NAME = re.compile(rf"M({_NUMBER})(?:\s?[xX×]\s?({_NUMBER}))?")
# 1/4-20, 1/4"-20 UNC, #6-32, No. 6-32, 6-32: a size, then its threads per inch.
_UNIFIED_NAME = re.compile(
    r"(?:(\d+/\d+|1)\s?(?:\"|″|''|in\.?|inch)?|(?:#|(?i:no\.?)\s?)?(\d+))"
    r"\s?-\s?(\d+)(?:\s?((?i:un[cf])))?"
)
# As a statement prints one: alone, or called out by the count of its holes as a drawing does
# (4-M3, 4xM3, and 8-M 2.0 as some datasheets space it).
_ALONE, _PRINTED_END = r"(?<![\w./#-])", r"(?![\w/]|[.-]\d)"
_PRINTED = [
    re.compile(
        rf"(?:{_ALONE}M|(?:(?<=\d-)|(?<=\d[xX×]))M\s?)({_NUMBER})"
        rf"(?:\s?[xX×]\s?({_NUMBER}))?{_PRINTED_END}"
    ),
    re.compile(rf"{_ALONE}(?:{_UNIFIED_NAME.pattern}){_PRINTED_END}"),
]


class Thread(NamedTuple):
    """A thread of one of the tables, its sizes in millimetres."""

    name: str  # as the report and a drawing print it: M3×0.5, 1/4-20 UNC
    size: str  # its screw's size alone: M3, 1/4, #6
    standard: str  # metric or unified
    major: float
    pitch: float
    # Its clearance hole and the loosest its table gives, where it gives the size any.
    clearance: float | None
    loosest: float | None

    @property
    def tap(self) -> float:
        """Its tap drill: the major diameter less the pitch."""
        return self.major - self.pitch

    @property
    def minor(self) -> float:
        """The basic minor diameter of its internal thread, which both tables share a profile
        for."""
        return self.major - 1.082532 * self.pitch


class Size(float):
    """A thread param's value, its major diameter in the project's length unit, with the sizes
    model.py builds its hole or shank from in that unit too."""

    thread: Thread
    per_mm: float

    def __new__(cls, thread: Thread, per_mm: float) -> Size:
        size = super().__new__(cls, thread.major * per_mm)
        size.thread, size.per_mm = thread, per_mm
        return size

    @property
    def pitch(self) -> float:
        return self.thread.pitch * self.per_mm

    @property
    def tap(self) -> float:
        return self.thread.tap * self.per_mm

    @property
    def minor(self) -> float:
        return self.thread.minor * self.per_mm

    @property
    def clearance(self) -> float:
        if self.thread.clearance is None:
            raise AttributeError(
                f"{self.thread.name} has no clearance hole in its table; give that hole's "
                "diameter a param"
            )
        return self.thread.clearance * self.per_mm


def _metric(size: str, pitch: str | None) -> Thread | None:
    entry = _METRIC.get(f"{float(size):g}")
    if entry is None:
        return None
    pitches, holes = entry
    chosen = pitches[0] if pitch is None else float(pitch)
    if chosen not in pitches:
        return None
    name = f"M{float(size):g}"
    return Thread(
        f"{name}×{chosen:g}", name, "metric", float(size), chosen, *(holes or (None,) * 2)
    )


def _unified(size: str, per_inch: str, series: str | None) -> Thread | None:
    entry = _UNIFIED.get(size)
    if entry is None:
        return None
    major, counts, holes = entry
    count = int(per_inch)
    if count not in counts or (series and _SERIES[counts.index(count)] != series.upper()):
        return None
    name = f"{size}-{count} {_SERIES[counts.index(count)]}"
    normal, loosest = (hole * INCH for hole in holes) if holes else (None, None)
    return Thread(name, size, "unified", major * INCH, INCH / count, normal, loosest)


def _read(metric: re.Match | None, unified: re.Match | None) -> Thread | None:
    if metric is not None:
        return _metric(metric[1], metric[2])
    if unified is not None:
        return _unified(unified[1] or f"#{unified[2]}", unified[3], unified[4])
    return None


def named(designation) -> Thread | None:
    """The thread a designation names, or None where neither table holds it."""
    text = str(designation).strip()
    return _read(_METRIC_NAME.fullmatch(text), _UNIFIED_NAME.fullmatch(text))


def printed_in(text: str) -> list[Thread]:
    """Each thread a quote or a reading prints, in either table. A size printed before a length
    (an M3x10 screw) is that size's coarse thread."""
    metric, unified = _PRINTED
    found = [_metric(m[1], m[2]) or _metric(m[1], None) for m in metric.finditer(text)]
    found += [_read(None, m) for m in unified.finditer(text)]
    return [thread for thread in found if thread is not None]


def unified_spans(text: str) -> list[tuple[int, int]]:
    """Where normalized text prints a Unified thread that reads no other way: a fraction size
    with its threads per inch (1/4-20), or a number size marked by its #, its No. or its
    series (#6-32, No. 6-32, 6-32 UNC). A bare 6-32 may be a range, so it is left to the reader."""
    spans = []
    for m in _PRINTED[1].finditer(text):
        marked = (m[1] is not None and m[1] != "1") or not m[0][0].isdigit() or m[4]
        if marked and _read(None, m) is not None:
            spans.append(m.span())
    return spans


def _unified_lengths() -> tuple[Fraction, ...]:
    found, length = [Fraction(1, 8)], Fraction(1, 8)
    for up_to, step in _UNIFIED_STEPS:
        while length < up_to:
            length += step
            found.append(length)
    return tuple(found)


_UNIFIED_LENGTHS = _unified_lengths()


def lengths(standard: str) -> tuple[float, ...]:
    """The standard screw lengths of a table, shortest first, in millimetres."""
    if standard == "metric":
        return tuple(float(length) for length in _METRIC_LENGTHS)
    return tuple(float(length) * INCH for length in _UNIFIED_LENGTHS)


def standard_length(thread: Thread, length: float, tol: float) -> float | None:
    """The standard length of a thread's table within tol of a length, both in millimetres;
    None where the length is none of them."""
    nearest = min(lengths(thread.standard), key=lambda standard: abs(standard - length))
    return nearest if abs(nearest - length) <= tol else None


def neighbours(thread: Thread, length: float) -> list[float]:
    """The standard lengths of a thread's table on either side of a length, in millimetres."""
    below = [standard for standard in lengths(thread.standard) if standard < length]
    above = [standard for standard in lengths(thread.standard) if standard > length]
    return below[-1:] + above[:1]


def length_text(thread: Thread, length: float) -> str:
    """A length in millimetres as its thread's table prints it: 10 mm, or 3/8 in."""
    if thread.standard == "metric":
        return f"{float(f'{length:.6g}'):g} mm"
    inches = Fraction(length / INCH).limit_denominator(64)
    # A binary fraction of an inch, as a rule and a catalogue print one; any other in decimals.
    if 64 % inches.denominator or abs(float(inches) - length / INCH) > 1e-6:
        return f"{float(f'{length / INCH:.6g}'):g} in"
    whole, part = divmod(inches, 1)
    return f"{'-'.join(str(n) for n in (whole, part) if n)} in"


def screw(thread: Thread, length: float) -> str:
    """A screw as it is ordered, its thread and its length in millimetres: M3×10, M8×1×25,
    1/4-20 UNC × 3/4 in. A coarse metric thread goes without its pitch."""
    printed = length_text(thread, length)
    if thread.standard == "unified":
        return f"{thread.name} × {printed}"
    coarse = _METRIC[thread.size[1:]][0][0]
    pitch = "" if thread.pitch == coarse else f"×{thread.pitch:g}"
    return f"{thread.size}{pitch}×{printed.removesuffix(' mm')}"


def sizes(standard: str) -> str:
    """The sizes of a table, as a finding lists them."""
    if standard == "metric":
        return ", ".join(f"M{size}" for size in _METRIC)
    return ", ".join(
        f"{size}-{count}" for size, (_, counts, _) in _UNIFIED.items() for count in counts if count
    )


def pitches(designation) -> str | None:
    """For a designation whose size a table holds but whose pitch it does not, the pitches that
    size takes, as a finding lists them; None where no table holds the size."""
    text = str(designation).strip()
    if (m := _METRIC_NAME.fullmatch(text)) and (entry := _METRIC.get(f"{float(m[1]):g}")):
        coarse, *fine = entry[0]
        return f"M{float(m[1]):g} takes pitch {coarse:g} (coarse)" + (
            f" or {', '.join(f'{p:g}' for p in fine)}" if fine else ""
        )
    if (m := _UNIFIED_NAME.fullmatch(text)) and (entry := _UNIFIED.get(m[1] or f"#{m[2]}")):
        size = m[1] or f"#{m[2]}"
        return f"{size} takes " + " or ".join(
            f"{count} threads per inch ({series})"
            for count, series in zip(entry[1], _SERIES)
            if count
        )
    return None
