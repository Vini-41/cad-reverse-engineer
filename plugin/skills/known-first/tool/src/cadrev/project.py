"""A reconstruction project: its files, what its ledger states, and the findings a run collects.

The rule the whole package enforces: a number reaches the CAD only through params.yaml, every
parameter declares its basis, and every source value is a verbatim quote, a pinned figure crop or
a probe of released geometry, found in a hashed source.
"""

from __future__ import annotations

import ast
import math
import re
from collections import Counter
from collections.abc import Generator
from contextlib import contextmanager
from dataclasses import dataclass, field
from functools import cached_property
from pathlib import Path

import yaml

from . import Fault, released, schema, sources, threads, units

FORMAT = 1  # the project.yaml format this cadrev reads
# Findings after which nothing else in the project is read and every command refuses it.
REFUSED = ("project-missing", "format-missing", "format-unknown")
BASES = ("source", "derived", "measured", "proposed")
# What a parameter can rest on, strongest first: a derived one rests on the weakest of its inputs.
RESTS_ON = ("source", "measured", "proposed")
# tolerance.length, and tolerance.angle in degrees, where project.yaml sets none.
DEFAULT_TOL = {"length": 1e-3, "angle": 0.01}
AXES = {"x": 0, "y": 1, "z": 2}
# The keys of a check that name a pose: the one a change is taken from, then the one it is
# evaluated at.
POSES = ("from", "pose")
# What each kind of probe evaluates.
PROBE_QUANTITY = {"bbox": "length", "distance": "length", "diameter": "length", "angle": "angle"}
SOURCE_KINDS = ("paper", "supplement", "datasheet", "video", "drawing", "geometry", "other")
TEXT_FORMATS = {".pdf", ".docx", ".txt", ".md", ".html", ".htm"}
MATH_NAMES = {
    name: getattr(math, name)
    for name in "pi sqrt sin cos tan asin acos atan atan2 radians degrees hypot".split()
} | {"min": min, "max": max, "abs": abs}
# What a derived param's expr or a check's expect is built from: arithmetic, numbers, MATH_NAMES.
_EXPR_SYNTAX = (
    ast.Expression,
    ast.BinOp,
    ast.UnaryOp,
    ast.Call,
    ast.Name,
    ast.Load,
    ast.Constant,
    ast.operator,
    ast.unaryop,
)
# A ledger value an expect names, <entry>.<key>; an evidence id may hold hyphens.
_LEDGER_NAME = re.compile(r"(?<![\w.])([A-Za-z_][\w-]*)\.([A-Za-z_]\w*)")


@dataclass
class Finding:
    level: str  # "error" or "warning"
    rule: str
    message: str


def evaluate(expr: str, names: dict[str, float]) -> float:
    """The value of an arithmetic expression over names and MATH_NAMES; raises ValueError saying
    why it has none."""
    try:
        tree = ast.parse(expr, mode="eval")
    except SyntaxError as exc:
        raise ValueError(f"is not valid syntax ({exc.msg}): {expr!r}") from exc
    except (RecursionError, MemoryError, ValueError) as exc:
        raise ValueError(f"is not valid syntax: {expr!r}") from exc
    for node in ast.walk(tree):
        if not isinstance(node, _EXPR_SYNTAX):
            raise ValueError(f"is not arithmetic ({type(node).__name__}): {expr!r}")
        if isinstance(node, ast.Constant):
            number = node.value
            if not isinstance(number, (int, float)) or isinstance(number, bool):
                raise ValueError(f"is not arithmetic ({number!r}): {expr!r}")
            node.value = float(number)  # so a power overflows rather than running on
    try:
        value = float(
            eval(compile(tree, "<expr>", "eval"), {"__builtins__": {}}, MATH_NAMES | names)
        )
    except NameError as exc:
        raise ValueError(f"uses an undefined name: {exc}") from exc
    except (ArithmeticError, ValueError, TypeError, RecursionError) as exc:
        raise ValueError(f"does not evaluate: {exc}") from exc
    if not math.isfinite(value):
        raise ValueError(f"does not evaluate: it gives {value}")
    return value


