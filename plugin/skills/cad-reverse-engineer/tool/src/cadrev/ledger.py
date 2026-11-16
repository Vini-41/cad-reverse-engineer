"""The rules that need no built model: sources, the ledger and its coverage, and the params."""

from __future__ import annotations

import math
import re

from . import Fault, released, sources, threads, units
from .project import (
    AXES,
    BASES,
    PROBE_QUANTITY,
    RESTS_ON,
    SOURCE_KINDS,
    Project,
    compared_refs,
    evaluate,
    expr_names,
    pose_refs,
)

# The loosest a comparison may be: tol as a fraction of each value it compares, and tol_rel.
TOL_CAP, TOL_REL_CAP = 0.05, 0.25
# Why coverage lists a released body.
_UNCOVERED = "no shape check compares it and no skip sets it aside"
_SET_ASIDE = ("not-modeled", "context")


def above_cap(tol: float, value: float, cap: float = TOL_CAP) -> bool:
    """Whether tol is looser than the fraction cap of value, the most a comparison may stray by."""
    return tol > cap * abs(value) * (1 + 1e-9)


def check(p: Project) -> None:
    """Every rule here but the coverage sweep, in the order their findings read best."""
    target = str(p.meta.get("target") or "")
    if not target or target.startswith("TODO"):
        p.error("target", "project.yaml target: name the object, version and configuration")
    for q, spelled in (p.meta.get("units") or {}).items():
        unit, problem = units.declared(q, spelled)
        if unit is None:
            p.error("units", f"project.yaml units.{q}: {problem}")
    check_sources(p)
    _evidence(p)
    _released_datums(p)
    _params(p)
    _usage(p)
    for part, entry in p.parts.items():
        for by, name in entry.items():
            p.hold_param(name, (by,), f"in params.yaml parts.{part}")
    for o in p.overlays:
        if ref := (o.get("calibration") or {}).get("evidence"):
            p.hold(ref, ("length",), f"overlay {o.get('id', '?')} calibration")


def check_sources(p: Project) -> None:
    for sid, s in p.sources.items():
        if s.get("kind") not in SOURCE_KINDS:
            p.error("source-kind", f"source {sid}: kind must be one of {', '.join(SOURCE_KINDS)}")
        if not s.get("citation"):
            p.error("source-citation", f"source {sid}: citation is required")
        path = p.source_path(sid)
        if not path.is_file():
            url = f"; download from {s['url']}" if s.get("url") else ""
            p.error("source-missing", f"source {sid}: {s.get('path')} not found{url}")
            continue
        if s.get("sha256") != sources.sha256(path):
            p.error("source-hash", f"source {sid}: sha256 does not match {s.get('path')}")
        try:
            if s.get("kind") == "geometry":
                p.sheet(sid) if released.is_sheet(path) else p.solids(sid)
            elif p.is_text(sid):
                sources.pages(path)
        except Exception as exc:  # noqa: BLE001 - the PDF, STEP, STL and SVG readers raise many types
            what = "geometry" if s.get("kind") == "geometry" else "text"
            p.error(
                "source-unreadable",
                f"source {sid}: cannot read {what} from {s.get('path')}: "
                f"{type(exc).__name__}: {exc}",
            )
            p.unreadable.add(sid)


