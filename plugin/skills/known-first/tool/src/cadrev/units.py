"""The built-in unit table: what each unit printed in a quote measures, and how large it is.

Spellings are matched in normalized text (NFKC, lower case), so `MPa` is `mpa` and `N·m` is
`n·m`; where lower case leaves two readings the one hardware papers use wins (`mn` is mN, `nm`
is N·m). Sizes are in SI units of the quantity.
"""

from __future__ import annotations

import re
from typing import NamedTuple

# The quantities a project's `units` may set, with the unit used when it sets none.
BASE = {"length": "mm", "angle": "deg", "mass": "g", "force": "N", "time": "s"}
# Every other quantity is measured in the project's base units: torque in N·mm by default.
# Those built from none (a fraction, a count, a charge) stay in SI: 40% is 0.4.
DERIVED = {
    "torque": {"force": 1, "length": 1},
    "pressure": {"force": 1, "length": -2},
    "density": {"mass": 1, "length": -3},
    "speed": {"length": 1, "time": -1},
    "area": {"length": 2},
    "volume": {"length": 3},
    "angular speed": {"angle": 1, "time": -1},
    # The physics values a joint or tendon applies: a spring, a damper; per radian, whatever the
    # project's angle unit, as a simulator reads them.
    "torsional stiffness": {"force": 1, "length": 1},
    "torsional damping": {"force": 1, "length": 1, "time": 1},
    "linear stiffness": {"force": 1, "length": -1},
    "linear damping": {"force": 1, "time": 1, "length": -1},
    "fraction": {},
    "count": {},
    "charge": {},
}

# "in" before a determiner is the word ("4 in total", "2 in each leg"), not inches.
INCH_IN = (
    r"in(?!\s(?:the|a|an|each|every|all|total|both|this|that|these|those|its|their|which"
    r"|series|parallel)\b)"
)
_SEP = r"(?:\s?[·⋅*]\s?|[.-])?"  # between the parts of a compound unit: N·m, kg ·cm, N.m, Nm
_CUBED = r"(?:3|\^3)"  # NFKC turns ³ into 3
_PER_CC = rf"(?:/\s?cm{_CUBED}|/\s?cc|/\s?ml|{_SEP}cm-3)"  # g/cm³, g/cc, g/ml, g·cm⁻³
_SQUARED = r"(?:2|\^2)"  # NFKC turns ² into 2


class Unit(NamedTuple):
    quantity: str
    si: float  # the size of one of it in SI units of its quantity
    spellings: tuple[str, ...]  # regexes over normalized text


# Compound units come first, so `n·m` is read as a torque before `n` could be read as a force,
# and `n·m·s/rad` as a damping before `n·m` could be read as a torque.
_PER_RAD = r"/\s?rad"
UNITS: dict[str, Unit] = {
    "N·m·s/rad": Unit("torsional damping", 1.0, (rf"n{_SEP}m{_SEP}s{_PER_RAD}",)),
    "N·mm·s/rad": Unit("torsional damping", 1e-3, (rf"n{_SEP}mm{_SEP}s{_PER_RAD}",)),
    "N·m/rad": Unit("torsional stiffness", 1.0, (rf"n{_SEP}m{_PER_RAD}",)),
    "N·mm/rad": Unit("torsional stiffness", 1e-3, (rf"n{_SEP}mm{_PER_RAD}",)),
    "N·s/m": Unit("linear damping", 1.0, (rf"n{_SEP}s/\s?m",)),
    "N·s/mm": Unit("linear damping", 1e3, (rf"n{_SEP}s/\s?mm",)),
    "N/m": Unit("linear stiffness", 1.0, (r"n/\s?m",)),
    "N/mm": Unit("linear stiffness", 1e3, (r"n/\s?mm",)),
    "g/cm³": Unit("density", 1e3, (rf"g{_PER_CC}",)),
    "kg/m³": Unit("density", 1.0, (rf"kg/\s?m{_CUBED}", rf"kg{_SEP}m-3")),
    "g/mm³": Unit("density", 1e6, (rf"g/\s?mm{_CUBED}",)),
    "N·m": Unit("torque", 1.0, (rf"n{_SEP}m",)),
    "N·mm": Unit("torque", 1e-3, (rf"n{_SEP}mm",)),
    "N·cm": Unit("torque", 1e-2, (rf"n{_SEP}cm",)),
    "mN·m": Unit("torque", 1e-3, (rf"mn{_SEP}m",)),
    "kgf·cm": Unit("torque", 9.80665e-2, (rf"kgf?{_SEP}cm",)),
    "mm/s": Unit("speed", 1e-3, (r"mm/s",)),
    "cm/s": Unit("speed", 1e-2, (r"cm/s",)),
    "m/s": Unit("speed", 1.0, (r"m/s",)),
    "km/h": Unit("speed", 1 / 3.6, (r"km/h",)),
    "MPa": Unit("pressure", 1e6, (r"mpa", r"n/\s?mm(?:2|\^2)")),
    "GPa": Unit("pressure", 1e9, (r"gpa",)),
    "kPa": Unit("pressure", 1e3, (r"kpa",)),
    "Pa": Unit("pressure", 1.0, (r"pa",)),
    "bar": Unit("pressure", 1e5, (r"bar",)),
    "psi": Unit("pressure", 6894.757293168, (r"psi",)),
    "rpm": Unit("angular speed", 0.10471975511965977, (r"rpm", r"r/min")),
    "rad/s": Unit("angular speed", 1.0, (r"rad/s",)),
    "mm²": Unit("area", 1e-6, (rf"mm{_SQUARED}",)),
    "cm²": Unit("area", 1e-4, (rf"cm{_SQUARED}",)),
    "m²": Unit("area", 1.0, (rf"m{_SQUARED}",)),
    "mm³": Unit("volume", 1e-9, (rf"mm{_CUBED}",)),
    "cm³": Unit("volume", 1e-6, (rf"cm{_CUBED}", r"cc", r"ml")),
    "m³": Unit("volume", 1.0, (rf"m{_CUBED}",)),
    "mm": Unit("length", 1e-3, (r"mm", r"millimet(?:er|re)s?")),
    "cm": Unit("length", 1e-2, (r"cm", r"centimet(?:er|re)s?")),
    "µm": Unit("length", 1e-6, (r"μm", r"um", r"microns?", r"micromet(?:er|re)s?")),
    "m": Unit("length", 1.0, (r"m", r"met(?:er|re)s?")),
    "in": Unit("length", 0.0254, (INCH_IN, r"inch(?:es)?", r'"', r"′′")),
    "ft": Unit("length", 0.3048, (r"ft", r"foot", r"feet")),
    "thou": Unit("length", 2.54e-5, (r"thou",)),
    "deg": Unit("angle", 0.017453292519943295, (r"deg", r"degrees?", r"°", r"◦")),
    "rad": Unit("angle", 1.0, (r"rad", r"radians?")),
    "mg": Unit("mass", 1e-6, (r"mg", r"milligrams?")),
    "g": Unit("mass", 1e-3, (r"g", r"grams?")),
    "kg": Unit("mass", 1.0, (r"kg", r"kilograms?")),
    # Before the pound, so `pounds-force` is not read as `pounds`.
    "lbf": Unit("force", 4.4482216152605, (r"lbf", r"pounds?[- ]force")),
    "lb": Unit("mass", 0.45359237, (r"lbs?", r"pounds?")),
    "oz": Unit("mass", 0.028349523125, (r"oz", r"ounces?")),
    "kN": Unit("force", 1e3, (r"kn",)),
    "mN": Unit("force", 1e-3, (r"mn",)),
    "N": Unit("force", 1.0, (r"n", r"newtons?")),
    "kgf": Unit("force", 9.80665, (r"kgf",)),
    "ms": Unit("time", 1e-3, (r"ms",)),
    "s": Unit("time", 1.0, (r"s", r"secs?", r"seconds?")),
    "min": Unit("time", 60.0, (r"min", r"mins", r"minutes?")),
    "h": Unit("time", 3600.0, (r"h", r"hrs?", r"hours?")),
    "%": Unit("fraction", 1e-2, (r"%", r"percent")),
    "turns": Unit("count", 1.0, (r"turns?",)),
    "teeth": Unit("count", 1.0, (r"teeth", r"tooth")),
    "mAh": Unit("charge", 3.6, (r"mah",)),
}


