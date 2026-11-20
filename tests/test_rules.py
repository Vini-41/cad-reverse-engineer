"""Every rule cadrev can file, tripped by the smallest change to a verified project that raises
it, and the damage no verification run may die of.

A FINDINGS key is `rule` or `rule: what the change is`; `test_every_rule_the_source_can_file_is_
tripped` holds the tables to the rules the tool's source names.
"""

import ast
import re

import pytest
from build123d import Box
from conftest import (
    ASSEMBLY,
    CORD,
    FOLD,
    INPUT_RANGE,
    KNEE,
    LOOP,
    M3_SCREW,
    PAPER,
    PROBE,
    SCREW,
    SHEET,
    SHEET_PROBE,
    SLIDE,
    SKILL,
    TEN_LONG,
    WOUND,
    add,
    add_line,
    add_quote,
    add_reading,
    add_source,
    cadrev,
    change,
    check,
    edit,
    meta,
    open_chain,
    pdf,
    place,
    probed,
    released,
    remodel,
    sheet,
    stack,
    threaded,
    write,
)

# The rules filed as warnings, which leave a project VERIFIED; a case of another rule that is one
# says so in its key.
WARNINGS = {
    "cable-on-axis",
    "conflict-open",
    "coverage-off",
    "gap-unused",
    "param-unused",
    "quote-page",
    "unchecked-source",
}
# A rule whose name the source builds: each name it can build.
TEMPLATED = {"value-not-in-{}": {"value-not-in-quote", "value-not-in-reading"}}
# Hyphenated words in the source that name no rule.
NOT_RULES = {"not-modeled"}


def _checks(cid, **fields):
    return lambda r, t: change(r, "checks", cid, **fields)


def _check(text: str):
    return lambda r, t: add(r, checks=text)


def _param(name, **fields):
    return lambda r, t: change(r, "params", name, **fields)


def _params(text: str):
    return lambda r, t: add(r, params=text)


def _evidence(eid, **fields):
    return lambda r, t: change(r, "evidence", eid, **fields)


def _ledger(entry):
    return lambda r, t: add(r, evidence=entry)


def _skip(text: str):
    """Replace the link project's one skip."""
    return lambda r, t: (edit(r, "evidence.yaml", lambda d: d.pop("skipped")), add(r, skipped=text))


def _meta(**keys):
    return lambda r, t: meta(r, **keys)


def _model(old: str, new: str):
    return lambda r, t: remodel(r, old, new)


def _line(line: str):
    return lambda r, t: add_line(r, line)


def _quoted(text: str, **values):
    return lambda r, t: add_quote(r, t, text, values=values)


def _reading(**fields):
    return lambda r, t: add_reading(r, **fields)


def _paged(**entry):
    """The paper again as a two-page PDF, source doc, and the pitch quoted from it as N1."""
    pages = [PAPER.split("The pivot")[0], "The pivot" + PAPER.split("The pivot")[1]]
    item = {"id": "N1", "source": "doc", "locator": "Sec. 2", "quote": "spaced 30 mm apart"}
    item |= {"scope": "context", "reason": "restates pitch"} | entry
    return lambda r, t: (add_source(r, t, "paper.pdf", pdf(pages)), add(r, evidence=item))


def _measured(**fields):
    spec = {"basis": "measured", "from": "F2", "value": 5.5, "method": "pitch as scale"}
    spec |= {"uncertainty": "±0.3 mm"} | fields
    spec = {k: v for k, v in spec.items() if v is not None}
    return lambda r, t: (add_reading(r, confirmed_by="A. Reviewer"), add(r, params={"foot": spec}))


def _released(*then, **kwargs):
    """The link released as a STEP and shape-checked, then each change in then."""
    return lambda r, t: (released(r, t, **kwargs), [step(r, t) for step in then])


def _probed(**entry):
    return lambda r, t: probed(r, t, **entry)


# A ring, its 30 mm hole about (20, 20), and an island cut inside the hole; and a circle datum
# through three points of the ring's hole, whose centre lies on the island.
ISLAND = """\
<svg xmlns="http://www.w3.org/2000/svg" width="100mm" height="100mm" viewBox="0 0 100 100">
  <path fill="black" fill-rule="evenodd" d="M 0 0 H 40 V 40 H 0 Z
    M 5 20 a 15 15 0 1 0 30 0 a 15 15 0 1 0 -30 0 Z"/>
  <path fill="black" d="M 15 15 h 10 v 10 h -10 Z"/>
</svg>
"""
RING_BORE = {
    "ring.r1": [5, 20],
    "ring.r2": [20, 5],
    "ring.r3": [35, 20],
    "ring.bore": {"circle": ["ring.r1", "ring.r2", "ring.r3"]},
}


def _sheet(*then, **kwargs):
    return lambda r, t: (sheet(r, t, **kwargs), [step(r, t) for step in then])


def _quoted_check(text: str, check: str, **values):
    """A notes source stating values, and a check that compares with them."""
    return lambda r, t: (add_quote(r, t, text, values=values), add(r, checks=check))


def _expecting(expr):
    """The pitch check compared with what expect expr works out, in place of a ledger value."""
    return _checks("pitch", evidence=None, key=None, expect=expr)


def _weighed(text: str, check: str, **values):
    """A mass check of the link, 1.78 g in resin of 1.2 g/cm3, against a notes source."""
    params = "rho: {basis: source, from: N1.rho}"
    return lambda r, t: (
        add_quote(r, t, text, values=values),
        add(r, params=params, checks=f"{{id: m, kind: mass, evidence: N1, {check}}}"),
    )


THREAD = "screw: {basis: proposed, thread: %s, rationale: a screw for a pin, gap: G1}"


def _threaded(designation: str, at: str):
    """A thread param, and the link's datum `at` declared for it."""
    return lambda r, t: (
        add(r, params=THREAD % designation),
        remodel(r, ASSEMBLY, ASSEMBLY + f'"threads": {{"{at}": "screw"}},'),
    )


def _screwed(length: str):
    """The link's holes threaded for an M3 screw, whose length is the param given as YAML."""
    return lambda r, t: (threaded(r, spec=M3_SCREW), add(r, params=length))


def _planned(**plan):
    """A plan of the link: made flat and placed by one step, with plan's changes to its make,
    buy and steps, each YAML text, or None for none."""
    plan = {"make": "link: print it flat", "steps": "[{place: [link_1]}]"} | plan
    return lambda r, t: add(r, **{key: text for key, text in plan.items() if text is not None})


RESIN = "The link weighs 1.8 g in resin of 1.2 g/cm3."
EXTRA = "{id: extra, source: paper, locator: Sec. 3, quote: branches of 60 mm diameter"
ANGLE = "{id: n, kind: angle, between: [link.b, link.a, link.top], evidence: N1, key: v"
SQUARE = ["link_step.b", "link_step.a", "link_step.top"]  # top lies above a, along z