def _evidence(p: Project) -> None:
    """Each ledger item is anchored in its source and states the values it records."""
    # A statement of a direction needs no values where only claim checks cite it.
    keyed = {ref.partition(".")[0] for c in p.checks for ref in compared_refs(c)}
    directions = {str(c.get("evidence")) for c in p.checks if "claim" in c} - keyed
    # Nor does a statement of a thread, which a thread param reads by its designation.
    threaded = {str(spec.get("from")) for spec in p.params.values() if "thread" in spec}
    for e in p.evidence:
        eid, values = e["id"], e.get("values") or {}
        with p.filing("evidence-anchor", f"{eid}: "):
            if e.get("source") not in p.sources:
                raise Fault(f"unknown source {e.get('source')!r}", "evidence-source")
            needed = "probe" in e or (
                "quote" in e and e.get("scope") != "context" and eid not in directions | threaded
            )
            if needed and not values:
                p.error("evidence-values", f"{eid}: needs values (or scope: context)")
            if not e.get("locator"):
                p.error("evidence-locator", f"{eid}: locator is required (Table S2, Fig. 2A)")
            _anchor(p, e, values)
            for key, value in values.items():
                printed = p.printed_units(f"{eid}.{key}")
                if len(printed) > 1:
                    shown = " and ".join(
                        f"{value:g} {u}" if u else f"{value:g} with no unit" for u in printed
                    )
                    p.error(
                        "unit-ambiguous",
                        f"{eid}.{key} is printed as {shown}; quote only the part that states it",
                    )


def _anchor(p: Project, e: dict, values: dict) -> None:
    """Hold item e to its anchor: a quote found in its text source, a crop with its reading, or a
    probe of a geometry source."""
    eid, sid = e["id"], e["source"]
    if "quote" in e:
        if not p.available(sid):
            raise Fault()  # its source's own finding says why
        if not p.is_text(sid):
            raise Fault(f"{sid} is not a text source; anchor it by image + reading, or a probe")
        found = sources.find_quote(p.source_path(sid), e["quote"], e.get("page"))
        if found is None:
            where = f" on page {e['page']}" if e.get("page") else ""
            raise Fault(f"quote not found in {sid}{where}: {e['quote']!r}", "quote-not-found")
        if not e.get("page") and len(sources.pages(p.source_path(sid))) > 1:
            p.warn("quote-page", f"{eid}: add page: {found}")
        _stated(p, eid, e["quote"], "quote", values)
    elif "probe" in e:
        _probe(p, e)
    elif "image" in e:
        image = p.root / e["image"]
        if not image.is_file():
            p.error("image-missing", f"{eid}: crop {e['image']} not found")
        elif e.get("image_sha256") != sources.sha256(image):
            p.error("image-hash", f"{eid}: image_sha256 does not match {e['image']}")
        if not e.get("reading"):
            p.error("image-reading", f"{eid}: image evidence needs reading: the text as printed")
        else:
            _stated(p, eid, str(e["reading"]), "reading", values)
    else:
        raise Fault("needs a quote, an image + reading, or a probe")


def _stated(p: Project, eid: str, text: str, kind: str, values: dict) -> None:
    """Each value is a number its quote or reading states, and read one way only."""
    stated = sources.numbers_in(text)
    ambiguous = sources.ambiguous_numbers(text)
    for key, value in values.items():
        value = float(value)
        if a := next((a for a in ambiguous if a.reads(value)), None):
            p.error(
                "number-ambiguous",
                f"{eid}.{key} = {value:g} is read from {a.printed} in its {kind}, which is "
                f"{a.thousands:g} with a thousands comma or {a.decimal:g} with a decimal comma; "
                "take the value from where it is printed in another form",
            )
        elif not any(math.isclose(value, q, rel_tol=1e-9) for q in stated):
            p.error(f"value-not-in-{kind}", f"{eid}.{key} = {value:g} is not in its {kind}")