def expr_names(expr: str) -> set[str]:
    """The names an expression reads besides MATH_NAMES; none where it does not parse."""
    try:
        tree = ast.parse(expr, mode="eval")
    except (SyntaxError, ValueError, RecursionError, MemoryError):
        return set()
    return {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)} - MATH_NAMES.keys()


def expect_refs(expr: str) -> list[str]:
    """The ledger values an expect names, <entry>.<key>, in order."""
    return list(dict.fromkeys(f"{m[1]}.{m[2]}" for m in _LEDGER_NAME.finditer(expr)))


def compared_refs(c: dict) -> list[str]:
    """The ledger values a check compares with the geometry, those its expect names among them."""
    eid = c.get("evidence")
    return (
        [f"{eid}.{key}" for key in (c.get("axes") or {})]
        + ([f"{eid}.{c['key']}"] if c.get("key") else [])
        + [str(ref) for ref in c.get("ends") or []]
        + expect_refs(str(c.get("expect", "")))
    )


def pose_refs(c: dict) -> list[str]:
    """The joint values a check's poses name, its from pose's then its pose's: each a param or a
    ledger value. A number a pose gives is neither: it is where the check is read."""
    return [v for key in POSES for v in (c.get(key) or {}).values() if isinstance(v, str)]


@dataclass
class Project:
    root: Path
    meta: dict
    evidence: list[dict]
    skipped: list[dict]
    conflicts: list[dict]
    params: dict[str, dict]
    checks: list[dict]
    gaps: dict[str, dict]
    # Datums declared on released bodies: <body>.<feature> -> its point in the body's frame, or
    # {circle: [a, b, c]} or {mid: [a, b]} of datums declared on that body.
    datums: dict[str, list | dict]
    # The mass model: part -> {mass: param} or {density: param}.
    parts: dict[str, dict]
    # plan.yaml's make, buy and steps; None for a project with no plan.
    plan: dict | None = None
    findings: list[Finding] = field(default_factory=list)
    # Each resolved param's value, and the basis it rests on (one of RESTS_ON).
    values: dict[str, float] = field(default_factory=dict)
    rests_on: dict[str, str] = field(default_factory=dict)
    # Params read only as a sweep's steps: a resolution, which states nothing about the object.
    resolution: set[str] = field(default_factory=set)
    # Sources whose file is there but cannot be read as text or geometry.
    unreadable: set[str] = field(default_factory=set)
    # Each probe's comparison, as report.json lists it.
    probes: list[dict] = field(default_factory=list)

    def error(self, rule: str, message: str) -> None:
        self.findings.append(Finding("error", rule, message))

    def warn(self, rule: str, message: str) -> None:
        self.findings.append(Finding("warning", rule, message))

    @contextmanager
    def filing(self, rule: str, where: str = "") -> Generator[None]:
        """Files a Fault raised inside as an error under its rule, else under rule."""
        try:
            yield
        except Fault as fault:
            if fault.message:
                self.error(fault.rule or rule, where + fault.message)

    @property
    def refused(self) -> bool:
        return any(f.rule in REFUSED for f in self.findings)

    @property
    def known_first(self) -> bool:
        return self.meta.get("known_first") is True

    @property
    def thread_standard(self) -> str:
        """The table a proposed thread comes from: the Unified one where the project's length
        unit is of the inch, and the ISO metric one where it is not."""
        return "unified" if self.units["length"] in threads.INCH_UNITS else "metric"

    @property
    def screws(self) -> dict[str, str]:
        """Each thread param that names a screw, and the param its length names."""
        return {
            name: str(spec["length"])
            for name, spec in self.params.items()
            if "thread" in spec and "length" in spec
        }

    def screw(self, name: str) -> str | None:
        """A screw as it is ordered, M3×10 or 1/4-20 UNC × 3/4 in: thread param `name`'s thread
        and its length, read as the standard length it is within tolerance.length of. None where
        the param names no screw, or its thread or its length has no value."""
        size, length = self.thread_params.get(name), self.values.get(self.screws.get(name, ""))
        if size is None or length is None:
            return None
        mm, tol = length / size.per_mm, self.length_tol / size.per_mm
        return threads.screw(size.thread, threads.standard_length(size.thread, mm, tol) or mm)

    @property
    def up(self) -> str:
        """The axis the object stands on, which the drawings' views are named by: z, or y."""
        return self.meta.get("up", "z")

    @property
    def thread_params(self) -> dict[str, threads.Size]:
        """Each resolved thread param's sizes."""
        return {n: v for n, v in self.values.items() if isinstance(v, threads.Size)}

    @property
    def physics(self) -> set[str]:
        """Params marked physics: true, which only the simulation reads."""
        return {name for name, spec in self.params.items() if spec.get("physics") is True}

    @property
    def proposed(self) -> set[str]:
        return {name for name, basis in self.rests_on.items() if basis == "proposed"}

    @property
    def inexact(self) -> set[str]:
        """The proposed params that keep a VERIFIED project from being exact: all but physics
        values and a sweep's resolution."""
        return self.proposed - self.physics - self.resolution

    # Sources.

    @cached_property
    def sources(self) -> dict[str, dict]:
        return {s["id"]: s for s in self.meta.get("sources", [])}

    def source_path(self, source_id: str) -> Path:
        return self.root / self.sources[source_id].get("path", "")

    def available(self, source_id: str) -> bool:
        """Whether a source is registered, its file there and readable."""
        return (
            source_id in self.sources
            and source_id not in self.unreadable
            and self.source_path(source_id).is_file()
        )

    def is_text(self, source_id: str) -> bool:
        return self.source_path(source_id).suffix.lower() in TEXT_FORMATS

    @cached_property
    def units(self) -> dict[str, str]:
        """The unit of each base quantity: the project's where it names a valid one."""
        out = dict(units.BASE)
        for q, spelled in (self.meta.get("units") or {}).items():
            unit, _ = units.declared(q, spelled)
            if unit is not None:
                out[q] = unit
        return out

    def tolerance(self, quantity: str) -> float:
        """project.yaml's tolerance.<quantity>, else the default; an angle's is in degrees."""
        return float(self.meta.get("tolerance", {}).get(quantity, DEFAULT_TOL[quantity]))

    @property
    def length_tol(self) -> float:
        return self.tolerance("length")

    def degrees(self, quantity: str | None) -> float:
        """What a value in the project's unit of quantity is multiplied by to be compared: an
        angle is compared in degrees whatever the project's angle unit, anything else as it is."""
        if quantity != "angle":
            return 1.0
        return units.size("angle", self.units) / units.UNITS["deg"].si

    # Released geometry.

    def _geometry(self, sheets: bool) -> list[str]:
        return [
            sid
            for sid, s in self.sources.items()
            if s.get("kind") == "geometry"
            and self.available(sid)
            and released.is_sheet(self.source_path(sid)) == sheets
        ]

    def solids(self, source_id: str) -> tuple:
        """A geometry source's solids, in file order and the project's length unit."""
        scale = units.convert(1.0, "mm", self.units)
        return released.solids(self.source_path(source_id), scale)

    def sheet(self, source_id: str) -> tuple:
        """A cut file's regions, in the project's length unit."""
        scale = units.convert(1.0, "mm", self.units)
        return released.regions(self.source_path(source_id), scale)

    @cached_property
    def bodies(self) -> dict:
        """Every solid of a readable geometry source, by body name."""
        out = {}
        for sid in self._geometry(sheets=False):
            try:
                found = self.solids(sid)
            except Exception:  # noqa: BLE001 - [source-unreadable] says why
                continue
            out |= dict(zip(released.body_names(sid, len(found)), found))
        return out

    @cached_property
    def regions(self) -> dict[str, tuple]:
        """The regions of each readable cut file, by source id."""
        out = {}
        for sid in self._geometry(sheets=True):
            try:
                out[sid] = self.sheet(sid)
            except Exception:  # noqa: BLE001 - [source-unreadable] says why
                continue
        return out

    @property
    def unread_geometry(self) -> set[str]:
        """The geometry sources whose bodies cannot be read: missing or unreadable."""
        read = {released.source_of(name) for name in self.bodies} | self.regions.keys()
        return {s for s, src in self.sources.items() if src.get("kind") == "geometry"} - read

    def region(self, name: str) -> tuple[str, int]:
        """The cut file and region index that <source>@<x>,<y> names by a point inside it."""
        at = released.at_point(name)
        if at is None or at[0] not in self.regions:
            raise Fault(f"{name} is not <source>@<x>,<y>, a point inside a region of a cut file")
        sid, point = at
        found = released.regions_at(self.regions[sid], point, self.length_tol)
        if len(found) != 1:
            count = f"{len(found)} regions" if found else "no region"
            raise Fault(f"{name} lies inside {count} of {sid}")
        return sid, found[0]

    def body(self, name: str):
        """The released body a name addresses: a region of a cut file, else a solid."""
        if released.at_point(name) is not None:
            sid, index = self.region(name)
            return self.regions[sid][index]
        if name in self.regions:
            raise Fault(f"{name} is a cut file: name a region of it {name}@<x>,<y>")
        if name not in self.bodies:
            raise Fault(f"{name} is not a body of a geometry source")
        return self.bodies[name]

    def released_datum(self, name: str) -> tuple[str, tuple[float, float, float]] | None:
        """The body a datum declared in evidence.yaml lies on, and its point there; None for one
        declared on no body. A cut file's datum lies on its sheet, at [x, y]."""
        point = self.datums.get(name)
        if isinstance(point, dict):
            try:
                return self.derived_datum(name)[:2]
            except Fault:
                return None  # the datum's own finding says why
        if not isinstance(point, list):
            return None
        sheet = next((s for s in self.regions if name.startswith(f"{s}.")), None)
        if sheet is not None:
            return (sheet, (float(point[0]), float(point[1]), 0.0)) if len(point) == 2 else None
        body = self._body_named(name)
        if body is None or len(point) != 3:
            return None
        return body, (float(point[0]), float(point[1]), float(point[2]))

    def derived_datum(self, name: str) -> tuple[str, tuple[float, float, float], float | None]:
        """The body a derived datum lies on, its point and, for a circle, the circle's diameter:
        the centre of the circle through three datums, or the midpoint of two. A Fault saying
        why where the datums it names give none."""
        entry = self.datums[name]
        assert isinstance(entry, dict)  # called for a derived datum alone
        form = next((f for f in ("circle", "mid") if f in entry), None)
        if form is None:
            raise Fault("give {circle: [a, b, c]} or {mid: [a, b]}")
        through, count = [str(d) for d in entry[form]], 3 if form == "circle" else 2
        if len(through) != count:
            raise Fault(f"{form} takes {count} datums, not {len(through)}")
        body = self._body_named(name)
        if body is None:
            raise Fault("names no body of a geometry source; name it <body>.<feature>")
        points = []
        for datum in through:
            if isinstance(self.datums.get(datum), dict):
                raise Fault(f"{datum} is itself derived; derive it from datums given as points")
            named = self.released_datum(datum)
            if named is None:
                raise Fault(f"{datum} is no datum given as a point on a body")
            if named[0] != body:
                raise Fault(f"{datum} lies on body {named[0]}, not {body}")
            points.append(named[1])
        if form == "mid":
            (ax, ay, az), (bx, by, bz) = points
            return body, ((ax + bx) / 2, (ay + by) / 2, (az + bz) / 2), None
        centre, diameter = released.circle(points, self.length_tol, through)
        return body, centre, diameter

    def _body_named(self, name: str) -> str | None:
        """The released body a datum's name <body>.<feature> names, if any: a solid, or a cut
        file's sheet."""
        named = (b for b in [*self.bodies, *self.regions] if name.startswith(f"{b}."))
        return max(named, key=len, default=None)

    def datum_on(self, name: str, body: str) -> tuple[float, float, float]:
        """The point of a datum declared on released body `body`: on a cut file's region, a datum
        of its sheet inside the region's outer contour, on its edge or derived from datums on it."""
        named = self.released_datum(str(name))
        at = released.at_point(body)
        if at is not None and named is not None and named[0] == at[0]:
            sid, index = self.region(body)
            if index not in released.outlines_at(self.regions[sid], named[1][:2], self.length_tol):
                raise Fault(f"{name} lies outside the outer contour of region {body}")
            entry = self.datums.get(name)
            through = [str(d) for f in entry.values() for d in f] if isinstance(entry, dict) else []
            for datum in through or [name]:
                point = (self.released_datum(datum) or named)[1]
                gap = released.off_edge([self.regions[sid][index]], point, self.length_tol)
                if gap:
                    of = "" if datum == name else f", which {name} is derived from,"
                    raise Fault(
                        f"{datum}{of} is {gap:.4g} from the nearest edge of region {body}; place "
                        "it on the outer contour or a hole's edge",
                        "datum-off-solid",
                    )
        elif named is None or named[0] != body:
            raise Fault(f"{name} is not a datum declared on {body}")
        return named[1]

    # The ledger.

    def item(self, eid: str) -> dict | None:
        """The evidence item with id eid: the first, where an id is repeated."""
        return self._items.get(eid)

    @cached_property
    def _items(self) -> dict[str, dict]:
        return {e["id"]: e for e in reversed(self.evidence)}

    def _ledgered(self, ref: str) -> tuple[float, str] | None:
        """An evidence value as printed, with the quote or reading it is printed in."""
        eid, _, key = str(ref).partition(".")
        item = self.item(eid)
        if item is None or key not in (item.get("values") or {}):
            return None
        text = item["quote"] if "quote" in item else str(item.get("reading", ""))
        return float(item["values"][key]), text

    def printed_units(self, ref: str) -> list[str | None]:
        """The unit printed after each appearance of an evidence value in its quote or reading."""
        ledgered = self._ledgered(ref)
        if ledgered is None:
            return []
        value, text = ledgered
        stated = sources.quantities_in(text)
        return list(dict.fromkeys(u for v, u in stated if math.isclose(v, value, rel_tol=1e-9)))

    def probe_of(self, ref: str) -> str | None:
        """The kind of probe an evidence value is recorded by; None for a quote or a reading."""
        if self._ledgered(ref) is None:
            return None
        kind = (self.item(str(ref).partition(".")[0]) or {}).get("probe")
        return kind if kind in PROBE_QUANTITY else None

    def unit_of(self, ref: str) -> str | None:
        """The unit an evidence value is printed in; None, the project's, where none is. A probe
        records its value in the project's unit of the quantity it evaluates."""
        if kind := self.probe_of(ref):
            return self.units[PROBE_QUANTITY[kind]]
        printed = self.printed_units(ref)
        return printed[0] if printed else None

    def prints_length(self, ref: str) -> bool:
        """Whether an evidence value is printed as a length: in a length unit, or as a diameter
        callout (Ø 22.5)."""
        unit, ledgered = self.unit_of(ref), self._ledgered(ref)
        if unit is not None:
            return units.quantity(unit) == "length"
        return ledgered is not None and any(
            math.isclose(v, ledgered[0], rel_tol=1e-9) for v in sources.diameters_in(ledgered[1])
        )

    def value(self, ref: str) -> float | None:
        """An evidence value in the project's units, converted from the unit its quote prints; a
        probe records its value in them, so it is read as recorded."""
        ledgered = self._ledgered(ref)
        if ledgered is None:
            return None
        unit = None if self.probe_of(ref) else self.unit_of(ref)
        return ledgered[0] if unit is None else units.convert(ledgered[0], unit, self.units)

    def stated(self, ref: str, quantity: str | None = None) -> float:
        """An evidence value as a check compares it in quantity: an angle in degrees, anything
        else in the project's units."""
        value = self.value(ref)
        if value is None:
            raise Fault(f"{ref} is not a ledger value")
        return value * self.degrees(quantity)

    def expect(self, expr: str) -> float:
        """The value an expect works out from the ledger values it names, each read in the unit a
        check compares its quantity in, or as printed where it prints no unit."""
        refs, names = expect_refs(expr), {}
        for i, ref in enumerate(refs):
            unit = self.unit_of(ref)
            names[f"_ledger{i}"] = self.stated(ref, units.quantity(unit) if unit else None)
        text = _LEDGER_NAME.sub(lambda m: f"_ledger{refs.index(f'{m[1]}.{m[2]}')}", expr)
        for name in expr_names(text) - names.keys():
            what = (
                "a param; an expect reads only ledger values" if name in self.params else "unknown"
            )
            raise Fault(f"expect {expr!r}: {name} is {what}")
        try:
            return evaluate(text, names)
        except ValueError as exc:
            raise Fault(f"expect {expr!r} {exc}") from exc

    def traced(self, name: str, through: tuple[str, ...] = ()) -> tuple[str, str] | None:
        """The source param a param's value copies, and the evidence value it is from: itself for
        basis source, or for a derived one the one param its expr scales by constants. A constant
        over a param (360 / pitch_angle) is no scaling: it changes the quantity."""
        spec = self.params.get(name) or {}
        if spec.get("basis") == "source":
            return name, str(spec.get("from", ""))
        if spec.get("basis") != "derived" or name in through:
            return None
        expr = str(spec.get("expr", ""))
        try:
            nodes = list(ast.walk(ast.parse(expr, mode="eval")))
            scales = all(
                isinstance(n, (ast.Expression, ast.Name, ast.Load, ast.Constant, ast.UnaryOp))
                or isinstance(n, (ast.UAdd, ast.USub, ast.BinOp, ast.Mult, ast.Div))
                for n in nodes
            ) and not any(
                isinstance(n, ast.BinOp)
                and isinstance(n.op, ast.Div)
                and expr_names(ast.unparse(n.right))
                for n in nodes
            )
        except (SyntaxError, ValueError):
            return None
        names = expr_names(expr)
        return self.traced(names.pop(), (*through, name)) if scales and len(names) == 1 else None

    def printed_as(self, what: str) -> tuple[str | None, str | None]:
        """The unit `what` is printed in, and the evidence value that prints it: `what` itself,
        or for a param the value it traces to."""
        traced = self.traced(what) if what in self.params else (what, what)
        ref = traced[1] if traced else None
        return (self.unit_of(ref) if ref else None), ref

    def hold_param(self, name: str, expected: tuple[str, ...], use: str) -> None:
        """hold, for a name meant to be a param: one that is none is another finding's to say."""
        if name in self.params:
            self.hold(name, expected, use)

    def hold(self, what: str, expected: tuple[str, ...], use: str) -> None:
        """[unit-quantity] unless `what`, an evidence value or a param tracing to one, is printed
        in a unit of an expected quantity or in none. A count is also a whole number."""
        unit, ref = self.printed_as(what)
        if unit is not None and units.quantity(unit) not in expected:
            by = ""
            if what in self.params:
                source = (self.traced(what) or (what,))[0]
                by = f"param {source}{'' if source == what else f' through {what}'} "
            kind = self.probe_of(str(ref))
            printed = f"{_a(kind)} probe's value in" if kind else "printed in"
            self.error(
                "unit-quantity",
                f"{ref} is {printed} {unit}, a unit of {units.quantity(unit)}, where "
                f"{' or '.join(_a(q) for q in expected)} is expected ({by}{use})",
            )
        elif expected == ("count",):
            value = self.values.get(what) if what in self.params else self.value(what)
            if value is not None and math.isfinite(value) and value != round(value):
                named = f"param {what}" if what in self.params else what
                self.error(
                    "unit-quantity",
                    f"{named} = {value:g} is not a whole number, where a count is expected ({use})",
                )


