"""Project files and every check that needs no geometry.

The rule the whole package enforces: a number reaches the CAD only through
params.yaml, every parameter declares its basis, and every source-basis value
is a verbatim quote (or a pinned figure crop) found in a hashed source.
"""

from __future__ import annotations

import ast
import math
import re
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from . import lint, released, schema, sources, units

FORMAT = 1  # the project.yaml format this cadrev reads
# Findings after which nothing else in the project is read and every command refuses it.
REFUSED = ("project-missing", "format-missing", "format-unknown")
BASES = ("source", "derived", "measured", "proposed")
# What a parameter can rest on, strongest first: a derived one rests on the weakest of its inputs.
RESTS_ON = ("source", "measured", "proposed")
LENGTH_TOL = 1e-3  # tolerance.length when project.yaml sets none
ANGLE_TOL = 0.01  # tolerance.angle, in degrees, when project.yaml sets none
DEFAULT_TOL = {"length": LENGTH_TOL, "angle": ANGLE_TOL}
# The unit a check compares a quantity in where it is not the project's: an angle in degrees,
# whatever the project's angle unit, as tolerance.angle is.
COMPARED_IN = {"angle": "deg"}
# The loosest tolerance a check may have: tol as a fraction of each value it compares, and tol_rel.
TOL_CAP, TOL_REL_CAP = 0.05, 0.25


def _mass_reads(p: Project, c: dict, weighs: tuple[str, ...] | None = None) -> list[str]:
    """The params a mass check reads: its density, or without one the mass model's params for
    the parts it weighs (its parts, else weighs, else every part), then its add and counts
    params."""
    parts = c.get("parts") or weighs
    names = mass_params(p, parts) if c.get("density") is None else []
    names += [str(c.get("density"))] + [str(n) for n in c.get("add") or []]
    return names + [str(n) for n in (c.get("counts") or {}).values()]


def _mass_names(c: dict) -> list[tuple[str, str]]:
    """The params a mass check names: its density, then each mass it adds, then each count of
    instances it weighs."""
    names = [(c.get("density") or "", "density")] + [(n, "mass") for n in c.get("add", [])]
    return names + [(str(n), "count") for n in (c.get("counts") or {}).values()]


@dataclass(frozen=True)
class CheckKind:
    """What a kind of check compares with the geometry: evidence values of quantity, within tol,
    which defaults to project.yaml's tolerance.<tolerance>; or, where tolerance is None, within
    tol_rel, a fraction of the value, which has no default. reads gives the params a check of the
    kind reads itself, given the parts a mass check weighs where known; span_capped caps its tol
    against the span between the two values it compares, rather than against each. A joint_valued
    check without between compares its joint's own value, so quantity and tolerance are its
    joint's: an angle for a revolute joint, a length for a slide. between_two, where set, is the
    quantity and tolerance of a check whose between names two datums rather than three: a
    distance. changes, where set, lets a check of the kind take a from pose besides its pose, and
    then compare the change in what it evaluates between the two. claims, where set, lets it take a
    claim (one of CLAIMS) in place of a key: a direction of change between the two poses, passing
    only beyond its tolerance, with no tol of its own (ADR-0010). body_cap, where set, makes it
    compare a built part with a released body (its body), its tol capped at that fraction of the
    body's bbox diagonal, as it compares with no value. names, where set, gives the params a
    check of the kind names by key, each with the quantity it must be in. exact, where set, makes
    it compare exactly, so it has no tolerance and takes no tol or tol_rel. expects, unless False,
    lets a check of the kind compare with a value worked out from the ledger (its expect) in place
    of evidence and key: a kind that compares one value (ADR-0014)."""

    quantity: str
    tolerance: str | None
    reads: Callable[[Project, dict, tuple[str, ...] | None], list[str]] | None = None
    span_capped: bool = False
    joint_valued: bool = False
    between_two: str | None = None
    changes: bool = False
    claims: bool = False
    body_cap: float | None = None
    names: Callable[[dict], list[tuple[str, str]]] | None = None
    exact: bool = False
    expects: bool = True


# The quantities a joint's value is in: a revolute joint's angle, a slide's length. Before the
# build names the joint, a pose value or range end may be either.
JOINT_QUANTITIES = ("angle", "length")


# The kinds of check that compare with a ledger value, or a shape check with a released body;
# interference (OVERLAP_KINDS) compares with neither.
CHECK_KINDS = {
    "bbox": CheckKind("length", "length", expects=False),
    # With from, the change between two poses: a slide's travel, a carrier's turn.
    "distance": CheckKind("length", "length", changes=True),
    "angle": CheckKind("angle", "angle", changes=True),
    # The diameter of the cylindrical face a datum lies on: a bore, a hub.
    "diameter": CheckKind("length", "length"),
    "mass": CheckKind("mass", None, reads=_mass_reads, names=_mass_names),
    # A joint's range: an angle at each end, or a slide's length, compared with a stated end that
    # is often 0.
    # Between two datums, a distance at each end, as a slide that sets a leg's width reaches it.
    "range": CheckKind(
        "angle", "angle", span_capped=True, joint_valued=True, between_two="length", expects=False
    ),
    # How far a cable shortens from as built, or a from pose, to a pose.
    "stroke": CheckKind("length", "length", changes=True, claims=True),
    # A part against its released body: the largest distance between their surfaces, which no
    # ledger value states, its tol capped against the body's size.
    "shape": CheckKind("length", "length", body_cap=0.01, expects=False),
    # How many instances of a part the assembly places, against a stated count (ADR-0012).
    "count": CheckKind("count", None, exact=True, expects=False),
}
# The kinds of check that compare how much instances overlap with an overlap limit.
OVERLAP_KINDS = ("interference",)
# The keys of a check that name a pose: the from pose a change is taken from (CheckKind.changes),
# then the pose it is evaluated at.
POSES = ("from", "pose")
# What a claim says its quantity does between a check's from pose and its pose: a stroke's
# shortening is positive or negative.
CLAIMS = {"shortens": 1, "lengthens": -1}
AXES = {"x": 0, "y": 1, "z": 2}
SOURCE_KINDS = ("paper", "supplement", "datasheet", "video", "drawing", "geometry", "other")
TEXT_FORMATS = {".pdf", ".docx", ".txt", ".md", ".html", ".htm"}
MATH_NAMES = {
    name: getattr(math, name)
    for name in (
        "pi",
        "sqrt",
        "sin",
        "cos",
        "tan",
        "asin",
        "acos",
        "atan",
        "atan2",
        "radians",
        "degrees",
        "hypot",
    )
} | {"min": min, "max": max, "abs": abs}


@dataclass
class Finding:
    level: str  # "error" or "warning"
    rule: str
    message: str