def _probe_values(p: Project, e: dict, body: str) -> dict[str, float]:
    """What a probe evaluates on its released body, a solid or a region of a cut file: each value
    key's value, in the project's units, an angle in degrees."""
    kind, values, shape = e["probe"], e.get("values") or {}, p.body(body)
    if kind == "bbox":
        axes, size = e.get("axes") or {}, shape.bounding_box().size
        for key in [*(axes.keys() - values.keys()), *values]:
            if axes.get(key) not in AXES or key not in values:
                raise Fault(f"axes gives each value its axis x, y or z, and {key} has none")
        return {key: tuple(size)[AXES[axes[key]]] for key in values}
    if kind not in PROBE_QUANTITY:
        raise Fault(f"probe must be bbox, distance, angle or diameter, not {kind!r}")
    if len(values) != 1:
        raise Fault(f"a {kind} probe records one value, not {len(values)}")
    (key,) = values
    if kind == "diameter":
        if "at" not in e:
            raise Fault("a diameter probe names the datum it is taken at in at")
        at, entry = str(e["at"]), p.datums.get(str(e["at"]))
        derived = isinstance(entry, dict)
        if released.at_point(body) and not (isinstance(entry, dict) and "circle" in entry):
            raise Fault(f"a diameter of a cut file's region is taken at a circle datum, not {at}")
        point = p.datum_on(at, body)
        if not derived:
            return {key: released.diameter_at(shape, point, p.length_tol, at)}
        diameter = p.derived_datum(at)[2]
        if diameter is None:
            raise Fault(f"{at} is a midpoint; take a diameter at a circle or on a cylindrical face")
        return {key: diameter}
    between = e.get("between") or []
    points = [p.datum_on(name, body) for name in between]
    if kind == "distance":
        return {key: released.datum_distance(points, e.get("along"))}
    return {key: released.angle_at(points, p.length_tol, between, e.get("along"))}


def _probe(p: Project, e: dict) -> None:
    """Evaluate probe e on its released body and compare each value it records with what the
    body gives: [probe-mismatch] beyond its tolerance, which is capped as a check's is."""
    eid, sid = e["id"], e["source"]
    if p.sources[sid].get("kind") != "geometry":
        raise Fault(f"a probe reads a geometry source, and {sid} is not one")
    if sid in p.unread_geometry:
        raise Fault()  # its source's own finding says why
    body = str(e.get("body", sid))
    if sid in p.regions:
        if (released.at_point(body) or ("",))[0] != sid:
            raise Fault(f"{body} is not a region of cut file {sid}; name one {sid}@<x>,<y>")
    else:
        names = [b for b in p.bodies if released.source_of(b) == sid]
        if body not in names:
            raise Fault(f"{body} is not a body of {sid}; its bodies are {', '.join(names)}")
    evaluated = _probe_values(p, e, body)
    quantity = PROBE_QUANTITY[e["probe"]]
    for key, value in evaluated.items():
        recorded = p.stated(f"{eid}.{key}", quantity)
        tol = float(e.get("tol", p.tolerance(quantity)))
        if above_cap(tol, recorded):
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


def _released_datums(p: Project) -> None:
    """[datum-off-solid] for each datum declared on released geometry that lies on no body, each
    derived datum the datums it names give no point, and each datum a derived one is worked out
    from that lies on no triangle corner of an STL or on no region's edge of a cut file."""
    unread = p.unread_geometry
    sheets = [
        sid
        for sid, s in p.sources.items()
        if s.get("kind") == "geometry" and released.is_sheet(p.source_path(sid))
    ]
    # The datums some derived datum is worked out from.
    deriving = {
        str(datum)
        for entry in p.datums.values()
        if isinstance(entry, dict)
        for through in entry.values()
        for datum in through
    }
    for name, point in p.datums.items():
        sheet = next((s for s in sheets if name.startswith(f"{s}.")), None)
        derived = isinstance(point, dict)
        misshapen = not derived and len(point) != (3 if sheet is None else 2)
        if misshapen:
            shape = "[x, y, z]" if sheet is None else f"[x, y] on cut file {sheet}"
            p.error("schema", f"evidence.yaml datums.{name}: must be {shape}, not {point}")
        elif released.source_of(name.partition(".")[0]) in unread or sheet in unread:
            continue  # its source's own finding says why
        elif derived:
            with p.filing("datum-off-solid", f"datum {name}: "):
                p.derived_datum(name)
        elif sheet is not None:
            found, at = p.regions[sheet], (point[0], point[1])
            holding = released.outlines_at(found, at, p.length_tol)
            if not holding:
                p.error(
                    "datum-off-solid",
                    f"datum {name} of cut file {sheet}: lies inside no region's outer contour",
                )
            elif name in deriving and (
                gap := released.off_edge([found[i] for i in holding], at, p.length_tol)
            ):
                p.error(
                    "datum-off-solid",
                    f"datum {name} of cut file {sheet}: lies on no region's edge, {gap:.4g} from "
                    "the nearest; a datum derived from it is pinned on a sheet only by edges",
                )
        elif (named := p.released_datum(name)) is None:
            p.error(
                "datum-off-solid",
                f"datum {name}: names no body of a geometry source; name it <body>.<feature>",
            )
        elif (gap := released.off_solid(p.bodies[named[0]], named[1], p.length_tol)) is not None:
            p.error("datum-off-solid", f"datum {name} of body {named[0]}: {released.off(gap)}")
        elif (
            name in deriving
            and released.is_mesh(p.source_path(released.source_of(named[0])))
            and (gap := released.off_corner(p.bodies[named[0]], named[1], p.length_tol))
        ):
            p.error(
                "datum-off-solid",
                f"datum {name} of body {named[0]}: lies on no triangle corner, {gap:.4g} from the "
                "nearest; a datum derived from it is pinned on an STL only by corners",
            )


