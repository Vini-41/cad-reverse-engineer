"""The two thread tables a thread is named from: ISO metric and Unified.

A thread is a designation one of the tables holds (`M3`, `M8x1`, `1/4-20`, `6-32`), never a
diameter and a pitch made up beside them. The model builds its hole or shank as a plain cylinder
and declares the thread on it, so the table's sizes are what the cylinder is held to.
"""

from __future__ import annotations

import re
from typing import NamedTuple

STANDARDS = {"metric": "ISO metric", "unified": "Unified"}
INCH = 25.4  # millimetres

# ISO 261's sizes from M1 to M36: the coarse pitch first, then the fine pitches, and ISO 273's
# medium clearance hole. Millimetres.
_METRIC = {
    "1": ((0.25, 0.2), 1.2),
    "1.2": ((0.25, 0.2), 1.4),
    "1.4": ((0.3, 0.2), 1.6),
    "1.6": ((0.35, 0.2), 1.8),
    "2": ((0.4, 0.25), 2.4),
    "2.5": ((0.45, 0.35), 2.9),
    "3": ((0.5, 0.35), 3.4),
    "3.5": ((0.6, 0.35), 3.9),
    "4": ((0.7, 0.5), 4.5),
    "5": ((0.8, 0.5), 5.5),
    "6": ((1, 0.75), 6.6),
    "8": ((1.25, 1, 0.75), 9),
    "10": ((1.5, 1.25, 1, 0.75), 11),
    "12": ((1.75, 1.5, 1.25, 1), 13.5),
    "14": ((2, 1.5, 1.25, 1), 15.5),
    "16": ((2, 1.5, 1), 17.5),
    "18": ((2.5, 2, 1.5, 1), 20),
    "20": ((2.5, 2, 1.5, 1), 22),
    "22": ((2.5, 2, 1.5, 1), 24),
    "24": ((3, 2, 1.5, 1), 26),
    "27": ((3, 2, 1.5, 1), 30),
    "30": ((3.5, 3, 2, 1.5, 1), 33),
    "36": ((4, 3, 2, 1.5), 39),
}
# ASME B1.1's coarse and fine series from #0 to 1 in: the major diameter, the threads per inch
# of UNC then UNF, and ASME B18.2.8's normal clearance hole. Inches.
_UNIFIED = {
    "#0": (0.06, (None, 80), 0.076),
    "#2": (0.086, (56, 64), 0.1015),
    "#4": (0.112, (40, 48), 0.1285),
    "#5": (0.125, (40, 44), 0.1562),
    "#6": (0.138, (32, 40), 0.1695),
    "#8": (0.164, (32, 36), 0.196),
    "#10": (0.19, (24, 32), 0.221),
    "1/4": (0.25, (20, 28), 0.2812),
    "5/16": (0.3125, (18, 24), 0.3438),
    "3/8": (0.375, (16, 24), 0.4062),
    "7/16": (0.4375, (14, 20), 0.4688),
    "1/2": (0.5, (13, 20), 0.5625),
    "5/8": (0.625, (11, 18), 0.6875),
    "3/4": (0.75, (10, 16), 0.8125),
    "7/8": (0.875, (9, 14), 0.9375),
    "1": (1.0, (8, 12), 1.0938),
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
_PRINTED = [
    re.compile(rf"(?<![\w./#-])(?:{name.pattern})(?![\w/]|[.-]\d)")
    for name in (_METRIC_NAME, _UNIFIED_NAME)
]


class Thread(NamedTuple):
    """A thread of one of the tables, its sizes in millimetres."""

    name: str  # as the report and a drawing print it: M3×0.5, 1/4-20 UNC
    size: str  # its screw's size alone: M3, 1/4, #6
    standard: str  # metric or unified
    major: float
    pitch: float
    clearance: float  # its clearance hole: ISO 273 medium, ASME B18.2.8 normal

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
    pitch: float
    tap: float
    minor: float
    clearance: float

    def __new__(cls, thread: Thread, per_mm: float) -> Size:
        size = super().__new__(cls, thread.major * per_mm)
        size.thread = thread
        for name in ("pitch", "tap", "minor", "clearance"):
            setattr(size, name, getattr(thread, name) * per_mm)
        return size


def _metric(size: str, pitch: str | None) -> Thread | None:
    entry = _METRIC.get(f"{float(size):g}")
    if entry is None:
        return None
    pitches, clearance = entry
    chosen = pitches[0] if pitch is None else float(pitch)
    if chosen not in pitches:
        return None
    name = f"M{float(size):g}"
    return Thread(f"{name}×{chosen:g}", name, "metric", float(size), chosen, clearance)


def _unified(size: str, per_inch: str, series: str | None) -> Thread | None:
    entry = _UNIFIED.get(size)
    if entry is None:
        return None
    major, counts, clearance = entry
    count = int(per_inch)
    if count not in counts or (series and _SERIES[counts.index(count)] != series.upper()):
        return None
    name = f"{size}-{count} {_SERIES[counts.index(count)]}"
    return Thread(name, size, "unified", major * INCH, INCH / count, clearance * INCH)


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
    with its threads per inch (1/4-20), or a number size marked by its # or its series
    (#6-32, 6-32 UNC). A bare 6-32 may be a range, so it is left to the reader."""
    spans = []
    for m in _PRINTED[1].finditer(text):
        marked = (m[1] is not None and m[1] != "1") or m[0].startswith("#") or m[4]
        if marked and _read(None, m) is not None:
            spans.append(m.span())
    return spans


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