@dataclass
class Project:
    root: Path
    meta: dict
    # Every ledger item, in order, whatever its id; look one up by id with item().
    evidence: list[dict]
    skipped: list[dict]
    conflicts: list[dict]
    params: dict[str, dict]
    checks: list[dict]
    gaps: dict[str, dict]
    overlays: list[dict]
    # Datums declared on released bodies: <body>.<feature> -> its point in the body's frame.
    datums: dict[str, list] = field(default_factory=dict)
    # The mass model: part -> {mass: param} or {density: param}, from params.yaml's parts.
    parts: dict[str, dict] = field(default_factory=dict)
    # Params read only as a sweep's steps: a resolution the reconstruction chooses, which states
    # nothing about the object, so exact leaves them out. Set by the build.
    resolution: set[str] = field(default_factory=set)
    values: dict[str, float] = field(default_factory=dict)
    # Text and geometry sources whose file exists but cannot be read as text or geometry.
    unreadable: set[str] = field(default_factory=set)
    # Each probe's comparison, as report.json lists it under probes.
    probes: list[dict] = field(default_factory=list)
    # Every body of a readable geometry source, read once a run asks for one.
    _bodies: dict | None = None
    # The regions of each readable cut file, read once a run asks for one.
    _regions: dict | None = None
    # The basis each resolved parameter rests on, one of RESTS_ON: its own, or for a derived one
    # the weakest among the parameters its expr references.
    rests_on: dict[str, str] = field(default_factory=dict)
    findings: list[Finding] = field(default_factory=list)

    @property
    def refused(self) -> bool:
        return any(f.rule in REFUSED for f in self.findings)

    def error(self, rule: str, message: str) -> None:
        self.findings.append(Finding("error", rule, message))

    def warn(self, rule: str, message: str) -> None:
        self.findings.append(Finding("warning", rule, message))

    @property
    def proposed(self) -> set[str]:
        """Parameters resting on a proposed value, directly or through derived expressions."""
        return {name for name, basis in self.rests_on.items() if basis == "proposed"}

    @property
    def physics(self) -> set[str]:
        """Parameters marked physics: true: values the MJCF export applies and no geometry reads,
        left out of exact (ADR-0008)."""
        return {name for name, spec in self.params.items() if spec.get("physics") is True}

    @property
    def sources(self) -> dict[str, dict]:
        return {s["id"]: s for s in self.meta.get("sources", [])}

    def source_path(self, source_id: str) -> Path:
        return self.root / self.sources[source_id].get("path", "")

    def solids(self, source_id: str) -> tuple:
        """The solids of geometry source source_id, in file order and the project's length unit;
        raises when its file cannot be read as geometry."""
        scale = units.convert(1.0, "mm", self.units)
        return released.solids(self.source_path(source_id), scale)

    @property
    def bodies(self) -> dict:
        """Every body of a readable geometry source by name (released.body_names), its solid in
        the project's length unit."""
        if self._bodies is not None:
            return self._bodies
        out = {}
        for sid in self._geometry(sheets=False):
            try:
                found = self.solids(sid)
            except Exception:  # noqa: BLE001 - check_sources says why it cannot be read
                continue
            out |= dict(zip(released.body_names(sid, len(found)), found))
        self._bodies = out
        return out

    def _geometry(self, sheets: bool) -> list[str]:
        """The geometry sources whose file is there and not found unreadable: the cut files where
        sheets, else the others."""
        return [
            sid
            for sid, s in self.sources.items()
            if s.get("kind") == "geometry"
            and _available(self, sid)
            and released.is_sheet(self.source_path(sid)) == sheets
        ]

    def read_regions(self, source_id: str) -> tuple:
        """The regions of cut file source_id (released.regions), in the project's length unit;
        raises when its file cannot be read as one."""
        scale = units.convert(1.0, "mm", self.units)
        return released.regions(self.source_path(source_id), scale)

    @property
    def regions(self) -> dict[str, tuple]:
        """The regions of each readable cut file, by source id."""
        if self._regions is not None:
            return self._regions
        out = {}
        for sid in self._geometry(sheets=True):
            try:
                out[sid] = self.read_regions(sid)
            except Exception:  # noqa: BLE001 - check_sources says why it cannot be read
                continue
        self._regions = out
        return out

    def region(self, name: str) -> tuple[str, int] | str:
        """The cut file and the index of its region that a body name <source>@<x>,<y> names by a
        point inside it; or why it names none: a point inside no region, or inside several."""
        at = released.at_point(name)
        if at is None or at[0] not in self.regions:
            return f"{name} is not <source>@<x>,<y>, a point inside a region of a cut file"
        sid, point = at
        found = released.regions_at(self.regions[sid], point, self.length_tol)
        if len(found) != 1:
            count = f"{len(found)} regions" if found else "no region"
            return f"{name} lies inside {count} of {sid}"
        return sid, found[0]

    def body(self, name: str) -> Any:
        """The released body a name addresses: a region of a cut file by a point inside it
        (region), else a solid of bodies; or, as text, why it addresses none."""
        if released.at_point(name) is not None:
            found = self.region(name)
            return found if isinstance(found, str) else self.regions[found[0]][found[1]]
        if name in self.regions:
            return f"{name} is a cut file: name a region of it {name}@<x>,<y>, by a point inside it"
        return self.bodies.get(name, f"{name} is not a body of a geometry source")

    def released_datum(self, name: str) -> tuple[str, tuple[float, float, float]] | None:
        """The body a datum declared on released geometry lies on, and its point in the body's
        frame; None for a name declared on no body, or not as three numbers. A datum on a cut file
        lies on the sheet, not on one region: its body is the source, its point [x, y] on the
        sheet (z 0)."""
        point = self.datums.get(name)
        if not isinstance(point, list):
            return None
        sheet = next((s for s in self.regions if name.startswith(f"{s}.")), None)
        if sheet is not None:
            return (sheet, (float(point[0]), float(point[1]), 0.0)) if len(point) == 2 else None
        body = max((b for b in self.bodies if name.startswith(f"{b}.")), key=len, default=None)
        if body is None or len(point) != 3:
            return None
        return body, (float(point[0]), float(point[1]), float(point[2]))

    def tolerance(self, quantity: str) -> float:
        """project.yaml's tolerance.<quantity>, else cadrev's default; an angle's in degrees."""
        return float(self.meta.get("tolerance", {}).get(quantity, DEFAULT_TOL[quantity]))

    @property
    def length_tol(self) -> float:
        return self.tolerance("length")

    @property
    def units(self) -> dict[str, str]:
        """The unit of each base quantity: the project's where it names a valid one, else the
        default."""
        out = dict(units.BASE)
        for q, spelled in (self.meta.get("units") or {}).items():
            unit, _ = units.declared(q, spelled)
            if unit is not None:
                out[q] = unit
        return out

    @property
    def repeated(self) -> list[str]:
        """The evidence ids two or more items share, in ledger order; a citation of one reads
        neither item."""
        return [eid for eid, n in Counter(e["id"] for e in self.evidence).items() if n > 1]

    def item(self, eid: str) -> dict | None:
        """The evidence item with id eid; None for an unknown or a repeated id."""
        found = [e for e in self.evidence if e["id"] == eid]
        return found[0] if len(found) == 1 else None

    def cites_repeated(self, ref: str) -> str | None:
        """What a citation of ref reads where its evidence id is repeated, so a citer's finding
        can say it; None for any other ref."""
        eid = ref.partition(".")[0]
        return f"cites {eid}, a repeated evidence id" if eid in self.repeated else None

    def _ledgered(self, ref: str) -> tuple[float, str] | None:
        """An evidence value as printed, with the quote or reading it is printed in."""
        item_id, _, key = ref.partition(".")
        item = self.item(item_id)
        if item is None or key not in item.get("values", {}):
            return None
        return float(item["values"][key]), item["quote"] if "quote" in item else str(
            item.get("reading", "")
        )

    def printed_units(self, ref: str) -> list[str | None]:
        """The units printed after each appearance of an evidence value in its quote or reading."""
        ledgered = self._ledgered(ref)
        if ledgered is None:
            return []
        value, text = ledgered
        return list(
            dict.fromkeys(
                unit
                for v, unit in sources.quantities_in(text)
                if math.isclose(v, value, rel_tol=1e-9)
            )
        )

    def prints_length(self, ref: str) -> bool:
        """Whether an evidence value is printed as a length: in a length unit, or as a diameter
        callout (Ø 22.5) with no unit."""
        unit, ledgered = self.unit_of(ref), self._ledgered(ref)
        if unit is not None:
            return units.quantity(unit) == "length"
        return ledgered is not None and any(
            math.isclose(v, ledgered[0], rel_tol=1e-9) for v in sources.diameters_in(ledgered[1])
        )

    def unit_of(self, ref: str) -> str | None:
        """The unit an evidence value is printed in; None (the project's units) if none is
        printed."""
        printed = self.printed_units(ref)
        return printed[0] if printed else None

    def evidence_value(self, ref: str) -> float | None:
        """An evidence value in the project's units, converted from the unit printed in its
        quote."""
        ledgered = self._ledgered(ref)
        if ledgered is None:
            return None
        value, unit = ledgered[0], self.unit_of(ref)
        return value if unit is None else units.convert(value, unit, self.units)

    def ledger_value(self, ref: str) -> float | None:
        """An evidence value as an expect reads it: in the unit a check compares its printed
        unit's quantity in, an angle in degrees and any other in the project's units, or as
        printed where it is printed with no unit."""
        value, unit = self.evidence_value(ref), self.unit_of(ref)
        if value is None or unit is None:
            return value
        return value * self.compared_size(units.quantity(unit))

    def value_as(self, ref: str, quantity: str | None) -> float | None:
        """The evidence value at ref compared as quantity: an angle in degrees, else in the
        project's units."""
        value = self.evidence_value(ref)
        return value if value is None or quantity is None else value * self.compared_size(quantity)

    def compared_size(self, quantity: str) -> float:
        """How many of the units a check compares quantity in make one of the project's: degrees
        per project angle unit, else 1, as every other quantity is compared in the project's."""
        unit = COMPARED_IN.get(quantity)
        return 1.0 if unit is None else units.size(quantity, self.units) / units.UNITS[unit].si


def read_yaml(root: Path, name: str, findings: list[Finding]) -> dict:
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
    """project.yaml's contents, or {} after a REFUSED finding: it is missing or of a format
    this cadrev does not read."""
    if not (root / "project.yaml").is_file():
        findings.append(
            Finding(
                "error",
                "project-missing",
                f"{root / 'project.yaml'} not found; "
                "point cadrev at a project directory (cadrev init creates one)",
            )
        )
        return {}
    before = len(findings)
    meta = read_yaml(root, "project.yaml", findings)
    if any(f.rule == "yaml-syntax" for f in findings[before:]):
        return meta  # the syntax finding names the problem; the format cannot be read past it
    fmt = meta.get("format")
    if fmt is None:
        findings.append(
            Finding(
                "error",
                "format-missing",
                f"project.yaml: format is missing; this cadrev reads format: {FORMAT}",
            )
        )
    elif type(fmt) is not int or fmt != FORMAT:
        findings.append(
            Finding(
                "error",
                "format-unknown",
                f"project.yaml: format {fmt!r} is not one "
                f"this cadrev reads (it reads format: {FORMAT})",
            )
        )
    else:
        return meta
    return {}