LINK_FINDINGS = {
    # The project and its files.
    "project-missing": lambda r, t: (r / "project.yaml").unlink(),
    "format-missing": _meta(format=None),
    "format-unknown": _meta(format=2),
    "format-unknown: text": _meta(format="1"),
    "yaml-syntax": lambda r, t: write(r, "params.yaml", "params:\n  a: [unclosed\n"),
    "yaml-syntax: not UTF-8": lambda r, t: (r / "gaps.yaml").write_bytes(b"\xff\xfe"),
    "schema: an entry without its id": lambda r, t: change(r, "checks", "pitch", id=None),
    "schema: a param that is a bare number": _params("spare: 3"),
    "schema: a value split at an unquoted comma": lambda r, t: write(
        r, "gaps.yaml", "gaps:\n  - {id: G1, question: which pin, and why}\n"
    ),
    "schema: a value that is no number": _evidence("pitch", values={"pitch": "about thirty"}),
    "schema: part and instances together": _checks("env", instances=["link_1"]),
    "schema: a count that is a bare number": _weighed(RESIN, "counts: {link: 1}", rho=1.2),
    "schema: a mass model entry with both": lambda r, t: add(
        r, parts="link: {mass: pitch, density: pitch}"
    ),
    "schema: a source with a license": lambda r, t: change(r, "sources", "paper", license="MIT"),
    "schema: a file that is a list": lambda r, t: write(r, "params.yaml", "- a\n- b\n"),
    "schema: a file's key that is none": lambda r, t: edit(
        r, "params.yaml", lambda d: d.update(parmas=d.pop("params"))
    ),
    "schema: a released datum of two numbers": _released(
        lambda r, t: add(r, datums="link_step.a: [1, 2]")
    ),
    "schema: an up axis that is none": _meta(up="x"),
    "target": _meta(target="TODO name the object"),
    "target: none": _meta(target=None),
    "units: a unit cadrev does not know": _meta(units={"length": "furlong"}),
    "units: a unit of another quantity": _meta(units={"length": "g"}),
    "units: a quantity that follows from the five": _meta(units={"torque": "N·m"}),
    # Sources.
    "source-kind": lambda r, t: change(r, "sources", "paper", kind="book"),
    "source-citation": lambda r, t: change(r, "sources", "paper", citation=""),
    "source-id": lambda r, t: add(
        r, sources={"id": "paper", "kind": "paper", "path": "x.txt", "sha256": "0", "citation": "c"}
    ),
    "source-missing": lambda r, t: (r / "sources" / "paper.txt").unlink(),
    "source-hash": lambda r, t: (r / "sources" / "paper.txt").write_text(PAPER + "Errata.\n"),
    "source-unreadable: a PDF that is none": lambda r, t: add_source(r, t, "x.pdf", b"%PDF-1.4 no"),
    "source-unreadable: a STEP that is none": lambda r, t: add_source(
        r, t, "x.step", "30 mm\n", "g", "geometry"
    ),
    "source-unreadable: an STL that does not close": _released(
        solid=Box(4, 4, 4).faces()[0], name="open.stl", check=False
    ),
    "source-unreadable: an SVG with no closed contour": lambda r, t: add_source(
        r,
        t,
        "x.svg",
        '<svg xmlns="http://www.w3.org/2000/svg"><path d="M 0 0 h 9"/></svg>',
        "g",
        "geometry",
    ),
    "source-unreadable: geometry in a format that is none": lambda r, t: add_source(
        r, t, "x.obj", "v 0 0 0\n", "g", "geometry"
    ),
    # The ledger.
    "evidence-id": _ledger(EXTRA.replace("extra", "pitch") + ", scope: context, reason: r}"),
    "evidence-source": _evidence("pitch", source="nowhere"),
    "evidence-locator": _evidence("pitch", locator=None),
    "evidence-anchor: no quote, image or probe": _evidence("pitch", quote=None),
    "evidence-anchor: a quote from a file that is no text": _released(
        _ledger("{id: q, source: link_step, locator: l, quote: x, scope: context, reason: r}")
    ),
    "evidence-values": _ledger(EXTRA + "}"),
    "evidence-values: a probe": _probed(values=None),
    "evidence-scope": _ledger(EXTRA + ", scope: not-modeled}"),
    "evidence-unused": _ledger(EXTRA + ", values: {d: 60}}"),
    "quote-not-found": _evidence("pitch", quote="spaced 31 mm apart"),
    "quote-not-found: inside a larger number": _evidence("pitch", quote="0 mm apart"),
    "quote-not-found: on another page": _paged(page=1),
    "quote-page": _paged(),
    "value-not-in-quote": _evidence("pitch", values={"pitch": 3}),
    "value-not-in-reading": _reading(values={"w": 71}),
    "number-ambiguous": _quoted("a 1,250 mm rail", v=1250),
    "unit-ambiguous": _quoted("4 mm pins in 4 cm links", v=4),
    "unit-ambiguous: once with a unit and once without": _quoted("4 mm pins in 4 links", v=4),
    "image-missing": lambda r, t: (add_reading(r), (r / "figures/crops/fig2.png").unlink()),
    "image-hash": _reading(image_sha256="0" * 64),
    "image-reading": _reading(reading=""),
    # Threads.
    "param-thread: a pitch its size does not take": _params(THREAD % "M3x0.6"),
    "param-thread: a size in neither table": _params(THREAD % "M9"),
    "param-thread: threads per inch its size does not take": _params(THREAD % "1/4-24"),
    "param-thread: one that is derived": _params(
        "screw: {basis: derived, thread: M3, expr: hole_d}"
    ),
    "param-thread: from that states nothing": _params(
        "screw: {basis: source, thread: M3, from: nowhere}"
    ),
    "param-thread: one its statement does not print": lambda r, t: (
        add_quote(r, t, "Each pin is an M4 screw."),
        add(r, params="screw: {basis: source, thread: M3, from: N1}"),
    ),
    "param-thread: a size its statement prints lower case": lambda r, t: (
        add_quote(r, t, "A gear of module m3."),
        add(r, params="screw: {basis: source, thread: M3, from: N1}"),
    ),
    "param-mismatch: a thread's value that is not its major diameter": _params(
        "screw: {basis: proposed, thread: M3, value: 2.5, rationale: r, gap: G1}"
    ),
    "param-proposed: a thread with no rationale": _params(
        "screw: {basis: proposed, thread: M3, gap: G1}"
    ),
    "thread-standard": _params(THREAD % "4-40"),
    "model-thread: a hole of neither its thread nor its clearance": _threaded("M5", "link.a"),
    "model-thread: a datum on no cylinder": _threaded("M3", "link.side"),
    "model-thread: a hole declared twice": lambda r, t: (
        add(r, params=THREAD % "M3"),
        remodel(r, ASSEMBLY, ASSEMBLY + '"threads": {"link.a": "screw", "link.top": "screw"},'),
    ),
    "model-thread: a hole of no thread whose table gives no clearance": _threaded("M2.2", "link.a"),
    "model-build: the clearance hole of a size its table gives none": lambda r, t: (
        add(r, params=THREAD % "M2.2"),
        add_line(r, "spare = p.screw.clearance"),
    ),
    "model-thread: a datum that is none": _threaded("M3", "link.nowhere"),
    "model-thread: a param that is no thread": lambda r, t: remodel(
        r, ASSEMBLY, ASSEMBLY + '"threads": {"link.a": "hole_d"},'
    ),
    "model-return: a thread that names no param": lambda r, t: remodel(
        r, ASSEMBLY, ASSEMBLY + '"threads": {"link.a": 3},'
    ),
    "check-config: a count of a thread that is none": _quoted_check(
        "Two screws hold it.", "{id: n, kind: count, thread: hole_d, evidence: N1, key: v}", v=2
    ),
    # Screws: a thread and a length.
    "screw-length: a proposed length off the standard lengths": _screwed(
        TEN_LONG.replace("10", "11.27")
    ),
    "screw-length: a length fitted to the model": _screwed(
        "screw_len: {basis: derived, expr: link_H + 2}"
    ),
    "screw-length: a length that names no param": _screwed("spare: " + TEN_LONG.partition(" ")[2]),
    "screw-length: a length that names a thread": lambda r, t: threaded(
        r, spec=M3_SCREW.replace("screw_len", "screw")
    ),
    "screw-length: a length on a param that is no thread": _param("hole_d", length="pitch"),
    "unit-quantity: a mass as a screw's length": lambda r, t: (
        add_quote(r, t, "Each screw weighs 10 g.", values={"m": 10}),
        _screwed("screw_len: {basis: source, from: N1.m}")(r, t),
    ),
    # The plan.
    "plan-part: a placed part neither made nor bought": _planned(make=None),
    "plan-part: a making of a part that is none": _planned(make="pin: turn it"),
    "plan-part: a part both made and bought": _planned(buy="link: a link"),
    "plan-part: a making that says nothing": _planned(make="link: ['', drill]"),
    "plan-part: a purchase that says nothing": _planned(buy="glue: ' '"),
    "plan-step: an instance no step places": lambda r, t: (stack(r, 2), _planned()(r, t)),
    "plan-step: several instances and no steps": lambda r, t: (
        stack(r, 2),
        _planned(steps=None)(r, t),
    ),
    "plan-step: an instance placed twice": _planned(steps="[{place: [link_1, link_1]}]"),
    "plan-step: an instance that is none": _planned(steps="[{place: [link_1, pin_1]}]"),
    "plan-step: a step that says nothing": _planned(steps="[{place: [link_1]}, {}]"),
    "held: an instance of a plan apart from the rest": lambda r, t: (
        place(r, link_1="Location()", link_2="Location((0, 0, p.link_H + p.hole_d))"),
        _planned(steps="[{place: [link_1, link_2]}]")(r, t),
    ),
    "held: warning, an instance apart from the rest with no plan": lambda r, t: place(
        r, link_1="Location()", link_2="Location((0, 0, p.link_H + p.hole_d))"
    ),
    "held: a clearance that names no param": _meta(clearance="fit"),
    "held: a clearance below nothing": lambda r, t: (
        add(r, params="fit: {basis: derived, expr: -hole_d}"),
        meta(r, clearance="fit"),
    ),
    "param-physics: a physics value as the clearance": lambda r, t: (
        change(r, "params", "hole_d", physics=True),
        meta(r, clearance="hole_d"),
    ),
    "unit-quantity: a mass as the clearance": lambda r, t: (
        add_quote(r, t, "Each screw weighs 10 g.", values={"m": 10}),
        add(r, params="fit: {basis: source, from: N1.m}"),
        meta(r, clearance="fit"),
    ),
    "plan-screw: a with that names no thread param": _planned(
        steps="[{place: [link_1], with: {hole_d: 2}}]"
    ),
    "plan-screw: a step that drives none": lambda r, t: (
        _screwed(TEN_LONG)(r, t),
        _planned(steps="[{place: [link_1], with: {screw: 0}}]")(r, t),
    ),
    "plan-screw: warning, holes threaded for a screw and left without one": lambda r, t: (
        _screwed(TEN_LONG)(r, t),
        _planned()(r, t),
    ),
    "schema: a step that places text": _planned(steps="[{place: link_1}]"),
    "schema: a step with a key that is none": _planned(steps="[{place: [link_1], tool: key}]"),
    "schema: follows that is neither": _meta(follows="form"),
    "schema: a count of a part and a thread": _quoted_check(
        "Two screws hold it.",
        "{id: n, kind: count, part: link, thread: hole_d, evidence: N1, key: v}",
        v=2,
    ),
    # What each use expects a value to be printed as.
    "unit-quantity: a mass where the model reads a length": lambda r, t: (
        add_quote(r, t, "The link reads 40 g on the gauge.", values={"v": 40}),
        change(r, "params", "link_L", **{"from": "N1.v"}),
    ),
    "unit-quantity: a length where a check compares an angle": lambda r, t: (
        add_quote(r, t, "The holes stand 90 mm square.", values={"v": 90}),
        add(r, checks=ANGLE + "}"),
    ),
    "unit-quantity: a mass where a check weighs by a density": _weighed(
        "The link weighs 1.8 g in resin of 1.2 g.",
        "key: m, density: rho, tol_rel: 0.1",
        m=1.8,
        rho=1.2,
    ),
    "unit-quantity: a count that is no whole number": lambda r, t: (
        add_quote(r, t, "The hand has 1.5 links.", values={"n": 1.5}),
        add(r, checks="{id: n, kind: count, part: link, evidence: N1, key: n}"),
    ),
    "unit-quantity: a length in the mass model": lambda r, t: add(
        r, parts="link: {density: pitch}"
    ),
    # Coverage and skips.
    "coverage": _skip("[]"),
    "coverage: a quote that covers half the quantity": _skip(
        "{source: paper, quote: branches of 60, reason: test}"
    ),
    "coverage: a released body nothing compares": _released(check=False),
    "coverage: a region of a cut file": _sheet(check=False),
    "coverage-off": lambda r, t: change(r, "sources", "paper", coverage=False),
    "skip-reason": _skip("{source: paper, quote: branches of 60 mm diameter}"),
    "skip-anchor": _skip("{source: paper, reason: test condition}"),
    "skip-anchor: from without to": _skip("{source: paper, from: Tests, reason: test}"),
    "skip-anchor: a released body unnamed": _released(
        lambda r, t: add(r, skipped="{source: link_step, reason: a jig}")
    ),
    "skip-anchor: a cut file's region unnamed": _sheet(
        lambda r, t: add(r, skipped="{source: sheet, reason: a jig}")
    ),
    "skip-not-found": _skip("{source: paper, quote: branches of 70 mm diameter, reason: test}"),
    "skip-not-found: from and to in the wrong order": _skip(
        "{source: paper, from: diameter., to: Tests used, reason: test}"
    ),
    "skip-not-found: a body the file lacks": _released(
        lambda r, t: add(r, skipped='{source: link_step, body: "link_step#2", reason: a jig}')
    ),
    "skip-not-found: a point inside no region": _sheet(
        lambda r, t: add(r, skipped='{source: sheet, body: "sheet@100,50", reason: a jig}')
    ),
    "skip-not-found: a point on the edge two regions share": _sheet(
        lambda r, t: add(r, skipped='{source: sheet, body: "sheet@130,50", reason: a jig}'),
        svg=SHEET.replace("h 10 v 10 h -10 Z", 'h 5 v 10 h -5 Z"/><path d="M 55 0 h 5 v 10 h -5 Z'),
        check=False,
    ),
    "skip-not-found: a rectangle holding no whole region": _sheet(
        lambda r, t: add(r, skipped="{source: sheet, within: [[0, 0], [30, 300]], reason: none}")
    ),
    "conflict-ref": lambda r, t: add(r, conflicts="{id: K1, evidence: [T2-link], summary: s}"),
    "conflict-open": lambda r, t: add(
        r, conflicts="{id: K1, evidence: [T1-link, pitch], summary: the pitch exceeds the link}"
    ),
    # Params and gaps.
    "param-basis": _param("hole_d", basis="assumed"),
    "param-from": _param("link_W", **{"from": "T1-link.D"}),
    "param-from: measured off no image": _measured(**{"from": "pitch"}),
    "param-mismatch: a source value": _param("pitch", value=31),
    "param-mismatch: a derived value": _params(
        "half: {basis: derived, expr: pitch / 2, value: 14}"
    ),
    "param-measured": _measured(uncertainty=None),
    "param-proposed": _param("hole_d", rationale=None),
    "param-gap: a gap gaps.yaml lacks": lambda r, t: write(r, "gaps.yaml", "gaps: []\n"),
    "param-gap: a gap on a source param": _param("pitch", gap="G1"),
    "param-gap: warning, a proposed param naming none": _param("hole_d", gap=None),
    "param-derived: no expr": _params("half: {basis: derived}"),
    "param-derived: an expr that does not parse": _params("half: {basis: derived, expr: pitch /}"),
    "param-derived: an undefined param": _params("half: {basis: derived, expr: pich / 2}"),
    "param-derived: an expr that is not arithmetic": _params(
        "half: {basis: derived, expr: 'pitch if pitch else 2'}"
    ),
    "param-derived: a division by zero": _params("half: {basis: derived, expr: pitch / 0}"),
    "param-derived: itself": _params("half: {basis: derived, expr: half + pitch}"),
    "param-derived: a param left without a value": _params(
        "{a: {basis: source, from: T1-link.D}, half: {basis: derived, expr: a / 2}}"
    ),
    "param-derived: a gap without an interpretation": _params(
        "half: {basis: derived, expr: pitch / 2, gap: G1}"
    ),
    "param-constant": _params("half: {basis: derived, expr: 2 * pi}"),
    "param-unused": _params("spare: {basis: proposed, value: 3, rationale: x, gap: G1}"),
    "gap-unused": lambda r, t: add(r, gaps="{id: G2, question: 'pin length?'}"),
    "known-first": _meta(known_first=True),
    "unchecked-source": lambda r, t: edit(r, "checks.yaml", lambda d: d["checks"].pop(1)),
    # model.py.
    "model-missing": lambda r, t: (r / "model.py").unlink(),
    "model-syntax": _model("def build(p):", "def build(p)"),
    "model-literal": _line("extra = 7.5"),
    "model-literal: arithmetic on literals alone": _line("extra = p.pitch * (2 * 2 - 0.5)"),
    "model-import": _model("from build123d", "import os\nfrom build123d"),
    "model-import: a relative import": _model("from build123d", "from . import x\nfrom build123d"),
    "model-import: a part loaded from a file": _line('link = import_step("link.step")'),
    "model-build: a param params.yaml lacks": _line("extra = p.pitch_2"),
    "model-build: an exception": _line("raise ValueError(p.pitch)"),
    "model-build: a param set in model.py": _line("p.pitch = p.link_L"),
    "model-build: a param left without a value": lambda r, t: (
        add(r, params="half: {basis: source, from: T1-link.D}"),
        add_line(r, "extra = p.half"),
    ),
    "model-build: no build function": _model("def build(p):", "def make(p):"),
    "model-return: not a mapping": _model("    return {", "    return []\n    _ = {"),
    "model-return: a part that is no shape": _model('{"link": link}', '{"link": p.pitch}'),
    "model-return: a part name no file could take": _model('{"link": link}', '{"a/b": link}'),
    "model-return: a datum that is no point": _model("(p.pitch / 2, 0, 0)", "(p.pitch / 2, 0)"),
    "model-return: an instance that is no pair": _model('("link", Location())', '"link"'),
    "model-return: joints that are no mapping": _model('"datums": datums', '"joints": [], **{}'),
    "part-invalid: a solid wrapped with no volume": _model(
        '{"link": link}', '{"link": Part(link.solids()[0].wrapped)}'
    ),
    "part-invalid: two solids": _model(
        '{"link": link}', '{"link": Compound([link, Pos(0, 0, 2 * p.link_H) * link])}'
    ),
    "assembly-part": lambda r, t: remodel(r, '("link", Location())', '("pin", Location())'),
    "datum-off-solid": _model("(-p.pitch / 2, 0, p.link_H / 2)", "(-p.pitch / 2, 0, p.link_H)"),
    "datum-off-solid: a released datum off its body": _released(
        lambda r, t: add(r, datums="link_step.far: [0, 0, 0]")
    ),
    "datum-off-solid: a released datum naming no body": lambda r, t: add(
        r, datums="nowhere.a: [0, 0, 0]"
    ),
    "datum-off-solid: a probe's sheet datum off its region's edge": _sheet(
        _ledger(SHEET_PROBE | {"between": ["sheet.a", "sheet.b"]})
    ),
    "datum-off-solid: a sheet datum a derived one names off every region's edge": _sheet(
        lambda r, t: add(
            r, datums={"sheet.x": [30, 42.5], "sheet.m": {"mid": ["sheet.x", "sheet.side"]}}
        )
    ),
    "datum-off-solid: a probe's derived sheet datum off its region's edge": lambda r, t: (
        add_source(r, t, "ring.svg", ISLAND, "ring", "geometry"),
        add(r, datums=RING_BORE),
        add(r, evidence=SHEET_PROBE | {"source": "ring", "body": "ring@20,20", "between": None}),
        change(r, "evidence", "P-s", probe="diameter", at="ring.bore"),
    ),
    "datum-off-solid: a cut file's datum outside every region": _sheet(
        lambda r, t: add(r, datums="sheet.far: [1, 1]")
    ),
    # Checks.
    "check-id": _check("{id: env, kind: interference}"),
    "check-kind": _checks("clear", kind="overlap"),
    "check-failed": _model("Box(p.link_L,", "Box(p.link_L + 1,"),
    "check-failed: a count one short": lambda r, t: (
        add_quote(r, t, "Two links make a finger.", values={"n": 2}),
        add(r, checks="{id: n, kind: count, part: link, evidence: N1, key: n}"),
    ),
    "check-failed: an overlap": lambda r, t: place(
        r, link_1="Location()", link_2="Location((0, 0, p.link_H / 2))"
    ),
    "check-config: an axis that is none": _checks("pitch", along="w"),
    "check-config: a part that is none": _checks("env", part="pin"),
    "check-config: a bbox axis that is none": _checks("env", axes={"L": "w"}),
    "check-config: a bbox with no axes": _checks("env", axes={}),
    "check-config: a ledger value that is none": _checks("pitch", key="nope"),
    "check-config: a datum that is none": _checks("pitch", between=["link.a", "link.z"]),
    "check-config: one datum where a distance needs two": _checks("pitch", between=["link.a"]),
    "check-config: no evidence and no expect": _checks("pitch", evidence=None, key=None),
    "check-config: an expect on an interference check": _checks("clear", expect="pitch.pitch"),
    "check-config: three datums where a distance needs two": _checks(
        "pitch", between=["link.a", "link.b", "link.top"]
    ),
    "check-config: datums of two parts without instances": lambda r, t: (
        remodel(r, '{"link": link}', '{"link": link, "pin": link}'),
        remodel(r, '"link.b": (p.pitch / 2, 0, 0)', '"pin.b": (p.pitch / 2, 0, 0)'),
        change(r, "checks", "pitch", between=["link.a", "pin.b"]),
    ),
    "check-config: an instance that is none": _checks(
        "pitch", instances=["link_2"], between=["link_2.a", "link_2.b"]
    ),
    "check-config: no instances": _checks("env", part=None, instances=[]),
    "check-config: a feature its instance's part lacks": _checks(
        "pitch", instances=["link_1"], between=["link_1.a", "link_1.z"]
    ),
    "check-config: a datum naming none of its instances": _checks(
        "pitch", instances=["link_1"], between=["link_1.a", "link.b"]
    ),
    "check-config: an angle whose datum is its vertex": _quoted_check(
        "The holes stand 90° square.", ANGLE.replace("link.b,", "link.a,") + "}", v=90
    ),
    "check-config: an angle whose datum projects onto its vertex": _quoted_check(
        "The holes stand 90° square.", ANGLE + ", along: z}", v=90
    ),
    "check-config: an angle along no axis": _quoted_check(
        "The holes stand 90° square.", ANGLE + ", along: w}", v=90
    ),
    "check-config: a diameter on no cylindrical face": _quoted_check(
        "The holes are 3 mm bores.",
        "{id: n, kind: diameter, at: link.side, evidence: N1, key: v}",
        v=3,
    ),
    "check-config: a diameter at no datum": _quoted_check(
        "The holes are 3 mm bores.",
        "{id: n, kind: diameter, at: link.z, evidence: N1, key: v}",
        v=3,
    ),
    "check-config: a count with a tolerance": _quoted_check(
        "One link makes a finger.",
        "{id: n, kind: count, part: link, evidence: N1, key: n, tol: 1}",
        n=1,
    ),
    "check-config: a count worked out to no whole number": _quoted_check(
        "Three links make a finger.", '{id: n, kind: count, part: link, expect: "N1.n / 2"}', n=3
    ),
    "check-config: a count of a part that is none": _quoted_check(
        "One link makes a finger.", "{id: n, kind: count, part: pin, evidence: N1, key: n}", n=1
    ),
    "check-config: a mass without tol_rel": _weighed(RESIN, "key: m, density: rho", m=1.8, rho=1.2),
    "check-config: a mass of an instance that is none": _weighed(
        RESIN, "key: m, density: rho, tol_rel: 0.1, instances: [link_2]", m=1.8, rho=1.2
    ),
    "check-config: a mass of a part it weighs none of": _weighed(
        RESIN, "key: m, density: rho, tol_rel: 0.1, parts: [pin]", m=1.8, rho=1.2
    ),
    "check-config: a mass with no density and no mass model": _weighed(
        RESIN, "key: m, tol_rel: 0.1", m=1.8, rho=1.2
    ),
    "check-config: a mass whose count differs from the instances": lambda r, t: (
        _weighed(
            "Two links weigh 1.8 g in resin of 1.2 g/cm3.",
            "key: m, density: rho, tol_rel: 0.1, counts: {link: n}",
            m=1.8,
            rho=1.2,
            n=2,
        )(r, t),
        add(r, params="n: {basis: source, from: N1.n}"),
    ),
    "check-config: a pose on a model with no joints": _checks("pitch", pose={"input": "pitch"}),
    "check-config: a sweep on a model with no joints": _checks(
        "clear", sweep={"joint": "input", "steps": "pitch"}
    ),
    "check-config: a range on a model with no joints": _check(
        "{id: r, kind: range, joint: input, ends: [pitch.pitch]}"
    ),
    "check-config: a stroke of a cable that is none": _check(
        "{id: s, kind: stroke, cable: cord, evidence: pitch, key: pitch}"
    ),
    "check-config: a stroke with neither key nor claim": _check(
        "{id: s, kind: stroke, cable: cord, evidence: pitch}"
    ),
    "check-config: a claim on another kind": _checks("pitch", claim="shortens"),
    "check-config: from on a kind that takes none": _checks("env", **{"from": {}}),
    "check-config: expect beside evidence": _checks("pitch", expect="pitch.pitch"),
    "check-config: expect on a kind that takes none": _checks(
        "env", evidence=None, expect="T1-link.L"
    ),
    "check-config: an expect naming a param": _expecting("pitch * 1"),
    "check-config: an expect naming nothing known": _expecting("pitch.pitch * tau"),
    "check-config: an expect naming an entry the ledger lacks": _expecting("T9.pitch * 1"),
    "check-config: an expect naming a key its entry lacks": _expecting("pitch.d * 1"),
    "check-config: an expect that does not parse": _expecting("pitch.pitch *"),
    "check-config: an expect dividing by zero": _expecting("pitch.pitch / 0"),
    "check-config: a shape aligned by two pairs": _released(
        pairs=[["link.a", "link_step.a"], ["link.b", "link_step.b"]]
    ),
    "check-config: a shape aligned by datums on one line": _released(
        lambda r, t: add(r, datums="link_step.mid: [100, 50, 20]"),
        pairs=[
            ["link.a", "link_step.a"],
            ["link.b", "link_step.b"],
            ["link.side", "link_step.mid"],
        ],
    ),
    "check-config: a shape pair naming another part's datum": _released(
        pairs=[["pin.a", "link_step.a"]] * 3
    ),
    "check-config: a shape pair naming no released datum": _released(
        pairs=[["link.a", "link_step.z"]] * 3
    ),
    "check-config: a shape against a body that is none": _released(body="link_step#2"),
    "check-config: a shape against a solid, projected": _released(along="z"),
    "check-config: a shape against a region, not projected": _sheet(along=None),
    "check-config: a shape against a region, along no axis": _sheet(along="w"),
    "check-config: a shape against a point inside no region": _sheet(body="sheet@100,50"),
    "check-config: a shape against a cut file, no region named": _sheet(body="sheet"),
    "check-config: a shape of a part with no face square to the axis": _sheet(
        _model('{"link": link}', '{"link": Sphere(p.link_L)}')
    ),
    "tolerance-cap: tol above 5% of the value": _checks("pitch", tol=1.51),
    "tolerance-cap: tolerance.length above 5% of a value": _meta(tolerance={"length": 0.26}),
    "tolerance-cap: tol_rel above 0.25": _weighed(
        RESIN, "key: m, density: rho, tol_rel: 0.26", m=1.8, rho=1.2
    ),
    "tolerance-cap: tol above 5% of what an expect works out": lambda r, t: (
        _expecting("pitch.pitch * 1")(r, t),
        change(r, "checks", "pitch", tol=1.51),
    ),
    "tolerance-cap: a shape's tol above 1% of its body": _released(tol=0.5),
    "tolerance-cap: a probe's tol": _probed(tol=0.5),
    "probe-mismatch": _probed(values={"L": 40.002, "W": 5, "H": 8}),
    "evidence-anchor: a probe of a source that is no geometry": _probed(source="paper"),
    "evidence-anchor: a probe of a cut file naming no region": _sheet(
        _ledger(PROBE | {"source": "sheet", "axes": {"L": "x", "W": "y"}, "values": {"L": 40}})
    ),
    "evidence-anchor: a diameter probe of a region at no circle datum": _sheet(
        _ledger(SHEET_PROBE | {"probe": "diameter", "at": "sheet.side"})
    ),
    "evidence-anchor: a probe of a region at a datum outside it": _sheet(
        lambda r, t: add(r, datums={"sheet.plate": [130, 50]}),
        _ledger(SHEET_PROBE | {"between": ["sheet.bore_a", "sheet.plate"]}),
    ),
    "evidence-anchor: a probe of a body that is none": _probed(body="link_step#2"),
    "evidence-anchor: a probe of a kind that is none": _probed(probe="volume"),
    "evidence-anchor: a bbox probe along no axis": _probed(axes={"L": "w", "W": "x", "H": "z"}),
    "evidence-anchor: a distance probe of two values": _probed(
        probe="distance", between=["link_step.a", "link_step.b"]
    ),
    "evidence-anchor: a distance probe between an undeclared datum": _probed(
        probe="distance", between=["link_step.a", "link_step.z"], values={"v": 30}
    ),
    "evidence-anchor: an angle probe between two datums": _probed(
        probe="angle", between=["link_step.a", "link_step.b"], values={"v": 90}
    ),
    "evidence-anchor: an angle probe whose datum projects onto its vertex": _probed(
        probe="angle", between=SQUARE, values={"v": 90}, along="z"
    ),
    "evidence-anchor: an angle probe along no axis": _probed(
        probe="angle", between=SQUARE, values={"v": 90}, along="w"
    ),
    "evidence-anchor: a diameter probe at no datum": _probed(probe="diameter", values={"v": 3}),
    "evidence-anchor: a diameter probe on no cylindrical face": _probed(
        probe="diameter", at="link_step.a", values={"v": 3}
    ),
    "evidence-anchor: a diameter probe at a mid datum": lambda r, t: (
        probed(r, t, probe="diameter", at="link_step.m", values={"v": 3}),
        add(r, datums={"link_step.m": {"mid": ["link_step.a", "link_step.b"]}}),
    ),
}


