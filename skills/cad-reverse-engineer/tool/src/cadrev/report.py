"""Write build/report.md and build/report.json."""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import asdict
from pathlib import Path

from .geometry import CheckResult
from .project import BASES, LENGTH_TOL, MODEL_LITERALS, RESTS_ON, Project, check_tolerance


def _cell(value) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ")


def _table(header: list[str], rows: list[list]) -> list[str]:
    if not rows:
        return ["_None._", ""]
    lines = ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
    lines += ["| " + " | ".join(_cell(c) for c in row) + " |" for row in rows]
    return lines + [""]


PASSING = ("VERIFIED", "VERIFIED PENDING REVIEW")


def awaiting_confirmation(p: Project) -> list[dict]:
    """The figure readings no named human has confirmed yet, each with its crop."""
    return [{"evidence": eid, "locator": e.get("locator"), "reading": e.get("reading"), "image": e["image"]}
            for eid, e in p.evidence.items() if "image" in e and not e.get("confirmed_by")]


def status(p: Project, partial: bool = False) -> str:
    """The one place a verification run's status is decided; everything else reads it.

    partial: the run skipped the build or the coverage sweep, so it makes no claim.
    """
    if partial:
        return "PARTIAL"
    if any(f.level == "error" for f in p.findings):
        return "NOT VERIFIED"
    return "VERIFIED PENDING REVIEW" if awaiting_confirmation(p) else "VERIFIED"


def exact(p: Project, status: str) -> bool:
    """Exact: VERIFIED with no parameter resting on a proposed value."""
    return status == "VERIFIED" and not p.proposed


def measured_params(p: Project) -> list[dict]:
    """Each measured parameter with the method and uncertainty of its scaling."""
    return [{"param": n, "value": p.values.get(n), "from": s.get("from"),
             "method": s.get("method"), "uncertainty": s.get("uncertainty")}
            for n, s in p.params.items() if s.get("basis") == "measured"]


def tolerances(p: Project) -> list[dict]:
    """Each check whose tolerance is not cadrev's default, with that tolerance: tol for one
    differing from LENGTH_TOL, and tol_rel for every mass check, which has no default."""
    out = []
    for c in p.checks:
        tolerance = check_tolerance(p, c)
        if tolerance is not None and tolerance != ("tol", LENGTH_TOL):
            out.append({"check": c.get("id"), "kind": c.get("kind"), tolerance[0]: tolerance[1]})
    return out


def literal_override(p: Project) -> list | None:
    """The numbers project.yaml allows in model.py in place of the default, or None."""
    literals = p.meta.get("model_literals")
    if literals is None or [float(v) for v in literals] == [float(v) for v in MODEL_LITERALS]:
        return None
    return literals


def counts(p: Project, results: list[CheckResult]) -> dict[str, int]:
    """The headline numbers shown beside the status."""
    errors = sum(f.level == "error" for f in p.findings)
    return {"errors": errors, "warnings": len(p.findings) - errors,
            "checks": len(results), "checks_passed": sum(r.ok for r in results),
            "params": len(p.params)} | {
            basis: sum(b == basis for b in p.rests_on.values()) for basis in RESTS_ON}