def load(root: Path) -> Project:
    """The project at root. Never raises: missing or malformed files become findings."""
    root = root.resolve()
    findings: list[Finding] = []
    meta = read_meta(root, findings)
    refused = any(f.rule in REFUSED for f in findings)
    files = {
        name: {} if refused else read_yaml(root, name, findings)
        for name in schema.FILES
        if name != "project.yaml"
    }
    project = Project(
        root=root,
        meta=meta,
        evidence=files["evidence.yaml"].get("evidence", []),
        skipped=files["evidence.yaml"].get("skipped", []),
        conflicts=files["evidence.yaml"].get("conflicts", []),
        params=files["params.yaml"].get("params", {}),
        checks=files["checks.yaml"].get("checks", []),
        gaps={g["id"]: g for g in files["gaps.yaml"].get("gaps", [])},
        overlays=files["overlays.yaml"].get("overlays", []),
        datums=files["evidence.yaml"].get("datums", {}),
        parts=files["params.yaml"].get("parts", {}),
        findings=findings,
    )
    for eid in project.repeated:
        project.error("evidence-id", f"evidence {eid}: evidence ids must be unique")
    printed = Counter(str(c["id"]) for c in project.checks)
    for cid, n in printed.items():
        if n > 1:
            project.error("check-id", f"check {cid}: check ids must be unique")
    return project


def check_sources(p: Project) -> None:
    for sid, s in p.sources.items():
        if s.get("kind") not in SOURCE_KINDS:
            p.error("source-kind", f"source {sid}: kind must be one of {', '.join(SOURCE_KINDS)}")
        path = p.root / s.get("path", "")
        if not path.is_file():
            p.error(
                "source-missing",
                f"source {sid}: {s.get('path')} not found"
                + (f"; download from {s['url']}" if s.get("url") else ""),
            )
        else:
            if s.get("sha256") != sources.sha256(path):
                p.error("source-hash", f"source {sid}: sha256 does not match {s.get('path')}")
            if s.get("kind") == "geometry":
                try:
                    if released.is_sheet(path):
                        p.read_regions(sid)
                    else:
                        p.solids(sid)
                except Exception as exc:  # noqa: BLE001 - the STEP, STL and SVG readers raise many types
                    p.error(
                        "source-unreadable",
                        f"source {sid}: cannot read geometry from {s.get('path')}: "
                        f"{type(exc).__name__}: {exc}",
                    )
                    p.unreadable.add(sid)
            elif path.suffix.lower() in TEXT_FORMATS:
                try:
                    sources.pages(path)
                except Exception as exc:  # noqa: BLE001 - pypdf and zipfile raise many types
                    p.error(
                        "source-unreadable",
                        f"source {sid}: cannot read text from {s.get('path')}: "
                        f"{type(exc).__name__}: {exc}",
                    )
                    p.unreadable.add(sid)
        if not s.get("citation"):
            p.error("source-citation", f"source {sid}: citation is required")


def _available(p: Project, sid: str) -> bool:
    return (
        sid in p.sources
        and sid not in p.unreadable
        and (p.root / p.sources[sid].get("path", "")).is_file()
    )


# What to do with a value read from a number such as 1,250, by the kind of text it is read from.
_DISAMBIGUATE = {
    "quote": "quote the value where it is printed in another form, or skip it",
    "reading": "ledger the value from another statement of it, or leave it out",
}


def check_values(p: Project, eid: str, text: str, kind: str, values: dict) -> None:
    """[value-not-in-quote] or [value-not-in-reading] for each value text does not state, and
    [number-ambiguous] for each read from a number that a thousands comma and a decimal comma
    read differently."""
    stated = sources.numbers_in(text)
    ambiguous = sources.ambiguous_numbers(text)
    for key, value in values.items():
        value = float(value)
        if a := next((a for a in ambiguous if a.reads(value)), None):
            p.error(
                "number-ambiguous",
                f"{eid}.{key} = {value:g} is read from {a.printed} in its {kind}, which is "
                f"{a.thousands:g} with a thousands comma or {a.decimal:g} with a decimal comma; "
                + _DISAMBIGUATE[kind],
            )
        elif not any(math.isclose(value, q, rel_tol=1e-9) for q in stated):
            p.error(f"value-not-in-{kind}", f"{eid}.{key} = {value:g} is not in its {kind}")


def check_evidence(p: Project) -> None:
    # A statement of a direction needs no values where only claim checks cite it.
    keyed = {ref.partition(".")[0] for c in p.checks for ref in check_refs(c)}
    directions = claimed_items(p) - keyed
    for e in p.evidence:
        eid = e["id"]
        sid = e.get("source")
        if sid not in p.sources:
            p.error("evidence-source", f"{eid}: unknown source {sid!r}")
            continue
        values = e.get("values") or {}
        stated = "quote" in e and e.get("scope") != "context" and eid not in directions
        if not values and (stated or "probe" in e):
            p.error("evidence-values", f"{eid}: needs values (or scope: context)")
        if "quote" in e:
            if not _available(p, sid):
                continue
            if Path(p.sources[sid]["path"]).suffix.lower() not in TEXT_FORMATS:
                p.error(
                    "evidence-anchor",
                    f"{eid}: {sid} is not a text source; use image + reading instead of quote, "
                    "or probe for a geometry source",
                )
                continue
            match = sources.find_quote(p.source_path(sid), e["quote"], e.get("page"))
            if match is None:
                where = f" on page {e['page']}" if e.get("page") else ""
                p.error(
                    "quote-not-found", f"{eid}: quote not found in {sid}{where}: {e['quote']!r}"
                )
                continue
            if not e.get("page") and len(sources.pages(p.source_path(sid))) > 1:
                p.warn("quote-page", f"{eid}: add page: {match.page}")
            check_values(p, eid, e["quote"], "quote", values)
        elif "probe" in e:
            check_probe(p, e)
        elif "image" in e:
            image = p.root / e["image"]
            if not image.is_file():
                p.error("image-missing", f"{eid}: crop {e['image']} not found")
            elif e.get("image_sha256") != sources.sha256(image):
                p.error("image-hash", f"{eid}: image_sha256 does not match {e['image']}")
            if not e.get("reading"):
                p.error(
                    "image-reading", f"{eid}: image evidence needs reading: the text as printed"
                )
            else:
                check_values(p, eid, str(e["reading"]), "reading", values)
        else:
            p.error(
                "evidence-anchor",
                f"{eid}: needs quote (text sources), image + reading (figures, video) or "
                "probe (geometry sources)",
            )
        for key, value in values.items():
            printed = p.printed_units(f"{eid}.{key}")
            if len(printed) > 1:
                shown = " and ".join(
                    f"{value:g} {u}" if u else f"{value:g} with no unit" for u in printed
                )
                p.error(
                    "unit-ambiguous",
                    f"{eid}.{key} is printed as {shown} in its "
                    f"{'quote' if 'quote' in e else 'reading'}; quote only the part that states it",
                )
        if not e.get("locator"):
            p.error(
                "evidence-locator",
                f"{eid}: locator is required (e.g. 'Table S2', 'Fig. 2A', 'Sec. 4.2')",
            )


def _probe_bbox(p: Project, e: dict, body: str) -> dict[str, float] | str:
    """The size of body's bbox along the axis each of bbox probe e's values names in axes."""
    axes, values = e.get("axes") or {}, e.get("values") or {}
    for key in axes.keys() - values.keys():
        return f"axes names {key}, which values does not record"
    size = p.bodies[body].bounding_box().size
    out = {}
    for key in values:
        if axes.get(key) not in AXES:
            return f"{key} names no axis x, y or z in axes"
        out[key] = (size.X, size.Y, size.Z)[AXES[axes[key]]]
    return out


def _probe_datums(p: Project, e: dict, body: str, count: int) -> tuple[str, list] | str:
    """The one value key probe e records and the points of the count datums its between names,
    each declared on body."""
    between, values = e.get("between") or [], e.get("values") or {}
    if len(between) != count:
        return f"a {e['probe']} probe names {count} datums in between, not {len(between)}"
    if len(values) != 1:
        return f"a {e['probe']} probe records one value, not {len(values)}"
    points = []
    for name in between:
        named = p.released_datum(name)
        if named is None or named[0] != body:
            return f"{name} is not a datum declared on body {body}"
        points.append(named[1])
    (key,) = values
    return key, points


def _probe_distance(p: Project, e: dict, body: str) -> dict[str, float] | str:
    """The distance between distance probe e's two datums, along its axis where along names one."""
    read = _probe_datums(p, e, body, 2)
    if isinstance(read, str):
        return read
    (key, points), axis = read, e.get("along")
    if axis is not None and axis not in AXES:
        return f"along names no axis x, y or z: {axis}"
    return {key: released.datum_distance(points[0], points[1], axis)}


def _probe_angle(p: Project, e: dict, body: str) -> dict[str, float] | str:
    """The angle in degrees at the middle of angle probe e's three datums."""
    read = _probe_datums(p, e, body, 3)
    if isinstance(read, str):
        return read
    key, points = read
    angle = released.angle_at(points[0], points[1], points[2], p.length_tol)
    if angle is None:
        between = e["between"]
        return f"{between[0]} or {between[2]} coincides with the vertex {between[1]}"
    return {key: angle}