def _chain(motion: str, *then, **params):
    """The slider-crank as an open chain moved by motion, then each change in then."""
    return lambda r, t: (open_chain(r, motion, **params), [step(r, t) for step in then])


def _wound(cable: str = WOUND, *then, turn="{basis: source, from: S2.turn}", **params):
    """The open chain with the crank's joint a wheel, its one-ended range the turn, winding a
    cable that pulls the slider 20 mm in."""
    pull = "{basis: proposed, value: -20, rationale: a full pull, gap: G1}"
    return lambda r, t: (
        remodel(r, INPUT_RANGE, '"range": ["turn"]'),
        open_chain(r, cable, **({"turn": turn, "pull": pull} | params)),
        [step(r, t) for step in then],
    )


PROPOSED = "{basis: proposed, value: %s, rationale: a choice, gap: G1}"
STAND = "{id: far, kind: angle, instances: [rail_1, crank_1], evidence: S2, key: stand, "
STAND += "between: [rail_1.top, rail_1.up, crank_1.down], pose: {input: %s}}"
INPUT = '"parent": "rail_1", "child": "crank_1"'
DRAW = "{id: draw, kind: stroke, cable: cord, evidence: S2, "


def _corded(claim: str, **fields):
    """The slider-crank with a cord from the crank pivot to the slider, and a stroke check of it
    posed at the stated turn."""
    return lambda r, t: (
        remodel(r, LOOP, LOOP + "\n        " + CORD),
        add(r, checks=DRAW + "pose: {input: S2.turn}, " + claim),
        change(r, "checks", "draw", **fields),
    )


