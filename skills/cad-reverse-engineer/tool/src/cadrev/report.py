"""Write build/report.md and build/report.json."""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import asdict
from pathlib import Path

from .geometry import CheckResult
from .project import BASES, Project


def _cell(value) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ")


def _table(header: list[str], rows: list[list]) -> list[str]:
    if not rows:
        return ["_None._", ""]
    lines = ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
    lines += ["| " + " | ".join(_cell(c) for c in row) + " |" for row in rows]
    return lines + [""]


def write(p: Project, results: list[CheckResult], images: list[Path]) -> Path:
    out = p.root / "build"
    out.mkdir(exist_ok=True)
    errors = [f for f in p.findings if f.level == "error"]
    warnings = [f for f in p.findings if f.level == "warning"]
    bases = Counter(spec.get("basis") for spec in p.params.values())
    traced = len(p.params) - len(p.proposed)
    total = len(p.params) or 1
    status = "VERIFIED" if not errors else "NOT VERIFIED"

    md = [f"# {p.meta.get('name', 'Reconstruction')}: verification report", ""]
    md += [f"**{status}**: {len(errors)} errors, {len(warnings)} warnings. "
           f"{sum(r.ok for r in results)}/{len(results)} geometry checks pass. "
           f"{traced}/{len(p.params)} parameters ({traced / total:.0%}) trace to sources alone; "
           f"{len(p.proposed)} rest on proposed values.", ""]
    md += ["VERIFIED means every number in the model is accounted for and the geometry matches "
           "every checked source value. It does not mean the sources fully define the part: "
           "proposed parameters are reconstruction choices, listed below.", ""]

    md += ["## Sources", ""]
    md += _table(["id", "kind", "citation", "sha256"],
                 [[s["id"], s.get("kind"), s.get("citation"), str(s.get("sha256", ""))[:12]]
                  for s in p.meta.get("sources", [])])

    md += ["## Geometry checks against the sources", ""]
    md += _table(["check", "result", "expected (evidence)", "measured", "interpretation"],
                 [[r.id, "pass" if r.ok else "**FAIL**", r.expected, r.measured, r.note]
                  for r in results])

    md += ["## Parameters", ""]
    md += [" · ".join(f"{b}: {bases[b]}" for b in BASES), ""]
    md += _table(["param", "value", "basis", "from / expr", "note"],
                 [[n, f"{p.values.get(n, float('nan')):g}",
                   s.get("basis") + (" (from proposed)" if s.get("basis") == "derived"
                                     and n in p.proposed else ""),
                   s.get("from") or s.get("expr") or "",
                   s.get("interpretation") or s.get("rationale") or s.get("method") or ""]
                  for n, s in p.params.items()])

    md += ["## Evidence", ""]
    md += _table(["id", "source", "locator", "values", "anchor"],
                 [[eid, e.get("source"), f"{e.get('locator', '')}"
                   + (f", p{e['page']}" if e.get("page") else ""),
                   ", ".join(f"{k}={v}" for k, v in (e.get("values") or {}).items()),
                   f"“{e['quote']}”" if "quote" in e
                   else f"figure {e.get('image')}: “{e.get('reading')}”"
                   + ("" if e.get("confirmed_by") else " (unconfirmed)")]
                  for eid, e in p.evidence.items()])

    unconfirmed = [(eid, e) for eid, e in p.evidence.items() if "image" in e and not e.get("confirmed_by")]
    if unconfirmed:
        md += ["## Figure readings awaiting human confirmation", ""]
        for eid, e in unconfirmed:
            md += [f"- **{eid}** ({e.get('locator')}): reads “{e.get('reading')}”", "",
                   f"  ![{eid}](../{e['image']})", ""]

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
        "errors": [asdict(f) for f in errors],
        "warnings": [asdict(f) for f in warnings],
        "checks": [asdict(r) for r in results],
        "params": {n: {"value": p.values.get(n), **s} for n, s in p.params.items()},
        "bases": dict(bases),
        "rests_on_proposed": sorted(p.proposed),
    }, indent=2, default=str), encoding="utf8")
    return path