def _probe_diameter(p: Project, e: dict, body: str) -> dict[str, float] | str:
    """The diameter of the cylindrical face of body that diameter probe e's datum at lies on."""
    values = e.get("values") or {}
    if "at" not in e:
        return "a diameter probe names the datum it is taken at in at"
    if len(values) != 1:
        return f"a diameter probe records one value, not {len(values)}"
    at, named = str(e["at"]), p.released_datum(str(e["at"]))
    if named is None or named[0] != body:
        return f"{at} is not a datum declared on body {body}"
    found = released.diameter_at(p.bodies[body], named[1], p.length_tol)
    if isinstance(found, str):
        return f"{at} lies on {found} of body {body}"
    (key,) = values
    return {key: found}


# The kinds of check a probe reads a released body as, each with what it evaluates there: each
# value key's value in the project's units (an angle in degrees), or why it cannot be evaluated.
# Each is compared in its CHECK_KINDS quantity.
PROBE_KINDS = {
    "bbox": _probe_bbox,
    "distance": _probe_distance,
    "angle": _probe_angle,
    "diameter": _probe_diameter,
}


def check_probe(p: Project, e: dict) -> None:
    """Evaluate probe e on its released body (ADR-0011) and compare each value it records with
    what the body gives: [probe-mismatch] beyond its tolerance, tolerance.length or .angle unless
    it sets tol, capped as a check's is; [evidence-anchor] where it cannot be evaluated."""
    eid, sid = e["id"], str(e.get("source"))
    if p.sources[sid].get("kind") != "geometry":
        p.error("evidence-anchor", f"{eid}: a probe reads a geometry source, and {sid} is not one")
        return
    if sid in _unread_geometry(p):
        return  # check_sources says why its bodies cannot be read
    if sid in p.regions:
        p.error(
            "evidence-anchor",
            f"{eid}: {sid} is a cut file, whose regions a shape check compares; a probe reads a "
            "solid",
        )
        return
    body = str(e.get("body", sid))
    names = [b for b in p.bodies if released.source_of(b) == sid]
    if body not in names:
        p.error(
            "evidence-anchor",
            f"{eid}: {body} is not a body of {sid}; its bodies are {', '.join(names)}",
        )
        return
    if e["probe"] not in PROBE_KINDS:
        p.error(
            "evidence-anchor", f"{eid}: probe must be {', '.join(PROBE_KINDS)}, not {e['probe']!r}"
        )
        return
    quantity = CHECK_KINDS[e["probe"]].quantity
    evaluated = PROBE_KINDS[e["probe"]](p, e, body)
    if isinstance(evaluated, str):
        p.error("evidence-anchor", f"{eid}: {evaluated}")
        return
    for key, value in evaluated.items():
        recorded = p.value_as(f"{eid}.{key}", quantity)
        if recorded is None:
            continue  # a repeated id: [evidence-id] says so
        tol = float(e.get("tol", p.tolerance(quantity)))
        if _above_cap(tol, recorded):
            p.error(
                "tolerance-cap",
                f"probe {eid}: tol {tol:g} is above {TOL_CAP:.0%} of {eid}.{key}, {recorded:g}",
            )
        ok = abs(value - recorded) <= tol
        p.probes.append(
            {
                "evidence": eid,
                "key": key,
                "body": body,
                "probe": e["probe"],
                "recorded": recorded,
                "value": float(f"{value:.12g}"),
                "tol": tol,
                "ok": ok,
            }
        )
        if not ok:
            p.error(
                "probe-mismatch",
                f"probe {eid}.{key}: evaluates to {value:.6g} on body {body}, but records "
                f"{recorded:g} (tolerance {tol:g})",
            )


def _offsets(text: str, needle: str) -> list[int]:
    """Every offset where needle occurs in text, none for an empty needle."""
    offsets, start = [], text.find(needle) if needle else -1
    while start != -1:
        offsets.append(start)
        start = text.find(needle, start + 1)
    return offsets


def _quote_spans(page: str, quote: str) -> list[tuple[int, int]]:
    """Where quote occurs on a page normalized with its line-break hyphens marked by NUL, as spans
    of the page with those hyphens dropped: found with them dropped (inter-|toe), else kept
    (dual-|axis), its offsets then shifted back past each hyphen before them. As find_quote does,
    a quote not found as written is found ignoring whitespace, so a word the text breaks with a
    space (li ne) still matches."""
    dropped, kept = page.replace("\0", ""), page.replace("\0", "-")
    for squashed in (False, True):
        for reading, to_dropped in (
            (dropped, lambda i: i),
            (kept, lambda i: i - page.count("\0", 0, i)),
        ):
            # The offset in reading of each char searched: every char, or every non-space one.
            at = [i for i, ch in enumerate(reading) if not (squashed and ch.isspace())]
            searched = "".join(reading[i] for i in at)
            found = [
                (to_dropped(at[start]), to_dropped(at[start + len(needle) - 1] + 1))
                for needle in dict.fromkeys(
                    re.sub(r"\s+", "", n) if squashed else n for n in sources.needles(quote)
                )
                for start in _offsets(searched, needle)
            ]
            if found:
                return found
    return []


def check_coverage(p: Project) -> list[tuple[str, str, str]]:
    """The stated quantities in each text source that no evidence or skip entry covers, each
    where it is (p<page>), and the bodies of each geometry source that no shape check or skip
    covers (body <name>)."""
    uncovered = []
    for sid, s in p.sources.items():
        geometry = s.get("kind") == "geometry"
        if geometry and sid in _unread_geometry(p):
            continue  # check_sources says why its bodies cannot be read
        if not geometry and (
            not _available(p, sid) or Path(s["path"]).suffix.lower() not in TEXT_FORMATS
        ):
            continue
        if s.get("coverage") is False:
            p.warn(
                "coverage-off",
                f"source {sid}: coverage: false, so the sweep does not read it; "
                "any stated quantity in it may be unledgered",
            )
            continue
        if geometry:
            sheet = sid in p.regions
            uncovered += _uncovered_regions(p, sid) if sheet else _uncovered_bodies(p, sid)
            continue
        texts = sources.pages(p.source_path(sid))
        anchors = [e for e in p.evidence if e.get("source") == sid and "quote" in e]
        skips = [k for k in p.skipped if k.get("source") == sid]
        for k in skips:
            if not k.get("reason"):
                p.error("skip-reason", f"skip in {sid}: reason is required")
            if not ("quote" in k or "pages" in k or ("from" in k and "to" in k)):
                p.error("skip-anchor", f"skip in {sid}: needs quote, pages, or from + to")
        skipped_pages = {n for k in skips for n in k.get("pages", [])}
        matched: set[int] = set()  # the skips, by index into skips, that cover text on some page
        for n, raw in enumerate(texts, 1):
            if n in skipped_pages:
                continue
            page = sources.normalize(raw, hyphen="\0")
            text = page.replace("\0", "")
            spans = []
            for a in anchors + [k for k in skips if "quote" in k]:
                if a.get("page") not in (None, n):
                    continue
                found = _quote_spans(page, a["quote"])
                if found and any(a is k for k in skips):
                    matched.add(next(i for i, k in enumerate(skips) if k is a))
                spans += found
            for i, k in enumerate(skips):
                if "from" not in k or k.get("page") not in (None, n):
                    continue
                start = text.find(sources.normalize(k["from"]))
                stop = (
                    text.find(sources.normalize(k.get("to", "")), start + 1) if start != -1 else -1
                )
                if start != -1 and stop != -1:
                    spans.append((start, stop + len(sources.normalize(k.get("to", "")))))
                    matched.add(i)
            as_printed = sources.normalize(raw, hyphen="\0", cased=True).replace("\0", "")
            for start, end, snippet in sources.stated_quantities(text, as_printed):
                if not any(a <= start and end <= b for a, b in spans):
                    context = text[max(0, start - 60) : end + 40]
                    uncovered.append((sid, f"p{n}", f"{snippet}  …{context}…"))
        for i, k in enumerate(skips):
            if i in matched or "pages" in k or not ("quote" in k or ("from" in k and "to" in k)):
                continue
            where = f" p{k['page']}" if k.get("page") is not None else ""
            what = f"quote {k['quote']!r}" if "quote" in k else f"from {k['from']!r} to {k['to']!r}"
            p.error(
                "skip-not-found",
                f"skip in {sid}{where}: {what} matches no text of the source on any one page; "
                "copy it from `cadrev text`, and split a block that runs onto the next page",
            )
    for sid, where, line in uncovered:
        if where.startswith("body "):
            p.error("coverage", f"{sid} {where}: {line}")
        else:
            p.error("coverage", f"{sid} {where}: unledgered stated quantity {line}")
    return uncovered


