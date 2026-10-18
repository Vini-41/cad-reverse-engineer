"""The built-in unit table: what each unit printed in a quote measures, and how large it is.

Spellings are matched in normalized text (NFKC, lower case), so `MPa` is `mpa` and `N·m` is
`n·m`; where lower case leaves two readings the one hardware papers use wins (`mn` is mN, `nm`
is N·m). Sizes are in SI units of the quantity.
"""

from __future__ import annotations

import re

# The quantities a project's `units` may set, with the unit used when it sets none.
BASE = {"length": "mm", "angle": "deg", "mass": "g", "force": "N", "time": "s"}
# Every other quantity is measured in the project's base units: torque in N·mm by default.
DERIVED = {"torque": {"force": 1, "length": 1}, "pressure": {"force": 1, "length": -2},
           "density": {"mass": 1, "length": -3}, "speed": {"length": 1, "time": -1}}

# "in" before a determiner is the word ("4 in total", "2 in each leg"), not inches.
INCH_IN = r"in(?!\s(?:the|a|an|each|every|all|total|both|this|that|these|those|its|their|which|series|parallel)\b)"
_SEP = r"(?:\s?[·⋅*]\s?|[.-])?"  # between the parts of a compound unit: N·m, kg ·cm, N.m, Nm
_CUBED = r"(?:3|\^3)"  # NFKC turns ³ into 3
_PER_CC = rf"(?:/\s?cm{_CUBED}|/\s?cc|/\s?ml|{_SEP}cm-3)"  # g/cm³, g/cc, g/ml, g·cm⁻³

# name: (quantity, size in SI, spellings as regexes). Compound units come first, so `n·m`
# is read as a torque before `n` could be read as a force.
UNITS: dict[str, tuple[str, float, tuple[str, ...]]] = {
    "g/cm³": ("density", 1e3, (rf"g{_PER_CC}",)),
    "kg/m³": ("density", 1.0, (rf"kg/\s?m{_CUBED}", rf"kg{_SEP}m-3")),
    "g/mm³": ("density", 1e6, (rf"g/\s?mm{_CUBED}",)),
    "N·m": ("torque", 1.0, (rf"n{_SEP}m",)),
    "N·mm": ("torque", 1e-3, (rf"n{_SEP}mm",)),
    "N·cm": ("torque", 1e-2, (rf"n{_SEP}cm",)),
    "mN·m": ("torque", 1e-3, (rf"mn{_SEP}m",)),
    "kgf·cm": ("torque", 9.80665e-2, (rf"kgf?{_SEP}cm",)),
    "mm/s": ("speed", 1e-3, (r"mm/s",)),
    "cm/s": ("speed", 1e-2, (r"cm/s",)),
    "m/s": ("speed", 1.0, (r"m/s",)),
    "km/h": ("speed", 1 / 3.6, (r"km/h",)),
    "MPa": ("pressure", 1e6, (r"mpa", r"n/\s?mm(?:2|\^2)")),
    "GPa": ("pressure", 1e9, (r"gpa",)),
    "kPa": ("pressure", 1e3, (r"kpa",)),
    "Pa": ("pressure", 1.0, (r"pa",)),
    "bar": ("pressure", 1e5, (r"bar",)),
    "psi": ("pressure", 6894.757293168, (r"psi",)),
    "mm": ("length", 1e-3, (r"mm", r"millimet(?:er|re)s?")),
    "cm": ("length", 1e-2, (r"cm", r"centimet(?:er|re)s?")),
    "µm": ("length", 1e-6, (r"μm", r"um", r"microns?", r"micromet(?:er|re)s?")),
    "m": ("length", 1.0, (r"m", r"met(?:er|re)s?")),
    "in": ("length", 0.0254, (INCH_IN, r"inch(?:es)?", r'"', r"′′")),
    "ft": ("length", 0.3048, (r"ft", r"foot", r"feet")),
    "deg": ("angle", 0.017453292519943295, (r"deg", r"degrees?", r"°", r"◦")),
    "rad": ("angle", 1.0, (r"rad", r"radians?")),
    "mg": ("mass", 1e-6, (r"mg", r"milligrams?")),
    "g": ("mass", 1e-3, (r"g", r"grams?")),
    "kg": ("mass", 1.0, (r"kg", r"kilograms?")),
    "kN": ("force", 1e3, (r"kn",)),
    "mN": ("force", 1e-3, (r"mn",)),
    "N": ("force", 1.0, (r"n", r"newtons?")),
    "kgf": ("force", 9.80665, (r"kgf",)),
    "ms": ("time", 1e-3, (r"ms",)),
    "s": ("time", 1.0, (r"s", r"secs?", r"seconds?")),
    "min": ("time", 60.0, (r"min", r"mins", r"minutes?")),
    "h": ("time", 3600.0, (r"h", r"hrs?", r"hours?")),
}


def spelling(but: tuple[str, ...] = ()) -> str:
    """A regex matching any unit's spelling as a whole word, leaving out the spellings in but."""
    words = "|".join(s for _, _, spellings in UNITS.values() for s in spellings if s not in but)
    return rf"(?:{words})(?![a-z0-9/^])"


_FOLLOWING = re.compile(rf"\s?({spelling()})")
_SPELLED = {name: re.compile(rf"(?:{'|'.join(spellings)})") for name, (_, _, spellings) in UNITS.items()}


def unit_at(text: str, pos: int) -> tuple[str, int] | None:
    """The unit printed at text[pos:] (normalized text, one optional space first) and where its
    spelling ends, or None."""
    m = _FOLLOWING.match(text, pos)
    if m is None:
        return None
    return next(name for name, spelled in _SPELLED.items() if spelled.fullmatch(m.group(1))), m.end()


def named(spelled: str) -> str | None:
    """The unit a project file names (`mm`, `millimetres`, `N`), or None if none is."""
    text = spelled.strip().lower()
    return next((name for name, s in _SPELLED.items() if s.fullmatch(text)), None)


def quantity(unit: str) -> str:
    return UNITS[unit][0]


def size(q: str, chosen: dict[str, str]) -> float:
    """The SI size of one project unit of quantity q, given the unit chosen for each base quantity."""
    if q in BASE:
        return UNITS[chosen.get(q, BASE[q])][1]
    out = 1.0
    for base, power in DERIVED[q].items():
        out *= size(base, chosen) ** power
    return out


def convert(value: float, unit: str, chosen: dict[str, str]) -> float:
    """value in unit, expressed in the project's unit of the same quantity."""
    q, si, _ = UNITS[unit]
    return value * si / size(q, chosen)