def spelling(but: tuple[str, ...] = ()) -> str:
    """A regex matching any unit's spelling as a whole word, leaving out the spellings in but."""
    words = "|".join(s for unit in UNITS.values() for s in unit.spellings if s not in but)
    return rf"(?:{words})(?![a-z0-9/^])"


# What may sit between a number and its unit: a space, or the hyphen of a unit used as an
# adjective (2-in. plate, 5-mm pin), unless another number follows the word (2-in-1). No
# spelling starts with a digit, so 5-10 mm stays a range.
UNIT_GAP = r"(?:\s|-(?!\w+-\d))?"
# A spelling that begins a dotted abbreviation is not a unit: the n of n.a. is no newton, while
# the mm of "10 mm.The" ends a sentence.
_FOLLOWING = re.compile(rf"{UNIT_GAP}({spelling()})(?!\.[a-z]\.)")
_SPELLED = {name: re.compile(rf"(?:{'|'.join(unit.spellings)})") for name, unit in UNITS.items()}


def unit_at(text: str, pos: int) -> tuple[str, int] | None:
    """The unit printed at text[pos:] (normalized text, after an optional UNIT_GAP) and where its
    spelling ends, or None."""
    m = _FOLLOWING.match(text, pos)
    if m is None:
        return None
    name = next(name for name, spelled in _SPELLED.items() if spelled.fullmatch(m.group(1)))
    return name, m.end()


def named(spelled: str) -> str | None:
    """The unit a project file names (`mm`, `millimetres`, `N`), or None if none is."""
    text = spelled.strip().lower()
    return next((name for name, s in _SPELLED.items() if s.fullmatch(text)), None)


def quantity(unit: str) -> str:
    return UNITS[unit].quantity


def declared(q, spelled) -> tuple[str | None, str]:
    """The unit a project's `units: {q: spelled}` sets, or None and why it sets none."""
    if q not in BASE:
        return (
            None,
            f"units sets {', '.join(BASE)}; "
            "other quantities follow from them (torque in force × length)",
        )
    unit = named(spelled) if isinstance(spelled, str) else None
    if unit is None:
        return None, (
            f"{spelled!r} is not a unit cadrev knows; one of "
            + ", ".join(n for n, u in UNITS.items() if u.quantity == q)
        )
    if quantity(unit) != q:
        return None, f"{unit} is a unit of {quantity(unit)}, not {q}"
    return unit, ""


def size(q: str, chosen: dict[str, str]) -> float:
    """The SI size of one project unit of quantity q, given the unit chosen for each base
    quantity."""
    if q in BASE:
        return UNITS[chosen.get(q, BASE[q])].si
    out = 1.0
    for base, power in DERIVED[q].items():
        out *= size(base, chosen) ** power
    return out


def convert(value: float, unit: str, chosen: dict[str, str]) -> float:
    """value in unit, expressed in the project's unit of the same quantity."""
    return value * UNITS[unit].si / size(quantity(unit), chosen)