def _uncovered_bodies(p: Project, sid: str) -> list[tuple[str, str, str]]:
    """The bodies of geometry source sid that no shape check compares and no skip sets aside, as
    check_coverage lists them; [skip-reason], [skip-anchor] and [skip-not-found] for its skips."""
    names = [b for b in p.bodies if released.source_of(b) == sid]
    compared = {str(c.get("body")) for c in p.checks if compares_body(c)}
    skipped = set()
    for k in (k for k in p.skipped if k.get("source") == sid):
        if not k.get("reason"):
            p.error("skip-reason", f"skip in {sid}: reason is required")
        if "body" not in k:
            p.error("skip-anchor", f"skip in {sid}: a geometry source's skip names its body")
        elif k["body"] not in names:
            p.error(
                "skip-not-found",
                f"skip in {sid}: body {k['body']} is not a body of {sid}; its bodies are "
                f"{', '.join(names)}",
            )
        skipped.add(k.get("body"))
    return [(sid, f"body {name}", _UNCOVERED) for name in names if name not in compared | skipped]


# Why coverage lists a released body.
_UNCOVERED = "no shape check compares it and no skip sets it aside"


def _uncovered_regions(p: Project, sid: str) -> list[tuple[str, str, str]]:
    """The regions of cut file sid that no shape check compares and no skip sets aside, each
    named by a point inside it, as check_coverage lists them; a skip sets aside the region a
    point inside it names (body), or every region inside a rectangle (within). [skip-reason],
    [skip-anchor] and [skip-not-found] for its skips."""
    found = p.regions[sid]
    covered = set()
    for c in p.checks:
        named = p.region(str(c.get("body"))) if compares_body(c) else None
        if isinstance(named, tuple) and named[0] == sid:
            covered.add(named[1])
    for k in (k for k in p.skipped if k.get("source") == sid):
        if not k.get("reason"):
            p.error("skip-reason", f"skip in {sid}: reason is required")
        if "body" in k:
            named = p.region(k["body"])
            if isinstance(named, str) or named[0] != sid:
                why = named if isinstance(named, str) else f"{k['body']} is not on {sid}"
                p.error("skip-not-found", f"skip in {sid}: {why}")
            else:
                covered.add(named[1])
        elif _rectangle(k.get("within")) is not None:
            inside = released.regions_within(found, _rectangle(k["within"]), p.length_tol)
            if not inside:
                p.error(
                    "skip-not-found",
                    f"skip in {sid}: within {k['within']} holds no whole region of {sid}",
                )
            covered |= set(inside)
        else:
            p.error(
                "skip-anchor",
                f"skip in {sid}: a cut file's skip names a region by a point inside it, "
                f"body: {sid}@<x>,<y>, or the regions inside a rectangle, "
                "within: [[x, y], [x, y]] at two opposite corners",
            )
    return [
        (sid, f"body {released.point_name(sid, released.inner_point(region))}", _UNCOVERED)
        for i, region in enumerate(found)
        if i not in covered
    ]


def _rectangle(within) -> tuple[tuple[float, float], tuple[float, float]] | None:
    """The rectangle a skip's within gives by two opposite corners [[x, y], [x, y]], as its least
    and greatest corner; None where within is not that."""
    if not (isinstance(within, list) and len(within) == 2 and all(len(c) == 2 for c in within)):
        return None
    (x0, y0), (x1, y1) = within
    return (min(x0, x1), min(y0, y1)), (max(x0, x1), max(y0, y1))


# What a derived param's expr or an expect is built from besides the names it reads: arithmetic,
# numbers and calls of MATH_NAMES.
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


def _evaluate(expr: str, names: dict[str, float]) -> float:
    tree = ast.parse(expr, mode="eval")
    for node in ast.walk(tree):
        if not isinstance(node, _EXPR_SYNTAX):
            raise ValueError(f"disallowed syntax {type(node).__name__}")
    return float(eval(compile(tree, "<expr>", "eval"), {"__builtins__": {}}, MATH_NAMES | names))


def expr_names(expr: str) -> set[str]:
    """Names a derived expression refers to; raises SyntaxError if it does not parse."""
    return {n.id for n in ast.walk(ast.parse(expr, mode="eval")) if isinstance(n, ast.Name)}


def _on_cycle(name: str, inputs: dict[str, set[str]]) -> bool:
    """Whether following name's inputs through the params in inputs leads back to name."""
    seen, todo = set(), list(inputs[name])
    while todo:
        if (n := todo.pop()) == name:
            return True
        if n in inputs and n not in seen:
            seen.add(n)
            todo += inputs[n]
    return False


def resolve_params(p: Project) -> None:
    """Fill p.values, enforcing each basis's obligations."""
    pending = dict(p.params)
    resolution = resolution_params(p)
    for name, spec in p.params.items():
        basis = spec.get("basis")
        if basis not in BASES:
            p.error("param-basis", f"param {name}: basis must be one of {', '.join(BASES)}")
            pending.pop(name)
            continue
        if basis == "source":
            ref = spec.get("from", "")
            value = p.evidence_value(ref)
            if value is None:
                why = p.cites_repeated(ref) or "is not an evidence value"
                p.error("param-from", f"param {name}: from: {ref!r} {why}")
            else:
                if "value" in spec and not math.isclose(float(spec["value"]), value, rel_tol=1e-9):
                    p.error(
                        "param-mismatch", f"param {name}: value {spec['value']} != {ref} = {value}"
                    )
                p.values[name] = value
            p.rests_on[name] = "source"
            pending.pop(name)
        elif basis == "measured":
            ref = str(spec.get("from", ""))
            item, why = p.item(ref.partition(".")[0]), p.cites_repeated(ref)
            if why:
                p.error("param-from", f"param {name}: from: {ref!r} {why}")
            elif item is None or "image" not in item:
                p.error("param-from", f"param {name}: measured needs from: an image evidence id")
            for key in ("value", "method", "uncertainty"):
                if key not in spec:
                    p.error("param-measured", f"param {name}: measured needs {key}")
            p.values[name] = float(spec.get("value", math.nan))
            p.rests_on[name] = "measured"
            pending.pop(name)
        elif basis == "proposed":
            if "value" not in spec or not spec.get("rationale"):
                p.error("param-proposed", f"param {name}: proposed needs value and rationale")
            # A sweep's resolution asks the sources nothing, so it has no gap to name.
            if not spec.get("gap") and name not in resolution:
                p.warn("param-gap", f"param {name}: proposed value names no gap to close it")
            p.values[name] = float(spec.get("value", math.nan))
            p.rests_on[name] = "proposed"
            pending.pop(name)
        elif basis == "derived" and spec.get("gap"):
            # Its expr is itself a reconstruction choice, so it rests on proposed below.
            if not spec.get("interpretation"):
                p.error(
                    "param-derived",
                    f"param {name}: derived naming a gap needs interpretation, "
                    "the choice its expr makes",
                )
        if spec.get("gap") and basis == "source":
            p.error("param-gap", f"param {name}: a source param has no value for a gap to replace")
        elif spec.get("gap") and spec["gap"] not in p.gaps:
            p.error("param-gap", f"param {name}: unknown gap {spec['gap']!r}")
    # Derived parameters may depend on each other; resolve until no progress.
    while pending:
        progressed = False
        for name, spec in list(pending.items()):
            if not spec.get("expr"):
                p.error("param-derived", f"param {name}: derived needs expr")
                pending.pop(name)
                continue
            try:
                needs = expr_names(spec["expr"]) - MATH_NAMES.keys()
            except (SyntaxError, ValueError) as exc:
                p.error(
                    "param-derived",
                    f"param {name}: expr is not valid syntax "
                    f"({getattr(exc, 'msg', exc)}): {spec['expr']!r}",
                )
                pending.pop(name)
                continue
            if not needs:
                p.error(
                    "param-constant",
                    f"param {name}: expr {spec['expr']!r} references no param, "
                    "so its value traces to nothing; give the number its own basis",
                )
            unknown = needs - p.params.keys()
            if unknown:
                p.error("param-derived", f"param {name}: expr uses undefined {sorted(unknown)}")
                pending.pop(name)
                continue
            if needs <= p.values.keys():
                try:
                    value = _evaluate(spec["expr"], p.values)
                except Exception as exc:  # noqa: BLE001 - report any evaluation failure
                    p.error("param-derived", f"param {name}: {exc}")
                    value = math.nan
                if "value" in spec and not math.isclose(float(spec["value"]), value, rel_tol=1e-6):
                    p.error(
                        "param-mismatch", f"param {name}: value {spec['value']} != expr = {value:g}"
                    )
                p.values[name] = value
                # A derived param naming a gap rests on proposed; a constant expr rests on
                # nothing, so it counts as the weakest basis.
                p.rests_on[name] = (
                    "proposed"
                    if spec.get("gap")
                    else max((p.rests_on[n] for n in needs), key=RESTS_ON.index, default="proposed")
                )
                pending.pop(name)
                progressed = True
        if pending and not progressed:
            # What is still pending waits on an input with no value; any not on a cycle names
            # the inputs it waits on.
            inputs = {
                name: expr_names(spec["expr"]) - MATH_NAMES.keys() for name, spec in pending.items()
            }
            for name in pending:
                if _on_cycle(name, inputs):
                    p.error("param-derived", f"param {name}: circular dependency")
                    continue
                missing = sorted(inputs[name] - p.values.keys())
                if len(missing) == 1:
                    p.error("param-derived", f"param {name}: input {missing[0]} has no value")
                else:
                    p.error(
                        "param-derived", f"param {name}: inputs {', '.join(missing)} have no value"
                    )
            break