def _offsets(text: str, needle: str) -> list[int]:
    """Every offset where needle occurs in text, none for an empty needle."""
    return [m.start() for m in re.finditer(f"(?={re.escape(needle)})", text)] if needle else []


def _quote_spans(page: str, quote: str) -> list[tuple[int, int]]:
    """Where quote occurs on a page normalized with its line-break hyphens marked by NUL, as spans
    of the page with those hyphens dropped: found with them dropped (inter-|toe), else kept
    (dual-|axis); and, as the quote matcher does, ignoring whitespace where it is not found as
    written."""
    dropped, kept = page.replace("\0", ""), page.replace("\0", "-")
    for squashed in (False, True):
        for reading, to_dropped in (
            (dropped, lambda i: i),
            (kept, lambda i: i - page.count("\0", 0, i)),
        ):
            # The offset in reading of each char searched: every char, or every non-space one.
            at = [i for i, ch in enumerate(reading) if not (squashed and ch.isspace())]
            searched = "".join(reading[i] for i in at)
            needles = dict.fromkeys(
                re.sub(r"\s+", "", n) if squashed else n for n in sources.needles(quote)
            )
            found = [
                (to_dropped(at[start]), to_dropped(at[start + len(needle) - 1] + 1))
                for needle in needles
                for start in _offsets(searched, needle)
            ]
            if found:
                return found
    return []


def coverage(p: Project) -> list[tuple[str, str, str]]:
    """The coverage sweep: each stated quantity of a text source that no quote or skip covers, as
    (source, p<page>, the quantity in its context), and each body of a geometry source that no
    shape check or skip covers, as (source, body <name>, why). Each is a [coverage] error."""
    uncovered = []
    for sid, s in p.sources.items():
        geometry = s.get("kind") == "geometry"
        if sid in p.unread_geometry if geometry else not (p.available(sid) and p.is_text(sid)):
            continue
        if s.get("coverage") is False:
            p.warn("coverage-off", f"source {sid}: coverage: false, so the sweep does not read it")
            continue
        skips = [k for k in p.skipped if k.get("source") == sid]
        for k in skips:
            if not k.get("reason"):
                p.error("skip-reason", f"skip in {sid}: reason is required")
        if geometry:
            uncovered += _uncovered_bodies(p, sid, skips)
        else:
            uncovered += _uncovered_text(p, sid, skips)
    for sid, where, line in uncovered:
        what = "" if where.startswith("body ") else "unledgered stated quantity "
        p.error("coverage", f"{sid} {where}: {what}{line}")
    return uncovered