def _a(word: str) -> str:
    return f"an {word}" if word[0] in "aeiou" else f"a {word}"


def _read_yaml(root: Path, name: str, findings: list[Finding]) -> dict:
    """A project file's contents in the expected shape; {} if absent. Problems become findings."""
    path = root / name
    if not path.is_file():
        return {}
    try:
        data = yaml.safe_load(path.read_text(encoding="utf8"))
    except yaml.YAMLError as exc:
        mark = getattr(exc, "problem_mark", None)
        where = f"{name} line {mark.line + 1}" if mark else name
        problem = getattr(exc, "problem", None) or str(exc)
        findings.append(Finding("error", "yaml-syntax", f"{where}: {problem}"))
        return {}
    except UnicodeDecodeError:
        findings.append(Finding("error", "yaml-syntax", f"{name}: not UTF-8 text"))
        return {}
    problems: list[str] = []
    data = schema.conform_file(name, {} if data is None else data, problems)
    findings += [Finding("error", "schema", message) for message in problems]
    return data


def read_meta(root: Path, findings: list[Finding]) -> dict:
    """project.yaml's contents, or {} after a REFUSED finding: it is missing, or of a format this
    cadrev does not read."""
    if not (root / "project.yaml").is_file():
        why = f"{root / 'project.yaml'} not found; cadrev init creates a project directory"
        findings.append(Finding("error", "project-missing", why))
        return {}
    before = len(findings)
    meta = _read_yaml(root, "project.yaml", findings)
    if any(f.rule == "yaml-syntax" for f in findings[before:]):
        return meta  # the format cannot be read past the syntax error
    fmt = meta.get("format")
    if type(fmt) is int and fmt == FORMAT:
        return meta
    rule, what = (
        ("format-missing", "is missing") if fmt is None else ("format-unknown", f"is {fmt!r}")
    )
    why = f"project.yaml: format {what}; this cadrev reads format: {FORMAT}"
    findings.append(Finding("error", rule, why))
    return {}