def check_refs(c: dict) -> list[str]:
    """The evidence values a check compares with the geometry, those its expect names among them."""
    eid = c.get("evidence")
    return (
        [f"{eid}.{key}" for key in (c.get("axes") or {})]
        + ([f"{eid}.{c['key']}"] if c.get("key") else [])
        + [str(ref) for ref in c.get("ends") or []]
        + expect_refs(str(c.get("expect", "")))
    )


# A ledger value an expect names, <entry>.<key>: an evidence id, which may hold hyphens, then one
# of its values' keys.
_LEDGER_NAME = re.compile(r"(?<![\w.])([A-Za-z_][\w-]*)\.([A-Za-z_]\w*)")


def expect_refs(expr: str) -> list[str]:
    """The ledger values an expect names, <entry>.<key>, in order."""
    return list(dict.fromkeys(f"{m[1]}.{m[2]}" for m in _LEDGER_NAME.finditer(expr)))


def expect_value(p: Project, expr: str) -> float:
    """The value an expect works out from the ledger values it names, each read as
    Project.ledger_value reads it; raises ValueError saying why it cannot: it names a param, an
    unknown name, entry or key, or does not parse or evaluate."""
    refs, names = expect_refs(expr), {}
    for i, ref in enumerate(refs):
        entry, _, key = ref.partition(".")
        item = p.item(entry)
        if item is None:
            raise ValueError(f"{entry} is not a ledger entry")
        if key not in (item.get("values") or {}):
            raise ValueError(f"{entry} records no {key}")
        names[f"_ledger{i}"] = p.ledger_value(ref)
    text = _LEDGER_NAME.sub(lambda m: f"_ledger{refs.index(f'{m[1]}.{m[2]}')}", expr)
    try:
        tree = ast.parse(text, mode="eval")
    except SyntaxError as exc:
        raise ValueError(f"does not parse: {exc.msg}") from exc
    except (RecursionError, MemoryError) as exc:  # the parser's stack overflowing
        raise ValueError("does not parse: nested too deep") from exc
    for node in ast.walk(tree):
        if not isinstance(node, _EXPR_SYNTAX):
            raise ValueError(f"does not parse as arithmetic: {type(node).__name__}")
        if isinstance(node, ast.Constant):
            number = node.value
            if type(number) is not int and type(number) is not float:
                raise ValueError(f"does not parse as arithmetic: {number!r}")
            node.value = float(number)  # so a power overflows rather than running on
        if isinstance(node, ast.Name) and node.id not in names.keys() | MATH_NAMES.keys():
            if node.id in p.params:
                raise ValueError(
                    f"names param {node.id}; an expect reads only ledger values, <entry>.<key>"
                )
            raise ValueError(f"names {node.id}, neither a ledger value <entry>.<key> nor math")
    try:
        code = compile(tree, "<expect>", "eval")
        value = float(eval(code, {"__builtins__": {}}, MATH_NAMES | names))
    except (ArithmeticError, ValueError, TypeError, RecursionError) as exc:
        raise ValueError(f"does not evaluate: {exc}") from exc
    if not math.isfinite(value):
        raise ValueError(f"does not evaluate: it gives {value}")
    return value


def expect_config(p: Project, c: dict) -> list[str]:
    """Why check c's expect, or its want of one, leaves it nothing to compare with: an expect on a
    kind that compares no one value (CheckKind.expects), beside evidence, or that cannot be worked
    out (expect_value); or a kind that takes one naming neither it nor evidence. An expect citing a
    repeated evidence id is left to check_citations."""
    kind = CHECK_KINDS.get(str(c.get("kind")))
    if "expect" not in c:
        # A claim citing no evidence is claim_config's to name.
        missing = kind is not None and kind.expects and not {"evidence", "claim"} & c.keys()
        return (
            ["give evidence and key, or expect, the value it is compared with"] if missing else []
        )
    if kind is None or not kind.expects:
        return [f"expect is for a check that compares one value; kind {c.get('kind')} takes none"]
    if "evidence" in c:
        return ["give expect or evidence, not both"]
    expr = str(c["expect"])
    if any(p.cites_repeated(ref) for ref in expect_refs(expr)):
        return []
    try:
        expect_value(p, expr)
    except ValueError as exc:
        return [f"expect {expr!r}: {exc}"]
    return []


def check_expects(p: Project) -> None:
    """[check-config] for each check whose expect cannot be compared with, or that names neither
    an expect nor evidence, which the build then leaves unevaluated."""
    for c in p.checks:
        for problem in expect_config(p, c):
            p.error("check-config", f"check {c.get('id', '?')}: {problem}")


def compared_ref(c: dict) -> str:
    """What check c compares with, as its result names it: its expect, else the ledger value at
    its evidence and key; raises KeyError for a check naming neither."""
    return str(c["expect"]) if "expect" in c else f"{c['evidence']}.{c['key']}"


def pose_refs(c: dict) -> list[str]:
    """The joint values check c's poses name, its from pose's then its pose's: each a param or an
    <evidence>.<key> ledger value."""
    return [str(v) for key in POSES for v in (c.get(key) or {}).values()]


def claimed_items(p: Project) -> set[str]:
    """The evidence ids claim checks cite: each a statement of a direction, with no values."""
    return {str(c.get("evidence")) for c in p.checks if "claim" in c}


def cited_refs(p: Project, c: dict) -> list[str]:
    """The ledger values check c cites: those it compares, those its poses name, and for a claim
    the evidence item stating it."""
    claimed = [str(c["evidence"])] if "claim" in c and "evidence" in c else []
    return check_refs(c) + [ref for ref in pose_refs(c) if ref not in p.params] + claimed


def _kinds_taking(flag: str) -> str:
    """The check kinds whose CheckKind sets flag, as a finding names them: `distance, angle or
    stroke`."""
    names = [name for name, kind in CHECK_KINDS.items() if getattr(kind, flag)]
    return " or ".join(filter(None, [", ".join(names[:-1]), names[-1]]))


def claim_config(p: Project, c: dict) -> list[str]:
    """Why check c's claim or from pose cannot be evaluated: a claim on a kind that takes none
    (CheckKind.claims), or a from pose (CheckKind.changes); or on a kind that takes a claim, a key
    and a claim, neither, a claim not in CLAIMS, a tol or tol_rel beside a claim, or a claim citing
    no evidence item."""
    kind = CHECK_KINDS.get(str(c.get("kind")))
    if kind is None:
        return []
    refused = [
        f"{key} is for a {_kinds_taking(flag)} check; kind {c['kind']} takes none"
        for key, flag in (("claim", "claims"), ("from", "changes"))
        if key in c and not getattr(kind, flag)
    ]
    if refused or not kind.claims:
        return refused
    if "claim" not in c:
        return (
            []
            if "key" in c or "expect" in c
            else [
                "give key, the ledger value its stroke is compared with, "
                "or claim: shortens or lengthens"
            ]
        )
    if "key" in c:
        return ["give key or claim, not both"]
    problems = (
        [] if c["claim"] in CLAIMS else [f"claim {c['claim']} is neither {' nor '.join(CLAIMS)}"]
    )
    problems += [
        f"a claim passes only beyond tolerance.length, so it takes no {key}"
        for key in ("tol", "tol_rel")
        if key in c
    ]
    eid = c.get("evidence")
    if eid is None:
        problems.append("a claim cites the evidence item that states it")
    elif p.item(str(eid)) is None and not p.cites_repeated(str(eid)):
        problems.append(f"evidence {eid} is not an evidence item")
    return problems


def check_claims(p: Project) -> None:
    """[check-config] for each check whose claim or from pose cannot be evaluated, which the build
    then leaves unevaluated."""
    for c in p.checks:
        for problem in claim_config(p, c):
            p.error("check-config", f"check {c.get('id', '?')}: {problem}")


def calibration_ref(o: dict) -> str:
    """The ledger value overlay o is scaled by."""
    return str((o.get("calibration") or {}).get("evidence", ""))


def check_citations(p: Project) -> None:
    """A check or overlay citing a repeated evidence id reads neither item, so the build leaves it
    unevaluated; its finding is raised here, so it is raised whether or not the model builds."""
    for c in p.checks:
        for ref in cited_refs(p, c):
            why = p.cites_repeated(ref)
            if why:
                p.error("check-config", f"check {c.get('id', '?')}: {ref} {why}")
    for o in p.overlays:
        ref = calibration_ref(o)
        why = p.cites_repeated(ref)
        if why:
            p.error("overlay-config", f"overlay {o.get('id', '?')}: calibration {ref} {why}")