def _uncovered_text(p: Project, sid: str, skips: list[dict]) -> list[tuple[str, str, str]]:
    uncovered = []
    anchors = [e for e in p.evidence if e.get("source") == sid and "quote" in e]
    for k in skips:
        if not ("quote" in k or "pages" in k or ("from" in k and "to" in k)):
            p.error("skip-anchor", f"skip in {sid}: needs quote, pages, or from + to")
    skipped_pages = {n for k in skips for n in k.get("pages", [])}
    matched: set[int] = set()  # the skips, by index, that cover text on some page
    for n, raw in enumerate(sources.pages(p.source_path(sid)), 1):
        if n in skipped_pages:
            continue
        page = sources.normalize(raw, hyphen="\0")
        text = page.replace("\0", "")
        spans = []
        for a in anchors:
            if a.get("page") in (None, n):
                spans += _quote_spans(page, a["quote"])
        for i, k in enumerate(skips):
            if k.get("page") not in (None, n):
                continue
            found = _quote_spans(page, k["quote"]) if "quote" in k else []
            if "from" in k:
                start, end = sources.normalize(k["from"]), sources.normalize(k.get("to", ""))
                a = text.find(start)
                b = text.find(end, a + 1) if a != -1 else -1
                found += [(a, b + len(end))] if b != -1 else []
            if found:
                matched.add(i)
            spans += found
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
    return uncovered


def _rectangle(within) -> tuple[tuple[float, float], tuple[float, float]] | None:
    """The rectangle a skip's within gives by two opposite corners, least corner first."""
    if not (isinstance(within, list) and len(within) == 2 and all(len(c) == 2 for c in within)):
        return None
    (x0, y0), (x1, y1) = within
    return (min(x0, x1), min(y0, y1)), (max(x0, x1), max(y0, y1))


def _uncovered_bodies(p: Project, sid: str, skips: list[dict]) -> list[tuple[str, str, str]]:
    """The bodies of a geometry source that no shape check compares and no skip sets aside: a
    file's solids by name, a cut file's regions each by a point inside it."""
    compared = [str(c.get("body")) for c in p.checks if c.get("kind") == "shape"]
    if sid not in p.regions:
        names = [b for b in p.bodies if released.source_of(b) == sid]
        for k in skips:
            if "body" not in k:
                p.error("skip-anchor", f"skip in {sid}: a geometry source's skip names its body")
            elif k["body"] not in names:
                p.error(
                    "skip-not-found",
                    f"skip in {sid}: {k['body']} is not a body of {sid}; its bodies are "
                    f"{', '.join(names)}",
                )
        covered = {*compared, *(k.get("body") for k in skips)}
        return [(sid, f"body {name}", _UNCOVERED) for name in names if name not in covered]
    found, covered = p.regions[sid], set()
    for name in compared:
        try:
            source, index = p.region(name)
        except Fault:
            continue  # the shape check's own finding says why
        if source == sid:
            covered.add(index)
    for k in skips:
        with p.filing("skip-not-found", f"skip in {sid}: "):
            if "body" in k:
                source, index = p.region(k["body"])
                if source != sid:
                    raise Fault(f"{k['body']} is not on {sid}")
                covered.add(index)
            elif (rectangle := _rectangle(k.get("within"))) is not None:
                inside = released.regions_within(found, rectangle, p.length_tol)
                if not inside:
                    raise Fault(f"within {k['within']} holds no whole region of {sid}")
                covered |= set(inside)
            else:
                raise Fault(
                    f"a cut file's skip names a region by a point inside it, body: {sid}@<x>,<y>, "
                    "or the regions inside a rectangle, within: [[x, y], [x, y]]",
                    "skip-anchor",
                )
    return [
        (sid, f"body {released.point_name(sid, released.inner_point(region))}", _UNCOVERED)
        for i, region in enumerate(found)
        if i not in covered
    ]


def named_by_checks(p: Project, c: dict, steps: bool = True, weighs=None) -> list[str]:
    """The params check c reads itself, in order: those its poses name, its sweep's steps (unless
    steps is False), and for a mass check its density, or without one the mass model's params for
    the parts it weighs (its parts, else weighs, else every part), then its add and counts."""
    names = pose_refs(c)
    if steps and isinstance(c.get("sweep"), dict):
        names.append(str(c["sweep"].get("steps")))
    if c.get("kind") == "mass":
        if c.get("density") is None:
            names += mass_params(p, c.get("parts") or weighs)
        names += [str(c.get("density")), *map(str, c.get("add") or [])]
        names += [str(n) for n in (c.get("counts") or {}).values()]
    if c.get("kind") == "count" and "thread" in c:
        names.append(str(c["thread"]))
    return [n for n in dict.fromkeys(names) if n in p.params]