def load(root: Path) -> Project:
    """The project at root. Never raises: missing or malformed files become findings."""
    root = root.resolve()
    findings: list[Finding] = []
    meta = read_meta(root, findings)
    refused = any(f.rule in REFUSED for f in findings)
    files = {
        name: {} if refused else _read_yaml(root, name, findings)
        for name in schema.FILES
        if name != "project.yaml"
    }
    p = Project(
        root=root,
        meta=meta,
        evidence=files["evidence.yaml"].get("evidence", []),
        skipped=files["evidence.yaml"].get("skipped", []),
        conflicts=files["evidence.yaml"].get("conflicts", []),
        datums=files["evidence.yaml"].get("datums", {}),
        params=files["params.yaml"].get("params", {}),
        parts=files["params.yaml"].get("parts", {}),
        checks=files["checks.yaml"].get("checks", []),
        gaps={g["id"]: g for g in files["gaps.yaml"].get("gaps", [])},
        plan=files["plan.yaml"] if (root / "plan.yaml").is_file() and not refused else None,
        findings=findings,
    )
    for what, rule, ids in (
        ("source", "source-id", [s["id"] for s in meta.get("sources", [])]),
        ("evidence", "evidence-id", [e["id"] for e in p.evidence]),
        ("check", "check-id", [str(c["id"]) for c in p.checks]),
    ):
        for repeated, n in Counter(ids).items():
            if n > 1:
                p.error(rule, f"{what} {repeated}: {what} ids must be unique")
    return p
