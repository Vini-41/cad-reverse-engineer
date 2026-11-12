"""A verification run's status, and build/report.md and build/report.json, which hold the same
data."""

from __future__ import annotations

import json
import math
from collections import Counter
from dataclasses import asdict
from pathlib import Path

from . import checks, ledger
from .build import GEAR_BY, PHYSICS, Model, printed, range_ends
from .checks import Result
from .lint import MODEL_LITERALS
from .motion import pose_text
from .project import BASES, DEFAULT_TOL, RESTS_ON, Project

VERIFIED, PENDING_REVIEW, PARTIAL, NOT_VERIFIED = (
    "VERIFIED",
    "VERIFIED PENDING REVIEW",
    "PARTIAL",
    "NOT VERIFIED",
)
PASSING = (VERIFIED, PENDING_REVIEW)


def awaiting_confirmation(p: Project) -> list[dict]:
    """The figure readings no named human has confirmed yet, each with its crop."""
    return [
        {
            "evidence": e["id"],
            "locator": e.get("locator"),
            "reading": e.get("reading"),
            "image": e["image"],
        }
        for e in p.evidence
        if "image" in e and not e.get("confirmed_by")
    ]


def status(p: Project, partial: bool = False) -> str:
    """The one place a verification run's status is decided. A partial run skipped the build or
    the coverage sweep, so it makes no claim."""
    if partial:
        return PARTIAL
    if any(f.level == "error" for f in p.findings):
        return NOT_VERIFIED
    return PENDING_REVIEW if awaiting_confirmation(p) else VERIFIED


def counts(p: Project, results: list[Result]) -> dict[str, int]:
    """The headline numbers: the params by what they rest on, proposed physics values apart."""
    errors = sum(f.level == "error" for f in p.findings)
    apart = p.proposed & p.physics
    rest = {
        b: sum(basis == b and n not in apart for n, basis in p.rests_on.items()) for b in RESTS_ON
    }
    return {
        "errors": errors,
        "warnings": len(p.findings) - errors,
        "checks": len(results),
        "checks_passed": sum(r.ok for r in results),
        "params": len(p.params),
        **rest,
        "physics_proposed": len(apart),
    }


def waiting(p: Project) -> dict | None:
    """What a known-first project leaves for later: each stated value no param or check uses, and
    each gap no param names, the question a waiting part asks; None for any other project."""
    if not p.known_first:
        return None
    return {
        "values": [
            {
                "evidence": e["id"],
                "key": key,
                "value": e["values"][key],
                "source": e.get("source"),
                "locator": e.get("locator"),
            }
            for e, key in ledger.unused_values(p)
        ],
        "gaps": [
            {"gap": gap, "question": p.gaps[gap].get("question"), "ask": p.gaps[gap].get("ask")}
            for gap in ledger.unnamed_gaps(p)
        ],
    }


def waiting_clause(p: Project) -> str:
    n = len(ledger.unused_values(p))
    return f"{n} stated value{'s' * (n != 1)} wait{'s' * (n == 1)}"


def motion(p: Project, model: Model, coarsened: dict) -> dict:
    """How the model moves, as the MJCF exports it. No joints means the model is static, unless a
    finding dropped them."""

    def valued(entry: dict, keys) -> dict:
        return {
            k: {"from": entry[k], "value": printed(p.values[entry[k]])[0]}
            for k in keys
            if k in entry
        }

    joints = {}
    for name, j in model.joints.items():
        joints[name] = {k: j[k] for k in ("type", "parent", "child", "drive") if k in j}
        if "range" in j:
            (low, lo), (high, hi) = range_ends(p, j)
            joints[name]["range"] = {"from": [low, high], "value": list(printed(lo, hi))}
        joints[name] |= valued(j, PHYSICS["joint"])
    cables = {}
    for name, c in model.cables.items():
        cables[name] = {"path": list(c["path"])}
        if "wheel" in c:
            cables[name] |= {"wheel": c["wheel"], "closes": valued(c["closes"], c["closes"])}
    return {
        "joints": joints,
        "loops": {name: list(pair) for name, pair in model.loops.items()},
        "gears": {
            name: {"driver": g["driver"], "driven": g["driven"]} | valued(g, GEAR_BY)
            for name, g in model.gears.items()
        },
        "tendons": {
            name: {"path": list(t["path"])} | valued(t, PHYSICS["tendon"])
            for name, t in model.tendons.items()
        },
        "cables": cables,
        "coarsened": coarsened,
        "dropped": model.dropped,
    }