MECH_FINDINGS = {
    "loop-open: as built": _model("Location((2 * bx, 0, p.H))", "Location((2 * bx + p.W, 0, p.H))"),
    "loop-open: at a pose": _check(
        "{id: far, kind: distance, instances: [rail_1, slider_1], evidence: S2, key: reach, "
        "between: [rail_1.a, slider_1.a], along: x, pose: {slide: S1.L}}"
    ),
    "joint-range": lambda r, t: add(
        r, params="beyond: {basis: derived, expr: input_max + 5}", checks=STAND % "beyond"
    ),
    "mjcf-load": lambda r, t: change(
        r, "params", "rho", basis="proposed", value=0, rationale="x", gap="G1", **{"from": None}
    ),
    "model-joint: a parent that is no instance": _model(INPUT, INPUT.replace("rail_1", "base_1")),
    "model-joint: an axis datum its child lacks": _model('"crank_1.up"]', '"rail_1.up"]'),
    "model-joint: axis datums that coincide": _model('"crank_1.up"]', '"crank_1.a"]'),
    "model-joint: a range param params.yaml lacks": _model(INPUT_RANGE, '"range": ["input_top"]'),
    "model-joint: a range whose low end exceeds its high": _model(
        INPUT_RANGE, '"range": ["input_max", "input_min"]'
    ),
    "model-joint: a child another joint moves": _model('"child": "slider_1"', '"child": "crank_1"'),
    "model-joint: a ring of joints": _model(INPUT, INPUT.replace("rail_1", "coupler_1")),
    "model-joint: a fixed joint with an axis": _model('"type": "slide"', '"type": "fixed"'),
    "model-joint: a spring rest with no stiffness": _model(KNEE, '"spring_rest": "rest", ' + KNEE),
    "model-loop": _model(LOOP, LOOP.replace("slider_1.up", "slider_1.nope")),
    "model-gear: a joint the model lacks": _chain(
        FOLD.replace("knee", "ankle"), fold=PROPOSED % -2
    ),
    "model-gear: one joint twice": _chain(FOLD.replace("knee", "input"), fold=PROPOSED % -2),
    "model-gear: a ratio across a hinge and a slide": _chain(
        FOLD.replace("knee", "slide"), fold=PROPOSED % -2
    ),
    "model-gear: a lead between two hinges": _chain(
        FOLD.replace('"ratio"', '"lead"'), fold=PROPOSED % -2
    ),
    "model-gear: a ratio params.yaml lacks": _chain(FOLD),
    "model-gear: a lead of 0": _chain(SCREW, lead=PROPOSED % 0),
    "model-cable: a path datum that is none": _wound(WOUND.replace("slider_1.down", "slider_1.z")),
    "model-cable: a wheel the model lacks": _wound(WOUND.replace('"input"', '"spool"')),
    "model-cable: a wheel with a two-ended range": _chain(WOUND, pull=PROPOSED % -20),
    "model-cable: a wheel whose turn is 0": _wound(turn=PROPOSED % 0),
    "model-cable: a path starting on the wheel": _wound(WOUND.replace("rail_1.up", "crank_1.up")),
    "model-cable: closing its own wheel": _wound(WOUND.replace('{"slide"', '{"input"')),
    "model-cable: closing a joint the model lacks": _wound(WOUND.replace('{"slide"', '{"ankle"')),
    "model-cable: closing a joint a gear couples": _wound(
        WOUND + "\n        " + SCREW, lead=PROPOSED % 8
    ),
    "model-cable: a closed param params.yaml lacks": _wound(WOUND.replace('"pull"', '"tug"')),
    "model-return: a joint type that is none": _model('"type": "slide"', '"type": "screw"'),
    "model-return: a drive that is none": _model('"drive": "actuated"', '"drive": "servo"'),
    "model-return: a joint key that is none": _model(KNEE, '"stiff": "rest", ' + KNEE),
    "model-return: a joint with no axis": _model('"axis": ["crank_1.a", "crank_1.up"], ', ""),
    "model-return: a range of three params": _model(
        INPUT_RANGE, '"range": ["input_min", "rest", "input_max"]'
    ),
    "model-return: a loop of one datum": _model(LOOP, LOOP.replace(', "slider_1.up"', "")),
    "model-return: a gear with both ratio and lead": _chain(
        FOLD.replace("}}", ', "lead": "fold"}}'), fold=PROPOSED % -2
    ),
    "model-return: a cable path of one datum": _wound(WOUND.replace('"rail_1.up", ', "")),
    "model-return: a wheel without closes": _wound(
        WOUND.replace(', "closes": {"slide": "pull"}', "")
    ),
    "model-return: a key build may not return": _model(LOOP, LOOP + '\n        "tendons": {},'),
    "model-return: a physics value params.yaml lacks": _model(KNEE, '"damping": "knee_c", ' + KNEE),
    "cable-on-axis": _wound(
        WOUND.replace("slider_1.down", "coupler_1.up").replace('{"slide"', '{"knee"')
    ),
    "param-physics: a joint's damping not marked so": _model(KNEE, '"damping": "W", ' + KNEE),
    "param-physics: a physics value the geometry reads": _param("W", physics=True),
    "part-mass: a placed part with no entry": lambda r, t: edit(
        r, "params.yaml", lambda d: d["parts"].pop("slider")
    ),
    "part-mass: an entry naming a param that is none": lambda r, t: add(
        r, parts="slider: {mass: slider_g}"
    ),
    "part-mass: an entry naming a part that is none": lambda r, t: add(
        r, parts="pin: {mass: slider_m}"
    ),
    "unit-quantity: a length posing a hinge": _checks("stand", pose={"input": "S1.L"}),
    "unit-quantity: a length as a hinge's range": _param("input_max", **{"from": "S1.L"}),
    "unit-quantity: an angle as a lead": _chain(SCREW, lead="{basis: source, from: S1.rest}"),
    "unit-quantity: a length as a range check's end": _checks("swing", ends=["S3.low", "S1.L"]),
    "check-config: a pose naming no joint": _checks("stand", pose={"wrist": "S2.turn"}),
    "check-config: a pose value that is none": _checks("stand", pose={"input": "S9.turn"}),
    "check-config: a pose naming a fixed joint": lambda r, t: (
        remodel(r, SLIDE, '"slide": {"type": "fixed", "parent": "rail_1", "child": "slider_1"},'),
        change(r, "checks", "stand", pose={"slide": "S2.turn"}),
    ),
    "check-config: a pose setting a gear out of ratio": _chain(
        FOLD,
        _checks("stand", pose={"input": "S2.turn", "knee": "S2.turn"}),
        fold=PROPOSED % -2,
    ),
    "check-config: a pose closing a cable's joint to 0": _wound(
        WOUND, _checks("stand", pose={"slide": "S1.L"}), pull=PROPOSED % 0
    ),
    "check-config: ends that are not one per range param": _checks("swing", ends=["S3.low"]),
    "check-config: a range of a joint with none": _checks("swing", joint="knee"),
    "check-config: a range of a joint that is none": _checks("swing", joint="wrist"),
    "check-config: a sweep of fewer than two poses": lambda r, t: add(
        r,
        params={"steps": {"basis": "proposed", "value": 1, "rationale": "coarse"}},
        checks="{id: clear, kind: interference, sweep: {joint: input, steps: steps}}",
    ),
    "check-config: a stroke with no wheel and no pose": lambda r, t: (
        remodel(r, LOOP, LOOP + "\n        " + CORD),
        add(r, checks=DRAW + "key: reach}"),
    ),
    "check-config: a claim that is neither": _corded("claim: tightens}"),
    "check-config: a claim beside a key": _corded("claim: shortens, key: reach}"),
    "check-config: a claim with a tolerance": _corded("claim: shortens, tol: 1}"),
    "check-config: a claim citing no evidence item": _corded("claim: shortens}", evidence="S9"),
    "tolerance-cap: a range's tol above 5% of its span": _checks("swing", tol=6.1),
}