def mass_params(p: Project, parts=None) -> list[str]:
    """The params the mass model weighs parts by: every part's, or only those of parts."""
    entries = [p.parts.get(n) or {} for n in parts] if parts is not None else p.parts.values()
    return [str(v) for entry in entries for v in entry.values()]


def _sweep_steps(c: dict) -> list[str]:
    """The param naming how many poses check c's sweep evaluates, if it is swept."""
    return [str(c["sweep"].get("steps"))] if isinstance(c.get("sweep"), dict) else []


def params_read_by(
    p: Project, c: dict, steps: bool = True, weighs: tuple[str, ...] | None = None
) -> list[str]:
    """The params check c reads itself, in order: the params its pose names, its sweep's steps
    (unless steps is False), then those its kind reads (CheckKind.reads), a mass check's for the
    parts it weighs where weighs gives them."""
    kind = CHECK_KINDS.get(str(c.get("kind")))
    names = pose_refs(c) + (_sweep_steps(c) if steps else [])
    names += kind.reads(p, c, weighs) if kind is not None and kind.reads is not None else []
    return [n for n in dict.fromkeys(names) if n in p.params]


def check_params(p: Project) -> set[str]:
    """The params the checks read themselves."""
    return {name for c in p.checks for name in params_read_by(p, c)}


def resolution_params(p: Project) -> set[str]:
    """The params the checks read only as a sweep's steps; the build leaves out those the model
    reads too, and sets the rest as Project.resolution."""
    steps = {n for c in p.checks for n in _sweep_steps(c) if n in p.params}
    return steps - {n for c in p.checks for n in params_read_by(p, c, steps=False)}


def compares_body(c: dict) -> bool:
    """Whether check c compares a built part with a released body: a kind with a body_cap."""
    kind = CHECK_KINDS.get(str(c.get("kind")))
    return kind is not None and kind.body_cap is not None


def check_tolerance(p: Project, c: dict, quantity: str | None = None) -> tuple[str, float] | None:
    """The tolerance a check compares with, as (key, value): tol, in its quantity's project units
    (degrees for an angle), or tol_rel, a fraction; None for a kind that compares with no ledger
    value, or a mass check missing its tol_rel. quantity, where given, is the one a joint_valued
    check compares in, its joint's."""
    kind = CHECK_KINDS.get(str(c.get("kind")))
    if kind is None or kind.exact:
        return None
    if kind.tolerance is None:
        return ("tol_rel", float(c["tol_rel"])) if "tol_rel" in c else None
    return "tol", float(c.get("tol", p.tolerance(quantity or str(compared_quantity(c)))))


def compared_quantity(c: dict) -> str | None:
    """The quantity check c compares with the ledger: its kind's, or for between two datums its
    kind's between_two; None for an unknown kind."""
    kind = CHECK_KINDS.get(str(c.get("kind")))
    if kind is None:
        return None
    return kind.between_two if kind.between_two and between_two(c) else kind.quantity


def between_two(c: dict) -> bool:
    """Whether check c's between names two datums, a distance, rather than three, an angle."""
    between = c.get("between")
    return isinstance(between, list) and len(between) == 2


def joint_valued(c: dict) -> bool:
    """Whether check c compares its joint's own value, so in its joint's quantity: a joint_valued
    kind without between."""
    kind = CHECK_KINDS.get(str(c.get("kind")))
    return kind is not None and kind.joint_valued and "between" not in c


def default_tolerance(c: dict) -> tuple[str, float] | None:
    """cadrev's own tolerance for check c, where project.yaml and the check set none; None for a
    kind with no default."""
    check = CHECK_KINDS.get(str(c.get("kind")))
    if check is None or check.tolerance is None:
        return None
    return "tol", DEFAULT_TOL[str(compared_quantity(c))]


def default_overlap_limit(length_tol: float = LENGTH_TOL) -> float:
    """The overlap limit of an interference check that sets no max_volume: tolerance.length³,
    cadrev's default where project.yaml sets no tolerance.length."""
    return length_tol**3


def overlap_limit(p: Project, c: dict) -> float:
    """The most overlap an interference check lets instances have: max_volume, else the default."""
    return float(c.get("max_volume", default_overlap_limit(p.length_tol)))


def _tolerance_bases(p: Project, c: dict) -> list[tuple[str, float | None]]:
    """The values check c's tolerance is capped against, each with how it is named: each value it
    compares, or the span between its two for a span_capped kind."""
    if "expect" in c:
        try:
            return [(f"expect {c['expect']}", expect_value(p, str(c["expect"])))]
        except ValueError:
            return []  # check_expects says why
    refs, quantity = check_refs(c), compared_quantity(c)
    if CHECK_KINDS[str(c.get("kind"))].span_capped and len(refs) == 2:
        low, high = (p.value_as(ref, quantity) for ref in refs)
        span = None if low is None or high is None else high - low
        return [(f"the range {refs[0]} to {refs[1]}", span)]
    return [(ref, p.value_as(ref, quantity)) for ref in refs]


def _above_cap(tol: float, value: float) -> bool:
    """Whether tol is looser than TOL_CAP of value, the most a check or probe may stray by."""
    return tol > TOL_CAP * abs(value) * (1 + 1e-9)


def check_tolerances(p: Project) -> None:
    """No check is loosened past the cap: tol to TOL_CAP of each value it compares, tol_rel to
    TOL_REL_CAP."""
    for c in p.checks:
        cid, tolerance = c.get("id", "?"), check_tolerance(p, c)
        kind = CHECK_KINDS.get(str(c.get("kind")))
        for key in ("tol", "tol_rel") if kind is not None and kind.exact else ():
            if key in c:
                p.error(
                    "check-config",
                    f"check {cid}: a {c['kind']} check compares exactly, so it takes no {key}",
                )
        if tolerance is None:
            continue
        key, value = tolerance
        if key == "tol_rel":
            if value > TOL_REL_CAP:
                p.error(
                    "tolerance-cap",
                    f"check {cid}: tol_rel {value:g} is above the cap of {TOL_REL_CAP:g}",
                )
            continue
        where = "" if "tol" in c else f" (tolerance.{CHECK_KINDS[c['kind']].tolerance})"
        cap = CHECK_KINDS[c["kind"]].body_cap
        body = p.body(str(c.get("body"))) if cap is not None else None
        if cap is not None and body is not None and not isinstance(body, str):
            diagonal = body.bounding_box().diagonal
            if value > cap * diagonal * (1 + 1e-9):
                p.error(
                    "tolerance-cap",
                    f"check {cid}: tol {value:g}{where} is above {cap:.0%} of body "
                    f"{c['body']}'s bbox diagonal, {diagonal:.4g}",
                )
        for ref, expected in _tolerance_bases(p, c):
            if expected is not None and _above_cap(value, expected):
                p.error(
                    "tolerance-cap",
                    f"check {cid}: tol {value:g}{where} is above {TOL_CAP:.0%} "
                    f"of {ref}, {expected:g}",
                )
                break


def _unread_geometry(p: Project) -> set[str]:
    """The geometry sources whose bodies cannot be read: missing, or not readable as geometry."""
    read = {released.source_of(name) for name in p.bodies} | p.regions.keys()
    return {sid for sid, s in p.sources.items() if s.get("kind") == "geometry" and sid not in read}


def check_released_datums(p: Project) -> None:
    """[datum-off-solid] for each datum declared on released geometry that names no body, or does
    not lie on its body's solid (ADR-0006), as a datum model.py returns must lie on its part's."""
    bodies, unread = p.bodies, _unread_geometry(p)
    # every cut file, read or not, so an unread one's datums are still held to [x, y]
    sheets = [
        sid
        for sid, s in p.sources.items()
        if s.get("kind") == "geometry" and released.is_sheet(p.source_path(sid))
    ]
    for name, point in p.datums.items():
        sheet = next((s for s in sheets if name.startswith(f"{s}.")), None)
        if len(point) != (3 if sheet is None else 2):
            shape = "[x, y, z]" if sheet is None else f"[x, y] on cut file {sheet}"
            p.error("schema", f"evidence.yaml datums.{name}: must be {shape}, not {point}")
            continue
        if released.source_of(name.partition(".")[0]) in unread or sheet in unread:
            continue  # check_sources says why its body cannot be read
        if sheet is not None:
            if not released.outlines_at(p.regions[sheet], (point[0], point[1]), p.length_tol):
                p.error(
                    "datum-off-solid",
                    f"datum {name} of cut file {sheet}: lies inside no region's outer contour; "
                    "place it on a region, or at the centre of a hole in one",
                )
            continue
        named = p.released_datum(name)
        if named is None:
            p.error(
                "datum-off-solid",
                f"datum {name}: names no body of a geometry source, so it lies on no solid; "
                "name it <body>.<feature>, its body a geometry source's id or <source>#<n>",
            )
            continue
        body, point = named
        gap = released.off_solid(bodies[body], point, p.length_tol)
        if gap is not None:
            p.error(
                "datum-off-solid",
                f"datum {name} of body {body}: is {gap:.4g} from the nearest axis or face; "
                "place it on a hole's, pin's or pivot's axis, or on a face",
            )