def mass_params(p: Project, parts=None) -> list[str]:
    """The params the mass model weighs parts by: every part's, or only those of parts."""
    entries = [p.parts.get(n) or {} for n in parts] if parts is not None else p.parts.values()
    return [str(v) for entry in entries for v in entry.values()]


def resolution(p: Project) -> set[str]:
    """The params the checks read only as a sweep's steps."""
    steps = {
        str(c["sweep"].get("steps")) for c in p.checks if isinstance(c.get("sweep"), dict)
    } & p.params.keys()
    return steps - {n for c in p.checks for n in named_by_checks(p, c, steps=False)}


def _params(p: Project) -> None:
    """Fill p.values and p.rests_on, holding each param to what its basis requires."""
    p.resolution = resolution(p)
    pending = {}
    for name, spec in p.params.items():
        basis, gap = spec.get("basis"), spec.get("gap")
        if basis not in BASES:
            p.error("param-basis", f"param {name}: basis must be one of {', '.join(BASES)}")
            continue
        if gap and basis == "source":
            p.error("param-gap", f"param {name}: a source param has no value for a gap to replace")
        elif gap and gap not in p.gaps:
            p.error("param-gap", f"param {name}: unknown gap {gap!r}")
        if "thread" in spec:
            with p.filing("param-thread", f"param {name}: "):
                p.values[name] = _thread(p, name, spec)
                p.rests_on[name] = basis if basis in RESTS_ON else "proposed"
            continue
        if basis == "derived":
            if gap and not spec.get("interpretation"):
                p.error(
                    "param-derived",
                    f"param {name}: derived naming a gap needs interpretation, the choice its "
                    "expr makes",
                )
            pending[name] = spec
            continue
        p.rests_on[name] = basis
        if basis == "source":
            ref = spec.get("from", "")
            value = p.value(ref)
            if value is None:
                p.error("param-from", f"param {name}: from: {ref!r} is not an evidence value")
                continue
            if "value" in spec and not math.isclose(float(spec["value"]), value, rel_tol=1e-9):
                p.error("param-mismatch", f"param {name}: value {spec['value']} != {ref} = {value}")
            p.values[name] = value
            continue
        if basis == "measured":
            item = p.item(str(spec.get("from", "")).partition(".")[0])
            if item is None or "image" not in item:
                p.error("param-from", f"param {name}: measured needs from: an image evidence id")
            elif (p.sources.get(str(item.get("source"))) or {}).get("kind") == "geometry":
                # A geometry source holds no figure: an image anchored to it is a render of it.
                p.error(
                    "param-from",
                    f"param {name}: from: {item['id']} is a render of geometry source "
                    f"{item['source']}, not a figure of the object",
                )
            for key in ("value", "method", "uncertainty"):
                if key not in spec:
                    p.error("param-measured", f"param {name}: measured needs {key}")
        else:
            if "value" not in spec or not spec.get("rationale"):
                p.error("param-proposed", f"param {name}: proposed needs value and rationale")
            # A sweep's resolution asks the sources nothing, so it has no gap to name.
            if not gap and name not in p.resolution:
                p.warn("param-gap", f"param {name}: proposed value names no gap to close it")
        if "value" in spec:
            p.values[name] = float(spec["value"])
    _derived(p, pending)