def _files(case: str, table: dict, root, tmp_path) -> None:
    table[case](root, tmp_path)
    rule = case.partition(":")[0]
    level = "warning" if rule in WARNINGS or ": warning" in case else "error"
    run = check(root)
    assert (level, rule) in run.findings, run.out


@pytest.mark.parametrize("case", LINK_FINDINGS)
def test_change_to_the_link_files_its_rule(proj_dir, tmp_path, case):
    _files(case, LINK_FINDINGS, proj_dir, tmp_path)


@pytest.mark.parametrize("case", MECH_FINDINGS)
def test_change_to_the_mechanism_files_its_rule(mech_dir, tmp_path, case):
    _files(case, MECH_FINDINGS, mech_dir, tmp_path)


def source_rules() -> set[str]:
    """Every rule the tool's source can file: the rule each error, warn, filing, Fault and
    Finding call names, and every hyphenated name the source holds as text, since a rule may
    reach those calls through a variable."""
    found: set[str] = set()
    for path in (SKILL / "tool" / "src" / "cadrev").glob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf8"))):
            named: list[ast.expr] = []
            if isinstance(node, ast.Call):
                name = getattr(node.func, "attr", getattr(node.func, "id", ""))
                at = {"error": 0, "warn": 0, "filing": 0, "Fault": 1, "Finding": 1}.get(name)
                named += node.args[at : at + 1] if at is not None else []
                named += [k.value for k in node.keywords if k.arg == "rule"]
            elif isinstance(node, ast.Constant) and isinstance(node.value, str):
                named += [node] if re.fullmatch(r"[a-z]+(-[a-z]+)+", node.value) else []
            for text in named:
                if isinstance(text, ast.JoinedStr):
                    parts = (v.value if isinstance(v, ast.Constant) else "{}" for v in text.values)
                    found |= TEMPLATED["".join(map(str, parts))]
                elif isinstance(text, ast.Constant) and isinstance(text.value, str):
                    found.add(text.value)
    return found - NOT_RULES