def _table(header: list[str], rows: list[list]) -> list[str]:
    if not rows:
        return ["_None._", ""]
    lines = ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
    for row in rows:
        cells = (str(cell).replace("|", "\\|").replace("\n", " ") for cell in row)
        lines.append("| " + " | ".join(cells) + " |")
    return lines + [""]


def _motion_lines(moves: dict | None) -> list[str]:
    if moves is None:
        return []
    if moves["dropped"]:
        return [
            "**Motion dropped**: model.py returns joints or loops the assembly cannot hold (see "
            "the findings), so nothing is posed or exported as MJCF.",
            "",
        ]
    if not moves["joints"]:
        return [
            "**Static**: model.py returns no joints, so nothing is posed or exported as MJCF.",
            "",
        ]
    joints, loops = len(moves["joints"]), len(moves["loops"])
    lines = []
    for name, c in moves["cables"].items():
        line = f"- Cable `{name}` through {' → '.join(c['path'])}"
        if "wheel" in c:
            closes = ", ".join(
                f"{j} to {v['value']:g} ({v['from']})" for j, v in c["closes"].items()
            )
            line += f", wound on {c['wheel']}; its full turn closes {closes}"
        lines.append(line + ".")
    if lines:
        lines.append("")
    for name, m in moves["coarsened"].items():
        lines.append(
            f"- Mesh `meshes/{name}.stl` exported coarser for MuJoCo's STL decoder: {m['faces']} "
            f"faces at tolerance {m['tolerance']:g} in the project's length unit and angular "
            f"tolerance {m['angular_tolerance']:g} rad, from {m['default_faces']} at the default."
        )
    if moves["coarsened"]:
        lines.append("")
    return [
        f"**Kinematic**: {joints} joint{'s' * (joints != 1)} and {loops} loop{'s' * (loops != 1)}, "
        "exported as `build/model.mjcf`; a posed check shows its pose beside its interpretation.",
        "",
        *lines,
    ]


def _interpretation(r: Result) -> str:
    """A check's interpretation, after how it was swept and posed, with what it rests on when
    that is less than source."""
    notes = []
    if r.sweep is not None:
        (low, high), (low_from, high_from) = r.sweep["range"], r.sweep["from"]
        notes.append(
            f"swept: {r.sweep['joint']} {low:g} to {high:g} ({low_from} to {high_from}), "
            f"{r.sweep['poses']} poses"
        )
    posed = f"posed: {pose_text(r.pose)}" if r.pose is not None else ""
    if r.from_pose is not None:
        posed = f"from: {pose_text(r.from_pose)}; {posed}"
    notes += [posed, r.note]
    if r.rests_on != "source":
        named = r.rests_on_params + [
            f"{part} ({n} instances uncounted)" for part, n in (r.uncounted or {}).items()
        ]
        notes.append(f"rests on {r.rests_on}: {', '.join(named)}")
    return "; ".join(filter(None, notes))


def _anchor(e: dict) -> str:
    """What an evidence item is anchored by: its quote, its probe, or its figure reading."""
    if "quote" in e:
        return f"“{e['quote']}”"
    if "probe" in e:
        where = f" at {e['at']}" if e.get("at") else ""
        if e.get("between"):
            where = f" between {', '.join(map(str, e['between']))}"
        return f"probe {e['probe']}{where}"
    confirmed = "" if e.get("confirmed_by") else " (unconfirmed)"
    return f"figure {e.get('image')}: “{e.get('reading')}”{confirmed}"