def _thread(p: Project, name: str, spec: dict) -> threads.Size:
    """A thread param's sizes; a Fault where neither table holds its designation. [param-thread]
    unless a source one is printed by the statement it is from, and [thread-standard] unless a
    proposed one comes from the project's table."""
    basis, designation = spec["basis"], spec["thread"]
    thread = threads.named(designation)
    if thread is None:
        known = threads.pitches(designation) or (
            "name an ISO metric thread (M3, M8x1) or a Unified one (1/4-20, 6-32)"
        )
        raise Fault(f"thread {designation} is in neither thread table; {known}")
    size = threads.Size(thread, units.convert(1.0, "mm", p.units))
    if "expr" in spec or basis not in ("source", "proposed"):
        p.error(
            "param-thread",
            f"param {name}: a thread is stated by a source or proposed, and takes no expr",
        )
    if "value" in spec and not math.isclose(float(spec["value"]), size, rel_tol=1e-9):
        p.error(
            "param-mismatch",
            f"param {name}: value {spec['value']} != {thread.name}'s major diameter "
            f"{float(size):g}",
        )
    if basis == "source":
        ref = str(spec.get("from", ""))
        item = p.item(ref) or p.item(ref.partition(".")[0])
        stated = None if item is None else item.get("quote", item.get("reading"))
        printed = threads.printed_in(str(stated or ""))
        if item is None or stated is None:
            p.error(
                "param-thread",
                f"param {name}: from: {ref!r} is no quote or reading, which is what states a "
                "thread",
            )
        elif thread not in printed:
            found = ", ".join(dict.fromkeys(t.name for t in printed)) or "no thread"
            p.error("param-thread", f"param {name}: {item['id']} prints {found}, not {thread.name}")
    elif basis == "proposed":
        if not spec.get("rationale"):
            p.error("param-proposed", f"param {name}: proposed needs rationale")
        if not spec.get("gap"):
            p.warn("param-gap", f"param {name}: proposed value names no gap to close it")
        if thread.standard != p.thread_standard:
            p.error(
                "thread-standard",
                f"param {name}: proposes {thread.name} from the "
                f"{threads.STANDARDS[thread.standard]} table, where project.yaml's threads is "
                f"{p.thread_standard}; a proposed thread comes from the project's table",
            )
    return size


def _derived(p: Project, pending: dict[str, dict]) -> None:
    """Resolve the derived params, which may read each other, until none is left that can be."""
    inputs = {name: expr_names(str(spec.get("expr") or "")) for name, spec in pending.items()}
    for name, spec in list(pending.items()):
        unknown = sorted(inputs[name] - p.params.keys())
        if not spec.get("expr"):
            p.error("param-derived", f"param {name}: derived needs expr")
        elif unknown:
            p.error("param-derived", f"param {name}: expr uses undefined {unknown}")
        else:
            continue
        del pending[name]
    progressed = True
    while pending and progressed:
        progressed = False
        for name, spec in list(pending.items()):
            needs = inputs[name]
            if not needs <= p.values.keys():
                continue
            progressed = True
            del pending[name]
            try:
                value = evaluate(spec["expr"], p.values)
            except ValueError as exc:  # it is left with no value, as whatever reads it will say
                p.error("param-derived", f"param {name}: expr {exc}")
                continue
            if not needs:
                p.error(
                    "param-constant",
                    f"param {name}: expr {spec['expr']!r} references no param, so its value "
                    "traces to nothing; give the number its own basis",
                )
            if "value" in spec and not math.isclose(float(spec["value"]), value, rel_tol=1e-6):
                p.error(
                    "param-mismatch", f"param {name}: value {spec['value']} != expr = {value:g}"
                )
            p.values[name] = value
            # One naming a gap rests on proposed: its expr is itself a reconstruction choice.
            weakest = max((p.rests_on[n] for n in needs), key=RESTS_ON.index, default="proposed")
            p.rests_on[name] = "proposed" if spec.get("gap") else weakest
    for name in pending:  # each waits on an input with no value, or on itself
        waits, seen = list(inputs[name]), set()
        while waits and name not in seen:
            n = waits.pop()
            if n not in seen and n in pending:
                waits += inputs[n]
            seen.add(n)
        missing = ", ".join(sorted(inputs[name] - p.values.keys()))
        why = "circular dependency" if name in seen else f"its input {missing} has no value"
        p.error("param-derived", f"param {name}: {why}")


