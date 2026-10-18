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

from . import schema, sources

BASES = ("source", "derived", "measured", "proposed")
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
    # Parameters resting on a proposed value, directly or through derived expressions.
    proposed: set[str] = field(default_factory=set)
    findings: list[Finding] = field(default_factory=list)

    def error(self, rule: str, message: str) -> None:
        self.findings.append(Finding("error", rule, message))

    def warn(self, rule: str, message: str) -> None:
        self.findings.append(Finding("warning", rule, message))

    @property
    def sources(self) -> dict[str, dict]:
        return {s["id"]: s for s in self.meta.get("sources", [])}

    def source_path(self, source_id: str) -> Path:
        return self.root / self.sources[source_id]["path"]

    @property
    def length_tol(self) -> float:
        return float(self.meta.get("tolerance", {}).get("length", 1e-3))

    def evidence_value(self, ref: str) -> float | None:
        item_id, _, key = ref.partition(".")
        item = self.evidence.get(item_id)
        if item is None or key not in item.get("values", {}):
            return None
        return float(item["values"][key])


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


def load(root: Path) -> Project:
    """The project at root. Never raises: missing or malformed files become findings."""
    root = root.resolve()
    findings: list[Finding] = []
    if not (root / "project.yaml").is_file():
        findings.append(Finding("error", "project-missing", f"{root / 'project.yaml'} not found; "
                                "point cadrev at a project directory (cadrev init creates one)"))
    files = {name: read_yaml(root, name, findings) for name in schema.FILES}
    evidence_list = files["evidence.yaml"].get("evidence", [])
    project = Project(
        root=root,
        meta=files["project.yaml"],
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
            if not e.get("confirmed_by"):
                p.warn("image-unconfirmed", f"{eid}: figure reading awaits human confirmation (confirmed_by)")
        else:
            p.error("evidence-anchor", f"{eid}: needs quote (text sources) or image + reading (figures, video)")
        if not e.get("locator"):
            p.error("evidence-locator", f"{eid}: locator is required (e.g. 'Table S2', 'Fig. 2A', 'Sec. 4.2')")


def check_coverage(p: Project) -> list[tuple[str, int, str]]:
    """Dimension-like text in each source that no evidence or skip entry covers."""
    uncovered = []
    for sid, s in p.sources.items():
        if not _available(p, sid) or Path(s["path"]).suffix.lower() not in TEXT_FORMATS:
            continue
        if s.get("coverage") is False:
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
            for start, end, snippet in sources.dimension_candidates(text):
                if not any(a <= start and end <= b for a, b in spans):
                    context = text[max(0, start - 60):end + 40]
                    uncovered.append((sid, n, f"{snippet}  …{context}…"))
    for sid, n, line in uncovered:
        p.error("coverage", f"{sid} p{n}: unledgered dimension {line}")
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
            pending.pop(name)
        elif basis == "measured":
            item = p.evidence.get(str(spec.get("from", "")).partition(".")[0])
            if item is None or "image" not in item:
                p.error("param-from", f"param {name}: measured needs from: an image evidence id")
            for key in ("value", "method", "uncertainty"):
                if key not in spec:
                    p.error("param-measured", f"param {name}: measured needs {key}")
            p.values[name] = float(spec.get("value", math.nan))
            pending.pop(name)
        elif basis == "proposed":
            if "value" not in spec or not spec.get("rationale"):
                p.error("param-proposed", f"param {name}: proposed needs value and rationale")
            if not spec.get("gap"):
                p.warn("param-gap", f"param {name}: proposed value names no gap to close it")
            elif spec["gap"] not in p.gaps:
                p.error("param-gap", f"param {name}: unknown gap {spec['gap']!r}")
            p.values[name] = float(spec.get("value", math.nan))
            p.proposed.add(name)
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
                if needs & p.proposed:
                    p.proposed.add(name)
                pending.pop(name)
                progressed = True
        if pending and not progressed:
            for name in pending:
                p.error("param-derived", f"param {name}: circular dependency")
            break


def check_accounting(p: Project) -> None:
    """Every evidence value is used by a parameter, checked against geometry, or set aside."""
    used = {spec.get("from") for spec in p.params.values()}
    measured_from = {str(spec.get("from", "")).partition(".")[0]
                     for spec in p.params.values() if spec.get("basis") == "measured"}
    for c in p.checks:
        eid = c.get("evidence")
        if c.get("key"):
            used.add(f"{eid}.{c['key']}")
        for key in (c.get("axes") or {}):
            used.add(f"{eid}.{key}")
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
    checked = {f"{c.get('evidence')}.{k}" for c in p.checks for k in (c.get("axes") or {})}
    checked |= {f"{c.get('evidence')}.{c['key']}" for c in p.checks if c.get("key")}
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
    lint_model(p)