def write(
    p: Project,
    status: str,
    results: list[Result],
    images: list[Path],
    model: Model | None,
    coarsened: dict,
    build_seconds: float | None,
) -> Path:
    """Write build/report.md and build/report.json; model is None when none was built, and
    build_seconds is None where no build ran."""
    out = p.root / "build"
    out.mkdir(exist_ok=True)
    findings = sorted(p.findings, key=lambda f: f.level != "error")  # errors first
    headline = counts(p, results)
    exact = status == VERIFIED and not p.inexact
    waits = waiting(p)
    awaiting = awaiting_confirmation(p)
    moves = None if model is None else motion(p, model, coarsened)
    bases = Counter(spec.get("basis") for spec in p.params.values())
    tolerances = [
        {"check": c.get("id"), "kind": c.get("kind"), found[0]: found[1]}
        for c in p.checks
        if (found := checks.tolerance(p, c)) is not None and found != checks.default_tolerance(c)
    ]
    limits = [
        {"check": c.get("id"), "max_volume": checks.overlap_limit(p, c)}
        for c in p.checks
        if c.get("kind") == "interference"
        and not math.isclose(checks.overlap_limit(p, c), DEFAULT_TOL["length"] ** 3)
    ]
    literals = p.meta.get("model_literals")
    if literals is not None and [float(v) for v in literals] == [float(v) for v in MODEL_LITERALS]:
        literals = None
    measured = [
        {
            "param": n,
            "value": p.values.get(n),
            "from": s.get("from"),
            "method": s.get("method"),
            "uncertainty": s.get("uncertainty"),
        }
        for n, s in p.params.items()
        if s.get("basis") == "measured"
    ]

    physics = headline["physics_proposed"]
    md = [f"# {p.meta.get('name', 'Reconstruction')}: verification report", ""]
    md += [
        f"**{status}**: {headline['errors']} errors, {headline['warnings']} warnings. "
        f"{headline['checks_passed']}/{headline['checks']} geometry checks pass.",
        f"Of {headline['params']} parameters, {headline['source']} rest on sources, "
        f"{headline['measured']} on measured values and {headline['proposed']} on proposed values"
        + (f"; {physics} more are proposed physics values." if physics else "."),
        "",
    ]
    if exact:
        aside = [f"{physics} physics value{'s' * (physics != 1)}"] if physics else []
        resolution = sorted(p.proposed & p.resolution)
        if resolution:
            aside.append(
                f"the sweep resolution{'s' * (len(resolution) != 1)} {', '.join(resolution)}"
            )
        many = len(aside) > 1 or physics > 1 or len(resolution) > 1
        md += [
            "**Exact**: no geometry or kinematic parameter rests on a proposed value; "
            f"{' and '.join(aside)} {'are' if many else 'is'} proposed."
            if aside
            else "**Exact**: no parameter rests on a proposed value.",
            "",
        ]
    if waits is not None:
        n = len(waits["gaps"])
        md += [
            f"**Known first**: {waiting_clause(p)}, with {n} gap{'s' * (n != 1)} no param "
            "names, listed under Waiting.",
            "",
        ]
    md += _motion_lines(moves)
    md += [
        "VERIFIED means every number in the model is accounted for and the geometry matches "
        "every checked source value. It does not mean the sources fully define the part: "
        "proposed parameters are reconstruction choices, listed below.",
        "",
    ]
    if status == PENDING_REVIEW:
        md += [
            f"PENDING REVIEW: {len(awaiting)} figure readings await human confirmation, listed "
            "below. Once a named reviewer has checked each against its crop and written "
            "`confirmed_by`, the project is VERIFIED.",
            "",
        ]
    md += ["## Sources", ""]
    md += _table(
        ["id", "kind", "citation", "sha256"],
        [
            [s["id"], s.get("kind"), s.get("citation"), str(s.get("sha256", ""))[:12]]
            for s in p.meta.get("sources", [])
        ],
    )
    md += ["## Geometry checks against the sources", ""]
    md += _table(
        ["check", "result", "expected (evidence)", "measured", "interpretation"],
        [
            [r.id, "pass" if r.ok else "**FAIL**", r.expected, r.measured, _interpretation(r)]
            for r in results
        ],
    )
    md += ["## Non-default tolerances", ""]
    md += _table(
        ["check", "kind", "tolerance"],
        [
            [t["check"], t["kind"], next(f"{k} {t[k]:g}" for k in ("tol", "tol_rel") if k in t)]
            for t in tolerances
        ],
    )
    md += ["## Non-default overlap limits", ""]
    md += _table(["check", "max_volume"], [[o["check"], f"{o['max_volume']:g}"] for o in limits])
    md += ["## Model literal override", ""]
    if literals is None:
        md += ["_None._", ""]
    else:
        allowed, default = (
            ", ".join(f"{v:g}" for v in values) for values in (literals, MODEL_LITERALS)
        )
        md += [
            f"project.yaml `model_literals` allows {allowed} in model.py, in place of the default "
            f"{default}.",
            "",
        ]
    md += [
        "## Parameters",
        "",
        "Declared basis: " + " · ".join(f"{b}: {bases[b]}" for b in BASES),
        "",
    ]
    md += _table(
        ["param", "value", "basis", "from / expr", "note"],
        [
            [
                n,
                f"{p.values.get(n, math.nan):g}",
                str(s.get("basis"))
                + (
                    f" (rests on {p.rests_on[n]})"
                    if s.get("basis") == "derived" and n in p.rests_on
                    else ""
                ),
                s.get("from") or s.get("expr") or "",
                s.get("interpretation") or s.get("rationale") or s.get("method") or "",
            ]
            for n, s in p.params.items()
        ],
    )
    md += ["## Measured parameters", ""]
    md += _table(
        ["param", "value", "from", "method", "uncertainty"],
        [
            [
                m["param"],
                f"{p.values.get(m['param'], math.nan):g}",
                m["from"],
                m["method"],
                m["uncertainty"],
            ]
            for m in measured
        ],
    )
    md += ["## Evidence", ""]
    md += _table(
        ["id", "source", "locator", "values", "anchor"],
        [
            [
                e["id"],
                e.get("source"),
                f"{e.get('locator', '')}" + (f", p{e['page']}" if e.get("page") else ""),
                ", ".join(f"{k}={v}" for k, v in (e.get("values") or {}).items()),
                _anchor(e),
            ]
            for e in p.evidence
        ],
    )
    md += ["## Probes of released geometry", ""]
    md += _table(
        ["probe", "body", "kind", "records", "evaluates to", "result"],
        [
            [
                f"{q['evidence']}.{q['key']}",
                q["body"],
                q["probe"],
                f"{q['recorded']:g}",
                f"{q['value']:.6g}",
                "pass" if q["ok"] else "**MISMATCH**",
            ]
            for q in p.probes
        ],
    )
    if awaiting:
        md += ["## Figure readings awaiting human confirmation", ""]
        for a in awaiting:
            md += [
                f"- **{a['evidence']}** ({a['locator']}): reads “{a['reading']}” in `{a['image']}`",
                "",
                f"  ![{a['evidence']}](../{a['image']})",
                "",
            ]
    md += ["## Conflicts between sources", ""]
    md += _table(
        ["id", "evidence", "summary", "resolution"],
        [
            [
                c.get("id"),
                ", ".join(c.get("evidence", [])),
                c.get("summary", ""),
                c.get("resolution") or "**open**",
            ]
            for c in p.conflicts
        ],
    )
    if waits is not None:
        md += [
            "## Waiting",
            "",
            "Each stated value below waits: the part it belongs to needs a value the sources "
            "leave open. Each gap below asks for such a value, and no param names it yet.",
            "",
        ]
        md += _table(
            ["stated value", "value", "source", "locator"],
            [
                [f"{v['evidence']}.{v['key']}", v["value"], v["source"], v["locator"]]
                for v in waits["values"]
            ],
        )
        md += _table(
            ["gap", "question", "close by"],
            [[g["gap"], g["question"] or "", g["ask"] or ""] for g in waits["gaps"]],
        )
    md += ["## Open gaps", ""]
    affected = {gap: [n for n, s in p.params.items() if s.get("gap") == gap] for gap in p.gaps}
    md += _table(
        ["gap", "question", "close by", "params"],
        [
            [gap, g.get("question", ""), g.get("ask", ""), ", ".join(affected[gap])]
            for gap, g in p.gaps.items()
            if waits is None or affected[gap]  # a known-first project lists the rest as waiting
        ],
    )
    if images:
        md += [
            "## Figure overlays",
            "",
            "Model edges (magenta) over the figure, scaled by the cited dimension (blue). Visual "
            "comparison only.",
            "",
            *(f"![{i.stem}](overlays/{i.name})" for i in images),
            "",
        ]
    md += ["## Findings", ""]
    md += [f"- **{f.level}** `{f.rule}`: {f.message}" for f in findings] or ["_None._"]
    (out / "report.md").write_text("\n".join(md) + "\n", encoding="utf8")

    data = {
        "status": status,
        "counts": headline,
        "findings": [asdict(f) for f in findings],
        # A result gives the keys that apply to its kind alone only where they do.
        "checks": [{k: v for k, v in asdict(r).items() if v is not None} for r in results],
        "build_seconds": build_seconds,
        "tolerances": tolerances,
        "overlap_limits": limits,
        "model_literals": literals,
        "exact": exact,
        "known_first": p.known_first,
        "waiting": waits,
        "motion": moves,
        "masses": None
        if model is None
        else {
            name: {
                "mass": m.mass,
                "from": {m.by: m.param},
                "center": list(m.center),
                "inertia": list(m.inertia),
            }
            for name, m in model.masses.items()
        },
        "params": {
            n: {"value": p.values.get(n), "rests_on": p.rests_on.get(n), **s}
            for n, s in p.params.items()
        },
        "bases": dict(bases),
        "rests_on_proposed": sorted(p.proposed),
        "measured": measured,
        "awaiting_confirmation": awaiting,
        "probes": p.probes,
    }
    (out / "report.json").write_text(json.dumps(data, indent=2, default=str), encoding="utf8")
    return out / "report.md"