def unused_values(p: Project) -> list[tuple[dict, str]]:
    """Each in-scope ledger value no param uses and no check compares or poses at, as its item
    and key. The image a measured param scales off states no values, so nothing is asked of it."""
    used = {spec.get("from") for spec in p.params.values()}
    used |= {ref for c in p.checks for ref in [*compared_refs(c), *pose_refs(c)]}
    return [
        (e, key)
        for e in p.evidence
        if e.get("scope") not in _SET_ASIDE
        for key in e.get("values") or {}
        if f"{e['id']}.{key}" not in used
    ]


def unnamed_gaps(p: Project) -> list[str]:
    """The gaps no param's gap names."""
    return [g for g in p.gaps if g not in {spec.get("gap") for spec in p.params.values()}]


def _usage(p: Project) -> None:
    """Every ledger value is used, checked or set aside, every gap is named, and every conflict
    cites the ledger; in a known-first project what is unused waits instead."""
    scaled = {
        str(spec.get("from", "")).partition(".")[0]
        for spec in p.params.values()
        if spec.get("basis") == "measured"
    }
    for e in p.evidence:
        only_scaled = e["id"] in scaled and not e.get("values")
        if e.get("scope") in _SET_ASIDE and not e.get("reason") and not only_scaled:
            p.error("evidence-scope", f"{e['id']}: scope {e['scope']} needs a reason")
    if not p.known_first:
        for e, key in unused_values(p):
            p.error(
                "evidence-unused",
                f"{e['id']}.{key} is neither used by a param nor checked "
                "(or mark the item scope: not-modeled with a reason)",
            )
        for gap in unnamed_gaps(p):
            p.warn("gap-unused", f"gap {gap}: no param names it")
    for c in p.conflicts:
        for eid in c.get("evidence", []):
            if p.item(eid) is None:
                p.error("conflict-ref", f"conflict {c.get('id')}: unknown evidence {eid}")
        if not c.get("resolution"):
            p.warn("conflict-open", f"conflict {c.get('id')}: {c.get('summary', '')} (unresolved)")


def known_first(p: Project) -> None:
    """[known-first] for each param of a known-first project resting on a proposed value, once
    the build has settled which params are only a sweep's resolution."""
    for name in [n for n in p.params if n in p.inexact] if p.known_first else []:
        p.error(
            "known-first",
            f"param {name} rests on proposed, and a known-first project holds only what the "
            "sources settle: leave out what needs it, and ask for it in gaps.yaml",
        )


def _feeding(p: Project, names: set[str]) -> set[str]:
    """names, and every param their derived exprs read, however deep."""
    found, pending = set(), list(names)
    while pending:
        name = pending.pop()
        if name not in found:
            found.add(name)
            spec = p.params.get(name) or {}
            if spec.get("basis") == "derived":
                pending += expr_names(str(spec.get("expr", ""))) & p.params.keys()
    return found


def unchecked(p: Project, read: set[str], model_reads: set[str]) -> None:
    """[unchecked-source] for each source param no check checks, where read is the params the
    checks read and model_reads those model.py reads. A check checks the params whose ledger value
    it compares and what the params it reads are derived from. No check sees a physics value, nor
    a param read only on the way to one, unless model.py reads it too."""
    feeds_physics = _feeding(p, p.physics) - p.physics
    physics_only = feeds_physics - _feeding(p, p.params.keys() - p.physics - feeds_physics)
    checked = _feeding(p, read)
    unchecked = p.params.keys() - checked - p.physics - physics_only
    unchecked |= physics_only & _feeding(p, model_reads) - checked
    compared = {ref for c in p.checks for ref in compared_refs(c)}
    for name, spec in p.params.items():
        if name in unchecked and spec.get("basis") == "source" and spec.get("from") not in compared:
            p.warn(
                "unchecked-source",
                f"param {name}: {spec.get('from')} feeds the model but no check confirms the "
                "geometry realises it",
            )