def write(p: Project, status: str, results: list[CheckResult], images: list[Path]) -> Path:
    out = p.root / "build"
    out.mkdir(exist_ok=True)
    errors = [f for f in p.findings if f.level == "error"]
    warnings = [f for f in p.findings if f.level == "warning"]
    bases = Counter(spec.get("basis") for spec in p.params.values())
    headline = counts(p, results)
    loosened = tolerances(p)
    override = literal_override(p)

    md = [f"# {p.meta.get('name', 'Reconstruction')}: verification report", ""]
    md += [f"**{status}**: {headline['errors']} errors, {headline['warnings']} warnings. "
           f"{headline['checks_passed']}/{headline['checks']} geometry checks pass.",
           f"Of {headline['params']} parameters, {headline['source']} rest on sources, "
           f"{headline['measured']} on measured values and {headline['proposed']} on proposed values.", ""]
    if exact(p, status):
        md += ["**Exact**: no parameter rests on a proposed value.", ""]
    md += ["VERIFIED means every number in the model is accounted for and the geometry matches "
           "every checked source value. It does not mean the sources fully define the part: "
           "proposed parameters are reconstruction choices, listed below.", ""]
    awaiting = awaiting_confirmation(p)
    if status == "VERIFIED PENDING REVIEW":
        md += [f"PENDING REVIEW: {len(awaiting)} figure readings await human confirmation, listed below. "
               "Once a named reviewer has checked each against its crop and written `confirmed_by`, "
               "the project is VERIFIED.", ""]

    md += ["## Sources", ""]
    md += _table(["id", "kind", "citation", "sha256"],
                 [[s["id"], s.get("kind"), s.get("citation"), str(s.get("sha256", ""))[:12]]
                  for s in p.meta.get("sources", [])])

    md += ["## Geometry checks against the sources", ""]
    md += _table(["check", "result", "expected (evidence)", "measured", "interpretation"],
                 [[r.id, "pass" if r.ok else "**FAIL**", r.expected, r.measured, r.note]
                  for r in results])

    md += ["## Non-default tolerances", ""]
    md += _table(["check", "kind", "tolerance"],
                 [[t["check"], t["kind"], next(f"{k} {t[k]:g}" for k in ("tol", "tol_rel") if k in t)]
                  for t in loosened])

    md += ["## Model literal override", ""]
    md += ([f"project.yaml `model_literals` allows {', '.join(f'{v:g}' for v in override)} in model.py, "
            f"in place of the default {', '.join(f'{v:g}' for v in MODEL_LITERALS)}.", ""]
           if override is not None else ["_None._", ""])

    md += ["## Parameters", ""]
    md += [" · ".join(f"{b}: {bases[b]}" for b in BASES), ""]
    md += _table(["param", "value", "basis", "from / expr", "note"],
                 [[n, f"{p.values.get(n, float('nan')):g}",
                   str(s.get("basis")) + (f" (rests on {p.rests_on[n]})" if s.get("basis") == "derived"
                                          and n in p.rests_on else ""),
                   s.get("from") or s.get("expr") or "",
                   s.get("interpretation") or s.get("rationale") or s.get("method") or ""]
                  for n, s in p.params.items()])

    md += ["## Measured parameters", ""]
    md += _table(["param", "value", "from", "method", "uncertainty"],
                 [[m["param"], f"{m['value']:g}", m["from"], m["method"], m["uncertainty"]]
                  for m in measured_params(p)])

    md += ["## Evidence", ""]
    md += _table(["id", "source", "locator", "values", "anchor"],
                 [[eid, e.get("source"), f"{e.get('locator', '')}"
                   + (f", p{e['page']}" if e.get("page") else ""),
                   ", ".join(f"{k}={v}" for k, v in (e.get("values") or {}).items()),
                   f"“{e['quote']}”" if "quote" in e
                   else f"figure {e.get('image')}: “{e.get('reading')}”"
                   + ("" if e.get("confirmed_by") else " (unconfirmed)")]
                  for eid, e in p.evidence.items()])

    if awaiting:
        md += ["## Figure readings awaiting human confirmation", ""]
        for a in awaiting:
            md += [f"- **{a['evidence']}** ({a['locator']}): reads “{a['reading']}” in `{a['image']}`", "",
                   f"  ![{a['evidence']}](../{a['image']})", ""]

    md += ["## Conflicts between sources", ""]
    md += _table(["id", "evidence", "summary", "resolution"],
                 [[c.get("id"), ", ".join(c.get("evidence", [])), c.get("summary", ""),
                   c.get("resolution") or "**open**"] for c in p.conflicts])

    md += ["## Open gaps", ""]
    affected = {gid: [n for n, s in p.params.items() if s.get("gap") == gid] for gid in p.gaps}
    md += _table(["gap", "question", "close by", "params"],
                 [[gid, g.get("question", ""), g.get("ask", ""), ", ".join(affected[gid])]
                  for gid, g in p.gaps.items()])

    if images:
        md += ["## Figure overlays", "",
               "Model edges (magenta) over the source figure, scaled by the cited dimension "
               "(blue). Visual comparison only.", ""]
        md += [f"![{i.stem}](overlays/{i.name})" for i in images] + [""]

    md += ["## Findings", ""]
    md += [f"- **{f.level}** `{f.rule}`: {f.message}" for f in errors + warnings] or ["_None._"]

    path = out / "report.md"
    path.write_text("\n".join(md) + "\n", encoding="utf8")
    (out / "report.json").write_text(json.dumps({
        "status": status,
        "counts": headline,
        "findings": [asdict(f) for f in errors + warnings],
        "checks": [asdict(r) for r in results],
        "tolerances": loosened,
        "model_literals": override,
        "exact": exact(p, status),
        "params": {n: {"value": p.values.get(n), "rests_on": p.rests_on.get(n), **s}
                   for n, s in p.params.items()},
        "bases": dict(bases),
        "rests_on_proposed": sorted(p.proposed),
        "measured": measured_params(p),
        "awaiting_confirmation": awaiting,
    }, indent=2, default=str), encoding="utf8")
    return path
