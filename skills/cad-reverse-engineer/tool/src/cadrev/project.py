"""Project files and every check that needs no geometry.

The rule the whole package enforces: a number reaches the CAD only through
params.yaml, every parameter declares its basis, and every source-basis value
is a verbatim quote (or a pinned figure crop) found in a hashed source.
"""

from __future__ import annotations

import ast
import math
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from . import schema, sources, units

FORMAT = 1  # the project.yaml format this cadrev reads
# Findings after which nothing else in the project is read and every command refuses it.
REFUSED = ("project-missing", "format-missing", "format-unknown")
BASES = ("source", "derived", "measured", "proposed")
# What a parameter can rest on, strongest first: a derived one rests on the weakest of its inputs.
RESTS_ON = ("source", "measured", "proposed")
LENGTH_TOL = 1e-3  # tolerance.length when project.yaml sets none
# The loosest tolerance a check may have: tol as a fraction of each value it compares, and tol_rel.
TOL_CAP, TOL_REL_CAP = 0.05, 0.25
SOURCE_KINDS = ("paper", "supplement", "datasheet", "video", "drawing", "other")
TEXT_FORMATS = {".pdf", ".docx", ".txt", ".md", ".html", ".htm"}
MATH_NAMES = {
    name: getattr(math, name)
    for name in ("pi", "sqrt", "sin", "cos", "tan", "asin", "acos", "atan", "atan2",
                 "radians", "degrees", "hypot")
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
    evidence: dict[str, dict]
    skipped: list[dict]
    conflicts: list[dict]
    params: dict[str, dict]
    checks: list[dict]
    gaps: dict[str, dict]
    overlays: list[dict]
    values: dict[str, float] = field(default_factory=dict)
    # Text sources whose file exists but cannot be read as text.
    unreadable: set[str] = field(default_factory=set)
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
    def sources(self) -> dict[str, dict]:
        return {s["id"]: s for s in self.meta.get("sources", [])}

    def source_path(self, source_id: str) -> Path:
        return self.root / self.sources[source_id]["path"]

    @property
    def length_tol(self) -> float:
        return float(self.meta.get("tolerance", {}).get("length", LENGTH_TOL))

    @property
    def units(self) -> dict[str, str]:
        """The unit of each base quantity: the project's where it names a valid one, else the default."""
        out = dict(units.BASE)
        for q, spelled in (self.meta.get("units") or {}).items():
            unit, _ = units.declared(q, spelled)
            if unit is not None:
                out[q] = unit
        return out

    def _ledgered(self, ref: str) -> tuple[float, str] | None:
        """An evidence value as printed, with the quote or reading it is printed in."""
        item_id, _, key = ref.partition(".")
        item = self.evidence.get(item_id)
        if item is None or key not in item.get("values", {}):
            return None
        return float(item["values"][key]), item["quote"] if "quote" in item else str(item.get("reading", ""))

    def printed_units(self, ref: str) -> list[str | None]:
        """The units printed after each appearance of an evidence value in its quote or reading."""
        ledgered = self._ledgered(ref)
        if ledgered is None:
            return []
        value, text = ledgered
        return list(dict.fromkeys(unit for v, unit in sources.quantities_in(text)
                                  if math.isclose(v, value, rel_tol=1e-9)))

    def unit_of(self, ref: str) -> str | None:
        """The unit an evidence value is printed in; None (the project's units) if none is printed."""
        printed = self.printed_units(ref)
        return printed[0] if printed else None

    def evidence_value(self, ref: str) -> float | None:
        """An evidence value in the project's units, converted from the unit printed in its quote."""
        ledgered = self._ledgered(ref)
        if ledgered is None:
            return None
        value, unit = ledgered[0], self.unit_of(ref)
        return value if unit is None else units.convert(value, unit, self.units)


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
        findings.append(Finding("error", "project-missing", f"{root / 'project.yaml'} not found; "
                                "point cadrev at a project directory (cadrev init creates one)"))
        return {}
    before = len(findings)
    meta = read_yaml(root, "project.yaml", findings)
    if any(f.rule == "yaml-syntax" for f in findings[before:]):
        return meta  # the syntax finding names the problem; the format cannot be read past it
    fmt = meta.get("format")
    if fmt is None:
        findings.append(Finding("error", "format-missing",
                                f"project.yaml: format is missing; this cadrev reads format: {FORMAT}"))
    elif type(fmt) is not int or fmt != FORMAT:
        findings.append(Finding("error", "format-unknown", f"project.yaml: format {fmt!r} is not one "
                                f"this cadrev reads (it reads format: {FORMAT})"))
    else:
        return meta
    return {}


def load(root: Path) -> Project:
    """The project at root. Never raises: missing or malformed files become findings."""
    root = root.resolve()
    findings: list[Finding] = []
    meta = read_meta(root, findings)
    refused = any(f.rule in REFUSED for f in findings)
    files = {name: {} if refused else read_yaml(root, name, findings)
             for name in schema.FILES if name != "project.yaml"}
    evidence_list = files["evidence.yaml"].get("evidence", [])
    project = Project(
        root=root,
        meta=meta,
        evidence={e["id"]: e for e in evidence_list},
        skipped=files["evidence.yaml"].get("skipped", []),
        conflicts=files["evidence.yaml"].get("conflicts", []),
        params=files["params.yaml"].get("params", {}),
        checks=files["checks.yaml"].get("checks", []),
        gaps={g["id"]: g for g in files["gaps.yaml"].get("gaps", [])},
        overlays=files["overlays.yaml"].get("overlays", []),
        findings=findings,
    )
    if len(project.evidence) != len(evidence_list):
        project.error("evidence-id", "evidence ids must be unique")
    return project


def check_sources(p: Project) -> None:
    for sid, s in p.sources.items():
        if s.get("kind") not in SOURCE_KINDS:
            p.error("source-kind", f"source {sid}: kind must be one of {', '.join(SOURCE_KINDS)}")
        path = p.root / s.get("path", "")
        if not path.is_file():
            p.error("source-missing", f"source {sid}: {s.get('path')} not found"
                    + (f"; download from {s['url']}" if s.get("url") else ""))
        else:
            if s.get("sha256") != sources.sha256(path):
                p.error("source-hash", f"source {sid}: sha256 does not match {s.get('path')}")
            if path.suffix.lower() in TEXT_FORMATS:
                try:
                    sources.pages(path)
                except Exception as exc:  # noqa: BLE001 - pypdf and zipfile raise many types
                    p.error("source-unreadable", f"source {sid}: cannot read text from {s.get('path')}: "
                            f"{type(exc).__name__}: {exc}")
                    p.unreadable.add(sid)
        if not s.get("citation"):
            p.error("source-citation", f"source {sid}: citation is required")


def _available(p: Project, sid: str) -> bool:
    return (sid in p.sources and sid not in p.unreadable
            and (p.root / p.sources[sid].get("path", "")).is_file())


def check_evidence(p: Project) -> None:
    for eid, e in p.evidence.items():
        sid = e.get("source")
        if sid not in p.sources:
            p.error("evidence-source", f"{eid}: unknown source {sid!r}")
            continue
        values = e.get("values") or {}
        if not values and "quote" in e and e.get("scope") != "context":
            p.error("evidence-values", f"{eid}: needs values (or scope: context)")
        if "quote" in e:
            if not _available(p, sid):
                continue
            if Path(p.sources[sid]["path"]).suffix.lower() not in TEXT_FORMATS:
                p.error("evidence-anchor", f"{eid}: {sid} is not a text source; "
                        "use image + reading instead of quote")
                continue
            match = sources.find_quote(p.source_path(sid), e["quote"], e.get("page"))
            if match is None:
                where = f" on page {e['page']}" if e.get("page") else ""
                p.error("quote-not-found", f"{eid}: quote not found in {sid}{where}: {e['quote']!r}")
                continue
            if not e.get("page") and len(sources.pages(p.source_path(sid))) > 1:
                p.warn("quote-page", f"{eid}: add page: {match.page}")
            quoted = sources.numbers_in(e["quote"])
            for key, value in values.items():
                if not any(math.isclose(float(value), q, rel_tol=1e-9) for q in quoted):
                    p.error("value-not-in-quote", f"{eid}.{key} = {value} does not appear in its quote")
        elif "image" in e:
            image = p.root / e["image"]
            if not image.is_file():
                p.error("image-missing", f"{eid}: crop {e['image']} not found")
            elif e.get("image_sha256") != sources.sha256(image):
                p.error("image-hash", f"{eid}: image_sha256 does not match {e['image']}")
            if not e.get("reading"):
                p.error("image-reading", f"{eid}: image evidence needs reading: the text as printed")
            else:
                read = sources.numbers_in(str(e["reading"]))
                for key, value in values.items():
                    if not any(math.isclose(float(value), q, rel_tol=1e-9) for q in read):
                        p.error("value-not-in-reading", f"{eid}.{key} = {value} not in its reading")
        else:
            p.error("evidence-anchor", f"{eid}: needs quote (text sources) or image + reading (figures, video)")
        for key, value in values.items():
            printed = p.printed_units(f"{eid}.{key}")
            if len(printed) > 1:
                shown = " and ".join(f"{value:g} {u}" if u else f"{value:g} with no unit" for u in printed)
                p.error("unit-ambiguous", f"{eid}.{key} is printed as {shown} in its "
                        f"{'quote' if 'quote' in e else 'reading'}; quote only the part that states it")
        if not e.get("locator"):
            p.error("evidence-locator", f"{eid}: locator is required (e.g. 'Table S2', 'Fig. 2A', 'Sec. 4.2')")


def check_coverage(p: Project) -> list[tuple[str, int, str]]:
    """The stated quantities in each source that no evidence or skip entry covers."""
    uncovered = []
    for sid, s in p.sources.items():
        if not _available(p, sid) or Path(s["path"]).suffix.lower() not in TEXT_FORMATS:
            continue
        if s.get("coverage") is False:
            p.warn("coverage-off", f"source {sid}: coverage: false, so the sweep does not read it; "
                   "any stated quantity in it may be unledgered")
            continue
        texts = sources.pages(p.source_path(sid))
        anchors = [e for e in p.evidence.values() if e.get("source") == sid and "quote" in e]
        skips = [k for k in p.skipped if k.get("source") == sid]
        for k in skips:
            if not k.get("reason"):
                p.error("skip-reason", f"skip in {sid}: reason is required")
            if not ("quote" in k or "pages" in k or ("from" in k and "to" in k)):
                p.error("skip-anchor", f"skip in {sid}: needs quote, pages, or from + to")
        skipped_pages = {n for k in skips for n in k.get("pages", [])}
        for n, raw in enumerate(texts, 1):
            if n in skipped_pages:
                continue
            text = sources.normalize(raw)
            spans = []
            for a in anchors + [k for k in skips if "quote" in k]:
                if a.get("page") not in (None, n):
                    continue
                needle = sources.normalize(a["quote"])
                start = text.find(needle)
                while needle and start != -1:
                    spans.append((start, start + len(needle)))
                    start = text.find(needle, start + 1)
            for k in skips:
                if "from" not in k or k.get("page") not in (None, n):
                    continue
                start = text.find(sources.normalize(k["from"]))
                stop = text.find(sources.normalize(k.get("to", "")), start + 1) if start != -1 else -1
                if start != -1 and stop != -1:
                    spans.append((start, stop + len(sources.normalize(k.get("to", "")))))
            for start, end, snippet in sources.stated_quantities(text):
                if not any(a <= start and end <= b for a, b in spans):
                    context = text[max(0, start - 60):end + 40]
                    uncovered.append((sid, n, f"{snippet}  …{context}…"))
    for sid, n, line in uncovered:
        p.error("coverage", f"{sid} p{n}: unledgered stated quantity {line}")
    return uncovered


def _evaluate(expr: str, names: dict[str, float]) -> float:
    tree = ast.parse(expr, mode="eval")
    allowed = (ast.Expression, ast.BinOp, ast.UnaryOp, ast.Call, ast.Name, ast.Load,
               ast.Constant, ast.operator, ast.unaryop)
    for node in ast.walk(tree):
        if not isinstance(node, allowed):
            raise ValueError(f"disallowed syntax {type(node).__name__}")
    return float(eval(compile(tree, "<expr>", "eval"), {"__builtins__": {}}, MATH_NAMES | names))


def expr_names(expr: str) -> set[str]:
    """Names a derived expression refers to; raises SyntaxError if it does not parse."""
    return {n.id for n in ast.walk(ast.parse(expr, mode="eval")) if isinstance(n, ast.Name)}


def resolve_params(p: Project) -> None:
    """Fill p.values, enforcing each basis's obligations."""
    pending = dict(p.params)
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
                p.error("param-from", f"param {name}: from: {ref!r} is not an evidence value")
            else:
                if "value" in spec and not math.isclose(float(spec["value"]), value, rel_tol=1e-9):
                    p.error("param-mismatch", f"param {name}: value {spec['value']} != {ref} = {value}")
                p.values[name] = value
            p.rests_on[name] = "source"
            pending.pop(name)
        elif basis == "measured":
            item = p.evidence.get(str(spec.get("from", "")).partition(".")[0])
            if item is None or "image" not in item:
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
            if not spec.get("gap"):
                p.warn("param-gap", f"param {name}: proposed value names no gap to close it")
            elif spec["gap"] not in p.gaps:
                p.error("param-gap", f"param {name}: unknown gap {spec['gap']!r}")
            p.values[name] = float(spec.get("value", math.nan))
            p.rests_on[name] = "proposed"
            pending.pop(name)
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
                p.error("param-derived", f"param {name}: expr is not valid syntax "
                        f"({getattr(exc, 'msg', exc)}): {spec['expr']!r}")
                pending.pop(name)
                continue
            if not needs:
                p.error("param-constant", f"param {name}: expr {spec['expr']!r} references no param, "
                        "so its value traces to nothing; give the number its own basis")
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
                    p.error("param-mismatch", f"param {name}: value {spec['value']} != expr = {value:g}")
                p.values[name] = value
                # A constant expr rests on nothing, so it counts as the weakest basis.
                p.rests_on[name] = max((p.rests_on[n] for n in needs), key=RESTS_ON.index,
                                       default="proposed")
                pending.pop(name)
                progressed = True
        if pending and not progressed:
            for name in pending:
                p.error("param-derived", f"param {name}: circular dependency")
            break


# The quantity of the evidence values each check kind compares with the geometry.
CHECK_READS = {"bbox": "length", "distance": "length", "mass": "mass"}


def check_refs(c: dict) -> list[str]:
    """The evidence values a check compares with the geometry."""
    eid = c.get("evidence")
    return [f"{eid}.{key}" for key in (c.get("axes") or {})] + ([f"{eid}.{c['key']}"] if c.get("key") else [])


def check_tolerance(p: Project, c: dict) -> tuple[str, float] | None:
    """The tolerance a check compares with, as (key, value): tol, a length, for bbox and distance,
    tol_rel, a fraction, for mass; None for a check of another kind."""
    if c.get("kind") in ("bbox", "distance"):
        return "tol", float(c.get("tol", p.length_tol))
    if c.get("kind") == "mass" and "tol_rel" in c:
        return "tol_rel", float(c["tol_rel"])
    return None


def overlap_limit(p: Project, c: dict) -> float:
    """The most overlap an interference check lets instances have: max_volume, else tolerance.length³."""
    return float(c.get("max_volume", p.length_tol ** 3))


def check_tolerances(p: Project) -> None:
    """No check is loosened past the cap: tol to TOL_CAP of each value it compares, tol_rel to TOL_REL_CAP."""
    for c in p.checks:
        cid, tolerance = c.get("id", "?"), check_tolerance(p, c)
        if tolerance is None:
            continue
        key, value = tolerance
        if key == "tol_rel":
            if value > TOL_REL_CAP:
                p.error("tolerance-cap", f"check {cid}: tol_rel {value:g} is above the cap of {TOL_REL_CAP:g}")
            continue
        where = "" if "tol" in c else " (tolerance.length)"
        for ref in check_refs(c):
            expected = p.evidence_value(ref)
            if expected is not None and value > TOL_CAP * abs(expected) * (1 + 1e-9):
                p.error("tolerance-cap", f"check {cid}: tol {value:g}{where} is above {TOL_CAP:.0%} "
                        f"of {ref}, {expected:g}")
                break


def check_accounting(p: Project) -> None:
    """Every evidence value is used by a parameter, checked against geometry, or set aside."""
    used = {spec.get("from") for spec in p.params.values()}
    measured_from = {str(spec.get("from", "")).partition(".")[0]
                     for spec in p.params.values() if spec.get("basis") == "measured"}
    checked = {ref for c in p.checks for ref in check_refs(c)}
    used |= checked
    for eid, e in p.evidence.items():
        if eid in measured_from and not e.get("values"):
            continue
        if e.get("scope") in ("not-modeled", "context"):
            if not e.get("reason"):
                p.error("evidence-scope", f"{eid}: scope {e['scope']} needs a reason")
            continue
        for key in e.get("values") or {}:
            if f"{eid}.{key}" not in used:
                p.error("evidence-unused", f"{eid}.{key} is neither used by a param nor checked "
                        "(or mark the item scope: not-modeled with a reason)")
    for name, spec in p.params.items():
        if spec.get("basis") == "source" and spec.get("from") not in checked:
            p.warn("unchecked-source", f"param {name}: {spec.get('from')} feeds the model but no "
                   "check confirms the geometry realises it")


def check_conflicts(p: Project) -> None:
    for c in p.conflicts:
        for eid in c.get("evidence", []):
            if eid not in p.evidence:
                p.error("conflict-ref", f"conflict {c.get('id')}: unknown evidence {eid}")
        if not c.get("resolution"):
            p.warn("conflict-open", f"conflict {c.get('id')}: {c.get('summary', '')} (unresolved)")


def expect_quantity(p: Project, ref: str, expected: tuple[str, ...], use: str) -> None:
    """[unit-quantity] unless the evidence value at ref is printed in a unit of an expected
    quantity, or in no unit."""
    unit = p.unit_of(ref)
    if unit is not None and units.quantity(unit) not in expected:
        p.error("unit-quantity", f"{ref} is printed in {unit}, a unit of {units.quantity(unit)}, "
                f"where {' or '.join(f'a {q}' for q in expected)} is expected ({use})")


_SCALING = (ast.Expression, ast.Name, ast.Load, ast.Constant, ast.UnaryOp, ast.UAdd, ast.USub,
            ast.BinOp, ast.Mult, ast.Div)


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


def check_units(p: Project) -> None:
    """The project names a unit for each quantity it sets, and each evidence value is used as
    the quantity its printed unit measures."""
    for q, spelled in (p.meta.get("units") or {}).items():
        unit, problem = units.declared(q, spelled)
        if unit is None:
            p.error("units", f"project.yaml units.{q}: {problem}")
    for c in p.checks:
        cid, kind = c.get("id", "?"), c.get("kind")
        if kind in CHECK_READS:
            for ref in check_refs(c):
                expect_quantity(p, ref, (CHECK_READS[kind],), f"check {cid}")
        if kind == "mass":
            expect_param_quantity(p, c.get("density") or "", ("density",), f"in check {cid}")
            for name in c.get("add", []):
                expect_param_quantity(p, name, ("mass",), f"in check {cid}")
    for o in p.overlays:
        ref = (o.get("calibration") or {}).get("evidence")
        if ref:
            expect_quantity(p, ref, ("length",), f"overlay {o.get('id', '?')} calibration")


def lint_model(p: Project) -> None:
    """model.py may hold no dimension literals; every number comes through params."""
    path = p.root / "model.py"
    if not path.is_file():
        p.error("model-missing", "model.py not found")
        return
    allowed = {float(v) for v in p.meta.get("model_literals", [0, 1, 2, -1, 0.5, 90, 180, 270, 360])}
    try:
        tree = ast.parse(path.read_text(encoding="utf8"))
    except (SyntaxError, ValueError) as exc:  # ValueError: null bytes or undecodable text
        line = getattr(exc, "lineno", None)
        where = f"model.py line {line}" if line else "model.py"
        p.error("model-syntax", f"{where}: {getattr(exc, 'msg', exc)}")
        return
    for node in ast.walk(tree):
        if (isinstance(node, ast.Constant) and isinstance(node.value, (int, float))
                and not isinstance(node.value, bool) and float(node.value) not in allowed):
            p.error("model-literal", f"model.py:{node.lineno}: literal {node.value!r}; "
                    "move it to params.yaml with a basis")


def check_static(p: Project) -> None:
    target = str(p.meta.get("target") or "")
    if not target or target.startswith("TODO"):
        p.error("target", "project.yaml target: name the object, version and configuration reconstructed")
    check_sources(p)
    check_evidence(p)
    resolve_params(p)
    check_accounting(p)
    check_conflicts(p)
    check_units(p)
    check_tolerances(p)
    lint_model(p)