def check_evidence_used(p: Project) -> None:
    """Every evidence value is used by a parameter, checked against geometry, or set aside."""
    used = {spec.get("from") for spec in p.params.values()}
    measured_from = {
        str(spec.get("from", "")).partition(".")[0]
        for spec in p.params.values()
        if spec.get("basis") == "measured"
    }
    checked = {ref for c in p.checks for ref in check_refs(c)}
    used |= checked | {ref for c in p.checks for ref in pose_refs(c)}
    for e in p.evidence:
        eid = e["id"]
        if eid in measured_from and not e.get("values"):
            continue
        if e.get("scope") in ("not-modeled", "context"):
            if not e.get("reason"):
                p.error("evidence-scope", f"{eid}: scope {e['scope']} needs a reason")
            continue
        for key in e.get("values") or {}:
            if f"{eid}.{key}" not in used:
                p.error(
                    "evidence-unused",
                    f"{eid}.{key} is neither used by a param nor checked "
                    "(or mark the item scope: not-modeled with a reason)",
                )


def check_gaps(p: Project) -> None:
    """Every gap is named by a param's gap; an id in a conflict's text does not count."""
    named = {spec.get("gap") for spec in p.params.values()}
    for gid in p.gaps:
        if gid not in named:
            p.warn("gap-unused", f"gap {gid}: no param names it")


def check_conflicts(p: Project) -> None:
    for c in p.conflicts:
        for eid in c.get("evidence", []):
            why = p.cites_repeated(eid)
            if why:
                p.error("conflict-ref", f"conflict {c.get('id')}: {why}")
            elif p.item(eid) is None:
                p.error("conflict-ref", f"conflict {c.get('id')}: unknown evidence {eid}")
        if not c.get("resolution"):
            p.warn("conflict-open", f"conflict {c.get('id')}: {c.get('summary', '')} (unresolved)")


def expect_quantity(p: Project, ref: str, expected: tuple[str, ...], use: str) -> None:
    """[unit-quantity] unless the evidence value at ref is printed in a unit of an expected
    quantity, or in no unit."""
    unit = p.unit_of(ref)
    if unit is not None and units.quantity(unit) not in expected:
        p.error(
            "unit-quantity",
            f"{ref} is printed in {unit}, a unit of {units.quantity(unit)}, "
            f"where {' or '.join(f'a {q}' for q in expected)} is expected ({use})",
        )


_SCALING = (
    ast.Expression,
    ast.Name,
    ast.Load,
    ast.Constant,
    ast.UnaryOp,
    ast.UAdd,
    ast.USub,
    ast.BinOp,
    ast.Mult,
    ast.Div,
)


def _traced(p: Project, name: str, through: tuple[str, ...] = ()) -> tuple[str, str] | None:
    """The source param a param's value copies, and the evidence value it is from: the param
    itself for basis source, or for basis derived the one param its expr scales by constants."""
    spec = p.params.get(name) or {}
    if spec.get("basis") == "source":
        return name, str(spec.get("from", ""))
    if spec.get("basis") != "derived" or name in through:
        return None
    try:
        tree = ast.parse(str(spec.get("expr", "")), mode="eval")
    except (SyntaxError, ValueError):
        return None  # already a param-derived finding
    names = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)} - MATH_NAMES.keys()
    if len(names) != 1 or not all(isinstance(n, _SCALING) for n in ast.walk(tree)):
        return None
    return _traced(p, names.pop(), (*through, name))


def expect_param_quantity(p: Project, name: str, expected: tuple[str, ...], use: str) -> None:
    """expect_quantity for the quote a param traces to, if it traces to one."""
    traced = _traced(p, name)
    if traced is not None:
        source, ref = traced
        via = f" through {name}" if source != name else ""
        expect_quantity(p, ref, expected, f"param {source}{via} {use}")


def _not_whole(value: float) -> bool:
    return math.isfinite(value) and value != round(value)


def expect_count(p: Project, ref: str, use: str) -> None:
    """[unit-quantity] unless the evidence value at ref reads as a count (ADR-0012): printed in a
    count unit or none, and a whole number."""
    expect_quantity(p, ref, ("count",), use)
    value = p.evidence_value(ref)
    if value is not None and _not_whole(value):
        p.error(
            "unit-quantity",
            f"{ref} = {value:g} is not a whole number, where a count is expected ({use})",
        )


def expect_param_count(p: Project, name: str, use: str, lengths: bool = False) -> None:
    """expect_count for a param: [unit-quantity] unless the quote it traces to prints a count
    unit or none, and its value is a whole number. Where lengths, a param whose quote prints a
    length, in a length unit or as a diameter callout (Ø 22.5), is read as a length instead, as a
    belt's pulley diameters are (ADR-0012)."""
    traced = _traced(p, name)
    unit = None if traced is None else p.unit_of(traced[1])
    if lengths and traced is not None and p.prints_length(traced[1]):
        return
    expect_param_quantity(p, name, ("count", "length") if lengths else ("count",), use)
    if unit is not None and units.quantity(unit) != "count":
        return  # [unit-quantity] says what it is read as
    value = p.values.get(name)
    if value is not None and _not_whole(value):
        p.error(
            "unit-quantity",
            f"param {name} = {value:g} is not a whole number, where a count is expected ({use})",
        )


def derived_from(p: Project, name: str, through: tuple[str, ...] = ()) -> list[str]:
    """The params a derived param's value is worked out from, through every derived param its
    expr references, in order: those with a basis of their own; none for a param not derived."""
    spec = p.params.get(name) or {}
    if spec.get("basis") != "derived" or name in through:
        return []
    try:
        needs = sorted(expr_names(str(spec.get("expr", ""))) - MATH_NAMES.keys())
    except (SyntaxError, ValueError):
        return []  # already a param-derived finding
    out = []
    for n in (n for n in needs if n in p.params):
        inner = derived_from(p, n, (*through, name))
        out += inner if (p.params[n] or {}).get("basis") == "derived" else [n]
    return list(dict.fromkeys(out))


def expect_joint_value(p: Project, ref: str, quantity: str | None, use: str) -> None:
    """expect_quantity for a joint value, a param's traced quote or a ledger value: of
    JOINT_QUANTITIES before the build, or of quantity, its joint's, after it. check_units has
    then held it to JOINT_QUANTITIES already, so only the other joint quantity is a finding."""
    expected = JOINT_QUANTITIES if quantity is None else (quantity,)
    if quantity is not None:
        traced = _traced(p, ref) if ref in p.params else (ref, ref)
        unit = None if traced is None else p.unit_of(traced[1])
        if unit is None or units.quantity(unit) not in JOINT_QUANTITIES:
            return
    if ref in p.params:
        expect_param_quantity(p, ref, expected, use)
    else:
        expect_quantity(p, ref, expected, use)


def check_units(p: Project) -> None:
    """The project names a unit for each quantity it sets, and each evidence value is used as
    the quantity its printed unit measures."""
    for q, spelled in (p.meta.get("units") or {}).items():
        unit, problem = units.declared(q, spelled)
        if unit is None:
            p.error("units", f"project.yaml units.{q}: {problem}")
    for c in p.checks:
        cid, kind = c.get("id", "?"), c.get("kind")
        if kind in CHECK_KINDS:
            expected = (str(compared_quantity(c)),)
            if joint_valued(c):
                expected = JOINT_QUANTITIES  # the build holds each to its joint's
            # An expect's ledger values are of whatever quantities its arithmetic combines.
            for ref in [] if "expect" in c else check_refs(c):
                if expected == ("count",):
                    expect_count(p, ref, f"check {cid}")
                else:
                    expect_quantity(p, ref, expected, f"check {cid}")
        for key in POSES:
            for ref in (c.get(key) or {}).values():
                expect_joint_value(p, str(ref), None, f"in check {cid}'s {key}")
        named = CHECK_KINDS[kind].names if kind in CHECK_KINDS else None
        for name, quantity in named(c) if named else []:
            if quantity == "count":
                expect_param_count(p, name, f"in check {cid}")
            else:
                expect_param_quantity(p, name, (quantity,), f"in check {cid}")
    for part, entry in p.parts.items():
        for by, name in entry.items():
            expect_param_quantity(p, name, (by,), f"in params.yaml parts.{part}")
    for o in p.overlays:
        ref = (o.get("calibration") or {}).get("evidence")
        if ref:
            expect_quantity(p, ref, ("length",), f"overlay {o.get('id', '?')} calibration")


def check_static(p: Project) -> None:
    target = str(p.meta.get("target") or "")
    if not target or target.startswith("TODO"):
        p.error(
            "target",
            "project.yaml target: name the object, version and configuration reconstructed",
        )
    check_sources(p)
    check_evidence(p)
    check_released_datums(p)
    resolve_params(p)
    check_evidence_used(p)
    check_gaps(p)
    check_conflicts(p)
    check_citations(p)
    check_claims(p)
    check_expects(p)
    check_units(p)
    check_tolerances(p)
    lint.lint_model(p)