def test_every_rule_the_source_can_file_is_tripped():
    tripped = {case.partition(":")[0] for case in [*LINK_FINDINGS, *MECH_FINDINGS]}
    rules = source_rules()
    assert len(rules) > 70 and rules - tripped == set()
    assert tripped - rules == set(), "a case names a rule the source does not file"


def _sourced(**entry):
    """A source project.yaml lists by hand, never registered."""
    listed = {"id": "x", "kind": "paper", "sha256": "0", "citation": "c"} | entry
    return lambda r, t: add(r, sources={k: v for k, v in listed.items() if v is not None})


def _file(name: str, content):
    return lambda r, t: (
        (r / name).write_bytes(content) if isinstance(content, bytes) else write(r, name, content)
    )


# Input that once crashed a verification run, or plausibly could: each must end on a status or a
# refusal like any other. Add a case for every new way project input or user code enters the run.
LINK_DAMAGE = {
    "expect is a list": _expecting(["pitch.pitch"]),
    "expect nested past the parser": _expecting("-" * 100_000 + "pitch.pitch"),
    "expect raising a power past any float": _expecting("9 ** 9 ** 9"),
    "expect calling a function wrongly": _expecting("sqrt(x=pitch.pitch)"),
    "expr nested past the parser": _params(f"deep: {{basis: derived, expr: {'(' * 300}pitch}}"),
    "expr overflowing": _params("big: {basis: derived, expr: pitch ** 1000}"),
    "param named by a number": _params("7: {basis: proposed, value: 3, rationale: x, gap: G1}"),
    "param value in words": _param("hole_d", value="three"),
    "thread that is a number": _params("screw: {basis: proposed, thread: 3, rationale: r}"),
    "thread that is a list": _params("screw: {basis: proposed, thread: [M3], rationale: r}"),
    "threads of the model is a list": _model(ASSEMBLY, ASSEMBLY + '"threads": ["link.a"],'),
    "screw length that is a number": _screwed("screw: {basis: proposed, thread: M3, length: 10}"),
    "screw length of infinity": _screwed(TEN_LONG.replace("10", ".inf")),
    "screw length with no value": _screwed("screw_len: {basis: proposed, rationale: r}"),
    "material is a list": _meta(material=["PLA"]),
    "follows is a mapping": _meta(follows={"design": True}),
    "plan of instances that are no solid": lambda r, t: (
        stack(r, 2),
        remodel(r, '{"link": link}', '{"link": link - link}'),
        edit(r, "checks.yaml", lambda d: d["checks"].pop()),  # its interference check
        _planned(steps="[{place: [link_1, link_2]}]")(r, t),
    ),
    "plan of a part too small to mesh": lambda r, t: (
        meta(r, tolerance={"length": 1e-7, "angle": 0.01}),
        add(r, params="speck: {basis: proposed, value: 0.00005, rationale: r, gap: G1}"),
        remodel(r, '{"link": link}', '{"link": link, "dot": Box(p.speck, p.speck, p.speck)}'),
        remodel(r, ASSEMBLY, ASSEMBLY.replace("},", ', "dot_1": ("dot", Location())},')),
        _planned(steps="[{place: [link_1, dot_1]}]", buy="dot: a speck")(r, t),
    ),
    "plan that is a list": _file("plan.yaml", "- make\n- buy\n"),
    "plan that is empty": _file("plan.yaml", ""),
    "plan make that is a list": _file("plan.yaml", "make: [link]\n"),
    "plan make of a number": _planned(make="link: 3"),
    "plan make of a list of numbers": _planned(make="link: [1, 2]"),
    "plan buy of a mapping": _planned(buy="link: {from: a shop}"),
    "plan steps that are a mapping": _file("plan.yaml", "steps: {place: [link_1]}\n"),
    "plan step with of text": _planned(steps="[{place: [link_1], with: {screw: two}}]"),
    "plan step with that is a list": _planned(steps="[{place: [link_1], with: [screw]}]"),
    "plan step placing a number": _planned(steps="[{place: [1]}]"),
    "plan of a model that does not build": lambda r, t: (
        _planned()(r, t),
        add_line(r, "raise ValueError(p.pitch)"),
    ),
    "plan is a directory": lambda r, t: (r / "plan.yaml").mkdir(),
    "name is a number": _meta(name=5),
    "format is a mapping": _meta(format={"v": 1}),
    "units is a number": _meta(units=5),
    "unit is a list": _meta(units={"length": ["mm"]}),
    "units keyed by a number": _meta(units={5: "mm"}),
    "unit is null": _meta(units={"length": None}),
    "tolerance of zero": _meta(tolerance={"length": 0}),
    "tolerance is text": _meta(tolerance="tight"),
    "known_first is text": _meta(known_first="x"),
    "sources is a mapping": _meta(sources={"paper": {"kind": "paper"}}),
    "source path is a directory": _sourced(path="sources"),
    "source path outside the project": _sourced(path="/etc/hosts"),
    "source without a path, with a datum": lambda r, t: (
        _sourced(kind="geometry")(r, t),
        add(r, datums="x.a: [1, 2, 3]"),
    ),
    "text source that is not UTF-8": lambda r, t: add_source(r, t, "b.txt", b"\xff\xfe 30 mm"),
    "geometry source of a truncated STL": lambda r, t: add_source(
        r, t, "g.stl", b"\0" * 80 + (1000).to_bytes(4, "little") + b"\1" * 25, "g", "geometry"
    ),
    "cut file of malformed XML": _sheet(svg="<svg><path d=", check=False),
    "cut file path of malformed data": _sheet(svg=SHEET.replace("M 50 0 h 10", "M 50 0 q !")),
    "cut file datum of text": _sheet(lambda r, t: add(r, datums="sheet.a: [x, y]")),
    "cut file skip within a list of numbers": _sheet(
        lambda r, t: add(r, skipped="{source: sheet, within: [1, 2], reason: r}")
    ),
    "cut file skip within corners of text": _sheet(
        lambda r, t: add(r, skipped="{source: sheet, within: [[a, b], [c, d]], reason: r}")
    ),
    "shape of a point on a released solid": _released(body="link_step@1,2"),
    "shape of a point with no number": _sheet(body="sheet@a,b"),
    "shape along a number": _sheet(along=3),
    "shape without pairs or body": _check("{id: s, kind: shape, part: link}"),
    "shape of a part that is none": _released(part="pin"),
    "shape pairs of one datum": _released(pairs=[["link.a"]] * 3),
    "shape against a source that is no geometry": _released(body="paper"),
    "probe of an unregistered source": _ledger(PROBE | {"source": "nowhere"}),
    "probe with a value in words": _probed(values={"L": "forty", "W": 5, "H": 8}),
    "probe between one datum": _probed(probe="angle", between=["link_step.a"], values={"v": 1}),
    "datums is a list": lambda r, t: edit(r, "evidence.yaml", lambda d: d.update(datums=[1, 2])),
    "reading is a number": _ledger(
        "{id: im, source: paper, locator: F, image: x.png, reading: 30, values: {v: 30}}"
    ),
    "image evidence is a directory": _ledger(
        "{id: im, source: paper, locator: F, image: sources, reading: '3'}"
    ),
    "evidence value keyed by a number": _evidence("pitch", values={"pitch": 30, 3: 30}),
    "evidence page that is none": _evidence("pitch", page=7),
    "skip of a page that is none": _skip("{source: paper, pages: [9], reason: r}"),
    "duplicate gap ids": _file("gaps.yaml", "gaps: [{id: G1}, {id: G1}]\n"),
    "unhashable YAML key": _file("params.yaml", "params:\n  ? [a, b]\n  : {basis: proposed}\n"),
    "undefined YAML alias": _file("gaps.yaml", "gaps: *nope\n"),
    "NUL byte in YAML": _file("gaps.yaml", b"gaps: []\x00\n"),
    "project file is a directory": lambda r, t: (
        (r / "evidence.yaml").unlink(),
        (r / "evidence.yaml").mkdir(),
    ),
    "empty project files": lambda r, t: [
        write(r, name, "") for name in ("evidence.yaml", "params.yaml", "checks.yaml", "gaps.yaml")
    ],
    "check tol in words": _checks("pitch", tol="wide"),
    "check claim is a list": _checks("pitch", claim=["shortens"]),
    "check from is a number": _checks("pitch", **{"from": 3}),
    "bbox without axes": _checks("env", axes=None),
    "bbox without evidence": _checks("env", evidence=None),
    "distance without between": _checks("pitch", between=None),
    "interference pairs of one instance": _checks("clear", pairs=[["link_1"]]),
    "interference pairs of an instance that is none": _checks("clear", pairs=[["link_1", "x"]]),
    "interference max_volume below zero": _checks("clear", max_volume=-1),
    "mass counts naming a param that is none": _weighed(
        RESIN, "key: m, density: rho, tol_rel: 0.1, counts: {link: nope}", m=1.8, rho=1.2
    ),
    "mass density naming a param that is none": _weighed(
        RESIN, "key: m, density: nope, tol_rel: 0.1", m=1.8, rho=1.2
    ),
    "datum of booleans": _model("(p.pitch / 2, 0, 0)", "(True, 0, 0)"),
    "part name is a number": _model('{"link": link}', '{"link": link, 3: link}'),
    "model.py exits": _line("raise SystemExit(p.pitch)"),
    "model.py recurses without end": _line("build(p)"),
    "model.py holds a NUL byte": _file("model.py", b"def build(p):\n    return {}\0\n"),
    "model.py is a directory": lambda r, t: ((r / "model.py").unlink(), (r / "model.py").mkdir()),
    "part its own boolean empties": _model('{"link": link}', '{"link": link - link}'),
    "expr that does not parse, read by the model": _param("hole_d", basis="derived", expr="3 +"),
    "param value of infinity": _param("hole_d", value=float("inf")),
    "ledger value that is not a number": _evidence("pitch", values={"pitch": float("nan")}),
    "datum named by a number": _model('"link.a":', '1: (0, 0, 0), "link.a":'),
    "derived datum on no body, its own input": lambda r, t: add(
        r, datums={"nowhere.c": {"circle": ["nowhere.c"] * 3}}
    ),
    "derived datum on a cut file": _sheet(lambda r, t: add(r, datums={"sheet.c": {"mid": []}})),
    "instance named by a number": _model('"link_1":', '1: ("link", Location()), "link_1":'),
}
MECH_DAMAGE = {
    "joint that is text": _model(SLIDE, '"slide": "rail_1",'),
    "joint range that is a number": _model(INPUT_RANGE, '"range": p.rest'),
    "joint range that is None": _model(INPUT_RANGE, '"range": None'),
    "joint axis that is None": _model('"axis": ["crank_1.a", "crank_1.up"]', '"axis": None'),
    "loop named by a number": _model('"loops": {"closure":', '"loops": {1:'),
    "cable path that is None": _wound(WOUND.replace('["rail_1.up", "slider_1.down"]', "None")),
    "cable closes that is None": _wound(WOUND.replace('{"slide": "pull"}', "None")),
    "joint axis of numbers": _model('"axis": ["crank_1.a", "crank_1.up"]', '"axis": [0, 1]'),
    "loops that are a list": _model(LOOP, '"loops": [["coupler_1.down", "slider_1.up"]],'),
    "gear ratio that is a number": _chain(FOLD.replace('"fold"}', "p.L}")),
    "cable path of numbers": _wound(WOUND.replace('["rail_1.up", "slider_1.down"]', "[1, 2]")),
    "cable closes that is a list": _wound(WOUND.replace('{"slide": "pull"}', '["slide"]')),
    "mass model that is a list": lambda r, t: edit(
        r, "params.yaml", lambda d: d.update(parts=["rail"])
    ),
    "mass model entry that is text": lambda r, t: add(r, parts="slider: slider_m"),
    "mass of zero": lambda r, t: add(
        r, params="slider_m: {basis: proposed, value: 0, rationale: x, gap: G1}"
    ),
    "pose that is a list": _checks("stand", pose=["input"]),
    "sweep without steps": _check("{id: c, kind: interference, sweep: {joint: input}}"),
    "sweep steps naming a param that is none": _check(
        "{id: c, kind: interference, sweep: {joint: input, steps: nope}}"
    ),
    "range without ends": _checks("swing", ends=None),
    "range between one datum": _checks("swing", instances=["rail_1"], between=["rail_1.a"]),
    "stroke without a cable": _check("{id: s, kind: stroke, evidence: S2, key: reach}"),
    "a pose at the toggle": lambda r, t: add(
        r,
        params="flat: {basis: derived, expr: -rest}",
        checks=STAND % "flat",
    ),
}


def _survives(root) -> None:
    """Whatever the project holds, every command that reads it ends by its own exit code."""
    check(root)  # asserts a status or a refusal, the exit code that goes with it, no traceback
    code, out = cadrev("text", root, "paper")
    assert code in (0, 1) and "Traceback" not in out, out


@pytest.mark.parametrize("damage", LINK_DAMAGE)
def test_no_damage_to_the_link_escapes_a_run(proj_dir, tmp_path, damage):
    LINK_DAMAGE[damage](proj_dir, tmp_path)
    _survives(proj_dir)


@pytest.mark.parametrize("damage", MECH_DAMAGE)
def test_no_damage_to_the_mechanism_escapes_a_run(mech_dir, tmp_path, damage):
    MECH_DAMAGE[damage](mech_dir, tmp_path)
    _survives(mech_dir)
