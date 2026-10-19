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

from . import lint, schema, sources, units

FORMAT = 1  # the project.yaml format this cadrev reads
# Findings after which nothing else in the project is read and every command refuses it.
REFUSED = ("project-missing", "format-missing", "format-unknown")
BASES = ("source", "derived", "measured", "proposed")
# What a parameter can rest on, strongest first: a derived one rests on the weakest of its inputs.
RESTS_ON = ("source", "measured", "proposed")
LENGTH_TOL = 1e-3  # tolerance.length when project.yaml sets none
ANGLE_TOL = 0.01  # tolerance.angle, in degrees, when project.yaml sets none
DEFAULT_TOL = {"length": LENGTH_TOL, "angle": ANGLE_TOL}
# The loosest tolerance a check may have: tol as a fraction of each value it compares, and tol_rel.
TOL_CAP, TOL_REL_CAP = 0.05, 0.25


@dataclass(frozen=True)
class CheckKind:
    """What a kind of check compares with the geometry: evidence values of quantity, within tol,
    which defaults to project.yaml's tolerance.<tolerance>; or, where tolerance is None, within
    tol_rel, a fraction of the value, which has no default."""

    quantity: str
    tolerance: str | None


# The kinds of check that compare with a ledger value; interference compares with none.
CHECK_KINDS = {
    "bbox": CheckKind("length", "length"),
    "distance": CheckKind("length", "length"),
    "angle": CheckKind("angle", "angle"),
    "mass": CheckKind("mass", None),
}
SOURCE_KINDS = ("paper", "supplement", "datasheet", "video", "drawing", "other")
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
    evidence: dict[str, dict]
    skipped: list[dict]
    conflicts: list[dict]
    params: dict[str, dict]
    checks: list[dict]
    gaps: dict[str, dict]
    overlays: list[dict]
    # The mass model: part -> {mass: param} or {density: param}, from params.yaml's parts.
    parts: dict[str, dict] = field(default_factory=dict)
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
    def physics(self) -> set[str]:
        """Parameters marked physics: true: values the MJCF export applies and no geometry reads,
        left out of exact (ADR-0008)."""
        return {name for name, spec in self.params.items() if spec.get("physics") is True}

    @property
    def sources(self) -> dict[str, dict]:
        return {s["id"]: s for s in self.meta.get("sources", [])}

    def source_path(self, source_id: str) -> Path:
        return self.root / self.sources[source_id]["path"]

    def tolerance(self, quantity: str) -> float:
        """project.yaml's tolerance.<quantity>, else cadrev's default; an angle's in degrees."""
        return float(self.meta.get("tolerance", {}).get(quantity, DEFAULT_TOL[quantity]))

    @property
    def length_tol(self) -> float:
        return self.tolerance("length")

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

    def compared_value(self, ref: str, kind: str) -> float | None:
        """The evidence value a check of kind compares with: an angle in degrees, since an angle
        check evaluates in degrees whatever the project's angle unit, else in the project's units."""
        value = self.evidence_value(ref)
        check = CHECK_KINDS.get(kind)
        if value is None or check is None or check.quantity != "angle":
            return value
        return value * units.size("angle", self.units) / units.UNITS["deg"].si


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
        parts=files["params.yaml"].get("parts", {}),
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
            p.error(
                "source-missing",
                f"source {sid}: {s.get('path')} not found"
                + (f"; download from {s['url']}" if s.get("url") else ""),
            )
        else:
            if s.get("sha256") != sources.sha256(path):
                p.error("source-hash", f"source {sid}: sha256 does not match {s.get('path')}")
            if path.suffix.lower() in TEXT_FORMATS:
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
                p.error(
                    "evidence-anchor",
                    f"{eid}: {sid} is not a text source; use image + reading instead of quote",
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
                f"{eid}: needs quote (text sources) or image + reading (figures, video)",
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
    (dual-|axis), its offsets then shifted back past each hyphen before them."""
    dropped, kept = page.replace("\0", ""), page.replace("\0", "-")
    for reading, to_dropped in (
        (dropped, lambda i: i),
        (kept, lambda i: i - page.count("\0", 0, i)),
    ):
        found = [
            (to_dropped(start), to_dropped(start + len(needle)))
            for needle in sources.needles(quote)
            for start in _offsets(reading, needle)
        ]
        if found:
            return found
    return []


def check_coverage(p: Project) -> list[tuple[str, int, str]]:
    """The stated quantities in each source that no evidence or skip entry covers."""
    uncovered = []
    for sid, s in p.sources.items():
        if not _available(p, sid) or Path(s["path"]).suffix.lower() not in TEXT_FORMATS:
            continue
        if s.get("coverage") is False:
            p.warn(
                "coverage-off",
                f"source {sid}: coverage: false, so the sweep does not read it; "
                "any stated quantity in it may be unledgered",
            )
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
            for start, end, snippet in sources.stated_quantities(text):
                if not any(a <= start and end <= b for a, b in spans):
                    context = text[max(0, start - 60) : end + 40]
                    uncovered.append((sid, n, f"{snippet}  …{context}…"))
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
    for sid, n, line in uncovered:
        p.error("coverage", f"{sid} p{n}: unledgered stated quantity {line}")
    return uncovered


def _evaluate(expr: str, names: dict[str, float]) -> float:
    tree = ast.parse(expr, mode="eval")
    allowed = (
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
                    p.error(
                        "param-mismatch", f"param {name}: value {spec['value']} != {ref} = {value}"
                    )
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
            for name in pending:
                p.error("param-derived", f"param {name}: circular dependency")
            break


def check_refs(c: dict) -> list[str]:
    """The evidence values a check compares with the geometry."""
    eid = c.get("evidence")
    return [f"{eid}.{key}" for key in (c.get("axes") or {})] + (
        [f"{eid}.{c['key']}"] if c.get("key") else []
    )


def pose_refs(c: dict) -> list[str]:
    """The joint values check c's pose names: each a param or an <evidence>.<key> ledger value."""
    return [str(v) for v in (c.get("pose") or {}).values()]


def mass_params(p: Project, parts=None) -> list[str]:
    """The params the mass model weighs parts by: every part's, or only those of parts."""
    entries = [p.parts.get(n) or {} for n in parts] if parts is not None else p.parts.values()
    return [str(v) for entry in entries for v in entry.values()]


def params_read_by(p: Project, c: dict) -> list[str]:
    """The params check c reads itself, in order: the params its pose names, then a mass check's
    density, or without one the mass model's params for the parts it weighs, then its add and
    counts params."""
    names = pose_refs(c)
    if c.get("kind") == "mass":
        if c.get("density") is None:
            names += mass_params(p, c.get("parts"))
        names += [str(c.get("density"))] + [str(n) for n in c.get("add") or []]
        names += [str(n) for n in (c.get("counts") or {}).values()]
    return [n for n in dict.fromkeys(names) if n in p.params]


def check_params(p: Project) -> set[str]:
    """The params the checks read themselves."""
    return {name for c in p.checks for name in params_read_by(p, c)}


def rests_on(p: Project, c: dict) -> tuple[str, list[str]]:
    """What check c rests on: the weakest basis among the params it reads, or source when it reads
    none, with the params it reads that rest on that basis."""
    bases = {name: p.rests_on.get(name, "proposed") for name in params_read_by(p, c)}
    weakest = max(bases.values(), key=RESTS_ON.index, default="source")
    return weakest, [name for name, basis in bases.items() if basis == weakest]


def check_tolerance(p: Project, c: dict) -> tuple[str, float] | None:
    """The tolerance a check compares with, as (key, value): tol, in its quantity's project units
    (degrees for an angle), or tol_rel, a fraction; None for a kind that compares with no ledger
    value, or a mass check missing its tol_rel."""
    kind = CHECK_KINDS.get(str(c.get("kind")))
    if kind is None:
        return None
    if kind.tolerance is None:
        return ("tol_rel", float(c["tol_rel"])) if "tol_rel" in c else None
    return "tol", float(c.get("tol", p.tolerance(kind.tolerance)))


def default_tolerance(kind: str | None) -> tuple[str, float] | None:
    """cadrev's own tolerance for a check of kind, where project.yaml and the check set none;
    None for a kind with no default."""
    check = CHECK_KINDS.get(str(kind))
    if check is None or check.tolerance is None:
        return None
    return "tol", DEFAULT_TOL[check.tolerance]


def default_overlap_limit(length_tol: float = LENGTH_TOL) -> float:
    """The overlap limit of an interference check that sets no max_volume: tolerance.length³,
    cadrev's default where project.yaml sets no tolerance.length."""
    return length_tol**3


def overlap_limit(p: Project, c: dict) -> float:
    """The most overlap an interference check lets instances have: max_volume, else the default."""
    return float(c.get("max_volume", default_overlap_limit(p.length_tol)))


def check_tolerances(p: Project) -> None:
    """No check is loosened past the cap: tol to TOL_CAP of each value it compares, tol_rel to TOL_REL_CAP."""
    for c in p.checks:
        cid, tolerance = c.get("id", "?"), check_tolerance(p, c)
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
        for ref in check_refs(c):
            expected = p.compared_value(ref, str(c.get("kind")))
            if expected is not None and value > TOL_CAP * abs(expected) * (1 + 1e-9):
                p.error(
                    "tolerance-cap",
                    f"check {cid}: tol {value:g}{where} is above {TOL_CAP:.0%} "
                    f"of {ref}, {expected:g}",
                )
                break


def check_accounting(p: Project) -> None:
    """Every evidence value is used by a parameter, checked against geometry, or set aside."""
    used = {spec.get("from") for spec in p.params.values()}
    measured_from = {
        str(spec.get("from", "")).partition(".")[0]
        for spec in p.params.values()
        if spec.get("basis") == "measured"
    }
    checked = {ref for c in p.checks for ref in check_refs(c)}
    used |= checked | {ref for c in p.checks for ref in pose_refs(c)}
    for eid, e in p.evidence.items():
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
    read_by_a_check = check_params(p)
    for name, spec in p.params.items():
        if name in read_by_a_check or name in p.physics:
            continue  # its check compares the result with the ledger; no check sees physics
        if spec.get("basis") == "source" and spec.get("from") not in checked:
            p.warn(
                "unchecked-source",
                f"param {name}: {spec.get('from')} feeds the model but no "
                "check confirms the geometry realises it",
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
            if eid not in p.evidence:
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
            for ref in check_refs(c):
                expect_quantity(p, ref, (CHECK_KINDS[kind].quantity,), f"check {cid}")
        for ref in pose_refs(c):
            use = f"in check {cid}'s pose"
            if ref in p.params:
                expect_param_quantity(p, ref, ("angle",), use)
            else:
                expect_quantity(p, ref, ("angle",), use)
        if kind == "mass":
            expect_param_quantity(p, c.get("density") or "", ("density",), f"in check {cid}")
            for name in c.get("add", []):
                expect_param_quantity(p, name, ("mass",), f"in check {cid}")
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
    resolve_params(p)
    check_accounting(p)
    check_gaps(p)
    check_conflicts(p)
    check_units(p)
    check_tolerances(p)
    lint.lint_model(p)
